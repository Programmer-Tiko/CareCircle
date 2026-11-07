"""Jitter/shimmer/HNR extraction from a short sustained-vowel sample, using
the same feature definitions as the UCI Oxford Parkinson's Telemonitoring
dataset (see models/train_pd_severity.py) so a live sample can be scored by
that model.

RPDE, DFA, and PPE from the original dataset are nonlinear-dynamics measures
not available in Praat/parselmouth and are deliberately left out here -- the
CCR training script trains on this same 13-feature subset, not the full 16,
so live features and the trained model always match.
"""
import parselmouth
from parselmouth.praat import call

JITTER_SHIMMER_ARGS = (0, 0, 0.0001, 0.02, 1.3)
SHIMMER_EXTRA_ARGS = (1.6,)


def extract_voice_quality_features(wav_path: str, f0min: float = 75, f0max: float = 500) -> dict:
    sound = parselmouth.Sound(wav_path)
    point_process = call(sound, "To PointProcess (periodic, cc)", f0min, f0max)

    harmonicity = call(sound, "To Harmonicity (cc)", 0.01, f0min, 0.1, 1.0)
    hnr = call(harmonicity, "Get mean", 0, 0)
    # Praat's direct noise-to-harmonics ratio needs the "Voice report" text
    # parse; this is the standard dB<->ratio approximation used when only
    # mean HNR is available. Treat as approximate, not authoritative.
    nhr = 1.0 / (10 ** (hnr / 10)) if hnr == hnr else float("nan")  # NaN check without numpy

    return {
        "Jitter(%)": call(point_process, "Get jitter (local)", *JITTER_SHIMMER_ARGS) * 100,
        "Jitter(Abs)": call(point_process, "Get jitter (local, absolute)", *JITTER_SHIMMER_ARGS),
        "Jitter:RAP": call(point_process, "Get jitter (rap)", *JITTER_SHIMMER_ARGS),
        "Jitter:PPQ5": call(point_process, "Get jitter (ppq5)", *JITTER_SHIMMER_ARGS),
        "Jitter:DDP": call(point_process, "Get jitter (ddp)", *JITTER_SHIMMER_ARGS),
        "Shimmer": call([sound, point_process], "Get shimmer (local)", *JITTER_SHIMMER_ARGS, *SHIMMER_EXTRA_ARGS),
        "Shimmer(dB)": call([sound, point_process], "Get shimmer (local_dB)", *JITTER_SHIMMER_ARGS, *SHIMMER_EXTRA_ARGS),
        "Shimmer:APQ3": call([sound, point_process], "Get shimmer (apq3)", *JITTER_SHIMMER_ARGS, *SHIMMER_EXTRA_ARGS),
        "Shimmer:APQ5": call([sound, point_process], "Get shimmer (apq5)", *JITTER_SHIMMER_ARGS, *SHIMMER_EXTRA_ARGS),
        "Shimmer:APQ11": call([sound, point_process], "Get shimmer (apq11)", *JITTER_SHIMMER_ARGS, *SHIMMER_EXTRA_ARGS),
        "Shimmer:DDA": call([sound, point_process], "Get shimmer (dda)", *JITTER_SHIMMER_ARGS, *SHIMMER_EXTRA_ARGS),
        "NHR": nhr,
        "HNR": hnr,
    }
