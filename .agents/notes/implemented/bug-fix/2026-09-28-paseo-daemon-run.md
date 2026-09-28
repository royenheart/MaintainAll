# Agent Note: paseo unit runs `paseo daemon run` after CLI 0.9.2 removed `--foreground`

Status: implemented — `deploy/paseo-daemon/install.sh` now generates `ExecStart=<paseo> daemon run --home <paseo-home>`; the reference `paseo.service` and the README match.

## Problem

`install.sh` generated `ExecStart=<paseo> daemon start --foreground`. paseo CLI 0.9.2 removed `--foreground` from `daemon start`, so the service crashed at boot with exit 1 ("Error: --foreground was removed. Use paseo daemon run --home <path> for foreground deployment.") and looped under `Restart=on-failure`.

A hand-edited unit without the flag was still wrong: `daemon start` now launches a *managed* supervisor and exits 0 once the daemon is ready. As a `Type=simple` main process, systemd treats the exit as "service finished" and tears down the cgroup, killing the daemon worker — `systemctl --user status` showed `inactive (dead)` and nothing listened on 6767.

The readiness fallback in `verify()` also silently broke: it grepped `daemon status` output for `local daemon.*running`, but 0.9.2 prints `localDaemon: running` (camelCase, no space), so the fallback could never match.

## Decision

- Generate `ExecStart=<paseo> daemon run --home $PASEO_HOME`. `daemon run` is the foreground/deployment mode: it stays in the foreground until SIGTERM (systemd stops it cleanly on restart/stop) and prints `Listening on <addr> (PID <pid>)` when ready.
- Update the `verify()` fallback grep to `localDaemon:[[:space:]]*running`.
- Keep `paseo daemon start` only in the `--no-systemd` detached path, where its spawn-and-exit behavior is exactly what is wanted.
- Document the CLI change in the README troubleshooting table (restart loop / `active (exited)` rows) so a stale unit is recognizable.

## Alternatives considered

- Keep `--foreground` and pin an older CLI. Loses upstream fixes and breaks again on the next global npm update; the flag removal is permanent upstream.
- `ExecStart=<paseo> daemon start` under `Type=oneshot` with `RemainAfterExit=yes`. Hides the real process state from systemd (no PID tracking, no clean stop, the managed supervisor sits outside the service's lifecycle), and a daemon crash would not trigger `Restart=on-failure`.
- `ExecStart=/bin/bash -lc 'exec paseo daemon run ...'`. Re-reads shell startup on every (re)start; a failing or slow `bashrc` takes the service down, duplicating what the `environment.d` snapshot already solves.

## Consequences

Re-running `./install.sh` on an already-deployed machine regenerates the unit and restarts the service, so existing installs heal on the next run. `paseo daemon run` inherits its environment from the user manager, so the `60-paseo.conf` login-shell snapshot keeps working unchanged. `daemon_pid()` stays valid: the pid lock file is still `~/.paseo/paseo.pid`. The `paseo daemon status` table format may drift again; the port probe remains the primary readiness check for that reason.
