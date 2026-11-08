# Integrated UI verification — November 8, 2026

## Implemented

Updated the actual teammate UI from GitHub (`Daily Hello Family.html`), retaining
its purple/white rounded-card design and typography. Removed fictional family
records, health gauges, disease tabs, medication/oxygen panels, sample charts,
host-Claude summaries and nonfunctional phone/caregiver flows.

The app now serves from FastAPI at `/` with no frontend build step:

- Browser microphone -> MediaRecorder -> true mono PCM WAV, preview, 3–5-take
  enrollment and current-passage check-ins.
- Four real timing measurements; separate optional pitch/energy observations
  with personal-reference differences, unavailable states and quality flags.
- Optional locally cached Whisper for passage verification and reviewed answers.
  ASR does not auto-send. Phrase match is not overall capture comparability.
- Live sourced template selection, durable turns, reload recovery, manual question
  playback and full note readback, corrections and revision-specific confirmation.
- Finish for now keeps unanswered question snapshots and uncertainty.
- Exact-word personal reports without an acoustic trigger, and real stored history.
- Only connection/profile/session IDs in localStorage; no synthetic patient data.

Three independently reviewed communication candidates were promoted into corpus
v3 with exact evidence spans and snapshot source links. Sleepiness/fatigue/off-time
proposals remain blocked. Context rules now handle tested negation, symptom
memory, direct voice reports and recording-vs-everyday noise distinctions. These
are finite language rules, not clinically validated semantic understanding.

## Actual tests

**243 passed, no skips** in the final Python 3.11 run, with real isolated Tiger
Cloud/local PostgreSQL integrations and both optional real cached-model ASR tests
enabled. Third-party PyTorch/Whisper deprecation/CPU precision warnings remain.
Root pytest.ini also verifies collection works from the repository root.

Browser acceptance was run repeatedly with installed Chrome headless and real
MediaRecorder, using file-simulated microphone input. It covers enrollment,
no-trigger reports, repeated change, three explicit answers, transcript review
without auto-send, source display, correction/stale409, confirmation, reload,
history, 375px mobile layout without overflow, keyboard control, microphone denial
and visible/recoverable service503. Provider responses in this deterministic
harness are explicitly stubbed; retrieval/validation and SQL transactions are real.

A separate **no-provider-stubs** browser run used actual Tiger Cloud, actual local
Whisper, Groq and ElevenLabs. The browser recorded a synthetic passage answer,
received 45 recognized words, allowed manual editing, and submitted it explicitly.
Question audio (21,776 bytes) and note audio (1,449,107 bytes) were playable MP3s.
Nine real Groq selections succeeded; the tenth rapid scripted call hit RateLimitError.
The answer was saved, uncertainty preserved, the note corrected/confirmed, and
history restored after reload. This was graceful degradation, not natural
conversation completion. Test schemas were removed. See
`INTEGRATED-LIVE-UI-VERIFICATION.json`.

After that stress result, normal conversations were bounded to four total
questions (configurable CADENCE_MAX_QUESTIONS), ending with uncertainty rather
than pretending resolution. Groq automatic retries are disabled. The budget is
separately tested to preserve the last answer without an extra provider call.
Long stress tests explicitly raise the budget to exercise 10+ turns.

Real-ASR HTTP passage-gating test: three synthetic full-passage references
accepted; matching check-in accepted and persisted with phrase evidence;
different-content real speech rejected422 without a second stored check-in.
See `PHRASE-CAPTURE-VERIFICATION.json`. No model weights were downloaded.

## Boundaries

The browser microphones were simulated and test answers fictional. A consenting
human/device demo acceptance run is still needed. Constructed near-identical
references can produce numerical-floor MADs and huge z-scores; raw score values
stay in API details rather than being presented as clinical significance.

Pitch/energy observations do not contribute to the timing trigger; cross-dataset
research did not establish reliable incremental benefit. The recorded noise-tail
failure still matters. No capture flag is a guarantee of valid measurement.

Confirmation does not share data. Authentication, caregiver authorization,
phone calling, notifications and clinical monitoring validation remain unbuilt
and are not shown as working features. This is a localhost-only prototype.

## Reproduction

`./run-cadence.sh`, then http://localhost:8000. Existing backend/.env is retained.
The optional backend/.venv-asr Python 3.11 environment is prepared locally; the
normal backend/.venv remains intact. ASR requires cached weights and ffmpeg.

From repo root, deterministic browser QA:

```bash
TEST_CONVERSATION_DB_URL=postgresql:///postgres \
CADENCE_PLAYWRIGHT_MODULE=/path/to/playwright \
backend/.venv-asr/bin/python backend/scripts/verify_integrated_ui.py \
  --output docs/INTEGRATED-UI-VERIFICATION.json
```

The live UI harness `verify_integrated_live.py` uses real provider quota and
private configured credentials, creates/removes only its isolated test schema,
and documents its synthetic fixture requirements. Do not rerun it just to
reproduce the existing verified result or during judging rate limits.

The final launcher smoke ran from the actual VoiceRadial workspace using its
preserved `.env`. Additive Tiger Cloud schema startup succeeded; `/`, the real
JavaScript asset, and `/capabilities` returned HTTP 200. Local ASR was ready,
TTS was configured, and the passage count was 41. The test server on port 18080
was shut down cleanly; ordinary launch uses port 8000.
