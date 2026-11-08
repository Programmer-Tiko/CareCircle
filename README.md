# Cadence

**Sense → Understand → Act.** A Parkinson's voice self-check prototype for UB Hacking.

Read the same passage, compare speech timing against your own reference takes,
and use a repeatable difference to open a sourced conversation. Measured audio,
your answers, corrections and unresolved information stay distinct.

## Open the integrated app

From the repository root on macOS/Linux:

```bash
./run-cadence.sh
```

Open **http://localhost:8000**. The API serves the integrated
`Daily Hello Family.html` and `frontend/` assets directly. It preserves the
teammate's purple rounded-card visual style, with all fictional family records,
health scores, disease tabs, medication/oxygen panels and pretend calls removed.
No separate frontend build or npm runtime is required.

The launcher uses `backend/.venv-asr` if present (local voice recognition),
otherwise `backend/.venv` (recordings plus typed answers). Keep your existing
`backend/.env`; never commit credentials. Set TIGER_DATA_URL for TimescaleDB
and ELEVENLABS_API_KEY for optional question/note speech. GROQ_API_KEY enables
validated question selection. Without ASR, typed answers remain fully usable.

For another OS, launch from backend with your Python environment:

```bash
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

This is an unauthenticated local demo: use fictional profile IDs and consenting
recordings. Confirmation saves a reviewed note; it does not share it with anyone.

## What the app does

1. Connect a new fictional profile or reuse an enrolled profile.
2. Record and preview 3–5 clean reference readings of the displayed passage.
3. Record a check-in. WAV conversion happens in the browser, then the real API
   compares pause fraction, longest internal gap, passage-rate estimate, and
   mean speech-burst duration with the personal median/MAD baseline.
4. Two consecutive elevated readings open a question. The LLM selects an
   eligible sourced template; validation prevents free-form question text.
5. Type an answer or record it locally, review/edit the transcript, then send.
   Follow-ups persist across reloads. Questions and notes can be read aloud.
6. Review the measured / you said / still unclear note, add a correction, and
   confirm its revision. Finish for now preserves unanswered questions and
   uncertainty instead of forcing a long conversation.
7. See actual saved check-ins/notes in history. Add an exact-word personal note
   even when the acoustic trigger does not fire.

Experimental observations are included by default in the UI. Enrollment builds
separate personal pitch-range and voiced-energy-variation references when at
least three usable takes exist. Check-ins display raw measurements and their
reference differences, along with capture flags. **These do not contribute to
the timing trigger, diagnose disease, or identify the cause of a change.**

The passage is the first two Rainbow Passage sentences, fixed at 41 syllables
under the documented convention in `backend/app/passage.py`. ASR can optionally
verify transcript similarity before enrollment/check-in scoring. Mismatched or
uncertain verified uploads are rejected before a new check-in is stored. A
matching transcript does not prove device/audio comparability or health status.

## Fresh setup

Core Python environment (Python 3.11 recommended):

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
# Create backend/.env from backend/.env.example ONLY if you do not have one.
```

Optional local speech recognition uses a separate compatible environment:

```bash
python3.11 -m venv backend/.venv-asr
backend/.venv-asr/bin/python -m pip install \
  -r backend/requirements.txt -r backend/requirements-asr.txt
```

Install ffmpeg on the host and provide an existing Whisper checkpoint at
`~/.cache/whisper/base.pt`. The runtime loads that exact local file; it never
silently downloads weights. `CADENCE_ASR_ENABLED=true` enables local recognition;
`CADENCE_WHISPER_MODEL=base` selects the checkpoint. The launcher enables ASR
when using `.venv-asr`; you can explicitly set CADENCE_ASR_ENABLED=false.

TimescaleDB is required for normal storage routes. Startup applies the additive
schema idempotently. Existing three-feature profiles require a new enrollment
under a new profile ID; old records are preserved. The UI reports unavailable
services rather than inventing sample records or synthetic health results.

## Verification and research

Run from backend:

```bash
python -m pytest tests/ -q
```

TEST_TIGER_DATA_URL enables the isolated TimescaleDB integration tests;
TEST_CONVERSATION_DB_URL enables ordinary PostgreSQL conversation/UI tests.
Optional real-model tests require CADENCE_ASR_SMOKE=1 and a cached checkpoint.
Browser QA uses installed Chrome and an optional Playwright package. See
`docs/UI-INTEGRATION-VERIFICATION.md` for the actual verification results.

- [API contract](VoiceShift-API-Spec.md) — legacy routes retained; new UI uses
  durable sessions, history, transcription and revision-safe note operations.
- [Conversation contract](backend/app/api/CONVERSATIONS.md).
- [Research brief](VoiceShift-Project-Brief.md) and [dataset reproduction](backend/data/README.md).
- [Multisignal artifact audit](docs/CCR-MULTISIGNAL-ARTIFACT-AUDIT.md).
- [Project history and handoff](VoiceShift-HANDOFF-TO-CODEX.md).

The corrected CCR experiment found within-cohort AUC improvement with prosody,
but less than 0.01 transfer improvement. It does not establish incremental
clinical or longitudinal monitoring value. Personal acoustic distance is not a
disease probability. Zero flags are not proof of a trustworthy recording.

Not implemented: authenticated patient/caregiver accounts, caregiver sharing,
notifications, outbound phone calls, prospective clinical monitoring validation,
or treatment decisions. The integrated UI does not pretend these exist.
