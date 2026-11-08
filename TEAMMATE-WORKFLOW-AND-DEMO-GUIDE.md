# Cadence: workflow walkthrough and demo guide for the team

## If an AI assistant (Codex, Antigravity, or similar) is reading this on a teammate's behalf

Your job is not to paste this file back at them. Read it, then explain it out loud/in chat
in your own plain words, section by section, checking that they actually follow each part
before moving to the next — especially "How it works, start to finish" below. If they ask a
question this file doesn't answer, say so honestly rather than guessing; ask the user or check
the code rather than inventing an answer. This project has been burned before this session by
claims that sounded right but weren't checked — don't repeat that pattern here.

## What Cadence is, in one paragraph

Cadence is a daily voice check-in for someone with Parkinson's. Every day, they read the same
short passage out loud. The app compares today's reading to *that person's own* past readings —
never to population averages — looking at timing: how much they pause, how long their pauses
get, how fast they're reading, how long their bursts of speech last between pauses. If something
in their own pattern looks different, the app has a real AI have a short, grounded conversation
with them about it, using a small set of pre-approved, sourced questions from real Parkinson's
Foundation materials — never inventing medical content on the fly.

## How it works, start to finish (plain language)

1. **Setting up ("enrollment")**: the person reads the passage 3 to 5 times when they first use
   the app. These readings become their personal baseline — their own normal. Nothing is
   compared to anyone else.
2. **A daily check-in starts**: the person picks "today's check-in," presses one button, and
   the AI *speaks out loud* asking them to read the passage. It waits for that to finish playing
   before it starts listening — the voice prompt and the actual reading can't happen at the same
   time, or the prompt's own voice would get picked up and mess up the exact numbers the app is
   trying to measure.
3. **They read, it listens**: the app watches the live microphone volume. Once it hears them
   start talking and then go quiet for about a second and a half, it assumes they're done and
   stops recording on its own — no "stop recording" button needed in the normal case. (There's
   still a manual Stop button and a 60-second safety cutoff, in case the room is noisy and the
   automatic detection misses.)
4. **The reading gets measured and compared**: four numbers come out of that recording — how
   much of it was pauses, the longest single pause, how fast they read, and how long their
   speech bursts were. Each of those four gets compared to *that person's own* past readings
   using simple, explainable statistics (not a trained black-box model) — the kind of math you
   could show someone on paper and they'd believe it.
5. **A conversation always opens** — this changed partway through today's work. It used to be
   that a conversation only started if something looked off two check-ins in a row. Now, every
   single check-in opens a short conversation, whether anything looks unusual or not, because a
   person should be able to say what's on their mind even on an ordinary day.
6. **The AI asks a real question — picked by AI, not a fixed script**: the first question
   (and every one after it) is chosen by a real language model (Groq, a fast cloud AI) from a
   small list of pre-approved questions sourced from actual Parkinson's Foundation and APDA
   materials — things like fatigue, sleep, anxiety, balance, speaking volume. The model picks
   whichever one makes sense; it never writes its own question text, and the server double-checks
   that whatever it picked was actually on the approved list before it's ever shown to anyone.
   The AI then speaks that question out loud.
7. **The person answers by voice**: once the question finishes being spoken, the app starts
   listening again automatically. Their spoken answer gets transcribed (locally, not sent to any
   outside transcription service) and sent in automatically — no "send" button needed in the
   normal case either, though they can still type or edit if they'd rather.
8. **It either keeps going or wraps up, based on what they actually said**: if they say
   something like "I'm fine, nothing unusual," the conversation recognizes that and ends there —
   it does *not* keep peppering them with unrelated questions about sleep or anxiety just because
   those questions exist. If they mention a real concern, or if the measurement is showing a
   real repeated change, it asks a relevant follow-up instead, up to 4 questions total in one
   check-in.
9. **A note gets saved**: what was measured, what they said, and anything still unclear all get
   shown together, kept as separate, clearly labeled things — never blended into one summary that
   implies more certainty than the system actually has. The person reviews it and confirms it.

## What's real AI, and what's deliberately simple on purpose

Two different things are happening, and it's worth being able to explain the difference out loud:

- **Deciding whether to open a conversation at all** is simple, explainable statistics (a robust
  median/spread comparison against that one person's own history). This was kept deliberately
  non-AI on purpose — a black-box model deciding "something's wrong with your voice" with no way
  to explain why would be the wrong kind of AI to trust here.
- **Choosing which question to ask** is real AI — a live call to a language model, constrained to
  pick only from a small, pre-vetted, sourced list, with the server itself checking the model's
  answer before trusting it (never generating free medical text, never inventing a source).

Both halves matter for the pitch: the explainable half is why a judge should trust it, the real-AI
half is why it's not "just a form with extra steps."

## How to actually run it

```
cd <repo root>
./run-cadence.sh
```
Then open **http://localhost:8000** in a browser. The script picks Python 3.11 with local speech
transcription if `backend/.venv-asr` exists, otherwise falls back to the regular `backend/.venv`
without local transcription (typing still works either way). `backend/.env` needs `GROQ_API_KEY`
(question selection) and `ELEVENLABS_API_KEY` (text-to-speech) set for the full experience.

## Things to know about before you touch it, so nothing looks like a mystery bug

- **Recording stops itself based on mic volume**, not a trained model. In a quiet room it works
  well; in a noisy one it may not trigger, and the manual Stop button is there for exactly that.
  There's a small live readout next to the recording timer showing the current volume and what
  it's waiting for — check that if the auto-stop doesn't seem to be working.
- **This is turn-based, not a phone call.** It records, responds, records again. It is not yet a
  continuously-listening conversation where it understands you while you're still mid-sentence —
  that would be a materially bigger piece of work than what exists today. Don't claim that in the
  demo narration; "it listens, responds, and keeps the conversation going naturally" is accurate,
  "it understands you in real time like a phone call" is not.
- **Groq's free tier has a rate limit** (8000 tokens/minute on the model used here). Rapid-fire
  back-to-back check-ins during testing can hit it and show an error. Space out test runs,
  especially right before recording the demo video.
- **A profile enrolled before today's fixes may still have an over-sensitive baseline.** If an
  existing test profile seems to flag every single reading as unusual, the fix for that was
  applied directly to one specific demo profile's stored numbers; a different old profile would
  need the same correction or a fresh enrollment under a new ID to benefit from it.
- There's an unmerged branch on the remote, `fix/transaction-test-and-groq`, with one small test
  fix, branched from an earlier point than the UI work described here. Worth checking with
  whoever pushed it before assuming it's already included in what's described in this file.

## Demo script — a suggested run-through

Aim for something like this order, narrating as you go:

1. **(10-15s) One-line pitch**: "Cadence is a daily voice check-in for Parkinson's that compares
   you to your own normal, not to anyone else's, and has a real AI ask a grounded follow-up
   question when something changes."
2. **(15-20s) Show enrollment briefly** — either do it live (3 quick readings) or say "I already
   set up my baseline earlier" and skip straight to a check-in if time is tight. Live is more
   convincing if you have the time; a pre-enrolled profile is safer if you don't.
3. **(30-40s) Do a real check-in.** Let the AI's spoken prompt play out loud — don't talk over it,
   that's the "Sense" step the rubric cares about. Read the passage. Let it auto-stop; don't reach
   for the Stop button unless it clearly isn't working.
4. **(20-30s) Let the conversation happen.** Let the AI's question play out loud, then answer it
   out loud and let it auto-send. If you want to show the "it actually listens" behavior clearly,
   answer with something unrelated to the question's exact wording but still responsive (e.g. for
   a fatigue question, "I've actually been more tired than usual this week") so the follow-up
   visibly reacts to real content, not just a generic script.
5. **(15s) Show it closing out cleanly.** Either answer "I'm doing well" and show the conversation
   ending on its own, or show a real follow-up firing if you've set up a reading that reads as a
   genuine change.
6. **(10-15s) Show the saved note** — measured / said / still-unclear kept visibly separate — and
   mention that confirming it doesn't send it anywhere, it's a private local prototype.
7. **(10s) Close on the two things that are actually this team's own work**, not borrowed: the
   real-AI-selects-from-sourced-content pipeline with server-side validation, and the specific
   acoustic finding (speech-burst duration) this team found in its own analysis of real patient
   recordings, which is now one of the four things being measured live.

Total: roughly 2 minutes of raw footage is plenty; trim pauses and loading time in editing rather
than narrating over them.

## Recording the video — practical tips

- **Do a full dry run first**, start to finish, before hitting record for real. Confirm the mic
  picks up your voice clearly, the auto-stop actually triggers for your room, and Groq/ElevenLabs
  respond without rate-limit errors.
- **Use a quiet room** and, if possible, a headset or external mic rather than a laptop's built-in
  one — the auto-stop detection and the underlying timing measurements are both more reliable with
  a cleaner signal.
- **Hard-refresh the browser** (Cmd+Shift+R / Ctrl+Shift+R) right before recording, in case a
  stale cached copy of the page is still loaded from an earlier test.
- **Have a backup plan**: if something flakes live (a rate limit, a flaky Wi-Fi moment), it's
  fine to cut and restart that one segment rather than restarting the whole recording — judges
  watch an edited video, not a single unbroken take.
- **Don't narrate over the AI's spoken prompt or question** — let it actually be heard; that's the
  "AI interacting with the physical world" moment the judging rubric is specifically looking for.
- **Say what's real and what's intentionally simple**, same as the section above — judges tend to
  trust a team more when it's precise about its own system than when everything is claimed to be
  equally "AI-powered."
