# End-to-end verification and original-idea delivery status

November 8, 2026. This report describes fresh executions, not inherited claims.

## Executed checks

| Check | Actual execution | Result / boundary |
| --- | --- | --- |
| Browser capture | Installed Chrome headless, simulated file microphone, real MediaRecorder and PCM WAV encoding | Three enrollment captures and one recorded check-in uploaded to real Tiger Cloud. Controlled long-gap inputs then exercised the legacy answer/confirm branch. No browser JS errors. Not a human microphone test. |
| Core backend | Actual localhost HTTP with an isolated Tiger Cloud schema | Four-take enrollment; first elevated check-in untriggered; second triggered; four feature z-scores and waveform evidence persisted. |
| Live question selection | Actual Groq calls using fictional answer text | Five sourced follow-ups selected; subsequent SelectionRejected preserved the sixth answer and ended as abstained, retaining uncertainty. This is graceful abstention, not a completed/resolved conversation. |
| Confirmation/recovery | Actual HTTP and cloud transactions | Stale revision rejected, exact revision confirmed, duplicate confirmation stable, fresh app recovered the identical snapshot. |
| Speech output | Actual ElevenLabs request | HTTP 200, audio/mpeg, 56,049 bytes. Page does not yet orchestrate question playback/read-back. |
| ASR | Actual cached Whisper base in isolated temporary Python 3.11 environment | Expected synthesized passage matched (bounded disagreement 0.0345); different-content attributed real speech mismatched (0.8966). Same model instance reused; weight download path explicitly blocked. Core backend venv unchanged. |
| Alignment regression | Independent re-review/fixes | Fixed cached loader's remaining download path, empty-token index drift, standalone punctuation index drift, and global timestamp ordering. No actual-audio-duration bound or unique repeated-word alignment guarantee yet. |
| Candidate corpus | Independent span and runtime review | 16/16 exact text/source matches. Three revised communication candidates remain proposals; runtime context extraction does not yet support their advertised eligibility reliably. No promotion. |

Machine-readable reports: `LIVE-WORKFLOW-VERIFICATION.json`,
`BROWSER-WORKFLOW-VERIFICATION.json`, `REAL-ASR-VERIFICATION.json`.
All real-service tests used isolated schemas removed after execution. Provider
calls were real; fixture speech and typed answers were explicitly test/demo data.

The mechanical trigger smoke used repeated short speech clips, not the full
passage. Their near-identical reference takes produce numerical-floor MADs and
huge robust z-scores. These establish routing/persistence, not score calibration,
realistic personal variability or clinical magnitude. The full-passage ASR test
used synthetic speech because consented human demo recordings do not yet exist.

## What can ship from the original idea

| Original capability | Current status | Remaining implementation |
| --- | --- | --- |
| Person reads a fixed passage into a browser | Capture/WAV/upload path verified with simulated microphone | Human device/permission smoke and consented recordings. |
| Compare with their own reference, require repetition | Core four-feature mechanism works | Recording-quality/phrase policy, MAD calibration and protocol provenance remain prototype limitations. |
| Ask a sourced, context-sensitive question | Live validated ID selection works | Fix negation, symptom memory and recording-vs-everyday context before promoting new units. |
| Spoken interaction | Real TTS and real ASR each verified | Integrate ASR/evidence into the API and orchestrate listening/playback in UI. Current answers are typed. |
| Continue follow-ups | Durable API is real and cloud-tested | Browser page still implements the legacy one-answer route; wire session/turn APIs. |
| Patient-reviewed three-bucket note | Storage and confirmation work | Human-readable multi-turn assembly, explicit semantic resolution, editing/correction and read-back integration. |
| Report symptoms despite typical audio | Original intention is implementable | Current legacy /answer requires a triggered question; add a non-triggered patient-report path. |
| Recognize a recording interruption | Can preserve patient explanation | Current score is already inserted before that answer; no retrospective exclusion/replay policy exists. |
| History view | Check-in rows and sessions persist | Add an authorized history endpoint and UI. |
| Caregiver receives approved report | Feasible future implementation | Identity, linkage, separate sharing permission, revocation and access enforcement. /confirm is not sharing consent. |
| Call my parent | Future implementation, not functioning today | Telephony provider, identity/consent, callback state, audio transport and separate phone-channel references. |
| Diagnose disease, predict severity or medication changes | Not supported by the implementation/evidence | Outside current product claim; cohort AUC is not validation for these purposes. |

## Integration order

1. Correct context extraction and explicit answer-resolution behavior; then
   promote only independently accepted sourced candidates.
2. Add opt-in phrase evidence alongside persisted waveform evidence. Distinguish
   transcript match from overall capture comparability. Persist quality context
   and define how unavailable/mismatched samples affect future tracker replay.
3. Wire the browser to durable sessions/turns and TTS; keep microphone permission
   and human finish controls explicit. Add typed reports even without a trigger.
4. Finish editable note review, correction and playback. Demo the real self-check
   with human recordings before adding caregiver/phone scope.
5. Add authorized history/sharing only with the corresponding identity model.

## Reproduction

From backend/, run `.venv/bin/python -m pytest tests/ -q`; dedicated database
integration needs TEST_TIGER_DATA_URL and TEST_CONVERSATION_DB_URL. The full cloud
run sets TEST_TIGER_DATA_URL privately from configured TIGER_DATA_URL; tests use
isolated schemas. Do not print credentials.

From repo root, `backend/.venv/bin/python backend/scripts/verify_live_workflow.py`
uses real Tiger/Groq/ElevenLabs and consumes small provider quota. It initializes
only its isolated schema, not public production tables.

Browser reproduction requires an optional Playwright npm installation, installed
Chrome, and CADENCE_PLAYWRIGHT_MODULE pointing to that package if not resolvable.
Run `backend/.venv/bin/python backend/scripts/verify_browser_workflow.py`.
It uses a simulated mic, not a user hardware device.

ASR reproduction uses the optional Whisper-capable Python environment and the
existing cached checkpoint. Run `backend/scripts/verify_real_asr.py --expected-wav
<fixed-passage.wav> --different-wav <different-content.wav> --output <report.json>`.
No ASR package was added to the core Python 3.15 backend environment.
