"""Trains a PD vs. healthy-control classifier on REAL raw audio from real
diagnosed patients -- not pre-extracted features from a CSV, and not
teammate recordings. Source: "Voice Samples for Patients with Parkinson's
Disease and Healthy Controls" (figshare, DOI 10.6084/m9.figshare.23849127),
81 real participants, sustained vowel /a/ recorded on their own phones.

Runs the SAME feature-extraction code the live app uses
(audio/voice_quality_features.py) against every recording, so this is a
genuine validation of our own pipeline against real patients, not a
borrowed, unrelated dataset.

Usage:
    python train_pd_classifier.py --dataset-dir /path/to/pd_dataset --out out/
    (dataset-dir must contain Demographics.xlsx, PD_AH/, HC_AH/)
"""
import argparse
import json
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.audio.voice_quality_features import extract_voice_quality_features

FEATURES = [
    "Jitter(%)", "Jitter(Abs)", "Jitter:RAP", "Jitter:PPQ5", "Jitter:DDP",
    "Shimmer", "Shimmer(dB)", "Shimmer:APQ3", "Shimmer:APQ5", "Shimmer:APQ11",
    "Shimmer:DDA", "NHR", "HNR",
]


def build_feature_table(dataset_dir: Path) -> pd.DataFrame:
    demographics = pd.read_excel(dataset_dir / "Demographics.xlsx")
    rows = []
    for _, record in demographics.iterrows():
        sample_id = record["Sample ID"]
        subdir = "PD_AH" if record["Label"] == "PwPD" else "HC_AH"
        wav_path = dataset_dir / subdir / f"{sample_id}.wav"
        if not wav_path.exists():
            raise FileNotFoundError(f"Expected recording not found: {wav_path}")
        features = extract_voice_quality_features(str(wav_path))
        features["sample_id"] = sample_id
        features["label"] = 1 if record["Label"] == "PwPD" else 0
        rows.append(features)
    return pd.DataFrame(rows)


def train_and_evaluate(df: pd.DataFrame):
    X = StandardScaler().fit_transform(df[FEATURES].to_numpy())
    y = df["label"].to_numpy()

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    model = LogisticRegression(max_iter=1000)
    cv_pred = cross_val_predict(model, X, y, cv=cv)
    cv_proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]

    metrics = {
        "n_pd": int((y == 1).sum()),
        "n_hc": int((y == 0).sum()),
        "cv_accuracy": float(accuracy_score(y, cv_pred)),
        "cv_roc_auc": float(roc_auc_score(y, cv_proba)),
        "confusion_matrix": confusion_matrix(y, cv_pred).tolist(),
        "note": (
            "5-fold stratified cross-validation, one recording per subject "
            "so there is no subject leakage between folds."
        ),
    }

    final_model = LogisticRegression(max_iter=1000).fit(X, y)
    return final_model, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = build_feature_table(args.dataset_dir)
    df.to_csv(args.out / "extracted_features.csv", index=False)

    model, metrics = train_and_evaluate(df)
    (args.out / "classifier_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

    joblib.dump({"model": model, "features": FEATURES}, args.out / "pd_classifier.joblib")

    coefs = model.coef_[0]
    order = np.argsort(coefs)
    plt.figure(figsize=(7, 5))
    plt.barh(np.array(FEATURES)[order], coefs[order])
    plt.xlabel("Logistic regression coefficient (standardized)")
    plt.title("Which voice features separate PD from healthy controls")
    plt.tight_layout()
    plt.savefig(args.out / "classifier_feature_weights.png", dpi=150)

    print(f"\nWrote extracted_features.csv, classifier_metrics.json, pd_classifier.joblib, "
          f"classifier_feature_weights.png to {args.out}/")


if __name__ == "__main__":
    main()
