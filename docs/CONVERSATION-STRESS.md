# Conversation persistence stress run

Run with the existing backend virtual environment, from the repository root:

```sh
TEST_CONVERSATION_DB_URL=postgresql:///postgres backend/.venv/bin/python backend/scripts/stress_conversations.py --output docs/CONVERSATION-STRESS-RESULTS.json
```

The runner starts an actual Uvicorn listener on an ephemeral localhost port and
uses HTTP requests and real PostgreSQL transactions. It creates a unique test
schema and removes it on completion or assertion failure. Cloud credentials,
existing profiles and existing schemas are not modified. Ordinary PostgreSQL
is sufficient for these conversation tables; this does not test TimescaleDB
hypertable behavior. Check-ins are seeded, not synthesized from patient audio.

The actual corpus, metadata filtering, lexical ranking, selector adapter,
validation, and API are exercised. Only the model call is replaced by a
reproducible choice from the offered eligible IDs. No external model is called,
and the exercise does not evaluate clinical usefulness of the questions.
The output records corpus version and SHA-256 and rejects mid-run corpus edits.

Observed result: five sessions and 50 answered turns persisted. Two check-ins
for the same profile each completed 12 turns with disjoint histories and turn
IDs. Every answer was retried without creating another revision or turn. The
same submission UUID was allowed independently in both sessions; attempting to
answer one session's turn through the other session returned 404. Confirming
one session did not change the other, and stale revisions were rejected.

With a changed, situational-distraction answer, the eligible set exhausted after
two answers, even though most corpus units remained unasked. The session
completed with no pending turn. This is eligibility exhaustion, not evidence
that all corpus topics were discussed. Two medication-gated units also remain
ineligible throughout the long runs because medication status is unavailable.

In two further 12-turn runs, an explicitly unresolved earlier turn or current
turn prevented completion at exhaustion: both became `abstained` and retained
unresolved information. Confirming that note preserved the uncertainty.

## Limits found

The state-layer completion guard works for persisted resolution flags. The
adapter currently sets `resolved=True` for a validated question selection, and
also returns `complete/resolved=True` when no eligible units remain. Neither
operation assesses whether the patient's answer actually resolves the question.
Therefore this run verifies bookkeeping, not semantic resolution. If that
stronger guarantee is required, the selector contract needs an explicit,
validated answer-resolution decision independent of retrieval exhaustion.

A previously unresolved turn also has no correction/re-resolution route today.
Later answers cannot resolve it; exhaustion produces terminal abstention. This
is conservative behavior but a limitation for future recovery conversations.

The corpus changed during initial execution (a safety notice was added without
a corpus version bump). The final completed run hashes the stable 14-unit
snapshot. No teammate-owned corpus or dialogue implementation was changed.
