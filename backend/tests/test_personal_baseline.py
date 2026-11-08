import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.personal_baseline import (
    FEATURE_ORDER,
    PersistentDeviationTracker,
    deviation_score,
    fit_baseline,
    per_feature_deviation,
)

CLEAN_TAKES = [
    {"pause_fraction": 0.18, "longest_internal_gap": 0.30, "speaking_rate": 3.2, "mean_speech_segment_duration": 1.9},
    {"pause_fraction": 0.20, "longest_internal_gap": 0.32, "speaking_rate": 3.1, "mean_speech_segment_duration": 1.8},
    {"pause_fraction": 0.19, "longest_internal_gap": 0.29, "speaking_rate": 3.3, "mean_speech_segment_duration": 2.0},
    {"pause_fraction": 0.21, "longest_internal_gap": 0.31, "speaking_rate": 3.0, "mean_speech_segment_duration": 1.85},
]


def test_fit_baseline_requires_minimum_takes():
    with pytest.raises(ValueError):
        fit_baseline(CLEAN_TAKES[:2])


def test_typical_take_scores_low():
    stats = fit_baseline(CLEAN_TAKES)
    typical = {"pause_fraction": 0.20, "longest_internal_gap": 0.30, "speaking_rate": 3.15,
               "mean_speech_segment_duration": 1.9}
    assert deviation_score(stats, typical) < 1.0


def test_acted_deviation_scores_high():
    stats = fit_baseline(CLEAN_TAKES)
    # Shorter speech bursts (segment duration dropping), not just longer
    # pauses -- the single strongest real-world correlate found in this
    # project's own research (r=-0.80 vs Hoehn-Yahr stage).
    acted = {"pause_fraction": 0.45, "longest_internal_gap": 0.90, "speaking_rate": 1.8,
             "mean_speech_segment_duration": 0.9}
    assert deviation_score(stats, acted) > 3.0


def test_per_feature_deviation_identifies_which_feature_moved():
    stats = fit_baseline(CLEAN_TAKES)
    # speaking_rate way off, the others untouched -- a real note should be
    # able to say "speaking rate", not default to "longer pauses".
    rate_only = {"pause_fraction": 0.20, "longest_internal_gap": 0.30, "speaking_rate": 1.0,
                 "mean_speech_segment_duration": 1.9}
    z = per_feature_deviation(stats, rate_only)
    assert set(z.keys()) == set(FEATURE_ORDER)
    assert abs(z["speaking_rate"]) > abs(z["pause_fraction"])
    assert abs(z["speaking_rate"]) > abs(z["longest_internal_gap"])
    assert abs(z["speaking_rate"]) > abs(z["mean_speech_segment_duration"])


def test_per_feature_deviation_combines_into_deviation_score():
    import math

    stats = fit_baseline(CLEAN_TAKES)
    take = {"pause_fraction": 0.45, "longest_internal_gap": 0.90, "speaking_rate": 1.8,
            "mean_speech_segment_duration": 0.9}
    z = per_feature_deviation(stats, take)
    expected = math.sqrt(sum(v * v for v in z.values()))
    assert deviation_score(stats, take) == pytest.approx(expected)


def test_persistent_tracker_needs_consecutive_hits():
    tracker = PersistentDeviationTracker(threshold=2.0, required_consecutive=2)
    assert tracker.observe(3.0) is False  # first hit, not persistent yet
    assert tracker.observe(0.5) is False  # reset by a normal take
    assert tracker.observe(3.0) is False  # first hit again
    assert tracker.observe(3.0) is True  # second consecutive hit -> persistent
