# Cadence — demo design (formerly VoiceShift)

**Implementation status, November 8, 2026:** this is the intended demo, not a
description of a completed UI. The current MVP primarily focuses on Parkinson's.
The API implements enrollment, check-in, one answer, confirmation and ElevenLabs
speech output. `Daily Hello Family.html` remains a separate sample dashboard
without microphone capture or calls to those routes. Phone calling, linked
caregiver authorization/sharing, note editing, completed follow-up turns and
history access remain planned. COPD/asthma extensions require separate clinical
validation. See [current status](README.md) and
[the roadmap](docs/CADENCE-ARCHITECTURE-ROADMAP.md).

One paragraph, then the exact screens and copy to build.

## The idea, in plain terms

Cadence's intended self-check is a between-visit record for people with a known
care context, currently emphasizing Parkinson's. A person reads a standard
passage and the software compares speech timing with their own references. A
repeatable difference can select a prototype question; the person's explanation
and unresolved details remain separate from the measurement. The proposed
daily/30-second experience and caregiver phone variant below are design goals,
not implemented scheduling, measured latency, or a functioning phone service.

**The pitch in three words, say this explicitly in the demo narration: Sense → Understand → Act.** Sense: the mic is the physical sensor. Understand: compare today's reading against this person's own baseline. Act: ask a different, better question because of what changed.

This is not a diagnosis tool. It never claims to detect disease. It claims to ask a better question than a static questionnaire would.

## The two entry points

- **Check my voice** — the patient does a self-check, any time, in the app.
- **Call my parent** — a caregiver (adult child) taps a button, and the system places an outbound AI call to their enrolled, linked parent, running the same check-in over the phone.

For tomorrow's demo, **build "Check my voice" as the fully real, deeply polished path.** Treat "Call my parent" as a secondary feature — fine to show as a short scripted/simulated sequence (a few screenshots of call states), but the self-check flow is what needs to actually work and look great.

## Screens to build — self-check path

1. **Home.** Two big entry points: "Check my voice" and "Call my parent." Calm, warm, clinical — not an alarm-styled health app. This is a daily habit, not an emergency tool.

2. **Enrollment (first time only).** Explain in one sentence: "Read this short passage a few times so we learn what's normal for you." Record 3–5 takes of the fixed passage (a short excerpt of the Rainbow Passage — a real standardized passage speech clinicians already use, ~15–20 seconds each). Simple record → stop → "sounds good, one more" loop.

3. **Daily check-in.** One screen: the passage text displayed, a record button, explicit "Finish" when done (not auto-cutoff).

4. **Processing (brief, 1–2 seconds).** A simple "comparing to your usual" state — this is the moment the "Understand" step happens, worth a small deliberate pause/animation so it's visible in the demo rather than instant.

5. **Outcome A — no meaningful change (the common case).** "Sounds like your usual self today. Anything you'd like to mention?" with a free-text/optional field. Fast, low-friction, done in one tap.

6. **Outcome B — persistent change detected.** This is the moment to make visually clear in the demo: show, plainly, *what* changed (e.g., "today's reading had more pauses than usual") — not a scary alert, a neutral observation — followed by the adaptive question. Use the real condition-specific language:
   - **COPD:** "What happened during that pause?" → if "I stopped to catch my breath" → "Is that more frequent than usual? What were you doing at the time?"
   - **Parkinson's:** "What happened there?" → if "it's harder to get words out" → "Where have you noticed that — and has being understood in everyday conversation changed?"

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

This richer fixture describes a proposed assembled UI record. It is not the
current `/checkin` response. The actual response has `profile_id`,
`measured.deviation_score`, `measured.deviation_from_baseline`,
`triggered_question`, and `status`; `/answer` returns `note` and
`follow_up_question` separately. Read the unchanged
[API contract](VoiceShift-API-Spec.md) before wiring the UI. No new response
fields or endpoints are introduced by this mock example.

```json
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
```

## Tone and copy rules (judges and real users will both notice violations)

- Never say "detected," "diagnosed," or imply a medical finding. Say "noticed a change" or "different than usual."
- Never show a measurement without also showing what the person actually said about it, once available.
- A missed call or missing audio is never framed as bad news — it's just "no reading available today."
- No red alert styling anywhere. This is a daily habit tool, not an ICU monitor.

## What's explicitly out of scope — don't build screens for these

Diagnosis, severity scoring shown as a verdict, medication suggestions, automated emergency dispatch, scheduled/recurring calls, inbound calls. If a scenario needs one of these, show a fixed, clearly-labeled scripted message instead of inventing a flow.
