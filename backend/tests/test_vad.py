import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audio.vad import detect_speech_segments


def test_detects_segments_in_synthetic_speech_like_signal(tmp_path):
    import numpy as np
    import soundfile as sf

    sr = 16000
    silence = np.zeros(int(0.5 * sr), dtype=np.float32)
    t = np.linspace(0, 1.0, sr, endpoint=False)
    tone = (0.3 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    signal = np.concatenate([silence, tone, silence, tone, silence])

    path = tmp_path / "synthetic.wav"
    sf.write(path, signal, sr)

    segments = detect_speech_segments(str(path))
    assert isinstance(segments, list)
    for start, end in segments:
        assert end > start
