# Agent Note: paseo supervisor auto-refresh after a package update

Status: implemented — `deploy/paseo-daemon/install.sh` also generates a `paseo-supervisor-refresh.path`/`paseo-supervisor-refresh.service` pair, so systemd restarts `paseo.service` once an update makes the installed package newer than the running supervisor; the restart is skipped while agents are busy.

## Problem

The Paseo daemon is two processes: a **supervisor** (a tiny long-lived launcher that owns `paseo.pid` and respawns the worker) and a **worker** (the real daemon). Updating the `@getpaseo/cli` npm package — from the GUI or `npm install -g` — only replaces the worker. The supervisor keeps executing its original in-memory code: replacing the files on disk never changes what a running process executes, and the supervisor deliberately never respawns itself because it owns respawn. Officially: "The running supervisor retains its original code. Its launcher must stop and start it to refresh the supervisor." In this deployment the launcher is `paseo.service`, so after every update the GUI showed the refresh warning and a human had to remember to `systemctl --user restart paseo.service`.

## Decision

Let systemd notice the update and refresh the service, with guards so the refresh is safe:

- `paseo-supervisor-refresh.path` watches `PathModified` on the installed `@getpaseo` npm scope directory (`.../node_modules/@getpaseo`); any install/update that rewrites the package bumps that directory's mtime.
- `paseo-supervisor-refresh.service` (oneshot) runs `supervisor_refresh.py`, which acts only when all of the following hold:
  1. `paseo.service` is active — a stopped daemon is never started by a watcher.
  2. The newest `package.json` mtime under the scope is newer than the supervisor process start time (read from `/proc/<pid>`; the PID comes from `paseo.pid`). This makes same-version reinstalls older than the supervisor and unrelated touches no-ops, and it is self-healing: after the restart the comparison is false until the next real update.
  3. `paseo ls --json` shows no agent in `running` or `initializing` — a daemon restart kills the worker and the agent processes it spawned. When the agent list cannot be fetched, the refresh is skipped as well; the next package change retries.
- `install.sh` resolves the scope directory from the resolved `paseo` binary path (refusing to install the watcher when the layout is not `…/@getpaseo/cli/bin/…`), writes both units — the oneshot carries `TimeoutStartSec=1200` so systemd's default 90s start timeout cannot kill a run that is legitimately waiting out a slow `node-pty` build — and enables the `.path`. It also stops restarting an already-active `paseo.service` when the regenerated unit is byte-identical, so re-running the installer (for example to add this watcher) no longer kills running agents.

## Alternatives considered

- Watch `~/.paseo/daemon.log` or the journal for the GUI's "Worker updated to …" line. The log records every worker event (constant churn), and parsing log text couples the watcher to a UI string instead of the filesystem fact it stands for.
- Restart unconditionally on any path event. npm's global install replaces the whole package directory, so the scope directory's mtime also changes on same-version reinstalls; an mtime-vs-supervisor-start comparison keeps those from bouncing the daemon.
- A timer that polls `paseo --version` against the daemon-reported version. The daemon-reported version is the *worker* version, which is already new after an update, so it cannot express supervisor staleness; the mtime comparison can.
- Restart immediately without the busy guard. Restarting mid-turn destroys a running agent's in-flight work; skipping is always safe because the next package change (or a manual `systemctl --user start paseo-supervisor-refresh.service`) retries.
- Guard only on agents. Shipped first, this failed in practice: the daemon's own self-update (`daemon.update.request`, "update daemon" in the GUI) runs `npm install --global @getpaseo/cli@latest` as a child of the worker, i.e. inside the service cgroup. With every agent idle the watcher restarted `paseo.service`, systemd SIGTERMed the cgroup, and the npm `node-pty` postinstall died — and each retry re-triggered the watcher, so updates could never succeed. The shipped guard watches the service cgroup for an in-flight `npm install` and waits it out (bounded, 15 min) before the agent check; see [paseo refresh must not kill the self-update](../bug-fix/2026-09-29-paseo-refresh-vs-self-update.md).

## Consequences

Updating via the GUI or npm now refreshes the supervisor automatically, usually within seconds of the install finishing (the oneshot waits a short settle period first). If an update lands while an agent is running, the refresh is deferred until the next package change or a manual trigger, and the journal entry of `paseo-supervisor-refresh.service` says why. Idle agents do not block the restart; their provider sessions are terminated and can be resumed afterwards. The watched path is pinned at install time, so switching node versions with nvm requires re-running `install.sh` (documented in `deploy/paseo-daemon/README.md`). The oneshot needs `paseo ls` to reach the daemon; when the daemon is wedged, the refresh is skipped rather than forced.
