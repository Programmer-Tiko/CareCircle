"""Robustness check on the headline finding (analyze_pause_timing_pd_vs_hc.py
and analyze_voice_breakdown_pd_vs_hc.py): does PD vs HC separation on pause
fraction and speech-segment duration survive changing the VAD's sensitivity
threshold, or is it an artifact of one particular setting? Reruns the same
real MDVR-KCL recordings at three threshold values.

Usage:
    python analyze_vad_sensitivity.py --dataset-dir /path/to/ReadText --out out/
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
from scipy import stats

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.audio.vad import detect_speech_segments
from app.audio.timing_features import compute_timing_features

FILENAME_RE = re.compile(r"ID\d+_(hc|pd)_\d+_\d+_\d+")
THRESHOLDS = [0.3, 0.5, 0.7]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    files = []
    for subdir in ["PD", "HC"]:
        for wav_path in sorted((args.dataset_dir / subdir).glob("*.wav")):
            match = FILENAME_RE.search(wav_path.name)
            if match:
                files.append((wav_path, 1 if match.group(1) == "pd" else 0))

    results = {}
    for threshold in THRESHOLDS:
        pause_fraction_by_label = {0: [], 1: []}
        segment_duration_by_label = {0: [], 1: []}
        for wav_path, label in files:
            segments = detect_speech_segments(str(wav_path), threshold=threshold)
            if len(segments) < 2:
                continue
            features = compute_timing_features(segments, passage_syllable_count=1)
            pause_fraction_by_label[label].append(features.pause_fraction)
            durations = [end - start for start, end in segments]
            segment_duration_by_label[label].append(float(np.mean(durations)))

        pf_t, pf_p = stats.ttest_ind(
            pause_fraction_by_label[1], pause_fraction_by_label[0], equal_var=False
        )
        sd_t, sd_p = stats.ttest_ind(
            segment_duration_by_label[1], segment_duration_by_label[0], equal_var=False
        )
        results[str(threshold)] = {
            "n_pd": len(pause_fraction_by_label[1]),
            "n_hc": len(pause_fraction_by_label[0]),
            "pause_fraction": {
                "pd_mean": float(np.mean(pause_fraction_by_label[1])),
                "hc_mean": float(np.mean(pause_fraction_by_label[0])),
                "p_value": float(pf_p),
            },
            "mean_speech_segment_duration": {
                "pd_mean": float(np.mean(segment_duration_by_label[1])),
                "hc_mean": float(np.mean(segment_duration_by_label[0])),
                "p_value": float(sd_p),
            },
        }
        print(f"threshold={threshold}: {json.dumps(results[str(threshold)], indent=2)}")

    output = {
        "results_by_threshold": results,
        "note": (
            "Default VAD threshold is 0.5. If pause_fraction and "
            "mean_speech_segment_duration stay significant (p<0.05) with the "
            "same direction across 0.3/0.5/0.7, the PD vs HC finding is not "
            "an artifact of one specific VAD sensitivity setting."
        ),
    }
    (args.out / "vad_sensitivity_analysis.json").write_text(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
