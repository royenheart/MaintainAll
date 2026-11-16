# Decision: Deterministic trigger engine core

Status: implemented — trigger sources, CEL subset, and rate limiting shipped under `src/core/triggers/` with `node --test` coverage

## Problem

The trigger pipeline ([docs/architecture.md](../../../../../../docs/architecture.md#trigger-pipeline))
needs a deterministic, dependency-free core: every source produces a
normalized `TriggerEvent`, source-native filters run first, a CEL `when`
expression decides, and debounce/rate limits apply before dispatch. The LLM
never participates in the trigger decision, and none of this may import dsh
or node_modules packages so it stays testable per
[docs/testing.md](../../../../../../docs/testing.md).

## Decision

Nine modules under
[`src/core/triggers/`](../../../../../../src/core/triggers/), importing only the shared
contracts in [`contract.ts`](../../../../../../src/core/contract.ts) and each other via
`.ts` relative imports (Node 24 strip-only mode: no parameter properties or
other non-erasable syntax). The only non-erasable runtime constructs are
`RegExp`, JSON, string/number/date operations, and `Buffer.byteLength` in the
filewatch poller.

- [`event.ts`](../../../../../../src/core/triggers/event.ts): `normalizeEvent`
  validates source kind, RFC 3339 instant, and plain-object payload, and
  copies the payload so callers cannot corrupt the event.
- [`condition.ts`](../../../../../../src/core/triggers/condition.ts): hand-written
  tokenizer + recursive-descent parser + tree-walking evaluator for a CEL
  subset — literals, `event`/`payload`/`occurredAt`/`source` roots with dot
  access, `== != < <= > >=`, `&& || !`, parentheses, and the whitelisted
  functions `matches`/`startsWith`/`endsWith`/`contains`. Unknown
  identifiers, unknown functions, type mismatches (`&&` on non-booleans,
  `<` across types, non-string function arguments), trailing tokens, and
  non-boolean results all throw. Empty `when` returns `true`.
- [`rate.ts`](../../../../../../src/core/triggers/rate.ts): `RateLimiter` with
  injectable `now()`; `tryFire` prunes timestamps outside the rolling hour,
  checks `minIntervalSeconds` before `maxPerHour` (denials report
  `min-interval` first), mutates only on allow, and returns the state to
  persist. `peek` decides without mutating. `rateStateOf`/`withRateState`
  bridge to `TriggerState.triggers`.
- [`schedule.ts`](../../../../../../src/core/triggers/schedule.ts): 5-field cron
  parser (`*`, `*/n`, `a-b`, `a-b/n`, numbers, comma lists; day-of-week 7
  normalizes to 0) and `nextFire`, which searches day-by-day in the timezone
  given as `timezoneOffsetMinutes` and returns a UTC instant. Restricted
  day-of-month AND day-of-week use Vixie-cron OR semantics.
- [`filewatch.ts`](../../../../../../src/core/triggers/filewatch.ts):
  `FileWatchPoller` with injected `stat`/`read`; tracks a byte offset,
  resets to 0 on rotation (size shrink or inode change), holds back trailing
  partial lines, and applies an optional regex filter without stalling the
  offset. Debounce stays with the caller.
- [`docker.ts`](../../../../../../src/core/triggers/docker.ts): JSON-line parsing
  (null on malformed), `events` matching `type` or `status`, `*` glob on
  `actor.Attributes.name` with regex metacharacters escaped, and
  `toTriggerEvent` normalizing `{type, action, status, container, exitCode}`
  (numeric exit codes become numbers).
- [`journald.ts`](../../../../../../src/core/triggers/journald.ts): `journalctl -o
  json` line parsing (`_SYSTEMD_UNIT`, `PRIORITY`, `MESSAGE`,
  `__REALTIME_TIMESTAMP` micros → ISO) and filters where `priority` matches
  entries at least as severe (entry priority <= filter priority).
- [`webhook.ts`](../../../../../../src/core/triggers/webhook.ts): case-insensitive
  `Authorization` lookup and RFC 7235 case-insensitive `Bearer` scheme with
  exact token comparison (empty expected token never verifies), and
  `parseWebhookBody` returning the JSON value or null.
- [`exec.ts`](../../../../../../src/core/triggers/exec.ts): `ExecEdgeDetector` fires
  on first observation, stdout change, or exit-code change; stderr changes
  are recorded but never fire. The constructor restores persisted state
  without producing an edge, and `snapshot` exposes state for
  `TriggerState.exec`.

Tests live in `tests/triggers/` (9 suites, 67 tests) and run with
`node --test tests/triggers/*.test.ts`. They use fixed dates, injectable
clocks, and in-memory fake `stat`/`read` — no real sockets, servers,
filesystem, or timers.

## Alternatives considered

- **A real CEL library (`cel-js`, `@marcbachmann/cel-js`)**: rejected —
  `src/core/` must stay dependency-free per the standing orders, and a full
  CEL runtime also admits constructs (macros, comprehension, dyn) that a
  trigger whitelist should not have. A ~300-line evaluator over a closed
  grammar is auditable and throws on anything outside the subset.
- **Node `croner`/`cron-parser` for schedules**: rejected for the same
  dependency reason; day-by-day search with per-field match lists is
  O(days × hours × minutes) over a bounded 4-year horizon and fast enough
  for a trigger engine.
- **Minute-by-minute `nextFire` scan**: rejected — up to ~2M iterations for
  a Feb 29 schedule; the day/hour/minute nested search is exact and cheap.
- **AND semantics for restricted dom+dow**: rejected in favor of standard
  Vixie OR semantics so imported cron knowledge transfers; documented in
  the module header and pinned by tests.
- **Stderr changes firing the exec edge**: rejected — stderr is noisy
  (progress bars, warnings); the contract treats stdout and exit code as
  the signal. Stderr is still persisted for the run's context.
- **Timing-safe token comparison**: skipped deliberately — the trigger
  token gates a local automation endpoint, not a public API, and pulling in
  `node:crypto` for one comparison adds a builtin to an otherwise pure
  module. Documented here so the choice is revisited if the webhook
  listener is ever exposed beyond localhost.

## Consequences

- The host service can wire real IO (sockets, subprocesses, HTTP listener)
  onto these pure cores without changing them; dispatch and `triggers.yml`
  loading are the remaining pieces.
- Any change to the CEL whitelist, cron semantics, filter shapes, or edge
  rules must update the matching `tests/triggers/` suite in the same change.
- `npm run typecheck` covers the new modules once `npm install` provides
  `@types/node`; until then `Buffer`/`node:*` names error project-wide, as
  before this change.
