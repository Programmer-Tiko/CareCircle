# Independent review results (Claude Code, per CLAUDE-CODE-REVIEW.md)

Reviewed `codex/ui-integration` at `1ac92c4` (then `ef0b415` after one fix made during
this pass — see Finding 1). Workspace used: the tracked clone at
`/private/tmp/cadence-handoff-reconcile`. I did not merge main, change thresholds, promote
any opt-in observation into the trigger, touch secrets, or run a new CCR job. One commit was
made: a documentation accuracy fix (Finding 1), which is a reversible, non-scope-changing
correction of my own earlier error.

## Tests actually run, and the limits of this pass

I ran the suite myself rather than trusting the stated counts:

```
227 passed, 17 skipped in ~5s
```

All 17 skips are opt-in environment gates with explicit, accurate skip-reason strings — not
hidden failures:
- 10 require `TEST_CONVERSATION_DB_URL` / `TEST_TIGER_DATA_URL` (a real Postgres/TimescaleDB
  test database — I did not stand one up for this pass)
- 2 require `CADENCE_ASR_SMOKE=1` (a real cached-Whisper smoke test)

This means I independently reproduced the suite being green, and confirmed the skip reasons are
real gates rather than suppressed failures — but I did **not** reproduce the "243 passed, no
skips" claim in `docs/UI-INTEGRATION-VERIFICATION.md`, since that requires real Postgres/Tiger and
a real cached ASR model that I didn't provision here. The claim is consistent with what I found
(same test files, same gating logic, same reasons my run skipped them) but is not independently
re-verified end to end. If winning the "ran it for real" argument matters for judging, someone
should actually do that full run once more, close to the demo, with fresh eyes.

I also did not deep-audit every new module line by line — `phrase_alignment.py` (554 lines) and
`alignment_validation.py` (338 lines) are covered by unusually large test files
(`test_phrase_alignment.py` is 670 lines, `test_alignment_validation.py` 184) which all pass; I
read representative sections and the module docstrings rather than the full implementation. I did
directly read `backend/app/api/speech.py` in full (the `/transcribe` endpoint) and found it
careful: 20 MiB upload cap, WAV-format validation before touching the file further, the
`CADENCE_WHISPER_MODEL` env var is regex-validated against path-traversal before being used to
locate a checkpoint, no fallback to a network download, and failures surface as HTTP 503/502
rather than silently degrading. No bug found there.

## Ranked findings

### 1. [Fixed during this review] Handoff doc overstated the ItalianPVS result

**File**: `VoiceShift-HANDOFF-TO-CODEX.md:55-56` and `:232` (before this review's fix).
**What I found**: my own handoff document said the `mean_speech_segment_duration` finding
"replicated... in a second language (ItalianPVS, task B1)." It did not replicate at the
conventional significance threshold — `backend/app/audio/timing_features.py:14-17` and
`VoiceShift-Project-Brief.md:46,92` both already carry the honest number: same direction, but
p=0.053, d=-0.60, explicitly **not** called significant. Codex had already corrected the code
comment and the brief; my own handoff doc was the one place this project's "verify every number"
rule had lapsed, and it was my own error to begin with.
**Status**: fixed and pushed as commit `ef0b415` on `codex/ui-integration`, both lines corrected
to match the brief's language.
**Why this matters**: this is exactly the kind of overclaim the team has repeatedly said it
cares about avoiding. Worth a final grep across any pitch/Devpost copy before submission for the
word "replicated" near ItalianPVS, in case it propagated further than these two files.

### 2. Conversation gating is exactly the product gap the review brief describes — confirmed, with the exact lines

**Files**: `backend/app/api/main.py:201`, `backend/app/api/conversations.py:97`,
`backend/app/dialogue/question_cards.py:31-34` (Parkinson's initial card text: `"What happened
there?"`).

I traced the full path end to end:
- `main.py:201` sets `'status': 'awaiting_answer' if result.triggered else 'no_change'` — the
  only place that decides whether a conversation can open at all.
- `conversations.py:97`, inside `start()`: `if row is None or not row['triggered'] or
  row['note_status'] is not None: raise HTTPException(409, ...)` — a second, redundant gate on
  the same flag.
- `frontend/cadence.js:376-384` branches on `result.status === 'awaiting_answer'`; the `else`
  branch hides the conversation panel and shows "Reading saved. The repeated-change threshold was
  not met. You can still add a personal note."

This confirms the brief's description precisely: a non-triggered check-in gets a static note box,
never an adaptive follow-up, no matter what the patient might want to report. One thing worth
adding to the brief's framing: **the first question of a triggered conversation is not currently
RAG-selected either** — `conversations.py:120-121` always inserts the deterministic card text from
`question_cards.py` as turn 1 (`id='legacy-initial'`). The RAG selector (`selector_core.py` /
`groq_selector.py`) only engages from turn 2 onward, inside `answer()`. So "adaptive from question
one" isn't literally true today, triggered or not — worth knowing before describing the system
that way in a demo.

### 3. The eligibility logic needed for a safe fix is already in place — this is why the fix can be minimal

**File**: `backend/app/dialogue/retrieval.py:141` —
`"measured_pause_fraction_elevated": feature_scores.get("pause_fraction", 0.0) > 1.5`.

This is the important discovery for the proposal below: follow-up question *eligibility* already
re-derives its own per-feature elevation threshold from `feature_scores`, independently of the
global `triggered`/`PersistentDeviationTracker` flag that gates whether a session can open at all.
In other words, extra evidence-grounded questions are already gated on "did this specific feature
actually move," not on "did the 2-consecutive-reading rule fire." That means opening a
conversation on every check-in will not, by itself, unlock inappropriate extra questions — the
existing precondition logic in `retrieval.py` already protects against that. I verified this by
reading the function directly, not inferring it from the docs.

### 4. Backward-compatibility edge case the minimal fix needs to handle

**File**: `backend/app/api/conversations.py:120` — `question = Question(..., text=row['question_text'], ...)`.

`checkins.question_text` is currently `NULL` for every historical row where `triggered` was
false, because `pipeline.py`'s `evaluate_checkin()` only computes a `question_text` when
`persistent` is true. If the gating relaxation below is implemented naively, retroactively
opening a conversation on an old untriggered check-in would try to seed turn 1 with `NULL` text.
The fix needs an explicit fallback (constant neutral text, or compute it in `start()` itself when
the stored value is `NULL`), not just removing the `triggered` check.

### 5. CCR multisignal AUC numbers verified byte-for-byte against the committed artifact

**File**: `backend/data/out/multisignal-v2/ablation-fixed.json`.

I did not take the brief's quoted numbers on faith — I loaded the JSON and read the actual
`within_dataset.auc` values:
- `timing`: italian_b1 = 0.6837, mdvr_kcl = 0.6815
- `combined`: italian_b1 = 0.7432, mdvr_kcl = 0.7351

These match "Combined vs timing CV AUC: Italian 0.743 vs 0.684; English 0.735 vs 0.682" in
`CLAUDE-CODE-REVIEW.md` exactly (rounding only). Participant counts also check out (49 + 37 = 86,
matching the top-level `participants: 86`). I also checked that this result is **not** overclaimed
anywhere it could leak into pitch copy: it doesn't currently appear in
`VoiceShift-Project-Brief.md` at all, and `docs/CCR-MULTISIGNAL-ARTIFACT-AUDIT.md:50` explicitly
says "Do not add prosody z-scores to the live trigger based on these results." Good discipline —
no fix needed here, flagging as confirmed-accurate rather than a bug.

### 6. Corpus v3 additions and exclusions verified against the diff, not just the summary

**File**: `backend/app/dialogue/question_corpus.json`, diffed against `main`.

Exactly three new unit ids appear in this branch's diff: `vocal_fatigue_check`,
`vocal_quality_hoarseness`, `group_and_noise_communication` — matching "Three reviewed
communication questions promoted to corpus v3" precisely. The corpus now totals 17 units. I also
read `docs/CCR-CORPUS-REVIEW.md:92-134` for the exclusion reasoning behind
`daytime_sleepiness_check` and a rejected "Medication Timing Adjustment" proposal — both are
declined on genuinely sound clinical-safety grounds (an elevated pause-fraction z-score doesn't
license inferring daytime sleepiness; the system must never suggest altering medication timing).
This is a real strength worth highlighting in a demo narrative, not just a gap list: the team is
turning down plausible-sounding corpus units for the right reasons.

## Plain-language assessment

**Works, verified directly by me**: VAD → 4-feature timing extraction → personal-baseline
trigger → RAG selection → server-side validation, end to end, with a real passing test suite in a
clean environment. The emergency-keyword bypass still short-circuits before any model call. The
`/transcribe` endpoint is defensively written. The CCR research numbers quoted in review docs are
real, not rounded-up, and the team is correctly keeping the research signal (prosody, severity
regression) out of the live trigger.

**Experimental / opt-in, correctly labeled as such in code**: pitch-spread and voiced-energy
variation (`observation_reference.py`, `prosody_features.py`) are UI-default-enabled but
confirmed NOT in `FEATURE_ORDER` (`personal_baseline.py:13`) — i.e., not wired into the trigger,
exactly as claimed. Passage verification (`verify_passage=true`) is optional and gates on a
real transcript match, not a rubber stamp. Local ASR is opt-in and cache-only.

**Missing from the original patient experience, confirmed real**: adaptive conversation is only
reachable after two consecutive elevated check-ins; a patient with no acoustic deviation who
wants to report something has no adaptive outlet today, only a static note box. This is Finding 2
above, and it's a real product gap, not a bug in the sense of broken code — the code does exactly
what it's built to do, it's just not built to do the thing the original vision described.

## Minimal proposal: always-available conversation

Scoped specifically to what Finding 3 already makes safe, without touching the trigger or
eligibility logic at all:

1. **`backend/app/dialogue/question_cards.py`**: add one neutral card per condition, e.g.
   `QuestionCard(condition="parkinsons", cue="neutral_initial", question_text="How did speaking
   feel today?", source="design decision — always-offered neutral opener", review_status="prototype")`.
2. **`backend/app/pipeline.py`, `evaluate_checkin()`**: always populate `question_text` — the
   existing triggered-card text when `persistent` is true, the new neutral card otherwise. Keep
   `triggered`/`persistent` meaning exactly what it means today; it still exists in the result and
   still drives history labeling and (via `feature_scores`) the real eligibility gating in
   `retrieval.py`.
3. **`backend/app/api/main.py:201`**: `'status': 'awaiting_answer'` unconditionally — there's
   always a `question_text` to seed a session with now.
4. **`backend/app/api/conversations.py:97`**: drop the `not row['triggered']` clause from the 409
   guard; keep the `note_status is not None` check. Add the fallback described in Finding 4 for
   legacy rows where `question_text` is `NULL`.
5. **No change needed to `retrieval.py`** — this is what makes the change minimal. Eligibility for
   extra evidence-grounded follow-ups is already independently gated on per-feature elevation and
   patient-reported concerns (Finding 3), not on the global trigger.
6. **`frontend/cadence.js:321,385-384`**: reword the history/result copy so it no longer implies a
   conversation only exists because something was detected — e.g. "Reading saved · a few questions
   are ready" regardless of trigger state, with the trigger state shown separately and
   informationally rather than gating the panel's existence. Do not word it in a way that implies
   illness or that the absence of extra follow-ups means "nothing is wrong."

This preserves every constraint in the review brief: no faked trigger, no weakened 2-reading rule,
and patients can report a concern on an ordinary day — point 2 of the brief's own three bullets
("extra evidence-grounded questions only for repeated acoustic differences or explicit patient
reports") is already satisfied by Finding 3's existing logic, not something this change needs to
build.

## Speech practice: review of a separate future mode

This should be a genuinely separate mode, not a toggle on the daily check-in, for a reason that's
already acknowledged in the review brief and worth stating plainly: deliberately changing how you
speak — louder, slower, different words — would distort the personal baseline this whole product
is built on. The two need to be structurally incapable of touching the same reference data, not
just conventionally kept apart.

**What the evidence actually supports offering**, grounded in the three sources named in the
review brief:
- LSVT LOUD's own description of its target is *normal, healthy loudness*, not maximum volume —
  "louder" is clinician-calibrated, not a number the app can produce from an energy-spread metric.
- SPEAK OUT!'s core idea is speaking with intent/deliberate articulation, not a louder/faster/slower
  dial.
- The Parkinson's Foundation materials support practicing personally meaningful phrases
  (greetings, things the person wants to say clearly), with playback for self-comparison.

**What this product can honestly offer today**: a practice screen where a patient (ideally with
their SLP) picks a small set of personally useful phrases, records them, and plays them back for
self-comparison — logging that a practice session happened, not scoring it. **What it cannot
honestly offer**: a loudness target, a rep count, a duration, or any claim that the current
energy-spread measurement (`prosody_features.py`) is a calibrated SPL/loudness reading — it isn't
one, and `docs/CCR-MULTISIGNAL-ARTIFACT-AUDIT.md` doesn't claim otherwise for the acoustic
measurements more generally. Specific exercises, intensities, and phrase lists should be something
a qualified SLP supplies or approves, not something the system generates.

**Minimal protocol boundary, concretely**: practice recordings must never reach
`fit_baseline()` / `per_feature_deviation()` (`personal_baseline.py`). The cleanest way to
guarantee that structurally rather than by convention is a separate capture endpoint (e.g.
`/practice`, distinct from `/checkin` and `/enroll`) that has no code path into the baseline-fitting
or deviation-scoring functions at all — not a shared endpoint with a mode flag that something
could someday forget to check. This is a recommendation for the next feature, not something I
implemented in this review pass, per the brief's instruction to review and propose rather than
build it unasked.
