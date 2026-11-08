"""Wires the RAG selection built in retrieval.py / groq_selector.py /
validation.py into Codex's conversation-state seam (app/api/conversations.py's
get_selector). This module never imports conversations.py -- the boundary
is the plain dict in, dict out contract described in CONVERSATIONS.md, so
either side can change independently as long as that shape holds.
"""
from typing import Callable

from app.dialogue.groq_selector import _default_model_call, select_question
from app.dialogue.retrieval import contains_emergency_signal, load_corpus, load_corpus_version, retrieve_eligible_units
from app.dialogue.validation import validate_selection

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
    feature_scores = (context.get("measured") or {}).get("feature_scores") or {}

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
            "sources": _sources_for(unit),
        },
    }
