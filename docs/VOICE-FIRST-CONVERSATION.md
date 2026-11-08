# Cadence voice-first development

This feature branch extends the actual Cadence application. PR #3, the original
integration checkout, existing demo databases, and final hackathon video are
preserved. The new local application is normally at http://127.0.0.1:8001/.

For the complete new-profile-to-history rehearsal, exact current-machine
commands, and judge narration, use [the full walkthrough](LIVE-JUDGE-WALKTHROUGH.md).
The updated guided offline server is at http://127.0.0.1:8003/; the older 8002
server remains running with the same dedicated walkthrough database.

## What changes

The existing FastAPI conversation engine, reviewed question library, retrieval,
Groq ID selection, emergency tripwire, SQL state, and explicit note confirmation
remain in use. Questions are displayed and optionally spoken. The patient taps
to record, stops or cancels, reviews an editable local-Whisper transcript, and
explicitly chooses **Confirm and send**. Only that reviewed text enters the
conversation. Recording an answer cannot change the standardized-passage
reference or create an acoustic check-in.

`frontend/voice.js` owns playback, pause/stop/replay, request cancellation,
autoplay errors, and a bounded page-memory audio cache. Questions are not
automatically repeated on reload or when reopening history. Browser voice is
explicitly labeled when ElevenLabs is unavailable; text always remains visible.
The microphone never starts automatically after playback. Stop speech before
tapping to record, so synthesized questions do not contaminate an answer.

Skipped questions are stored as explicit skips with no fabricated patient
answer. They remain unresolved in the note. Existing question limits, emergency
handling, finish, corrections, revisions, and confirmation rules still apply.

The measurement banner now uses the backend classification. The same existing
threshold is used for the check-in response, conversation snapshots (including
legacy reads), and history. No medical analysis threshold is changed.

## Providers and retention

* **Preferred TTS:** ElevenLabs through the existing backend `/speak` route.
  The backend retains the legacy Rachel ID (`21m00Tcm4TlvDq8ikWAM`) at speed
  0.92. The provider may route it to a replacement; API availability depends
  on the account. `CADENCE_VOICE_ID` can select an accessible warm
  American female voice. The backend also accepts the legacy
  `ELEVENLABS_VOICE_ID` configuration when `CADENCE_VOICE_ID` is absent.
  Voice availability and account permissions must be checked with the provider.
  The checked account rejects the default Voice Library voice on its free API
  plan. A different API-permitted voice/account configuration is required;
  this is not fixed by assuming the key is invalid or purchasing access
  automatically. See the [provider voice changes](https://elevenlabs.io/docs/help-center/product/voices/voice-library/how-are-voices-updated-changed)
  and [default-voice access rules](https://elevenlabs.io/docs/help-center/product/voices/my-voices/how-do-i-access-eleven-labs-default-voices).
* **TTS fallback:** browser speech synthesis, preferring an available local
  American female voice such as Microsoft Zira. The exact selected voice is
  shown; availability and quality vary by browser and operating system.
* **ASR:** local `openai-whisper==20250625`, cached `base.en` for this launch.
  WAV decoding uses soundfile and the existing resampling loader, so no system
  FFmpeg executable is needed for the application WAV path. Runtime never
  downloads weights. Word probabilities are uncalibrated; every transcript
  requires human review, including apparently confident transcripts.
* **Selection:** the existing Groq adapter and validated evidence-guided
  question engine. Missing credentials, timeout, invalid output, or unavailable
  guidance produce honest uncertainty/abstention, not invented model replies.

Keys stay in the backend process. The scripts never write `.env` files or
credential archives. Spoken text goes to ElevenLabs when configured; provider
retention policies apply. Browser voices may use the browser's speech provider.
Conversational audio stays local to this backend, is processed in temporary
files, and is not retained by default. Its browser preview stays in page memory
until discarded, submitted, or the page closes. Canceling a pending request
discards its result; already-started server inference may finish before its
temporary file is removed.

This remains an unauthenticated localhost research prototype. Do not bind it to
a public interface or use it for diagnosis, medication advice, or unrestricted
patient access. It does not share notes with caregivers.

## Windows setup

From a checkout of this feature branch, with Python 3.11 or 3.12 and Docker
Desktop running:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-asr.txt
$env:CADENCE_WHISPER_CACHE = Join-Path $PWD '.venv\whisper-cache'
.\.venv\Scripts\python.exe -c "import os, whisper; whisper.load_model('base.en', device='cpu', download_root=os.environ['CADENCE_WHISPER_CACHE'])"
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-CadenceVoice.ps1
```

The download is an explicit one-time setup step, about 139 MiB. Install optional
Playwright only when running the browser acceptance tests. Existing provider
keys may be inherited from your shell, or loaded by the backend from an
explicit settings file:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-CadenceVoice.ps1 -SettingsFile .\backend\.env
```

Do not paste keys into chat or commit them. `GROQ_API_KEY` enables live question
selection and `ELEVENLABS_API_KEY` enables preferred TTS. The new database URL
is explicitly selected before optional settings are loaded, so a settings
file's cloud/older-demo database URL cannot replace it.

On the existing development machine, the feature checkout is isolated inside
the original repository's ignored `.venv` folder. Its exact command is:

```powershell
$repo = 'C:\Users\lionl\OneDrive\Desktop\Hackerthon file\CareCircle'
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\.venv\voice-first-worktree\Start-CadenceVoice.ps1" -PythonPath "$repo\.venv\Scripts\python.exe" -SettingsFile "$repo\backend\.env" -Port 8001
```

The launcher runs in the terminal and does **not** open a browser. The dedicated
container is `cadence-voice-first-dev`, database `cadence_voice_first`, and
named Docker volume `cadence-voice-first-dev-data`. The volume retains records
across container restarts. Do not remove it when records must be preserved.
This does not alter or migrate existing demo databases. Stop this new server
with Ctrl+C in its terminal; restart it with the same command.

### Explicit walkthrough when Groq is unavailable

The live default never invents a provider response. An optional demonstration
can instead simulate **only model ID choice**, while using the real eligibility
rules, sourced templates, safety, local Whisper, microphone, and SQL. The
application prominently labels this mode. It uses a **different** database,
container `cadence-voice-first-demo`, and volume
`cadence-voice-first-demo-data`, so simulated conversations do not enter the
live development database.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-CadenceVoice.ps1 -Port 8002 -OfflineQuestionDemo
```

For the current isolated checkout:

```powershell
$repo = 'C:\Users\lionl\OneDrive\Desktop\Hackerthon file\CareCircle'
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\.venv\voice-first-worktree\Start-CadenceVoice.ps1" -PythonPath "$repo\.venv\Scripts\python.exe" -Port 8002 -OfflineQuestionDemo
```

Open http://127.0.0.1:8002/ manually and use a new fictional profile such as
`voice-manual-20261108`. This command does not load provider settings: speech
uses the labeled browser fallback. Model choice is simulated, not live Groq.
Question eligibility changes with the actual reviewed answers, prior questions,
and measurement context. There is no hardcoded sample conversation and no fake
microphone. The same manual steps below apply, using port 8002 for this mode.

## Manual real-microphone check

1. Open http://127.0.0.1:8001/ yourself in regular Chrome. No automation or fake
   media flags are used by the launcher. Enable **Read questions aloud**.
2. Connect a new fictional profile such as `voice-live-20261108`. Do not reuse
   `alex-morgan-demo` or compare your voice against a fixture baseline.
3. Read the entire displayed passage three times using Start/Finish recording.
   Save the reference and check `n_reference_takes: 3` in the API response.
4. Record one daily reading of that same passage. The real pipeline displays
   its four acoustic measurements and actual classification.
5. Choose **Continue to AI Conversation** after reviewing the measurements.
   If live selection is available, a sourced question appears and is spoken.
   Verify the shown provider/voice, that you actually hear it, and that
   pause/stop/replay work. If autoplay is blocked, use Replay question.
6. Once speech finishes, tap **Tap to answer**. Allow your physical microphone,
   speak naturally, then stop. Verify the recording indicator and timer.
7. Listen to your local preview if useful. Check **Here's what I heard**, edit
   any error, and choose **Confirm and send**. Nothing is auto-submitted.
8. Verify a relevant follow-up selected by the existing engine. Repeat by voice;
   try cancel/retry and typing. A denied microphone must leave typing usable.
9. Finish for now, review **Measured / You said / Still unclear**, save any
   correction, and explicitly confirm. Reopen history and reload the note.
10. Reload the page: old questions/notes must not speak automatically. An active
    conversation can be resumed through history.

If Groq is not configured or rejects the request, the engine may abstain before
asking a question. Do not describe that as a successful adaptive voice session.
If a provider fails after a confirmed answer, the answer remains in a reviewable
note with uncertainty. Real microphone input, audible playback, and recognition
accuracy require the user's manual check; headless fixture tests do not prove them.

## Automated checks

Use a **separate, disposable** local database named `cadence_integration_test`.
Never point tests at `cadence_voice_first` or any existing demo/user database.

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q --disposable-db-url "postgresql://postgres@127.0.0.1:TEST_PORT/cadence_integration_test" --browser-smoke
```

Install `playwright` and Chrome for `--browser-smoke`. That opt-in suite uses a
clearly named fixture microphone, injected ASR/TTS and provider choices, actual
browser recording/playback controls, HTTP, and isolated SQL schemas. It never
accesses your manually opened Chrome profile or microphone. Tests prevent
dotenv loading and external provider calls. See `VOICE-FIRST-VERIFICATION.md`
for the recorded results and live-service limitations.

Provider reference: [ElevenLabs speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert).
