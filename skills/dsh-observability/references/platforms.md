# Observability platforms

Use this when the user asks to monitor, trace, evaluate, or compare plugin/agent runs, or
asks which observability framework to use. Start with the local metrics scripts; add a
platform only when the question needs cross-run storage, dashboards, or shared traces.

## Default recommendation

1. **Local first**: `session_metrics.py` / `session_events.py` / `codex_metrics.py`.
2. **Portable traces**: OpenTelemetry (OTLP/HTTP or gRPC) to a collector.
3. **Platform**: Langfuse, Phoenix, Grafana/Tempo, or the user's existing backend.
4. **Evals**: Braintrust/LangSmith only when the task is dataset/eval management, not
   ad-hoc run inspection.

Do not add a vendor SDK just for one run. Prefer OTLP because it is vendor-neutral and
keeps DSH free of Langfuse/LangSmith-specific code.

## Matrix

| Backend | Best for | Integration | Self-host | Watch out |
|---|---|---|---|---|
| Local JSON/OTLP | debugging one run; no network | scripts + collector | yes | no cross-run UI |
| Langfuse | traces, prompts, evals, sessions | OTLP `/api/public/otel` (basic auth) or SDK; `scripts/langfuse_export.py` | yes (Docker) | API keys; redact prompts |
| Arize Phoenix | local trace/eval UI | OTel-native | yes | Python/JS runtime |
| Grafana Tempo/Loki | existing Grafana stack | OTLP | yes | needs collector/dashboards |
| Jaeger | simple trace UI | OTLP | yes | traces only |
| LangSmith | LangChain/LangGraph eval | SDK/API | cloud | vendor coupling |
| Helicone | proxy-level LLM logs | base URL/proxy | cloud/self | changes request path |
| Braintrust | eval datasets/experiments | SDK | cloud/self | eval-centric |
| W&B Weave | experiment tracking | SDK | cloud/self | not a DSH plugin API |
| Datadog/New Relic | existing APM | OTLP/agent | cloud | cost, PII |

## OTel mapping for DSH/Codex

Use the GenAI semantic conventions where possible:

- one trace per run/session; `session.id`, `dsh.profile`, `plugin.name/version`;
- one span per model call (`gen_ai.operation.name=chat`, model, input/output token counts,
  cache read/write);
- one span per tool call (`tool.name`, target hash/type, duration, status);
- one span per skill activation/reference read (`skill.name`, bytes);
- compaction as an event, not a fake LLM span;
- never put prompts, credentials, or raw session text in attributes; use length/hash.

## Plugin-effect experiment

To measure whether a plugin changed behavior, record per arm:

- task/case id, plugin/skill version, model, seed;
- tokens (uncached, cache read/write), wall time, tool p50/p95;
- skill/reference reads, compaction count;
- outcome score and invalid/incomplete reason.

Compare paired arms on the same case; do not pool across cases or grader versions.

## Selection rules

- Asked for "just inspect this run" -> local scripts.
- Asked for "dashboard/shared traces" -> OTLP + Langfuse/Phoenix/Grafana.
- Asked for "evals/datasets" -> Braintrust/LangSmith/Phoenix, not a trace-only tool.
- Asked for "cost/latency by model" -> OTel metrics + existing APM; do not infer from
  message count.
- Credentials only from env; never print or commit them.
