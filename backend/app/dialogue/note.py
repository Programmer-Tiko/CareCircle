"""Three-bucket note: measured, patient-said, unresolved -- kept separate
always, per the brief's dialogue policy. The patient's own words, not the
acoustic measurement, are what the note actually reports as fact.
"""
from dataclasses import dataclass, field

_FEATURE_DESCRIPTIONS = {
    "pause_fraction": "Longer pauses than your usual pattern, repeated across this check-in.",
    "longest_internal_gap": "One notably longer pause than your usual pattern.",
    "speaking_rate": "A different speaking pace than your usual pattern.",
}


@dataclass
class Note:
    measured: str
    patient_said: str | None = None
    unresolved: list[str] = field(default_factory=list)
    status: str = "awaiting_confirmation"

    def confirm(self) -> None:
        self.status = "confirmed"

    def to_dict(self) -> dict:
        return {
            "measured": self.measured,
            "patient_said": self.patient_said,
            "unresolved": list(self.unresolved),
            "status": self.status,
        }


def describe_measured_deviation(deviation_score: float, feature_scores: dict[str, float] | None = None) -> str:
    """Names the feature that actually drove the deviation, instead of
    assuming it was pauses. Falls back to the generic pause description
    only when no per-feature breakdown is available (keeps old callers
    working), not as the default explanation."""
    if deviation_score < 2.0:
        return "Sounds like your usual self today."
    if not feature_scores:
        return _FEATURE_DESCRIPTIONS["pause_fraction"]
    dominant = max(feature_scores, key=lambda f: abs(feature_scores[f]))
    return _FEATURE_DESCRIPTIONS.get(dominant, _FEATURE_DESCRIPTIONS["pause_fraction"])


def build_note(
    deviation_score: float,
    patient_said: str | None,
    cue_resolved: bool,
    feature_scores: dict[str, float] | None = None,
    classification_succeeded: bool = True,
) -> Note:
    """`cue_resolved` means "no further question is needed" (a recognized
    cue that doesn't require follow-up). `classification_succeeded` means
    "we understood what the patient's answer was about" -- these are not
    the same thing. An answer that matched nothing (classification failed)
    must stay unresolved even though there's no follow-up to ask, rather
    than being silently treated as resolved because follow_up was None.
    """
    measured = describe_measured_deviation(deviation_score, feature_scores)
    truly_resolved = cue_resolved and classification_succeeded
    unresolved = [] if (patient_said is None or truly_resolved) else ["What caused the change is still unclear."]
    return Note(measured=measured, patient_said=patient_said, unresolved=unresolved)
