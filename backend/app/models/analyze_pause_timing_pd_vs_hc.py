"""The test that actually matters for VoiceShift's live mechanism: does
pause-timing from CONNECTED/READ speech differ between real diagnosed PD
patients and healthy controls? Everything tested before this (jitter,
shimmer, HNR, wav2vec2 embeddings) used sustained vowels, which is not what
the live app measures. This runs the live app's own VAD + timing-feature
code (audio/vad.py, audio/timing_features.py) against real patients reading
the same connected text passage.

Source: MDVR-KCL ("Mobile Device Voice Recordings at King's College
London"), Zenodo DOI 10.5281/zenodo.2867216. 37 subjects (16 PD, 21 HC)
reading the same paragraph, recorded on an actual smartphone -- the closest
real-world analog to VoiceShift's own capture scenario we've found.

This is a cross-sectional diagnosis-type comparison (PD vs HC), not a
longitudinal tracking test -- MDVR-KCL has no repeat sessions per subject,
so it can't test "does this change over time for one person" (that's what
the live app's personal-baseline tier does, and nothing in the public data
can substitute for a person's own history). It can test the more basic
question: in real patients, is there a measurable pause-timing difference
at all.

Usage:
    python analyze_pause_timing_pd_vs_hc.py --dataset-dir /path/to/26-29_09_2017_KCL/ReadText --out out/
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.audio.vad import detect_speech_segments
from app.audio.timing_features import compute_timing_features


def analyze_file(wav_path: Path) -> dict:
    segments = detect_speech_segments(str(wav_path))
    if len(segments) < 2:
        return None
    # passage_syllable_count unknown for this dataset -- use 1 as a
    # placeholder and ignore speaking_rate, which depends on it. Pause
    # fraction and longest gap don't need the passage length at all.
    features = compute_timing_features(segments, passage_syllable_count=1)
    return {
        "pause_fraction": features.pause_fraction,
        "longest_internal_gap": features.longest_internal_gap,
        "n_segments": len(segments),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    results = {"PD": [], "HC": []}
    for label, subdir in [("PD", "PD"), ("HC", "HC")]:
        for wav_path in sorted((args.dataset_dir / subdir).glob("*.wav")):
            result = analyze_file(wav_path)
            if result is not None:
                result["file"] = wav_path.name
                results[label].append(result)
            print(f"{label} {wav_path.name}: {result}")

    summary = {}
    for feature in ["pause_fraction", "longest_internal_gap"]:
        pd_vals = np.array([r[feature] for r in results["PD"]])
        hc_vals = np.array([r[feature] for r in results["HC"]])
        t_stat, p_value = stats.ttest_ind(pd_vals, hc_vals, equal_var=False)
        summary[feature] = {
            "pd_mean": float(pd_vals.mean()),
            "pd_std": float(pd_vals.std()),
            "hc_mean": float(hc_vals.mean()),
            "hc_std": float(hc_vals.std()),
            "welch_t": float(t_stat),
            "p_value": float(p_value),
        }

    output = {
        "n_pd": len(results["PD"]),
        "n_hc": len(results["HC"]),
        "summary": summary,
        "raw": results,
        "note": (
            "Cross-sectional PD vs HC comparison on connected read speech, "
            "using the live app's own VAD + pause-timing feature code. Not "
            "a longitudinal test -- MDVR-KCL has one session per subject."
        ),
    }
    (args.out / "pause_timing_pd_vs_hc.json").write_text(json.dumps(output, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
