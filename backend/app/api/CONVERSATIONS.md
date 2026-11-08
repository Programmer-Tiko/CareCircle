# Durable conversation integration

This opt-in API supplements the five legacy routes. Restart the backend to apply
`schema.sql`'s additive, idempotent tables/indexes. Existing check-in rows and
legacy flows remain intact. The check-in response now also returns
`checkin_time` (an ISO timestamp); keep that exact value to start a conversation.

## HTTP flow

1. `POST /profiles/{profile}/conversations` with
   `{"checkin_time":"<exact timestamp returned by checkin>"}` creates a session
   for an unanswered triggered check-in. Repeating the start returns the same
   session. It snapshots the existing prototype initial question and raw measured
   features/aggregate score. It does not manufacture per-feature z-scores.
2. `GET /profiles/{profile}/conversations/{session_id}` restores session, note,
   revision and ordered turns after reload/restart.
3. `POST /profiles/{profile}/conversations/{session_id}/turns/{turn_id}/answer`
   with `{"submission_id":"<client-generated UUID>","answer_text":"..."}`
   answers that exact turn. Repeating the same ID/text/turn is idempotent and
   returns current session state, not a historical response. Changed text or a
   reused ID on another turn returns 409. An ask decision appends the next turn.
4. `POST /profiles/{profile}/conversations/{session_id}/confirm` with
   `{"revision":2}` confirms that exact reviewed note revision. An outstanding
   question or stale revision returns 409. Confirmation is idempotent. It does
   not grant sharing permission.

All successful responses are session snapshots with ordered `turns`. Each turn
stores question ID/version/text, source ID/version pairs, asked/answered
 timestamps, answer, resolution flag, submission ID, and selection decision.
Answered, resolved and session complete are distinct states. Abstention ends
questioning but leaves unresolved information visible and confirmable; it does
not mark the conversation complete. Confirmation preserves unresolved content.

Once opted in, legacy `/answer` and `/confirm` reject that check-in with 409.
New check-ins do not retarget an existing conversation. Multiple sessions remain
bound to their original measurements. Tables intentionally reference profiles
and store the exact check-in timestamp rather than imposing a new foreign key
on the existing Timescale hypertable.

## Selector adapter boundary

`get_selector` in `conversations.py` returns a synchronous callable. Wire the
validated corpus adapter with:

```python
application.dependency_overrides[get_selector] = lambda: validated_selector
```

Input: `condition`, immutable `measured` snapshot, ordered `turns` (before the
current answer is written), and `answer_text` for the current answer.

Output conforms to `Selection`:

```json
{
  "decision": "ask",
  "resolved": true,
  "question": {
    "id": "communication-impact",
    "version": "1",
    "text": "Where have you noticed it?",
    "sources": [{"id": "curated-excerpt-12", "version": "1"}]
  }
}
```

`resolved` refers to the just-answered turn, not the whole conversation.
`complete` and `abstain` must omit the question. Completion requires the current
and all earlier answers to be resolved. Repeated question IDs, invalid outputs
and selector exceptions fall back to abstention, preserving the answer.

The adapter must enforce corpus membership, source eligibility, quote checking,
question eligibility and a bounded provider timeout before returning. Pydantic
validation enforces shape, not groundedness. Selection happens under the profile
transaction lock to serialize duplicate answers; keep provider calls short.
The default adapter always abstains; no Gemini integration is claimed.

The persisted note currently contains structured measured evidence, verbatim
answers, and a conservative unresolved marker. It does not call the legacy note
builder or imply feature-specific explanations. The dialogue owner's new note
builder and per-feature z-score field still need explicit wiring after their
contracts land. Source versions on the initial question identify the existing
prototype dialogue policy, not clinical review.

## Verification

`TEST_CONVERSATION_DB_URL=postgresql:///your_test_db python -m pytest tests/test_conversations.py -q`

Tests use isolated PostgreSQL schemas removed afterward. They cover actual SQL,
fresh-app recovery, question snapshots, concurrent answers, duplicate submissions,
profile isolation, stale confirmation, provider failure and the additive check-in
timestamp. These tables do not need TimescaleDB; the existing API integration
suite still independently requires `TEST_TIGER_DATA_URL` for hypertable behavior.
