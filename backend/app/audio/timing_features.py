"""Pause/timing features computed from VAD speech-segment timestamps.

Kept separate from the VAD call itself so the math can be unit-tested with
synthetic segment lists, without needing real audio or a model.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TimingFeatures:
    pause_fraction: float
    longest_internal_gap: float
    speaking_rate: float


def compute_timing_features(
    speech_segments: list[tuple[float, float]], passage_syllable_count: int
) -> TimingFeatures:
    """speech_segments: list of (start_sec, end_sec) for each detected speech
    segment, in chronological order, with edge silence already excluded
    (first segment starts at first speech onset, last ends at final speech
    offset).
    """
    if len(speech_segments) == 0:
        raise ValueError("No speech segments detected; recording is unusable.")

    span_start = speech_segments[0][0]
    span_end = speech_segments[-1][1]
    total_span = span_end - span_start
    if total_span <= 0:
        raise ValueError("Degenerate speech span; recording is unusable.")

    total_speech_duration = sum(end - start for start, end in speech_segments)

    gaps = [
        speech_segments[i + 1][0] - speech_segments[i][1]
        for i in range(len(speech_segments) - 1)
    ]
    internal_gap_total = sum(gaps)
    longest_internal_gap = max(gaps, default=0.0)

    pause_fraction = internal_gap_total / total_span
    speaking_rate = passage_syllable_count / total_speech_duration

    return TimingFeatures(
        pause_fraction=pause_fraction,
        longest_internal_gap=longest_internal_gap,
        speaking_rate=speaking_rate,
    )
