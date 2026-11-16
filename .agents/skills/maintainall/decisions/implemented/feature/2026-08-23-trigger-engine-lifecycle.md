# Decision: Host-facing trigger engine lifecycle (`src/engine/`)

Status: implemented — `TriggerEngine` + state helpers shipped under `src/engine/` with `node --test` coverage in `tests/engine/`

## Problem

The pure trigger primitives under [`src/core/triggers/`](../../../../../../src/core/triggers/)
(cron math, pollers, parsers, edge detectors, rate limiters — see
[the trigger-engine-core note](2026-08-23-trigger-engine-core.md)) each cover
one source in isolation. The host still needs one object that owns the
lifecycle: enumerate enabled task triggers, run the right listener per source,
apply the source-native filter, evaluate the CEL `when`, enforce
debounce/rate limits, and only then hand off to dispatch — with all runtime
state persisted to `storages/trigger-state.json` and no LLM anywhere in the
decision path.

## Decision

[`src/engine/trigger-engine.ts`](../../../../../../src/engine/trigger-engine.ts)
exports `TriggerEngine`, built from `{ root, tasks, dispatch, now?,
scheduler?, exec?, filewatchIo?, pollIntervalMs? }`. Everything side-effecting
is injected: `tasks()` is re-read on `reload()`, `dispatch` is a callback (the
host wires session creation; tests fake it), `exec` runs exec-source
commands, `scheduler` arms intervals, `now` is the clock. The module imports
only node built-ins and `src/core/` — no dsh packages — so it runs under
`node --test` with a temp root.

- The host feeds observations: `onScheduleTick` / `onFilewatchTick` /
  `onExecTick` (also armed as intervals by `start()` at 1s and
  `pollIntervalMs` respectively), `onDockerEvent(line)`,
  `onJournaldLine(line)`, and `onWebhookRequest(triggerId, path, headers,
  body)` returning whether a dispatch happened. `stop()` clears intervals and
  flushes state; `reload()` rebuilds the trigger index, schedule next-fire
  map, filewatch pollers, and exec edge detectors from persisted state.
- Every source funnels into one `accept(taskId, trigger, event)` pipeline:
  `evaluateCel` on `when`, then a `RateLimiter` rebuilt from persisted
  `TriggerState.triggers[triggerId]` (rate state persisted *before* dispatch
  so a dispatch failure cannot re-arm inside the debounce window), then
  `dispatch`.
- Trigger field conventions: schedule reads `params.cron` +
  `params.timezoneOffsetMinutes`; filewatch reads `filter.path` (file, or
  base directory when `filter.glob` is set, resolved against `root`),
  `filter.recursive`, `filter.regex`; docker `filter.events`/`container`;
  journald `filter.unit`/`priority`/`regex`; webhook `filter.path`/`token`;
  exec `filter.command`.
- Filewatch treats the first poll of a path with no persisted offset as a
  baseline: it adopts the current end of file without emitting historical
  lines. Offsets persist after every poll, so restarts resume exactly.
- [`src/engine/state.ts`](../../../../../../src/engine/state.ts) wraps the core
  storage functions to load/save `TriggerState` with all default sections
  guaranteed present.

## Alternatives considered

- **Host owns scheduling, engine is tick-only.** Rejected: arming the 1s
  schedule tick and poll intervals inside `start()` keeps `src/index.ts`
  thin while the injected `scheduler` keeps tests deterministic.
- **Emit existing file content on first filewatch poll.** Rejected: a fresh
  trigger would fire on historical log lines at every state loss; the
  baseline poll matches how log shippers behave, at the cost of one primed
  flag per path.
- **Per-source engine classes.** Rejected: one class with a shared `accept`
  pipeline keeps the filter → CEL → rate-limit ordering in exactly one
  place; the sources differ only in how they produce `TriggerEvent`s.

## Consequences

- `npm test` now includes `tests/engine/*.test.ts` (11 tests covering all six
  sources, debounce, hourly caps, restart persistence, and reload).
- `src/index.ts` can wire the engine with real timers, a filesystem
  `filewatchIo` default, and a dispatch that calls into `src/dispatch/`;
  webhook/docker/journald transports stay host-side and just call the
  `on*` feeders.
- Duplicate enabled trigger ids fail loud in `rebuild()`; a schedule trigger
  without `params.cron` throws at `start()`/`reload()` rather than silently
  never firing.
