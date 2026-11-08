# Cadence: from timing to independent speech evidence

## What works now

The live path measures four statistics from Silero speech boundaries, fits a
personal median/MAD baseline, persists repeated check-ins and selects a sourced
question through validated LLM ID selection. It stores question snapshots,
answers and confirmation revisions. Those are our measurement/comparison and
conversation systems; Silero itself is a reused neural speech detector.

Four timing statistics are not four independent sensing modalities. More useful
new dimensions come from the waveform and a comparable reading protocol:

| Channel | New measurement | Product purpose | Current state |
| --- | --- | --- | --- |
| Timing | Pauses, gaps, rate, burst duration | Notice repeated timing changes | Live trigger |
| Prosody | Robust voiced pitch range in semitones | Record intonation variation independently of silence boundaries | Implemented; opt-in observed evidence |
| Energy dynamics | Voiced-frame RMS p90-p10 in dB | Record within-reading energy variation; constant gain cancels mathematically | Implemented; AGC/noise/distance remain confounds |
| Capture quality | Clipping, cancellation, insufficient voicing, unstable pitch | Mark measurements unavailable when extraction is unreliable | Implemented experimental flags |
| Phrase/word placement | Passage comparison and word-level pause location | Avoid comparing the wrong reading; contextualize pauses | Antigravity assignment |
| Phonation/articulation | CPPS/GNE, then matched-vowel formants | Additional independent acoustic candidates | Research next, not implemented |

`POST /profiles/{id}/checkin?experimental=true` extracts waveform evidence from
the original continuous WAV, persists it in `checkins.waveform_evidence` and
returns it under `measured.waveform_evidence`. Conversations retain that exact
snapshot. It does not alter the timing score or claim a pitch-related diagnosis.
Default requests leave the optional field null. Restart the backend to apply
the additive nullable column.

The local extraction smoke ran all 37 MDVR-KCL files (16 PD, 21 controls), with
no extractor failures or flags. Availability is not clinical performance. Pitch
spread medians were very similar in this extraction, so there is no reason to
promise it will improve classification. Full details:
`PROSODY-EXTRACTION-SMOKE.json`.

## Work split

Codex: experimental waveform extractor, opt-in API persistence, participant-safe
ablation, paired capture perturbations and review of the resulting evidence.

Antigravity: `ANTIGRAVITY-TASK.md` is the concrete assignment. The external agent
is not connected to this Codex session; the user must open that file in its
workspace/chat. Keep alignment code separate from the extractor and API.

Human participant: consented clean/variation/acted recordings. Current final
status from the user: not yet created. Constructed test audio is not a substitute.

## CCR: a result that determines what ships

Compare timing-only, prosody-only, and combined feature families on MDVR-KCL and
ItalianPVS B1. Aggregate by participant, keep all recordings of one participant
in the same fold, and fit preprocessing inside each training fold. Freeze
hyperparameters; evaluate transfer to the other dataset in both directions.
Report missingness and quality flags by cohort. Do not confuse cross-sectional
cohort ranking with within-person daily monitoring validation.

Run paired gain and noise variants to measure recording sensitivity. These are
not extra independent participants and never become training rows. Unknown
passage syllable counts remain unavailable; do not reuse the app's 41 count
for a different dataset passage. The runner reports the resulting reduced
feature family explicitly.

The new API observations let us inspect real captures immediately. Promotion
into the trigger requires evidence of added value and recording robustness,
followed by a versioned/calibrated scoring protocol. Appending correlated
z-scores to the Euclidean norm changes false-trigger behavior; we do not do it
merely because the extractor returns another number.

### Commands for an authenticated CCR session

Codex's SSH attempt failed public-key authentication. No CCR job was submitted.
The user can run these after the branch is available:

```bash
cd ~/CareCircle
git fetch origin
git switch codex/multisignal-experiments
cd backend
# Activate your existing project Python environment.
python scripts/build_multisignal_manifest.py \
  --mdvr-dir /actual/path/to/ReadText \
  --italian-b1-pd /actual/path/to/flattened/B1/PD \
  --italian-b1-hc /actual/path/to/flattened/B1/HC \
  --output data/out/multisignal-manifest.csv
# Use your CCR account/partition options if required by your allocation.
sbatch --cpus-per-task=8 --mem=16G --time=01:00:00 \
  --job-name=cadence-multisignal \
  scripts/run_multisignal_ccr.sh data/out/multisignal-manifest.csv
```

The Italian paths must be the verified flattened B1 directories used in the
existing replication, with pd_00.wav / hc_00.wav names. For other layouts, write
an explicit manifest with true participant IDs; do not guess IDs from chunks.
The builder intentionally rejects unknown layouts. Output is under
`backend/data/out/multisignal-v1/`: feature CSV, extraction failures, paired
robustness CSV, and ablation JSON. Bring those small artifacts back for review.
This is a CPU signal-processing/model-evaluation job; requesting a large GPU
would add no value. GPU alignment becomes useful when Antigravity has a tested
ASR/forced-alignment workload.

## Source guidance

Praat documents pitch estimation and octave-error tradeoffs:
https://www.fon.hum.uva.nl/praat/manual/how_to_choose_a_pitch_analysis_method.html
The installed parselmouth extraction uses raw autocorrelation, recorded in its
parameters; this is not a claim to use Praat's newer filtered method.

Phonation evidence is task/sex dependent; CPP is a candidate, not a proven win
for our connected-reading task:
https://www.isca-archive.org/interspeech_2023/simek23_interspeech.pdf

Matched-vowel articulation work motivates a later alignment-dependent channel:
https://pubmed.ncbi.nlm.nih.gov/22389682/
