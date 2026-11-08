"""Validates the connected-speech embedding classifier result properly.

A naive bootstrap CI on this result is INVALID and was caught, not
reported: resampling 37 subjects with replacement duplicates some
subjects' exact 768-dim embedding into both a bootstrap sample's train
and test folds, letting the model memorize rather than generalize. That
produced a nonsensical, inflated CI of [0.83, 1.0].

The correct check for "is this AUC real, or just what 768 dimensions on
37 samples can achieve by chance" is a label-permutation test: shuffle
the labels (keeping features fixed), rerun the exact same clean
cross-validation many times, and see what AUC chance alone produces in
this same high-dimensional, small-sample regime.

Usage:
    python permutation_test_embeddings.py --embeddings /path/to/connected_speech_embeddings.csv --out out/
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


def clean_cv_auc(X: np.ndarray, y: np.ndarray, seed: int, pipe: Pipeline) -> float:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    proba = np.zeros(len(y))
    for train_idx, test_idx in cv.split(X, y):
        pipe.fit(X[train_idx], y[train_idx])
        proba[test_idx] = pipe.predict_proba(X[test_idx])[:, 1]
    return float(roc_auc_score(y, proba))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.embeddings)
    emb_cols = [c for c in df.columns if c.startswith("emb_")]
    X = df[emb_cols].to_numpy()
    y = df["label"].to_numpy()

    pipe = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, C=0.05))])

    observed_auc = clean_cv_auc(X, y, seed=0, pipe=pipe)

    rng = np.random.RandomState(0)
    null_aucs = []
    for i in range(N_PERMUTATIONS):
        y_shuffled = rng.permutation(y)
        null_aucs.append(clean_cv_auc(X, y_shuffled, seed=i, pipe=pipe))
    null_aucs = np.array(null_aucs)

    results = {
        "n_samples": int(len(y)),
        "n_features": len(emb_cols),
        "observed_auc": observed_auc,
        "null_mean": float(null_aucs.mean()),
        "null_std": float(null_aucs.std()),
        "null_95th_percentile": float(np.percentile(null_aucs, 95)),
        "null_max": float(null_aucs.max()),
        "n_permutations": N_PERMUTATIONS,
        "empirical_p_value": float((null_aucs >= observed_auc).mean()),
        "note": (
            "null_max is the highest AUC chance alone produced across "
            "n_permutations label-shuffles, in this exact high-dimensional "
            "(768 features, 37 samples) regime. observed_auc beating every "
            "permutation is real evidence, not an artifact of dimensionality."
        ),
    }
    (args.out / "permutation_test_embeddings.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
