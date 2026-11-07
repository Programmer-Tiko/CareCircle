# Data

Not committed to the repo. Download these yourself:

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

4. **COPD dataset** — not yet confirmed accessible without a request process.
   If you find a public one with raw audio or extracted jitter/shimmer/HNR-style
   features in the next ~20 minutes, drop it here and flag it; otherwise the
   COPD side stays rule-based (personal baseline + ALA/GOLD-sourced question
   cards) for this build, with the trained-model tier noted as future work.
