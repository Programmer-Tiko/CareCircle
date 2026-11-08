"""Comparable-phrase verification and word-level pause localization.

Experimental module — Antigravity's contribution to the VoiceRadial/Cadence
pipeline. Verifies that a recording contains the expected passage and
localizes inter-word pauses for interpretable reporting.

Design constraints (from ANTIGRAVITY-TASK.md & ANTIGRAVITY-REVIEW-FIXES.md):
 - Separate model-derived observations (ASR transcription + word timestamps)
   from the deterministic phrase-comparison and alignment logic built here.
 - The ASR/aligner is injectable: tests use deterministic fakes, live use
   plugs in a real local model.
 - Never interpret ASR confidence or mismatch as Parkinson's severity.
 - Never download multi-GB weights during ordinary tests.
 - Keep large optional dependencies out of core API startup.
 - Validates model outputs and configuration against NaN/infinity/invalid values.
 - Position-aware pause classification via Levenshtein alignment backtrace.
"""
from __future__ import annotations

import math
import re
import string
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence

from app.audio.alignment_validation import (
    TimestampValidity,
    TranscriptionValidity,
    normalize_unicode,
    validate_expected_passage,
    validate_thresholds,
    validate_transcription,
    validate_word_timestamp,
)
from app.audio.pause_classification import (
    AlignOp,
    classify_pause_position,
    levenshtein_alignment,
)
from app.passage import PASSAGE_TEXT


# ---------------------------------------------------------------------------
# Transcriber/aligner contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WordTimestamp:
    """A single word with its time boundaries and recognition confidence.

    Contract:
      - word: the recognized text token (may include punctuation attached by
        the ASR model — the alignment code normalizes separately).
      - start: onset time in seconds from recording start.
      - end:   offset time in seconds from recording start.
      - confidence: 0.0–1.0 recognition confidence for this word. The aligner
        MUST emit a numeric value; use 0.0 if the model provides no per-word
        confidence rather than omitting the field.

    Timestamps must be finite and nonnegative with start <= end. Pathological
    ASR outputs can violate this — the alignment code handles nonmonotonic
    or invalid timestamps explicitly.
    """
    word: str
    start: float
    end: float
    confidence: float


@dataclass(frozen=True)
class TranscriptionResult:
    """Output of a transcriber/aligner callable.

    Fields:
      - words: per-word timestamps; empty list means the model returned no
        speech (silence, noise-only, etc.).
      - overall_confidence: aggregate model confidence for the entire
        transcription. 0.0 for empty/silent input.
      - model_id: identifier string for the model that produced this result,
        e.g. "whisper-large-v3", "injected-test-stub". Used in provenance
        reporting, never for logic branching.
    """
    words: list[WordTimestamp]
    overall_confidence: float
    model_id: str


# Type alias for the injectable transcriber/aligner callable.
# Signature: (wav_path: str) -> TranscriptionResult
TranscriberCallable = Callable[[str], TranscriptionResult]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

# Punctuation table for stripping — keep apostrophes inside contractions
_PUNCT_STRIP = str.maketrans("", "", string.punctuation.replace("'", ""))


def normalize_token(token: str) -> str:
    """Lowercase, normalize Unicode punctuation, strip outer punctuation, collapse whitespace."""
    t = normalize_unicode(token).strip().lower()
    t = t.translate(_PUNCT_STRIP)
    # strip leading/trailing apostrophes (but keep internal: don't → don't)
    t = t.strip("'")
    return t


def normalize_tokens(text: str) -> list[str]:
    """Split text into normalized tokens, dropping empties."""
    return [t for t in (normalize_token(w) for w in text.split()) if t]


def _expected_tokens_raw(text: str) -> list[str]:
    """Keep raw punctuation while sharing normalized-token indices.

    Standalone punctuation belongs to the preceding lexical word's boundary;
    leading standalone punctuation attaches to the next lexical word.
    """
    raw_tokens: list[str] = []
    leading = ''
    for token in normalize_unicode(text).split():
        if normalize_token(token):
            raw_tokens.append(leading + token)
            leading = ''
        elif raw_tokens:
            raw_tokens[-1] += token
        else:
            leading += token
    return raw_tokens


# ---------------------------------------------------------------------------
# Edit-distance alignment (word-level)
# ---------------------------------------------------------------------------

def _levenshtein_ops(
    expected: Sequence[str], observed: Sequence[str]
) -> tuple[int, int, int]:
    """Compute word-level Levenshtein edit counts: (substitutions, insertions, deletions).

    Delegates to full Levenshtein alignment for consistency.
    """
    alignment = levenshtein_alignment(expected, observed)
    subs = sum(1 for a in alignment if a.op == "substitution")
    ins = sum(1 for a in alignment if a.op == "insertion")
    dels = sum(1 for a in alignment if a.op == "deletion")
    return subs, ins, dels


# ---------------------------------------------------------------------------
# Pause localization
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PauseEvent:
    """A detected pause between two words.

    Fields:
      - before_word: the word token immediately before the pause.
      - after_word:  the word token immediately after the pause.
      - duration:    pause duration in seconds (None or 0.0 when unavailable/invalid).
      - position:    index into the lexical word list (empty/punctuation-only
                     ASR emissions excluded; pause is between word[position-1]
                     and word[position]).
      - category:    'punctuation_adjacent' if the pause occurs next to a
                     natural clause boundary in the *expected* passage;
                     'within_clause' if strictly within a clause;
                     'unknown' if flanking tokens are unaligned/ambiguous.
      - provenance:  'measured' for normal timestamp-derived pauses;
                     'nonmonotonic_boundary' for pauses at nonmonotonic
                     timestamp transitions (duration set to 0.0);
                     'invalid_timestamp' when word boundaries contain NaN/invalid
                     numbers (duration set to 0.0).
    """
    before_word: str
    after_word: str
    duration: float
    position: int
    category: str  # 'punctuation_adjacent' | 'within_clause' | 'unknown'
    provenance: str  # 'measured' | 'nonmonotonic_boundary' | 'invalid_timestamp'


def _is_punctuation_adjacent(
    before_raw: str, after_raw: str, expected_tokens_raw: list[str] | None
) -> bool:
    """Legacy helper maintained for backward compatibility.

    Prefer `classify_pause_position` which is position-aware and uses the
    Levenshtein alignment to avoid cross-occurrence punctuation pollution.
    """
    if not expected_tokens_raw:
        return False
    from app.audio.pause_classification import _TRAILING_PUNCT_RE, _LEADING_PUNCT_RE
    if _TRAILING_PUNCT_RE.search(before_raw) or _LEADING_PUNCT_RE.search(after_raw):
        return True
    return False


def localize_pauses(
    words: list[WordTimestamp],
    expected_text: str | None = None,
    pause_threshold: float = 0.15,
    alignment: list[AlignOp] | None = None,
) -> list[PauseEvent]:
    """Detect inter-word pauses from word timestamps.

    Args:
        words: List of WordTimestamp from the aligner.
        expected_text: The expected passage text. None means all pauses are
            classified as 'within_clause'.
        pause_threshold: Minimum gap (seconds) between consecutive words to
            count as a pause.
        alignment: Optional precomputed Levenshtein alignment ops.

    Returns:
        List of PauseEvent, one per detected inter-word pause.
    """
    # DP alignment and pause positions must use the same lexical-word list.
    # Empty/punctuation-only ASR emissions are not lexical word boundaries.
    words = [w for w in words if isinstance(w.word, str) and normalize_token(w.word)]
    if len(words) < 2:
        return []

    expected_raw = _expected_tokens_raw(expected_text) if expected_text else None

    # If alignment not supplied and expected_text is present, compute it
    if alignment is None and expected_text:
        expected_norm = normalize_tokens(expected_text)
        observed_norm = [normalize_token(w.word) for w in words if normalize_token(w.word)]
        alignment = levenshtein_alignment(expected_norm, observed_norm)

    events: list[PauseEvent] = []

    for i in range(1, len(words)):
        prev = words[i - 1]
        curr = words[i]

        # Validate timestamps on both words
        prev_valid = (
            math.isfinite(prev.start) and math.isfinite(prev.end) and
            prev.start >= 0 and prev.end >= 0 and prev.start <= prev.end
        )
        curr_valid = (
            math.isfinite(curr.start) and math.isfinite(curr.end) and
            curr.start >= 0 and curr.end >= 0 and curr.start <= curr.end
        )

        category = (
            classify_pause_position(i, alignment, expected_raw)
            if (alignment and expected_raw)
            else "within_clause"
        )

        if not (prev_valid and curr_valid):
            # Invalid timestamps: record boundary with invalid_timestamp provenance,
            # never fabricate a measured duration
            events.append(PauseEvent(
                before_word=prev.word,
                after_word=curr.word,
                duration=0.0,
                position=i,
                category=category,
                provenance="invalid_timestamp",
            ))
            continue

        gap = curr.start - prev.end

        if gap < 0:
            # Nonmonotonic timestamps — record the boundary with 0.0 duration
            events.append(PauseEvent(
                before_word=prev.word,
                after_word=curr.word,
                duration=0.0,
                position=i,
                category=category,
                provenance="nonmonotonic_boundary",
            ))
        elif gap >= pause_threshold:
            events.append(PauseEvent(
                before_word=prev.word,
                after_word=curr.word,
                duration=round(gap, 4),
                position=i,
                category=category,
                provenance="measured",
            ))

    return events


# ---------------------------------------------------------------------------
# Phrase match status
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhraseMatchResult:
    """Phrase verification and pause localization result.

    This is the top-level return type of `verify_phrase()`. It bundles:
    - Token-level comparison (expected vs. observed, edit counts, WER).
    - Phrase-match status with explicit weak-confidence / empty handling.
    - Word-level pause events with clause-boundary classification.
    - Recording quality/provenance metadata.

    IMPORTANT: The `mismatch_score` is an ASR-disagreement measure, NOT a
    patient cognitive accuracy score. Accent, background noise, and ASR
    recognition errors can all inflate it. Never interpret this as
    Parkinson's severity.

    Note: `mismatch_score` is a bounded WER-style disagreement score in [0.0, 1.0].
    Standard uncapped WER can exceed 1.0; here it is capped at 1.0.
    """
    # Token comparison
    expected_tokens: list[str]
    observed_tokens: list[str]
    substitutions: int
    insertions: int
    deletions: int
    mismatch_score: float  # Bounded WER-style: min((S + I + D) / len(expected), 1.0)

    # Phrase match status
    phrase_match: str  # 'matched' | 'mismatch' | 'uncertain'
    phrase_match_reason: str  # human-readable explanation

    # Pause localization
    pause_events: list[PauseEvent]
    alignment_available: bool  # False when timestamps are corrupt or words list is empty
    word_timestamps: list[WordTimestamp]

    # Recording quality / provenance
    model_id: str
    overall_confidence: float
    limitations: list[str]


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

MATCH_WER_THRESHOLD = 0.15
MISMATCH_WER_THRESHOLD = 0.50
LOW_CONFIDENCE_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def verify_phrase(
    wav_path: str,
    transcriber: TranscriberCallable,
    expected_passage: str = PASSAGE_TEXT,
    match_threshold: float = MATCH_WER_THRESHOLD,
    mismatch_threshold: float = MISMATCH_WER_THRESHOLD,
    confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    pause_threshold: float = 0.15,
) -> PhraseMatchResult:
    """Verify that a recording contains the expected passage and localize pauses.

    Args:
        wav_path: Path to the WAV recording.
        transcriber: Injectable transcriber/aligner callable.
        expected_passage: The expected passage text (default: Rainbow Passage).
        match_threshold: WER at or below which we call the phrase 'matched'.
        mismatch_threshold: WER at or above which we call it 'mismatch'.
        confidence_threshold: Overall confidence below which we report
            'uncertain' regardless of WER.
        pause_threshold: Minimum inter-word gap (seconds) to count as a pause.

    Returns:
        PhraseMatchResult with all structured evidence.

    Raises:
        ValueError: If thresholds are invalid or expected_passage is empty/degenerate.

    Notes:
        - This function NEVER interprets results as clinical severity.
        - It NEVER downloads model weights.
    """
    # Validate caller configuration
    validate_thresholds(
        match_threshold=match_threshold,
        mismatch_threshold=mismatch_threshold,
        confidence_threshold=confidence_threshold,
        pause_threshold=pause_threshold,
    )
    validate_expected_passage(expected_passage)

    # Get transcription
    result = transcriber(wav_path)
    limitations: list[str] = []

    # Validate transcription evidence
    validity = validate_transcription(result)
    limitations.extend(validity.issues)

    expected_norm = normalize_tokens(expected_passage)
    words = [w for w in result.words if isinstance(w.word, str) and normalize_token(w.word)]
    observed_norm = [normalize_token(w.word) for w in words]
    if len(words) != len(result.words):
        limitations.append('Empty or punctuation-only ASR tokens excluded from lexical alignment.')

    # Handle unusable or empty transcript
    if not validity.transcript_usable or not observed_norm:
        return PhraseMatchResult(
            expected_tokens=expected_norm,
            observed_tokens=[],
            substitutions=0,
            insertions=0,
            deletions=len(expected_norm),
            mismatch_score=1.0,
            phrase_match="uncertain",
            phrase_match_reason=(
                "No usable speech detected in recording. This may indicate silence, "
                "background noise only, or an ASR model failure — not necessarily "
                "that the participant did not speak."
            ),
            pause_events=[],
            alignment_available=False,
            word_timestamps=[],
            model_id=result.model_id,
            overall_confidence=result.overall_confidence if math.isfinite(result.overall_confidence) else 0.0,
            limitations=[
                "Empty or unusable transcription — cannot verify passage or localize pauses."
            ] + limitations,
        )

    # Compute full Levenshtein alignment
    alignment = levenshtein_alignment(expected_norm, observed_norm)
    subs = sum(1 for a in alignment if a.op == "substitution")
    ins = sum(1 for a in alignment if a.op == "insertion")
    dels = sum(1 for a in alignment if a.op == "deletion")
    total_edits = subs + ins + dels

    # Bounded WER-style mismatch score
    wer = min(total_edits / max(len(expected_norm), 1), 1.0)

    # Localize pauses using alignment
    pause_events = localize_pauses(
        words,
        expected_text=expected_passage,
        pause_threshold=pause_threshold,
        alignment=alignment,
    )

    # Check alignment availability: requires usable timestamps
    alignment_available = validity.alignment_usable and len(words) > 0

    # Check for nonmonotonic timestamps
    nonmono_count = sum(
        1 for e in pause_events if e.provenance == "nonmonotonic_boundary"
    )
    if nonmono_count > 0:
        limitations.append(
            f"{nonmono_count} nonmonotonic timestamp boundary(ies) detected — "
            f"some pause durations are unreliable."
        )

    # Check for invalid timestamps
    invalid_ts_count = sum(
        1 for e in pause_events if e.provenance == "invalid_timestamp"
    )
    if invalid_ts_count > 0:
        limitations.append(
            f"{invalid_ts_count} invalid timestamp boundary(ies) detected — "
            f"pause alignment is compromised."
        )

    # Check per-word confidence
    low_conf_words = [
        w for w in result.words
        if math.isfinite(w.confidence) and w.confidence < confidence_threshold
    ]
    if low_conf_words:
        limitations.append(
            f"{len(low_conf_words)} of {len(result.words)} words have confidence "
            f"below {confidence_threshold:.2f} — WER may overstate actual errors."
        )

    # Determine phrase_match status
    phrase_match: str
    phrase_match_reason: str

    # Guard: if overall_confidence is invalid (NaN/inf) or below threshold
    if not validity.confidence_usable or result.overall_confidence < confidence_threshold:
        phrase_match = "uncertain"
        conf_str = f"{result.overall_confidence:.2f}" if math.isfinite(result.overall_confidence) else repr(result.overall_confidence)
        phrase_match_reason = (
            f"Overall transcription confidence ({conf_str}) "
            f"is invalid or below threshold ({confidence_threshold:.2f}). The passage may "
            f"have been read correctly, but the recording quality or ASR model "
            f"confidence is too low to verify reliably."
        )
        limitations.append(
            "Low or invalid overall confidence — phrase match determination is unreliable."
        )
    elif wer <= match_threshold:
        phrase_match = "matched"
        phrase_match_reason = (
            f"WER {wer:.3f} is at or below match threshold ({match_threshold:.2f}). "
            f"The recording closely matches the expected passage."
        )
    elif wer >= mismatch_threshold:
        phrase_match = "mismatch"
        phrase_match_reason = (
            f"WER {wer:.3f} is at or above mismatch threshold ({mismatch_threshold:.2f}). "
            f"The recording does not match the expected passage. This could "
            f"indicate a different passage was read, significant background noise, "
            f"or ASR recognition errors — not necessarily a clinical finding."
        )
    else:
        phrase_match = "uncertain"
        phrase_match_reason = (
            f"WER {wer:.3f} is between match ({match_threshold:.2f}) and mismatch "
            f"({mismatch_threshold:.2f}) thresholds. Some word-level differences "
            f"were detected but the overall reading is partially recognizable. "
            f"Consider re-recording if this is unexpected."
        )

    return PhraseMatchResult(
        expected_tokens=expected_norm,
        observed_tokens=observed_norm,
        substitutions=subs,
        insertions=ins,
        deletions=dels,
        mismatch_score=round(wer, 4),
        phrase_match=phrase_match,
        phrase_match_reason=phrase_match_reason,
        pause_events=pause_events,
        alignment_available=alignment_available,
        word_timestamps=words,
        model_id=result.model_id,
        overall_confidence=result.overall_confidence if math.isfinite(result.overall_confidence) else 0.0,
        limitations=limitations,
    )


# ---------------------------------------------------------------------------
# Optional: real ASR transcriber
# ---------------------------------------------------------------------------

def make_whisper_transcriber(
    model_size: str = "base",
) -> TranscriberCallable:
    """Create a cached-only transcriber backed by OpenAI Whisper.

    Delegates to :class:`app.audio.whisper_adapter.CachedWhisperTranscriber`.
    Does not download weights. Raises FileNotFoundError if model is not cached.
    """
    from app.audio.whisper_adapter import CachedWhisperTranscriber
    return CachedWhisperTranscriber(model_size=model_size)
