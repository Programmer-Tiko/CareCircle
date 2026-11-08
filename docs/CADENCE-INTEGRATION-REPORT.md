# Cadence teammate integration verification

## Scope and ancestry

The stable base is `origin/main` at `fd9fc9d`. It was unchanged after fetching.
The integration branch is `integration/cadence-teammate-updates`; main and all
teammate branches were preserved.

| Source | Commit | Relationship |
| --- | --- | --- |
| `codex/four-feature-integration` | `68321e7` | Ancestor of multisignal and UI |
| `codex/multisignal-experiments` | `7363896` | Seven commits ahead of main; ancestor of UI |
| `codex/ui-integration` | `59c7590` | Contains all 17 implementation commits plus the latest demo guide |
| PR #2 / `fix/transaction-test-and-groq` | `256b5d7` | One separate test-fix commit |
| `docs/cadence-architecture-roadmap` | `8fce598` | Already contained in main |

The UI implementation at `da7583f` was fast-forwarded into the isolated integration branch once.
PR #2's original commit was merged with merge commit `145fa1c`; it was not
cherry-picked or duplicated. The only conflict was the database test double in
`test_api.py`. Resolution retains the ownership-query behavior, real `get_db`
teardown, commit-attempt checks, sanitized response check, and HTTP 503 assertion.
PR #2 was not merged into main. Its standalone suite was reverified in a separate
temporary worktree: **70 passed, 6 database tests skipped**.

A final fetch found documentation-only teammate commit `59c7590`, adding
`TEAMMATE-WORKFLOW-AND-DEMO-GUIDE.md`. It was reviewed and merged separately;
application code and tests were unchanged, so the completed verification remains
applicable. The guide's narration of live-provider behavior is not an additional
live-service verification by this integration task.

## Stabilization changes

- Preserve the established check-in `status` contract: routine/untriggered
  readings return `no_change`; persistent deviations return `awaiting_answer`.
  The new UI still starts an adaptive conversation for either result.
- Update SQL test fixtures to select opening questions explicitly through actual
  retrieval/validation with an injected provider choice. Existing follow-up and
  provider-failure scenarios keep their assertions and original purposes.
- Run the existing deterministic emergency notice before the conversation
  budget and provider seam. A question limit or unavailable selector cannot
  suppress it. This is the existing narrow keyword tripwire, not comprehensive
  emergency detection.
- Starting a new check-in saves the previous conversation as an unconfirmed
  draft. Only the explicit confirmation action marks the note confirmed.
- Retain PR #2's collection-time secret/provider isolation. Add an explicit
  `--disposable-db-url` option restricted to the dedicated localhost database;
  arbitrary database URLs and inherited configuration remain blocked.
- Add optional browser tooling and executable migration/browser regressions.

## Measurement and question-selection behavior

The integrated protocol uses 41 fixed syllables, excludes edge silence from
internal pause measurements, and computes speaking rate as fixed syllables /
detected speech duration. Mean speech-segment duration is the fourth feature.
These teammate definitions were preserved, not recalibrated during integration.
Personal robust deviations use the teammate's relative MAD floor of 20% of each
feature median and aggregate threshold 3.0 with two consecutive check-ins.
These are prototype parameters, not validated diagnostic thresholds.

Waveform/prosody evidence remains experimental and separate from the timing
trigger. Phrase verification/ASR is optional; unavailable evidence is not
fabricated. Legacy three-feature baselines keep their history but require a new
profile before scoring under the new protocol; no old baseline is overwritten.

The active question path is metadata filtering plus lexical ranking, Groq
`openai/gpt-oss-20b`, and output validation over sourced question templates.
Persisted feature scores and explicit reports/denials/interruption flags gate
eligibility. The opening selection retains its bounded retries and retrieved
template fallback. Embedding index artifacts are not the live retrieval path.
The dormant Gemini wrapper is unchanged and is not enabled by this integration.

## Verification

Use the project-local isolated `.venv`. Core dependencies are unchanged.
Optional browser tooling is declared in `backend/requirements-browser.txt`.
Chrome/Edge must be installed separately; the test launches a temporary profile.

From `backend`, with the port of a newly created, disposable TimescaleDB:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/ -q --tb=short -rs --browser-smoke --disposable-db-url postgresql://postgres@127.0.0.1:PORT/cadence_integration_test
```

The database must be a new localhost-only disposable container. No connection
is taken from dotenv or inherited database credentials. Without this explicit
option, real database calls are blocked and SQL integration tests skip. Real
Groq, Gemini, ElevenLabs, and outbound HTTPX requests remain blocked in both modes.

Verified combined results: **279 passed, 2 skipped, 0 failed**. The two skips are
optional real-Whisper smoke tests. Two upstream warnings concern deprecated
Silero resource loading and TorchScript loading. `pip check` passed. JavaScript
syntax checks passed for `frontend/cadence.js` and all three browser scripts,
using Playwright's bundled Node runtime. There is no npm application build.

Real Chrome exercised browser audio capture using the existing licensed
control-speech fixture, WAV upload, actual FastAPI/VAD processing, persisted
four-feature evidence, actual retrieval/validation, multi-turn SQL state,
correction, explicit confirmation, reload recovery, history, and draft reset.
No application HTTP endpoint was intercepted. Provider ID choices and bounded
completion were injected; external font requests were blocked. This verifies
fixture-audio integration, not a live microphone study or passage recognition.

SQL tests additionally cover normal/repeatedly changed recordings, invalid and
silent audio, reported difficulty despite a typical acoustic reading, profile
scoping, concurrent requests, idempotent retries, revisions, question limits,
missing credentials, and deterministic emergency guidance. The migration test
applies the schema twice over fictional legacy three-feature history and checks
that stored baselines and confirmed answers remain unchanged.

## Database rollout and remaining limits

The schema changes are additive (`ADD COLUMN IF NOT EXISTS`, new tables/indexes).
They add waveform baselines, per-check-in evidence, turn closure timestamps and
`patient_reports`. No production database was accessed or migrated. Before a
real deployment, take a database backup, verify TimescaleDB/role compatibility,
and apply `backend/app/api/schema.sql` in a reviewed maintenance window. The
application still performs initialization at startup when a database is configured.
Do not rewrite legacy baselines or invent missing evidence during migration.

The inherited research output artifacts are unchanged from the teammate branch;
no private data, credentials, local environment, browser profile, or new dataset
was added. Existing local secrets and the intentionally deleted archive were not
used. The temporary database contains only fictional test records.

This is a local, unauthenticated prototype. Profile scoping is not authenticated
access control: knowing another profile ID can expose its local history. Drafts
remain unconfirmed and are not shared through a caregiver feature, but this must
not be represented as production privacy. Authentication, authorization and
explicit sharing consent are prerequisites before any shared deployment.

Real ASR, real Groq/ElevenLabs service behavior, human microphone conditions, and
caregiver workflows were not verified here. Typed answers and provider failure
paths were tested; ASR/voice responses in tests use injections. COPD/asthma,
multimodal monitoring and expanded clinical libraries remain research directions.

Recommended next work: validate the complete flow with consented standardized
passage recordings and optional local ASR, then address authenticated access and
sharing before network deployment. Keep Groq/RAG as the working provider; an
optional Gemini provider is a later task after integration review and merge.
