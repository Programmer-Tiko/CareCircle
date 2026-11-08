import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dialogue.note import build_note


def test_typical_deviation_reports_normal():
    note = build_note(deviation_score=0.5, patient_said=None, cue_resolved=True)
    assert "usual" in note.measured
    assert note.unresolved == []
    assert note.status == "awaiting_confirmation"


def test_resolved_cue_has_no_unresolved_items():
    note = build_note(deviation_score=3.0, patient_said="I stopped for breath", cue_resolved=True)
    assert note.unresolved == []
    assert note.patient_said == "I stopped for breath"


def test_unresolved_cue_flags_it():
    note = build_note(deviation_score=3.0, patient_said="not sure why", cue_resolved=False)
    assert len(note.unresolved) == 1


def test_confirm_changes_status():
    note = build_note(deviation_score=0.5, patient_said=None, cue_resolved=True)
    note.confirm()
    assert note.status == "confirmed"
