# Instrumenting a plugin

The goal is to observe a plugin's effect without shipping prompts, tool outputs, or
credentials to a backend. Export derived spans/events and keep the payload small.

## Span shape

Use OpenTelemetry GenAI conventions where they fit:

- `dsh.plugin.run` (root for one plugin activation/turn):
  `dsh.plugin.name`, `dsh.plugin.version`, `dsh.session.id`, `dsh.case`, `dsh.arm`;
- `dsh.hook` for each hook/middleware call:
  `dsh.hook.name`, duration, status;
- `dsh.tool` for a tool the plugin registers:
  `tool.name`, `tool.call_id`, `tool.duration_ms`, result size (not content);
- `dsh.skill` for a skill activation/reference read:
  `skill.name`, `reference.bytes`, `reference.count`;
- `dsh.compaction` as an event, not an LLM span.

Do not put prompt text, tool arguments, file contents, tokens, cookies, or `.npmrc`
values in attributes. Use lengths, hashes, relative paths, or counts.

## Minimal JS wrapper

```js
import { trace } from '@opentelemetry/api'

const tracer = trace.getTracer('dsh-plugin')

export function observe(name, attrs, fn) {
  return tracer.startActiveSpan(name, { attributes: attrs }, async (span) => {
    try {
      const result = await fn()
      span.setStatus({ code: 1 })
      return result
    } catch (error) {
      // Do not export raw exceptions: the SDK stores the message and stack, which can
      // contain commands, paths, tokens, or file contents. Emit an allowlisted kind.
      const kind = error?.name === 'AbortError' ? 'aborted' : 'tool_error'
      span.setStatus({ code: 2, message: kind })
      span.setAttribute('dsh.error.type', kind)
      throw error
    } finally {
      span.end()
    }
  })
}
```

A loadable example is in `examples/dsh-plugin` (real dsh web profile, collector span).

Wrap only the plugin's own hook/tool boundary; do not wrap the whole host or the model
loop. A plugin should depend on `@opentelemetry/api` optionally, not bundle a collector.

## Export

- Collector/OTLP: set `OTEL_EXPORTER_OTLP_ENDPOINT`; the host/collector owns batching.
- Langfuse: point the OTLP exporter at `https://<host>/api/public/otel` with basic auth;
  the provided `scripts/langfuse_export.py` does this for recorded dsh runs, not for a
  live plugin.
- Local: emit JSONL spans and use `scripts/export_otlp.py` for offline conversion.

## Verification

Compare paired arms on the same case:

- outcome score and invalid/incomplete reason;
- uncached tokens, cache read/write, wall time, tool p50/p95;
- skill/reference reads, compaction count;
- plugin hook latency and error rate.

A plugin effect is a difference on the same case and model, not a pooled average across
different graders.
