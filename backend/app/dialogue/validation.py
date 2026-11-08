"""Server-side validation of the selector's structured output. Schema
validity (Gemini's structured-output feature) is not semantic correctness
-- these checks are what actually enforce "the model can only pick what's
already approved," not the schema alone.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SelectorOutput:
    selected_question_id: str | None
    evidence_ids: list[str]
    patient_quote: str | None
    abstain: bool


@dataclass(frozen=True)
class ValidatedSelection:
    unit: dict
    # Always the stored template, never the model's own phrasing.
    rendered_question_text: str


class SelectionRejected(Exception):
    """The model's output failed validation. Callers fall back to the
    deterministic initial/follow-up card -- never retry with looser checks."""


def validate_selection(
    output: SelectorOutput,
    eligible_units: list[dict],
    latest_answer: str,
) -> ValidatedSelection:
    if output.abstain or output.selected_question_id is None:
        raise SelectionRejected("Model abstained or returned no selection.")

    eligible_by_id = {u["id"]: u for u in eligible_units}
    unit = eligible_by_id.get(output.selected_question_id)
    if unit is None:
        raise SelectionRejected(
            f"Selected question {output.selected_question_id!r} is not in the eligible set."
        )

    # One source per unit in this corpus -- evidence_ids must point only at
    # the selected question's own provenance, never borrowed from another.
    if output.evidence_ids and output.evidence_ids != [unit["id"]]:
        raise SelectionRejected("Evidence IDs do not belong to the selected question's own provenance.")

    if output.patient_quote and output.patient_quote.strip().lower() not in latest_answer.lower():
        raise SelectionRejected("Patient quote does not occur verbatim in the answer.")

    return ValidatedSelection(unit=unit, rendered_question_text=unit["question_template"])
