# Decision: Run-session watcher pressure and retained-handle cleanup

Status: implemented — replay sessions resolve the schema-valid watching-disabled ops preset by default; live profile activation remains a verification limitation

## Problem

The plugin itself registers no inotify watches: its `filewatch` source polls
with `stat` and `readFile`. A replayed run, however, creates a new directory
under `ops/<task-id>/runs/` and copies `.agents/skills/` into it. The `ops`
preset mounts `@deepseek-ai/dsh-skill-filesystem`, whose default is
`watch: true`; dsh treats each run cwd as a project root (there is no `.git`
above it), so every run could add one Chokidar/inotify project root. dsh
bounds that with `watchMaxProjects` (default 128) and evicts the oldest
project, so the leak is bounded, but old run directories remain watched until
eviction. The task asset writer also creates an empty `.agents/skills/`, so
even a task without skills produced a watched root. Separately,
`MaintainAllService.agentHandles` was only ever set, never removed, and the
docker/journald listeners killed their child processes without closing the
readline interfaces or waiting for the child to exit.

## Decision

- The [ops preset patch](../../../../../../preset/ops.patch.yml) declares an
  `@deepseek-ai/dsh-agent-preset` with `id: ops`; the plugin's
  `dsh.bundle.patch` array loads it alongside `cordis.patch.yml`. Its
  `skill-filesystem` sets `watch: false` and caps `watchMaxProjects` at 8, and
  its reminder row is `@deepseek-ai/dsh-tool-schedule`. The persona, todo, and
  plan-mode rows carry the configs required by dsh 0.2.1-rc.3. A task without
  an explicit `agentPreset` binding resolves `ops` by default; if that implicit
  `ops` is missing or broken, dispatch logs and falls back to the deployment
  default. An explicit binding fails closed. Edit sessions use the deployment
  default unless the task has an explicit binding. In the
  shipped Web composition the base host `skill-filesystem` row is disabled, so
  this preset row is the run agent's local provider; discovery and skill
  loading still scan the run cwd, and only live catalog invalidation is
  disabled. A deployment that needs live skill edits during a long run can set
  `watch: true`, or use `watchUsePolling: true` to avoid inotify.
- [`createRunCwd`](../../../../../../src/dispatch/run-cwd.ts) does not copy an empty
  `.agents/skills/`. A task without skills no longer creates an empty skill
  directory; a task with skills copies them as before. Omitting the empty
  directory is not by itself sufficient protection when a watcher-enabled
  default preset is used; `watch: false` on `ops` is the actual guard.
- The host registers a `session/disposed` listener that deletes the session's
  entry from `agentHandles`, and teardown clears the map. The map is capped at
  256 entries because an archived Session may never emit `session/disposed`;
  it is a retention aid only, and dsh owns the Agent lifecycle.
- [`startDockerListener`](../../../../../../src/engine/listeners.ts) and
  `startJournaldListener` close their readline interfaces, send SIGTERM, wait
  up to two seconds for exit, and escalate to SIGKILL. Teardown stops the
  engine first so no new tick starts while the listeners drain.
- No `fs.watch`, `watchFile`, Chokidar, or inotify is added by the plugin.

## Alternatives considered

- **Keep `watch: true` and lower `watchMaxProjects`.** Rejected as the
  default: it still creates inotify watches, just fewer of them, and a
  long-running host keeps the most recent run roots watched. It remains a
  documented opt-in for deployments that need live skill updates.
- **Set `watchUsePolling: true`.** Rejected as the default: it removes inotify
  but spends CPU polling every retained project root. It is a reasonable
  opt-in together with a small `watchMaxProjects`.
- **Add a `.git` marker above `ops/` so runs share one project root.**
  Rejected: it changes Git and project-root behavior for the agent, not just
  the watcher, and is a surprising side effect of a task asset directory.
- **Remove `agentHandles` entirely.** Rejected for now: the map is never read,
  but removing it changes reference lifetime in one step. Deleting entries on
  `session/disposed` and clearing on teardown fixes the unbounded growth
  without changing active-run behavior.
- **Dispose handles on session disposal.** Rejected: dsh already owns the
  Session's teardown; the plugin only needs to drop its retained reference.
- **Leave the listeners as `child.kill()` only.** Rejected: closing the
  readline interfaces is idempotent, and waiting for exit with a bounded
  SIGKILL escalation releases pipe readers even when the child exits slowly.
- **Delete `agentHandles` entries on `workspace/session-activity`.** Rejected:
  that waterfall runs before the archive is committed, so dropping the handle
  there would also drop it when another provider refuses the archive. The
  bounded map plus `session/disposed` cleanup avoids that false signal.

## Consequences

- A task without skills produces a run cwd without `.agents/`; skill discovery
  correctly finds nothing. A task with skills is unchanged. The empty-directory
  omission is defense in depth; it does not suppress watchers on a fallback
  preset that watches missing skill roots through existing ancestors.
- Live add/rename/delete of a skill inside an already running run is no longer
  reflected in that run's catalog until the next session. Loading a known skill
  still re-reads its current body. This is the deliberate cost of disabling the
  watcher for static replay runs.
- The plugin still has no direct inotify cleanup responsibility. If an operator
  overrides `watch: true` or the `ops` preset is unavailable so dispatch falls
  back to the deployment default, the run-cwd-to-project-root behavior returns,
  bounded by dsh's watcher settings. This fallback is logged.
- `agentHandles` is bounded to 256 retained entries, drops a Session on
  `session/disposed`, and is cleared on unload. An archived Session that never
  disposes may stay until eviction or unload, but cannot grow the map without
  bound. Child-process teardown closes line readers, waits for exit, and
  escalates to SIGKILL after two seconds.
- The run-cwd tests cover both an empty and a non-empty `.agents/skills/`
  directory.
