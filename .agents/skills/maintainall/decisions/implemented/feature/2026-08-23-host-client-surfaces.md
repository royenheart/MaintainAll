# Decision: Host entry, dispatch helpers, and client surfaces

Status: implemented — `src/index.ts`, `src/dispatch/`, `src/client.ts`, and `src/locales/` shipped with `node --test` coverage

## Problem

The pure core modules and trigger engine (see
[core modules](./2026-08-23-core-modules.md) and
[trigger engine core](./2026-08-23-trigger-engine-core.md)) had no host or
client surface: nothing owned the plugin data root at runtime, served the
browser, materialized run working directories, or assembled a replay session
seed. [docs/architecture.md](../../../../../../docs/architecture.md) assigns these to
`src/index.ts`, `src/dispatch/`, and `src/client.ts`.

## Decision

- [`src/index.ts`](../../../../../../src/index.ts): `MaintainAllService`, a Cordis
  `Service` named `maintainall` with
  `static inject = ['webServer', 'sessions', 'tools', 'logger']`
  (`ctx.logger` with a `console.warn` fallback), plus an `apply(ctx, config)`
  wrapper and a default export. On init it resolves the data root via
  `pluginDataRoot()` (`config.root` overrides it, for tests), creates
  `ops/` and `storages/`, and loads registry/trigger-state/run-map. HTTP
  routes under `/plugins/@royenheart/dsh-plugin-maintainall`: `GET /status`,
  `GET /tasks`, `POST /save` (validates `{ sessionId, boundarySeq, meta }`
  and appends a pending save request to a `pendingSaves` key inside
  `registry.json` — asset generation stays with the model), `POST /import`
  (501 placeholder), and a prefix route `/triggers/<taskId>/(enable|disable)`
  toggling the registry record and persisting.
- [`src/dispatch/run-cwd.ts`](../../../../../../src/dispatch/run-cwd.ts):
  `createRunCwd(root, taskId, now)` creates
  `ops/<task-id>/runs/<YYYYMMDD-HHMMSS>-<runid>/` and copies `AGENTS.md`,
  `.agents/skills/`, `scripts/` with `dereference: true` /
  `verbatimSymlinks: false` so run cwds contain plain files, never symlinks.
- [`src/dispatch/session.ts`](../../../../../../src/dispatch/session.ts):
  `buildSeedForRun` composes `rewriteSeedCwd` + `filterSeedTools` from the
  core; `firstUserMessage` renders the trigger event as JSON plus the
  `AGENTS.md` instruction. Session creation itself stays behind the exported
  `dispatchReplay` stub (`{ ok: false, error: 'session dispatch wiring
  pending' }`) until the sessions wiring pass.
- [`src/client.ts`](../../../../../../src/client.ts): `inject = ['slots', 'locale',
  'connection']`; registers the `maintainall` locale namespace, a
  `conversation.session.header.utilities` capsule (`id: 'maintainall-save'`,
  `order: -1`) opening a React-state modal that posts to `/save`, and a
  `sidebar.footer.action` entry (`id: 'maintainall-ops'`) opening a
  fixed-position drawer over `GET /tasks` with enable/disable toggles. No
  JSX; all strings via `ctx.locale.bind('maintainall')`.
- [`src/locales/`](../../../../../../src/locales/index.ts): `MAINTAINALL_KEYS` union
  with symmetric `zh`/`en` dictionaries; key-set and placeholder symmetry is
  enforced by [tests/client/i18n.test.ts](../../../../../../tests/client/i18n.test.ts),
  and run-cwd behavior by
  [tests/dispatch/run-cwd.test.ts](../../../../../../tests/dispatch/run-cwd.test.ts).

## Alternatives considered

- **Custom RPC via the apiproxy instead of HTTP routes.** The save dialog
  posts form-shaped data that has no host domain yet, and the web route
  registry is the established pattern for session-agnostic plugin endpoints
  (as in `dsh-plugin-mcp-support`); an RPC domain can come later with the
  dispatch wiring.
- **Persisting pending saves in a new storage file.** A host-local
  `pendingSaves` key inside `registry.json` survives the core
  load/save round-trip (`{ ...defaults, ...state }`) without widening the
  core contract, and the queue is logically part of registry state.
- **Symlinking task assets into run cwds.** Rejected: symlinks leak writes
  back into the asset and break when the asset is moved or archived; copies
  keep runs self-contained.

## Consequences

- The trigger engine and session-dispatch wiring can be developed against
  the stable `dispatchReplay` seam and the `/save` pending queue without
  touching these surfaces again.
- `node --test tests/client/i18n.test.ts tests/dispatch/run-cwd.test.ts`
  runs without `node_modules`; host/client entries are covered by
  `node --check` until dependencies are installed for `npm run typecheck`.
