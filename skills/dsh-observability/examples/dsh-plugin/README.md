# Real dsh plugin with a startup span

This plugin is loaded by a dsh web host. Its `apply(ctx)` creates a provider, emits
`dsh.plugin.run`, and flushes to the OTLP collector. It contains no tool/prompt data.

Install into a throwaway profile:

```sh
export DSH_HOME=$PWD/.tmp/dsh-home
export PNPM_HOME=$PWD/.tmp/pnpm-home
dsh plugin --profile otelweb add "file:$PWD/skills/dsh-observability/examples/dsh-plugin"
```

Add the row if the plugin manager did not insert it:

```yaml
- insert:
    - id: otel-dsh-plugin
      name: '@local/otel-dsh-plugin'
```

Boot:

```sh
dsh --profile otelweb web --port 3099
```

The collector should show `dsh.plugin.run` with:
`dsh.plugin.name=otel-dsh-plugin`, `dsh.plugin.host=dsh-web`.
