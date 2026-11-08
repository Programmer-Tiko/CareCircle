"""Tests deep pretrained embeddings on our STRONGEST dataset (MDVR-KCL,
connected speech) instead of only the sustained-vowel set tested earlier.
Extracts wav2vec2 embeddings from the VAD-detected speech-only portion of
each recording (silence excluded, same approach as voice_quality_features'
speech-only extraction), then compares three feature sets head-to-head on
the same 37 real patients: hand-engineered features alone (already 0.75
AUC, see analyze_voice_breakdown_pd_vs_hc.py), embeddings alone, and both
combined.

Usage:
    python analyze_embeddings_connected_speech.py --dataset-dir /path/to/ReadText --hand-features /path/to/voice_breakdown_features.csv --out out/
"""
import argparse
import json
import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
import torchaudio
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.audio.vad import detect_speech_segments, load_mono_16k

FILENAME_RE = re.compile(r"(ID\d+)_(hc|pd)_\d+_\d+_\d+")
BUNDLE = torchaudio.pipelines.WAV2VEC2_BASE


def speech_only_embedding(wav_path: Path, model) -> np.ndarray:
    import torch

    segments = detect_speech_segments(str(wav_path))
    waveform = load_mono_16k(wav_path)
    sr = 16000
    chunks = [waveform[int(s * sr):int(e * sr)] for s, e in segments]
    speech_only = torch.cat(chunks).unsqueeze(0)
    with torch.inference_mode():
        features, _ = model.extract_features(speech_only)
        pooled = features[-1].mean(dim=1).squeeze(0)
    return pooled.numpy()


def build_embedding_table(dataset_dir: Path) -> pd.DataFrame:
    model = BUNDLE.get_model()
    model.eval()
    rows = []
    for subdir in ["PD", "HC"]:
        for wav_path in sorted((dataset_dir / subdir).glob("*.wav")):
            match = FILENAME_RE.search(wav_path.name)
            if not match:
                continue
            file_id, health_status = match.groups()
            vector = speech_only_embedding(wav_path, model)
            row = {f"emb_{i}": v for i, v in enumerate(vector)}
            row["file"] = wav_path.name
            row["label"] = 1 if health_status == "pd" else 0
            rows.append(row)
            print(f"  embedded {wav_path.name}")
    return pd.DataFrame(rows)


def evaluate(X: np.ndarray, y: np.ndarray) -> float:
    X = StandardScaler().fit_transform(X)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    model = LogisticRegression(max_iter=2000, C=0.05)
    proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]
    return float(roc_auc_score(y, proba))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--hand-features", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    emb_df = build_embedding_table(args.dataset_dir)
    emb_df.to_csv(args.out / "connected_speech_embeddings.csv", index=False)

    hand_df = pd.read_csv(args.hand_features)
    merged = emb_df.merge(hand_df, on="file", suffixes=("", "_hand"))

    emb_cols = [c for c in emb_df.columns if c.startswith("emb_")]
    hand_cols = [c for c in hand_df.columns if c not in ("file", "label", "hoehn_yahr", "updrs_ii_5", "updrs_iii_18")
                 and merged[c].notna().all()]

    y = merged["label"].to_numpy()
    results = {
        "n_samples": int(len(merged)),
        "hand_engineered_alone_auc": evaluate(merged[hand_cols].to_numpy(), y),
        "embeddings_alone_auc": evaluate(merged[emb_cols].to_numpy(), y),
        "combined_auc": evaluate(merged[emb_cols + hand_cols].to_numpy(), y),
        "hand_features_used": hand_cols,
        "note": (
            "Same 37 real patients, same 5-fold stratified CV throughout -- "
            "only the feature set differs. hand_engineered_alone should "
            "match analyze_voice_breakdown_pd_vs_hc.py's combined_classifier "
            "result (0.75) up to CV-fold randomness."
        ),
    }
    (args.out / "embeddings_vs_handcrafted_connected_speech.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
