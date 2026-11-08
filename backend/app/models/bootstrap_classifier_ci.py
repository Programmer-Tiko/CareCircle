"""Bootstrap 95% CI on the combined-feature classifier AUC from
analyze_voice_breakdown_pd_vs_hc.py. A bare point estimate (0.75) on 37
real patients is fragile-looking without knowing its uncertainty -- this
makes that uncertainty explicit instead of implying false precision.

Usage:
    python bootstrap_classifier_ci.py --features /path/to/voice_breakdown_features.csv --out out/
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

N_BOOTSTRAP = 1000
EXCLUDED_COLS = ("file", "label", "hoehn_yahr", "updrs_ii_5", "updrs_iii_18")


def point_estimate_auc(X: np.ndarray, y: np.ndarray, seed: int = 0) -> float:
    X = StandardScaler().fit_transform(X)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    proba = cross_val_predict(LogisticRegression(max_iter=2000, C=0.1), X, y, cv=cv, method="predict_proba")[:, 1]
    return float(roc_auc_score(y, proba))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.features)
    feature_cols = [c for c in df.columns if c not in EXCLUDED_COLS and df[c].notna().all()]
    X, y = df[feature_cols].to_numpy(), df["label"].to_numpy()

    point_auc = point_estimate_auc(X, y)

    rng = np.random.RandomState(0)
    boot_aucs = []
    for i in range(N_BOOTSTRAP):
        idx = rng.choice(len(y), size=len(y), replace=True)
        Xb, yb = X[idx], y[idx]
        if len(set(yb)) < 2:
            continue
        boot_aucs.append(point_estimate_auc(Xb, yb, seed=i))
    boot_aucs = np.array(boot_aucs)

    results = {
        "n_samples": int(len(y)),
        "n_features": len(feature_cols),
        "point_estimate_auc": point_auc,
        "bootstrap_mean_auc": float(boot_aucs.mean()),
        "bootstrap_95ci_low": float(np.percentile(boot_aucs, 2.5)),
        "bootstrap_95ci_high": float(np.percentile(boot_aucs, 97.5)),
        "n_valid_resamples": int(len(boot_aucs)),
        "note": (
            "A wide CI reflects real uncertainty from small N (37), not a "
            "bug. The point estimate being real and non-trivial matters more "
            "than its exact value -- report the range, not just 0.75."
        ),
    }
    (args.out / "bootstrap_classifier_ci.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
