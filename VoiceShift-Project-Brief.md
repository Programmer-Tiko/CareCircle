# Cadence

Build and research brief for UB Hacking 2026 / Radial Atoms. Previously
VoiceShift / CareCircle; this filename is retained for existing links.

## Current focus and status

Cadence is an AI-assisted, voice-guided health check-in prototype. The current
hackathon MVP primarily focuses on Parkinson's disease and uses the loop
**Sense -> Understand -> Act**: accept a standardized reading, compare measurable
speech timing with that individual's reference takes, then ask a relevant
question and distinguish what was measured from what the patient reported.

This is not a diagnostic medical device. Acoustic changes do not identify a
cause, and a typical sample does not rule out illness. The current software
mechanism is tested, but the longitudinal clinical monitoring hypothesis is not
validated by the public-dataset comparisons below.

The [README](README.md) describes the actual stack and launch instructions.
[The API contract](VoiceShift-API-Spec.md) and
[API implementation notes](backend/app/api/README.md) describe the five existing
routes. [The architecture and roadmap](docs/CADENCE-ARCHITECTURE-ROADMAP.md)
separates proposed features from working components.

| Status | Scope |
| --- | --- |
| Implemented and software-tested | WAV upload, Silero VAD, three timing features, personal median/MAD reference, two-check-in trigger, prototype question lookup, note/confirmation, TimescaleDB history, and ElevenLabs text-to-MP3. |
| Separate UI prototype | `Daily Hello Family.html`: sample caregiver records, charts, local settings/audio playback, optional host Claude summaries. No microphone capture or backend API calls are present. |
| Planned MVP integration | Browser recording/WAV encoding, current API wiring, MP3 playback, frozen passage/count, human clean/acted demo fixtures, follow-up completion, note corrections and history access. |
| Future product/research | Reviewed adaptive questioning, medical-history and wearable context, authorized caregiver reports/updates, phone capture, separate disease validation and prospective monitoring evaluation. |

The `copd` condition label and its prototype cards work as software routes;
that does not mean the COPD use case has been clinically validated. Asthma is
future work. The only current condition values are `copd` and `parkinsons`.

## Actual measurement and dialogue mechanism

- WAV audio is loaded using `soundfile`, converted to mono 16 kHz, and passed to
  pretrained Silero VAD. Timing ignores silence before the first and after the
  last detected speech segment.
- Features are pause fraction, longest internal gap, and syllable count divided
  by speech duration. The API uses placeholder count **40**; it neither verifies
  the spoken passage nor estimates its syllables from a transcript.
- Enrollment uses 3-5 clean reference takes. The baseline stores per-feature
  median and scaled MAD; a zero MAD is floored at 1e-6. A multifeature robust
  z-score norm >=2.0 on two consecutive check-ins triggers a question. These
  are prototype parameters, not clinical thresholds.
- `profiles` holds baseline JSONB; `checkins` is a TimescaleDB hypertable with
  one row for every check-in. Recent scores are replayed per request, so no
  in-memory per-profile tracker must survive a restart. Profile row locks
  serialize updates.
- Four condition/cue cards in `app/dialogue/question_cards.py` are labeled
  `prototype`. Selection and answer classification are deterministic lookup and
  keyword matching. There is no backend LLM, semantic search, clinician review
  record, or evidence retrieval service.
- `/answer` returns a three-bucket note and optional follow-up. It stores the
  patient's words/status, and rejects a second answer for that check-in. The
  full returned note is not separately persisted. `/confirm` changes status;
  it neither corrects content nor grants sharing permission.
- `/speak` voices explicitly supplied text through ElevenLabs. It can be called
  by a future UI for the question, follow-up, or report read-back; it does not
  implement speech recognition, a voice agent, or an outbound call.

The trigger's multifeature score can rise because of rate or another feature,
so the current generic note wording about longer pauses needs refinement before
claiming a feature-specific explanation. Current references are keyed only by
profile, not channel, phrase or device. There is no enrollment-update flow or
adaptive check-in scheduling.

## Research evidence retained in the repository

These are exploratory offline results reported in committed files, not a
fresh model training run or measures of clinical diagnostic performance. The
[datasets guide](backend/data/README.md) retains download and reproduction
commands. Source studies and project background remain linked below.

| Analysis | Stored finding | Interpretation boundary |
| --- | --- | --- |
| MDVR-KCL connected reading | 16 PD / 21 HC; pause fraction 0.328 / 0.233, nominal p=0.008; mean speech segment 2.09s / 2.81s, p=0.016. The detailed feature artifact reports pause-fraction d about 1.00. | One session per participant, small cohort, possible age/recording confounding, exploratory multiple tests. A group difference does not validate personal change detection. |
| MDVR-KCL severity association | Within 16 PD participants, segment duration vs Hoehn-Yahr Spearman r=-0.80, p=0.00022; pause fraction r=0.73, p=0.00145. | Cross-sectional association; not a causal dose-response experiment or longitudinal tracking validation. |
| VAD sensitivity | Both headline MDVR-KCL timing features retain their direction at thresholds 0.3, 0.5, 0.7; nominal p approximately 0.006-0.025. | Robustness to these settings, not proof of generalizability or clinical sensitivity/specificity. |
| ItalianPVS B1 primary replication | **27 PD / 21 HC actually analyzed**; pause fraction 0.265 / 0.196, p=0.044, d=0.61; segment-duration p=0.053, d=-0.60. | Continuous passage, matching the task category; segment duration is borderline and not significant at 0.05. Cohort composition and protocols still differ. |
| ItalianPVS PR1/FB2 secondary comparison | 28 PD / 22 HC; pause fraction 0.347 / 0.178, p=0.000092, d=1.21; segment-duration p=0.214. | Isolated-word list, not continuous reading. Do not substitute its stronger effect for the B1 result. |
| Connected-speech classifier — **corrected** | 21 timing/quality features on 37 participants: CV AUC 0.747 (was 0.75 before fixing feature scaling to fit inside each CV fold instead of on the whole dataset first). | Offline cohort ranking only. Fix verified to change nothing material — same conclusion, more correctly computed. |
| Bootstrap CI — **replaced, not just flagged** | The flagged bootstrap (scaled before folds, resampled with replacement before CV, so duplicate participants could cross folds) is fixed: `permutation_test_combined_classifier.py` replaces it with the same label-permutation method already used for the embeddings result. Observed AUC 0.747 beats 299/300 label-shuffles (empirical p=0.0033). | A clean significance check, not a leaky confidence interval. The old flagged artifact is gone, not just annotated. |
| Connected-speech embeddings — **corrected** | 37 participants; within-dataset AUC 0.887 (was 0.89) vs handcrafted 0.738 (was 0.74); 0 of 300 shuffled-label runs reached observed AUC (maximum about 0.83, from the already-correct permutation script, unchanged by this fix). | The artifact reports empirical p=0, not a true zero probability. Finite permutation uncertainty, small samples, preprocessing and other biases remain. An earlier naive embedding bootstrap was rejected because duplicates could cross folds. |
| Cross-dataset embeddings — **task-matched rerun completed** | Both sides now use the continuous-passage task (MDVR-KCL ReadText, ItalianPVS B1), removing the task-category confound: English→Italian AUC 0.628, p=0.29; Italian→English AUC 0.628, p=0.14 (chance alone reaches 0.80–0.86 in permutation). Still not significant either direction. | This is a task-matched cross-dataset negative result, not an isolation of language alone — cohort, site, recording device, passage content, and protocol still differ between the two datasets. Useful evidence against assuming transfer; not evidence that language specifically is the cause. |
| Figshare sustained vowel — **corrected** | 40 PD / 41 HC: handcrafted accuracy 0.630, AUC 0.624 (was 0.630 before the same scaling fix); embeddings accuracy 0.617, AUC 0.680 (was 0.679). | Sustained /a/, not the app's connected-reading task. Differences from the fix are negligible — same conclusion either way. |
| UCI Telemonitoring | 42 patients: feature-vs-own-UPDRS median correlations near zero (roughly -0.02 to 0.03), sign consistency about 52-60%. | These vowel-derived features did not supply convincing personal severity tracking in this analysis. Earlier session notes also report R-squared -0.35 / -0.09 for regression; those fit metrics are not stored in the committed correlation-summary file. |

Preserve `backend/data/pd_classifier_out/` and `backend/data/out/` outputs.
The B1 JSON's `note` still contains an old word-list interpretation; the
corrected task and numeric summary above take precedence.

**The scaling/bootstrap methodology flagged above has now been fixed** (not just documented) in `train_pd_classifier.py`, `train_pd_classifier_embeddings.py`, `analyze_voice_breakdown_pd_vs_hc.py`, and `analyze_embeddings_connected_speech.py`: feature scaling now fits inside each cross-validation fold via an sklearn `Pipeline`, not on the whole dataset before splitting. `bootstrap_classifier_ci.py` is retired and replaced by `permutation_test_combined_classifier.py`, using the same label-permutation method already trusted for the embeddings result. Every affected number was rerun against the real data, not just recalculated in theory — differences from the fix were negligible everywhere (same conclusions, more correctly computed), except the bootstrap CI, which is gone entirely rather than patched.

Timing results motivate further study. They do not demonstrate that this
prototype diagnoses Parkinson's, tracks progression, predicts exacerbations,
or has proven utility for a single person's daily monitoring. Keep every
population-trained classifier/severity score offline. Never turn AUC,
classification accuracy or the baseline distance into a disease probability.

## COPD evidence and search boundaries

The original research identified potentially relevant COPD literature: a
50-person structured-speech study, a University of Cadiz/INiBICA telehealth
abstract reporting 16 patients / 4,741 patient-days, and a wearable speech study
reporting 18 patients. These are literature leads and external findings cited
by the team, not Cadence validation. Consult each primary source before reusing
its clinical claims; they do not establish the prototype's thresholds.

During the documented search, the team did not verify a dataset satisfying all
of its requirements: diagnosed COPD participants, raw reading/talking/counting
or vowel audio, usable diagnosis/severity labels, immediate download, and clear
reuse provenance. Evaluated leads included gated/unreleased collections,
non-speech cough or stethoscope sounds, and feature-only data. A surfaced
interview-audio GitHub repository had uncertain clinical label provenance and
reuse terms, so it was not used for validation. Some search/API requests were
blocked; do not call the search exhaustive or claim no public COPD speech
dataset exists anywhere. Some previously excluded Parkinson's datasets were
access checks, not COPD evidence. COPD and asthma require separate validation.

## Product direction and planned workflows

The intended user is a person with a known care context who wants a useful
between-visit record. The current hackathon emphasis is Parkinson's. Future
COPD, asthma and other applications should combine voice with authorized
medical history, confirmed diagnoses, symptoms, prior answers, independently
measured physiology/wearables, and clinically reviewed evidence.

A proposed Adaptive Clinical Question Engine would use observed changes, known
conditions, patient explanations, missing distinguishing information, prior
evidence, and approved rules to choose useful questions. A proposed Clinical
Question Library would evolve through published research, longitudinal studies,
clinician review, authorized confirmed outcomes, independent testing and
version-controlled releases. No unreviewed diagnostic rule should be promoted
automatically. An LLM may eventually help phrase approved content; it must not
invent diagnoses or unsupported probabilities. Detailed design and review gates
are in [the roadmap](docs/CADENCE-ARCHITECTURE-ROADMAP.md).

The planned self-check flow needs real browser capture, note correction,
completed follow-up turns, and optional explicit sharing. A proposed caregiver
flow additionally needs verified identities, active patient authorization,
recipient/scope checks, revocation and patient-approved report access. Phone
calling, callback verification, voicemail handling and separate phone references
are deferred. Existing `/confirm` is neither a consent system nor a publishing
operation. Reports must keep measured observations, patient reports and
unresolved questions separate. A missing reading is missing data, not illness.

The earlier team responsibilities remain: speech/backend integration,
frontend/UX, and conversation/research, with ownership coordinated before edits.
Phone work is future scope, not a third required working adapter for this MVP.
Daily check-ins and a later taper to every 2-3 days were design ideas; no scheduler
or validated frequency recommendation is implemented.

## Demo fixture and acceptance plan

Use fictional profiles and consenting teammate audio for demonstrations. The
short committed test fixture checks software mechanics, not clinical utility.
A human demo fixture set is still needed:

| Take | Label | Purpose |
| --- | --- | --- |
| Days 1-3 | Clean reference | Establish one person's comfortable reading reference. |
| Day 4 | Typical variation | Exercise ordinary timing variation. |
| Day 5, twice | Acted deviation | Exercise two consecutive elevated check-ins and question selection. |

Label acted clips clearly; do not train disease models on them or call them
real patient validation. Acceptance should include end-to-end browser/API
behavior, unusable/noisy input, changed device/phrase, typical audio with a
reported symptom, follow-up correction, provider failures, and report consent.
The latter consent/caregiver tests depend on future implementation. Compare the
usefulness of approved questions with a fixed questionnaire in later studies.
No authentication, deployment protection, emergency assessment, medication
advice, or automated dispatch is supplied by the current API.

## Source index retained from the original research

1. [CDC county COPD estimates](https://www.cdc.gov/copd/php/case-reporting/county-level-estimates-in-copd.html)
2. [ECMC Pulmonary & Sleep Clinic](https://www.ecmc.edu/health-services/outpatient-services/pulmonary-sleep-clinic-and-function-testing-lab/)
3. [Can Passive Cough Monitoring Predict COPD Exacerbations?](https://pubmed.ncbi.nlm.nih.gov/40223505/)
4. [Improved Precision of COPD Exacerbation Detection in Night-Time Cough Monitoring](https://pmc.ncbi.nlm.nih.gov/articles/PMC12387909/)
5. [Systematic review of cough monitoring in chronic respiratory disease](https://pubmed.ncbi.nlm.nih.gov/40044185/)
6. [American Lung Association COPD Action Plan and Management Tools](https://www.lung.org/lung-health-diseases/lung-disease-lookup/copd/living-with-copd/copd-management-tools)
7. [GOLD 2026 Report and Pocket Guide](https://goldcopd.org/2026-gold-report-and-pocket-guide/)
8. [Hyfe Cough Monitoring](https://hyfe.com/faq)
9. [TensorFlow YAMNet tutorial](https://www.tensorflow.org/tutorials/audio/transfer_learning_audio)
10. [Official YAMNet source and class map](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet)
11. [UB Hacking](https://ubhacking.cse.buffalo.edu/)
12. [Silero VAD reference implementation](https://github.com/snakers4/silero-vad)
13. [Rainbow Passage](https://dailycues.com/learn/iqpedia/pages/rainbow-passage/)
14. [ASHA Recommended Protocols for Instrumental Assessment of Voice](https://pubs.asha.org/doi/10.1044/2018_AJSLP-17-0009)
15. [High Frequency Remote Monitoring of Parkinson's Disease via Smartphone (HopkinsPD)](https://arxiv.org/pdf/1601.00960)
16. [Oxford Parkinson's Telemonitoring Voice Dataset](https://www.emergentmind.com/topics/oxford-parkinson-s-telemonitoring-voice-dataset)
17. [Voice Samples for Patients with Parkinson's Disease and Healthy Controls (figshare)](https://figshare.com/articles/dataset/Voice_Samples_for_Patients_with_Parkinson_s_Disease_and_Healthy_Controls/23849127)
18. [MDVR-KCL: Mobile Device Voice Recordings at King's College London (Zenodo)](https://zenodo.org/records/2867216)
19. [ItalianPVS: Italian Parkinson's Voice and Speech (Hugging Face mirror)](https://huggingface.co/datasets/birgermoell/Italian_Parkinsons_Voice_and_Speech)
20. [A Longitudinal Multivariate Assessment of Acoustic and Motor Biomarkers in COPD Telehealth](https://zenodo.org/records/23600864)
21. [Association of daily lung condition in COPD patients with wearable speech and physiological data](https://pmc.ncbi.nlm.nih.gov/articles/PMC12480672/)
