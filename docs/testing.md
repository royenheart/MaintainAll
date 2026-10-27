# Testing

Tests are `node --test` under `tests/`. `src/core/` has no dsh imports and is tested directly. Trigger sources are tested with fake emitters and streams; dispatch is tested with a fake `agents` face and save tests with a fake `sessions` face.

## Coverage by area

| Area | What tests prove |
|---|---|
| `core/manifest` | schema validation, version compatibility, scalar metadata types; checksum mismatch is covered through import in `core/opskit` |
| `core/seed` | boundary cut and open-turn trim, durable-event retention, tool-call argument remap, history/payload preservation, changed-stream clearing, context filtering, cwd bounds, real-envelope unavailable-tool filtering |
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
| `dispatch` | run cwd materialization, existing-id refusal, trigger validation, `agents.create` arguments, producer-owned first `UserMessage`, permission preset, title, rollback, failed-preflight cleanup |
| `client` | pure schedule form params/legacy preservation/at shape, source-field/filter mapping, i18n key symmetry; slot, dialog, Ops panel, and host-error rendering have no runtime test |

## Rules

- Trigger tests never call real clocks, sockets, or filesystem watchers unless the test is marked e2e and self-skips.
- `tests/engine/ops-preset.test.ts` parses `preset/ops.patch.yml` and pins the declaration, persona prompt-variable allowlist, required todo/plan-mode config fields, watcher fields, and reminder tool. It does not prove that a real profile activates the preset or that `package.json` ships the patch. Run-cwd tests pin the empty-skills omission and the non-empty copy.
- A behavior change updates or adds targeted tests in the same change. Verify the files covering the touched module; the full suite is a release gate, not the edit loop.
- Client i18n tests enforce that `zh` and `en` have identical key sets and matching placeholders. The Ops panel and Save dialog have no React/runtime test; the management-route trust fence, exec subprocess, and live profile preset activation have no end-to-end test.
- Seed tests cover executable tool-call argument remapping, JSON/Windows escaping, path-field containment, unchanged history/meta/streams, regenerated-context filtering, and cwd bounds; normalize tests cover path-only legacy webhook filters and `params: null`; save validation covers webhook token typing.
