# Voice-first and complete-flow verification

Verification date: November 8, 2026, America/New_York.

## Scope and preservation

Development continues on `feature/voice-first-adaptive-conversation`, in an
isolated worktree based on `04db56d`. The original integration checkout stays
on `integration/cadence-teammate-updates`. Remote fetch confirmed that base
is still current; PR #3 is open and unmerged. No merge, reset, history rewrite,
credential edit, or demo-video change is part of this feature.

The old demo servers and their databases were left running. The new live and
explicit offline development databases use separate named Docker volumes.
The updated offline server at 8003 shares only the dedicated walkthrough
database with the earlier 8002 process. Neither is an automated browser.

The original intended manual profile `voice-manual-20261108` returned 404 on
both 8001 and 8002 at the start of the resumed check. No claim is made about
unsaved WAVs in a manually opened tab. A fitted reference is persisted only
after successful enrollment; captured and accepted reference WAVs remain
page-memory data until that step. SQL stores statistics, not raw reference
audio or a durable take count. The enrollment response reports the count.

## Automated verification

The resumed pre-extension suite passed **298 tests, 2 skipped**, with the
explicit disposable database and `--browser-smoke`. Package consistency
(`pip check`) passed. JavaScript syntax and `git diff --check` passed.

The full guided extension adds actual per-take acoustic validation, a new
fictional-profile path, stage guidance, reference medians/differences, an
explicit measurements-to-conversation action, and saved-history inspection.
Its final release rerun passed **301 tests, 2 skipped, 0 failed** in 127.86
seconds, with two upstream Silero/Torch deprecation warnings. The skipped
tests are opt-in real-ASR smoke tests; real local ASR was checked separately
through the running server below. All **five JavaScript syntax checks** passed.

Exact command used from the isolated feature checkout on this machine:

```powershell
..\Scripts\python.exe -B -m pytest backend/tests -q --disposable-db-url "postgresql://postgres@127.0.0.1:51388/cadence_integration_test" --browser-smoke
```

The local full-run log is under the original checkout's ignored
`.venv/cadence-verification/voice-guided-verified.txt`. Tests are never run
against either retained development/demo database.

The tests use only an explicit localhost `cadence_integration_test` database
with isolated schemas. They prevent dotenv loading and live provider calls.
Optional headless Chrome tests have their own temporary browser context,
**explicit fixture microphone input**, and injected provider/ASR responses.
They do not use, open, or close the user's regular Chrome windows. These
tests cannot establish that a physical microphone or audible playback worked.

Coverage includes:

* Actual browser capture/WAV upload through real VAD/timing processing,
  rejected-reference retry, three accepted references, unchanged enrollment,
  actual check-in measurements and SQL persistence.
* A genuinely new fictional profile with the existing seeded profile preserved.
* Measurements reviewed before conversation, and backend actual
  usual/elevated/persistent classification across session reloads and history.
* Voice recording cancellation, editable transcript preview, explicit send,
  saved original answers, adaptive follow-ups with injected provider choice,
  and separation from reference/check-in audio.
* Replay cache, pause/stop, blocked autoplay, browser speech fallback,
  microphone denial, ASR failure, and continued typing.
* Emergency-before-provider handling, question budgets, no-repeat rules,
  skip with no invented answer, idempotency, unknowns, finish, correction,
  explicit confirmation, refreshed history, and mobile layout.
* Real validation endpoint without a database dependency; malformed WAV,
  silence, and passage mismatch rejection. Enrollment still reprocesses
  originals and uses the existing baseline mathematics and thresholds.

## Real service checks

| Component | Observed result | Limit |
|---|---|---|
| FastAPI/frontend | 8001, 8002, guided 8003, and fresh live-Groq 8004 reachable | A reachable page does not prove microphone use. |
| Local Whisper | Actual 8003 `/transcribe`: HTTP 200, `whisper-base.en`, nonempty transcript, `needs_review: true`, about 33 seconds | Input was an existing dramatized answer WAV, not a newly recorded physical-microphone answer. No SQL profile/check-in created. |
| Groq | Initially missing; user updated settings. Actual `openai/gpt-oss-20b` application-adapter inference succeeded with structured JSON in 1.77 seconds. Fresh 8004 capabilities report `groq`. | This proves connectivity/inference, not a completed live adaptive patient conversation. |
| ElevenLabs configuration | `ELEVENLABS_API_KEY` present; voice/model overrides absent | Presence is not a health check. No key value was shown. |
| ElevenLabs voice/models/subscription reads | HTTP 401, sanitized category `missing_permissions` | Voice availability, model access, and quota could not be confirmed. These responses do not establish that the key is invalid. |
| ElevenLabs synthesis | Actual minimal request: HTTP 402, sanitized category `payment_required`; internally classified as the free-tier Voice Library API restriction, not an insufficient-credit error | Live ElevenLabs output is not verified. An API-permitted voice/account configuration is required; no account purchase or credential edit was performed. |
| Browser TTS | Available fallback in UI; API behavior tested with injected browser speech | Audible voice on the user's speakers still needs human verification. |
| Offline selector | 8002/8003 explicitly return `question_selection: offline-demo` | Only model ID choice is simulated; never call this a live Groq test. |

No external provider response body, account identifier, credential value,
or patient transcript is included in this report. The launcher respects
an explicit `CADENCE_VOICE_ID`, then the legacy `ELEVENLABS_VOICE_ID`, then
the backend default. Inherited environment variables precede dotenv values.

## Manual verification still required

The user reported that reference recording on 8004/profile
`voice-manual-20261108` is in progress. Completion has not been confirmed.
The server is left running without restart while those takes are unsaved.
The following remain pending:

1. Configure an API-permitted ElevenLabs voice and verify nonempty synthesis
   using the loaded settings. Groq's minimal real inference has passed.
2. On a single new fictional profile: three full physical-microphone reference
   readings, successful enrollment with `n_reference_takes: 3`, and today's
   new recording through real acoustic processing.
3. Audibly hear matching displayed/spoken questions, record a physical voice
   answer, inspect/edit its actual Whisper transcript, and explicitly submit.
4. Verify relevant live follow-ups under the existing stopping rules, review
   and explicitly confirm the report, then refresh and reopen saved history.

An earlier microphone test on another old demo profile is preserved; it does
not establish success for this new workflow. Do not describe the entire live
Groq/ElevenLabs judge demo as passed until these checks are complete.

## Repository checks

A targeted scan of tracked/candidate text files found no credential patterns
except the intentional sample database-password placeholder in
`backend/.env.example`. No real `.env` file is tracked or included in the
feature candidates, and none appears in the fetched Git path history for
the root/backend `.env` paths. The only tracked audio is the existing licensed
test fixture `backend/tests/fixtures/speech_chunk.wav`; no new manual audio,
profile dump, provider audio, model checkpoint, or video is added.

This is a targeted scan, not a guarantee that every possible credential
format has been detected. Keys, local models, diagnostic logs, Docker volumes,
and saved test/user data stay outside the feature commit.

## Changed files

Application:
`Daily Hello Family.html`, `frontend/cadence.js`, `frontend/cadence.css`,
new `frontend/voice.js`, `backend/app/api/main.py`,
`backend/app/api/conversations.py`, `backend/app/api/workspace.py`,
`backend/app/api/speech.py`, `backend/app/audio/whisper_adapter.py`.

Startup/dependencies:
new `Start-CadenceVoice.ps1`, new `scripts/run_voice.py`,
`backend/requirements-asr.txt`.

Tests:
`backend/tests/conftest.py`, `backend/tests/test_browser_workflow.py`,
`backend/tests/test_speech.py`, `backend/tests/test_whisper_adapter.py`,
new `backend/tests/test_voice_first.py`, new `backend/tests/test_voice_browser.py`.

Documentation:
`README.md`, new `docs/VOICE-FIRST-CONVERSATION.md`,
new `docs/LIVE-JUDGE-WALKTHROUGH.md`, this verification report.

The legacy HTML filename is retained. No repository rename or database-schema
change is needed. See [full launch, rehearsal, recovery, and judge script](LIVE-JUDGE-WALKTHROUGH.md).
