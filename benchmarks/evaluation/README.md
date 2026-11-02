# Unified evaluation framework

One evaluation surface for this repository. The old `benchmarks/agent_eval` and
`benchmarks/skill_bench` trees remain as **legacy adapters and evidence sources**, not as
two independent products. A second CLI/report is not added; legacy entry points become
migration surfaces. The framework is deliberately a skeleton: it fixes contracts,
layers, ports and one report path before replacing the mature skill_bench renderer.

The architecture follows the migrate-bot workflow/evaluation split
([workflow design](https://github.com/royenheart/dsh-migrate-bot/blob/main/docs/design/workflow.md),
[evaluation design](https://github.com/royenheart/dsh-migrate-bot/blob/main/docs/design/evaluation.md),
and [issue #8](https://github.com/royenheart/dsh-migrate-bot/issues/8)), adapted to
skill evaluation.

## Layers

```
composition root (CLI)
  -> workflow (pure)        contracts.py, workflow.py, metrics.py, comparison.py
  -> runtime/evidence       store.py, RunManifest, event log, record hash
  -> activity ports         ports.py: suite/case/fixture source, trial runner, grader,
                            calibrator, reviewer, record/artifact store, metrics engine,
                            report builder, trace sink
  -> capabilities           adapters/agent_eval.py, adapters/skill_bench.py,
                            future dsh/codex/harbor/OTel adapters
  -> report                 report.py: one static page, zero model calls
```

Rules:

- `contracts.py`, `workflow.py`, `metrics.py` and `comparison.py` are pure: no
  filesystem, network, clock or model.
- The runtime records immutable `Record` objects; the workflow is an event-log
  projection, not a second score.
- Activities depend on ports. Capabilities are replaceable adapters.
- A grader/reviewer never writes a record; it returns evidence the runtime seals.
- `RunManifest` is the bridge to Langfuse/OTel and to a future framework.

## Minimum schemas

- `RunManifest`: runId, suite, case, arm, workflowHash, promptHashes, skillCommit,
  agentRuntime, model, provider, target/source, traceId, evaluation link.
- `Attempt`: outcome (`scored|timeout|exception|infrastructure|incomplete|failed`),
  reward/max, checks, usage, artifacts, error. Infrastructure/incomplete is not 0.
- `Record`: immutable manifest + attempts + metrics + evidence hashes; content hash
  checked on read.
- `CaseSpec`/`SuiteSpec`: split, scale, prompt/fixture/grader/truth hashes; no answers.
- `Report`: one page over sealed records plus links to legacy published reports.

## Existing adapters and migration parity

- `adapters/agent_eval.py` reads `benchmarks/agent_eval/datasets/validation-1.json`,
  cases, results, and writes unified records. It never rewrites the legacy files.
- `adapters/skill_bench.py` reads the public catalog and lists its published reports as
  summary-only legacy routes. The mature art-creation renderer remains authoritative for
  those bundles.

Import rules:

- legacy bytes are read-only; records carry `legacy.stack/path/original hashes` and a
  limitations note when a hash differs from the current case/grader;
- IDs are namespaced (`ae-*`); imports are idempotent and never reconstruct missing traces;
- a cumulative skill_bench report is not exploded into duplicate trials;
- parity is accepted only when case, grader, status and metric counts match, or the
  record is explicitly marked `legacy-unmapped`.

## Commands

```sh
PYTHONPATH=benchmarks/evaluation/src python3 -m eval_framework.cli ingest-agent-eval
PYTHONPATH=benchmarks/evaluation/src python3 -m eval_framework.cli build-site
PYTHONPATH=benchmarks/evaluation/src python3 -m eval_framework.cli validate
```

`ingest-agent-eval` is idempotent: an existing record is never overwritten.
`build-site` writes `benchmarks/evaluation/site/index.html` and record JSON; it makes no
model calls and does not publish.

## Merge plan

1. **Contracts first** (this change): one record/manifest/report path; legacy stacks
   remain adapters; no data migration.
2. **Parity reads**: adapters ingest agent_eval results and link skill_bench reports;
   compare counts/hashes with the legacy JSON before changing any public page.
3. **One public entry**: the unified site is the only navigation; legacy bundles get a
   “legacy report” link until the renderer reaches parity.
4. **Runtime manifest**: every live run writes `runs/<id>/manifest.json` and
   `events.jsonl`; Harbor/OTel attach to the same manifest, not a second DB.
5. **Retire duplicates**: after parity, remove the second report/Catalog path; keep
   historical bundles immutable and hash-verified.

## Current webpage gaps

Review notes and dispositions are in [REVIEW.md](REVIEW.md).

Review finding: the public catalog contains only three October art-creation bundles; it
does not represent the separate agent-eval history. A page refresh alone cannot fix
stale inputs. Migrate-bot has table rows but no suite/case/record page, split/calibration
badge, grader/judge/skill provenance, live `RunManifest` link, or `not-verified` section.
skill_bench has a strong report but CI uploads an artifact (no Pages), the catalog is
manual, and it has no case/provenance page. Shared gap: no page answers
`case -> trial -> record -> report -> live run`, and cohort incomparability is not visible.

- `benchmarks/results/catalog.json` contains only art-creation; no dsh-skill suite.

- The current agent_eval attribution records are published in the unified page from sealed `evidence/` records.
- No page shows RunManifest/prompt/skill/model/trace identity per trial.
- No unified view distinguishes scored / incomplete / infrastructure / failed.
- No case-level structured findings or holdout labels on the public page.
- The old site cannot compare two frameworks without a second navigation/source or a
  hand-maintained table.

This skeleton fixes the single entry and record identity; the rich legacy renderer is
intentionally not replaced yet.

## Non-goals

- no unified scalar score or cross-domain leaderboard;
- no re-score/rewrite of legacy records, bundles or sites;
- no full Harbor/Temporal/worker rewrite;
- no new workflow DSL or low-code editor;
- no second reward computed in Langfuse;
- no data migration of the art-creation records;
- no claim that a skeleton improves a model score;
- no live model run in this change;
- no LLM judge in scoring, no OTel/Langfuse as source of truth, no public raw trajectories.

## Current public site

`benchmarks/evaluation/build_public_site.py` is the single build entry. It ingests sealed
records from `evidence/`, builds an index at `/`, a detailed attribution report at
`/dsh-sandbox-attribution/`, and a normalized legacy report at `/art-creation/` with its public reference and comparison images, then writes
`public-benchmark-site/`. The attribution report includes charts, all case prompts,
truth/config details, record checks and skill diffs; the art report includes normalized
trial tables, quality/outcome/trend charts and prompt details. The page is deployed by
`.github/workflows/evaluation-site.yml` to GitHub Pages; local preview is served from
`public-benchmark-site/` on the LAN. The report makes no model calls.
