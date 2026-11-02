import { trace } from '@opentelemetry/api'
export const name = 'otel-fixture'
export function apply(ctx) {
  const tracer = trace.getTracer('dsh-otel-fixture')
  return tracer.startActiveSpan('dsh.plugin.run', {
    attributes: { 'dsh.plugin.name': name, 'dsh.plugin.version': '0.1.0' },
  }, (span) => {
    try {
      const result = ctx.tool('echo', { text: 'hello' })
      return tracer.startActiveSpan('dsh.tool', {
        attributes: { 'tool.name': 'echo', 'tool.result_chars': String(result).length },
      }, (toolSpan) => {
        toolSpan.end()
        span.setAttribute('dsh.plugin.outcome', 'ok')
        return result
      })
    } finally {
      span.end()
    }
  })
}
