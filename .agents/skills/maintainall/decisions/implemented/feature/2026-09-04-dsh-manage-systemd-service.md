# Decision: dsh-manage systemd --user service

Status: implemented — `deploy.py install-manage-service` writes/enables `dsh-manage.service`; `manage.py --pid-file` self-tracks its pid; `deploy.py` prefers the unit when installed and otherwise keeps the direct-process lifecycle.

## Problem

`deploy.py up` starts `manage.py` as a plain host process with a pid file. After
the host reboots, Docker restarts the `dsh-proxy` caddy container
(`--restart unless-stopped`), but the manage process does not come back. The
result is exactly the 2026-09-04 incident: `https://<LAN_IP>:3081/` was
healthy (200) while `/manage/` returned 502 and `127.0.0.1:9097` refused
connections, because the pid file was stale and no process was listening.

The same failure repeats after every reboot unless the operator remembers to run
`deploy.py reload` by hand.

## Decision

Add an opt-in systemd **user** service for the manage backend, installed through
`deploy.py` itself so no standalone shell scripts are needed:

- `manage.py` gains `--pid-file` (default `data/manage.pid`). After it binds
  `127.0.0.1:<port>` successfully it writes `os.getpid()` to that file, so both
  systemd-run and direct-run instances participate in deploy.py's existing
  pid-file + port-fact reconciliation.
- `deploy.py install-manage-service` renders the unit with the **current
  interpreter** (`sys.executable`) and absolute paths:
  `ExecStart=<python> <repo>/manage.py --port <port> --container <container>
  --pid-file <repo>/data/manage.pid`, writes it under
  `${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/dsh-manage.service`, then runs
  `systemctl --user daemon-reload` + `enable --now` (or `restart` when already
  active). It refuses to install over an already-listening `127.0.0.1:<port>`
  that is not the unit itself.
- `deploy.py` gains `manage_systemd_unit_file`, `systemctl_user`, and
  `manage_systemd_main_pid`. `start_manage` uses `systemctl --user start` when
  the unit is installed; `stop_manage` stops the unit instead of SIGTERM when the
  unit's `MainPID` equals the resolved listener; `status` prints whether the unit
  is installed/active. When the unit is absent, behavior is unchanged.

## Alternatives considered

- **Separate shell scripts for the unit wrapper and installer**: the first cut
  shipped `dsh-manage-service.sh` + `install-manage-service.sh`. Rejected on
  operator request: the wrapper existed only to write the pid file before exec,
  which `manage.py --pid-file` now does itself; the installer logic is a natural
  `deploy.py` action because `sys.executable` and the repo paths are already
  known there.
- **Run manage.py inside the caddy container**: fits “everything in Docker”, but
  `caddy:2` has no Python; it would require a custom image (caddy + python3 +
  PyYAML + procps/iproute2), an in-container supervisor, `~/.dsh` mount, and a
  rewrite of deploy.py's manage lifecycle around `docker exec`. Rejected as more
  moving parts for the same boot-time guarantee; noted as viable if the operator
  later wants one container.
- **Cron `@reboot`**: rejected because `crontab` is PAM-blocked for this user on
  this host, and cron has no clean stop/status integration with `deploy.py`.
- **Do nothing (document the manual `reload`)**: still the fallback for hosts
  without a user systemd manager, but it does not solve “挂了下一次”.

## Consequences

- After `python3 deploy.py install-manage-service`, manage survives reboots and
  restarts on failure (`Restart=on-failure`). `deploy.py down` stops the unit;
  `up`/`reload` start it via systemd.
- `deploy.py` still falls back to direct `Popen` process management when the unit
  is not installed, so script-only deployments and `--dry-run` behavior are
  unchanged.
- The service runs as the same user, with the same Python and repo directory, so
  file permissions on `data/` and `$DSH_HOME` are unchanged.
