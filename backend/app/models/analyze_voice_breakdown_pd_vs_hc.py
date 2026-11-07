"""Breaks the signal down further than pause_fraction/longest_gap, and
checks for a severity gradient, not just a binary PD/HC split. Same real
dataset as analyze_pause_timing_pd_vs_hc.py (MDVR-KCL), same VAD code.

Richer timing features: number of pauses, pause duration stats, speech
segment duration stats, pause rate per minute -- not just two numbers.

Voice quality on CONNECTED speech (not sustained vowel, unlike every
earlier jitter/shimmer test): VAD-detected speech segments are extracted
and concatenated into a speech-only buffer, then run through the same
Praat-based extractor used elsewhere, so silence doesn't dilute the
measurement.

Severity gradient: MDVR-KCL filenames encode real clinical scores --
ID<N>_<hc|pd>_<HoehnYahr>_<UPDRS-II-5>_<UPDRS-III-18>. Within the PD group,
correlates every feature against these, since a dose-response relationship
(more severe = more pause) is stronger evidence than a bare PD-vs-HC split.

Usage:
    python analyze_voice_breakdown_pd_vs_hc.py --dataset-dir /path/to/ReadText --out out/
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.audio.vad import detect_speech_segments, load_mono_16k
from app.audio.voice_quality_features import extract_voice_quality_features

FILENAME_RE = re.compile(r"ID\d+_(hc|pd)_(\d+)_(\d+)_(\d+)")

TIMING_FEATURES = [
    "pause_fraction", "longest_internal_gap", "num_pauses",
    "mean_pause_duration", "std_pause_duration",
    "mean_speech_segment_duration", "std_speech_segment_duration",
    "pause_rate_per_min",
]
VOICE_FEATURES = [
    "Jitter(%)", "Jitter(Abs)", "Jitter:RAP", "Jitter:PPQ5", "Jitter:DDP",
    "Shimmer", "Shimmer(dB)", "Shimmer:APQ3", "Shimmer:APQ5", "Shimmer:APQ11",
    "Shimmer:DDA", "NHR", "HNR",
]


def richer_timing_features(segments: list[tuple[float, float]]) -> dict:
    span_start, span_end = segments[0][0], segments[-1][1]
    total_span = span_end - span_start
    gaps = [segments[i + 1][0] - segments[i][1] for i in range(len(segments) - 1)]
    gaps = np.array(gaps) if gaps else np.array([0.0])
    durations = np.array([end - start for start, end in segments])

    return {
        "pause_fraction": float(gaps.sum() / total_span),
        "longest_internal_gap": float(gaps.max()),
        "num_pauses": int(len(gaps)),
        "mean_pause_duration": float(gaps.mean()),
        "std_pause_duration": float(gaps.std()),
        "mean_speech_segment_duration": float(durations.mean()),
        "std_speech_segment_duration": float(durations.std()),
        "pause_rate_per_min": float(len(gaps) / (total_span / 60)),
    }


def speech_only_voice_quality(path: Path, segments: list[tuple[float, float]]) -> dict | None:
    waveform = load_mono_16k(path)
    sr = 16000
    chunks = [waveform[int(s * sr):int(e * sr)] for s, e in segments]
    speech_only = np.concatenate([c.numpy() for c in chunks])
    if len(speech_only) < sr:  # need at least ~1s of speech to extract reliably
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, speech_only, sr)
        try:
            return extract_voice_quality_features(tmp.name)
        except Exception as exc:
            print(f"  voice-quality extraction failed for {path.name}: {exc}")
            return None


def build_table(dataset_dir: Path) -> pd.DataFrame:
    rows = []
    for subdir in ["PD", "HC"]:
        for wav_path in sorted((dataset_dir / subdir).glob("*.wav")):
            match = FILENAME_RE.search(wav_path.name)
            if not match:
                print(f"  skipping {wav_path.name}: filename doesn't match expected pattern")
                continue
            health_status, hoehn_yahr, updrs_ii_5, updrs_iii_18 = match.groups()

            segments = detect_speech_segments(str(wav_path))
            if len(segments) < 2:
                continue

            row = richer_timing_features(segments)
            vq = speech_only_voice_quality(wav_path, segments)
            if vq:
                row.update(vq)
            row["label"] = 1 if health_status == "pd" else 0
            row["hoehn_yahr"] = int(hoehn_yahr)
            row["updrs_ii_5"] = int(updrs_ii_5)
            row["updrs_iii_18"] = int(updrs_iii_18)
            row["file"] = wav_path.name
            rows.append(row)
            print(f"  {wav_path.name}: pause_fraction={row['pause_fraction']:.3f} "
                  f"num_pauses={row['num_pauses']} HNR={row.get('HNR', 'NA')}")
    return pd.DataFrame(rows)


def pd_vs_hc_tests(df: pd.DataFrame) -> dict:
    results = {}
    for feature in TIMING_FEATURES + VOICE_FEATURES:
        if feature not in df.columns or df[feature].isna().any():
            continue
        pd_vals = df.loc[df["label"] == 1, feature]
        hc_vals = df.loc[df["label"] == 0, feature]
        t_stat, p_value = stats.ttest_ind(pd_vals, hc_vals, equal_var=False)
        pooled_std = np.sqrt((pd_vals.var() + hc_vals.var()) / 2)
        cohens_d = (pd_vals.mean() - hc_vals.mean()) / pooled_std if pooled_std > 0 else 0.0
        results[feature] = {
            "pd_mean": float(pd_vals.mean()),
            "hc_mean": float(hc_vals.mean()),
            "p_value": float(p_value),
            "cohens_d": float(cohens_d),
        }
    return dict(sorted(results.items(), key=lambda kv: kv[1]["p_value"]))


def severity_gradient_within_pd(df: pd.DataFrame) -> dict:
    pd_df = df[df["label"] == 1]
    results = {}
    for feature in TIMING_FEATURES + VOICE_FEATURES:
        if feature not in pd_df.columns or pd_df[feature].isna().any():
            continue
        for severity_col in ["hoehn_yahr", "updrs_ii_5", "updrs_iii_18"]:
            r, p = stats.spearmanr(pd_df[feature], pd_df[severity_col])
            results[f"{feature}__vs__{severity_col}"] = {"spearman_r": float(r), "p_value": float(p)}
    return dict(sorted(results.items(), key=lambda kv: kv[1]["p_value"]))


def combined_classifier_auc(df: pd.DataFrame) -> dict:
    usable_features = [f for f in TIMING_FEATURES + VOICE_FEATURES
                        if f in df.columns and not df[f].isna().any()]
    X = StandardScaler().fit_transform(df[usable_features].to_numpy())
    y = df["label"].to_numpy()
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    model = LogisticRegression(max_iter=2000, C=0.1)
    proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]
    return {
        "features_used": usable_features,
        "n_samples": int(len(y)),
        "cv_roc_auc": float(roc_auc_score(y, proba)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = build_table(args.dataset_dir)
    df.to_csv(args.out / "voice_breakdown_features.csv", index=False)

    output = {
        "n_pd": int((df["label"] == 1).sum()),
        "n_hc": int((df["label"] == 0).sum()),
        "pd_vs_hc_by_feature": pd_vs_hc_tests(df),
        "severity_gradient_within_pd": severity_gradient_within_pd(df),
        "combined_classifier": combined_classifier_auc(df),
        "note": (
            "pd_vs_hc_by_feature: every feature tested individually, sorted "
            "by p-value, on real patients reading connected speech. "
            "severity_gradient_within_pd: Spearman correlation against real "
            "Hoehn-Yahr/UPDRS scores encoded in the dataset's filenames -- a "
            "dose-response check, not just binary PD/HC. combined_classifier: "
            "all usable features together, not just pause_fraction alone."
        ),
    }
    (args.out / "voice_breakdown_analysis.json").write_text(json.dumps(output, indent=2))
    print("\n" + json.dumps(output["pd_vs_hc_by_feature"], indent=2))
    print("\nSeverity gradient (top 10 by p-value):")
    for k, v in list(output["severity_gradient_within_pd"].items())[:10]:
        print(f"  {k}: r={v['spearman_r']:.3f}, p={v['p_value']:.3f}")
    print("\nCombined classifier:", json.dumps(output["combined_classifier"], indent=2))


if __name__ == "__main__":
    main()
