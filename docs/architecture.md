# Architecture

MaintainAll is a dsh plugin that records successful ops sessions into reusable task assets and replays them when deterministic triggers fire. This document is the current-state authority for the code under `src/`; design rationale lives in historical decision records under `.agents/skills/maintainall/decisions/implemented/`.

## Components

```
┌─ dsh host ─────────────────────────────────────────────────────┐
│  tools registry · sessions · skills · slots · locale           │
│                                                                │
│  @royenheart/dsh-plugin-maintainall                            │
│  ├── src/index.ts        host service wiring the trigger engine           │
│  ├── src/engine/         trigger engine lifecycle (dependency-free)       │
│  ├── src/client.ts       client entry: slots/locale/styles     │
│  └── src/core/           pure logic, no dsh imports            │
│                                                                │
│  $DSH_HOME/@royenheart/dsh-plugin-maintainall/                 │
│  ├── ops/<task-id>/      task assets + runs                    │
│  └── storages/           state, logs, exports                  │
└────────────────────────────────────────────────────────────────┘
```

## Persisted state

The plugin uses local JSON state under `storages/` and file assets under `ops/`; there is no relational database. State files are written atomically by the host and are not a second source of task content.

- `registry.json` is the task index: id, name, version, enabled, imported time, last run, icon, and color. Task assets under `ops/<task-id>/` are authoritative for content; the index is updated by save/edit/import/toggle/delete and refreshed after dispatch. Manifest icon, color, and naturalPrompt values are validated as strings before they enter this index.
- `trigger-state.json` is engine-owned and version 2: per-trigger rate state, committed schedule targets, per-trigger/per-path filewatch offsets, and exec edge state. A version-1 file retains its `triggers`, `schedules`, and `exec` sections, but its path-keyed `filewatch` offsets cannot be attached to a trigger id safely, so that section is discarded on first read and the next poll establishes a fresh baseline. The retired v1 `journald` cursor section is also dropped.
- `run-map.json` maps run ids to task/session/cwd records for the Ops panel. Deleting a task removes its runs and trigger state.
- `storages/logs/` and `storages/exports/` hold generated logs and export archives; they are not authoritative state.

Empty/default sections are created on load. A task is materialized once; re-saving through `ops_save_task` preserves the seed, skills, scripts, runs, requirements, and bindings, while updating the manifest, `AGENTS.md`, and triggers.

## Package layout

```
src/
├── index.ts            host entry: maintainall service, lifecycle, HTTP routes
├── client.ts           client entry: locale, styles, slot registration
├── client/
│   ├── api.ts          bounded host HTTP helpers and route base
│   ├── shared.ts       Save/Ops shared task types and selectors
│   ├── save-dialog.ts  Save capsule and create/edit modal
│   ├── ops-panel.ts    Ops main panel, task list, run history, actions
│   ├── settings-log.ts settings-page plugin log viewer
│   ├── schedule-form.ts pure Save-dialog schedule form helpers
│   └── trigger-fields.ts source-field/filter mapping
├── core/
│   ├── contract.ts     shared task/trigger/event types
│   ├── manifest.ts     task manifest schema, validation, checksums
│   ├── seed.ts         compact seed extraction and rewrite
│   ├── storage.ts      plugin data root, atomic JSON files
│   ├── logger.ts       plugin-owned JSONL log
│   ├── task-writer.ts  task asset write/read under ops/<task-id>/
│   ├── opskit.ts       opskit zip export/import, stored-ZIP codec
│   └── triggers/
│       ├── event.ts    normalized TriggerEvent
│       ├── condition.ts CEL evaluation and whitelist
│       ├── schedule.ts legacy cron parsing and fixed-offset next-fire
│       ├── schedule-time.ts IANA schedule rules, DST resolution, selectors
│       ├── normalize.ts legacy trigger-field normalization
│       ├── filewatch.ts log delta polling and rotation handling
│       ├── docker.ts   docker event stream client
│       ├── journald.ts journalctl JSON stream parser
│       ├── webhook.ts  HTTP listener and token check
│       ├── exec.ts     command output/exit edge detector
│       └── rate.ts     debounce and rate limiting
├── host/
│   ├── task-state.ts   registry/run-map ownership and atomic persistence
│   ├── replay-runtime.ts replay Agent creation and bounded handle retention
│   └── trigger-runtime.ts trigger engine + source listeners lifecycle
├── engine/
│   ├── trigger-engine.ts host-facing trigger lifecycle: source listeners ->
│   │                     filter -> CEL when -> rate limit -> injected dispatch
│   ├── schedule-time.ts pure schedule-time resolver
│   ├── listeners.ts    docker/journald child listeners and teardown
│   └── state.ts        trigger-state.json load/save helpers
├── dispatch/
│   ├── run-cwd.ts      run workspace materialization
│   ├── replay.ts       agent/session creation, preset/title/rollback
│   ├── save.ts         task materialization and trigger validation
│   ├── load-task.ts    task asset loading for dispatch
│   └── session.ts      session.create seed assembly
└── locales/
    ├── keys.ts         key union
    ├── zh.ts
    ├── en.ts
    └── index.ts
```

## Host service

The host service is the composition root. It delegates registry/run-map persistence to `host/task-state.ts`, replay Agent creation/handle retention to `host/replay-runtime.ts`, and trigger engine/listener lifecycle to `host/trigger-runtime.ts`; the service retains lifecycle wiring and the HTTP/tool surface.

The host service owns:

- Lifecycle of the trigger engine: starting and stopping watchers for enabled tasks.
- Task asset API: save, list, detail, edit (manual metadata edit and natural-language edit session), run, delete, export, import, trigger enable/disable. The materialize `POST /save` path refuses an id that already exists; auto saves queue an LLM save turn, and other `/save` requests are rejected; the `ops_save_task` re-save path and manual edit preserve the existing seed, skills, scripts, runs, `requires`, `bindings`, and omitted `icon`/`color`/`naturalPrompt` fields. Re-save does not rewrite skills/scripts from `ops_save_task` arguments; change those files directly. A metadata-only re-save with empty `instructions` keeps the existing AGENTS.md; creation still derives a minimal runbook from name and description.
- Every management route except the token-authenticated `/webhook` endpoint applies dsh's `connection.requestRejection` Host/Origin/authentication fence before reading a body or mutating state. The fence covers task, run, edit, delete, export, import, logs, and trigger-toggle routes.
- Trigger validation: every trigger is shape-checked, source-required filters are enforced, schedule rules are parsed and their first target computed, and trigger ids are non-empty, exclude the reserved object-prototype names, and are unique across tasks; webhook trigger ids must additionally match `^[A-Za-z0-9][A-Za-z0-9._-]*$` before a save, edit, or `ops_save_task` write. Docker `filter.events` must be an array of non-empty strings and `filter.container` a non-empty string. Host task/trigger write endpoints and the save tool are serialized, so concurrent saves/imports/toggles cannot interleave their id check with another write; dispatch bookkeeping is outside that lock. A failed trigger-toggle reload restores the previous enabled flag and trigger flags.
- Dispatch: fail-closed permission-preset preflight, run cwd creation, seed rewrite, `ctx.agents.create` with the task's agent preset, permission-preset application, session title, and first-message injection. A failure before a run is recorded removes the fresh run cwd; a failure after creation disposes the unpublished handle. Once the trigger message is published, a later bookkeeping failure keeps the live run (the run-map/registry entry may be incomplete).
- Save and replay use the dsh 0.2.1-rc.3 contracts: `Session.snapshotEvents()` for the seed and a complete `UserMessage` (`id`, `role`, `content`, `source`); the source kind is producer-owned `plugin:maintainall`. dsh marks `snapshotEvents()` deprecated for new callers, so migrating to its replacement is a future compatibility task.
- `requires.mcpServers` is validated and carried, but replay does not mount MCP servers yet; a task that requires one can start without its tools. `requires.dsh` and `requires.secrets` are validated and carried only; replay does not enforce the dsh version or resolve/supply secrets.

The service resolves `$DSH_HOME` with dsh-compatible rules (tilde expansion, whitespace-as-unset, absolute normalization) and never writes to dsh-owned directories.

## Client surfaces

- `conversation.session.header.utilities` slot, `order: -1`: Save button, same capsule style as the Session log download.
- Save dialog: collects task metadata, creation mode (`safe-copy` / `compact` / `fresh`; `auto` is a request mode for the model path), icon/color, trigger source/parameters, CEL condition, and debounce/rate limits. It edits the first trigger and preserves all other triggers and their ids/enabled flags on save. The mode is fixed during edit; manual edits update metadata in place and natural-language edits open a fresh session. There are no run-environment or secret fields. All client copy is registered once under the `maintainall` locale namespace from `src/locales/index.ts`; components only reference keys, with `src/locales/keys.ts` as the completeness authority.
- `sidebar.panellist` + `main`: one Ops main panel and its sidebar entry render a two-level tree of tasks and their runs, with pagination and per-task run/edit/toggle/delete actions. This is the plugin's only Ops surface; there is no footer action or fixed right drawer.

## Task asset format

`manifest.yml` is the single source of truth for a task's identity and compatibility:

```yaml
format: dsh-opskit/1
id: <task-id>
name: Restart nginx
version: 1.0.0
description: Restart nginx when its config changes
taskMode: safe-copy | compact | fresh
icon: <emoji>
color: <css-color>
naturalPrompt: <original natural-language description>
requires: { dsh: ">=x.y", tools: [...], mcpServers: [...], secrets: [...] }
bindings: { agentPreset: { hint: ops }, permissionPreset: { hint: readonly } }
checksums: { ... }
```

A legacy persisted `taskMode: auto` is read as `fresh` (the old mode also materialized without a seed); new writes accept only `safe-copy`, `compact`, or `fresh`. `taskMode` is captured at creation time and is immutable for the life of the task: `safe-copy` stores the full durable seed, `compact` stores only the compacted seed (reasoning blocks and timed streams stripped), and `fresh` stores no seed. `auto` is only a request mode: it lets the model choose one of those three before the first save. Edits never re-cut the seed; to recapture a trajectory, delete the task and re-create it from a real ops session.

`seed/session.jsonl` stores only durable events: `turn/start`, `step/start`, `user/message`, `assistant/message`, `tool/call`, `tool/result`, `step/end`, `turn/end`. A save boundary is trimmed to the last `turn/end` at or before the requested sequence, so an open turn cannot produce a constructor seed with a dangling tool call; no completed turn means an empty seed. Import normalizes legacy trigger `params.path`/`params.command` before validating and writing, then rewrites machine-local manifest bindings; the captured seed paths are preserved as-is. Docker event JSON is normalized from the native `Type`/`Action`/`Actor.Attributes` spelling, with lowercase aliases accepted for existing fixtures. Import rejects archives over 64 MiB, more than 4096 entries, more than 128 MiB of uncompressed data, duplicate entry names, directory entries with data, and CRC/checksum mismatches. Export enforces the archive/entry/uncompressed caps against the actual ZIP header size, so it cannot emit an archive that the importer rejects for size. Replay filters tool calls only when `requires.tools` is declared; without a declaration it preserves the captured tool history rather than guessing a fallback allowlist. It also drops capture-session environment context that dsh regenerates (`snapshot`/`catalog` user messages, `agent-instructions`, and cleared `runtime-context`) before remapping paths.

Replay remaps the seed header cwd and executable `tool/call` argument JSON. Argument JSON is parsed; shell fields (`command`, `cmd`, `command_line`, `commandline`, `script`, `commands`) and legacy `tool/call.data.command` go through the bounded shell lexer, path-valued fields are replaced only when the whole string is the captured cwd or below it, and content/text/query and old/new text fields, including nested payload objects, are left byte-identical. The matching arguments in assistant `tool-call` blocks receive the same replacement; a changed assistant message clears its timed stream. Tool results, tool-private `meta`, user/assistant prose, provider state, and all other event data remain historical evidence and are not rewritten. Replay adds a first-message note that executable paths were remapped while captured output and prose may mention the original workspace.

The shell lexer is best-effort for command fields only; heredocs, remote/container execution, PowerShell/cmd dialects, aliases, and variable-concatenated paths are not guaranteed. A shell argument that contains the captured cwd is rejected when the replay cwd contains shell metacharacters, rather than substituting a path that would split or execute as shell syntax. Percent-encoded matching applies only at local `file:` URI path positions; ordinary percent-containing filenames are not decoded, and replacement URIs encode reserved filename characters. Path comparison uses the captured platform (POSIX or Windows) and never guesses cross-platform forms. Parsed seeds are bounded to 16 MiB, 100,000 events, and a 4 KiB absolute cwd; command or raw argument strings over 2 million characters are left untouched rather than scanned, and argument JSON traversal stops at depth 64. Relative cwds, filesystem roots, and cwds containing NUL/CR/LF are rejected. Argument JSON with numeric literals outside JSON strings that would lose value is left untouched rather than re-serialized.

## Trigger pipeline

Sources are `schedule`, `filewatch`, `docker`, `journald`, `webhook`, and `exec`; `manual` is an event-only source used by `POST /tasks/<id>/run`. A manual run dispatches directly and does not apply the trigger filter, CEL `when`, or rate limits.

Each source is a typed listener that emits normalized `TriggerEvent` JSON. Source-native filters run first to avoid waking the condition evaluator for every event. The Save dialog writes filewatch paths to `filter.path`, exec commands to `filter.command`, docker selectors to `filter.container`, journald selectors to `filter.regex`, and webhook bearer tokens to `filter.token`; a webhook path is optional and, when present, must equal the full request pathname (empty matches any path for the trigger id); every webhook trigger requires a non-empty bearer token. Legacy `params.path`/`params.command` are normalized on task read and on every trigger write; the old `/hooks/...` webhook value is discarded. The CEL `when` expression then evaluates over the event. Debounce and rate limits apply per trigger id and persist their state to `storages/trigger-state.json`; `maxPerHour: 0` means no hourly cap. Exec commands run through a bounded host subprocess (60 s timeout, 1 MiB output, plugin data root cwd).

Legacy `cron` strings with `timezoneOffsetMinutes` and legacy trigger `params.path`/`params.command` shapes remain readable for assets written before 0.1. They are compatibility only: remove those branches after an asset scan finds none of those shapes and no `/hooks/...` webhook path remains.

The `schedule` source accepts exactly one rule per trigger: `cron` (IANA zone), `daily`, `weekly`, `everySeconds`, `afterSeconds`, or `at`. A legacy `cron` string with `timezoneOffsetMinutes` is a fixed-offset `cron-offset` rule; a bare legacy `cron` string with neither a zone nor an offset is also `cron-offset` at UTC and emits `payload.timezoneOffsetMinutes`, not `payload.timeZone`. Daily and weekly skip a DST-gap local time and use the earlier instant of an overlap; cron follows dsh's star-based day-of-month/day-of-week rule. The engine persists a committed `scheduledAt` per trigger in `schedules` inside `trigger-state.json`; a rule change resets it. Deleting a task clears its id-keyed trigger state, including filewatch offsets. A recurring target that is overdue when the Host starts fires once with the committed target, then advances strictly past `now`; `everySeconds` keeps its committed cadence. A one-shot is marked done when its committed instant is reached, before CEL/rate admission, so a rejected one-shot is consumed rather than retried. The committed target is rolled back in memory if its state persistence fails, so a disk error does not silently consume a one-shot.

The trigger path makes no LLM call. After dispatch, the new session's agent decides how to execute the runbook. On first observation of a filewatch path, the poller adopts the current file size without reading historical content; later polls read complete lines from the persisted byte offset. The reader returns raw-byte consumption, so invalid UTF-8 cannot shift the offset. A filewatch offset is committed after the batch has been processed; a runtime condition or rate-state error on one line is logged and does not abort the remaining lines.

## Concurrency and teardown

Trigger timers, docker/journald child-process listeners, and HTTP routes are owned by the service lifecycle. A schedule trigger whose params or first target cannot be built fails engine startup; docker/journald spawn or stream failures are logged and leave that source unavailable without failing the engine. An initialization failure releases routes, the tool, listeners, and the engine before rethrowing; route/tool registration is inside that cleanup boundary. On shutdown the engine stops accepting new ticks first, then the listeners close their readline interfaces, send SIGTERM, wait briefly, and escalate to SIGKILL; routes and the tool unregister, and retained agent handles are released. The handle map is capped at 256 entries and drops a Session on `session/disposed`, so an archived Session that never disposes cannot grow it without bound.

The plugin registers no inotify watches: the `filewatch` source polls `stat` and reads from the persisted byte offset, and no `fs.watch`/Chokidar dependency exists. A replayed run is watched by dsh's `skill-filesystem` only when its resolved agent preset watches `skill-filesystem` and the run cwd becomes a project root. The plugin bundle patch array registers the `ops` preset through [`preset/ops.patch.yml`](../preset/ops.patch.yml); a task without an explicit `agentPreset` binding resolves `ops` by default. A missing or broken implicit `ops` preset falls back to the deployment default with a log (the default may retain its watcher); an explicit binding fails closed. Edit sessions use the deployment default unless the task has an explicit binding. The `ops` preset disables the watcher (`watch: false`, cap 8), and [`createRunCwd`](../src/dispatch/run-cwd.ts) omits an empty `.agents/skills/`.
