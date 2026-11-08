# Cadence

**Sense → Understand → Act** · UB Hacking 2026 · Research and demo prototype

Cadence is an AI-assisted, voice-guided health check-in project. The hackathon
MVP primarily focuses on Parkinson's disease: collect a comparable reading,
measure speech timing against that individual's reference recordings, and use a
repeatable difference to select a relevant question. The person's explanation
becomes a note with measured observations, patient-reported information, and
unresolved questions kept separate.

The repository is still named **CareCircle**. Earlier documents and code use
**VoiceShift** or **VoiceGuard**; the standalone UI is titled **Daily Hello
Family**. These names refer to the same project's iterations. File names,
imports, environment variables, database names, and API paths are retained for
compatibility. This documentation update changes no runtime behavior.

Cadence is **not a diagnostic medical device**. Public-dataset associations do
not establish clinical diagnostic accuracy or validate day-to-day monitoring of
an individual's health. A deviation score is an acoustic distance, not a disease
probability; a typical recording does not rule out a health concern.

## What is implemented

| Component | Actual implementation and verification |
| --- | --- |
| Audio input | FastAPI accepts uploaded WAV/WAVEX recordings. `soundfile`, PyTorch, and `torchaudio` prepare mono 16 kHz audio for pretrained Silero VAD. Invalid or speech-free recordings are rejected. Browser recording is not connected. |
| Timing measurements | Pause fraction, longest internal gap, and a passage-syllable-count / speech-duration rate estimate. Edge silence is excluded. The count is currently a **40-syllable placeholder**, not verified transcript content. |
| Personal baseline | Enrollment fits medians and scaled median absolute deviations from 3–5 reference takes. The Euclidean norm of robust feature z-scores is compared with prototype threshold 2.0; two consecutive elevated check-ins trigger a question. |
| Question selection | Four hard-coded prototype cards: initial and follow-up cards for `parkinsons` and `copd`. Selection is deterministic condition/cue lookup with substring matching, not an LLM, vector search, or a clinically reviewed adaptive engine. |
| Note and confirmation | `/answer` returns measured / patient-said / unresolved fields. `/confirm` changes the latest answered row's status; it does not authorize caregiver sharing. Only one answer is accepted per check-in. |
| Tiger Data | PostgreSQL/TimescaleDB via `psycopg`; `profiles` stores baselines and `checkins` is a hypertable. Prior scores rebuild tracker state per request. Transactions and profile row locks protect history and concurrent updates. |
| ElevenLabs | `/speak` sends text to the real ElevenLabs REST API and returns MP3 bytes. It supports voicing a question or reading a note back; it is not a complete voice-agent or phone integration. |
| Verification | 34 tests with a configured TimescaleDB test database, including real speech fixtures, storage across new app instances, concurrent requests, and mocked TTS errors. Previous setup also verified local and Tiger Cloud storage and a live ElevenLabs MP3 response. See [API verification notes](backend/app/api/README.md). |

The API supports both condition labels, but COPD question paths are prototype
software behavior without project-level COPD patient validation. Asthma has no
backend condition path. No population disease/severity classifier drives the
live API; those scripts and model artifacts are offline research.

## Frontend and remaining integration

[Daily Hello Family.html](Daily%20Hello%20Family.html) is a standalone HTML/CSS/
JavaScript caregiver dashboard with fictional sample conversations, SVG charts,
settings in browser `localStorage`, transcript entry, and local audio playback.
Optional summaries call the host's `window.claude.use("sample")` capability;
that capability is unavailable in a normal standalone browser.

The file has no `getUserMedia`, `MediaRecorder`, or requests to `/profiles/...`
or `/speak`. Its charts, sample health metrics, alerts, and transcript-derived
voice estimates are demo content, not measurements from the backend. Movement,
medication, asthma, and oxygen-related panels do not establish implemented or
validated monitoring for those conditions. Use fictional data only.

Still planned: browser capture/WAV encoding and API wiring, speech-to-text,
completed follow-up turns and note correction, a history API/UI, authenticated
patient/caregiver accounts, sharing permissions, notifications, and phone calls.
There is no integrated patient-to-caregiver end-to-end workflow yet.

## Run the actual backend

Python 3.10+ is required by the source syntax; Python 3.12 was used for the
recorded API verification. Run these commands from the repository root.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Create backend/.env from .env.example only if you do not already have one.
# Set TIGER_DATA_URL and ELEVENLABS_API_KEY privately in that file or the environment.
python -m uvicorn app.api.main:app --reload --port 8000
```

On macOS/Linux, activate with `source .venv/bin/activate`. The backend directory
is the working directory for `uvicorn app.api.main:app` and the test commands.
Open http://localhost:8000/docs to exercise real uploads and responses.

`TIGER_DATA_URL` must point to a TimescaleDB database (Tiger Cloud or local
PostgreSQL with the extension). Startup applies
[the schema](backend/app/api/schema.sql) idempotently when a URL is configured;
the role needs appropriate schema/extension permissions. Plain Postgres without
TimescaleDB is insufficient. Without a URL, storage routes return 503; docs
remain accessible. `/speak` independently needs `ELEVENLABS_API_KEY`. Optional
voice/model settings are in [backend/.env.example](backend/.env.example).

The local demo has permissive CORS and no authentication or authorization.
Do not expose it as a real patient service. Secrets, credential archives, and
real patient records must remain outside commits. Uploaded audio is temporary;
feature summaries, free-text answers, and note status persist in the database.
Text sent to `/speak` is transmitted to ElevenLabs.

## Existing API contract

All routes below are **POST**. The historical `/api/baseline`, `/api/checkin`,
`/api/ai/...`, and `/api/alerts` routes from earlier planning are not implemented.

| Route | Request | Response / behavior |
| --- | --- | --- |
| `/profiles/{profile_id}/enroll` | Multipart `files` (3–5 WAVs); `condition=parkinsons` or `copd` in form or query | `status`, `profile_id`, `n_reference_takes`; duplicate profile returns 409. |
| `/profiles/{profile_id}/checkin` | Multipart `file` (one WAV) | `profile_id`, `measured.deviation_score`, `measured.deviation_from_baseline`, `triggered_question`, `status` (`no_change` or `awaiting_answer`). Timing features are stored, not returned as separate response fields. |
| `/profiles/{profile_id}/answer` | JSON `{"answer_text":"I had trouble speaking"}` | Three-bucket `note` plus optional `follow_up_question`; requires the latest unanswered triggered row. A second answer returns 404. |
| `/profiles/{profile_id}/confirm` | No body | `{"status":"confirmed"}` for the latest answered note; does not publish or share it. |
| `/speak` | JSON `{"text":"What happened there?"}` | MP3 bytes with `audio/mpeg`; missing key 503, provider failure 502, timeout 504. |

See the [API build contract](VoiceShift-API-Spec.md) and
[implementation/setup notes](backend/app/api/README.md). The richer JSON in the
[demo brief](VoiceShift-Demo-Brief.md) is a UI proposal, not the live response.

## Tests and research

From `backend/`:

```powershell
python -m pytest tests/ -q
```

Set `TEST_TIGER_DATA_URL` to a dedicated TimescaleDB test database to enable all
34 tests. Three integration tests create and remove isolated schemas; without
the variable, they skip (31 pass / 3 skip when the remaining suite succeeds).
The TTS tests mock provider responses; a real provider smoke check is separate.
The short real-speech [fixture and attribution](backend/tests/fixtures/README.md)
verify software mechanics, not clinical effectiveness.

Dataset locations, download commands, reproduction commands, and committed
results are in [backend/data/README.md](backend/data/README.md). The
[project brief](VoiceShift-Project-Brief.md) retains research sources and the
corrected ItalianPVS task interpretation. In particular:

- MDVR-KCL has 16 PD / 21 control recordings for the reported read-speech
  comparison: mean pause fractions 0.328 / 0.233, nominal p≈0.008.
- The primary ItalianPVS **B1 continuous-passage** result uses **27 PD / 21
  controls actually analyzed**: pause fractions 0.265 / 0.196, nominal p≈0.044.
  Segment duration is borderline, p≈0.053; do not call it significant. The
  separate PR1/FB2 word-list result uses 28 / 22 and is secondary.
- The stored cross-dataset embedding result is AUC≈0.61 / 0.55 with permutation
  p≈0.20 / 0.34. It mixes language and task type. A B1 task-matched rerun script
  exists, but its output is not committed in the reviewed snapshot.
- Classifier results, severity correlations, and bootstrap/permutation outputs
  are exploratory offline evidence. Small samples, recording/age confounding,
  preprocessing and resampling review, and independent prospective validation
  remain necessary. No reported AUC is a patient probability.
- The team did not verify a COPD speech dataset satisfying its requirements
  during the documented search. Some evaluated sources were gated, non-speech,
  feature-only, or had uncertain labels/access/reuse terms. This is a limitation
  of that search and those sources, not proof that no public COPD dataset exists.

## Architecture, roadmap, and team work

The [Cadence architecture and research roadmap](docs/CADENCE-ARCHITECTURE-ROADMAP.md)
distinguishes working components from the proposed Adaptive Clinical Question
Engine, Clinical Question Library, multimodal context, and consent-based
caregiver reporting. COPD, asthma, and other disease extensions need separate
condition-specific validation; calibrated disease probabilities are not a
current feature or an approved next-step assumption.

Actual repository layout:

```text
README.md
Daily Hello Family.html          Standalone demo dashboard
VoiceShift-*.md                 Existing briefs, API spec, prompts, and log
backend/
  app/api/                     FastAPI routes, TimescaleDB schema, setup notes
  app/audio/                   VAD, timing, offline voice-quality extraction
  app/dialogue/                Prototype cards and three-bucket notes
  app/models/                  Personal baseline plus offline research scripts
  app/pipeline.py              Shared analysis and answer processing
  data/                        Dataset guide and committed research outputs
  tests/                       Audio, baseline, dialogue, pipeline, and API tests
docs/CADENCE-ARCHITECTURE-ROADMAP.md
research/italianpvs/            Six-participant descriptive audio-graph pilot
```

The original three-person responsibilities remain useful: frontend/UX owns the
capture and patient/caregiver experience; audio/backend owns measurement,
baselines, persistence and API integration; conversation/research owns prototype
cards, evidence interpretation and note policy. Coordinate changes to these
areas with teammates. Earlier `frontend/**`, `backend/ai/**`, `data/research.json`
and Gemini setup paths were proposed allocations, not present implementations.
Git history preserves the individual contributions and prior designs.

Fetch before coordinating changes. Work on a focused feature branch, stage only
intended files, and open a pull request to `main`; do not force-push or merge
without review. [The project log](VoiceShift-LOG.md) records historical findings
and pending work; its newest audit takes precedence over older session notes.
