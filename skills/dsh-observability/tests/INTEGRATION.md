# Integration checks

These require external services and are not part of the offline check.

## OTel collector

```sh
docker run --rm -d --name dsh-otel -p 4318:4318 \
  -v "$PWD/.tmp/otel/config.yaml:/etc/otelcol-contrib/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:latest \
  --config=/etc/otelcol-contrib/config.yaml

python3 scripts/export_otlp.py /path/to/result.json \
  --endpoint http://127.0.0.1:4318 --out /tmp/otlp.json
docker logs dsh-otel | tail
```

The debug exporter shows `dsh.run`, `gen_ai.chat`, `tool.call`, `dsh.compaction`.
No prompt, path, or tool body should appear.

## Langfuse (self-host or cloud)

Set:

```sh
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_HOST=https://<langfuse-host>:3000  # self-signed local
LANGFUSE_INSECURE=1                       # local self-signed cert only
python3 scripts/langfuse_export.py result.json --out /tmp/langfuse-otlp.json
```

Then open Langfuse → project → traces, or query:

```sh
curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_HOST/api/public/traces?limit=5"
```

The trace is `dsh.run` with `gen_ai.chat`, `tool.call`, `dsh.compaction` observations.
The exporter sends only derived fields.

## Instrumented plugin

```sh
cd skills/dsh-observability/examples/otel-plugin
npm install
node run.mjs
```

The collector should show `dsh.plugin.run` and `dsh.tool`.

## Last verified (2026-10-31, local)

- OpenTelemetry Collector Contrib `0.164.0`: exporter POST returned HTTP 200; debug
  exporter showed `dsh.run`, `gen_ai.chat`, `tool.call`, `dsh.compaction`; no raw
  path/body/prompt appeared.
- Langfuse `3.225.15` self-hosted (web + worker + Postgres + ClickHouse + Redis + MinIO):
  `langfuse_export.py` POST returned HTTP 200; trace `dsh.run` visible with
  `gen_ai.chat`, `tool.call`, `dsh.compaction` observations; no secret strings found.
- Instrumented example plugin: Node execution with the pinned OpenTelemetry packages
  produced `dsh.plugin.run` and `dsh.tool` spans in the collector. This used a minimal
  fake `ctx`, not a full dsh host session.
- Langfuse API is eventually consistent; the integration test polls. A trace can appear
  before its child observations.

## Real dsh host plugin load (2026-10-31)

A local `@local/otel-dsh-plugin` was installed into a throwaway `otelweb` profile
(`dsh plugin add file:...`), inserted by a profile patch, and the `dsh web` host was
booted on port 3099. The collector received `dsh.plugin.run` with
`dsh.plugin.name=otel-dsh-plugin` and `dsh.plugin.host=dsh-web`. This verifies that a
real dsh host loads the instrumented plugin; the web listener itself was not kept up.

- Real dsh web host loaded `@local/otel-dsh-plugin` and registered `otel_echo`; the collector span had `dsh.tool.registered=true`. This verifies host plugin/tool registration, not a model-invoked tool call.

## Real model tool call (2026-10-31)

A real dsh session loaded `@local/otel-dsh-plugin` from `/work/plugin/index.js` and the model called `otel_echo` with `hello from dsh`; the case graded 4/4 and the collector received `dsh.tool` with `tool.name=otel_echo`. The tool uses a JSON Schema parameter object; the earlier non-schema form was rejected by the provider.
