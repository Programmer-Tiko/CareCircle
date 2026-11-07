# Data

Not committed to the repo. Download these yourself:

1. **UCI Oxford Parkinson's Telemonitoring dataset** (public, no request needed):
   https://archive.ics.uci.edu/dataset/189/parkinsons+telemonitoring
   Download `parkinsons_updrs.data.csv`, place it here as `parkinsons_updrs.data.csv`.
   This is real data from 42 diagnosed patients, 5,875 recordings, with longitudinal
   UPDRS severity labels. Used by `app/models/train_pd_severity.py`.

2. **COPD dataset** — not yet confirmed accessible without a request process.
   If you find a public one with raw audio or extracted jitter/shimmer/HNR-style
   features in the next ~20 minutes, drop it here and flag it; otherwise the
   COPD side stays rule-based (personal baseline + ALA/GOLD-sourced question
   cards) for this build, with the trained-model tier noted as future work.
