"""Three-bucket note: measured, patient-said, unresolved -- kept separate
always, per the brief's dialogue policy. The patient's own words, not the
acoustic measurement, are what the note actually reports as fact.
"""
from dataclasses import dataclass, field


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


def describe_measured_deviation(deviation_score: float) -> str:
    if deviation_score < 2.0:
        return "Sounds like your usual self today."
    return "Longer pauses than your usual pattern, repeated across this check-in."


def build_note(deviation_score: float, patient_said: str | None, cue_resolved: bool) -> Note:
    measured = describe_measured_deviation(deviation_score)
    unresolved = [] if (patient_said is None or cue_resolved) else ["What caused the change is still unclear."]
    return Note(measured=measured, patient_said=patient_said, unresolved=unresolved)
