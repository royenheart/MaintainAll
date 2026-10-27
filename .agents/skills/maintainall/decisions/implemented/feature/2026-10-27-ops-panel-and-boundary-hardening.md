# Decision: Ops main panel and replay boundary hardening

Status: implemented — the Ops surface is one sidebar panel and the trigger/seed boundaries fail closed

## Problem

The Ops surface used a sidebar footer action plus a fixed right drawer, duplicating navigation that dsh already models as a sidebar panel. The host management routes were registered without dsh's connection trust fence, so a cross-origin request could reach task mutation and `exec` triggers. The replay path also accepted cwd remappings that a shell would split, constructor seeds cut inside an open turn, Docker JSON under the wrong field casing, filewatch offsets derived from decoded strings, and schedule state that could be consumed by a failed persistence write. Trigger ids and docker filter shapes were accepted without the constraints the engine required.

## Decision

- The client registers one `sidebar.panellist` entry and one `main` panel. There is no footer action and no fixed right drawer. All visible strings come from the single `maintainall` locale namespace; `src/locales/keys.ts` is the key authority and `src/locales/index.ts` registers both dictionaries. The locale registration and stylesheet are released through `ctx.effect`.
- Every management route except the token-authenticated webhook route calls `connection.requestRejection` before reading the body. The host injects `connection` and keeps the fence at the route boundary.
- A replay seed is cut at the last `turn/end` at or before the requested boundary; an empty completed-turn prefix stays empty rather than producing a dangling tool call. Compact mode clears the timed stream as well as reasoning blocks.
- Docker event JSON is normalized from native `Type`/`Action`/`Actor.Attributes` spelling, with lowercase aliases retained for existing assets/tests. A missing container filter name matches nothing.
- Filewatch adopts the current EOF on first observation without reading history. Reads return the complete-line text plus raw byte consumption, so offsets cannot drift on invalid UTF-8.
- A shell argument containing the captured cwd is rejected when the replay cwd contains shell metacharacters; silently substituting a path that the shell would split is not acceptable.
- Schedule targets are persisted before dispatch but rolled back in memory when persistence fails. Source accept errors are isolated per trigger/line so one bad condition does not starve other triggers.
- Trigger ids are non-empty, non-reserved, and unique across tasks; webhook ids are URL-safe; docker filter types and manifest icon/color/naturalPrompt types are validated before write.
- Current-state behavior lives in [docs/architecture.md](../../../../../../docs/architecture.md); tests remain scoped by [docs/testing.md](../../../../../../docs/testing.md).

## Alternatives considered

- Keep the footer/drawer and add a panel: rejected because it leaves two Ops navigation surfaces with the same state.
- Inject the panel into the native Automation tasks page: rejected because dsh has no generic automation-provider extension point; the native page is schedule-specific.
- Quote shell cwd replacements: deferred because POSIX/PowerShell/cmd quoting cannot be made reliable across the captured dialect; failing closed avoids a wrong working directory or command.
- Regenerate a dangling turn in the seed: rejected because dsh owns turn repair and a constructor seed must be a durable prefix, not a synthesized turn.

## Consequences

- Users navigate Ops from the sidebar; the panel owns task/run actions and the save action stays in the session header.
- Management routes now reject unauthenticated/cross-origin requests; the webhook keeps its own token check.
- Tasks with dangerous shell cwd substitutions fail replay with an explicit seed-build error instead of running in the original workspace.
- The Ops panel remains separate from native Automation tasks because their execution/delivery contracts differ.
