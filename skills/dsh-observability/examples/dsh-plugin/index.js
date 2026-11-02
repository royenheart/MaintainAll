import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node'
import { SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'

export const name = 'otel-dsh-plugin'
export const inject = ['tools']

export function apply(ctx) {
  const provider = new NodeTracerProvider()
  provider.addSpanProcessor(new SimpleSpanProcessor(new OTLPTraceExporter({ url: 'http://127.0.0.1:4318/v1/traces' })))
  provider.register()
  const tracer = provider.getTracer('otel-dsh-plugin')
  ctx.tools.register({
    name: 'otel_echo',
    description: 'Echo text; used only to verify plugin tool registration.',
    parameters: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: String(value) }] },
    execute: async ({ text }) => {
      const toolSpan = tracer.startSpan('dsh.tool', { attributes: { 'tool.name': 'otel_echo', 'tool.input_chars': String(text).length } })
      try { return String(text) } finally { toolSpan.end() }
    },
  })
  const registered = Boolean(ctx.tools.get('otel_echo'))
  const span = tracer.startSpan('dsh.plugin.run', { attributes: { 'dsh.plugin.name': name, 'dsh.plugin.version': '0.1.0', 'dsh.plugin.host': 'dsh-web', 'dsh.tool.registered': registered ? 'true' : 'false' } })
  span.end()
  ctx.effect(() => () => { provider.shutdown().catch(() => {}) }, 'otel-dsh-plugin')
  return provider.forceFlush().catch(() => {})
}
