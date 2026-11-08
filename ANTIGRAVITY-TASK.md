# Antigravity: own phrase verification and word-level pause localization

Start now in the shared VoiceRadial workspace. Read VoiceShift-HANDOFF-TO-CODEX.md,
backend/app/passage.py, backend/app/audio/vad.py and backend/app/pipeline.py first.
Codex and two coding agents own experimental prosody extraction and the CCR
multisignal ablation runner. Do not edit their files or the API/schema/baseline.

## Deliver a working experimental module, not a proposal

Build `backend/app/audio/phrase_alignment.py` and
`backend/tests/test_phrase_alignment.py`. The contribution is comparable-phrase
verification and interpretable pause placement, not a new disease classifier.
Use an existing ASR/aligner if needed, but separate model-derived observations
from the deterministic phrase comparison and alignment code you build.

Input: WAV path, expected passage (default app.passage.PASSAGE_TEXT), and a
transcriber/aligner callable injectable for deterministic tests. Define its
word timestamp/confidence contract explicitly. Real implementation may use an
available local ASR model; keep large optional dependencies out of core API
startup. Never download multi-GB weights implicitly during ordinary tests.

Return structured evidence:
- normalized expected/observed tokens and edit counts, with WER-style mismatch
  score (an ASR disagreement measure, NOT patient cognitive accuracy);
- phrase_match status `matched | mismatch | uncertain`, with explicit handling
  of weak/no transcription confidence and empty/silent input;
- aligned word timestamps and within-clause vs punctuation-adjacent pause events,
  distinguishing unavailable alignment from a measured zero;
- recording quality/provenance and limitations.

Never interpret ASR confidence or errors as a Parkinson's severity score. Accent,
background noise and recognition mistakes can cause mismatch. Don't claim a
pause indicates word-finding difficulty. The useful action is asking whether
there was a distraction or an incomplete reading, or declining comparison when
capture conditions are not comparable.

Tests: exact passage, punctuation/case normalization, repeated/missing words,
wrong passage, low-confidence transcript, nonmonotonic timestamps, pauses at
punctuation vs inside a clause, and a real local consenting-demo/attributed-fixture
smoke run if a suitable ASR model is already available. Report provider/model
availability honestly; injectable tests alone are not a live-ASR verification.

Write `docs/ANTIGRAVITY-ALIGNMENT-RESULTS.md`: commands run, actual outputs,
remaining gaps and proposed integration contract. Keep the module experimental;
no automatic changes to the live trigger, reference data or patient text.
Coordinate via this file and the user's agent chat; do not overwrite teammate work.
