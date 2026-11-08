import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.retrieval import compute_context_flags, load_corpus, retrieve_eligible_units


def test_corpus_loads_and_every_unit_has_required_fields():
    units = load_corpus()
    assert len(units) >= 5
    for unit in units:
        for field in ("id", "condition", "information_sought", "preconditions",
                      "exclusions", "question_template", "review_status"):
            assert field in unit
        assert unit["review_status"] == "prototype"


def test_distraction_excludes_symptom_follow_ups():
    # distraction_check is specifically about an already-flagged, persistent
    # deviation that turned out to have an innocent explanation -- it must
    # not appear just because a conversation exists (every check-in opens
    # one now), only when the deviation was actually persistent.
    flags = compute_context_flags(feature_scores={"pause_fraction": 2.0}, prior_answers=["the dog interrupted me"],
                                   persistent_deviation_triggered=True)
    assert flags["answer_indicates_situational_distraction"] is True
    results = retrieve_eligible_units(
        condition="parkinsons",
        feature_scores={"pause_fraction": 2.0},
        prior_answers=["the dog interrupted me"],
        already_asked_ids=set(),
        persistent_deviation_triggered=True,
    )
    ids = {u["id"] for u in results}
    assert "everyday_communication_impact" not in ids
    assert "distraction_check" in ids


def test_distraction_check_not_offered_without_a_real_persistent_deviation():
    # Same answer and feature scores as above, but persistent_deviation_triggered
    # defaults to False -- an ordinary, non-triggered check-in's conversation
    # must not be able to reach distraction_check at all.
    results = retrieve_eligible_units(
        condition="parkinsons",
        feature_scores={"pause_fraction": 2.0},
        prior_answers=["the dog interrupted me"],
        already_asked_ids=set(),
    )
    assert "distraction_check" not in {u["id"] for u in results}


def test_several_units_are_eligible_with_no_prior_answer_at_all():
    # The opening turn of every check-in now goes through this same
    # eligible-set mechanism, with no answer yet to react to. There must be
    # real choice available, not a single unit masquerading as a selection.
    results = retrieve_eligible_units(
        condition="parkinsons", feature_scores={}, prior_answers=[""], already_asked_ids=set(),
    )
    assert len(results) >= 3


def test_already_asked_units_are_excluded():
    results = retrieve_eligible_units(
        condition="parkinsons",
        feature_scores={},
        prior_answers=["it's hard to get words out"],
        already_asked_ids={"everyday_communication_impact"},
    )
    ids = {u["id"] for u in results}
    assert "everyday_communication_impact" not in ids


def test_medication_question_excluded_without_known_status():
    results = retrieve_eligible_units(
        condition="parkinsons",
        feature_scores={},
        prior_answers=["it happens sometimes"],
        already_asked_ids=set(),
        medication_status_known=False,
    )
    ids = {u["id"] for u in results}
    assert "off_period_timing" not in ids


def test_lexical_overlap_ranks_more_relevant_unit_first():
    results = retrieve_eligible_units(
        condition="parkinsons",
        feature_scores={"pause_fraction": 2.0},
        prior_answers=["it's hard to get words out and people ask me to repeat myself"],
        already_asked_ids=set(),
    )
    ids = [u["id"] for u in results]
    assert ids.index("repetition_frequency") < len(ids) - 1
