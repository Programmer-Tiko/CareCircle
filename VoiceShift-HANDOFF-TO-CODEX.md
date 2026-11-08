# Handoff: Codex, you are now driving this project

This file is a full context transfer. The user (building this with you now) was previously
working with me (Claude, in Claude Code) and is moving the driver's seat to you because of
token/limit pressure on my side. Read this whole file before touching anything. Treat it as if
I'm briefing a teammate who is about to take over mid-task — because that's exactly what this is.

Also read, in this order, for deeper background (this file is the fast-start; those are the
full record):
1. `VoiceShift-LOG.md` — running session log, chronological, has the "why" behind every pivot.
2. `VoiceShift-Project-Brief.md` — current state of the pitch/architecture doc (title: "Cadence").
3. `docs/` — whatever Codex-side docs already exist there (I have not audited this folder).

## What this project is

**Cadence** (repo/internal name still `VoiceShift` / `CareCircle` in places — naming not fully
unified yet, don't worry about it, functionality matters more for judging). A UB Hacking 2026
hackathon project, 3 people, targeting the **"Radial Atoms" track** (sponsor: Radial Ventures).
Rubric is Sense → Understand → Act, with explicit judging weight on "AI interacting with the
physical world" and "functional over complicated" — i.e. working demo beats clever slides.

**Product**: a daily voice check-in for people with **Parkinson's disease only** (scope was
narrowed from Parkinson's+COPD specifically for evidence-strength reasons — see research section
below). The person reads the same short passage every day. The system compares today's speech
timing to *that person's own historical baseline* (never population norms — this is a deliberate,
repeatedly-defended design choice). If a persistent deviation is found (not a one-off noisy
take), the system asks a **real LLM-driven, RAG-grounded follow-up question** instead of a
hardcoded one — selected from a small curated, sourced corpus, never freely generated.

## Why it's built this way (don't undo these without re-litigating with the user first)

These are decisions the user and I already fought through. Re-opening them wastes everyone's
time unless something has materially changed:

- **Personal baseline, not population ML, for the live trigger.** `personal_baseline.py` uses
  robust median/MAD z-scores fit on that person's own clean reference takes. This is deliberately
  *not* a trained ML model — it needs to be explainable or over-triggering on noisy
  voices/environments becomes an unactionable black box. There IS a separate ML research track
  (severity regression, CCR-trained classifiers) but it is explicitly **not** wired into the live
  trigger — it's a labeled-as-research side result, kept separate on purpose
  (`models/pd_severity_infer.py`, `models/train_pd_*.py`).
- **RAG selects, it does not generate.** The LLM (Groq, model `openai/gpt-oss-20b`) picks one
  question from a pre-vetted eligible set and is server-side validated afterward (eligible-set
  membership check, evidence-provenance check, verbatim-quote check). It is structurally
  incapable of inventing medical claims. This was the resolution to the user's repeated demand
  for "a real AI brain, not hardcoded logic" balanced against safety/explainability — do not
  relax the validation layer to make the demo "feel more AI."
- **The user explicitly rejects "we bolted together 4-5 pretrained things with no real
  differentiation."** The two things that count as genuine technical work by this team, which you
  should keep sharpening and should foreground in any demo/pitch copy:
  1. The RAG retrieval+selection+validation pipeline itself (`app/dialogue/*`) — this is actually
     built, not a wrapper.
  2. The **research finding that `mean_speech_segment_duration` is the single strongest acoustic
     correlate of Parkinson's severity** found anywhere in this project's own analysis (Spearman
     r=-0.80 vs Hoehn-Yahr stage in MDVR-KCL, beating pause_fraction's r=0.73). **Correction from
     my own earlier claim**: ItalianPVS B1 is same-direction but borderline (p=0.053, d=-0.60) —
     not a significant replication. Codex caught and fixed this in the code comment and brief;
     this file had the overclaim until this review pass. See Research section for the honest
     numbers. This was *this team's own result*, not copied from a paper, and it was just wired
     into the live detector (see
     "In-progress work" below — this is the task you're picking up).
- **CCR (the HPC cluster) must produce things that get used live, not performative compute-burning.**
  The user has twice pushed back hard when CCR work ("we have the compute, use it") produced
  results that were never actually wired into the running product. Don't run expensive jobs for
  the optics of having used the cluster — only run them if the output becomes a corpus unit, a
  validated finding, or a feature actually read by the live pipeline.
- **Never fabricate research numbers.** Every correlation/statistic in the brief and in code
  comments has been independently verified (permutation tests, caught leakage bugs, corrected a
  task-mislabeling in ItalianPVS). If you add a new number, verify it the same way — the user
  explicitly asked for "as accurate as possible," not impressive-sounding.

## Architecture (Sense → Understand → Act)

```
audio (wav) ──Sense──> VAD (Silero, real pretrained net) ──> speech segments
                              │
                              v
                     timing_features.py: pause_fraction, longest_internal_gap,
                     speaking_rate, mean_speech_segment_duration
                              │
Understand ───────────────────┘
      personal_baseline.py: robust z-score per feature vs this person's own
      history (median/MAD) → combined deviation_score (Euclidean norm)
      PersistentDeviationTracker: requires N consecutive elevated readings
      (not just one noisy take) before triggering anything
                              │
                              v (if persistent deviation)
Act ───────────────────────────
      Tier 1: deterministic emergency-keyword bypass (safety net, see
              contains_emergency_signal in retrieval.py) — short-circuits
              BEFORE any LLM call, has a test proving the model is never
              invoked for emergency content (test_emergency_safety.py)
      Tier 2: RAG question selection
        - retrieval.py: filter question_corpus.json units by condition,
          preconditions (based on feature_scores + prior answers), and
          already-asked exclusion → eligible set
        - selector_core.py / groq_selector.py: LLM picks ONE unit id from
          the eligible set (structured output, Groq, openai/gpt-oss-20b,
          timeout=8.0s)
        - validation.py: server-side enforcement — rejects anything not in
          the eligible set, without matching evidence provenance, or with a
          non-verbatim quote. Template-only rendering, no free text from
          the model reaches the user.
      conversation_adapter.py: the integration seam to Codex's
      conversation-state system (see Integration Contract below)
```

## File-by-file state (as of this handoff)

### Just changed, not yet pushed, not yet verified end-to-end — THIS IS THE ACTIVE TASK

- `backend/app/audio/timing_features.py` — added `mean_speech_segment_duration: float` to the
  `TimingFeatures` dataclass and its computation (mean of per-segment durations) in
  `compute_timing_features()`. Comment in the dataclass explains the r=-0.80 research backing.
- `backend/app/models/personal_baseline.py` — `FEATURE_ORDER` expanded from 3 to 4 features to
  include `mean_speech_segment_duration`. This is the file that actually drives live trigger
  decisions, so this is the real "wire it in" step.
- `backend/app/pipeline.py` — `build_take_from_audio()` now returns the 4th field too.
- `backend/tests/test_pipeline.py` and `backend/tests/test_personal_baseline.py` — updated all
  hardcoded take-dicts (CLEAN_TAKES etc.) to include the new field with realistic values. Full
  suite passes: **64 passed, 6 skipped** last run.

**What is NOT done yet (pick this up first):**

1. **Schema/API side (this is specifically your domain, not mine)** — the `checkins` table in
   `schema.sql` and the INSERT/response handling in `app/api/main.py` / `conversations.py` do not
   yet have a column for `mean_speech_segment_duration` (or for per-feature scores generally —
   `feature_scores` dict already exists in `CheckinResult`/`process_answer` as an *additive,
   optional* field, not yet persisted). Add a nullable column, wire it through the insert and the
   response dict. Keep it additive/backward-compatible the way `feature_scores` already is in
   `pipeline.py` (see the docstring in `process_answer` — it explains why it's optional).
2. **My last verification attempt found a real gap worth fixing properly, not papering over**: I
   tried re-testing against the real Parkinson's patient audio chunks at
   `/tmp/live_test_audio/pd_real_chunk_a.wav` / `pd_real_chunk_b.wav` (extracted earlier this
   session from a real dataset recording). The *first* synthetic construction (two real chunks
   with one inserted long pause between them) correctly drove up `pause_fraction` and
   `longest_internal_gap` but **did not exercise `mean_speech_segment_duration` at all** (z=0.0),
   because concatenating two unmodified chunks with one gap doesn't change segment lengths. I
   switched to a more clinically realistic synthetic case — fragmenting one chunk into several
   shorter bursts with small internal pauses (simulating hypokinetic dysarthria's "breaking into
   shorter bursts" pattern, which is the actual real-world phenomenon this feature targets,
   distinct from "one long pause"). That test construction had a bug: the micro-pause duration I
   used (0.35s) was too close to the VAD's own silence-detection threshold, producing a garbage
   VAD segmentation (massive z-scores, clearly wrong — not a bug in `personal_baseline.py` or
   `timing_features.py`, a bug in my synthetic fixture). **Next step: redo this with a cleaner
   fragmentation test — use a clearly-above-threshold micro-pause (try 0.5-0.6s) and confirm VAD
   returns the expected number of segments before trusting the z-scores.** The real_chunk files
   still exist at the path above, no need to re-extract them.
3. Update `VoiceShift-Project-Brief.md` and `VoiceShift-LOG.md` to document this 4th-feature
   addition and its research justification (the brief currently doesn't mention it as a 4th live
   feature yet — only the research-backing numbers exist in scattered analysis scripts).
4. Push this change set (`timing_features.py`, `personal_baseline.py`, `pipeline.py`,
   `test_pipeline.py`, `test_personal_baseline.py`) to the CareCircle repo. Note: this local
   directory (`/Users/AtharvaBadgujar/VoiceRadial`) is **not itself a git repo** (`git status`
   returns "not a git repository") — there is a separate git-tracked clone/location that changes
   get copied into before committing (pull → copy specific files → commit -F message-file →
   push). I don't have that local clone path recorded in this file, but the remote itself is now
   confirmed: `https://github.com/Programmer-Tiko/CareCircle` (seen in a CCR `git pull` output,
   also cloned there at `~/CareCircle`). Find or create a local clone of that remote, copy the
   pending files in, commit, push. Note also that Codex has already pushed commits ahead of what
   I last saw locally (a `docs/CADENCE-ARCHITECTURE-ROADMAP.md`, updates to
   `conversation_adapter.py`, `retrieval.py`, `question_corpus.json`,
   `ccr_build_knowledge_index.py`, and a `test_emergency_safety.py` of their own) — pull first,
   diff against what's described in this file as "mine," and reconcile before pushing on top.

### Stable, built, working — don't need rework unless bugs surface

- `backend/app/audio/vad.py` — Silero VAD wrapper, `detect_speech_segments()`,
  `load_mono_16k()`. Real pretrained model, used live.
- `backend/app/dialogue/question_corpus.json` — 14 units (version `"2026-11-08-v2"`). Each unit:
  id, condition, information_sought, preconditions, exclusions, question_template, source_type
  (`"patient_education"` or `"design_policy"`), source_url, source_excerpt, source_version,
  review_status=`"prototype"`. Recent additions (fatigue, medication wearing-off, anxiety, sleep
  quality, balance concern) sourced from real Parkinson's Foundation fact sheets. Also has
  `safety_notice` (design_policy-sourced, fixed emergency-fallback copy, explicitly excluded from
  normal retrieval flow — only reachable via the emergency bypass).
- `backend/app/dialogue/retrieval.py` — `load_corpus()`, `load_corpus_version()`,
  `compute_context_flags()`, `is_eligible()`, `retrieve_eligible_units()`,
  `contains_emergency_signal()` + `EMERGENCY_KEYWORDS` (narrow, literal, documented as prototype
  not exhaustive).
- `backend/app/dialogue/validation.py` — `SelectorOutput`, `ValidatedSelection`,
  `SelectionRejected`, `validate_selection()`. This is the real safety enforcement — don't weaken
  it for demo polish.
- `backend/app/dialogue/selector_core.py` — provider-agnostic prompt/schema/`select_question()`.
- `backend/app/dialogue/groq_selector.py` — `MODEL = "openai/gpt-oss-20b"` (verified live against
  Groq's `/v1/models`, don't trust docs-guessed model names), 8s timeout.
- `backend/app/dialogue/conversation_adapter.py` — the seam into Codex's conversation-state
  system. Already reads `feature_scores` from `context["measured"]["feature_scores"]` (you wired
  that through on your end already per an earlier file-change I observed). Emergency bypass
  returns a `safety_notice` selection without ever calling the model — has a dedicated test
  (`test_emergency_safety.py`) with a `model_call` that raises `AssertionError` if invoked, to
  prove the bypass actually bypasses.
- `backend/app/dialogue/note.py` — `describe_measured_deviation()` picks the feature with the
  largest `abs(z)` to describe, not hardcoded to pauses. `build_note()` takes
  `classification_succeeded` separately from `cue_resolved` — don't collapse these back together,
  they mean different things (see test comments in `test_pipeline.py` around line 78 for why this
  distinction matters — a deterministic keyword matcher failing to recognize an answer is not the
  same as "this cue is resolved").
- `backend/app/dialogue/ccr_build_knowledge_index.py` — CCR ingestion script. `fetch_html_text()`
  uses BeautifulSoup (not trafilatura — trafilatura's `lxml[html_clean]` dependency is broken on
  CCR and locally; verified BeautifulSoup extraction works against a real URL before pushing).
  Chunks from a CCR run are meant for **manual review** into new `question_corpus.json` units —
  deliberately not automated into the corpus directly.
- `backend/app/api/main.py`, `conversations.py`, `schema.sql`, `CONVERSATIONS.md` — primarily
  Codex's files. My only edit to `main.py` was the two-line dependency wiring:
  `from app.api.conversations import get_selector, install_routes` and
  `application.dependency_overrides[get_selector] = lambda: selector_adapter`.
  `conversations.py` defines `Source`, `Question`, `Selection` (decision:
  `Literal['ask','complete','abstain']`), `get_selector()` stub, `install_routes()`.

### Known open item, deliberately deferred (your call whether it matters before demo)

- Codex flagged that `resolved: True` is currently set based on "a valid selection was made" vs.
  "the answer specifically addressed the question" — these aren't the same thing. I agreed this
  is a real precision gap but deferred it as low-priority since it has no visible demo impact.
  Revisit only if you have spare time close to submission; not worth spending scarce time on
  otherwise, per the user's explicit "I want to win this" prioritization.

## Research findings backing the live features (verified, not fabricated — re-verify before citing new numbers)

Datasets actually used:
- UCI Oxford Parkinson's Telemonitoring (42 patients, severity labels)
- Figshare PD/HC sustained vowel (81 patients)
- MDVR-KCL (16 PD / 21 HC, continuous passage, Zenodo, CC-BY-4.0)
- ItalianPVS (28 PD / 22 HC, IEEE Dataport via HuggingFace mirror; task code B1 = continuous
  passage — PR1/FB2 are word-list tasks, this was initially mislabeled from filenames and later
  corrected by checking the actual FILE CODES.xlsx, don't re-introduce that mistake)

Key verified results:
- `mean_speech_segment_duration`: Spearman r=-0.80 vs Hoehn-Yahr stage in MDVR-KCL — the single
  strongest correlate found in any analysis in this project, stronger than `pause_fraction`
  (r=0.73). ItalianPVS task B1 (same task type, second language) is same-direction but
  borderline (p=0.053, d=-0.60) — not a significant replication. Don't call this "replicated."
- Severity regression attempt (trying to predict a continuous severity score) failed (R²=-0.35) —
  diagnosed as a between-subject vs. within-subject variance confound. Correctly retired from the
  live product rather than patched; documented as a negative result, not hidden.
- Cross-lingual embedding generalization (wav2vec2-XLSR53): does NOT generalize across languages
  even after removing the task-type confound. Codex correctly pointed out this only removes the
  task confound, not cohort/site/device/protocol confounds — brief wording was corrected to
  reflect that limitation honestly rather than over-claim "language isolated."
- Known bugs already caught and fixed during this research (don't reintroduce): StandardScaler
  fit before train/test split (leakage, fixed via sklearn Pipeline across 5 scripts, re-ran, numeric
  differences were negligible — original conclusions held); bootstrap resampling duplicating
  subjects across folds (invalid CI, replaced with permutation testing, which is the trusted
  method throughout this project).

## Integration contract with the conversation-state system (your side)

`selector_adapter(context: dict, model_call: Callable[[str], str] = _default_model_call) -> dict`
in `conversation_adapter.py` is the single function your conversation-state code calls. Expected
`context` keys: `condition`, `turns` (list of prior `{question, answer}` turns), `answer_text`,
`measured` (dict with `feature_scores`). Returns `{"decision": "ask"|"complete", "resolved": bool,
"question": {...}}`. This contract is already working end-to-end with Groq live — if you change
its shape, update both sides together and re-run `test_conversation_adapter.py`.

## Working with CCR (UB's HPC cluster)

CCR is used for anything compute-heavy that the research/corpus pipeline needs — currently just
the knowledge-indexing job (`ccr_build_knowledge_index.py`: fetch sourced documents, chunk them,
embed with `sentence-transformers` BAAI/bge-base-en-v1.5). Earlier severity-model/embedding
research scripts in `backend/app/models/` were also run there. Confirmed-working details from
this session, observed directly in terminal output the user pasted back (not guessed):

- **Remote**: `https://github.com/Programmer-Tiko/CareCircle.git`, cloned on CCR at
  `~/CareCircle`. The backend package lives at `~/CareCircle/backend`.
- **Environment**: a venv named `voiceshift-env` (not conda), Python 3.10
  (`/user/abadguja/voiceshift-env/lib/python3.10/site-packages`). Activate it before running
  anything — the prompt shows `(voiceshift-env)` when active.
- **Observed hostname**: `cpn-c02-04.core.ccr.buffalo.edu` — a compute node, not the login node.
  Outbound GitHub access (both `git pull` and `git push` over HTTPS) works fine from this node.
  Outbound `scp`/direct network access from a compute node is NOT confirmed either way — don't
  assume it works. **Now verified from Slurm output:** the session is an Open
  OnDemand VS Code allocation (`ood-vscode`, job 26746273), on `cpn-c02-04`.
  Account `filippom`, cluster `ub-hpc`, partition/QoS `general-compute`,
  eight CPUs and 16000M memory. Separate sbatch jobs queue independently.

**The established round-trip workflow** (confirmed working, used successfully twice this
session):
```bash
ssh <ccr host>                      # ask the user for the actual host/alias
source ~/voiceshift-env/bin/activate   # or wherever it actually activates from
cd ~/CareCircle/backend
git pull                            # always pull first -- Codex and I have both pushed mid-session
pip install <anything missing>      # e.g. beautifulsoup4 was missing, installed ad hoc
python app/dialogue/ccr_build_knowledge_index.py --out data/out
# review the printed output -- fetch succeeded per-URL, chunk counts, final total
```

**Getting output back** — this is the part that isn't obvious and tripped us up (trafilatura's
`lxml[html_clean]` dependency was broken on CCR, fixed by switching `fetch_html_text()` to
BeautifulSoup; verified locally first before trusting it on CCR). For *data* output files (like
`knowledge_chunks.json`, `knowledge_embeddings.npy`), since direct `scp` from the compute node is
unconfirmed, the pattern that's actually worked is: commit the output files to git from CCR and
push, then pull on whatever machine needs to read them. Already done once:
```bash
cd ~/CareCircle/backend
git add data/out/knowledge_chunks.json data/out/knowledge_embeddings.npy
git commit -m "Add CCR knowledge-index run output: 311 chunks, 10 sources"
git push
```
This worked (commit `fd9fc9d`, pushed to `main`). Codex checked its actual
numstat: `knowledge_embeddings.npy` was already binary (`- -`); the 240,716
added text lines belong to `knowledge_chunks.json`, which duplicates vectors
as JSON arrays. Explicit `*.npy binary` attributes are still useful, but do
not fix the JSON size. Preserve existing artifacts; avoid redundant inline
vectors in future formats unless a consumer needs them.

**Verified execution/storage rules from subsequent runs:**
- `/scratch/voiceshift_data` was readable on interactive node cpn-c02-04 but
  unreadable on batch node cpn-c02-06: all 86 audio files failed. Do not assume
  this scratch path is shared. Stage audio under `~/cadence-audio` and write
  absolute shared-home paths into the manifest. The rerun successfully read them.
- Working sbatch options: `-M ub-hpc --account=filippom
  --partition=general-compute --qos=general-compute --ntasks=1
  --cpus-per-task=8 --mem=16G --time=01:00:00 --export=ALL`.
- Job 26746762 completed extraction/evaluation in 4m39s. The 86 extraction
  issues were deliberate unknown passage counts; other timing features
  extracted for every recording, prosody missing for one. Original
  within-dataset folds failed; fix `3e4b755` stratifies participants directly.
  User has generated `data/out/multisignal-v2/ablation-fixed.json`; awaiting
  its summary/raw artifacts. Do not repeat audio extraction for this fix.
- Active code branch is `codex/multisignal-experiments`, not necessarily main.
  Use `git pull --ff-only` and explicit paths when committing artifacts.
- Codex's own `ssh ccr` access fails publickey authentication; commands are
  currently executed in the user's authenticated CCR terminal.

Some other generated outputs may be intentionally local. Before including
additional untracked artifacts, inspect `git status --short`; stage only named
feature/results/provenance files. Do not bulk-add the output directory or raw
audio. Ask about unrelated artifacts when they are actually needed.

**The one rule that matters more than the mechanics**: don't run a CCR job just to demonstrate
compute usage. The user has pushed back twice this session when a CCR run produced output that
never actually got used by the live product. Before kicking off a job, know what it becomes —
a reviewed `question_corpus.json` unit, a verified research number for the brief, or a feature
actually read by the live pipeline. If you can't name which of those it is, don't run it yet.

## How the user works / expectations (read this, it'll save you friction)

- Wants rigor over impressiveness, but ALSO wants to win — these aren't actually in tension if
  you keep claims accurate; don't round up numbers to sound better.
- Gets frustrated by work that doesn't visibly feed the live demo (see CCR note above). Before
  running something expensive, ask: "will this become a corpus unit / a wired feature / a cited
  number," not "does this sound like we used our resources."
  Explicitly said things like "we have the compute and the tokens, use them" but also, twice,
  pushed back when that compute didn't produce anything the running product actually uses — both
  are real, hold both.
- Dislikes generic/hardcoded-feeling AI. The RAG selection layer exists specifically because a
  fully deterministic question-picker felt like "no brain" to them. Keep the LLM doing real
  selection work; don't quietly replace it with more deterministic logic to "simplify."
- Wants a persistent log of session context (`VoiceShift-LOG.md`) — keep appending to it, don't
  replace/rewrite history in it.
- Teammate is asleep/unavailable at various points — don't block on them; there's a teammate task
  outstanding (see Pending Tasks) to record demo fixture audio (7 clips: 3 clean, 1
  typical-variation, 2 acted-deviation) — last status unknown, ask the user directly.
- Scope is Parkinson's-only (COPD was cut) — don't reintroduce COPD-specific logic without the
  user explicitly asking.

## Pending tasks (in rough priority order)

1. Finish the `mean_speech_segment_duration` verification properly (fix the fragmentation-test
   micro-pause bug described above) and confirm it against real patient audio.
2. Schema + API wiring for the new feature (nullable column + INSERT + response dict) — this one
   is specifically yours.
3. Update brief/log docs with the 4th-feature addition.
4. Push the pending change set to the CareCircle repo (find the actual git clone path first — this
   working directory isn't it).
5. Confirm demo fixture-audio recording status with the user (teammate's task, unconfirmed).
6. Optional/low-priority: the `resolved` semantics precision gap noted above.
7. **UPDATE — this already ran, don't redo it**: the CCR knowledge-index job was rerun
   successfully (BeautifulSoup fix confirmed working on CCR) against 10 sources — the original 8
   Parkinson's Foundation fact sheets plus two new PDFs Codex added to the script's source list
   (APDA "Communication and PD" and "Managing Off-Time 2024"). Output: 311 embedded chunks in
   `data/out/knowledge_chunks.json` + `data/out/knowledge_embeddings.npy` on the CCR clone at
   `~/CareCircle/backend`. **These two files still need to be pulled off CCR onto a machine where
   someone can actually read them** (scp or similar — the run output literally said "Bring both
   back"). Once local: manually review the highest-relevance chunks and draft new sourced
   `question_corpus.json` units from them, same process as the existing 13-14 units. This step is
   deliberately manual — the script builds the retrieval base, it does not write patient-facing
   question text itself. Don't automate corpus insertion directly from scraped text.

## One more thing

The user asked for this handoff specifically so you can "be me, but in Codex" — meaning: keep the
same standards (verify before trusting, report negative results honestly, don't fabricate
numbers, don't let CCR/compute use become performative, keep the RAG layer real) rather than
reverting to a more conservative or more hardcoded default because the context feels unfamiliar.
Ask the user directly for anything this file doesn't cover rather than guessing — they've been
closely steering architecture decisions throughout and will want to keep doing so with you.

## Latest delivery: integrated UI (supersedes earlier integration-pending notes)

The real UI is now `Daily Hello Family.html` plus `frontend/cadence.js/css`,
served by FastAPI at `/`. Run `./run-cadence.sh` and open localhost:8000.
README.md describes current setup. The optional Python 3.11 environment at
`backend/.venv-asr` is prepared locally and uses the existing cached checkpoint.

Enrollment/check-in WAV capture, real measurements, experimental personal
references, optional phrase verification, reviewed ASR answers, durable
multi-turn questions with sources, manual TTS, note correction/confirmation,
Finish for now, non-triggered personal reports, and history are wired.
Unsupported mock content is removed. Three reviewed communication candidates
are live in corpus v3; the other proposals remain excluded. Context rules now
have tested negation/memory fixes. Ordinary sessions have a four-question budget
and no automatic provider retries.

Final suite: **243 passed, no skips**, with cloud/local database integrations and
real cached-model ASR enabled. Chrome acceptance and a separate real
Tiger/Groq/ElevenLabs/Whisper UI run passed; passage gating also passed positive
and negative HTTP checks. See `docs/UI-INTEGRATION-VERIFICATION.md`.

The long live run hit Groq's rate limit after nine selections and preserved the
tenth answer under abstention. Do not claim natural conversation completion.
Human recordings/device acceptance, authentication, caregiver sharing, phone
calling, and clinical monitoring validation remain outstanding.
