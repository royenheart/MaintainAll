# Agent Note: paseo refresh watcher must not kill the daemon self-update

Status: implemented — `supervisor_refresh.py` waits for daemon quiescence (no in-cgroup `npm install`, worker up for at least a minute) before restarting `paseo.service`.

## Problem

The first version of the supervisor-refresh watcher ([paseo supervisor auto-refresh](../feature/2026-09-29-paseo-supervisor-auto-refresh.md)) restarted `paseo.service` whenever the installed `@getpaseo` package became newer than the running supervisor and no *agent* was busy. That guard missed the daemon's own update path: the GUI's "update daemon" sends `daemon.update.request`, and the daemon runs `npm install --global @getpaseo/cli@latest` as a child of the worker — inside the `paseo.service` cgroup. npm replacing the package directory triggered the watcher within seconds; with all agents idle it restarted the service; systemd's cgroup teardown SIGTERMed the npm install mid-`node-pty` postinstall, and the GUI reported "Update failed / signal SIGTERM". Every retry re-bumped the watched directory, re-triggered the watcher, and was killed again — a loop that made updating impossible while the watcher was enabled. The oneshot was also exposed to systemd's default 90 s `TimeoutStartSec` once it had to wait at all.

The first fix (wait for npm to leave the cgroup) failed a second way hours later: the install completed in ~11 s, the daemon began its own post-install worker restart, and the watcher — seeing no npm and all agents idle — restarted the service into that window. The install had already succeeded on disk, but the interrupted restart severed the desktop app's local transport session, and every further GUI action failed with `Error invoking remote method 'paseo:invoke': Local transport session not found …` until the app was restarted. The guard had to cover the whole update transaction, not just the install subprocess.

## Decision

Make the watcher update-aware instead of merely agent-aware. It shipped in two lessons:

1. The daemon's self-update runs `npm install --global @getpaseo/cli@latest` as a child of the worker — inside the `paseo.service` cgroup. The watcher must not restart the service while that npm exists (first fix: detect `npm install` in the cgroup and wait it out, bounded).
2. npm finishing is not the end of the update. The daemon then stops and respawns its worker ("daemon_update. Stopping worker for restart…"), and `daemon status` is unreachable or reports a seconds-old worker in that window. The watcher restarted into this gap too, which surfaced in the GUI as `Local transport session not found` because the restart severed the desktop app's session mid-update (second fix: wait for *quiescence* — no npm in the cgroup **and** a worker at least 60 s old — before restarting).

Concretely:

- Enumerate the PIDs of the service cgroup (`systemctl --user show -p ControlGroup`, then `cgroup.procs` under `/sys/fs/cgroup`, nested children included) and treat any `npm install` among their cmdlines as "update in progress". A plain `npm install` in the user's own terminal is a different cgroup and does not block the refresh — and is safe anyway, since a service restart cannot signal it.
- Read the worker age from `paseo daemon status --json` (`workerPid` + `/proc/<pid>` start time). Unreachable status or a worker younger than 60 s means the daemon is mid-restart: keep waiting. A status payload without `workerPid` means an older daemon and is treated as settled, since the guard cannot help it.
- When quiescent, settle briefly to let any in-flight worker restart finish, then re-run the agent check, so a successful self-update still ends with the supervisor refreshed. Budget exceeded → skip with a journal message; the next package change or a manual `systemctl --user start paseo-supervisor-refresh.service` retries.
- The generated oneshot sets `TimeoutStartSec=1500`, above the 20-minute quiescence budget, so systemd's default 90 s start timeout cannot kill a run that is legitimately waiting out a slow native build.

## Alternatives considered

- Only check for npm processes system-wide. A user-driven `npm install` of an unrelated package would then delay or block the refresh for no reason; the cgroup scope targets exactly the dangerous case (a restart can signal it).
- Skip instead of wait when npm is detected. A successful self-update would leave the supervisor stale forever, because the directory does not change again after npm exits — the very state the watcher exists to fix.
- Have the GUI/daemon exclude the watcher (e.g. a lock file around self-update). Requires upstream cooperation; the local cgroup check needs no changes to Paseo and covers manual `daemon.update.request` paths too.

## Consequences

Updating via the GUI now completes end-to-end: npm finishes, the daemon restarts its worker, and the watcher refreshes the supervisor a few seconds later. The refresh is delayed by however long the install takes (the path trigger fires at install start; the oneshot holds until install end), which is invisible in practice. The cgroup walk assumes cgroup v2 (`/sys/fs/cgroup/<group>/cgroup.procs`), true on this Fedora machine; if the control group cannot be resolved, the watcher proceeds without the npm guard rather than wedging, and the agent guard still applies.
