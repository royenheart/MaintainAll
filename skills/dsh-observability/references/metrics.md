# Metric definitions

- **uncached**: `inputTokens + outputTokens`; use this for new-token cost.
- **total**: `inputTokens + outputTokens + cacheReadTokens + cacheWriteTokens`; the
  provider's total includes cache reads/writes as separate fields.
- **uncached**: `inputTokens + outputTokens`; report it separately from cache.
- **dsh cache hit rate**: `cacheReadTokens / (inputTokens + cacheReadTokens + cacheWriteTokens)`;
  the dsh usage event reports cache as separate counters. For Codex, cached input is a
  subset of input, so use `cached_input_tokens / input_tokens` there.
- **tool p50/p95**: call→result elapsed time for matched `callId`s; includes shell jobs.
- **model time (approx)**: event wall span minus matched tool time; an approximation,
  not provider-reported latency.
- **calls before first edit**: index of the first `write`/`edit`/`apply_patch` call.
- **verification calls**: bash commands containing test/build/typecheck/dump-config/
  npm pack/install/uninstall.
- **reference reads**: `read` calls whose target contains `/references/`; count and
  bytes from tool results.
- **compaction**: count of `compaction/*` events; summary characters; shadowed events
  from `compaction/prune.data.shadowedSeqs`.

Do not compare total tokens across different context-window/cache conditions without
reporting input, output, and cache separately.

## Exact percentile and tie convention

`session_metrics.py` is the source of truth for its output. It sorts matched latencies and takes
`pct(p) = latencies[min(n - 1, int(n * p))]`. This is not the same as nearest-rank
(`ceil(p * n)` 1-based) or linear interpolation. For 900 samples, the script's p95 index is
`int(900 * 0.95) = 855` (0-based), while nearest-rank and R-7 can produce a different value.

- Quote `tool_latency_ms_p50` / `tool_latency_ms_p95` exactly as the script prints them.
- If you need another convention, label it explicitly (`nearest-rank`, `R-7`) and do not put it
  in the script-named field.
- `tool_by_name` uses `Counter.most_common` order. When counts tie, `top_tool` is not unique;
  report the tie and the full tied set instead of picking an alphabetical or arbitrary winner.
