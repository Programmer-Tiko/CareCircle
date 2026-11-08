# ItalianPVS audio graphs

Small public-data pilot, not COPD validation. No model training or diagnosis.

Source: https://huggingface.co/datasets/birgermoell/Italian_Parkinsons_Voice_and_Speech
Original: https://doi.org/10.21227/aw6b-tg17 (Dimauro and Girardi).
The mirror declares CC BY 4.0. Cite the original dataset and its associated papers.

The script selects the first three subjects in source-path order in each of the
elderly healthy-control and Parkinson's folders who have both B1 and VA1 files.
These are source task codes (B1: first text reading; VA1: first /a/ vowel).
Task interpretation follows published protocol and filename conventions; confirm
against FILE CODES.xlsx before task-specific statistical analysis. Young controls
are excluded. This is a convenience sample, not an age/sex matched study.

Run `python research/italianpvs/prepare_graphs.py` from the project root.
Dependencies: numpy, scipy, matplotlib. No credentials needed. The exact source
revision is saved in revision.txt and reused on subsequent runs.

Outputs:

- raw/: unmodified WAV downloads under local sample IDs; ignored by Git.
- plots/: waveform, spectrogram and RMS envelope per recording; comparison.png
  shows all spectrograms with the same color limits.
- arrays/: compressed NumPy files containing PSD, time/frequency axes and RMS
  arrays for later analysis; ignored by Git.
- manifest.csv: source paths/URLs, diagnosis group, subject IDs, task codes,
  checksums, original sample rate/channels, duration, peak and RMS amplitude.

Waveforms are scaled by the PCM full-scale range, not peak normalized. Stereo
is averaged for graphing only; original files remain unchanged. No denoising,
trimming, resampling or filtering. Spectrogram: Hann window 25 ms, hop 10 ms,
one-sided PSD, dB relative to 1 full-scale squared/Hz, floor -120 dB. Display
range is 0–8 kHz (or Nyquist if lower), color range -120 to -20 dB. RMS uses
the same window/hop. Only the displayed waveform may be subsampled.

Keep subjects together in any later train/test split. Graph differences can
reflect recording gain, task execution, age or equipment; these figures do not
establish disease effects or replicate a statistical finding. Folder-derived
diagnosis labels are retained, not independently clinically reverified.
