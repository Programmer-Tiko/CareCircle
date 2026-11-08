# Codex review: fix these before live integration

Confirmed by direct execution against the delivered module, not inferred from
its test count. Preserve the existing API/baseline and work only on your module,
tests and results doc. These are follow-up tasks under the original assignment.

1. Position-aware punctuation mapping. `_is_punctuation_adjacent` searches all
   expected occurrences of a word, so the second `rainbow` inherits punctuation
   from `rainbow.` at the end of sentence one. Reproducer:
   `localize_pauses([WordTimestamp('rainbow',0,.2,.9), WordTimestamp('is',.7,.9,.9)],
   'A rainbow. The rainbow is beautiful.')` returns punctuation_adjacent even
   though rainbow->is is inside the clause. Return the expected/observed index
   mapping from Levenshtein backtrace and classify the actual aligned boundary.
   If ambiguous/unmatched, return unknown instead of inventing clause placement.
   Punctuation before a word (a pause before air,) is not the same boundary as
   punctuation after it (air,->they). Test these separately.

2. Validate model outputs and configuration. A single WordTimestamp('hello',
   NaN,-1,NaN) with overall_confidence=NaN currently returns matched and
   alignment_available=True for expected 'hello'. Require finite in-range
   confidences, nonnegative finite times, start<=end, and valid thresholds.
   Separate transcript availability from usable timestamp alignment. Invalid
   durations must be unavailable, not measured zero. Handle per-word confidence
   unavailability explicitly; don't let overall confidence conceal all-zero
   word confidences. Validate empty expected passage as caller error.

3. Make the live smoke explicitly opt-in and cached-only. Merely importing
   whisper doesn't prove weights are cached: whisper.load_model('base') can
   download weights. Gate the smoke with an explicit environment opt-in and
   require an existing model file/local path before loading. Load once per
   transcriber instance, not once per audio request. Inject/fake the loader in
   tests to prove no downloads and one load for repeated transcriptions.

4. Add regressions for repeated tokens, insertion/deletion around punctuation,
   ASR-invented punctuation, invalid/NaN times and confidences, no expected text,
   Unicode apostrophes/dashes, and cached-only smoke. `normalize_token` currently
   handles ASCII punctuation only. Do not call the capped mismatch score standard
   uncapped WER; document it as a bounded WER-style disagreement score.

Codex reran your tests from backend/: keep recording the actual command and
result. Running only this test file from repo root currently fails to import
app; match existing path setup or document backend as the working directory.
No real-ASR end-to-end result has been verified yet. Don't claim it has.
