#!/usr/bin/env python3
"""Refresh the systemd-managed Paseo daemon after a package update.

The Paseo daemon is two processes: a supervisor (a tiny long-lived launcher)
and a worker (the real daemon). Updating the npm package on disk only
restarts the worker; the supervisor keeps running its original in-memory
code, and only whoever launched it can do a full-process replacement. The
GUI phrases it as: "The running supervisor retains its original code. Its
launcher must stop and start it to refresh the supervisor."

For the systemd deployment in this directory, the launcher is
paseo.service. A paseo-supervisor-refresh.path unit watches the installed
@getpaseo npm scope directory; when an update rewrites it, this script
restarts paseo.service so the supervisor is re-executed from the new
package.

Guards, in order:
  1. paseo.service is active (a stopped daemon is never started),
  2. the installed package is newer than the running supervisor process,
  3. the daemon is quiescent — no `npm install` inside the service cgroup
     (the GUI "update daemon" flow spawns one) and a worker that has been
     up for at least a minute (so the watcher never lands inside the
     daemon's own post-install worker restart). The watcher waits, bounded
     (see WAIT_TIMEOUT_SECONDS), instead of restarting into either window.
  4. no agent is running or initializing — restarting the daemon kills the
     worker and the agent processes it spawned.
When the agent list cannot be fetched, the refresh is skipped: not
restarting is always safe, the next package change retries.

The generated unit sets TimeoutStartSec above the wait budget: the
default 90s would kill a oneshot that is legitimately waiting for
`node-pty`'s postinstall build or the daemon's own restart to settle.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

BUSY_STATUSES = frozenset({"running", "initializing"})
SETTLE_SECONDS = 3.0
LS_TIMEOUT_SECONDS = 20.0
SYSTEMCTL_TIMEOUT_SECONDS = 30.0
WAIT_TIMEOUT_SECONDS = 20 * 60
POLL_INTERVAL_SECONDS = 5.0
MIN_WORKER_UPTIME_SECONDS = 60.0
CGROUP_ROOT = Path("/sys/fs/cgroup")
PROC_ROOT = Path("/proc")

ACTION_NOOP = "noop"
ACTION_SKIP = "skip"
ACTION_RESTART = "restart"


def read_supervisor_pid(home: Path) -> int | None:
    """Supervisor PID recorded in <home>/paseo.pid (empty when unset)."""
    try:
        data = json.loads((home / "paseo.pid").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pid = data.get("pid")
    return pid if isinstance(pid, int) and pid > 0 else None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def process_start_epoch(pid: int, proc_root: Path = PROC_ROOT) -> float | None:
    """Process start time as epoch seconds.

    Computed from field 22 (starttime, clock ticks since boot) of
    /proc/<pid>/stat plus btime from /proc/stat. The /proc/<pid> directory
    mtime is NOT reliable: procfs creates those inodes lazily on first
    access, so the timestamp can postdate the real start and reset later.
    """
    try:
        stat_text = (proc_root / str(pid) / "stat").read_text(encoding="ascii")
    except OSError:
        return None
    # comm (field 2) may contain spaces or parentheses; fields resume after
    # the last ')'. starttime is field 22 overall, index 19 in the remainder.
    try:
        rest = stat_text[stat_text.rindex(")") + 2 :]
        start_ticks = int(rest.split()[19])
    except (ValueError, IndexError):
        return None
    try:
        btime = None
        for line in (proc_root / "stat").read_text(encoding="ascii").splitlines():
            if line.startswith("btime "):
                btime = int(line.split()[1])
                break
    except OSError:
        btime = None
    if btime is None:
        return None
    try:
        ticks_per_second = os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError, AttributeError):
        ticks_per_second = 100
    return btime + start_ticks / ticks_per_second


def installed_package_mtime(scope_dir: Path) -> float | None:
    """Newest package.json mtime inside the @getpaseo scope directory."""
    newest: float | None = None
    for name in ("cli", "server"):
        try:
            mtime = (scope_dir / name / "package.json").stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    return newest


def default_watch_dir(paseo_bin: str) -> Path:
    """<scope>/cli/bin/paseo -> <scope>, where updates rewrite package.json."""
    return Path(paseo_bin).resolve().parent.parent.parent


def busy_agent_ids(agents: object) -> list[str]:
    ids: list[str] = []
    if not isinstance(agents, list):
        return ids
    for agent in agents:
        if isinstance(agent, dict) and agent.get("status") in BUSY_STATUSES:
            agent_id = agent.get("id") or agent.get("shortId")
            ids.append(str(agent_id) if agent_id else "<unknown>")
    return ids


def decide(
    *,
    service_active: bool,
    supervisor_pid: int | None,
    supervisor_start: float | None,
    package_mtime: float | None,
    busy_ids: list[str] | None,
) -> tuple[str, str]:
    """Pure decision step so the policy is unit-testable without processes."""
    if not service_active:
        return ACTION_NOOP, "paseo.service is not active; nothing to refresh"
    if supervisor_pid is None:
        return ACTION_NOOP, "no supervisor PID recorded in paseo.pid"
    if supervisor_start is None or package_mtime is None:
        return ACTION_NOOP, "cannot compare the supervisor start time with the package mtime"
    if package_mtime <= supervisor_start:
        return ACTION_NOOP, "installed package is not newer than the running supervisor"
    if busy_ids is None:
        return ACTION_SKIP, "agent state is unknown; not safe to restart"
    if busy_ids:
        return ACTION_SKIP, "agents busy: " + ", ".join(busy_ids)
    return ACTION_RESTART, "installed package is newer than the running supervisor"


def run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def systemctl_is_active(
    service: str,
    runner=None,
    timeout: float = SYSTEMCTL_TIMEOUT_SECONDS,
) -> bool:
    runner = runner or run
    try:
        proc = runner(["systemctl", "--user", "is-active", "--quiet", service], timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def collect_busy_ids(
    paseo_bin: str,
    runner=None,
    timeout: float = LS_TIMEOUT_SECONDS,
) -> list[str] | None:
    """Busy agent IDs, or None when the agent list cannot be determined."""
    runner = runner or run
    try:
        proc = runner([paseo_bin, "ls", "--json"], timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return busy_agent_ids(json.loads(proc.stdout))
    except ValueError:
        return None


def service_control_group(
    service: str,
    runner=None,
    timeout: float = SYSTEMCTL_TIMEOUT_SECONDS,
) -> str | None:
    """cgroup path of the service (relative to /sys/fs/cgroup), or None."""
    runner = runner or run
    try:
        proc = runner(["systemctl", "--user", "show", "-p", "ControlGroup", "--value", service], timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    control_group = proc.stdout.strip()
    return control_group or None


def cgroup_pids(control_group: str, cgroup_root: Path = CGROUP_ROOT) -> list[int]:
    """PIDs under a cgroup v2 directory, including nested children."""
    base = cgroup_root / control_group.lstrip("/")
    if not base.is_dir():
        return []
    pids: list[int] = []
    for procs in sorted(base.rglob("cgroup.procs")):
        try:
            pids.extend(int(line) for line in procs.read_text(encoding="ascii").split())
        except (OSError, ValueError):
            continue
    return pids


def cmdline_is_npm_install(pid: int, proc_root: Path = PROC_ROOT) -> bool:
    """True when the process is an `npm install` invocation of any form."""
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return False
    parts = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
    if not any(Path(part).name in ("npm", "npm-cli.js") for part in parts):
        return False
    return "install" in parts


def npm_busy(control_group: str, cgroup_root: Path = CGROUP_ROOT, proc_root: Path = PROC_ROOT) -> bool:
    return any(cmdline_is_npm_install(pid, proc_root) for pid in cgroup_pids(control_group, cgroup_root))


def worker_is_settled(
    paseo_bin: str,
    *,
    minimum_uptime: float = MIN_WORKER_UPTIME_SECONDS,
    runner=None,
    proc_root: Path = PROC_ROOT,
    now=time.time,
    timeout: float = LS_TIMEOUT_SECONDS,
) -> bool:
    """True when the daemon answers status with a worker up for a while.

    False while the daemon is restarting its worker (the self-update flow
    stops and respawns it, and `daemon status` is unreachable or reports a
    fresh worker in that window — exactly when a service restart would land
    mid-update). Daemons whose status payload lacks `workerPid` predate the
    field and are treated as settled, since the guard cannot help them.
    """
    runner = runner or run
    try:
        proc = runner([paseo_bin, "daemon", "status", "--json"], timeout)
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    pid = data.get("workerPid")
    if pid is None:
        return True
    if not isinstance(pid, int) or pid <= 0:
        return False
    start = process_start_epoch(pid, proc_root)
    if start is None:
        return False
    return now() - start >= minimum_uptime


def daemon_quiescent(
    service: str,
    paseo_bin: str,
    *,
    runner=None,
    cgroup_root: Path = CGROUP_ROOT,
    proc_root: Path = PROC_ROOT,
    now=time.time,
) -> bool:
    """True when neither the self-update install nor the daemon's own
    worker restart is in flight."""
    runner = runner or run
    control_group = service_control_group(service, runner=runner)
    if control_group is not None and npm_busy(control_group, cgroup_root, proc_root):
        return False
    return worker_is_settled(paseo_bin, runner=runner, proc_root=proc_root, now=now)


def wait_for_quiescence(
    service: str,
    paseo_bin: str,
    *,
    runner=None,
    cgroup_root: Path = CGROUP_ROOT,
    proc_root: Path = PROC_ROOT,
    sleep=time.sleep,
    monotonic=time.monotonic,
    now=time.time,
    timeout: float = WAIT_TIMEOUT_SECONDS,
    poll: float = POLL_INTERVAL_SECONDS,
    log=lambda _msg: None,
) -> bool:
    """Wait until the daemon is quiescent (install and restart windows over).

    The GUI's "update daemon" runs `npm install` inside the service cgroup
    and then restarts the worker; restarting the service during either phase
    breaks the update. Returns False when the budget elapses (caller skips).
    """
    runner = runner or run
    deadline = monotonic() + timeout
    while True:
        if daemon_quiescent(service, paseo_bin, runner=runner, cgroup_root=cgroup_root, proc_root=proc_root, now=now):
            return True
        remaining = deadline - monotonic()
        if remaining <= 0:
            return False
        log(f"{service} is mid-update or restarting its worker; waiting {int(remaining)}s more")
        sleep(min(poll, remaining))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Restart paseo.service when the installed @getpaseo package "
        "is newer than the running supervisor and no agent is busy.",
    )
    parser.add_argument("--home", type=Path, default=Path("~/.paseo"), help="Paseo home (default: ~/.paseo)")
    parser.add_argument(
        "--watch-dir",
        type=Path,
        default=None,
        help="@getpaseo npm scope directory (default: derived from --paseo-bin)",
    )
    parser.add_argument("--paseo-bin", default="paseo", help="paseo executable used for `paseo ls`")
    parser.add_argument("--service", default="paseo.service", help="systemd user unit to restart")
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=SETTLE_SECONDS,
        help="grace period before checking, so npm can finish writing (default: %(default)s)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the decision, never restart")
    args = parser.parse_args(argv)

    home = args.home.expanduser()
    watch_dir = args.watch_dir if args.watch_dir is not None else default_watch_dir(args.paseo_bin)
    watch_dir = watch_dir.expanduser()

    if args.settle_seconds > 0:
        time.sleep(args.settle_seconds)

    service_active = systemctl_is_active(args.service)
    supervisor_pid = read_supervisor_pid(home) if service_active else None
    supervisor_alive = pid_alive(supervisor_pid) if supervisor_pid is not None else False
    supervisor_start = process_start_epoch(supervisor_pid) if supervisor_alive else None
    package_mtime = installed_package_mtime(watch_dir)

    stale = (
        service_active
        and supervisor_alive
        and supervisor_start is not None
        and package_mtime is not None
        and package_mtime > supervisor_start
    )
    if stale:
        # Never restart while the daemon is updating itself: its npm install
        # runs inside the service cgroup and would be SIGTERMed, and its own
        # post-install worker restart is an equally bad landing spot. Wait
        # for quiescence, then give the daemon a moment to settle.
        if not wait_for_quiescence(args.service, args.paseo_bin, log=print):
            print("skip: the daemon is still mid-update or restarting after the wait budget")
            return 0
        if args.settle_seconds > 0:
            time.sleep(args.settle_seconds)
    busy_ids = collect_busy_ids(args.paseo_bin) if stale else []

    action, reason = decide(
        service_active=service_active,
        supervisor_pid=supervisor_pid if supervisor_alive else None,
        supervisor_start=supervisor_start,
        package_mtime=package_mtime,
        busy_ids=busy_ids,
    )
    print(f"{action}: {reason}")

    if action != ACTION_RESTART or args.dry_run:
        return 0
    try:
        proc = run(["systemctl", "--user", "restart", args.service], SYSTEMCTL_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"error: systemctl restart failed to run: {exc}", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print(f"error: systemctl restart exited {proc.returncode}: {detail}", file=sys.stderr)
        return 1
    print(f"restarted {args.service}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
