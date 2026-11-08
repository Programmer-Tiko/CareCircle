"""Per-profile multivariate deviation check, replacing a single-feature
threshold with a joint robust z-score across pause fraction, longest
internal gap, speaking rate, and mean speech-segment duration. Fit on that person's own clean reference
takes only -- never on population data, and never on acted/flagged takes.

This is the tier that decides whether to trigger a follow-up question.
It does not use the CCR-trained severity model; that model is a separate,
clearly-labeled research signal (see models/pd_severity_infer.py).
"""
import math
from dataclasses import dataclass

FEATURE_ORDER = ("pause_fraction", "longest_internal_gap", "speaking_rate", "mean_speech_segment_duration")


@dataclass(frozen=True)
class BaselineStats:
    median: dict
    mad: dict


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def fit_baseline(reference_takes: list[dict]) -> BaselineStats:
    if len(reference_takes) < 3:
        raise ValueError("Need at least 3 clean reference takes to fit a baseline.")

    median, mad = {}, {}
    for feature in FEATURE_ORDER:
        values = [take[feature] for take in reference_takes]
        med = _median(values)
        deviations = [abs(v - med) for v in values]
        # 1.4826 makes MAD a consistent estimator of std under normality.
        mad_val = 1.4826 * _median(deviations)
        median[feature] = med
        mad[feature] = mad_val if mad_val > 0 else 1e-6
    return BaselineStats(median=median, mad=mad)


def per_feature_deviation(stats: BaselineStats, take: dict) -> dict[str, float]:
    """Signed robust z-score per feature, not collapsed into one number --
    this is what lets the note/selector say *which* feature actually moved
    (e.g. speaking_rate, not pause_fraction) instead of a fixed guess."""
    return {
        feature: (take[feature] - stats.median[feature]) / stats.mad[feature]
        for feature in FEATURE_ORDER
    }


def deviation_score(stats: BaselineStats, take: dict) -> float:
    """Combined robust z-score across all features (Euclidean norm in
    z-score space). Larger = further from this person's own normal."""
    z_scores = per_feature_deviation(stats, take)
    return math.sqrt(sum(z * z for z in z_scores.values()))


class PersistentDeviationTracker:
    """Requires a deviation to repeat across consecutive check-ins before
    counting as 'persistent' -- a single noisy take should not trigger the
    condition-specific follow-up on its own."""

    def __init__(self, threshold: float, required_consecutive: int = 2):
        self.threshold = threshold
        self.required_consecutive = required_consecutive
        self._consecutive = 0

    def observe(self, score: float) -> bool:
        if score >= self.threshold:
            self._consecutive += 1
        else:
            self._consecutive = 0
        return self._consecutive >= self.required_consecutive
