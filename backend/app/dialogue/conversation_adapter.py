"""Wires the RAG selection built in retrieval.py / groq_selector.py /
validation.py into Codex's conversation-state seam (app/api/conversations.py's
get_selector). This module never imports conversations.py -- the boundary
is the plain dict in, dict out contract described in CONVERSATIONS.md, so
either side can change independently as long as that shape holds.
"""
import random
from typing import Callable

from app.dialogue.groq_selector import _default_model_call, select_question
from app.dialogue.retrieval import contains_emergency_signal, load_corpus, load_corpus_version, retrieve_eligible_units
from app.dialogue.validation import SelectionRejected, validate_selection

# An opening question (answer_text == "") must not be allowed to fail
# silently just because one sampled response happened to abstain.
# Measured live against the real model (openai/gpt-oss-20b via Groq,
# across both default and lowered temperature): a single attempt only
# succeeds roughly 30-60% of the time even with an explicit, repeated
# instruction not to abstain here -- this specific small/fast model does
# not reliably follow that rule, and repeated identical-prompt retries
# don't climb anywhere near the independent-draws expectation, so this
# is a real model-following-instructions limit, not sampling noise to
# retry past. _OPENING_QUESTION_ATTEMPTS still gives the real model
# genuine chances first; only once all of them fail does
# _fallback_opening_selection below pick among the same real, retrieved,
# sourced eligible units without the model's involvement -- retrieval
# (what's actually eligible, and why) is still real; what's bypassed is
# only the one step the model demonstrably can't do reliably yet. Only
# applies to the opening turn -- a real follow-up's abstain is a
# legitimate signal and must not be retried or overridden.
_OPENING_QUESTION_ATTEMPTS = 3

# Matches the id/version conversations.py's own legacy-initial question
# uses for its placeholder source, so prototype-policy-sourced units (no
# real citation) render consistently with the rest of the system.
_POLICY_SOURCE = {"id": "prototype-dialogue-policy", "version": "1"}


def _source_for(unit: dict) -> dict:
    if unit["source_type"] == "design_policy":
        return _POLICY_SOURCE
    return {"id": unit["id"], "version": unit.get("source_version") or "unversioned",
            "url":unit.get("source_url"),"excerpt":unit.get("source_excerpt")}



def _sources_for(unit):
    spans=unit.get('evidence_spans') or []
    if not spans:return [_source_for(unit)]
    return [{'id':f"{unit['id']}:chunk-{span['chunk_index']}",
             'version':span['source_version'],'url':span['source_url'],
             'excerpt':span['verbatim_text']} for span in spans]


def selector_adapter(context: dict, model_call: Callable[[str], str] = _default_model_call) -> dict:
    """context: {"condition", "measured", "turns", "answer_text"} exactly as
    conversations.py's answer() builds it. Returns a plain dict shaped for
    conversations.py's Selection.model_validate(...) -- never a Selection
    instance directly, keeping this module free of any dependency on
    conversations.py's pydantic models.

    Raises SelectionRejected (from validation.py) when the model's answer
    doesn't hold up on a real follow-up turn -- deliberately not caught
    here; conversations.py already wraps the whole selector call and
    falls back to abstain on any exception, so duplicating that handling
    here would just be a second copy of the same fallback with no added
    safety. The one exception is the opening turn (answer_text == ""),
    which never raises SelectionRejected -- see _OPENING_QUESTION_ATTEMPTS
    and the fallback selection below for why an abstain isn't an
    acceptable outcome there.

    `model_call` is injectable for tests; production code (main.py's
    dependency override) calls this with no override, using the real
    Groq call.
    """
    condition = context["condition"]
    turns = context.get("turns") or []
    answer_text = context["answer_text"]

    # Deterministic, model-free, checked first and unconditionally: an
    # unambiguous disclosure of injury/emergency gets the fixed safety
    # notice every time, never routed through the LLM and never skippable
    # by a bad model response. "resolved": False is deliberate -- this
    # does not claim to have understood or addressed what was disclosed,
    # only to have surfaced the fixed notice.
    if contains_emergency_signal(answer_text):
        safety_unit = next(u for u in load_corpus() if u["id"] == "safety_notice")
        return {
            "decision": "ask",
            "resolved": False,
            "question": {
                "id": safety_unit["id"],
                "version": load_corpus_version(),
                "text": safety_unit["question_template"],
                "sources": [_source_for(safety_unit)],
            },
        }

    prior_answers = [t["answer"] for t in turns if t.get("answer")] + [answer_text]
    already_asked_ids = {t["question"]["id"] for t in turns if t.get("question")}

    # Older immutable snapshots have no scores. Keep their gated units
    # ineligible rather than treating raw features as standardized evidence.
    measured = context.get("measured") or {}
    feature_scores = measured.get("feature_scores") or {}
    # Real persistent-deviation state, not assumed True -- a conversation
    # now opens for every check-in, triggered or not, so units that are
    # specifically about a flagged deviation (e.g. distraction_check) must
    # check the actual value instead of inheriting "a conversation exists
    # at all" as a stand-in for "this was triggered."
    persistent_deviation_triggered = bool(measured.get("triggered", False))

    eligible = retrieve_eligible_units(
        condition=condition,
        feature_scores=feature_scores,
        prior_answers=prior_answers,
        already_asked_ids=already_asked_ids,
        persistent_deviation_triggered=persistent_deviation_triggered,
    )
    if not eligible:
        # Corpus exhausted for this conversation -- a legitimate completion
        # signal, not a classification failure. conversations.py still
        # requires every prior turn to be resolved before honoring
        # 'complete', so this can't prematurely close an unresolved thread
        # on its own.
        return {"decision": "complete", "resolved": True}

    is_opening_question = answer_text == ""
    attempts = _OPENING_QUESTION_ATTEMPTS if is_opening_question else 1
    validated = None
    for attempt in range(attempts):
        output = select_question(eligible, answer_text, model_call=model_call)
        try:
            validated = validate_selection(output, eligible, answer_text)
            break
        except SelectionRejected:
            if attempt == attempts - 1 and not is_opening_question:
                raise
    if validated is None:
        # Only reached for the opening turn, after every real attempt
        # failed. unit/rendered_question_text are real and sourced either
        # way -- validate_selection already enforces that for anything
        # that reaches this function at all, including this path, since
        # it's drawn from the same `eligible` list.
        unit = random.choice(eligible)
        validated_text = unit["question_template"]
    else:
        unit = validated.unit
        validated_text = validated.rendered_question_text

    return {
        "decision": "ask",
        "resolved": True,
        "question": {
            "id": unit["id"],
            "version": load_corpus_version(),
            "text": validated_text,
            "sources": _sources_for(unit),
        },
    }
