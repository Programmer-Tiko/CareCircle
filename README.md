

Pasted text(20261107-223509).txt
Document
# VoiceShift — what we're building, for the person building the demo

One paragraph, then the exact screens and copy to build.

## The idea, in plain terms

VoiceShift is a between-visit check-in for people already diagnosed with COPD or Parkinson's. Once a day, they read a short standard passage into their phone or laptop mic. The system compares *that person's own* speech timing (pauses, speaking rate) against *their own* past recordings — never against other people. Most days, nothing changes, and the check-in is a 30-second non-event. When something repeatable changes, the system asks a smarter follow-up question instead of a generic one, and whatever the person says — not the measurement — becomes the actual note. A linked caregiver can also trigger an AI phone call that does the same thing on the patient's behalf.

**The pitch in three words, say this explicitly in the demo narration: Sense → Understand → Act.** Sense: the mic is the physical sensor. Understand: compare today's reading against this person's own baseline. Act: ask a different, better question because of what changed.

This is not a diagnosis tool. It never claims to detect disease. It claims to ask a better question than a static questionnaire would.

## The two entry points

- **Check my voice** — the patient does a self-check, any time, in the app.
- **Call my parent** — a caregiver (adult child) taps a button, and the system places an outbound AI call to their enrolled, linked parent, running the same check-in over the phone.

For tomorrow's demo, **build "Check my voice" as the fully real, deeply polished path.** Treat "Call my parent" as a secondary feature — fine to show as a short scripted/simulated sequence (a few screenshots of call states), but the self-check flow is what needs to actually work and look great.

## Screens to build — self-check path

1. **Home.** Two big entry points: "Check my voice" and "Call my parent." Calm, warm, clinical — not an alarm-styled health app. This is a daily habit, not an emergency tool.

2. **Enrollment (first time only).** Explain in one sentence: "Read this short passage a few times so we learn what's normal for you." Record 3–5 takes of the fixed passage (a short excerpt of the Rainbow Passage — a real standardized passage speech clinicians already use, ~15–20 seconds each). Simple record → stop → "sounds good, one more" loop.

3. **Daily check-in.** One screen: the passage text displayed, a record button, explicit "Finish" when done (not auto-cutoff). If the person has Parkinson's, add one extra ~5 second step after: "hold a steady 'ahh' for 5 seconds."

4. **Processing (brief, 1–2 seconds).** A simple "comparing to your usual" state — this is the moment the "Understand" step happens, worth a small deliberate pause/animation so it's visible in the demo rather than instant.

5. **Outcome A — no meaningful change (the common case).** "Sounds like your usual self today. Anything you'd like to mention?" with a free-text/optional field. Fast, low-friction, done in one tap.

6. **Outcome B — persistent change detected.** This is the moment to make visually clear in the demo: show, plainly, *what* changed (e.g., "today's reading had more pauses than usual") — not a scary alert, a neutral observation — followed by the adaptive question. Use the real condition-specific language:
   - **COPD:** "What happened during that pause?" → if "I stopped to catch my breath" → "Is that more frequent than usual? What were you doing at the time?"
   - **Parkinson's:** "What happened there?" → if "it's harder to get words out" → "Where have you noticed that — and has being understood in everyday conversation changed?"
   - For Parkinson's profiles only, also show a secondary, separately-labeled "voice quality index" number with a tooltip: *"research-informed, not a diagnosis."* Never put this number next to anything that looks like a diagnosis or a red/green status light.

7. **Note review.** Three clearly separate sections, always: **Measured** (the acoustic observation, in plain language), **You said** (their actual words), **Still unclear** (anything unresolved). Editable. A "Looks right" confirm button. Nothing leaves this screen un-confirmed.

8. **History (nice-to-have if time allows).** A simple day-by-day strip showing past check-ins — this is where the 5-day demo script below actually gets shown.

## Screens to build — caregiver path (lighter effort)

- A "Call my parent" button on the caregiver's home screen.
- A call-status strip: queued → ringing → in progress → completed → awaiting approval → report available. (For the demo, this can just be a scripted sequence of these states, not a live call.)
- Once "report available": the same three-bucket note, read-only, with a line making clear the caregiver only ever sees the parent-approved version — never raw audio or an unapproved draft.

## The 5-day demo script (so you don't need to wait on real elapsed days)

Seed one fictional profile with 5 pre-recorded takes:
- **Days 1–3:** normal, clean reads → this builds "their usual."
- **Day 4:** slightly faster or slower, still within normal range → demo should show Outcome A (no change flagged) — proves it doesn't cry wolf on ordinary variation.
- **Day 5 (two takes):** a teammate deliberately inserts a breathing pause (for the COPD version) or deliberately slows/slurs a word (for the Parkinson's version), repeated on a second take → demo shows Outcome B firing, with the correct condition-specific question.

Narrate day 5 live: "here's where it notices something repeatable, and here's the question it asks instead of a generic one."

## Mock data shape, so the UI doesn't need to wait on the backend

Build against this shape now; it'll match what the backend actually returns later.

{
  "profile_id": "demo-copd-1",
  "condition": "copd",
  "day": 5,
  "label": "acted-deviation",
  "measured": {
    "pause_fraction": 0.42,
    "longest_internal_gap_sec": 0.85,
    "speaking_rate_syll_per_sec": 2.1,
    "deviation_from_baseline": "persistent"
  },
  "triggered_question": "What happened during that pause?",
  "note": {
    "measured": "Longer pauses than your usual pattern, repeated across two readings today.",
    "patient_said": "I stopped to catch my breath — happens more on stairs lately.",
    "unresolved": []
  },
  "status": "awaiting_confirmation"
}


## Tone and copy rules (judges and real users will both notice violations)

- Never say "detected," "diagnosed," or imply a medical finding. Say "noticed a change" or "different than usual."
- Never show a measurement without also showing what the person actually said about it, once available.
- A missed call or missing audio is never framed as bad news — it's just "no reading available today."
- Keep the voice quality index (Parkinson's only) visually and verbally separate from the baseline-deviation question — one is a research-informed number, the other is what actually drives the conversation.
- No red alert styling anywhere. This is a daily habit tool, not an ICU monitor.

## What's explicitly out of scope — don't build screens for these

Diagnosis, severity scoring shown as a verdict, medication suggestions, automated emergency dispatch, scheduled/recurring calls, inbound calls. If a scenario needs one of these, show a fixed, clearly-labeled scripted message instead of inventing a flow.

those are from my teammate
I understand. These are your teammate's specifications for VoiceShift, the project your team is building for UB Hacking 2026.

I'll use this as the working project specification for our next steps.

What I understand about your project
VoiceShift = Sense → Understand → Act

Sense: Record a standardized reading passage through a microphone.

Understand: Compare speaking rate and pauses against the patient's personal baseline.

Act: Ask an adaptive, condition-specific question and create a patient-confirmed note.

The target users are people already diagnosed with COPD or Parkinson's, rather than people seeking a new diagnosis.

The two experiences are the patient's Check my voice and the caregiver's Call my parent.

Three issues I noticed in your teammate's specifications
1. The two versions have different priorities.

The shorter brief says to make the self-check fully functional and simulate the caregiver phone call. The longer attached specification calls for a real outbound phone call and a parallel Parkinson's model-training track.

For tomorrow's competition, I recommend making the real self-check the non-negotiable deliverable. Only attempt a live phone call once that works reliably.

2. Three baseline recordings are not enough for a statistically reliable personal model.

They are fine for demonstrating the mechanism, but I would use simple median comparisons and conservative prototype thresholds rather than presenting a robust multivariate z-score as clinically meaningful.

Also, two unusual recordings on Day 5 demonstrate a repeatable within-session change, not persistence across several days.

3. The Parkinson's voice quality index could create more questions than value.

A model trained on the UCI Parkinson's Telemonitoring dataset would require careful validation before its score could be interpreted meaningfully for a new person. I would keep it optional and separate from the main question-selection engine.

What I think will win over the judges
Your team's most compelling demonstration is:

A patient records their voice

The system measures a repeatable difference

The system asks a more relevant question

The patient confirms what the system understood

An authorized caregiver can view the approved report

The advantage is that VoiceShift doesn't merely collect health information. It uses a measurable change in the physical world to decide how to interact with a person. That is particularly relevant to the Radial Atoms track.

I can now help you build, test, and prepare the actual VoiceShift demo based on your teammate's specifications, while keeping the technical implementation, medical claims, and presentation consistent.

now show me complete structure and idea (combined what I mention before) of this project, I want to write to ReadMe in github

Worked for 2m 54s
I've combined your original VoiceGuard AI vision with your teammate's more focused VoiceShift proposal into a complete, GitHub-ready README in English.

VoiceShift_README.md

Markdown · 16 sections · Ready for GitHub

 Download the complete README

The document covers the complete product concept, technical architecture, user interfaces, example conversations, voice-analysis pipeline, caregiver workflow, API structure, five-day demo, medical limitations, research sources, and future roadmap.

Project positioning
VoiceShift
A voice-guided health check-in companion

For people living with COPD or Parkinson's

SENSE

Record speech

UNDERSTAND

Compare patterns

ACT

Ask & document

What's included
Area

Key contents

Product concept

Problem, audience, unique value proposition, Sense → Understand → Act

Patient interface

Enrollment, daily recording, adaptive questions, note review, history

Caregiver interface

Call my parent, call status, approved report, optional automatic notification

Voice intelligence

Pause measurement, speaking rate, personal baseline, repeatability

AI conversation

COPD and Parkinson's question paths, open-ended dialogue, patient corrections

Engineering

React/TypeScript, FastAPI, proposed APIs, data schema, repository structure

Demo

Simulated five-day history, working audio comparison, judging walkthrough

Future vision

Familiar AI companion, phone integration, proactive family updates, evidence-linked research

How I reconciled your original idea with the teammate's specification
Your original idea included disease probability charts, a familiar family-like AI character, and automatic alerts to an adult child. The revised design keeps their underlying goals but distinguishes them from what you can responsibly demonstrate tomorrow.

Disease probability charts: Replaced with explainable speech measurements and patient-reported observations. Unvalidated disease probabilities are excluded.

Natural conversational AI: Retained, using condition-aware, open-ended questions rather than a fixed yes/no questionnaire.

Familiar AI character: Preserved as a future accessibility feature with consent and clear AI disclosure.

Automatic family updates: Preserved after patient approval. A caregiver can be notified automatically when an authorized report becomes available, without needing to request it.

Phone calls: Documented as a secondary caregiver-triggered workflow, clearly distinguishing simulated demo states from an implemented calling system.

Most importantly, the README does not claim your team has implemented features that haven't been tested yet. Proposed components and future work are labeled accordingly.

GitHub description
VoiceShift is an AI-assisted, voice-guided check-in platform for people living with COPD or Parkinson's. By comparing daily speech patterns with each person's own baseline, VoiceShift identifies measurable changes, asks context-aware follow-up questions, and creates patient-confirmed notes that can be shared with authorized caregivers.

Sense → Understand → Act.

Built for UB Hacking 2026 · Radial Atoms.

Research-inspired prototype. Not intended for medical diagnosis or emergency monitoring.

Suggested GitHub repository topics
hackathon · ubhacking · healthtech · voice-analysis · speech-processing · digital-health · fastapi · react · parkinsons · copd · ai

Next step: Save the downloaded file as README.md at the root of your VoiceShift GitHub repository. The repository layout and API endpoints in the document are proposed structures, so update them as your team finalizes the implementation.


VoiceShift_README.md
Document
should I copy all content of your given file in my readme file or just replace it
You should replace the existing content of your GitHub README.md with the complete content of the file I provided, rather than adding it below your existing README.

How to do it on GitHub
Open your VoiceShift GitHub repository.

Click README.md.

Click the  Edit button.

Select all existing content (Ctrl + A).

Copy and paste the entire contents of VoiceShift_README.md.

Click Commit changes.

Before committing
Check these three things:

Team information: Preserve any existing team member names, contributions, or acknowledgments that aren't in the new README.

Implementation status: Make sure features described as working have actually been implemented. Keep unfinished features labeled as planned or in development.

Technical stack: Update the technology section to match what your teammates are actually using.

My recommendation: Use the provided file as your main README because it explains the complete VoiceShift concept, architecture, demo, and future roadmap in one organized document. You don't need to paste it twice or keep the old introductory content if the new file already covers it.


VoiceShift_README.md
Document

1 selection
I have not clone the repo in my local, now I open VS code in the folder what I want to put the repo, what should I do next
Since you already opened VS Code in the folder where you want to store VoiceShift, the next step is to clone your GitHub repository into that folder, then update README.md.

Step 1. Open the VS Code terminal
In VS Code, select:

Terminal → New Terminal

Or press Ctrl + Shift + ~.

Check your current folder:

pwd

For example, you might see:

C:\Users\YourName\Documents\Hackathon
This is where the cloned repository will be created.

Step 2. Copy your GitHub repository URL
Open your VoiceShift repository on GitHub.

Click the green Code button.

Select HTTPS.

Copy the repository URL.

It should look something like:

https://github.com/YOUR_USERNAME/VoiceShift.git
Step 3. Clone the repository
In your VS Code terminal, run:

git clone https://github.com/YOUR_USERNAME/VoiceShift.git

Replace YOUR_USERNAME with your actual GitHub username or your team's organization name.

Then enter the cloned repository:

cd VoiceShift

Check the files:

ls

You should see something similar to:

VoiceShift/
├── README.md
├── .gitignore
└── ...
Note: If your currently opened folder is already named VoiceShift and is empty, clone into the current folder with git clone YOUR_REPO_URL . instead. This avoids creating VoiceShift/VoiceShift.

Step 4. Replace the README
In VS Code, click File → Open Folder and select the newly cloned VoiceShift directory, if it isn't already open.

Open README.md.

Press Ctrl + A to select the existing content.

Paste the complete content from VoiceShift_README.md.

Press Ctrl + S to save.

Keep the filename as README.md, not VoiceShift_README.md, so GitHub automatically displays it on the repository homepage.

Step 5. Commit and push to GitHub
In the VS Code terminal, run:

git status

You should see that README.md has been modified.

Then:

git add README.md
git commit -m "docs: add VoiceShift project README"
git push

If the push succeeds, refresh your GitHub repository page. The updated README should appear.

Step 6. Important for team collaboration
Since this is a team hackathon repository, check whether teammates are also working on the same branch.

Before future work, you can run:

git pull

to retrieve their latest changes.

Avoid using git push --force, since that could overwrite a teammate's work.

Your complete workflow
Local parent folder in VS Code

Clone GitHub repository

git clone <repository-url>

Edit README.md

Paste the new project documentation and save

Commit and push

git add → git commit → git push

One question: Is the folder you currently have open in VS Code empty, or does it already contain project files?

That determines whether you should use git clone URL or git clone URL ..


VoiceShift_README.md
Document
VoiceShift
Sense → Understand → Act
A personalized, voice-guided check-in that helps people living with COPD or Parkinson's document changes between healthcare visits.

VoiceShift is a UB Hacking 2026 project designed for the Radial Atoms track. It uses a microphone as a real-world sensor, compares a person's current speech timing with their own earlier recordings, and uses that information to ask a more relevant follow-up question. The person's explanation—not an acoustic measurement or an AI-generated diagnosis—becomes the foundation of a note they can review, correct, and choose to share.

Our central idea: A useful health check-in should not ask everyone the same questions every day. It should notice when something is different, ask what happened, and let the person tell their own story.

Important: VoiceShift is a research-inspired hackathon prototype, not a medical device, diagnostic tool, emergency-monitoring system, or substitute for professional care. It does not diagnose COPD, Parkinson's, disease progression, or flare-ups.

1. The Problem
People living with long-term conditions may have important experiences between clinic visits that are difficult to remember or communicate later. Traditional daily questionnaires can feel repetitive and may miss the context behind a change. Family members also want to stay informed without requiring an older adult to navigate a complicated app or share every personal recording.

VoiceShift explores a more personal workflow:

Less effort for the patient: A short, familiar reading task and a conversational follow-up only when it might be useful.
More relevant questions: A change in speech timing can influence what the system asks next.
More useful records: A structured, editable note separates measurements from the person's own words.
Respectful family involvement: An authorized caregiver receives only information the patient has approved for sharing.
Accessibility: Large controls, simple language, optional spoken interactions, and a calm—not alarming—interface.
2. Who It's For
User	Need	VoiceShift experience
Person living with COPD	Describe whether speech pauses are associated with breathlessness or everyday activities	Personal speech-timing comparison followed by neutral, breathing-related questions
Person living with Parkinson's	Describe whether speech production or being understood has changed	Personal speech-timing comparison followed by communication-related questions
Authorized caregiver	Check in without intruding, and understand what the person has chosen to share	A read-only dashboard of patient-approved notes and an optional Call my parent flow
Clinician (future stakeholder)	Receive concise, patient-verified observations between visits	Potential export of an approved, clearly labeled note; no current clinical integration
VoiceShift is designed around known conditions and lived experiences, not identifying a disease from an unknown person's voice.

3. Our Core Principle: Sense → Understand → Act
Sense — microphone as a physical sensor
A user reads the same short passage into a phone or laptop microphone. The app measures features of their speech, such as pauses and speaking rate. A Parkinson's-specific research extension may separately capture a five-second sustained “ahh” vowel.

Understand — personal comparison, not population diagnosis
The system compares today's recording with that same person's previous recordings made using comparable passages and recording setups. A small, repeated difference can qualify for a follow-up question. No comparison with other people is needed for the primary check-in decision.

Act — ask a better question and document the answer
Instead of assigning a disease probability, VoiceShift asks a condition-aware, open-ended question. What the person actually reports determines the content of an editable note. The patient confirms the note and chooses whether to share it.

4. The Two Entry Points
A. Check my voice — primary hackathon experience
The person completes a self-check in the web app. This is the fully functional path we prioritize for the hackathon demo: microphone recording, measurable analysis, adaptive questions, editable notes, and a clear outcome.

B. Call my parent — caregiver-initiated experience
A linked caregiver requests an outbound AI call to an enrolled parent. With the parent's permission, the call would run the same check-in over the phone and ask for confirmation before sharing a report.

For the hackathon, the call-state journey may be a clearly labeled simulation. Real outbound calling, verification, recording consent, callbacks, and a phone-specific voice baseline are separate engineering requirements—not features we claim are working unless implemented and tested.

Caregiver autonomy does not override patient consent: A caregiver may request a check-in, but they cannot read raw audio, an unapproved draft, or private answers. An automatic notification can be delivered after a report is explicitly approved for sharing; the caregiver does not need to repeatedly request updates.

5. Patient Experience: Screens and UX Copy
Screen 1 — Home
A calm, accessible interface with large controls, readable text, and an optional conversational guide.

Primary action: Check my voice
Greeting: Good morning. Ready for a quick check-in?
Secondary navigation: My history, Sharing preferences
The caregiver has a separate home/dashboard with Call my parent and patient-approved reports.

Screen 2 — Enrollment (first visit)
Copy: Read this short passage a few times so we can learn what's usual for you.

Record 3–5 clean takes of the same short, standardized text.
Show Record, Stop, Try again, and One more reading controls.
Use a consistent passage (such as a short Rainbow Passage excerpt used according to applicable permissions).
Label this an initial/provisional reference, not an established clinical baseline. Additional good-quality recordings over time can improve the reference.
Screen 3 — Daily check-in
Copy: Read the passage at your comfortable pace. Tap Finish when you're done.

Show the passage and a large microphone button.
Never auto-cut off a person mid-reading; use explicit Finish.
For a Parkinson's profile only, optionally prompt: Now hold a steady “ahh” for about five seconds.
Provide a retry or accessible non-audio option if recording cannot be completed.
Screen 4 — Understanding the recording
Copy: Comparing this reading with your usual speech timing…

Show a brief, calm processing state. Do not claim medical findings while analyzing.

Screen 5A — Within expected variation
Copy: Your speech timing was similar to your previous readings today. Anything you'd like to mention?

An optional open-text or spoken answer allows the person to record something important even when the measurements look typical. A typical recording is not proof that everything is medically fine.

Screen 5B — Repeatable change
Copy: Today's reading had longer pauses than usual. We noticed a similar pattern when you tried again.

Show a neutral explanation of what was measured, not a red health warning or disease prediction. Then ask an open-ended, condition-specific question. A second recording establishes repeatability within this session, not persistence across several days.

For a COPD profile:

What happened during that pause?
If the person says I stopped to catch my breath, ask: Is that happening more often than usual? What were you doing at the time?
For a Parkinson's profile:

What happened there?
If the person says It's harder to get words out, ask: Where have you noticed that? Has being understood in everyday conversations changed?
If a person says they were distracted, reading unfamiliar text, or interrupted, record that context instead of assuming a health explanation.

Screen 6 — Review your note
Always present three distinct sections:

Section	Contents
Measured	Objective acoustic observation, with limitations and the recording context
You said	The person's own account, quoted or faithfully summarized and editable
Still unclear	Missing details, unanswered questions, or reasons the comparison may be uncertain
Actions: Edit note, Looks right, Keep private, Approve sharing.

Nothing should be shared with a caregiver before the patient's confirmation and sharing authorization.

Screen 7 — History (stretch goal)
A simple day-by-day timeline of completed check-ins, with a distinction between ordinary variation, repeatable changes, missing recordings, and approved notes. Avoid presenting this as a disease severity timeline.

Screen 8 — Caregiver dashboard
Call my parent
Call status: Queued → Ringing → In progress → Completed → Awaiting approval → Report available
Neutral states: No answer, Declined, No reading available today
Read-only, patient-approved note, with no raw audio or unapproved transcript
In the hackathon demo, any simulated call and statuses are clearly labeled Demo simulation.

6. What Makes the Conversation Intelligent?
The original idea behind VoiceShift included more natural, engaging conversations for older adults. We preserve that vision while making the first version measurable and responsible:

Start with an open invitation, not a long series of yes/no questions: Tell me how your morning has been.
Use a real signal only as a cue: a timing change can select a more relevant question, but does not establish its cause.
Ask follow-ups based on what the person said: What happened?, When do you notice it?, How does it affect your day?
Let the person correct the interpretation before anything becomes part of a report.
Keep conversation supportive and easy to use through readable, accessible UI and optional voice interaction.
Future personalization: Users could select an AI companion or a familiar conversational style. A relative-inspired avatar or synthetic voice would require informed permission from that relative, clear disclosure that it is AI, and controls to change or disable it. The system must not deceptively impersonate a real family member.

7. Measurement and Decision Logic
Acoustic signals in the core MVP
Pause fraction: internal silent gaps divided by the span from first to last speech activity.
Longest internal gap: longest silence between speech segments, excluding leading/trailing silence.
Speaking rate: syllables from the fixed passage divided by the appropriate reading duration, only when passage completion is sufficiently verified.
Recording quality: length, clipping/noise, microphone consistency, and whether the same text was read.
A voice-activity detector (VAD) supplies time stamps for speech segments. Silence alone cannot tell the system whether someone stopped to breathe, hesitated, was interrupted, or had a microphone issue.

Personal reference rules
Use recordings from the same person, passage, capture channel, and comparable setup.
Keep web and phone references separate even if audio is resampled to the same format.
Start with several clean recordings; use their median/spread as a prototype reference, not a validated clinical threshold.
Consider minimum absolute differences and repeat checks to avoid triggering on trivial noise.
Do not automatically add poor-quality or unusual recordings to the reference.
When evidence is insufficient, say We couldn't compare this recording reliably and allow the check-in to continue.
Question-selection policy
The first version can be deterministic, explainable, and safe:

usable audio + comparable personal reference?
    no  -> invite retry or ask routine check-in question
    yes -> calculate timing differences
             within prototype tolerance -> optional everyday question
             outside prototype tolerance -> offer a repeat recording
                  change repeats -> select relevant follow-up card
                  change does not repeat -> record variation, avoid assumption
The known condition chooses the question wording, not a disease verdict. A language model, if used, can help phrase follow-ups or summarize responses, but should be grounded in approved question cards and the person's actual words. Emergency symptom reports must bypass ordinary generation and receive fixed, appropriate safety guidance.

Optional research track, not part of the medical decision
For Parkinson's profiles, a separately labeled Voice Quality Index could eventually be explored using published voice features or a research model. It would be shown only as an experimental acoustic indicator, not a diagnostic probability, health score, or trigger for caregiver escalation. If it is not implemented and validated enough to explain, omit it from the demo.

8. Example Data Contract
This example uses fictional information and simulated Day 5 recordings. API fields can be finalized with the backend team; in particular, repeatable_today must not be mistaken for a change verified across multiple calendar days.

{
  "profile_id": "demo-copd-1",
  "condition": "copd",
  "day": 5,
  "label": "acted-deviation",
  "source": "simulated_five_day_history",
  "measured": {
    "pause_fraction": 0.42,
    "longest_internal_gap_sec": 0.85,
    "speaking_rate_syll_per_sec": 2.1,
    "deviation_from_baseline": "repeatable_today"
  },
  "triggered_question": "What happened during that pause?",
  "note": {
    "measured": "Longer internal pauses than the demo reference, repeated in two readings today.",
    "patient_said": "I stopped to catch my breath. It happens more on stairs lately.",
    "unresolved": ["Whether the same difficulty occurs at rest"]
  },
  "status": "awaiting_confirmation",
  "sharing_approved": false
}
The measured numbers are illustrative fixture data, not a diagnosis, a validated cutoff, or results from a real patient.

9. Proposed Technical Architecture
Proposed stack
Layer	Practical options
Frontend	React + TypeScript; responsive senior-friendly design
Backend	Python + FastAPI
Audio	Browser MediaRecorder, audio normalization, Silero VAD or similar
Decision logic	Personal baseline statistics + explicit question-card rules
Conversational layer	Approved question cards; optional LLM with structured output and deterministic fallback
Persistence	SQLite for fast prototyping; PostgreSQL or MongoDB if needed
Caregiver	Separate role, explicit linking, patient-controlled sharing
Phone (future or stretch)	Outbound-call provider with call verification, consent, and separate telephone-audio references
Suggested repository layout
VoiceShift/
├── README.md
├── frontend/
│   ├── src/
│   │   ├── pages/            # Home, Enrollment, CheckIn, NoteReview, History
│   │   ├── caregiver/        # Caregiver dashboard and simulated call flow
│   │   ├── components/       # Large buttons, recorder, waveform, timeline
│   │   ├── services/         # API client
│   │   └── types/            # Shared request/response types
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── routes/          # Profiles, recordings, check-ins, notes, sharing
│   │   ├── services/
│   │   │   ├── audio.py     # Audio validation, VAD, feature extraction
│   │   │   ├── baseline.py  # Same-person reference comparison
│   │   │   ├── dialogue.py  # Condition-aware question selection
│   │   │   └── reports.py   # Three-section note preparation
│   │   ├── models/          # API and persistence schemas
│   │   └── question_cards/  # Reviewed, source-linked prompts
│   ├── tests/
│   └── requirements.txt
├── demo/
│   ├── fixtures/            # Labeled consented recordings / synthetic scenarios
│   ├── scenarios/           # Five-day scripted history
│   └── demo-guide.md
└── docs/
    ├── architecture.md
    ├── privacy-and-safety.md
    └── research.md
This is an intended structure, not a claim that every file or integration has been built.

Suggested API boundaries
Method	Route	Purpose
POST	/api/profiles	Create an enrolled, consented demo profile
POST	/api/recordings	Upload and validate a passage recording
POST	/api/baselines	Create/update a provisional personal reference
POST	/api/checkins/analyze	Compare a recording with the relevant reference
POST	/api/checkins/{id}/answers	Store patient response and select next question
GET	/api/checkins/{id}/note	Retrieve the editable three-section draft
POST	/api/checkins/{id}/confirm	Confirm or correct the note
POST	/api/checkins/{id}/sharing	Explicitly approve or decline sharing
GET	/api/caregiver/reports	Read authorized, patient-approved reports
POST	/api/caregiver/calls	Optional future outbound call request
Endpoints are proposed integration contracts and should be updated to match the running repository.

10. The Five-Day Hackathon Demo
We do not need five real days to demonstrate the interaction. Use clearly labeled, consented teammate recordings to simulate a five-day timeline.

Demo day	Recording	Expected behavior
1–3	Same person reads normally	Initialize provisional personal reference
4	Slight variation, within prototype tolerance	No change-specific question; show ordinary variation
5, take 1	Deliberately insert a pause or slow a section	Invite an optional repeat; no medical interpretation
5, take 2	Repeat the same changed reading	Show measurable repeatability and select the appropriate question
A deliberately inserted pause or slowed/slurred word is an audio-processing test, not a simulation of COPD or Parkinson's pathology. Scripted patient responses test the dialogue workflow, not clinical accuracy.

Suggested 4–5 minute judging walkthrough
Problem + 3-word pitch: Sense → Understand → Act.
Sense: Record or replay an actual consented reading; show real measurements.
Understand: Compare Day 4 with Day 5 and reveal a repeatable timing change.
Act: Show a COPD- or Parkinson's-specific question and a scripted answer.
Patient control: Edit, confirm, and approve the three-section note.
Caregiver view: Show only the approved report; label call-state simulations.
Trustworthy failure case: Noisy audio leads to Please try again, not an invented conclusion.
For Radial Atoms, explicitly explain that a physical microphone signal changes what the software does next. The project is not merely a chatbot asking a generic daily questionnaire.

11. How We'll Evaluate the Prototype
Engineering checks
A real recording changes pause measurements in a repeatable, inspectable way.
Minor variation does not repeatedly cause unnecessary follow-ups.
Noisy, incomplete, or wrong-passage audio does not produce a confident comparison.
A typical reading still allows the person to report an important symptom.
COPD and Parkinson's profiles use different follow-up questions.
Notes retain a clean boundary between Measured, You said, and Still unclear.
A caregiver cannot access an unapproved report or a revoked link.
Web audio is never silently compared against a phone-audio baseline.
Research questions for future clinical collaboration
Does adaptive questioning capture more useful, patient-confirmed information than a fixed questionnaire?
Are results reliable across microphones, environments, languages, accents, and changes in daily routine?
How often does the system ask unnecessary questions or miss a relevant self-reported change?
Do patients find the daily habit usable, comfortable, and respectful?
Do clinicians find the resulting notes understandable and actionable?
Clinical effectiveness is not established by this hackathon demo. Future studies would need appropriate consent, diagnosed-patient cohorts, clinician review, and independent validation.

12. Privacy, Accessibility, and Safety
Opt-in enrollment: Patient participation and caregiver linking require clear consent.
Patient-owned reporting: Drafts stay private; the patient can correct and approve each shared report.
Minimal sharing: Caregivers see approved summaries and appropriate status only, not raw voice data by default.
Audio minimization: Prefer temporary processing of raw recordings; secure storage and retention controls are necessary for any real deployment.
No impersonation: A familiar voice/avatar is optional future work, and must be clearly disclosed as AI and authorized by the person whose likeness is used.
No medical verdicts: Do not show disease probabilities, new diagnoses, disease-stage labels, treatment advice, or false precision.
No emergency dispatch: If someone reports potentially urgent symptoms, present fixed emergency-help guidance rather than generating speculative advice or claiming the app is continuously monitoring them.
No negative inference from silence: Missing recordings, declined calls, and missed calls mean only that no reading is available.
Designed for older adults: Large controls, high readability, explicit recording completion, short tasks, and minimal navigation.
13. What Is in Scope?
Feature	Hackathon priority	Status to communicate
Browser microphone capture	Essential	Implement and demonstrate with real audio
Fixed-passage timing features	Essential	Show actual measured values
Personal baseline comparison	Essential	Prototype reference, not clinical validation
Repeat check + adaptive question	Essential	Real decision logic with reviewed question cards
Editable three-part patient note	Essential	Demonstrate confirmation before sharing
Five-day history	High	Clearly labeled seeded demo history
Caregiver read-only approved report	High	Demonstrate authorization; simulation is acceptable if labeled
Outbound AI phone call	Stretch	Simulated unless genuinely implemented and verified
Parkinson's voice quality index	Research stretch	Separate, non-diagnostic; omit if not justified
Disease prediction / automated treatment	Out of scope	Not represented as a capability
Scheduled calls / emergency dispatch	Out of scope	No UI or functioning workflow claimed
14. Longer-Term Vision
The original VoiceGuard concept imagined an elder-friendly AI companion and a family dashboard that kept adult children informed without requiring constant manual check-ins. VoiceShift preserves those goals while first proving a narrower, more testable interaction:

Longitudinal personalization: Learn a better individual reference through comparable, consented check-ins over time.
Patient-approved proactive updates: Automatically notify authorized relatives when a confirmed report has been approved for sharing, so the caregiver does not need to keep checking the app.
Convenient telephone access: Support verified outbound AI-assisted check-ins for people who prefer a regular phone to an app.
Optional AI companion: Natural, open-ended conversations and selectable, disclosed AI personas to improve engagement.
Evidence-linked context: Show which clinical literature motivates the monitored signals, without translating associations into unvalidated disease probabilities.
Clinician-ready summaries: Explore patient-controlled export and clinician feedback before building any healthcare-system integration.
Validated research features: Investigate condition-specific acoustic measures with appropriate patient datasets and prospective studies, while keeping them separate from the core conversation trigger.
We are intentionally not building a diagnosis engine. The product's promise is a better, more human-centered conversation based on repeatable observations.

15. Research and Inspiration
The following references motivate the design. They do not independently validate VoiceShift as a clinical tool.

Structured speech and COPD exacerbation research — motivates exploring speech characteristics in COPD.
Parkinson's acoustic voice research review — discusses potential signals and limitations.
Telehealth recording setup and acoustic measurement — supports controlling for recording conditions.
ASHA voice assessment resources — context for standardized speech assessment.
UCI Parkinson's Telemonitoring dataset — a possible research dataset for future, separately validated analysis; not a source of raw audio for our self-check demo.
American Lung Association COPD management resources — patient guidance context.
UB Hacking — hackathon and project context.
16. Team Responsibilities (Suggested)
Audio/backend: Recording intake, quality checks, speech features, personal references, comparison API, and tests.
Conversation/decision logic: Condition-aware question cards, follow-up routing, patient-answer handling, and structured notes.
Frontend/integration: Accessible check-in, note approval, demo history, caregiver dashboard, and end-to-end presentation.
Everyone is responsible for testing that the explanation shown in the interface matches what the code actually measures.

One-sentence pitch
VoiceShift uses changes in a person's own speech timing to ask more meaningful health check-in questions, preserve their account in a confirmed note, and help them share it with family on their terms.

Built as a hackathon prototype. Not intended for diagnosis, medical decision-making, or emergency monitoring.





0⋮⋮⋮⋮