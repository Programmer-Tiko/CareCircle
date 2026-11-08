# Independent review of Antigravity CCR candidates

Date: November 8, 2026. Reviewed the actual six candidate records, their cited
local knowledge chunks, current retrieval implementation and direct eligibility
reproducers. No candidate has been promoted to the live corpus.

## Decisions

| Candidate | Decision | Required change |
| --- | --- | --- |
| vocal_fatigue_check | Revise before promotion | Shorten the multi-part question; gate on explicit reported voice/speech difficulty or vocal effort, not an assumed cause of a timing deviation. |
| vocal_quality_hoarseness | Revise before promotion | Hoarse/breathy wording is supported; either supply the separate strain excerpt (e.g. chunk 281) or remove strained. Make direct voice-quality reports reachable. |
| group_and_noise_communication | Revise before promotion | Distinguish environmental noise in daily conversations from interruption during this recording; current broad distraction exclusion can suppress the intended topic. |
| daytime_sleepiness_check | Block under proposed gate | Chunk 84 supports asking about sleepiness; it does not establish pause-fraction z>1.5 as a reason to suspect sleepiness. Require an explicit report of sleepiness, or an independently defined routine check-in policy. |
| fatigue_physical_vs_mental | Keep blocked / revise | Missing fatigue context extraction; allow both/other rather than implying physical versus mental fatigue is an exclusive binary. |
| morning_off_period_check | Keep blocked / revise | Verified medication use alone does not establish morning timing or medication effect. Ask timing neutrally, without combining medication and routine into an assumed mechanism. |

## Reproduced runtime gaps

- `compute_context_flags({}, ['I have no trouble speaking'])` sets the speech
  difficulty/motor flags true. Candidate eligibility therefore does not reliably
  establish acknowledged symptoms. This is an existing retrieval defect, not a
  defect introduced by adding these candidate files.
- `My voice feels hoarse` and `My voice gets tired by evening` do not set the
  speech-motor flag, so their corresponding candidate questions are unreachable.
- `People find it difficult to hear me in background noise` sets both speech
  difficulty and distraction; the proposed noise-context question is excluded.
  The current code checks literal 'noise', not 'noisy', so behavior also varies
  with paraphrase. Do not conflate room noise while reading with daily functional
  communication difficulties.
- `initial_answer_mentions_*` flags currently inspect only the latest answer;
  candidate documentation describes prior-turn context more broadly than code.
- `blocked` is candidate metadata; current `is_eligible()` does not read it.
  Separate proposal files are safe, but copying blocked records into the live
  corpus would not establish an explicit block by itself.

## Source provenance corrections

All six `source_excerpt` fields fail a literal single-chunk substring check
because they combine spans, use editorial ellipses and/or normalize typography.
That does not make all content unsupported, but calling them exact excerpts
without per-span provenance is inaccurate. Store `evidence_spans` with individual
chunk index, exact verbatim text, source URL and source version; verify each
span belongs to that source. Keep a separate readable evidence summary if useful.

`vocal_fatigue_check` cites chunk 2 (Parkinson's Foundation) alongside APDA
chunks while its single source URL identifies only APDA. Separate the sources.
`group_and_noise_communication` includes an excerpt continuation not present in
its two named chunks; add the actual originating chunk or remove that text.
The supplied hoarseness excerpt does not itself support the added word strained.

Source-topic coverage and review notes do not independently establish that every
one of the 311 chunks received full manual review. Describe exactly which source
ranges/decisions were inspected; do not elevate agent synthesis to clinical review.

## Next task for Antigravity

Revise the six proposal records and review documentation, keeping live corpus,
retrieval and API unchanged. Use separate parallel lanes for exact evidence-span
provenance, candidate wording/context rules, and adversarial review. Add proposed
eligibility cases with expected outcomes (affirmation, negation, uncertainty,
resolved past symptom, current recording interruption, everyday noisy-room
communication). Any runtime context-extraction change needs a separate reviewed
implementation. Codex owns that integration decision.

Prototype source review is not clinician approval. Existing deterministic
keyword flags are not sufficient proof that a patient confirmed a symptom.
