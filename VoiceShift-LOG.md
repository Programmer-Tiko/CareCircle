# Cadence / VoiceShift / CareCircle — project log

## Repository audit — November 8, 2026

The current project name is **Cadence**; the repository remains CareCircle and
legacy paths remain intact. This audit used `origin/main` at `45f43f0`. Read the
[README](README.md) for the actual architecture/setup and
[the roadmap](docs/CADENCE-ARCHITECTURE-ROADMAP.md) for proposed features.

- The hackathon MVP primarily focuses on Parkinson's. COPD has working
  prototype cards/API condition handling, but no separate project-level COPD
  monitoring validation; asthma is future scope.
- The backend has four TimescaleDB-backed core routes and `/speak`. Previous
  cloud/database and live ElevenLabs verification is recorded in the API notes.
  This review reran the suite: 34 passed, including cloud integration tests.
  Historical results below must not be mistaken for a fresh research run.
- The HTML dashboard has sample records, local settings/playback and optional
  Claude-hosted summaries. Code inspection found no browser recorder or calls
  to the backend. Caregiver authorization, report sharing, notifications, phone
  capture, and emergency assessment are not implemented.
- Question retrieval is deterministic lookup/keyword matching; all four cards
  are `prototype`. The planned Adaptive Clinical Question Engine and reviewed
  Clinical Question Library do not exist as runtime services.
- The API accepts one answer per check-in and returns follow-up text; it cannot
  accept that follow-up's answer through a second `/answer`. `/confirm` is not a
  sharing permission. These are current contract limits, not completed flows.
- Existing cross-sectional research is exploratory, not clinical validation of
  daily personal-baseline monitoring. The primary ItalianPVS B1 output analyzed
  27 PD / 21 HC; segment-duration p≈0.053 is not significant at 0.05. Its JSON
  still has an old word-list `note`. Existing bootstrap/preprocessing methods
  need research review; outputs and scripts remain untouched.
- The committed cross-dataset negative result mixes language/task differences.
  A B1 rerun script exists, but its result is not committed in this snapshot;
  protocol matching would not eliminate all other confounds.
- The documented COPD search did not establish a qualifying dataset, with
  access/provenance limits. Neither an API access claim in an older note nor
  the list of rejected sources proves that no public dataset exists anywhere.

The earlier session record below is preserved for contributions and research
history. Its statements that the live monitoring mechanism is “validated” or
that all timing features generalize should be read with the qualifications
above. It also describes a different contributor's workspace and old build
plans; those are not current local setup instructions.

## Follow-up — November 8, 2026 (Claude), responding to the audit above

Two of the audit's open items are now resolved, not just acknowledged:

- **The scaling/bootstrap methodology issue is fixed, not just flagged.** Verified the audit's claim directly against the code (it was correct), then fixed feature scaling to happen inside a per-fold `Pipeline` in all four affected scripts, and replaced `bootstrap_classifier_ci.py` entirely with `permutation_test_combined_classifier.py` (same label-permutation method already used correctly for the embeddings result). Reran every affected analysis against the real re-downloaded datasets. Differences were negligible everywhere (0.630→0.624, 0.679→0.680, 0.75→0.747, 0.89→0.887) — same conclusions, now correctly computed. The invalid bootstrap CI is gone; its replacement gives a clean result (observed AUC 0.747 beats 299/300 label-shuffles, p=0.0033). Details and full diff context in the brief's research table.
- **A real end-to-end live test of the API passed**, using the real credentials now in `backend/.env` (Tiger Cloud + ElevenLabs, not mocks): enroll (4 reference takes) → check-in (elevated but not yet persistent, correctly didn't trigger on one reading) → second check-in (persistent, correctly triggered the COPD question) → answer (correctly classified the breath-related cue, returned the right follow-up) → confirm → `/speak` (real MP3 returned, 58KB). The stateless tracker-rebuild-from-DB-history design actually works across separate requests, confirmed live, not just in tests. One test profile (`live-test-1`) now exists in the real Tiger Cloud database — harmless, but worth knowing it's there if it shows up in a demo.
- **The task-matched CCR rerun completed.** With the task-type confound removed (both sides now continuous-passage: MDVR-KCL ReadText vs. ItalianPVS B1), cross-dataset generalization still fails: AUC 0.628/0.628, neither significant (p=0.29/0.14, chance reaches 0.80-0.86). **Correction (caught by Codex, not self-caught):** this rules out "it was just the task mismatch" as an explanation, but it is not an isolation of language alone — cohort, site, recording device, passage content, and protocol still differ between the two datasets. Precise framing: a task-matched cross-dataset negative result, evidence against assuming transfer, not evidence that language specifically is the cause. Result: `backend/data/pd_classifier_out/cross_lingual_generalization_taskmatched_b1.json`.
- Still open and unchanged from the audit: UI wiring status to the real API, the day 1–5 fixture audio, and the movement/balance/medication content question.

## Integrated — real multi-turn RAG conversation, live-tested end to end

Codex finished the conversation-state half (durable sessions, question snapshots/provenance, reload recovery, duplicate-answer protection, confirmation tied to a note revision — see `backend/app/api/CONVERSATIONS.md`). Wired my RAG selection into its `get_selector` seam via `backend/app/dialogue/conversation_adapter.py`, tested by validating the adapter's output against the real `Selection` pydantic model, not a guess at its shape. Wired into `main.py` via `application.dependency_overrides[get_selector]`.

Ran a real five-turn conversation against the live API, real Groq, real cloud DB — not scripted, not stubbed: each answer produced a genuinely different, cited, grounded follow-up (symptom → communication impact → repetition frequency → rate change → volume awareness), each with a real source citation attached. This is the actual "AI changes its questioning in real time" behavior, verified live, going multiple turns deep rather than capped at one follow-up.

Found a real bug by actually running it rather than just testing in isolation: the corpus had a "pd_initial" unit duplicating conversations.py's own hardcoded turn-1 question under a different ID, so it slipped past the already-asked check and got reselected five turns into the conversation. Removed it — conversations.py always seeds turn 1 itself, the selector never needs to produce it.

Known honest gap, carried forward explicitly rather than hidden: `measured.features` in the conversation context is raw feature values, not per-feature z-scores. `personal_baseline.per_feature_deviation()` exists but isn't threaded through checkins → conversations yet. The adapter passes an empty `feature_scores` dict rather than computing a flag from the wrong scale — units gated on that (e.g. breath_support_phrasing) stay ineligible until that wiring lands.

60 tests passing (56 unit, 4 against real local PostgreSQL).

## RAG question selection — built, Claude's half of the agreed split with Codex

Codex is building persisted multi-turn conversation state; Claude built the selection side, per an explicitly negotiated integration boundary (selector input: condition + per-feature evidence + prior Q/A + latest answer; output: question id, evidence ids, validated text, ask/complete/abstain). New: `backend/app/dialogue/question_corpus.json` (9 Parkinson's question units, real sourced excerpts from Parkinson's Foundation and APDA patient-education material, not research papers), `retrieval.py` (metadata filter + lexical ranking, no vector DB at this scale), `validation.py` (the actual enforcement — eligible-set membership, evidence provenance, verbatim patient-quote check, template-only rendering), `gemini_selector.py` (selects an id, never generates text; model call injectable so tests need no real key; malformed output degrades to abstain, never a crash). Also fixed two real bugs the architecture audit found: `describe_measured_deviation` no longer hardcodes a pause-based description regardless of which feature moved (added `per_feature_deviation` to `personal_baseline.py`, additive), and `cue_resolved`/`classification_succeeded` are now distinct so an unclassified answer stays honestly unresolved. 49 tests passing (28 new/updated). `GEMINI_API_KEY` not yet provisioned — everything is built and tested against a stub; wiring the real key is a one-line change once available. Not yet integrated with Codex's persistence layer — waiting on that to land.

## Earlier session record (retained)

**Read this first if you're picking this project up cold** (new session, context ran out, etc.). This is a running log, not the pitch doc — for that, read `VoiceShift-Project-Brief.md`, which stays current and is what judges would see. This file exists so an AI or person resuming mid-hackathon doesn't have to re-derive everything from git history.

**Event:** UB Hacking 2026, Radial Atoms track (sponsor: Radial Ventures). Rubric: Sense → Understand → Act, AI + physical-world sensing, judges value functional over complicated. Team of 3: this user (research/backend, working with Claude), a UI teammate, and a third teammate running Codex in parallel on the backend/API. Repo: github.com/Programmer-Tiko/CareCircle (the actual shared repo — this session's local working copy is a separate, non-git `VoiceRadial` folder synced to CareCircle by hand via a cloned-elsewhere git checkout).

## The product, in one paragraph

A between-visit check-in for people already diagnosed with COPD or Parkinson's. They read a short standard passage into a mic; the system compares today's pause/timing pattern against *their own* past recordings, not a population norm. A persistent, repeatable deviation triggers a condition-specific follow-up question instead of a generic one; the patient's own answer, not the acoustic measurement, becomes the note. Never claims to diagnose — explicitly a "better question," not disease detection. A caregiver variant ("Call my parent") does the same thing over a phone call; deprioritized, not built.

## Status by track, as of now

**Research (this session, Claude):** Strong, extensively validated. See "Key findings" below. Currently idle between CCR jobs; last thing done was fixing a task-matched rerun of the cross-lingual generalization test (queued, not yet run by the user on CCR).

**Backend/API (teammate's Codex):** Essentially done and verified for real, not just code. `backend/app/api/main.py` — four endpoints (enroll/checkin/answer/confirm) on TimescaleDB (Tiger Cloud, live, verified against both local TimescaleDB and a real free Tiger Cloud instance), plus `/speak` (ElevenLabs, live-verified: got real MP3 bytes back). 34/34 tests passing including real-DB integration tests, concurrent-request tests, restart-persistence tests. Targets two MLH prize tracks (Best Use of Tiger Data, Best Use of ElevenLabs) — both genuine architectural fits, not bolted on. Spec: `VoiceShift-API-Spec.md`.

**UI (other teammate):** `Daily Hello Family.html` in repo root. Last checked, it included movement/balance/medication/"near-fall" tracking that goes beyond VoiceShift's actual voice-only scope — **flagged to the user as a possible misalignment, not yet confirmed resolved.** Demo-facing spec: `VoiceShift-Demo-Brief.md` (screens, copy, mock JSON shape). Unknown whether UI has been wired to the real API yet or is still pure mock data.

**Most time-critical open item, not delegable to any AI:** the demo's day 1–5 fixture audio (3 clean reads, 1 typical-variation, 2 acted-deviation) has not been recorded by a human as of the last check. The whole demo narrative depends on this existing.

**CCR (user's HPC access, used for heavier compute jobs):** Used for: (1) Telemonitoring severity-regression training (led to retiring the live "voice quality index" feature, see below), (2) a 300M-param multilingual embedding model (XLSR-53) cross-lingual generalization test (completed, real negative result, see below), (3) a corrected task-matched rerun of #2 is written and ready but not yet run.

## Key findings (research), chronological, most important first

**The live mechanism (pause-timing, personal baseline) is validated on real patients, independently, twice:**
- MDVR-KCL (English, Zenodo, public): 16 PD + 21 HC reading the same connected paragraph. Pause fraction PD 0.328 vs HC 0.233, p=0.008, d=1.07. Segment duration (shorter speech bursts in PD) p=0.016. Dose-response confirmed within PD group using real Hoehn-Yahr/UPDRS scores encoded in filenames: segment duration vs H&Y r=-0.80 (p<0.001). Robust across VAD sensitivity thresholds (0.3/0.5/0.7, all p<0.03).
- ItalianPVS (Italian, HuggingFace mirror of IEEE Dataport, public): 28 PD + 22 HC. **Correction made mid-session:** initially analyzed the wrong task (guessed "PR1" = word-list from the filename; the dataset's own `FILE CODES.xlsx` shows the real continuous-passage match to MDVR-KCL is code **B1** — "Il ramarro della zia"). Corrected/primary result on B1: pause fraction p=0.044 d=0.61; segment duration now borderline p=0.053 d=-0.60 (same direction as MDVR-KCL — the earlier wrong-task result had wrongly concluded this didn't replicate at all). Word-list (PR1/FB2) kept as secondary: pause fraction p=0.0001 d=1.21 (stronger); segment duration p=0.21 (expected, word-by-word lacks continuous rhythm). **Lesson applied:** check a dataset's own task documentation before inferring from filenames.

**Deep embeddings: real within-dataset signal, but does not generalize cross-lingually:**
- wav2vec2-base on sustained-vowel data (figshare, 81 real PD/HC): AUC 0.68 (vs 0.63 hand-engineered).
- wav2vec2-base on MDVR-KCL connected speech: AUC 0.89. A naive bootstrap CI came back absurd ([0.83,1.0]) — **caught and rejected**: resampling 37 subjects with replacement duplicates exact 768-dim embeddings into both train/test folds. Correct check: permutation test (shuffle labels, rerun), chance tops out at 0.83 across 300 shuffles; real result beats all of them.
- **CCR job, XLSR-53 (300M params), cross-lingual:** train English (MDVR-KCL) → test Italian, and vice versa. AUC 0.61 / 0.55, neither significant (permutation p=0.20 / 0.34). **This result currently conflates language with task type** (used ItalianPVS's PR1/word-list, the same mistake as above, since this script predates that fix) — fixed and queued for a rerun using B1 (continuous, task-matched). Until that reruns, treat the existing negative result as "language+task shift," not "language shift alone."
- **Takeaway used in the brief:** interpretable timing features generalize across language/protocol/task; embeddings don't generalize out-of-domain despite higher within-dataset AUC. This is why the live app's trigger is built on transparent timing features, not a trained classifier — now an empirical argument, not just a safety one.

**Severity regression (predicting UPDRS from voice): failed, and that's informative, not just a null result.**
- UCI Telemonitoring dataset (42 real PD patients, CCR job): predicting absolute UPDRS from sustained-vowel features: R²=-0.35 (worse than the mean). Diagnosed why: between-subject baseline severity variance (range ~6-36) swamps within-subject variance (~1-4) — the model was being asked to predict something confounded by who-is-just-generally-sicker, not what-changed.
- Reframed as within-subject deviation: still R²=-0.09. Direct per-subject correlation (feature vs. own UPDRS over time): median r≈0.02-0.03, ~55% same-sign (barely above chance).
- **Decision made because of this:** retired the planned live "voice quality index" (sustained-vowel-based trained severity score shown to the patient) from the product entirely. It's now offline-only evidence in the brief, never patient-facing. This also simplified the live app (no sustained-vowel capture step needed).

**COPD: no public raw-audio dataset found, after an extensive, honest search — documented as a real field-wide pattern, not a search failure.**
- Ruled out (both independently by Claude and by Codex's research pass): COPDVD, Danish COPD dataset, PC-GITA, NeuroVoz, UK COVID-19 Sounds (no speech in open version), Coswara (messy labels, broken folder links).
- Checked platforms directly: IEEE DataPort, OSF, Mendeley, Harvard Dataverse, GitHub, Zenodo (note: Zenodo's search UI blocks some browsing tools / spoofed user-agents with 403 — **use the plain REST API, `zenodo.org/api/records?q=...`, without a Mozilla UA string, which works**).
- Found **two new real citations** (not downloadable, but real, recent, relevant): a 2026 University of Cádiz telehealth study (16 patients, 4,741 patient-days, **daily sentence-reading task** — exactly VoiceShift's mechanism — pause count/duration change p<0.01 before exacerbation) and an 18-patient Nature *Scientific Reports* smartwatch speech study. Both request-only, like the original Augsburg study already in the brief. Three independent serious studies all gated the same way = a real privacy/IRB-driven pattern in this field, not insufficient searching.
- **Rejected on ethical grounds, not just data-quality:** a GitHub repo (`PythonVoiceExtraction`) with real audio labeled COPD/healthy — scraped from named, identifiable real patients' personal YouTube health-advocacy videos, no license, no sign of consent for this reuse. Different and more serious problem than messy labels.

## Architecture decisions currently in force

- Tier 1 (drives the dialogue trigger): personal-baseline deviation on pause fraction / longest gap / speaking rate, deterministic, no ML. `backend/app/models/personal_baseline.py`.
- Tier 2: retrieval-constrained question cards + note assembly, deterministic lookup, no LLM required to function (one could be layered on top later for phrasing). `backend/app/dialogue/`.
- Tier 3 (offline only, never shown to patient): the severity-regression/classification research described above. Exists as evidence, not a feature.
- Fixed phrase: a short Rainbow Passage excerpt (a real, named, standardized clinical elicitation text), not an arbitrary phrase.
- Cadence: daily by default, taper to every 2-3 days when stable.
- VAD: Silero VAD, wrapped in `backend/app/audio/vad.py` (loads audio via `soundfile`, not `torchaudio.load`, to avoid needing an extra `torchcodec` dependency).

## File index

- `VoiceShift-Project-Brief.md` — the pitch/spec doc, current and judge-facing. All research findings are cited here with sources and honest caveats.
- `VoiceShift-Demo-Brief.md` — UI teammate's spec: screens, copy, tone rules, mock JSON shape.
- `VoiceShift-API-Spec.md` — Codex's build spec: endpoints, Tiger Data schema, ElevenLabs integration.
- `backend/app/pipeline.py` — ties VAD → timing features → personal baseline → dialogue into two functions: `evaluate_checkin`, `process_answer`. `build_take_from_audio` is the shared helper both enrollment and check-in use.
- `backend/app/api/main.py` — the live HTTP API (Codex).
- `backend/data/README.md` — every dataset used: where to get it, exact download commands (most need no login), what was found, how to reproduce.
- `backend/data/pd_classifier_out/` — every analysis's raw JSON/CSV output, reproducibly named.
- `backend/tests/` — 21 baseline tests (audio/dialogue/pipeline) + Codex's API tests (34 total with real-DB tests enabled).

## Open items / next steps

1. Run the task-matched CCR rerun: `python app/models/ccr_cross_lingual_generalization.py --workdir /scratch/voiceshift_data --out data/out` (writes to a new filename, won't collide with the existing task-confounded result).
2. **Record the day 1-5 fixture audio** — human task, blocking the demo.
3. Confirm whether the UI has been wired to the real (now-verified) API, or is still mock-only.
4. Re-confirm the UI's movement/balance/medication content question from earlier — may or may not still be relevant depending on what's changed.
5. Optional, lower priority: COPD dataset search is reasonably exhausted; not worth further time unless a genuinely new lead surfaces.

## Keeping this file current

Claude: update this file after any major finding, pivot, or correction — not after every small edit. Push it to CareCircle the same way as everything else. If resuming cold, read this file fully before re-reading the brief or touching code.

## Codex handoff pickup — November 8, 2026

Read `VoiceShift-HANDOFF-TO-CODEX.md` and reconciled against a fresh clone of
`https://github.com/Programmer-Tiko/CareCircle` at `fd9fc9d` in
`/private/tmp/cadence-handoff-reconcile`. That commit already contains the CCR
outputs, so no further CCR command or transfer is needed. Copied both artifacts
into this workspace: 311 chunks, ten distinct source URLs, finite 311x768 matrix;
JSON embeddings and NumPy rows agree. No generated chunks were promoted into
patient-facing corpus units automatically. Manual source/chunk review remains.

Completed the pending fourth-feature integration: nullable additive checkins
columns `mean_speech_segment_duration` and `feature_scores`, four-value INSERT,
raw features and signed scores in `/checkin` responses, persisted evidence copied
into conversation snapshots, and score-aware legacy note assembly. Added neutral
speech-burst-duration note wording. Older profiles with only three baseline
features return a clear 409 for new check-ins; historical rows remain readable
without fabricating missing evidence. A new profile is required for new captures.

Corrected the fragmentation verification: preserve the same a+b speech content,
split each chunk into three pieces, insert 0.6s gaps, and require exactly six VAD
segments before interpreting results. Baseline median burst duration 3.275s,
fragmented mean 1.1667s, signed z=-5.9876; the first elevated reading does not
trigger, the second does. Reference MAD is 0.3521s, not the numerical floor.
This is constructed-audio software verification, not clinical validation.
Reproducer: `backend/scripts/verify_fragmentation.py`; metrics:
`docs/FOUR-FEATURE-VERIFICATION.json`. No real participant audio is committed.

Regression run with isolated local PostgreSQL schemas: 70 passed, three
TimescaleDB-specific tests skipped. The new real-audio HTTP contract test covers
enroll/checkin/conversation, four-feature score norm, persisted score reuse,
fresh-app recovery, and legacy-profile handling. Schema creation exercises the
additive ALTER statements against the original checkins shape. No cloud schema
or live provider call was made in this pickup.

Research wording correction: the MDVR-KCL severity correlation motivates the
fourth feature; the ItalianPVS B1 segment-duration difference has matching
direction but p=0.053 and is not a significant replication. Kept existing
research artifacts intact.

Demo-fixture status: user's final correction is **not yet created** (supersedes
an initial "ready elsewhere" reply). Consenting human clean/variation/acted
recordings remain outstanding. UI remains deprioritized and untouched.

## Independent waveform channels — November 8, 2026

User explicitly authorized parallel agents and a larger CCR/product exploration.
Two coding agents built waveform prosody extraction and the CCR ablation runner;
a third reviewed primary-source evidence. External Antigravity is in this same
workspace but has no control connection here. Its concrete assignment is
`ANTIGRAVITY-TASK.md`: fixed-passage verification and word-level pause placement,
with a later path toward articulation, without editing others' API/extractor work.

Added experimental waveform-derived F0 p90-p10 range in semitones and voiced
frame RMS p90-p10 spread in dB, plus voicing coverage, octave-jump and clipping/
cancellation diagnostics. Uses Praat raw autocorrelation on continuous audio,
not Silero segment boundaries. Unreliable measurements are null. This does not
revive the retired severity classifier or label ASR/acoustic values as disease.

Live integration: opt-in `/profiles/{id}/checkin?experimental=true` persists
`waveform_evidence` JSONB and returns it under measured; conversation snapshots
retain it. It does not change the timing trigger. Candidate-feature promotion
requires incremental value, capture robustness and scoring recalibration.

Actual local runs: all 37 MDVR-KCL recordings extracted without errors/flags;
74 paired perturbations tested half gain and 30dB noise. Half gain left spread
metrics effectively unchanged; median absolute noise-induced deltas were
0.01670 semitones and 0.09273dB. Unknown dataset passage counts made speaking rate
explicitly unavailable in 37 rows; other timing and prosody fields were present.
No disease-performance improvement is claimed. Evidence is in
`docs/PROSODY-EXTRACTION-SMOKE.json` and `docs/PROSODY-ROBUSTNESS-SMOKE.json`.

CCR runner compares timing/prosody/combined, aggregates participant medians,
uses fold-local preprocessing and participant-disjoint evaluation, and evaluates
frozen cross-dataset transfer in both directions. Perturbations never become
training samples. Added a verified-layout manifest builder and an sbatch runner.
See `docs/MULTISIGNAL-PLAN.md` for exact commands and promotion criteria.
SSH access here failed with publickey; no CCR job was submitted. User's existing
authenticated CCR session can run the prepared job. No GPU is required for this
CPU extraction/ablation; alignment may later justify GPU work.

Full regression with isolated local PostgreSQL: 83 passed, 3 TimescaleDB-specific
tests skipped. Seven new extractor tests, five ablation tests, and an API/SQL
persistence test cover the new work. UI untouched. Demo recordings remain a
human task; no new clinical results are inferred from constructed fixtures.

## CCR multisignal-v2 report — November 8, 2026

User supplied terminal output for completed job 26746762 (4m39s): 86 recordings,
86 participants. All timing fields except unknown-count speaking_rate extracted;
one recording lacked prosody. The 86 logged issues are exclusively deliberate
UnavailablePassageCount, not audio-read failures. Transfer timing AUC:
Italian->MDVR 0.72619 (p=0.08911); reverse 0.70408 (p=0.17822). Prosody:
0.46726 (p=0.49505) / 0.56973 (p=0.50495). Combined: 0.73512 (p=0.10891) /
0.71088 (p=0.23762). These are user-reported outputs, not locally inspected raw
artifacts. Combined gains <0.01 do not establish incremental value, and the
permutation p-values test ranking against chance, not superiority over timing.
Keep prosody experimental; no live trigger change justified by this run.

Within-dataset evaluation reported a class-missing fold for all families. Fixed
the runner to stratify participant IDs directly using StratifiedKFold, then map
all participant recordings into each fold. This replaces heuristic SGKF class
balancing without leaking participants. Regression checks 101 shuffled label
assignments at the MDVR 16/21 imbalance; both classes remain in every fold and
each participant appears exactly once in held-out predictions. Re-evaluation
only needs the existing feature CSV; no audio re-extraction is necessary.

## Local audit of returned CCR artifacts — November 8, 2026

Fetched `96f0c1b`; verified feature SHA256 and fold participant isolation.
Recomputed all twelve observed AUCs from features.csv: exact agreement within
1e-12, with no new permutations. Full audit:
`docs/CCR-MULTISIGNAL-ARTIFACT-AUDIT.md`. Prosody helps within-cohort ranking but
has weak transfer, and paired incremental significance has not been tested.
Keep it experimental. Notable quality findings: clipped Italian hc_06 is
correctly suppressed; noisy hc_19 shifts pitch spread by -5.8166 semitones with
no flag; Italian pd_19 contains a single 1.1s detected burst (old analysis
excluded single-segment recordings). No participant was dropped to improve
results. Review raw capture/phrase completeness and tracking reliability before
promoting candidate features or claiming general noise robustness.

## Full workflow verification — November 8, 2026

User requested whole-flow testing after revised Antigravity candidates. Verified
16/16 exact source spans but did not promote proposals: existing context flags
still mishandle negation, voice fatigue, interruption, noisy daily conversation
and symptom memory. The proposed interruption case must not claim the tracker
never advanced: check-in scoring is persisted before the later answer.

Independent alignment review found/fixed four further gaps: exact cached-path
loading (no named-model downloader), normalized empty ASR token index drift,
standalone expected punctuation index drift, and global timestamp ordering.
Focused helper suite passed 97 with two optional ASR skips. Real cached Whisper
was then executed in a separate temporary Python 3.11 environment, with model
weight downloading explicitly blocked: synthetic full passage matched at bounded
disagreement 0.0345, different-content attributed speech mismatched at 0.8966.
One transcriber instance handled both. Core backend environment was unchanged.

Actual localhost HTTP + isolated Tiger Cloud schema + live Groq + live ElevenLabs
workflow passed: enrollment, two-check-in persistence, waveform evidence, five
selected follow-ups, a sixth answer saved under graceful abstention with
uncertainty, stale revision rejection, confirmation, duplicate requests, fresh
app recovery, Timescale hypertable and 56,049-byte MP3. Near-identical short
fixture references produce numerical-floor MAD/huge scores: this is mechanical
verification, not score calibration. All test schemas were removed.

Installed Chrome headless with a file-simulated microphone passed actual
MediaRecorder capture, WAV conversion, three-take enrollment, recorded check-in,
controlled long-gap trigger, legacy answer and confirmation against isolated
Tiger Cloud. No browser JS errors. Not a human microphone test and not a
multi-turn UI (that wiring does not exist yet). Corrected stale HTML count copy
from placeholder 40 to the real 41; no visual redesign or dashboard edits.

Final full regression from backend/ with cloud and local SQL integrations:
186 passed, 2 optional ASR tests skipped, one PyTorch/Python deprecation warning.
Separate real-ASR smoke passed as above. Reports and reproducible harnesses:
`docs/END-TO-END-STATUS.md`, LIVE-WORKFLOW-VERIFICATION.json,
BROWSER-WORKFLOW-VERIFICATION.json, REAL-ASR-VERIFICATION.json and verify_* scripts.

Original-idea delivery: real self-check core is implementable now, but finish
browser session/turn/TTS wiring, phrase-evidence integration, corrected context
and explicit resolution, non-triggered symptom reporting and editable note
review. History is stored but not exposed as an authorized history UI. Caregiver
sharing requires identity and separate consent; phone path remains unbuilt.
No diagnosis/progression/medication claim follows from current research.

## Integrated teammate UI — November 8, 2026

The user authorized replacing unsupported dashboard content and integrating the
real system. Fetched GitHub before editing: main remained fd9fc9d; the existing
feature branch was 7363896. Work is on codex/ui-integration, preserving main.
The new UI retains the purple rounded-card design while removing fictional
families, disease tabs, invented scores/charts, medication/oxygen panels,
host-Claude summaries, and pretend calling/sharing. FastAPI serves the page and
assets, with profile discovery, actual history, and exact-word personal reports.

Added optional local cached Whisper through a separate prepared Python 3.11
environment; core .venv is unchanged. Voice answers are transcribed for editing
before Send. Optional phrase verification gates enrollment/check-ins before
scoring; matching is not overall capture certification. Enrollment can fit
separate experimental pitch/energy references from three usable takes, and the
UI shows descriptive differences without changing the timing trigger.

Added source links/excerpts, revision-safe note corrections, Finish for now,
manual question/note playback, and reload recovery. Tested context rules now
handle negation, voice fatigue/hoarseness, symptom memory, and recording versus
everyday noise. Three independently reviewed communication questions entered
corpus v3 with exact evidence spans; three other proposals remain excluded.

Final Python 3.11 suite: 243 passed, no skips, including real cloud/local SQL and
cached-model ASR checks. Chrome acceptance used a file-simulated microphone,
actual MediaRecorder/WAV capture and SQL; provider stubs are explicitly labeled.
It covered enrollment, personal reports without a trigger, multi-turn answers,
review without auto-send, correction, stale revision rejection, confirmation,
early finish, reload/history, keyboard/mobile layout, mic denial and service
errors. Final run stored four check-ins and two confirmed sessions, with no
browser JavaScript errors. Its isolated schema was removed.

A separate browser run used actual Tiger Cloud, local Whisper, Groq and
ElevenLabs: the recorded answer yielded 45 recognized words, and real question
and note MP3s played. Nine selections succeeded; the tenth rapid call hit a
rate limit. That answer and uncertainty were preserved through correction and
confirmation. This was graceful degradation, not natural completion. Normal
check-ins now have a configurable four-question budget and no automatic Groq
retries; separate tests verify the last answer is saved without another call.

Real ASR passage-gating HTTP verification accepted three synthetic passage
references and a matching check-in, rejected different-content speech with 422,
and retained only one stored check-in. Human/device acceptance remains pending.
No new CCR work was run and no clinical monitoring claim follows. Reports and
reproduction commands are in docs/UI-INTEGRATION-VERIFICATION.md.

Launcher acceptance also passed from the actual working folder after sync:
Tiger Cloud additive startup, root UI/assets HTTP200, ASR ready, TTS configured,
41-syllable passage. The temporary port18080 server was stopped cleanly.
