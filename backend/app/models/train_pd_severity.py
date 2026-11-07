"""Run this on CCR. Trains a severity-correlation model on the public UCI
Oxford Parkinson's Telemonitoring dataset (42 real diagnosed patients, 5875
voice recordings, longitudinal UPDRS labels) -- not on teammate audio.

Dataset: https://archive.ics.uci.edu/dataset/189/parkinsons+telemonitoring
Download parkinsons_updrs.data.csv and pass its path with --data.

Usage:
    python train_pd_severity.py --data /path/to/parkinsons_updrs.data.csv --out out/

Outputs to --out:
    model.joblib            trained regressor
    metrics.json            cross-validated R^2 / MAE per fold and averaged
    feature_importances.png bar chart of which voice features drive the score
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
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold

# Matches audio/voice_quality_features.py exactly. The source dataset also
# has RPDE, DFA, PPE (nonlinear-dynamics measures), but those aren't
# available via Praat/parselmouth, so they're left out here too -- the live
# extractor and this trained model must always use the same feature set.
VOICE_FEATURES = [
    "Jitter(%)",
    "Jitter(Abs)",
    "Jitter:RAP",
    "Jitter:PPQ5",
    "Jitter:DDP",
    "Shimmer",
    "Shimmer(dB)",
    "Shimmer:APQ3",
    "Shimmer:APQ5",
    "Shimmer:APQ11",
    "Shimmer:DDA",
    "NHR",
    "HNR",
]
TARGET = "motor_UPDRS"
GROUP_COL = "subject#"


def load_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in VOICE_FEATURES + [TARGET, GROUP_COL] if c not in df.columns]
    if missing:
        raise ValueError(
            f"Dataset is missing expected columns {missing}. "
            "Confirm this is the UCI parkinsons_updrs.data.csv file."
        )
    return df


def cross_validate_by_subject(df: pd.DataFrame, n_splits: int = 5):
    X = df[VOICE_FEATURES].to_numpy()
    y = df[TARGET].to_numpy()
    groups = df[GROUP_COL].to_numpy()

    gkf = GroupKFold(n_splits=n_splits)
    fold_metrics = []
    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups)):
        model = GradientBoostingRegressor(random_state=0)
        model.fit(X[train_idx], y[train_idx])
        preds = model.predict(X[test_idx])
        fold_metrics.append(
            {
                "fold": fold,
                "r2": r2_score(y[test_idx], preds),
                "mae": mean_absolute_error(y[test_idx], preds),
                "n_test": int(len(test_idx)),
            }
        )
    return fold_metrics


def train_final_model(df: pd.DataFrame) -> GradientBoostingRegressor:
    X = df[VOICE_FEATURES].to_numpy()
    y = df[TARGET].to_numpy()
    model = GradientBoostingRegressor(random_state=0)
    model.fit(X, y)
    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = load_dataset(args.data)

    fold_metrics = cross_validate_by_subject(df)
    avg_r2 = float(np.mean([m["r2"] for m in fold_metrics]))
    avg_mae = float(np.mean([m["mae"] for m in fold_metrics]))
    metrics = {
        "folds": fold_metrics,
        "avg_r2": avg_r2,
        "avg_mae": avg_mae,
        "n_subjects": int(df[GROUP_COL].nunique()),
        "n_recordings": int(len(df)),
        "note": (
            "Cross-validated by subject (GroupKFold), so no patient's "
            "recordings appear in both train and test for the same fold."
        ),
    }
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

    final_model = train_final_model(df)
    joblib.dump({"model": final_model, "features": VOICE_FEATURES}, args.out / "model.joblib")

    importances = final_model.feature_importances_
    order = np.argsort(importances)
    plt.figure(figsize=(7, 5))
    plt.barh(np.array(VOICE_FEATURES)[order], importances[order])
    plt.xlabel("Feature importance")
    plt.title("Which voice features predict motor UPDRS severity")
    plt.tight_layout()
    plt.savefig(args.out / "feature_importances.png", dpi=150)

    print(f"\nWrote model.joblib, metrics.json, feature_importances.png to {args.out}/")
    print("Bring all three back -- metrics.json + the png are what go in the pitch deck.")


if __name__ == "__main__":
    main()
