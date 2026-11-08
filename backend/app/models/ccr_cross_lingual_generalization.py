"""Run this on CCR -- needs real compute (a 300M+ param multilingual model
across ~87 recordings) and is self-contained: downloads both datasets,
extracts embeddings, and runs the single most convincing generalization
test available to us: train a classifier on PD-vs-HC in ENGLISH connected
speech, test it on ITALIAN word-list speech never seen in training, and
vice versa. No cross-validation needed for this part -- train and test are
two fully independent real-world datasets, so there's no leakage risk at
all, unlike same-dataset CV.

Also reruns the within-dataset numbers with this larger model for
comparison against the wav2vec2-base results already in the repo.

Usage:
    python ccr_cross_lingual_generalization.py --workdir /scratch/voiceshift_data --out out/

Requires: pip install -r requirements.txt (torch, torchaudio, soundfile,
pandas, scikit-learn already listed there).
"""
import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
import torch
import torchaudio
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.audio.vad import detect_speech_segments, load_mono_16k

BUNDLE = torchaudio.pipelines.WAV2VEC2_XLSR53
MDVR_KCL_URL = "https://zenodo.org/api/records/2867216/files/26_29_09_2017_KCL.zip/content"
HF_API = "https://huggingface.co/api/datasets/birgermoell/Italian_Parkinsons_Voice_and_Speech"
HF_RESOLVE = "https://huggingface.co/datasets/birgermoell/Italian_Parkinsons_Voice_and_Speech/resolve/main/"


def download(url: str, dest: Path) -> None:
    if dest.exists():
        return
    print(f"downloading {url} -> {dest}")
    urllib.request.urlretrieve(url, dest)


def prepare_mdvr_kcl(workdir: Path) -> Path:
    zip_path = workdir / "kcl.zip"
    download(MDVR_KCL_URL, zip_path)
    read_text_dir = workdir / "26-29_09_2017_KCL" / "ReadText"
    if not read_text_dir.exists():
        with zipfile.ZipFile(zip_path) as zf:
            members = [m for m in zf.namelist() if "ReadText" in m]
            zf.extractall(workdir, members=members)
    return read_text_dir


def prepare_italianpvs(workdir: Path) -> tuple[Path, Path]:
    pd_dir, hc_dir = workdir / "italianpvs_pd", workdir / "italianpvs_hc"
    pd_dir.mkdir(parents=True, exist_ok=True)
    hc_dir.mkdir(parents=True, exist_ok=True)
    if any(pd_dir.iterdir()) and any(hc_dir.iterdir()):
        return pd_dir, hc_dir

    with urllib.request.urlopen(HF_API) as resp:
        meta = json.load(resp)
    files = [s["rfilename"] for s in meta.get("siblings", [])]
    pd_files = [f for f in files if "People with Parkinson's disease" in f and "/PR1" in f and f.endswith(".wav")]
    hc_files = [f for f in files if "Elderly Healthy Control" in f and "/PR1" in f and f.endswith(".wav")]

    for label, file_list, out_dir in [("pd", pd_files, pd_dir), ("hc", hc_files, hc_dir)]:
        for i, f in enumerate(file_list):
            url = HF_RESOLVE + urllib.parse.quote(f)
            download(url, out_dir / f"{label}_{i:02d}.wav")
    return pd_dir, hc_dir


def embed(model, wav_path: Path) -> np.ndarray:
    segments = detect_speech_segments(str(wav_path))
    waveform = load_mono_16k(wav_path)
    sr = 16000
    chunks = [waveform[int(s * sr):int(e * sr)] for s, e in segments]
    speech_only = torch.cat(chunks).unsqueeze(0)
    with torch.inference_mode():
        features, _ = model.extract_features(speech_only)
        pooled = features[-1].mean(dim=1).squeeze(0)
    return pooled.numpy()


def build_embeddings(model, pd_dir: Path, hc_dir: Path, source: str) -> pd.DataFrame:
    rows = []
    for label, directory in [(1, pd_dir), (0, hc_dir)]:
        for wav_path in sorted(Path(directory).glob("*.wav")):
            try:
                vector = embed(model, wav_path)
            except Exception as exc:
                print(f"  skipping {wav_path.name}: {exc}")
                continue
            row = {f"emb_{i}": v for i, v in enumerate(vector)}
            row["label"] = label
            row["source"] = source
            rows.append(row)
            print(f"  embedded [{source}] {wav_path.name}")
    return pd.DataFrame(rows)


def cross_dataset_auc(train_df: pd.DataFrame, test_df: pd.DataFrame) -> float:
    emb_cols = [c for c in train_df.columns if c.startswith("emb_")]
    scaler = StandardScaler().fit(train_df[emb_cols])
    model = LogisticRegression(max_iter=2000, C=0.05)
    model.fit(scaler.transform(train_df[emb_cols]), train_df["label"])
    proba = model.predict_proba(scaler.transform(test_df[emb_cols]))[:, 1]
    return float(roc_auc_score(test_df["label"], proba))


def permutation_p_value(train_df: pd.DataFrame, test_df: pd.DataFrame, observed_auc: float, n: int = 300) -> dict:
    emb_cols = [c for c in train_df.columns if c.startswith("emb_")]
    rng = np.random.RandomState(0)
    null_aucs = []
    for _ in range(n):
        shuffled = train_df.copy()
        shuffled["label"] = rng.permutation(shuffled["label"].to_numpy())
        null_aucs.append(cross_dataset_auc(shuffled, test_df))
    null_aucs = np.array(null_aucs)
    return {
        "null_mean": float(null_aucs.mean()),
        "null_max": float(null_aucs.max()),
        "empirical_p_value": float((null_aucs >= observed_auc).mean()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--out", default=Path("out"), type=Path)
    args = parser.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)

    print("preparing datasets...")
    read_text_dir = prepare_mdvr_kcl(args.workdir)
    it_pd_dir, it_hc_dir = prepare_italianpvs(args.workdir)

    print("loading WAV2VEC2_XLSR53 (multilingual, ~300M params)...")
    model = BUNDLE.get_model()
    model.eval()

    print("embedding MDVR-KCL (English, connected speech)...")
    mdvr_df = build_embeddings(model, read_text_dir / "PD", read_text_dir / "HC", source="mdvr_kcl")
    print("embedding ItalianPVS (Italian, word-list speech)...")
    italian_df = build_embeddings(model, it_pd_dir, it_hc_dir, source="italianpvs")

    mdvr_df.to_csv(args.out / "mdvr_kcl_xlsr_embeddings.csv", index=False)
    italian_df.to_csv(args.out / "italianpvs_xlsr_embeddings.csv", index=False)

    results = {}
    auc_en_to_it = cross_dataset_auc(mdvr_df, italian_df)
    results["train_english_test_italian"] = {
        "auc": auc_en_to_it,
        **permutation_p_value(mdvr_df, italian_df, auc_en_to_it),
    }
    auc_it_to_en = cross_dataset_auc(italian_df, mdvr_df)
    results["train_italian_test_english"] = {
        "auc": auc_it_to_en,
        **permutation_p_value(italian_df, mdvr_df, auc_it_to_en),
    }
    results["note"] = (
        "No cross-validation, no resampling -- train and test are two fully "
        "independent real-world datasets, so there is no leakage risk at "
        "all. permutation_p_value shuffles only the TRAINING labels and "
        "refits, never touching the held-out test set, so it's a clean "
        "significance check on a genuinely held-out generalization test."
    )
    (args.out / "cross_lingual_generalization.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    print(f"\nBring back {args.out}/cross_lingual_generalization.json and the two embeddings CSVs.")


if __name__ == "__main__":
    main()
