# Cadence: full live judge walkthrough

Use one new fictional profile throughout: reference, check-in, conversation,
report, and history. Never substitute Alex's seeded reference for your voice.
This is an acoustic self-check prototype, not a diagnosis or clinically
validated disease-progression assessment.

## Current rehearsal URLs

As checked on November 8, 2026 (America/New_York):

* `http://127.0.0.1:8003/` is the updated guided walkthrough. Real microphone,
  acoustic processing, optional passage verification, cached local Whisper,
  and persistent SQL are available. **Question ID selection is explicitly
  simulated; TTS uses the labeled browser fallback.** This is not a verified
  live Groq/ElevenLabs demonstration.
* `http://127.0.0.1:8002/` remains running. It shares the dedicated walkthrough
  database but is an older backend without per-take validation. Do not close,
  reload, or switch away from an 8002 tab with unsaved reference takes. Save
  them first. Saved baseline/history can then be opened on 8003 using the
  same profile ID; browser-memory recordings cannot move between tabs.
* `http://127.0.0.1:8001/` remains the earlier live-provider process with its
  separate live-development database. Its provider settings are loaded at
  startup; editing a settings file cannot update that running process.

The intended manual profile, `voice-manual-20261108`, was not enrolled on
8001 or 8002 at the start of this resumed verification. That finding does not
describe recordings that might still be held in an open browser tab.

## One-command Windows launch

Current machine, **live providers**, using a new port without stopping any
existing server:

```powershell
$repo = 'C:\Users\lionl\OneDrive\Desktop\Hackerthon file\CareCircle'
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\.venv\voice-first-worktree\Start-CadenceVoice.ps1" -PythonPath "$repo\.venv\Scripts\python.exe" -SettingsFile "$repo\backend\.env" -Port 8004
```

After this branch is checked out in a normal clone with its virtualenv:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-CadenceVoice.ps1 -SettingsFile .\backend\.env -Port 8001
```

Use `-Port 0` to select an available port. Open the clean localhost URL
printed by the running application, manually, in normal Chrome. The
launcher starts/reuses its dedicated persistent TimescaleDB container and
serves the frontend from FastAPI. It opens no browser, seeds no recordings,
and has no fake-media flags. Docker Desktop, installed backend/ASR packages,
and cached Whisper weights are prerequisites; see
[setup](VOICE-FIRST-CONVERSATION.md#windows-setup).

The live database is `cadence_voice_first`, retained in Docker volume
`cadence-voice-first-dev-data`. Explicit offline mode uses the separate
`cadence_voice_first_demo` database and `cadence-voice-first-demo-data` volume.
Do not remove either volume when keeping records. No old demo database is
reset, migrated to this profile, or used by the automated tests.

To keep the offline fallback available:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "$repo\.venv\voice-first-worktree\Start-CadenceVoice.ps1" -PythonPath "$repo\.venv\Scripts\python.exe" -Port 8003 -OfflineQuestionDemo
```

If 8003 is already running, open it instead of launching another copy, or
use `-Port 0`. Keep one profile on one chosen database for the whole rehearsal.

## Configure live providers locally

Open the existing `backend\.env` in your editor; preserve all other settings.
Never paste keys into chat, screenshots, commands, or Git. Set:

* `GROQ_API_KEY`: required for real inference. The existing adapter uses
  `openai/gpt-oss-20b`; `GROQ_MODEL` is not a recognized override.
* `ELEVENLABS_API_KEY`: required for ElevenLabs synthesis.
* `CADENCE_VOICE_ID`: optional explicit API-accessible voice. If absent,
  `ELEVENLABS_VOICE_ID` is honored, otherwise the backend default is used.
* `ELEVENLABS_MODEL_ID`: optional; default `eleven_multilingual_v2`.

The launcher loads the explicitly supplied settings file with
`override=False`. Inherited process variables take precedence. It selects
the dedicated database before loading settings, preventing an old/cloud
database URL in the file from redirecting the rehearsal. FastAPI's default
dotenv lookup is relative to the feature checkout's backend, not the original
checkout. Supply `-SettingsFile` when using this isolated worktree.

At verification, Groq's key was missing. ElevenLabs read calls returned
HTTP 401 `missing_permissions`; synthesis returned HTTP 402
`payment_required`. Those are separate findings. The read failures do not
prove that the key is invalid. Voice access, model availability, and quota
could not be independently confirmed with the current permissions.

Use [Groq keys](https://console.groq.com/keys) and
[ElevenLabs API-key settings](https://elevenlabs.io/app/settings/api-keys)
locally. Permit Text to Speech and, for diagnosis, Voices/Models/User read
access. Check voice API entitlement and account credits before assuming a
free account can synthesize a particular voice. No paid upgrade is performed
by this project. References: [key permissions](https://elevenlabs.io/docs/overview/administration/workspaces/api-keys),
[provider error categories](https://elevenlabs.io/docs/eleven-api/resources/errors),
[Groq setup](https://console.groq.com/docs/quickstart).

After updating settings, start a new live process on an unused port. Verify
a real minimal Groq inference and an actual nonempty ElevenLabs audio response
before describing the external providers as working. Capability discovery
reports configuration presence, not a provider health check. The offline
process must remain labeled and must not be called live AI selection.

## Physical microphone rehearsal

1. In normal Chrome, open the chosen server URL yourself. Under **Connection
   & profile**, connect `voice-manual-20261108` if continuing that profile on
   the walkthrough database. For a genuinely fresh presentation, use **Start
   a new fictional profile**. It prepares a new UUID, connects it, and shows
   welcome/reference guidance without deleting another profile. The profile
   is persisted only when enrollment succeeds. IDs stay inside settings.
2. Allow microphone access for that exact localhost origin. In Windows and
   Chrome, select your actual microphone. Speak and check the recording
   indicator/timer; listen to your take's preview. The agent does not open,
   control, or close your Chrome window.
3. Read the **entire displayed passage**, comfortably, three times. Click
   **Start recording**, read, then **Finish recording** each time. The server
   runs the same VAD/timing pipeline used by enrollment, and optional
   passage verification. Wait for **Completed and accepted** and progress
   Reference 1/2/3 of 3. A rejected take does not advance progress; retry it.
   Three accepted takes are still browser-memory audio, not a saved baseline.
4. Click **Save my reference**. The original WAVs are reprocessed and the
   unchanged robust baseline is fitted. Wait for **Baseline ready**. Only
   success marks enrollment saved; a conflict means that profile already
   exists and must be reconnected, never overwritten.
5. Record today's full reading of the same passage. Finish; the actual
   check-in uploads automatically. Wait for the four measurement cards:
   internal pause proportion, longest internal pause, estimated passage
   syllable rate, and average speech burst. Each includes its personal
   reference median and difference. Explain variation separately from a
   diagnosis. A first changed reading cannot be called persistent unless
   the actual backend says the existing persistence rule was met.
6. Choose **Continue to AI Conversation**. Hear the actual selected question
   while its exact text and available source citations remain visible.
   Check the voice/provider status. If autoplay is blocked, click Replay.
   Verify pause, resume, stop, and replay by listening, not just watching a
   status label. Browser voice is an explicitly labeled fallback.
7. After playback finishes, tap **Tap to answer**. Speak a fictional response,
   stop, and wait for local Whisper. Review **Here's what I heard**, preview
   your recording if useful, edit any mistake, then **Confirm and send**.
   A visible transcript alone is not a saved conversation answer.
8. Answer the next relevant question in the same way, preferably two or
   three total. The evidence-guided engine may stop early or abstain; do
   not force questions, change thresholds, or present a fixed sequence as
   generated output. Keep the physical microphone test separate from the
   standardized-reading pipeline. Typing, cancel/retry, and Skip remain
   available.
9. Finish when appropriate. Review **Measured / You said / Still unclear**.
   Add a correction if needed. Verify **Not yet confirmed**, then explicitly
   click **Looks right - confirm**. This records review and sends no caregiver
   alert.
10. Open **Your history**, **Refresh**, expand saved measurements, and open
    the confirmed note. Refresh the page and confirm that answers, correction,
    measurements, and confirmation remain saved. Old questions must not speak
    automatically. Never switch to a seeded profile halfway through.

After the manual run, report the port and profile ID (no credentials or raw
audio). Backend verification can inspect baseline compatibility, check-in
count, answer records, note revision, and confirmation. It cannot independently
prove that you heard audio or used a physical microphone; that requires your
attestation. Existing schema stores fitted baseline statistics, not raw
reference WAVs or a durable reference-take count. The enrollment success
response establishes `n_reference_takes: 3` during the rehearsal.

## Four-to-six-minute presentation

| Time | What to show | Suggested narration |
|---|---|---|
| 0:00-0:30 | Welcome, new fictional profile, empty reference progress | "Cadence compares a person's speech with their own voice. This fictional profile has no baseline or history yet." |
| 0:30-1:50 | Full passage, three physical-microphone takes, acceptance progress, Save | "These are three live readings. Each goes through the real audio pipeline. Saving fits this person's reference; a failed take must be retried." |
| 1:50-2:35 | Baseline ready, today's fresh reading, four measured cards and reference differences | "Today's timing comes from this recording. Variation is an observation, not a disease diagnosis or proof of progression." |
| 2:35-4:35 | Continue, spoken sourced question, voice answer, editable Whisper transcript, explicit send, follow-up | "The question comes from the existing evidence-guided engine. I review what transcription heard before sending. The next eligible question depends on the reviewed answer and prior questions." |
| 4:35-5:30 | Report sections, correction, explicit confirmation | "Measured observations, my words, and unknowns stay separate. I confirm the note myself; it is not automatically shared." |
| 5:30-6:00 | History refresh, saved measurements, confirmed note | "The database retains the check-in and reviewed answers. Refreshing does not erase this record." |

If either external provider is unavailable, disclose that before starting.
The labeled offline walkthrough can demonstrate the recording/review/storage
flow, but it does not satisfy verification of live Groq or ElevenLabs.

## Recovery during rehearsal

| Problem | Safe recovery |
|---|---|
| Permission denied or no input | Allow microphone for the current origin; check Chrome/Windows selected device. Use recording preview. Keep a typed answer if the mic remains unavailable. |
| Silence auto-stop interrupts reading | Retry the full passage in a quiet room; Finish recording manually when done. Rejected takes never count as accepted. |
| Passage mismatch | Check that the full displayed passage was read. Preview/replace the failing take. Keep normal acceptance rules for the live demonstration. |
| Slow ASR / first model load | Wait for the processing indicator. Do not resubmit repeatedly. Local CPU inference can take tens of seconds. Typing remains an explicit fallback. |
| Incorrect transcript | Edit before Confirm and send, or cancel and rerecord. Report correction preserves the original confirmed answer rather than rewriting it. |
| Playback blocked | Click Replay question; check system volume and the selected output. If provider speech fails, verify the labeled browser fallback audibly. |
| Groq/ElevenLabs unavailable | Preserve the saved reading and answers. Report the failure honestly; do not rename offline selection as live AI. Update settings locally and start a new live process. |
| Page closed before Save reference | The unsaved WAVs are gone from page memory. Repeat three readings; existing saved profiles remain intact. |
| Page closed after check-in | Reconnect the same profile on the same database, open history, and resume the saved reading/conversation. No need to redo its baseline. |
| Port busy | Leave the existing process alone; choose another `-Port` or `-Port 0`. Use the printed URL. |

See [verification results](VOICE-FIRST-VERIFICATION.md) for exactly which
parts used fixture audio or injected providers in automated tests, and which
physical-microphone/live-provider checks remain pending.
