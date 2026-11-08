# Cadence API — existing build contract (formerly VoiceShift)

Status review, November 8, 2026: the five routes below are implemented in
`backend/app/api/main.py`. This document retains their existing paths, request
fields, response examples, and storage contract. It is not an assertion that the
standalone HTML dashboard calls them. See [current setup/status](README.md) and
[the future architecture](docs/CADENCE-ARCHITECTURE-ROADMAP.md).

The current hackathon emphasis is Parkinson's. Both `parkinsons` and `copd`
remain accepted condition labels, with prototype question cards; this is not
clinical validation of either condition's monitoring use case. Browser capture,
transcription, caregiver authorization, report sharing, a history route, and an
adaptive clinical engine are not implemented by this contract. A returned
follow-up is text only: the one-answer rule below prevents a second answer to
that check-in. Confirmation changes status, not sharing permission.

The original instructions below describe the completed API build and are kept
for integration context. For current verification use
[backend/app/api/README.md](backend/app/api/README.md): 34 tests with a configured
TimescaleDB test database, including the original 21 pipeline tests.

Wraps the already-built, already-tested pipeline in `backend/app/pipeline.py` as a minimal HTTP API, so the UI (`Daily Hello Family.html`, or whatever it becomes) can call something real instead of only the mock JSON in `VoiceShift-Demo-Brief.md`.

**This build also targets two MLH prize tracks, and both are genuine fits, not bolted on:**
- **Best Use of Tiger Data** — VoiceShift's whole mechanism is time-series by nature (daily check-ins, personal baselines built from history, deviation tracked over time), so Tiger Data (TimescaleDB/PostgreSQL) replaces the in-memory storage below — see the State storage section.
- **Best Use of ElevenLabs** — the brief's caregiver workflow already calls for reading the proposed report back for confirmation; ElevenLabs voicing the follow-up question and the note read-back turns the check-in into an actual spoken conversation instead of a text quiz — see the Voice synthesis section.

Priority order if you don't finish everything: **core endpoints first** (enroll/checkin/answer/confirm, working against Postgres), **then** ElevenLabs voice synthesis. Partial is fine either way, per the note at the bottom — just be clear in your commit message about what's done.

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

## State storage — Tiger Data (TimescaleDB / PostgreSQL)

Not in-memory. Sign up for a free Tiger Cloud instance (search "Tiger Data" / "TimescaleDB cloud free tier" to find the current signup page — don't guess a URL, find the real one) and get a connection string. If that signup has any friction, a local Postgres with the `timescaledb` extension works identically for this scope; either way the schema below is the same.

Two tables: `profiles` (one row per enrolled person, holds the fitted baseline) and `checkins` (one row per check-in, a **hypertable** — this is the actual time-series data the prize track is about, and it's also genuinely useful: it's what a real "history" view would query, and it's how `PersistentDeviationTracker`'s "N consecutive" logic can be rebuilt from the last few rows instead of living only in process memory).

```sql
CREATE TABLE profiles (
    profile_id TEXT PRIMARY KEY,
    condition TEXT NOT NULL,
    baseline_median JSONB,
    baseline_mad JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE checkins (
    time TIMESTAMPTZ NOT NULL DEFAULT now(),
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
    pause_fraction DOUBLE PRECISION,
    longest_internal_gap DOUBLE PRECISION,
    speaking_rate DOUBLE PRECISION,
    deviation_score DOUBLE PRECISION,
    triggered BOOLEAN,
    question_text TEXT,
    patient_said TEXT,
    note_status TEXT
);
SELECT create_hypertable('checkins', 'time');
```

`baseline_median`/`baseline_mad` store `BaselineStats.median` / `.mad` (both are already plain dicts, so `json.dumps` them straight into the `JSONB` columns). Use `psycopg` (sync, simplest to wire into FastAPI handlers for this scope — no need for an async driver here) for the connection. Keep the connection string in an environment variable, never committed — add a `.env.example` with a placeholder, and make sure `.env` itself is gitignored (check `backend/.gitignore`, add it if it's missing).

Rebuild `PersistentDeviationTracker`'s consecutive-hit state per request by querying the most recent `required_consecutive` rows for that `profile_id` from `checkins` and replaying `.observe()` on their stored `deviation_score` values, rather than keeping a tracker object alive in memory between requests — this is what makes the design actually stateless/restart-safe, which is the whole point of using a real database here instead of a dict.

## Endpoints

Use FastAPI. One router file (e.g. `app/api/main.py`) is fine for this scope — don't over-structure it.

### `POST /profiles/{profile_id}/enroll`
Multipart form upload, field name `files`, 3–5 wav files (the reference takes). Also takes `condition` (`"copd"` | `"parkinsons"`) as a form field or query param.

- For each uploaded file: save to a temp path, call `build_take_from_audio`, collect the dicts.
- Call `fit_baseline(takes)`.
- `INSERT` a row into `profiles` (`profile_id`, `condition`, `baseline_median`, `baseline_mad`).
- Response: `{"status": "enrolled", "profile_id": "...", "n_reference_takes": 4}`
- If fewer than 3 files: 400 with a clear error (matches `fit_baseline`'s own `ValueError` — just catch and translate it to an HTTP error, don't change the validation logic itself).

### `POST /profiles/{profile_id}/checkin`
Multipart form upload, field name `file`, one wav (today's reading).

- 404 if `profile_id` has no row in `profiles`.
- Load `BaselineStats` back from the `profiles` row. Rebuild the tracker by replaying the last `required_consecutive` `checkins` rows for this profile (see the State storage section) rather than holding a tracker object across requests.
- Call `evaluate_checkin(path, baseline, tracker, condition, PASSAGE_SYLLABLE_COUNT)`.
- `INSERT` the result into `checkins` (the timing features from `build_take_from_audio`, the `deviation_score`, `triggered`, `question_text`) — every check-in gets a row, triggered or not, since that history is what makes the tracker rebuild actually work and is also the real time-series data for a history view.
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

- 404 if `profile_id` has no row in `profiles`, or if the most recent `checkins` row for this profile isn't `triggered`, or `note_status` on that row is already set (already answered) — any of those means there's no pending question to answer right now.
- Read `condition` and the most recent row's `deviation_score` from the DB, then call `process_answer(condition, deviation_score, answer_text)`.
- `UPDATE` that `checkins` row with `patient_said` and `note_status` (no separate "pending" flag needed — the most-recent-triggered-row-with-no-answer-yet check above does that job).
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
No body needed. `UPDATE` the most recent `checkins` row for this profile, setting `note_status = 'confirmed'`. Response: `{"status": "confirmed"}`.

## Testing it yourself

Needs `TIGER_DATA_URL` (the Postgres connection string) and, once you get to that section, `ELEVENLABS_API_KEY` set in the environment (or a `.env` file loaded via `python-dotenv` — add it to requirements if you use it).

```bash
uvicorn app.api.main:app --reload --port 8000
# in another terminal:
curl -F "files=@ref1.wav" -F "files=@ref2.wav" -F "files=@ref3.wav" "http://localhost:8000/profiles/demo-1/enroll?condition=copd"
curl -F "file=@today.wav" http://localhost:8000/profiles/demo-1/checkin
curl -X POST -H "Content-Type: application/json" -d '{"answer_text":"I stopped to catch my breath"}' http://localhost:8000/profiles/demo-1/answer
```
FastAPI gives you free interactive docs at `http://localhost:8000/docs` — use that to sanity-check the shapes visually instead of only curl.

If you don't have real wav files handy to test with: `backend/tests/fixtures/speech_chunk.wav` is a 1-second real speech clip (see its own README for attribution) — not long enough to be a realistic check-in, but enough to confirm the endpoints don't crash on real audio input.

## Voice synthesis (ElevenLabs)

After the core endpoints work, add one small addition: voicing text via ElevenLabs. Sign up for a free ElevenLabs account (search for the current signup page, don't guess a URL) and get an API key — their free tier's character quota is enough for a hackathon demo. Keep the key in an environment variable, same as the Postgres connection string, never committed.

Add a `POST /speak` endpoint: JSON body `{"text": "..."}`, calls ElevenLabs' text-to-speech REST API (a single POST to their `text-to-speech/{voice_id}` endpoint with the API key in a header, picking any one of their stock voices is fine), and returns the audio bytes directly with `media_type="audio/mpeg"` — no need to save it anywhere, stream it straight through.

This is intentionally generic (any text in, audio out) rather than baked into `/checkin` or `/answer` specifically — the UI calls `/speak` with whatever text it wants voiced: the triggered question, the follow-up question, or the note's `measured`/`patient_said` text read back for confirmation (the brief's caregiver workflow already calls for reading the report back before approval — this is that, for real).

## What NOT to build

No auth, no deployment config, no HTTPS, no rate limiting, no phone/Twilio integration (that's a separate, deprioritized track — ElevenLabs here is for voicing the web/app check-in, not for placing calls). CORS: add permissive CORS (`allow_origins=["*"]`) since this is a local demo, not a security review.

## When you're done

Run the test suite once more (`python -m pytest tests/ -q`) to confirm nothing in the existing code broke, then commit and push to `main` as usual. Leave a note in your commit message about which endpoints are done if you don't finish all four — partial is fine, just be clear about what works.
