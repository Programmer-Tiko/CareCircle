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
- The CCR cross-lingual rerun got cancelled mid-run once already (disconnected session); the script now checkpoints each dataset's embeddings to disk, so a second cancellation won't force redoing already-finished work. Rerun still pending as of this entry.
- Still open and unchanged from the audit: UI wiring status to the real API, the day 1–5 fixture audio, and the movement/balance/medication content question.

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
