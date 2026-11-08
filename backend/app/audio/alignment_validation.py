"""Validation helpers for word-level alignment evidence.

These functions catch pathological ASR outputs — NaN timestamps, infinite
confidence, negative durations, empty words, and Unicode normalization gaps —
before they silently pass through the phrase-matching pipeline.

Key bug motivation: ``WordTimestamp("hello", float('nan'), -1, float('nan'))``
with ``overall_confidence=float('nan')`` previously yielded
``phrase_match='matched'`` because Python NaN comparisons are always False,
so all threshold checks passed vacuously.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.audio.phrase_alignment import TranscriptionResult, WordTimestamp


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimestampValidity:
    """Validation result for a single WordTimestamp."""

    text_usable: bool  # word text is non-empty after stripping whitespace
    timestamps_usable: bool  # start and end are finite, nonneg, start <= end
    confidence_usable: bool  # confidence is finite and in [0.0, 1.0]
    issues: list[str]  # human-readable list of problems found


@dataclass(frozen=True)
class TranscriptionValidity:
    """Validation result for an entire TranscriptionResult."""

    transcript_usable: bool  # at least one word has usable text
    alignment_usable: bool  # all words with usable text also have usable timestamps
    confidence_usable: bool  # overall_confidence is finite and in [0.0, 1.0]
    usable_word_count: int
    total_word_count: int
    issues: list[str]


# ---------------------------------------------------------------------------
# Per-word validation
# ---------------------------------------------------------------------------

def _is_finite_and_in_range(
    value: float, lo: float, hi: float
) -> bool:
    """Return True iff *value* is finite and lo <= value <= hi."""
    return math.isfinite(value) and lo <= value <= hi


def validate_word_timestamp(wt: WordTimestamp) -> TimestampValidity:
    """Validate a single :class:`WordTimestamp`.

    Checks:
    - word is a non-empty string after stripping whitespace.
    - start is finite and >= 0.
    - end is finite and >= 0.
    - start <= end (equal is OK for instantaneous tokens).
    - confidence is finite and in [0.0, 1.0].
    - NaN, infinity, and negative values are ALL invalid.
    """
    issues: list[str] = []

    # --- text ---
    from app.audio.phrase_alignment import normalize_token
    text_usable = isinstance(wt.word, str) and bool(normalize_token(wt.word))
    if not text_usable:
        issues.append("word text is empty or whitespace-only")

    # --- timestamps ---
    timestamps_usable = True

    if not math.isfinite(wt.start):
        timestamps_usable = False
        issues.append(f"start is not finite ({wt.start!r})")
    elif wt.start < 0:
        timestamps_usable = False
        issues.append(f"start is negative ({wt.start!r})")

    if not math.isfinite(wt.end):
        timestamps_usable = False
        issues.append(f"end is not finite ({wt.end!r})")
    elif wt.end < 0:
        timestamps_usable = False
        issues.append(f"end is negative ({wt.end!r})")

    # start <= end (only check when both are individually valid)
    if timestamps_usable and wt.start > wt.end:
        timestamps_usable = False
        issues.append(f"start ({wt.start}) > end ({wt.end})")

    # --- confidence ---
    confidence_usable = _is_finite_and_in_range(wt.confidence, 0.0, 1.0)
    if not confidence_usable:
        issues.append(f"confidence is not in [0.0, 1.0] or not finite ({wt.confidence!r})")

    return TimestampValidity(
        text_usable=text_usable,
        timestamps_usable=timestamps_usable,
        confidence_usable=confidence_usable,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Transcription-level validation
# ---------------------------------------------------------------------------

def validate_transcription(result: TranscriptionResult) -> TranscriptionValidity:
    """Validate an entire :class:`TranscriptionResult`.

    - ``overall_confidence`` must be finite and in [0.0, 1.0]; NaN → not usable.
    - Transcript text may be usable even when timestamps are not.
    - If ALL per-word confidences are 0.0, a warning is flagged.
    - Invalid individual word timestamps do not invalidate the whole
      transcript for text purposes.
    """
    issues: list[str] = []
    total = len(result.words)

    # overall confidence
    confidence_usable = _is_finite_and_in_range(
        result.overall_confidence, 0.0, 1.0,
    )
    if not confidence_usable:
        issues.append(
            f"overall_confidence is not in [0.0, 1.0] or not finite "
            f"({result.overall_confidence!r})"
        )

    # per-word validation
    usable_word_count = 0
    alignment_usable = True  # optimistic until proven otherwise

    previous_end: float | None = None
    per_word_validities: list[TimestampValidity] = []
    for wt in result.words:
        v = validate_word_timestamp(wt)
        per_word_validities.append(v)
        if v.text_usable:
            usable_word_count += 1
            if not v.timestamps_usable:
                alignment_usable = False
            else:
                if previous_end is not None and wt.start < previous_end:
                    alignment_usable = False
                    issues.append('word timestamps overlap or run backwards across lexical words')
                previous_end = wt.end

    transcript_usable = usable_word_count > 0
    if not transcript_usable:
        issues.append("no words with usable text")

    if total > 0 and not alignment_usable:
        issues.append(
            "one or more words with usable text have unusable timestamps"
        )

    # Edge case: no usable-text words → alignment is trivially not usable
    if not transcript_usable:
        alignment_usable = False

    # All zero confidences warning
    if total > 0 and all(wt.confidence == 0.0 for wt in result.words):
        issues.append(
            "all word confidences zero — model may not provide per-word confidence"
        )

    # Propagate individual-word issues (condensed)
    for i, v in enumerate(per_word_validities):
        for iss in v.issues:
            issues.append(f"word[{i}] ({result.words[i].word!r}): {iss}")

    return TranscriptionValidity(
        transcript_usable=transcript_usable,
        alignment_usable=alignment_usable,
        confidence_usable=confidence_usable,
        usable_word_count=usable_word_count,
        total_word_count=total,
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Threshold validation
# ---------------------------------------------------------------------------

def validate_thresholds(
    match_threshold: float,
    mismatch_threshold: float,
    confidence_threshold: float,
    pause_threshold: float,
) -> None:
    """Raise :exc:`ValueError` if any threshold is invalid.

    Rules:
    - All thresholds must be finite (no NaN, no infinity).
    - ``match_threshold`` must be in [0, 1].
    - ``mismatch_threshold`` must be in [0, 1].
    - ``match_threshold < mismatch_threshold`` (strict).
    - ``confidence_threshold`` must be in [0, 1].
    - ``pause_threshold`` must be >= 0.
    """
    _assert_finite("match_threshold", match_threshold)
    _assert_finite("mismatch_threshold", mismatch_threshold)
    _assert_finite("confidence_threshold", confidence_threshold)
    _assert_finite("pause_threshold", pause_threshold)

    if not (0.0 <= match_threshold <= 1.0):
        raise ValueError(
            f"match_threshold must be in [0, 1], got {match_threshold}"
        )
    if not (0.0 <= mismatch_threshold <= 1.0):
        raise ValueError(
            f"mismatch_threshold must be in [0, 1], got {mismatch_threshold}"
        )
    if match_threshold >= mismatch_threshold:
        raise ValueError(
            f"match_threshold ({match_threshold}) must be strictly less than "
            f"mismatch_threshold ({mismatch_threshold})"
        )
    if not (0.0 <= confidence_threshold <= 1.0):
        raise ValueError(
            f"confidence_threshold must be in [0, 1], got {confidence_threshold}"
        )
    if pause_threshold < 0.0:
        raise ValueError(
            f"pause_threshold must be >= 0, got {pause_threshold}"
        )


def _assert_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


# ---------------------------------------------------------------------------
# Expected-passage validation
# ---------------------------------------------------------------------------

def validate_expected_passage(text: str) -> None:
    """Raise :exc:`ValueError` if *text* is not a usable expected passage.

    Checks:
    - text is not None (raises TypeError naturally, but we give a clear msg).
    - text is not empty or whitespace-only.
    - text normalizes to at least one token.
    """
    if text is None:
        raise ValueError("expected passage text must not be None")
    if not isinstance(text, str):
        raise ValueError(
            f"expected passage text must be a str, got {type(text).__name__}"
        )
    if not text.strip():
        raise ValueError("expected passage text is empty or whitespace-only")

    # Import locally to avoid circular dependency issues at module level
    from app.audio.phrase_alignment import normalize_tokens

    tokens = normalize_tokens(text)
    if not tokens:
        raise ValueError(
            "expected passage text normalizes to zero tokens "
            f"(original: {text!r})"
        )


# ---------------------------------------------------------------------------
# Unicode normalization
# ---------------------------------------------------------------------------

# Mapping table for common Unicode punctuation → ASCII equivalents
_UNICODE_REPLACE: list[tuple[str, str]] = [
    # Curly / smart single quotes → ASCII apostrophe
    ("\u2018", "'"),  # LEFT SINGLE QUOTATION MARK
    ("\u2019", "'"),  # RIGHT SINGLE QUOTATION MARK
    ("\u201a", "'"),  # SINGLE LOW-9 QUOTATION MARK
    # Curly / smart double quotes → ASCII double quote
    ("\u201c", '"'),  # LEFT DOUBLE QUOTATION MARK
    ("\u201d", '"'),  # RIGHT DOUBLE QUOTATION MARK
    ("\u201e", '"'),  # DOUBLE LOW-9 QUOTATION MARK
    # Dashes → ASCII hyphen-minus
    ("\u2014", "-"),  # EM DASH
    ("\u2013", "-"),  # EN DASH
    ("\u2012", "-"),  # FIGURE DASH
    ("\u2015", "-"),  # HORIZONTAL BAR
    # Ellipsis → three dots
    ("\u2026", "..."),  # HORIZONTAL ELLIPSIS
    # Other common Unicode punctuation
    ("\u00b7", "."),  # MIDDLE DOT
    ("\u2022", "."),  # BULLET
    ("\u2010", "-"),  # HYPHEN
    ("\u2011", "-"),  # NON-BREAKING HYPHEN
    ("\u00ad", ""),   # SOFT HYPHEN (remove entirely)
    ("\u200b", ""),   # ZERO WIDTH SPACE
    ("\u200c", ""),   # ZERO WIDTH NON-JOINER
    ("\u200d", ""),   # ZERO WIDTH JOINER
    ("\ufeff", ""),   # BYTE ORDER MARK / ZERO WIDTH NO-BREAK SPACE
]

# Build a translation table for single-char replacements and a list for
# multi-char replacements (like ellipsis → "...")
_UNICODE_TRANS = str.maketrans(
    {src: dst for src, dst in _UNICODE_REPLACE if len(dst) <= 1}
)
_UNICODE_MULTI = [(src, dst) for src, dst in _UNICODE_REPLACE if len(dst) > 1]


def normalize_unicode(text: str) -> str:
    """Normalize Unicode characters that affect token comparison.

    This function should be called BEFORE ``normalize_token()`` in the
    phrase-alignment pipeline so that curly quotes, em-dashes, etc. are
    mapped to their ASCII equivalents before punctuation stripping.

    Replacements:
    - Curly/smart quotes (single and double) → ASCII equivalents
    - Em-dash (U+2014) and en-dash (U+2013) → ASCII hyphen-minus
    - Horizontal ellipsis (U+2026) → ``...``
    - Various zero-width and invisible characters → removed
    """
    # Multi-char replacements first (e.g., ellipsis → "...")
    for src, dst in _UNICODE_MULTI:
        text = text.replace(src, dst)
    # Single-char replacements via translate table
    text = text.translate(_UNICODE_TRANS)
    return text
