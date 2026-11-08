# CCR multisignal ablation: research candidate, not a live trigger

The useful question is whether waveform-derived prosody adds information beyond
four VAD timing measurements, and whether any increment survives a separate
cohort/device/language/protocol. No disease probability or severity estimate is
exposed to the live API. The candidate predictors are F0 spread in semitones and
voiced-frame energy spread in dB. Voiced fraction and octave-jump fraction are
quality diagnostics, not clinical feature additions.

## Manifest

CSV columns: `path,subject_id,label,dataset` and optional
`passage_syllable_count`. Paths can be absolute or relative to the manifest.
Labels are 0=control, 1=PD. A subject ID must refer to one actual person globally;
reuse for all that person's recordings. Do not hide shared participants by
prefixing a new dataset ID. A participant appearing in multiple datasets is
rejected, as are conflicting labels and duplicate paths.

Example schema (replace paths with actual recordings):

```csv
path,subject_id,label,dataset,passage_syllable_count
/path/mdvr/ID00.wav,mdvr_person_00,0,mdvr,
/path/mdvr/ID01.wav,mdvr_person_01,1,mdvr,
/path/italian/B1_person_00.wav,italian_person_00,0,italian_b1,
/path/italian/B1_person_01.wav,italian_person_01,1,italian_b1,
```

Use the actual count for each dataset's actual passage if available. Never use
the app's 41-syllable Rainbow excerpt for MDVR-KCL or ItalianPVS B1. An absent
count deliberately leaves speaking rate unavailable and records that fact;
other timing features still extract. A globally unavailable feature is excluded
explicitly from the ablation report. Per-recording failures stay missing,
never silently zero-filled.

## Commands on an allocated CCR compute node

From the `backend` directory, with the project's dependencies installed:

```sh
python scripts/ccr_multisignal_ablation.py extract \
  --manifest /path/manifest.csv --output data/out/multisignal_features.csv \
  --perturbations
python scripts/ccr_multisignal_ablation.py evaluate \
  --features data/out/multisignal_features.csv \
  --output data/out/multisignal_ablation.json --permutations 300 --seed 0
```

Extraction uses CPU Praat plus the existing VAD; a GPU is not necessary.
Use CCR's account/partition/time settings from the user's working allocation;
this script does not guess Slurm resources or run a large job on a login node.
Checkpointed feature CSV separates expensive extraction from cheap reruns.
Bring back the feature CSV, `.failures.json`, `.robustness.csv`, and result JSON.
Do not add patient recordings to git.

## What the report establishes

Each participant becomes one median feature row before evaluation, giving one
vote per person. Within each dataset, stratified group-disjoint folds use an
imputer, scaler and fixed logistic classifier fit only on training data. Reported
fold subject lists allow auditing isolation. Cross-dataset runs train on one
complete cohort and test on the other without tuning on the target. Optional
label permutations happen at participant level; cross-dataset permutation
shuffles training labels only. Plus-one p-values avoid a false zero probability.
These remain exploratory comparisons with uncorrected multiple comparisons.

The separate perturbation CSV compares each recording with half gain and
additive 30 dB SNR noise. These are paired robustness probes, not extra training
participants. They show whether a putative signal could instead reflect capture
conditions. Failure/quality-flag counts by dataset and label must be inspected
before interpreting AUC. Small cohorts, class-dependent missingness, device/site
confounding and distinct passage content remain even with task-matched cohorts.

Promotion requires a prespecified increment over timing alone, independent
cohort replication, useful perturbation behavior, and later repeated within-person
assessment. A negative result is useful and should keep this candidate out of the
live baseline rather than justify relaxing the experiment.
