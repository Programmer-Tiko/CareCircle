import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.passage import PASSAGE_TEXT, PASSAGE_SYLLABLE_COUNT, PASSAGE_SYLLABLES
from app.api.main import PASSAGE_SYLLABLE_COUNT as API_COUNT


def test_pinned_passage_matches_audited_count():
    assert re.findall(r'[A-Za-z]+', PASSAGE_TEXT) == [word for word, count in PASSAGE_SYLLABLES]
    assert sum(count for word, count in PASSAGE_SYLLABLES) == PASSAGE_SYLLABLE_COUNT == API_COUNT == 41
