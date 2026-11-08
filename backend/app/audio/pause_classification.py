"""Position-aware pause classification using Levenshtein alignment.

Fixes critical bugs in the original ``_is_punctuation_adjacent`` helper:
1. Searching all expected tokens caused words appearing multiple times
   (e.g. "rainbow" in the Rainbow Passage) to incorrectly inherit punctuation
   from other occurrences.
2. Checking any punctuation on the word after the pause caused pauses BEFORE
   "air," to be treated as punctuation-adjacent, even though the comma is
   trailing (boundary after "air,").

This module provides:
  - ``levenshtein_alignment``: full Levenshtein DP with backtrace returning
    per-operation alignment mappings.
  - ``classify_pause_position``: uses the alignment to check only the
    boundary between the specific expected tokens flanking the pause.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


# ---------------------------------------------------------------------------
# Alignment data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AlignOp:
    """A single alignment operation from the Levenshtein backtrace.

    Attributes:
        op: One of ``'match'``, ``'substitution'``, ``'insertion'``,
            ``'deletion'``.
        expected_idx: Index into the *expected* token list. ``None`` for
            insertions (the observed word has no expected counterpart).
        observed_idx: Index into the *observed* token list. ``None`` for
            deletions (an expected word was skipped).
    """
    op: str  # 'match' | 'substitution' | 'insertion' | 'deletion'
    expected_idx: int | None
    observed_idx: int | None


# ---------------------------------------------------------------------------
# Levenshtein alignment with full backtrace
# ---------------------------------------------------------------------------

def levenshtein_alignment(
    expected: Sequence[str],
    observed: Sequence[str],
) -> list[AlignOp]:
    """Compute word-level Levenshtein alignment with a full backtrace.

    Args:
        expected: Normalised expected tokens.
        observed: Normalised observed (ASR) tokens.

    Returns:
        A list of :class:`AlignOp` in passage order (left to right).
    """
    n, m = len(expected), len(observed)
    INF = float("inf")

    # dp[i][j] = (cost, op_label)
    dp: list[list[tuple[float, str]]] = [
        [(INF, "")] * (m + 1) for _ in range(n + 1)
    ]
    dp[0][0] = (0, "")
    for i in range(1, n + 1):
        dp[i][0] = (i, "D")
    for j in range(1, m + 1):
        dp[0][j] = (j, "I")

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if expected[i - 1] == observed[j - 1]:
                candidates = [(dp[i - 1][j - 1][0], "M")]
            else:
                candidates = [(dp[i - 1][j - 1][0] + 1, "S")]
            candidates.append((dp[i - 1][j][0] + 1, "D"))
            candidates.append((dp[i][j - 1][0] + 1, "I"))
            dp[i][j] = min(candidates, key=lambda c: c[0])

    # Backtrace — collect in reverse then flip.
    ops_rev: list[AlignOp] = []
    i, j = n, m
    while i > 0 or j > 0:
        _, op = dp[i][j]
        if op == "M":
            ops_rev.append(AlignOp("match", i - 1, j - 1))
            i -= 1
            j -= 1
        elif op == "S":
            ops_rev.append(AlignOp("substitution", i - 1, j - 1))
            i -= 1
            j -= 1
        elif op == "D":
            ops_rev.append(AlignOp("deletion", i - 1, None))
            i -= 1
        elif op == "I":
            ops_rev.append(AlignOp("insertion", None, j - 1))
            j -= 1
        else:
            break  # origin reached

    ops_rev.reverse()
    return ops_rev


# ---------------------------------------------------------------------------
# Punctuation regexes — covers ASCII and Unicode dashes
# ---------------------------------------------------------------------------

# Trailing punctuation on token before pause (e.g. "air,", "rainbow.", "end!")
_TRAILING_PUNCT_RE = re.compile(r"[,;:.!?\-\u2014\u2013]+['\"]*$")

# Leading punctuation on token after pause (e.g. "--start", "-and")
_LEADING_PUNCT_RE = re.compile(r"^['\"]*[,;:.!?\-\u2014\u2013]+")

# Any clause punctuation in a deleted token
_ANY_CLAUSE_PUNCT_RE = re.compile(r"[,;:.!?\-\u2014\u2013]")


# ---------------------------------------------------------------------------
# Position-aware pause classification
# ---------------------------------------------------------------------------

def classify_pause_position(
    observed_idx: int,
    alignment: list[AlignOp],
    expected_tokens_raw: list[str],
) -> str:
    """Classify a pause as punctuation-adjacent, within-clause, or unknown.

    The ``observed_idx`` is the index of the observed word **after** the pause
    (i.e. pause sits between ``observed_idx - 1`` and ``observed_idx``).

    Args:
        observed_idx: Index of the observed word immediately *after* the pause.
        alignment: Alignment ops returned by :func:`levenshtein_alignment`.
        expected_tokens_raw: The raw (un-normalised) expected passage tokens
            (``passage_text.split()``).

    Returns:
        ``'punctuation_adjacent'``, ``'within_clause'``, or ``'unknown'``.

    Rules:
    - Punctuation classification is derived EXCLUSIVELY from expected_tokens_raw.
      ASR-invented punctuation on observed words is ignored.
    - If either flanking observed word cannot be aligned to an expected token
      (e.g. insertion or out-of-order), returns ``'unknown'``.
    - Checks:
      1. Trailing punctuation on expected token before pause (e.g., "air, -> they")
      2. Leading punctuation on expected token after pause
      3. Any punctuation on intermediate deleted tokens (e.g., if "air," was deleted)
    - If none of the above match, returns ``'within_clause'``.
    """
    if observed_idx < 1:
        return "unknown"

    if not expected_tokens_raw:
        return "within_clause"

    # Alignment indices count lexical tokens only. Public callers may supply
    # raw split() tokens containing standalone punctuation; retain its boundary
    # without letting it shift the expected indices.
    from app.audio.phrase_alignment import _expected_tokens_raw
    expected_tokens_raw = _expected_tokens_raw(' '.join(expected_tokens_raw))

    # Map observed index → expected index for match/substitution ops.
    obs_to_exp: dict[int, int] = {}
    for a in alignment:
        if a.op in ("match", "substitution") and a.observed_idx is not None and a.expected_idx is not None:
            obs_to_exp[a.observed_idx] = a.expected_idx

    # Locate expected indices for the words flanking the pause.
    before_exp = obs_to_exp.get(observed_idx - 1)
    after_exp = obs_to_exp.get(observed_idx)

    # If either flanking word is an insertion / unmatched, boundary is ambiguous
    if before_exp is None or after_exp is None:
        return "unknown"

    # In a monotonic reading, before_exp < after_exp
    if before_exp >= after_exp:
        # Nonmonotonic or repeated token alignment anomaly
        return "unknown"

    # Check 1: Trailing punctuation on the expected token before the pause
    # (e.g. "air," in "in the air, they act")
    if 0 <= before_exp < len(expected_tokens_raw):
        raw_before = expected_tokens_raw[before_exp]
        if _TRAILING_PUNCT_RE.search(raw_before):
            return "punctuation_adjacent"

    # Check 2: Leading punctuation on the expected token after the pause
    if 0 <= after_exp < len(expected_tokens_raw):
        raw_after = expected_tokens_raw[after_exp]
        if _LEADING_PUNCT_RE.search(raw_after):
            return "punctuation_adjacent"

    # Check 3: Intermediate deleted tokens containing punctuation
    for del_idx in range(before_exp + 1, after_exp):
        if 0 <= del_idx < len(expected_tokens_raw):
            if _ANY_CLAUSE_PUNCT_RE.search(expected_tokens_raw[del_idx]):
                return "punctuation_adjacent"

    # Neither side has clause-boundary punctuation in the expected passage.
    return "within_clause"
