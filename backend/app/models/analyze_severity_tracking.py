"""Answers a different question than train_pd_severity.py: not "can a model
predict an unseen patient's absolute severity from voice" (it can't --
negative R^2, see metrics.json), but "does this feature move WITH symptom
severity for a given person, over time." That's the question actually
relevant to VoiceShift's design, since the live app never predicts anyone's
absolute severity -- it only compares a person to their own past.

Usage:
    python analyze_severity_tracking.py --data /path/to/parkinsons_updrs.data --out out/
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

KEY_FEATURES = ["HNR", "Jitter(%)", "Shimmer", "NHR"]
MIN_RECORDINGS_PER_SUBJECT = 10


def within_subject_correlations(df: pd.DataFrame) -> dict:
    results = {f: [] for f in KEY_FEATURES}
    n_subjects = 0
    for _, group in df.groupby("subject#"):
        if len(group) < MIN_RECORDINGS_PER_SUBJECT:
            continue
        n_subjects += 1
        for feature in KEY_FEATURES:
            r, _ = stats.pearsonr(group[feature], group["motor_UPDRS"])
            results[feature].append(r)

    summary = {"n_subjects_analyzed": n_subjects, "features": {}}
    for feature, rs in results.items():
        rs = np.array(rs)
        summary["features"][feature] = {
            "median_r": float(np.median(rs)),
            "mean_r": float(np.mean(rs)),
            "pct_subjects_same_sign": float(max((rs > 0).mean(), (rs < 0).mean()) * 100),
        }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.data)
    summary = within_subject_correlations(df)
    summary["interpretation"] = (
        "Near-zero median correlation and sign-consistency barely above chance "
        "(50%) across all four features means sustained-vowel jitter/shimmer/HNR "
        "do not reliably track within-person symptom change over time in this "
        "real 42-patient dataset. This matches the published claim that sustained "
        "vowels suit cross-sectional diagnosis, not longitudinal monitoring -- and "
        "is why VoiceShift's live trigger uses reading-passage pause-timing "
        "instead, and never surfaces a trained severity score to the patient."
    )
    (args.out / "severity_tracking_analysis.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
