---
name: dsh-observability
description: Use when analyzing a DeepSeek Harness or Codex agent run for tokens, cache, tool calls, latency, context, compaction, skill activation, plugin effect, or run-to-run differences; or when choosing an observability backend (local, OpenTelemetry, Langfuse, Phoenix, Grafana, LangSmith, Braintrust). Read-only; never print prompts, credentials, or raw session contents.
---

# DSH observability

Load `model-policy` once from its host catalog location and apply its guidance.

Analyze the recorded evidence, not your impression of the run. Do not rerun the model
unless the question requires a new distribution.

## Quick start

```sh
# A dsh SDK result.json
python3 scripts/session_metrics.py <result.json>

# OTLP JSON for a collector/Langfuse/Phoenix
python3 scripts/export_otlp.py <result.json> --out otlp.json
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 python3 scripts/export_otlp.py <result.json>

# Langfuse thin wrapper (keys from env; local JSON if unset)
LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=... python3 scripts/langfuse_export.py <result.json>

# A raw dsh session log (zstd) without printing its contents
python3 scripts/session_events.py <session.v4.jsonl.zstd>

# A Codex CLI --json event log
python3 scripts/codex_metrics.py <codex-events.jsonl>
```

## Choose a backend

Default to the local scripts. For shared traces or dashboards, use OpenTelemetry
(OTLP) and pick a backend from [platforms](references/platforms.md) — Langfuse,
Phoenix, Grafana/Tempo, Jaeger, or the user's existing stack. Do not add a vendor SDK
just to inspect one run, and do not send prompts or credentials to a backend.

## Sandbox artifacts

When a metric looks like "no GPU", "no network", "no host process", or "nested Codex
failed", first check the sandbox: DSH's file-effect sandbox uses a private `/dev` and PID
namespace, ephemeral `/tmp`, and a read-only host home. A confined probe cannot establish
host capability. Record the sandbox mode/denial as a limitation, and use a wider approved
mode or a host runner before drawing a host-level conclusion. Do not put raw device paths
or host credentials in a report.

## What to report

| Question | Metric |
|---|---|
| Did it loop? | tool calls, repeated `(tool,target)`, calls before first edit, step count |
| Was it expensive? | input/output tokens, cache read/write, cache hit rate, model vs tool time |
| Where did time go? | tool p50/p95/max, total tool time, phase after last edit |
| Did it verify? | verification calls (`test`, `build`, `dump-config`, `npm pack`, install/uninstall) |
| Did it use the skill? | skill calls, model-policy calls, reference reads and bytes |
| Did context pressure occur? | compaction events, summary/prune counts, shadowed events |
| Was it a real run? | final response, errors, missing result, timeout, environment failure |

Always separate **uncached input + output** from **cache read**; total tokens include
cache reads and are not additive with input. A single trial is descriptive, not an
effect estimate. Report per case and per arm, not only an aggregate mean.


For exact p50/p95, top-tool ties and token totals, run `scripts/session_metrics.py` and quote its
fields; if you use nearest-rank or interpolation, label it separately. Do not substitute an
alternate percentile for the script's `tool_latency_ms_p95`.

## Interpret

- A zero `compaction_events` means "not triggered by this case", not "compaction is
  irrelevant". Check the context window and the case size.
- Aggressive compaction thresholds can cause re-reading and repeated compaction with
  no edit; count summary/prune events and `phase_after_edit_ms`.
- High tool p95 can be a slow shell job, not model latency; inspect tool names.
- A missing `result.json` or a killed trial is an explicit failure, never a low score.

Integration commands and last verified setup are in [tests/INTEGRATION.md](tests/INTEGRATION.md).

Read [event schema](references/event-schema.md), [metric definitions](references/metrics.md),
[compaction](references/compaction.md), [Codex](references/codex.md), and
[privacy](references/privacy.md) only when needed.

## Scripts

| Script | Use |
|---|---|
| [session_metrics.py](scripts/session_metrics.py) | Full event-derived metrics for one dsh `result.json` |
| [session_events.py](scripts/session_events.py) | Event/tool/usage/compaction summary from a raw session log |
| [codex_metrics.py](scripts/codex_metrics.py) | Usage and item summary from `codex exec --json` |
