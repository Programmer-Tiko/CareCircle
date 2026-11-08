# CCR Knowledge Base Review & Candidate Question Units (v2)

**Document**: `docs/CCR-CORPUS-REVIEW.md`
**Structured Output**: `docs/CCR-CANDIDATE-QUESTIONS.json`
**Input Source**: `backend/data/out/knowledge_chunks.json` (311 chunks, generated via CCR job)
**Author**: Antigravity agent
**Status**: Revised Proposal Records — **`backend/app/dialogue/question_corpus.json` remains untouched**
**Date**: 2026-11-08

---

## 1. Overview & Follow-Up Scope

Following independent review by Codex (`docs/CODEX-CCR-CANDIDATE-REVIEW.md`) and project instructions (`ANTIGRAVITY-CORPUS-FOLLOWUP.md`), the 6 candidate question units were revised across three separate review lanes:

1. **Per-Span Exact Evidence Provenance** ([`docs/review_evidence_spans.md`](review_evidence_spans.md)):
   - Replaced stitched composite quotes and ellipses with discrete `evidence_spans` records.
   - Programmatically verified that every cited excerpt is a 100% exact verbatim substring of its specific chunk in `knowledge_chunks.json`.
   - Separated multi-source citations (e.g., distinguishing Parkinson's Foundation Chunk 2 from APDA Chunks 281/282 in `vocal_fatigue_check`).
   - Supplied exact chunk provenance for previously unsupported words (Chunk 281 for `"strain"` in `vocal_quality_hoarseness`; Chunk 279 for continuation in `group_and_noise_communication`).

2. **Neutral Wording & Defensible Context Gates** ([`docs/review_candidate_revisions.md`](review_candidate_revisions.md)):
   - Shortened `vocal_fatigue_check` to a single, focused concept.
   - Grounded `group_and_noise_communication` in chronic everyday conversational difficulty, separating it from situational check-in room distraction.
   - **Blocked `daytime_sleepiness_check`** from the acoustic gate: an elevated pause-fraction z-score does not clinically support inferring daytime sleepiness.
   - Reworded `fatigue_physical_vs_mental` to eliminate false exclusive binaries (allowing both physical and mental fatigue to co-occur).
   - Reworded `morning_off_period_check` neutrally without assuming whether medication or morning routine is the underlying mechanism.

3. **Adversarial Audit & Eligibility Test Cases** ([`docs/review_adversarial_audit.md`](review_adversarial_audit.md)):
   - Documented 4 reproduced runtime gaps in current `retrieval.py` keyword matching.
   - Established 6 canonical test cases (affirmation, negation, uncertainty, resolved past symptom, situational recording interruption, everyday ambient noise).

---

## 2. Chunk Scope Disclosure

Of the 311 total chunks in `backend/data/out/knowledge_chunks.json`:
- **Deep Line-by-Line Manual Audit**: Chunks 0–111 (Speech, Fatigue, Anxiety, Sleep, Fall Prevention), 202–285 (APDA Communication & Voice Handicap Index), and 298–310 (Managing Off-Time).
- **Inspected Non-Content Metadata**: Chunks 11–22, 45–58, 69–82, 95–106, 120–131, 145–157, 169–179, and 190–201 contain web page headers, donation links, helpline phone numbers, chapter dropdowns, and form fields resulting from automated HTML scraping. These were screened and categorized as non-content.

---

## 3. Revised Candidate Question Units

Full JSON is stored in [`docs/CCR-CANDIDATE-QUESTIONS.json`](CCR-CANDIDATE-QUESTIONS.json).

### Group A: Active Communication Candidates (Ready for Review)

#### 1. `vocal_fatigue_check`
- **Condition**: `parkinsons`
- **Information Sought**: `vocal_fatigue_or_evening_decline`
- **Revised Question**: *"Does your voice feel weaker or more tired as the day goes on?"*
- **Evidence Spans**:
  - Chunk 2 (PF Speech Fact Sheet): `"Is my voice weak or does it tire easily?"`
  - Chunk 281 (APDA p. 23): `"My voice is worse in the evening"`
  - Chunk 282 (APDA p. 23): `"My voice “gives out” on me in the middle of speaking"`
- **Preconditions**: `["speech_motor_cue_present"]`
- **Exclusions**: `["answer_indicates_situational_distraction"]`
- **Eligibility Basis**: Gated on patient's explicit report of voice or speech difficulty (`speech_motor_cue_present=True`). Never triggered as an assumed cause of an acoustic pause deviation.
- **Blocked**: `false`

#### 2. `vocal_quality_hoarseness`
- **Condition**: `parkinsons`
- **Information Sought**: `vocal_quality_change`
- **Revised Question**: *"Have you noticed your voice sounding hoarse, breathy, or strained recently?"*
- **Evidence Spans**:
  - Chunk 218 (APDA p. 5): `"When the airflow is reduced, it lowers the volume of the voice and makes the voice breathy and/or hoarse in quality."`
  - Chunk 219 (APDA p. 5): `"This changes the quality of the voice, making it sound breathy and/or hoarse, and makes it more difficult"`
  - Chunk 281 (APDA p. 23): `"I feel as though I have to strain to produce voice"`
- **Preconditions**: `["speech_motor_cue_present"]`
- **Exclusions**: `["answer_indicates_situational_distraction"]`
- **Eligibility Basis**: Gated on patient reporting speech/voice changes; differentiates dysphonia and vocal roughness from volume/softness (`volume_awareness`).
- **Blocked**: `false`

#### 3. `group_and_noise_communication`
- **Condition**: `parkinsons`
- **Information Sought**: `ambient_noise_and_group_communication`
- **Revised Question**: *"Is it harder for people to hear you in group conversations or when there is background noise, like in a restaurant?"*
- **Evidence Spans**:
  - Chunk 277 (APDA p. 22): `"People have difficulty understanding me in a noisy room"`
  - Chunk 278 (APDA p. 22): `"I tend to avoid groups of people because of my voice"`
  - Chunk 279 (APDA p. 22): `"I feel left out of conversations because of my voice"`
- **Preconditions**: `["initial_answer_mentions_speech_difficulty"]`
- **Exclusions**: `["recording_interrupted_by_distraction"]`
- **Eligibility Basis**: Gated on prior acknowledgment of everyday communication difficulty. Differentiates room noise during recording from ambient noise in daily life.
- **Blocked**: `false`

---

### Group B: Gated / Blocked Candidates

#### 4. `daytime_sleepiness_check`
- **Condition**: `parkinsons`
- **Information Sought**: `daytime_sleepiness_and_napping`
- **Question Template**: *"Have you been feeling unusually sleepy during the day, or finding yourself needing unexpected naps?"*
- **Evidence Spans**:
  - Chunk 84 (PF Sleep Fact Sheet): `"Still feeling tired after a full night in bed"`
  - Chunk 84 (PF Sleep Fact Sheet): `"Sleeping more during the day or napping often"`
  - Chunk 89 (PF Sleep Fact Sheet): `"Sleeping too much during the day or taking long or late naps can make it harder to sleep at night."`
- **Preconditions**: `["explicit_patient_report_of_sleepiness"]`
- **Status**: **BLOCKED** (`blocked: true`).
- **Reason**: Chunk 84 supports asking about sleepiness, but does **not** establish an acoustic pause-fraction deviation as an evidence basis to suspect daytime sleepiness. Blocked from acoustic triggering; requires an explicit patient report of daytime sleepiness or an independently scheduled routine check-in policy.

#### 5. `fatigue_physical_vs_mental`
- **Condition**: `parkinsons`
- **Information Sought**: `fatigue_physical_motor_vs_mental`
- **Revised Question**: *"Does that fatigue feel more physical in your body and muscles, more mental where it's hard to concentrate, or a combination of both?"*
- **Evidence Spans**:
  - Chunk 25 (PF Fatigue Fact Sheet): `"Fatigue is a feeling of being extremely tired, of being either physically or mentally weary."`
  - Chunk 29 (PF Fatigue Fact Sheet): `"Akinesia, or trouble starting a movement, often feels like fatigue. A person with this symptom must move slowly and will find it hard to finish a task in a regular amount of time."`
- **Preconditions**: `["initial_answer_mentions_fatigue"]`
- **Status**: **BLOCKED** (`blocked: true`).
- **Reason**: `retrieval.py` does not currently extract a fatigue flag from answer text. The unit is marked blocked rather than making it eligible unconditionally.

#### 6. `morning_off_period_check`
- **Condition**: `parkinsons`
- **Information Sought**: `early_morning_symptom_prominence`
- **Revised Question**: *"Did you record this check-in early in the morning, and do your symptoms usually feel more noticeable at that time of day?"*
- **Evidence Spans**:
  - Chunk 303 (PF Managing Off-Time, p. 2): `"Early morning “off,” before the first dose kicks in"`
  - Chunk 301 (PF Managing Off-Time, p. 2): `"Non-movement symptoms like anxiety, depression, fatigue, foggy thinking and pain may also appear or intensify."`
- **Preconditions**: `["patient_known_to_take_pd_medication"]`
- **Status**: **BLOCKED** (`blocked: true`).
- **Reason**: Gated strictly on verified pharmacotherapy status. In `retrieval.py`, `medication_status_known` is `False` by default; strictly blocked for unverified profiles.

---

## 4. Evaluated & Rejected Proposals Log

| Topic | Source Chunk(s) | Primary Reason for Rejection |
|---|---|---|
| **Pause Attribution to Word-Finding** | Chunk 2 (`speech-swallowing`) | **Core instruction violation**: *"Don't claim a pause indicates word-finding difficulty."* Conflates normal reading pauses with cognitive deficits. |
| **Facial Masking Check** | Chunks 253–254 (`APDA p.15`) | Purely visual modality; Cadence has no camera or video sensor. |
| **Medication Timing Adjustment** | Chunk 306 (`Managing Off-Time`) | **Clinical safety boundary**: System must never advise patients to alter dosages or schedules. |
| **Sleep Hygiene Checklist** | Chunks 89–90 (`sleep`) | Generic lifestyle questionnaire creep; detached from acute speech timing check-ins. |
| **Gait Freezing Probing** | Chunks 108, 110 (`fall-prevention`) | Unprompted gait screening is outside Cadence's voice-first monitoring scope. |

---

## 5. Runtime Keyword Matching Gaps & Recommendations for Codex

Our direct execution audit confirmed the 4 defects flagged by Codex:

1. **Negation Blindness**:
   - Reproducer: `"I have no trouble speaking"` activates `speech_motor_cue_present=True` and `initial_answer_mentions_speech_difficulty=True` due to literal substring `"trouble speaking"`.
   - *Recommendation*: Introduce basic negation detection before substring scoring in `compute_context_flags()`.
2. **Missing Voice Quality / Fatigue Lexicon**:
   - `"My voice feels hoarse"` and `"My voice gets tired by evening"` currently evaluate to `speech_motor_cue_present=False`.
   - *Recommendation*: Add `"hoarse"`, `"breathy"`, `"tired"`, `"strain"`, `"weak"`, `"effort"` to `_SPEECH_MOTOR_KEYWORDS`.
3. **Daily Noise vs. Recording Interruption Conflation**:
   - `"People find it difficult to hear me in background noise"` matches `"noise"` in `_DISTRACTION_KEYWORDS`, setting distraction to `True` and suppressing the communication question.
   - *Recommendation*: Separate situational check-in interruptions (dog, doorbell, phone ringing during check-in) from chronic functional communication trouble in noisy environments.
4. **Single-Turn Memory**:
   - `latest_answer = prior_answers[-1]` evaluates only the immediate last turn. If a patient confirms a symptom on turn 1, subsequent follow-up turns lose that context flag unless re-stated.
   - *Recommendation*: Differentiate cumulative session facts from turn-immediate triggers.

---

## 6. Proposed Canonical Eligibility Test Cases

| Case | Patient Utterance | Expected Flags | Expected Selection Outcome |
|---|---|---|---|
| **1. Affirmation** | *"Yes, my voice gets very tired and weak as the day goes on."* | `speech_motor_cue_present=True`, `distraction=False` | `vocal_fatigue_check` eligible & ranked top. |
| **2. Negation** | *"I have no trouble speaking today, everything felt normal."* | `speech_motor_cue_present=False`, `speech_difficulty=False` | Speech difficulty follow-ups ineligible; general check-ins remain. |
| **3. Uncertainty** | *"I'm not really sure, maybe my voice sounds a bit different but I can't tell."* | Ambiguous motor cue | Exploratory or neutral follow-up; no premature escalation. |
| **4. Resolved Past Illness** | *"I had laryngitis two weeks ago, but my voice has been completely back to normal since Monday."* | `speech_motor_cue_present=False` | Acute speech follow-ups must NOT treat resolved illness as Parkinson's decline. |
| **5. Recording Interruption** | *"Sorry for that long pause, my neighbor rang the doorbell right while I was reading."* | `distraction=True` | Attributed to interruption; baseline deviation tracker does NOT advance. |
| **6. Everyday Noisy Room** | *"I do fine talking one-on-one at home, but people can't hear me when we are out at a noisy restaurant."* | `speech_difficulty=True`, `recording_distraction=False` | `group_and_noise_communication` eligible & selected. |
