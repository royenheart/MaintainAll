# Decision: IANA schedule selectors and replay hardening

Status: implemented — IANA/DST schedule targets, source-filter normalization, replay rollback, and a bundle-declared ops preset; live profile activation remains a verification limitation

## Problem

The `schedule` trigger only accepted a five-field cron string plus a fixed
`timezoneOffsetMinutes`. That could not express a daily or weekly wall-clock
rule, silently ignored DST, and stored no committed target: every restart
recomputed from "now", so an occurrence missed while dsh was down disappeared.
The Save dialog and the `ops_save_task` tool wrote trigger params without
validation, so a malformed rule surfaced later as an engine start failure.
Separately, replay dispatch honored the manifest's `agentPreset` hint but
ignored `permissionPreset`, never titled the new Session, and left an
unpublished Agent behind when the first message failed.

## Decision

- [`src/core/triggers/schedule-time.ts`](../../../../../../src/core/triggers/schedule-time.ts)
  parses exactly one selector — `cron`, `daily`, `weekly`, `everySeconds`,
  `afterSeconds`, or `at` — and computes fire instants in an explicit IANA
  zone. Daily and weekly skip a local time inside a DST gap and choose the
  earlier instant of an overlap. Cron keeps dsh's Vixie day rule: a field
  whose source text starts with `*` is a star, so `*/2` restrains the other
  day field instead of switching to OR semantics. A legacy cron string plus
  `timezoneOffsetMinutes` remains a `cron-offset` rule and uses the existing
  fixed-offset arithmetic; a bare legacy cron string with neither field is
  `cron-offset` at UTC. Current-state behavior lives in
  [docs/architecture.md](../../../../../../docs/architecture.md).
- [`src/engine/schedule-time.ts`](../../../../../../src/engine/schedule-time.ts) exposes
  a small `ScheduleTime` resolver over the pure core. The host uses that single
  resolver; tests may inject one, but production has no dynamic adapter or
  fallback.
- `trigger-state.json` gains a `schedules` map keyed by trigger id with the
  committed `scheduledAt`, the normalized `ruleKey`, and a `done` flag. A rule
  change resets the target; deleting a task clears its id-keyed schedule/rate/
  filewatch/exec state. A
  tick captures its generation and per-entry state so a reload cannot let a
  stale tick mark a replacement one-shot done. A recurring rule fires once
  with its committed target, then advances strictly past `now`; `everySeconds`
  preserves its committed cadence. A one-shot is marked done when its
  committed instant is reached, before CEL/rate admission.
- The Save dialog offers the six selectors with an IANA zone input backed by
  `Intl.supportedValuesOf('timeZone')` when available. It preserves the stored
  `params` verbatim until a schedule field is edited, keeps local `at` date/time
  shapes, and surfaces the host's rejection instead of closing as if saved.
  For non-schedule sources it writes the host contract (`filter.path` for
  filewatch, `filter.command` for exec, `filter.container`/`filter.regex` for
  docker/journald) while preserving other filter fields. A webhook path is
  optional and must be the full request pathname; the old `/hooks/...` value is
  discarded. Manual edit preserves the first trigger's id/enabled flag and all
  other triggers. The host validates trigger shape, required filters, duplicate
  ids, and the schedule first target before writing in `materializeTaskFromSave`,
  `materializeTaskEdit`, and `ops_save_task`; ids are also checked against all
  other tasks. A failed trigger toggle restores the previous flags.
- The plugin bundle patch array loads
  [`preset/ops.patch.yml`](../../../../../../preset/ops.patch.yml), which declares the
  `ops` agent preset with valid persona/todo/plan-mode configs and
  `skill-filesystem` watching disabled. A task without an explicit
  `agentPreset` binding resolves `ops` by default; a missing or broken `ops`
  preset falls back to the deployment default with a log; an explicit binding
  fails closed. Edit sessions use the deployment default unless the task has an
  explicit binding.
- Replay dispatch resolves the manifest's `permissionPreset` before creating
  the Agent and applies it before the first message, sets a
  `<task name> · <source>` Session title after creation, and disposes the
  unpublished handle when permission application or the first message fails.
  A missing Session on the created Agent is fail-closed; a title failure is
  presentation-only. Save uses `Session.snapshotEvents()`; the first turn is a
  complete `UserMessage` with `id`, `role`, and a producer-owned
  `plugin:maintainall` source kind accepted by dsh v4 persistence.
- The browser half is split into `client/api.ts` (bounded host HTTP),
  `client/save-dialog.ts`, `client/ops-panel.ts`, `client/settings-log.ts`,
  and shared task/selector types; the entry owns only locale/style/slot
  registration. The host
  composition root delegates registry/run-map persistence to
  `host/task-state.ts`, replay Agent creation/handle retention to
  `host/replay-runtime.ts`, and trigger engine/source-listener lifecycle to
  `host/trigger-runtime.ts`; HTTP routes and the tool remain in the service.
- Replay remaps the seed header and executable tool-call arguments only.
  Argument JSON is parsed; shell fields use the bounded linear shell lexer,
  whole path values are matched by the captured platform, and content/text/query and old/new
  text fields (including nested payloads) are left unchanged. Assistant tool-call arguments receive
  the same replacement and changed timed streams are cleared. Tool results,
  tool-private metadata, prose, provider state, and other event data remain
  historical evidence. Capture-session environment context is filtered because
  dsh regenerates it. Percent-encoded matching is limited to local `file:` URI
  paths, and replacement URIs encode reserved filename characters. Parsed seeds
  are bounded to 16 MiB, 100,000 events, and
  a 4 KiB absolute cwd; command/argument strings over 2 million characters are
  left untouched rather than scanned, and argument traversal stops at depth
  64. Numeric literals outside JSON strings that would lose value are left
  untouched instead of being round-tripped. Root cwds are rejected.
- The materialize `POST /save` path refuses an existing id; auto saves queue
  an LLM save turn, and other `/save` requests are rejected. The
  `ops_save_task` re-save path preserves the captured seed, skills, scripts, runs, `requires`, and
  `bindings`, and does not apply skill/script arguments. Manual edit preserves
  the task's enabled flag, the first trigger's id/enabled flag, and all other
  triggers. Removed trigger ids have their runtime state forgotten. Task
  deletion, trigger toggles, and initialization failures keep host state and
  registrations consistent.
- The client's primitive icon imports were updated from the removed
  `...14`/`...16` names to the current `...Regular` exports so the plugin
  typechecks against dsh 0.2.1-rc.3.

## Alternatives considered

- **Use `ScheduleService` as the trigger bus.** Rejected: `create(sessionId,
  request)` binds a reminder to one Session and delivery appends a follow-up
  to that Session. There is no generic fire callback or "create a run Session"
  action; using it would put an Agent turn in the trigger path and serialize
  runs through one conversation.
- **Use `WebhookSessionRequest` for replay.** Rejected: it only carries a
  workspace path, title, prompt, and presets. It cannot carry a seed, a run
  cwd, copied assets, tool filtering, or a run-map entry, and it attaches the
  Session to a Web Workspace.
- **Keep the fixed offset and only add selectors.** Rejected: the fixed offset
  cannot represent DST or an IANA zone, and the task explicitly asked for the
  dsh time semantics.
- **Copy the whole dsh Schedule domain implementation.** Rejected: the pure
  core is small, dependency-free, directly unit-tested, and the single
  production authority.
- **Apply the permission preset after the first message.** Rejected: the
  prompt must not run under default permissions when the task declares a
  stricter preset. A composition without the permission-preset service, an
  unknown preset, or a Session-less created Agent fails closed; `set` or
  first-message failure rolls the Agent back.
- **Keep one lexer over every seed string.** Rejected: prose, JSON tool
  arguments, shell commands, tool results, and provider state are different
  grammars. The repeated fixes for compact JSON, Windows escaping, and
  backtick/colon forms were inverse cases of that mismatch, and historical
  file contents/diffs were being rewritten as if they were executable paths.
- **Tokenize the cwd at capture and substitute a placeholder at replay.**
  Deferred: it improves at-rest portability, but capture still has to decide
  which occurrences are references, and it adds a seed-format migration,
  collision/leak handling, and unresolved-token failure modes. Revisit only if
  cross-machine portable assets become a requirement.
- **Use a shell parser library.** Rejected for now: tree-sitter-bash adds a
  native/WASM packaging burden and still covers only Bash; bash-parser is
  unmaintained and lacks exact source offsets. JSON and path libraries cover
  their own grammars, so the implementation uses built-ins plus the bounded
  shell lexer only for command fields.

## Consequences

- Existing v1 `trigger-state.json` files retain their `triggers`, `schedules`, and `exec` sections, but drop legacy path-keyed filewatch offsets (the next poll starts from a fresh baseline) and the retired journald cursor section.
  Previously saved triggers without a committed target get one at the next
  start; retained v1 targets are reused. A stale target that is already in the
  past fires once, not once per missed occurrence.
- The legacy `timezoneOffsetMinutes` form still works and keeps emitting
  `payload.timezoneOffsetMinutes`. A new `cron` object emits `payload.cron`
  and `payload.timeZone`; a CEL `when` expression that reads the old offset
  field should switch to `timeZone` when the trigger is migrated. A
  metadata-only edit preserves the stored legacy params exactly; only an
  explicit schedule-field edit migrates the rule. The dialog maps a whole-hour
  legacy offset to the equivalent `Etc/GMT` zone and shows `UTC` for a
  fractional offset, which the user must re-select when editing the schedule.
- Existing source triggers that stored `params.path`/`params.command` keep
  working: task reads and engine rebuilds normalize them into `filter`, and the
  next save writes the canonical shape.
- [`tests/triggers/schedule-time.test.ts`](../../../../../../tests/triggers/schedule-time.test.ts)
  pins DST, star, canonicalization, and selector behavior against the pure core.
- `materializeTaskFromSave`, `materializeTaskEdit`, and `ops_save_task` validate
  trigger shape, required filters, duplicate ids, and the schedule first target
  before any file or registry write; the materialize `POST /save` path also
  rejects an existing id. `handleTriggerToggle` restores the previous flags if `reload` throws. Exec
  commands now run through a 60 s/1 MiB bounded host subprocess;
  `maxPerHour: 0` means no hourly cap. This is a behavior change for callers that
  previously persisted a bad or duplicate trigger and learned about it on the
  next engine reload/start.
- The inotify mitigation is registered through the plugin's bundle patch
  array: [`preset/ops.patch.yml`](../../../../../../preset/ops.patch.yml) declares the
  `ops` agent preset, and a task without an explicit `agentPreset` binding
  resolves `ops` by default. If `ops` is missing or broken, dispatch logs and
  falls back to the deployment default, which may retain that default's skill
  watcher. See [docs/architecture.md](../../../../../../docs/architecture.md).
- Known limits: replay does not mount `requires.mcpServers`; surface replace
  operations are not preserved; journald cursor state is not written; a
  SIGKILL escalation does not await child exit. These are outside the current
  fix scope and are documented in the architecture/testing references as
  appropriate.
- A recurring rule with no representable future target becomes inactive in
  trigger state instead of throwing from the tick. The engine still fails loud
  at start when a rule cannot produce its first target.
