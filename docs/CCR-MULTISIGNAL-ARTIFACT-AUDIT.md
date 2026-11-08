# CCR multisignal artifact audit — November 8, 2026

Fetched commit `96f0c1b` and copied its four artifacts into the local workspace.
The feature CSV SHA-256 matches the saved report exactly:
`ac1729569c4d9659721babc3dee84b7513aff48e1f6795a92783f7487f65e2d2`.

Recomputed all twelve observed AUCs locally from the saved feature CSV, with
zero new permutations: all match the CCR report to tolerance 1e-12. Verified
within-dataset fold audits: no participant crosses train/test, every participant
appears in exactly one test fold. The report does not store individual predicted
probabilities, so this is reproduction of aggregate AUC and split auditing,
not comparison of saved per-person prediction vectors.

| Feature family | Italian CV | MDVR CV | Italian -> MDVR | MDVR -> Italian |
| --- | ---: | ---: | ---: | ---: |
| Timing | 0.68367 | 0.68155 | 0.72619 | 0.70408 |
| Prosody | 0.70918 | 0.71131 | 0.46726 | 0.56973 |
| Combined | 0.74320 | 0.73512 | 0.73512 | 0.71088 |

No significant incremental benefit over timing has been established. The stored
permutation tests compare each family's AUC to chance, not paired improvement
between families. This is cross-sectional cohort analysis, not validation of
within-person daily alerts. Keep waveform measurements experimental.

## Availability and capture findings

- 86 unique participants: MDVR 16 PD/21 control, Italian B1 28 PD/21 control.
- Speaking rate unavailable in all 86 because actual passage syllable counts
  were not supplied. No other timing feature is missing.
- One Italian control (`italian_b1_hc_06`) is clipped; the extractor correctly
  suppresses its two prosody values rather than substituting zero. The evaluator
  imputes missing values inside training folds, as documented.
- 172 perturbation rows: half-gain and 30dB-noise for each recording. On the 85
  baseline-valid recordings, half-gain changes pitch spread by exactly zero;
  energy spread changes only at floating-point precision.
- Added 30dB noise: median absolute pitch-spread change 0.02586 semitones,
  p90 0.12006. Energy-spread changes: median 0.12474dB, p90 0.42642dB.
- Important tail failure: `italian_b1_hc_19` changes pitch spread by -5.81657
  semitones under added noise, with no quality flag. The octave-jump heuristic
  does not guarantee reliable pitch tracking. Do not describe noise robustness
  solely by median change or treat no flag as proof of valid capture.
- `italian_b1_pd_19` has zero internal pause and mean speech segment 1.1s,
  implying a single short detected burst. This needs raw-audio inspection for
  passage completeness before using this recording as a comparable paragraph.
  It was not removed post hoc to improve metrics. The old replication required
  at least two segments and analyzed 27 PD, explaining the new denominator.

## Next evidence decision

Do not add prosody z-scores to the live trigger based on these results. Before
promotion, review the short/unstable recordings, add capture-quality checks and
predeclare sensitivity rules; then assess paired incremental value. Phrase
verification from Antigravity addresses whether the intended passage was read.
The tail failure motivates pitch-estimator agreement/voicing diagnostics rather
than assuming every unflagged F0 summary is trustworthy. No additional CCR
extraction is necessary merely to reproduce these saved results.
