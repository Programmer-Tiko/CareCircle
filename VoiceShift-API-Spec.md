# VoiceShift API — build spec

Wraps the already-built, already-tested pipeline in `backend/app/pipeline.py` as a minimal HTTP API, so the UI (`Daily Hello Family.html`, or whatever it becomes) can call something real instead of only the mock JSON in `VoiceShift-Demo-Brief.md`.

**Everything underneath the API is done and tested (21/21 tests passing).** This spec is only about the HTTP layer on top: endpoints, request/response shapes, and where to store per-profile state. Don't modify `app/audio/`, `app/dialogue/`, `app/models/`, or `app/pipeline.py` — call them, don't rewrite them. If something there seems to be missing a capability, ask rather than reworking it.

## Before you start

```
cd backend
git pull   # make sure you have the latest -- pipeline.py was just refactored
pip install -r requirements.txt   # fastapi, uvicorn, python-multipart just added
python -m pytest tests/ -q   # confirm 21 passed before you add anything
```

## What already exists (read, don't rewrite)

- `app/pipeline.py`:
  - `build_take_from_audio(wav_path: str, passage_syllable_count: int) -> dict` — runs VAD + timing features on one recording, returns `{pause_fraction, longest_internal_gap, speaking_rate}`.
  - `evaluate_checkin(wav_path, baseline, tracker, condition, passage_syllable_count) -> CheckinResult` — scores a check-in against a fitted baseline. `CheckinResult` has `.triggered: bool`, `.deviation_score: float`, `.question_text: str | None`.
  - `process_answer(condition, deviation_score_value, answer_text) -> (Note, follow_up_question: str | None)` — classifies the patient's answer, returns the assembled note and a follow-up question if one fired.
- `app/models/personal_baseline.py`:
  - `fit_baseline(reference_takes: list[dict]) -> BaselineStats` — needs at least 3 takes (dicts shaped like `build_take_from_audio`'s output).
  - `PersistentDeviationTracker(threshold: float, required_consecutive: int)` — stateful; call `.observe(score)` each check-in. Use `threshold=2.0, required_consecutive=2` as defaults (what's been tested).
- `app/dialogue/note.py`: `Note` has `.measured`, `.patient_said`, `.unresolved`, `.status`, and `.to_dict()`.

`condition` is always `"copd"` or `"parkinsons"`. `passage_syllable_count` is a fixed int per the standard passage — use `40` as a placeholder (the Rainbow Passage excerpt's actual count isn't pinned down yet; make it a constant in one place so it's a one-line fix later).

## State storage

In-memory, process-local dict keyed by `profile_id`. No database, no persistence across server restarts — this is explicitly fine for the hackathon demo; don't build more than this.

```python
# something like this, in its own module (e.g. app/api/state.py)
@dataclass
class ProfileState:
    condition: str
    baseline: BaselineStats | None = None
    tracker: PersistentDeviationTracker = field(default_factory=lambda: PersistentDeviationTracker(2.0, 2))
    pending_deviation_score: float | None = None  # set when a check-in triggers, used by /answer

PROFILES: dict[str, ProfileState] = {}
```

## Endpoints

Use FastAPI. One router file (e.g. `app/api/main.py`) is fine for this scope — don't over-structure it.

### `POST /profiles/{profile_id}/enroll`
Multipart form upload, field name `files`, 3–5 wav files (the reference takes). Also takes `condition` (`"copd"` | `"parkinsons"`) as a form field or query param.

- For each uploaded file: save to a temp path, call `build_take_from_audio`, collect the dicts.
- Call `fit_baseline(takes)`.
- Store a new `ProfileState(condition=condition, baseline=baseline)` in `PROFILES[profile_id]`.
- Response: `{"status": "enrolled", "profile_id": "...", "n_reference_takes": 4}`
- If fewer than 3 files: 400 with a clear error (matches `fit_baseline`'s own `ValueError` — just catch and translate it to an HTTP error, don't change the validation logic itself).

### `POST /profiles/{profile_id}/checkin`
Multipart form upload, field name `file`, one wav (today's reading).

- 404 if `profile_id` not enrolled.
- Call `evaluate_checkin(path, state.baseline, state.tracker, state.condition, PASSAGE_SYLLABLE_COUNT)`.
- If `triggered`: store `state.pending_deviation_score = result.deviation_score` (the `/answer` endpoint needs this next).
- Response shape, matching `VoiceShift-Demo-Brief.md`'s mock JSON as closely as possible:
```json
{
  "profile_id": "demo-copd-1",
  "measured": {
    "deviation_score": 2.4,
    "deviation_from_baseline": "persistent"
  },
  "triggered_question": "What happened during that pause?",
  "status": "awaiting_answer"
}
```
When not triggered, `triggered_question` is `null` and `status` is `"no_change"`.

### `POST /profiles/{profile_id}/answer`
JSON body: `{"answer_text": "I stopped to catch my breath"}`.

- 404 if `profile_id` not enrolled or has no pending check-in (no `pending_deviation_score` set) — this means `/answer` was called without a preceding triggered `/checkin`.
- Call `process_answer(state.condition, state.pending_deviation_score, answer_text)`.
- Clear `state.pending_deviation_score` after this call (one answer resolves one pending check-in; a returned follow-up question is communicated to the caller, but re-asking it is a second full `/answer` call with the new reply, not special-cased state).
- Response:
```json
{
  "note": {
    "measured": "Longer pauses than your usual pattern, repeated across this check-in.",
    "patient_said": "I stopped to catch my breath",
    "unresolved": ["What caused the change is still unclear."],
    "status": "awaiting_confirmation"
  },
  "follow_up_question": "Is that more frequent than usual, and what were you doing at the time?"
}
```
`follow_up_question` is `null` when there's nothing more to ask.

### `POST /profiles/{profile_id}/confirm`
No body needed for now (there's no stored note object to mutate server-side yet — the UI holds the note after `/answer` and confirms its own copy). Response: `{"status": "confirmed"}`. This is intentionally thin; don't build note persistence beyond this unless asked.

## Testing it yourself

```bash
uvicorn app.api.main:app --reload --port 8000
# in another terminal:
curl -F "files=@ref1.wav" -F "files=@ref2.wav" -F "files=@ref3.wav" "http://localhost:8000/profiles/demo-1/enroll?condition=copd"
curl -F "file=@today.wav" http://localhost:8000/profiles/demo-1/checkin
curl -X POST -H "Content-Type: application/json" -d '{"answer_text":"I stopped to catch my breath"}' http://localhost:8000/profiles/demo-1/answer
```
FastAPI gives you free interactive docs at `http://localhost:8000/docs` — use that to sanity-check the shapes visually instead of only curl.

If you don't have real wav files handy to test with: `backend/tests/fixtures/speech_chunk.wav` is a 1-second real speech clip (see its own README for attribution) — not long enough to be a realistic check-in, but enough to confirm the endpoints don't crash on real audio input.

## What NOT to build

No auth, no database, no deployment config, no HTTPS, no rate limiting, no phone/Twilio integration (that's a separate, deprioritized track). CORS: add permissive CORS (`allow_origins=["*"]`) since this is a local demo, not a security review.

## When you're done

Run the test suite once more (`python -m pytest tests/ -q`) to confirm nothing in the existing code broke, then commit and push to `main` as usual. Leave a note in your commit message about which endpoints are done if you don't finish all four — partial is fine, just be clear about what works.
