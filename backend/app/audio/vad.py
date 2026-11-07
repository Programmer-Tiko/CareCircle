"""Silero VAD wrapper. Loads audio via soundfile rather than silero_vad's
own read_audio helper, because the installed torchaudio version requires an
extra torchcodec dependency we don't otherwise need.
"""
from pathlib import Path

import soundfile as sf
import torch
import torchaudio
from silero_vad import get_speech_timestamps, load_silero_vad

TARGET_SR = 16000

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = load_silero_vad()
    return _model


def load_mono_16k(path: str | Path) -> torch.Tensor:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data.T)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != TARGET_SR:
        waveform = torchaudio.functional.resample(waveform, sr, TARGET_SR)
    return waveform.squeeze(0)


def detect_speech_segments(path: str | Path, threshold: float = 0.5) -> list[tuple[float, float]]:
    waveform = load_mono_16k(path)
    timestamps = get_speech_timestamps(
        waveform, _get_model(), threshold=threshold, return_seconds=True
    )
    return [(t["start"], t["end"]) for t in timestamps]
