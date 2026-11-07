import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.audio.timing_features import compute_timing_features


def test_pause_fraction_and_longest_gap():
    # Two 1s speech segments separated by a 0.5s gap -> span 2.5s, 0.5s pause.
    segments = [(0.0, 1.0), (1.5, 2.5)]
    features = compute_timing_features(segments, passage_syllable_count=10)

    assert math.isclose(features.pause_fraction, 0.5 / 2.5)
    assert math.isclose(features.longest_internal_gap, 0.5)
    assert math.isclose(features.speaking_rate, 10 / 2.0)


def test_no_internal_gap_is_zero_pause_fraction():
    segments = [(0.0, 2.0)]
    features = compute_timing_features(segments, passage_syllable_count=10)
    assert features.pause_fraction == 0.0
    assert features.longest_internal_gap == 0.0


def test_empty_segments_rejected():
    with pytest.raises(ValueError):
        compute_timing_features([], passage_syllable_count=10)


def test_longest_gap_picks_the_largest_of_several():
    segments = [(0.0, 1.0), (1.2, 2.0), (2.5, 3.0)]
    features = compute_timing_features(segments, passage_syllable_count=10)
    # gaps are 0.2 and 0.5
    assert math.isclose(features.longest_internal_gap, 0.5)
