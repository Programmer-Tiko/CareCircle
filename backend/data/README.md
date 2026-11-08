# Cadence data and research reproduction

Raw cohort datasets are generally downloaded separately. This directory does
contain committed research results and model artifacts; the short attributed
software-test clip is under `backend/tests/fixtures/`. Those outputs are offline
research, not a clinically validated model used by the API. Download the cohort
sources below separately and retain their terms and provenance.

1. **UCI Oxford Parkinson's Telemonitoring dataset** (public, no request needed):
   https://archive.ics.uci.edu/dataset/189/parkinsons+telemonitoring
   Download `parkinsons_updrs.data.csv`, place it here as `parkinsons_updrs.data.csv`.
   This is real data from 42 diagnosed patients, 5,875 recordings, with longitudinal
   UPDRS severity labels. Used by `app/models/train_pd_severity.py`.

2. **Figshare "Voice Samples for Patients with Parkinson's Disease and Healthy Controls"**
   (public, no request needed, DOI 10.6084/m9.figshare.23849127):
   https://figshare.com/articles/dataset/Voice_Samples_for_Patients_with_Parkinson_s_Disease_and_Healthy_Controls/23849127
   Real raw audio (.wav) from 40 diagnosed PD patients and 41 healthy controls,
   sustained vowel /a/, recorded on participants' own phones. Download via the
   figshare API (no login):
   ```
   curl -sL -o Demographics.xlsx "https://ndownloader.figshare.com/files/41836707"
   curl -sL -o PD_AH.zip "https://ndownloader.figshare.com/files/41836710"
   curl -sL -o HC_AH.zip "https://ndownloader.figshare.com/files/41836713"
   unzip PD_AH.zip && unzip HC_AH.zip
   ```
   Already downloaded, run, and validated locally — see `backend/data/pd_classifier_out/`
   for the real results (5-fold CV accuracy 0.617, ROC-AUC 0.630). Reproduce with:
   `python app/models/train_pd_classifier.py --dataset-dir <dir with Demographics.xlsx, PD_AH/, HC_AH/> --out data/pd_classifier_out`

3. **MDVR-KCL** (public, no request needed, Zenodo DOI 10.5281/zenodo.2867216):
   https://zenodo.org/records/2867216
   Real raw audio (.wav, 44.1kHz) from 16 diagnosed PD patients and 21 healthy
   controls reading the SAME paragraph aloud on a smartphone — connected speech,
   not a sustained vowel, which is what the live app's pause-timing feature
   actually needs. Download (606MB zip):
   ```
   curl -sL -o kcl.zip "https://zenodo.org/api/records/2867216/files/26_29_09_2017_KCL.zip/content"
   unzip kcl.zip "26-29_09_2017_KCL/ReadText/*"
   ```
   Already downloaded, run, and validated locally — see
   `backend/data/pd_classifier_out/pause_timing_pd_vs_hc.json` for the real
   per-file results (PD pause fraction 0.328 vs HC 0.233, p=0.008, large effect).
   Reproduce with:
   `python app/models/analyze_pause_timing_pd_vs_hc.py --dataset-dir <path to ReadText folder> --out data/pd_classifier_out`

4. **ItalianPVS** (public, no login needed, mirrored on Hugging Face from IEEE Dataport DOI 10.21227/aw6b-tg17):
   https://huggingface.co/datasets/birgermoell/Italian_Parkinsons_Voice_and_Speech
   Real raw audio from 28 diagnosed PD patients and 22 elderly healthy controls.
   **Check each group folder's own `FILE CODES.xlsx` before assuming what a
   filename prefix means** — an earlier pass guessed "PR1" was a word-list
   task from the filename alone; the actual documented codes are:
     - **B1 / B2** = reading the phonemically-balanced continuous text "Il
       ramarro della zia" — this is the real match to MDVR-KCL's "read the
       same paragraph" task. Use B1 as the primary replication.
     - **FB2** = reading phonemically-balanced isolated words — this is
       what's actually in the files named "PR1..." in this HF mirror
       (confirmed by reading one file's transcript `.txt`, which shows
       isolated words, not sentences). Secondary comparison only.
   Download either task's wav for each participant via
   `https://huggingface.co/datasets/.../resolve/main/<path from the HF file list>`
   (filter the file list for `/B1` or `/PR1` respectively).
   Already downloaded, run, and validated locally for both tasks — see
   `backend/data/pd_classifier_out/italianpvs_continuous_passage_B1_replication.json`
   (primary: **27 PD / 21 HC actually analyzed**, pause fraction p=0.044 d=0.61,
   segment duration p=0.053 d=-0.60, both same direction as MDVR-KCL; segment
   duration is not significant at 0.05) and
   `backend/data/pd_classifier_out/italianpvs_wordlist_PR1_replication.json`
   (secondary: pause fraction p=0.0001 d=1.21, segment duration p=0.21 as
   expected for a word-by-word task). Reproduce with:
   `python app/models/analyze_italianpvs_replication.py --pd-dir <PD wavs> --hc-dir <HC wavs> --out data/pd_classifier_out`

   The analysis script writes `italianpvs_replication.json` under `--out`; use
   distinct output directories for B1 and PR1 to avoid overwriting results.
   The committed B1 artifact's `note` still describes the older word-list
   interpretation; use the corrected task documentation and numerical summary.

5. **COPD search limitation.** The team did not verify a source satisfying all
   requirements during its documented search: diagnosed COPD, raw spoken or
   vowel audio, usable labels, immediate access, and clear reuse provenance.
   Evaluated sources included gated/unreleased data, cough/stethoscope audio,
   feature-only files, and uncertain interview labels/reuse terms. Some API
   searches were blocked. This is not proof that no public COPD dataset exists.
   Extracted features alone do not satisfy the raw-speech validation need.
   Current COPD cards are prototype deterministic behavior, not clinically
   approved rules. See [the project brief](../../VoiceShift-Project-Brief.md).

## Interpretation and pending research work

Public PD/control comparisons and severity correlations do not validate
day-to-day within-person alerts. Report the analyzed cohort, task, nominal
statistics and uncertainty without converting an AUC into a disease probability.
Small cohorts, multiple tests and age/device/protocol confounding remain.

`pd_classifier_out/cross_lingual_generalization.json` is the earlier PR1/word-list
versus continuous-reading result (AUC approximately 0.61/0.55, permutation
p approximately 0.20/0.34). `app/models/ccr_cross_lingual_generalization.py`
now selects B1, but no `cross_lingual_generalization_taskmatched_b1.json` is
committed in the reviewed snapshot. Do not claim the task-matched rerun finished.

The historical bootstrap interval and high within-dataset embedding AUC also
need methodological review: full-dataset preprocessing and duplicate subjects
across resampled folds can bias evaluation. The outputs remain unchanged as
research history. [The roadmap](../../docs/CADENCE-ARCHITECTURE-ROADMAP.md)
documents validation gates and known interpretation issues.
