import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node'
import { SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base'
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http'
import { apply } from './index.mjs'
const provider = new NodeTracerProvider()
provider.addSpanProcessor(new SimpleSpanProcessor(new OTLPTraceExporter({ url: 'http://127.0.0.1:4318/v1/traces' })))
provider.register()
const ctx = { tool: (name, args) => `${name}:${args.text}` }
console.log(apply(ctx))
await provider.forceFlush()
await provider.shutdown()
