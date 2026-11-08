"""Metadata filtering plus lexical ranking over the question corpus. No
vector database -- at a few dozen units, filtering by condition/context
flags and ranking by keyword overlap is enough. Add embeddings only if
paraphrase misses actually show up in practice, not preemptively.
"""
import json
import re
from pathlib import Path

_CORPUS_PATH = Path(__file__).with_name("question_corpus.json")

# Deliberately narrow and literal, not a clinical triage system: catches
# an unambiguous disclosure of injury/emergency so the fixed safety notice
# fires every time, not only when a language model happens to notice. A
# prototype safety net, not exhaustive -- documented as such, not implied
# to be complete.
EMERGENCY_KEYWORDS = (
    "i fell", "fell down", "fell and", "hurt myself", "injured", "broke my",
    "can't get up", "cant get up", "bleeding", "call 911", "need an ambulance",
    "hospital now", "chest pain",
)

# These are deliberately narrow language rules for prototype eligibility,
# not a diagnosis or a clinically validated understanding model.
_SPEECH_DOMAIN = r"\b(?:speak(?:ing)?|speech|talk(?:ing)?|voice|words?|sentences?|slurr?\w*)\b"
_SPEECH_ATTRIBUTE = r"(?:hoarse|hoarser|weak|weaker|tired|strained|soft|softer|quiet|quieter|slurred|unclear|faster|slower)"
_SPEECH_ACTION = r"(?:speaking|talking|speech|(?:my )?voice|getting (?:the )?words out|saying words|being understood)"
_UNCERTAIN = re.compile(r"\b(?:not sure|unsure|maybe|might|could|possibly|cannot tell|can\'t tell|do not know|don\'t know)\b")


def _clauses(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("isn't", "is not").replace("wasn't", "was not")
    text = text.replace("don't", "do not").replace("didn't", "did not").replace("can't", "cannot")
    return [part.strip() for part in re.split(r"[.!?;,]|\b(?:but|however|although)\b", text) if part.strip()]


def _speech_report(answer: str) -> bool | None:
    """Last explicit speech assertion in an answer; None means no new evidence.

    Neutral/uncertain answers preserve earlier explicit reports. Denial or
    resolution must name speech, rather than borrowing a word like 'no' from
    an unrelated answer. We do not infer symptoms from general tiredness,
    sleep difficulty, breathlessness during exercise, or arbitrary 'words'.
    """
    state = None
    for clause in _clauses(answer):
        has_domain = bool(re.search(_SPEECH_DOMAIN, clause))
        if _UNCERTAIN.search(clause):
            continue
        denial = (
            re.search(r"\b(?:no|without) (?:trouble|difficulty|problems?|issues?)(?: with)? " + _SPEECH_ACTION, clause)
            or re.search(r"\b(?:do not|did not) (?:have|experience)(?: any)? (?:trouble|difficulty|problems?)(?: with)? " + _SPEECH_ACTION, clause)
            or re.search(r"\bno longer (?:have |having )?(?:trouble|difficulty|problems?)(?: with)? " + _SPEECH_ACTION, clause)
            or re.search(r"\b(?:no|without) (?:speech|voice|speaking|communication) (?:problems?|difficulties|issues?)\b", clause)
            or (has_domain and re.search(r"\b(?:is|sounds?|feels?) no longer " + _SPEECH_ATTRIBUTE + r"\b", clause))
            or (has_domain and re.search(r"\b(?:is|feels|sounds|are) (?:back to )?(?:normal|fine|okay|ok|usual)\b", clause))
            or (has_domain and re.search(r"\b(?:resolved|recovered|gone away|cleared up|no longer present)\b", clause))
            or (has_domain and re.search(r"\b(?:do not|did not|never) (?:slur|need to repeat|have to repeat|run out of breath)\b", clause))
            or (has_domain and re.search(r"\b(?:is|are|was|sounds?|feels?) not (?:very |at all )?" + _SPEECH_ATTRIBUTE + r"\b", clause))
        )
        if denial:
            state = False
            continue
        if re.search(r"\bused to\b", clause) and not re.search(r"\b(?:still|again|currently)\b", clause):
            continue  # A past-only report does not establish a current symptom.
        affirmative = (
            re.search(r"\b(?:hard|difficult)(?: for me)? to (?:speak|talk|get (?:the )?words out|say words|be understood)\b", clause)
            or re.search(r"\b(?:trouble|difficulty|problems?)(?: with)? " + _SPEECH_ACTION, clause)
            or re.search(r"\b(?:cannot|unable to|struggle to) (?:speak|talk|get (?:the )?words out|be understood)\b", clause)
            or re.search(r"\b(?:voice|speech)(?: (?:is|feels|sounds|gets|has become|seems))?(?: (?:very|more|a bit|too|unusually))? " + _SPEECH_ATTRIBUTE + r"\b", clause)
            or re.search(r"\b(?:slur|slurring|slurred) (?:my |the )?words\b", clause)
            or re.search(r"\b(?:ask|asks|asked|asking) me to repeat\b|\b(?:need|have) to repeat myself\b", clause)
            or re.search(r"\b(?:people|others|family|they) (?:cannot|do not) (?:hear|understand) me\b", clause)
            or (has_domain and re.search(r"\b(?:run|running) out of (?:air|breath)\b", clause))
        )
        if affirmative:
            state = True
    return state


def _recording_interruption(answer: str) -> bool:
    """Only an interruption of this capture, not everyday noisy communication.

    Clear short answers such as 'the dog interrupted me' are accepted in the
    check-in context. Generic noise/distraction needs a recording/reading cue.
    This flag affects question eligibility only; it never changes scored audio
    or replays/undoes the persistence tracker.
    """
    state = False
    for clause in _clauses(answer):
        capture = bool(re.search(r"\b(?:recording|reading|passage|microphone|mic|check[ -]?in|this take|that pause)\b", clause))
        everyday = bool(re.search(r"\b(?:restaurant|crowd|party|dinner|social|conversation|noisy room|at work)\b", clause))
        disruption = bool(re.search(r"\b(?:interrupt\w*|distract\w*|noise|bark\w*|doorbell|phone rang|someone spoke)\b", clause))
        if disruption and re.search(r"\b(?:no|nothing|not|never)\b", clause):
            state = False
            continue
        clear_event = bool(re.search(r"\b(?:dog|cat|someone|child|kid)\b.{0,30}\binterrupted me\b|\b(?:phone|doorbell) rang\b", clause))
        if disruption and (capture or (clear_event and not everyday)):
            state = True
    return state


# "I feel good, nothing unusual" was getting followed by an unrelated sleep
# question, then anxiety, then balance -- several corpus units have no
# preconditions at all (deliberately, so an opening question always has a
# real choice), which also meant nothing made them *stop* being offered
# once the patient had already said they're fine. This flag exists so a
# clear, current reassurance can close those out, same spirit as
# _recording_interruption: narrow and literal, latest answer only (an
# earlier "I feel good" must not block a later answer that says otherwise),
# not a claim of understanding sentiment in general.
_WELLNESS_POSITIVE_STATE = re.compile(
    r"\b(?:feel(?:ing)?|doing|am|is|was|seem(?:s|ing)?) "
    r"(?:pretty |really |just |quite )?(?:good|fine|okay|ok|well|great|normal|alright)\b"
)
_WELLNESS_NO_PROBLEMS = re.compile(
    r"\bnothing (?:unusual|wrong|new|different|to report)\b"
    r"|\bno (?:concerns|issues|problems|complaints)\b"
    r"|\ball (?:good|fine|well|okay|ok)\b"
)
# The single most common real answer to "how are you doing?" is just one
# of these words on its own, with or without "I'm" in front -- exactly the
# example given when this flag was requested ("I'll say good"). A clause
# that short has no verb for _WELLNESS_POSITIVE_STATE to anchor on.
_WELLNESS_BARE = re.compile(
    r"^(?:i'?m|i am|im)?\s*(?:pretty |really |just |quite )?(?:good|fine|okay|ok|well|great|normal|alright)$"
)
_NEGATION_TOKEN = re.compile(r"\b(?:not|never|hardly)\b")


def _wellness_reassurance(answer: str) -> bool:
    for clause in _clauses(answer):
        if _WELLNESS_NO_PROBLEMS.search(clause) or _WELLNESS_BARE.match(clause):
            return True
        if _WELLNESS_POSITIVE_STATE.search(clause) and not _NEGATION_TOKEN.search(clause):
            return True
    return False


_STOPWORDS = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "is", "it", "that", "this", "was", "were"}


def contains_emergency_signal(answer_text: str) -> bool:
    text = answer_text.lower()
    return any(kw in text for kw in EMERGENCY_KEYWORDS)


def load_corpus() -> list[dict]:
    data = json.loads(_CORPUS_PATH.read_text())
    return data["units"]


def load_corpus_version() -> str:
    data = json.loads(_CORPUS_PATH.read_text())
    return data["version"]


def compute_context_flags(
    feature_scores: dict[str, float],
    prior_answers: list[str],
    medication_status_known: bool = False,
    persistent_deviation_triggered: bool = False,
) -> dict[str, bool]:
    """Derives the named boolean flags units' preconditions/exclusions
    check against, from what's actually available: the per-feature
    deviation scores and the conversation's answers so far. Anything not
    derivable (we don't track medication status yet) defaults to False/
    excluded, rather than guessing.

    `persistent_deviation_triggered` used to be hardcoded True here, back
    when this function was only ever reachable from an already-triggered
    conversation. Now every check-in opens a conversation, so the caller
    must pass the real value -- defaulting to False keeps units gated on
    an actual persistent deviation (e.g. distraction_check) from firing
    on ordinary readings just because a conversation exists at all.
    """
    # Replay explicit reports, not substrings in only the latest sentence.
    speech_reported = False
    for answer in prior_answers:
        update = _speech_report(answer)
        if update is not None:
            speech_reported = update
    interruption = _recording_interruption(prior_answers[-1]) if prior_answers else False
    reassured = _wellness_reassurance(prior_answers[-1]) if prior_answers else False
    return {
        "persistent_deviation_triggered": persistent_deviation_triggered,
        "measured_pause_fraction_elevated": feature_scores.get("pause_fraction", 0.0) > 1.5,
        "initial_answer_mentions_speech_difficulty": speech_reported,
        "speech_motor_cue_present": speech_reported,
        "recording_interrupted_by_distraction": interruption,
        "answer_indicates_situational_distraction": interruption,  # compatibility alias
        "patient_known_to_take_pd_medication": medication_status_known,
        "medication_status_unknown": not medication_status_known,
        "patient_reports_no_concerns": reassured,
    }


def is_eligible(unit: dict, context: dict[str, bool]) -> bool:
    if unit.get("blocked", False):
        return False
    if any(flag not in context for flag in unit["preconditions"] + unit["exclusions"]):
        return False
    for flag in unit["preconditions"]:
        if not context.get(flag, False):
            return False
    for flag in unit["exclusions"]:
        if context.get(flag, False):
            return False
    return True


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _lexical_overlap(unit: dict, answer_text: str) -> int:
    answer_tokens = _tokenize(answer_text)
    unit_tokens = _tokenize(unit["question_template"]) | _tokenize(unit["information_sought"].replace("_", " "))
    return len(answer_tokens & unit_tokens)


def retrieve_eligible_units(
    condition: str,
    feature_scores: dict[str, float],
    prior_answers: list[str],
    already_asked_ids: set[str],
    medication_status_known: bool = False,
    persistent_deviation_triggered: bool = False,
) -> list[dict]:
    """Returns eligible units ranked by lexical overlap with the latest
    answer, most relevant first. Already-asked units are excluded
    entirely -- the selector should never be offered a repeat."""
    context = compute_context_flags(feature_scores, prior_answers, medication_status_known, persistent_deviation_triggered)
    latest_answer = prior_answers[-1] if prior_answers else ""

    candidates = [
        unit
        for unit in load_corpus()
        if unit["condition"] == condition
        and unit["id"] != "safety_notice"  # reachable only via the hard-coded emergency check, never normal selection
        and unit["id"] not in already_asked_ids
        and is_eligible(unit, context)
    ]
    return sorted(candidates, key=lambda u: _lexical_overlap(u, latest_answer), reverse=True)
