"""Wires the RAG selection built in retrieval.py / groq_selector.py /
validation.py into Codex's conversation-state seam (app/api/conversations.py's
get_selector). This module never imports conversations.py -- the boundary
is the plain dict in, dict out contract described in CONVERSATIONS.md, so
either side can change independently as long as that shape holds.
"""
from typing import Callable

from app.dialogue.groq_selector import _default_model_call, select_question
from app.dialogue.retrieval import load_corpus_version, retrieve_eligible_units
from app.dialogue.validation import validate_selection

# Matches the id/version conversations.py's own legacy-initial question
# uses for its placeholder source, so prototype-policy-sourced units (no
# real citation) render consistently with the rest of the system.
_POLICY_SOURCE = {"id": "prototype-dialogue-policy", "version": "1"}


def _source_for(unit: dict) -> dict:
    if unit["source_type"] == "design_policy":
        return _POLICY_SOURCE
    return {"id": unit["id"], "version": unit.get("source_version") or "unversioned"}


def selector_adapter(context: dict, model_call: Callable[[str], str] = _default_model_call) -> dict:
    """context: {"condition", "measured", "turns", "answer_text"} exactly as
    conversations.py's answer() builds it. Returns a plain dict shaped for
    conversations.py's Selection.model_validate(...) -- never a Selection
    instance directly, keeping this module free of any dependency on
    conversations.py's pydantic models.

    Raises SelectionRejected (from validation.py) when the model's answer
    doesn't hold up -- deliberately not caught here. conversations.py
    already wraps the entire selector call in try/except and falls back
    to abstain on any exception, so duplicating that handling here would
    just be a second copy of the same fallback with no added safety.

    `model_call` is injectable for tests; production code (main.py's
    dependency override) calls this with no override, using the real
    Groq call.
    """
    condition = context["condition"]
    turns = context.get("turns") or []
    answer_text = context["answer_text"]

    prior_answers = [t["answer"] for t in turns if t.get("answer")] + [answer_text]
    already_asked_ids = {t["question"]["id"] for t in turns if t.get("question")}

    # `measured.features` (context["measured"]) currently holds raw feature
    # values (pause_fraction, longest_internal_gap, speaking_rate), not the
    # per-feature z-scores personal_baseline.per_feature_deviation() can
    # produce -- that wiring from checkin into the conversations table
    # isn't in yet (flagged in CONVERSATIONS.md). Passing an empty dict
    # here is deliberate, not an oversight: a context flag like
    # measured_pause_fraction_elevated needs a z-score to mean anything,
    # and computing it from a raw value on the wrong scale would be worse
    # than leaving it unavailable. Units gated on that flag (e.g.
    # breath_support_phrasing) simply stay ineligible until this lands.
    feature_scores: dict[str, float] = {}

    eligible = retrieve_eligible_units(
        condition=condition,
        feature_scores=feature_scores,
        prior_answers=prior_answers,
        already_asked_ids=already_asked_ids,
    )
    if not eligible:
        # Corpus exhausted for this conversation -- a legitimate completion
        # signal, not a classification failure. conversations.py still
        # requires every prior turn to be resolved before honoring
        # 'complete', so this can't prematurely close an unresolved thread
        # on its own.
        return {"decision": "complete", "resolved": True}

    output = select_question(eligible, answer_text, model_call=model_call)
    validated = validate_selection(output, eligible, answer_text)

    unit = validated.unit
    return {
        "decision": "ask",
        "resolved": True,
        "question": {
            "id": unit["id"],
            "version": load_corpus_version(),
            "text": validated.rendered_question_text,
            "sources": [_source_for(unit)],
        },
    }
