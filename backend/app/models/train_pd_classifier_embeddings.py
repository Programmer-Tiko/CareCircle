"""Same task and same real diagnosed-patient dataset as
train_pd_classifier.py, but with a richer feature representation: instead
of 13 hand-engineered jitter/shimmer/HNR numbers, use a pretrained
self-supervised speech model (wav2vec2, trained on ~960 hours of real
speech) to turn each recording into a 768-dim embedding, mean-pooled over
time. Direct comparison: does a deep pretrained representation beat the
classic clinical acoustic features on this real 81-patient dataset?

Usage:
    python train_pd_classifier_embeddings.py --dataset-dir /path/to/pd_dataset --out out/
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import soundfile as sf
import torch
import torchaudio
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

BUNDLE = torchaudio.pipelines.WAV2VEC2_BASE
TARGET_SR = BUNDLE.sample_rate  # 16000


def load_and_resample(wav_path: Path) -> torch.Tensor:
    data, sr = sf.read(str(wav_path), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data.T)  # (channels, time)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != TARGET_SR:
        waveform = torchaudio.functional.resample(waveform, sr, TARGET_SR)
    return waveform


def embed(model, waveform: torch.Tensor) -> np.ndarray:
    with torch.inference_mode():
        features, _ = model.extract_features(waveform)
        last_layer = features[-1]  # (1, time, 768)
        pooled = last_layer.mean(dim=1).squeeze(0)  # mean-pool over time
    return pooled.numpy()


def build_embedding_table(dataset_dir: Path) -> pd.DataFrame:
    demographics = pd.read_excel(dataset_dir / "Demographics.xlsx")
    model = BUNDLE.get_model()
    model.eval()

    rows = []
    for _, record in demographics.iterrows():
        sample_id = record["Sample ID"]
        subdir = "PD_AH" if record["Label"] == "PwPD" else "HC_AH"
        wav_path = dataset_dir / subdir / f"{sample_id}.wav"
        if not wav_path.exists():
            raise FileNotFoundError(f"Expected recording not found: {wav_path}")
        waveform = load_and_resample(wav_path)
        vector = embed(model, waveform)
        row = {f"emb_{i}": v for i, v in enumerate(vector)}
        row["sample_id"] = sample_id
        row["label"] = 1 if record["Label"] == "PwPD" else 0
        rows.append(row)
    return pd.DataFrame(rows)


def train_and_evaluate(df: pd.DataFrame):
    embedding_cols = [c for c in df.columns if c.startswith("emb_")]
    X = df[embedding_cols].to_numpy()
    y = df["label"].to_numpy()

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    # L2-regularized logistic regression -- 768 dims on 81 samples needs
    # strong regularization or it will just memorize the training folds.
    # Scaler lives inside the pipeline so each fold's held-out rows never
    # influence the normalization used to score them.
    model = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, C=0.05))])
    cv_pred = cross_val_predict(model, X, y, cv=cv)
    cv_proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]

    metrics = {
        "n_pd": int((y == 1).sum()),
        "n_hc": int((y == 0).sum()),
        "embedding_dim": len(embedding_cols),
        "cv_accuracy": float(accuracy_score(y, cv_pred)),
        "cv_roc_auc": float(roc_auc_score(y, cv_proba)),
        "confusion_matrix": confusion_matrix(y, cv_pred).tolist(),
        "comparison_baseline": {
            "method": "hand-engineered jitter/shimmer/HNR (train_pd_classifier.py)",
            "cv_accuracy": 0.6172839506172839,
            "cv_roc_auc": 0.6304878048780488,
        },
        "note": (
            "Same 5-fold stratified CV, same subjects, same labels as the "
            "hand-engineered-feature baseline -- only the feature "
            "representation differs. 81 samples is small for a 768-dim "
            "embedding, so this is a real but noisy comparison, not a "
            "final verdict."
        ),
    }

    final_model = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, C=0.05))]).fit(X, y)
    return final_model, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = build_embedding_table(args.dataset_dir)

    model, metrics = train_and_evaluate(df)
    (args.out / "embedding_classifier_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))

    joblib.dump(model, args.out / "pd_embedding_classifier.joblib")

    labels = ["hand-engineered\n(jitter/shimmer/HNR)", "wav2vec2 embeddings"]
    aucs = [metrics["comparison_baseline"]["cv_roc_auc"], metrics["cv_roc_auc"]]
    plt.figure(figsize=(5, 5))
    plt.bar(labels, aucs)
    plt.ylim(0, 1)
    plt.axhline(0.5, color="gray", linestyle="--", label="chance")
    plt.ylabel("Cross-validated ROC-AUC")
    plt.title("PD vs. healthy control: feature representation comparison")
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.out / "representation_comparison.png", dpi=150)

    print(f"\nWrote embedding_classifier_metrics.json, pd_embedding_classifier.joblib, "
          f"representation_comparison.png to {args.out}/")


if __name__ == "__main__":
    main()
