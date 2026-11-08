"""Validates the combined-feature classifier AUC (0.75, from
analyze_voice_breakdown_pd_vs_hc.py) on 37 real patients.

An earlier version of this script used a bootstrap CI that was invalid
for the same reason caught in permutation_test_embeddings.py: resampling
37 subjects with replacement duplicates some subjects into both a
resampled fold's train and test portions, inflating the result. It also
scaled features on the whole dataset before cross-validation, leaking
each fold's held-out rows into their own normalization. Both are fixed
here: scaling happens inside a per-fold Pipeline, and significance comes
from a label-permutation test (same method as permutation_test_embeddings.py)
instead of a bootstrap CI.

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
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

N_PERMUTATIONS = 300
EXCLUDED_COLS = ("file", "label", "hoehn_yahr", "updrs_ii_5", "updrs_iii_18")


def clean_cv_auc(X: np.ndarray, y: np.ndarray, seed: int, pipe: Pipeline) -> float:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    proba = np.zeros(len(y))
    for train_idx, test_idx in cv.split(X, y):
        pipe.fit(X[train_idx], y[train_idx])
        proba[test_idx] = pipe.predict_proba(X[test_idx])[:, 1]
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

    pipe = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, C=0.1))])
    observed_auc = clean_cv_auc(X, y, seed=0, pipe=pipe)

    rng = np.random.RandomState(0)
    null_aucs = [clean_cv_auc(X, rng.permutation(y), seed=i, pipe=pipe) for i in range(N_PERMUTATIONS)]
    null_aucs = np.array(null_aucs)

    results = {
        "n_samples": int(len(y)),
        "n_features": len(feature_cols),
        "observed_auc": observed_auc,
        "null_mean": float(null_aucs.mean()),
        "null_95th_percentile": float(np.percentile(null_aucs, 95)),
        "null_max": float(null_aucs.max()),
        "n_permutations": N_PERMUTATIONS,
        "empirical_p_value": float((null_aucs >= observed_auc).mean()),
        "note": (
            "Replaces an earlier, invalid bootstrap CI (resampling 37 "
            "subjects with replacement before CV duplicates subjects across "
            "folds). This is a label-permutation test instead: shuffle "
            "labels, rerun the identical per-fold-scaled cross-validation, "
            "see what chance alone produces at this sample size/feature count."
        ),
    }
    (args.out / "permutation_test_combined_classifier.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
