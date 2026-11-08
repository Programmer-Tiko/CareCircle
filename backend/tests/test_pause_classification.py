"""Tests for position-aware pause classification and Levenshtein alignment."""
import pytest

from app.audio.pause_classification import (
    AlignOp,
    classify_pause_position,
    levenshtein_alignment,
)
from app.audio.phrase_alignment import normalize_tokens
from app.passage import PASSAGE_TEXT


class TestLevenshteinAlignment:
    def test_exact_identity(self):
        tokens = ["when", "the", "sunlight"]
        alignment = levenshtein_alignment(tokens, tokens)
        assert len(alignment) == 3
        for i, op in enumerate(alignment):
            assert op.op == "match"
            assert op.expected_idx == i
            assert op.observed_idx == i

    def test_substitution_and_deletion(self):
        expected = ["a", "rainbow", "is", "beautiful"]
        observed = ["a", "moon", "beautiful"]
        alignment = levenshtein_alignment(expected, observed)
        ops = [a.op for a in alignment]
        assert "match" in ops
        assert "substitution" in ops  # rainbow -> moon
        assert "deletion" in ops      # is deleted

    def test_insertion(self):
        expected = ["when", "sunlight"]
        observed = ["when", "the", "sunlight"]
        alignment = levenshtein_alignment(expected, observed)
        ops = [a.op for a in alignment]
        assert ops == ["match", "insertion", "match"]
        assert alignment[1].expected_idx is None
        assert alignment[1].observed_idx == 1


class TestPositionAwarePauseClassification:
    def test_reproducer_rainbow_second_occurrence(self):
        """Reproducer from ANTIGRAVITY-REVIEW-FIXES.md:
        'A rainbow. The rainbow is beautiful.'
        Pause between the second 'rainbow' and 'is' must be within_clause.
        """
        raw_passage = "A rainbow. The rainbow is beautiful."
        expected_raw = raw_passage.split()
        expected_norm = normalize_tokens(raw_passage)
        # expected_norm = ['a', 'rainbow', 'the', 'rainbow', 'is', 'beautiful']
        # expected_raw indices:
        # 0: "A", 1: "rainbow.", 2: "The", 3: "rainbow", 4: "is", 5: "beautiful."

        # Observed reading has the second rainbow and is:
        observed_norm = ["the", "rainbow", "is", "beautiful"]
        alignment = levenshtein_alignment(expected_norm, observed_norm)

        # Pause between observed[1] ('rainbow') and observed[2] ('is')
        cat = classify_pause_position(
            observed_idx=2,
            alignment=alignment,
            expected_tokens_raw=expected_raw,
        )
        assert cat == "within_clause", (
            f"Pause between second 'rainbow' and 'is' must be within_clause, got {cat}"
        )

    def test_reproducer_rainbow_first_occurrence(self):
        """Pause between first 'rainbow.' and 'The' must be punctuation_adjacent."""
        raw_passage = "A rainbow. The rainbow is beautiful."
        expected_raw = raw_passage.split()
        expected_norm = normalize_tokens(raw_passage)
        # Pause between observed[1] ('rainbow') and observed[2] ('the')
        observed_norm = ["a", "rainbow", "the", "rainbow", "is", "beautiful"]
        alignment = levenshtein_alignment(expected_norm, observed_norm)

        cat = classify_pause_position(
            observed_idx=2,
            alignment=alignment,
            expected_tokens_raw=expected_raw,
        )
        assert cat == "punctuation_adjacent", (
            f"Pause after 'rainbow.' must be punctuation_adjacent, got {cat}"
        )

    def test_distinguish_pause_before_air_from_after_air(self):
        """Rainbow passage: '... in the air, they act ...'
        Pause BEFORE 'air,' ('the' -> 'air') must be within_clause.
        Pause AFTER 'air,' ('air,' -> 'they') must be punctuation_adjacent.
        """
        expected_raw = PASSAGE_TEXT.split()
        expected_norm = normalize_tokens(PASSAGE_TEXT)
        # Expected indices:
        # 6: "the", 7: "air,", 8: "they"
        observed_norm = expected_norm.copy()
        alignment = levenshtein_alignment(expected_norm, observed_norm)

        # Pause between observed[6] ('the') and observed[7] ('air')
        cat_before = classify_pause_position(
            observed_idx=7,
            alignment=alignment,
            expected_tokens_raw=expected_raw,
        )
        assert cat_before == "within_clause", (
            f"Pause BEFORE 'air,' must be within_clause, got {cat_before}"
        )

        # Pause between observed[7] ('air') and observed[8] ('they')
        cat_after = classify_pause_position(
            observed_idx=8,
            alignment=alignment,
            expected_tokens_raw=expected_raw,
        )
        assert cat_after == "punctuation_adjacent", (
            f"Pause AFTER 'air,' must be punctuation_adjacent, got {cat_after}"
        )

    def test_asr_invented_punctuation_ignored(self):
        """If ASR outputs punctuation where expected has none, classification
        is strictly driven by expected passage.
        """
        raw_passage = "The sunlight strikes raindrops"
        expected_raw = raw_passage.split()
        expected_norm = normalize_tokens(raw_passage)

        # Observed has the same words, but ASR attaches a comma to "sunlight,"
        # Normalization strips it for alignment:
        observed_norm = ["the", "sunlight", "strikes", "raindrops"]
        alignment = levenshtein_alignment(expected_norm, observed_norm)

        # Pause between observed[1] ('sunlight') and observed[2] ('strikes')
        cat = classify_pause_position(
            observed_idx=2,
            alignment=alignment,
            expected_tokens_raw=expected_raw,
        )
        assert cat == "within_clause"

    def test_inserted_word_reports_unknown(self):
        """If a pause is adjacent to an inserted (unaligned) word, report unknown."""
        expected_raw = ["When", "the", "sunlight"]
        expected_norm = ["when", "the", "sunlight"]
        # Participant said: "when um the sunlight"
        observed_norm = ["when", "um", "the", "sunlight"]
        alignment = levenshtein_alignment(expected_norm, observed_norm)

        # Pause between 'when' (idx 0) and 'um' (idx 1 - insertion)
        cat = classify_pause_position(
            observed_idx=1,
            alignment=alignment,
            expected_tokens_raw=expected_raw,
        )
        assert cat == "unknown"

    def test_deletion_with_punctuation_preserves_boundary(self):
        """If participant skipped 'air,' (which has a comma) and said 'the they',
        the gap spans a deleted punctuation mark.
        """
        raw_passage = "in the air, they act"
        expected_raw = raw_passage.split()
        expected_norm = normalize_tokens(raw_passage)

        # Observed skipped 'air':
        observed_norm = ["in", "the", "they", "act"]
        alignment = levenshtein_alignment(expected_norm, observed_norm)

        # Pause between 'the' (idx 1) and 'they' (idx 2)
        cat = classify_pause_position(
            observed_idx=2,
            alignment=alignment,
            expected_tokens_raw=expected_raw,
        )
        assert cat == "punctuation_adjacent"

    def test_empty_or_degenerate_inputs(self):
        assert classify_pause_position(0, [], ["hello"]) == "unknown"
        assert classify_pause_position(1, [], []) == "within_clause"


def test_raw_punctuation_only_token_preserves_lexical_boundary_indices():
    text = 'hello ... world again'
    alignment = levenshtein_alignment(normalize_tokens(text), ['hello','world','again'])
    assert classify_pause_position(1,alignment,text.split()) == 'punctuation_adjacent'
    assert classify_pause_position(2,alignment,text.split()) == 'within_clause'
