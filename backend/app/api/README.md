# Cadence HTTP API (legacy VoiceShift module)

The project is now named Cadence; `app.api.main`, environment names, database
schema and HTTP paths remain unchanged. The current MVP primarily focuses on
Parkinson's, while the accepted `copd` label selects prototype dialogue cards.
See [current repository status](../../../README.md) and
[planned architecture](../../../docs/CADENCE-ARCHITECTURE-ROADMAP.md).

This is the backend API, not a completed browser/caregiver workflow. The
standalone HTML dashboard has no calls to these routes or microphone capture.
Authentication, consent/sharing enforcement, history access and multi-turn
follow-up persistence remain future work. None of the existing cards is marked
clinically approved, and no trained disease model is called by these endpoints.

From `backend/`:

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in TIGER_DATA_URL and optionally ELEVENLABS_API_KEY in .env.
python -m uvicorn app.api.main:app --reload --port 8000
```

Open http://localhost:8000/docs for enrollment, check-in, answer, confirmation,
and `/speak`. Enrollment accepts `condition` either in the query or multipart
form, with 3–5 `files`. Check-in accepts one `file`. Both accept WAV audio up
to 20 MiB per recording. An existing profile returns 409 on re-enrollment;
its baseline and history are preserved.

The API calls the existing pipeline unchanged. The passage syllable placeholder
is `PASSAGE_SYLLABLE_COUNT = 40` in main.py. Every check-in is stored, including
untriggered ones. Prior scores are replayed in chronological order for every
request. A database row lock serializes operations for each profile. Answer and
confirm update only the latest check-in by `(profile_id, time)`. Confirmation
requires an answered note; confirming an already confirmed latest note is
idempotent. The spec permits one answer per check-in: the returned follow-up is
available for the UI, but a second `/answer` is rejected. A follow-up-answer
workflow is outside this endpoint contract.

`schema.sql` installs TimescaleDB, creates the two spec tables, converts
`checkins` into a hypertable and adds a profile/time index. Initialization is
idempotent at startup when `TIGER_DATA_URL` is set. The database role must be
able to create the extension/tables (or have an administrator initialize them).
There is no in-memory or SQLite fallback. Without a URL, docs and speech remain
available and storage endpoints return 503. Connection/SQL errors are sanitized.

## Service setup

Current official Tiger Cloud setup and connection documentation:

- https://www.tigerdata.com/docs/get-started/quickstart/create-service
- https://www.tigerdata.com/docs/integrate/find-connection-details
- https://console.cloud.timescale.com/

Create a free TimescaleDB service, copy its Postgres URL to `TIGER_DATA_URL`,
and retain the service's TLS parameters. The spec also permits a local database
with the TimescaleDB extension. Plain Postgres without TimescaleDB is insufficient.
Both database URLs and API keys belong only in your environment or ignored `.env`.

ElevenLabs setup: https://elevenlabs.io/docs/eleven-api/quickstart/
API contract: https://elevenlabs.io/docs/api-reference/text-to-speech/convert

`POST /speak` accepts `{"text":"What happened during that pause?"}` and returns
MP3 bytes directly, without saving audio. Set `ELEVENLABS_API_KEY`; the default
voice is the stock George voice from the provider's example. Override it with
`ELEVENLABS_VOICE_ID`, and optionally override `ELEVENLABS_MODEL_ID`. Missing
credentials return 503, provider failures 502, and timeouts 504. No fake audio
is substituted when the provider is unavailable.

## Tests

```powershell
python -m pytest tests/ -q
```

To include the three real-database integration tests, set `TEST_TIGER_DATA_URL`
to a dedicated TimescaleDB database before running that command (or set it in
backend/.env). Each test creates and drops its own unique schema. These tests
exercise actual WAV uploads and the real VAD/baseline/dialogue pipeline, verify
hypertable storage, a fresh application instance reconstructing tracker state,
profile isolation, invalid/silent uploads, and concurrent check-ins/answers.
Without this variable they explicitly skip; the other tests still run.
ElevenLabs HTTP behavior is tested using mocked provider responses; a live
synthesis check additionally needs a real key and consumes provider quota.

Implementation verification: the unchanged baseline suite passed 21 tests before
the API work. The completed suite passed 34 tests with the real database tests
enabled against both local TimescaleDB 2.31.0 / PostgreSQL 17 and a free shared
Tiger Cloud service running TimescaleDB 2.31.0 / PostgreSQL 18. Startup
initialization was run twice and `checkins` was verified in
`timescaledb_information.hypertables` on both databases. The cloud integration
tests exercised the same real-audio flow, fresh-app persistence, and concurrent
requests as the local tests, using isolated schemas removed after each test.
Live ElevenLabs synthesis was also verified: `/speak` returned HTTP 200,
`audio/mpeg`, and 41,838 bytes for a short non-patient demo sentence. Credentials
and the cloud connection string remain in ignored backend/.env only. The prior
local URL is preserved there as `LOCAL_TIGER_DATA_URL` for manual fallback; the
API itself always uses `TIGER_DATA_URL` and never silently switches databases.
