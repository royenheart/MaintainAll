# Instrumented plugin example

This is a real plugin module (`apply(ctx)`) instrumented with the OpenTelemetry API.
`run.mjs` supplies a minimal fake `ctx`, registers a Node tracer provider, and exports
to an OTLP/HTTP collector. It is intentionally small: no dsh host is required.

```sh
cd skills/dsh-observability/examples/otel-plugin
npm install
# collector on 127.0.0.1:4318 (see ../../tests/INTEGRATION.md)
node run.mjs
```

The emitted spans are `dsh.plugin.run` and `dsh.tool`. They contain names, versions,
status and result length; no prompt, arguments, file contents, or credentials.

To use in a real plugin, keep the `apply`/hook boundary and the same attributes; do not
wrap the whole host or the model loop. See `references/plugin-instrumentation.md`.
