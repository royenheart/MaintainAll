# Testing

Tests are `node --test` under `tests/`. `src/core/` has no dsh imports and is tested directly. Trigger sources are tested with fake emitters and streams; dispatch is tested with a fake `agents` face and save tests with a fake `sessions` face.

## Coverage by area

| Area | What tests prove |
|---|---|
| `core/manifest` | schema validation, version compatibility, scalar metadata types, continuation binding shape; checksum mismatch is covered through import in `core/opskit` |
| `host` | `ReplayRuntime.resolveSourceSession` reuses a live Agent, fails closed for an archived or subagent-owned source Session (live or activated), activates a cold Session through the embedding's reminder activation compatibility bridge (`schedule/resolve-agent` waterfall handler or the Web controller fallback), fails closed without an activation provider, and wraps activation failures |
| `core/seed` | boundary cut and open-turn trim, durable-event retention, tool-call argument remap, history/payload preservation, changed-stream clearing, context filtering, cwd bounds, real-envelope unavailable-tool filtering, exact serialized byte measurement, compact size, and the latest fitting turn boundary |
| `core/storage` | atomic write, registry index integrity, corrupted-state handling, dsh-compatible home resolution |
| `triggers/schedule` | legacy cron parse, fixed-offset next-fire, star-based day rule |
| `triggers/schedule-time` | IANA zones, DST gap/overlap, daily/weekly/every/after/at, selector rejection, rule identity |
| `engine` | committed-target persistence, stale-tick cancellation, restart catch-up, one-shot completion, source filters, rate state, ops preset patch watcher setting |
| `triggers/filewatch` | delta reads, baseline priming, byte-count reader shape, rotation, regex filter |
| `triggers/docker` | event stream parse (native capitalization and aliases), container glob, action filter |
| `triggers/journald` | journalctl JSON parse, unit/priority/regex filters |
| `triggers/webhook` | route match, bearer token, malformed body rejection |
| `triggers/normalize` | legacy filewatch/exec params move into `filter`; old webhook `/hooks` values are discarded; existing filters win |
| `triggers/exec` | output and exit-code edge detection |
| `triggers/condition` | CEL allow/deny, type errors, non-whitelisted function rejection |
| `triggers/rate` | min interval, max per hour (zero = no cap), persisted state |
| `dispatch` | run cwd materialization, existing-id refusal, trigger validation and its accepted-source error, `agents.create` arguments, producer-owned first `UserMessage`, permission preset, title, rollback, failed-preflight cleanup, seed-budget preflight with measured bytes and compact/fitting-boundary alternatives, `ops_save_task` trigger schema/guide/examples, save-prompt seed and continuation lines, continuation dispatch (live/source resolver only, no run cwd or seed, run-map source session, archived/deleted/registry-read/publish rollback), continuation save binding (fresh-only, no seed, no preset binding, mode-aware default runbook) |
| `core/http` | JSON response headers pin `cache-control: no-store` for both success and error bodies |
| `client` | pure schedule form params/legacy preservation/at shape, source-field/filter mapping, save request payloads (continuation forces fresh and is absent from both edit requests), i18n key symmetry (including continuation copy), API GET cache bypass, POST helper method/body/error contract; slot, dialog, Ops panel, and host-error rendering have no runtime test |

## Rules

- Trigger tests never call real clocks, sockets, or filesystem watchers unless the test is marked e2e and self-skips.
- `tests/engine/ops-preset.test.ts` parses `preset/ops.patch.yml` and pins the declaration, persona prompt-variable allowlist, required todo/plan-mode config fields, watcher fields, and reminder tool. It does not prove that a real profile activates the preset or that `package.json` ships the patch. Run-cwd tests pin the empty-skills omission and the non-empty copy.
- A behavior change updates or adds targeted tests in the same change. Verify the files covering the touched module; the full suite is a release gate, not the edit loop.
- Client i18n tests enforce that `zh` and `en` have identical key sets and matching placeholders. `tests/client/api.test.ts` stubs `fetch` and pins that every GET goes out with `cache: 'no-store'` (a deployment proxy may cache the `/plugins/<package>/` prefix as immutable assets) and that the POST helpers keep their method, body, and error contract. The Ops panel and Save dialog have no React/runtime test; the `/save` route preflight and continuation checkbox are exercised through pure request builders, `summarizeSessionSeed`/`buildTaskSeed`, prompt tests, and dispatch fakes, not through a live host. Route ordering, `editTaskId` combinations, registered-tool re-save behavior, and the rendered checkbox itself remain unverified without a live host or React test. Continuation activation through the real Web `sessionController` or a real SDK schedule handler has no end-to-end test; ownership is covered structurally (the resolver test proves the runtime never calls plugin-owned create/resume and never returns a handle for provider activation). The management-route trust fence, exec subprocess, live profile preset activation, and the proxy cache headers themselves have no end-to-end test.
- Seed tests cover executable tool-call argument remapping, JSON/Windows escaping, path-field containment, unchanged history/meta/streams, regenerated-context filtering, and cwd bounds; normalize tests cover path-only legacy webhook filters and `params: null`; save validation covers webhook token typing.
