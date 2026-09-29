# paseo-daemon deployment

Installs the [Paseo](https://paseo.sh) daemon on this machine (headless, driven
via Remote/SSH from the GUI) and keeps it running **across reboots**.

It follows the "user systemd manages the daemon" approach (the old
`deploy/systemd/install-user-daemon.sh` was removed together with the old
MaintainAll daemon). This directory matches the actual environment of this
machine (ASUS / `RoyenHeartAsus`, bash login shell, node via nvm v24.14.0).

## Why this script exists (design background)

1. **The GUI never installs or starts a daemon for you.** The desktop app runs
   its own daemon automatically, but Remote/SSH transport only connects to a
   daemon that is **already running** — the official docs state SSH does not
   install, start, or configure anything remotely. So a headless machine must
   install the CLI and start the daemon itself; this is by design, not a
   missing step.
2. **`paseo daemon start` does not survive a reboot.** It detaches a background
   supervisor (writing `~/.paseo/paseo.pid` and `~/.paseo/daemon.log`) in the
   current user session; an internal supervisor survives SSH disconnects, but
   nothing is registered with systemd — after a reboot nothing listens on 6767
   again and the GUI reports the same socket error.
3. **Solution: CLI + systemd --user + linger.** A user-level systemd service
   runs `paseo daemon run --home ~/.paseo` in the foreground
   (`daemon run` is the foreground/deployment command since CLI 0.9.2; the old
   `--foreground` flag of `daemon start` was removed — passing it exits 1 with
   "Error: --foreground was removed"). `Restart=on-failure` covers crashes, and
   `loginctl enable-linger` covers "start at boot even when nobody is logged
   in".

> Note: in CLI 0.9.2 `paseo daemon start` itself changed semantics — it now
> spawns a *managed* supervisor and **exits 0 once the daemon is ready**. Used
> as a `Type=simple` ExecStart, systemd considers the service finished and
> tears down the cgroup, killing the daemon. Foreground mode under systemd is
> exactly what `paseo daemon run` is for.

## Supervisor auto-refresh on update

The daemon is two processes: a **supervisor** (a tiny long-lived launcher
that owns `paseo.pid` and respawns the worker) and a **worker** (the real
daemon). Updating the npm package — from the GUI or
`npm install -g @getpaseo/cli` — only replaces the worker; the supervisor
keeps running its original in-memory code ("The running supervisor retains
its original code. Its launcher must stop and start it to refresh the
supervisor."). Only a full restart of `paseo.service` refreshes it.

`install.sh` therefore also generates and enables a watcher pair:

| Unit | Role |
| --- | --- |
| `paseo-supervisor-refresh.path` | `PathModified` on the installed `@getpaseo` npm scope directory; fires whenever an install/update rewrites the package |
| `paseo-supervisor-refresh.service` | oneshot: runs `supervisor_refresh.py`, which restarts `paseo.service` only when safe |

`supervisor_refresh.py` guards, in order:

1. `paseo.service` must be active — a stopped daemon is never started.
2. The installed package must be newer than the running supervisor process
   (newest `package.json` mtime under the `@getpaseo` scope vs. the
   supervisor's `/proc` start time), so unrelated touches and reinstalls
   that predate the supervisor are no-ops.
3. The daemon must be **quiescent** — no `npm install` inside the service
   cgroup (the GUI "update daemon" flow runs its install there) and a worker
   that has been up for at least a minute (the update flow restarts the
   worker right after installing; restarting the service inside either
   window breaks the update). The watcher waits, bounded (20 minutes; the
   oneshot unit gets a matching `TimeoutStartSec`), then proceeds, so a
   successful self-update still ends with a refreshed supervisor.
4. No agent may be `running` or `initializing` — restarting the daemon
   kills the worker and its child agent processes. When the agent list
   cannot be fetched, the refresh is skipped too; the next package change
   retries. Idle agents do not block the restart; their sessions are
   terminated and can be resumed afterwards.

Trigger a check manually at any time:

```bash
systemctl --user start paseo-supervisor-refresh.service   # safe: skips busy agents
journalctl --user -u paseo-supervisor-refresh.service -n 5
```

The watched path is pinned at install time to the resolved nvm path;
after switching/upgrading node versions, re-run `./install.sh`.

## Quick start (one shot)

```bash
cd deploy/paseo-daemon
./install.sh
```

The script is idempotent; each run does, in order:

| Step | Equivalent command | Notes |
| --- | --- | --- |
| 1 | `npm install -g @getpaseo/cli` | Only when `paseo` is not on PATH |
| 2 | `sync_login_env.py` | Runs a clean login shell once and writes its environment to `~/.config/environment.d/60-paseo.conf` (an existing file is first copied to `60-paseo.conf.bak`) |
| 3 | Generate `~/.config/systemd/user/paseo.service` | `ExecStart` uses the resolved real absolute path (nvm symlinks are expanded with `readlink -f`); the unit sets no `PATH`. Re-runs leave an active daemon running when the unit is unchanged |
| 4 | Generate the supervisor-refresh units + `systemctl --user daemon-reload` + `enable --now paseo-supervisor-refresh.path` | See [Supervisor auto-refresh on update](#supervisor-auto-refresh-on-update); skipped when the `@getpaseo` scope cannot be derived from the resolved binary |
| 5 | `systemctl --user enable --now paseo.service` (when not active) | If an old detached instance is detected it is stopped first with `paseo daemon stop` so it cannot hold 6767 |
| 6 | `loginctl enable-linger "$USER"` | Skipped when already enabled |
| 7 | Readiness probe + `paseo daemon status` | Verifies 6767 is listening / `localDaemon: running` |

## Verify

```bash
paseo daemon status --no-color
systemctl --user is-active paseo.service      # active
```

`paseo daemon status` should show `localDaemon: running` (and
`connectedDaemon: reachable` once a client connects). After that, the GUI's
Remote/SSH to this machine should no longer report connection/socket errors.

## Manage / uninstall

```bash
systemctl --user restart paseo.service        # restart
systemctl --user start paseo-supervisor-refresh.service  # supervisor refresh check (skips busy agents)
journalctl --user -u paseo.service -f         # systemd journal
tail -f ~/.paseo/daemon.log                   # daemon log

# Uninstall
systemctl --user disable --now paseo.service
systemctl --user disable --now paseo-supervisor-refresh.path
rm -f ~/.config/systemd/user/paseo.service
rm -f ~/.config/systemd/user/paseo-supervisor-refresh.path
rm -f ~/.config/systemd/user/paseo-supervisor-refresh.service
rm -f ~/.config/environment.d/60-paseo.conf
systemctl --user daemon-reload
# (optional) npm uninstall -g @getpaseo/cli
```

## Options

```bash
./install.sh --no-systemd   # only step 1 + `paseo daemon start` (detached; no boot autostart)
./install.sh --no-install   # skip npm install (paseo must already be on PATH)
./install.sh --dry-run      # sniff and print the generated unit / commands; write nothing, start nothing
python3 -m unittest test_sync_login_env test_supervisor_refresh   # in this directory; no real login shell or daemon is touched
```

## Notes

- **nvm shims are often invisible to systemd.** The unit's `ExecStart` is
  generated from the resolved real path — do not hand-edit it (the reference
  `paseo.service` in this directory is only an example). `PATH` is not written
  into the unit: `Environment=PATH=...` would replace the user manager's whole
  `PATH`, and `$PATH` is not expanded in a unit.
- **Login-shell snapshot.** `sync_login_env.py` runs
  `env -i $SHELL --login -c 'env -0'` and writes the result to
  `~/.config/environment.d/60-paseo.conf` (mode `0600`). An existing file is
  first copied to `60-paseo.conf.bak` (not a `.conf`, so systemd ignores it).
  After `daemon-reload`, **every user service started afterwards** inherits
  this snapshot, not only `paseo.service`. Already-running processes are not
  affected. Re-run `./install.sh` after changing `~/.bashrc` /
  `~/.bash_profile` to refresh the snapshot. One caveat: `daemon-reload` does
  **not** override variables the user manager already holds — `PATH` is
  pinned when the user manager starts (at boot/login), long before this file
  exists. The installer therefore pushes the freshly probed PATH into the
  manager itself with `systemctl --user set-environment PATH=…` after the
  reload; without that step, services keep the stale manager PATH.
- **The install-time toolchain is pinned onto PATH.** `install.sh` passes
  the bin directories of the resolved `paseo` and `node` (for example
  `~/.nvm/versions/node/<ver>/bin`) to `sync_login_env.py
  --ensure-path-dir`, and the snapshot prepends them when missing. Without
  this, a host whose login shell sees a different node first (a system node
  in `/usr/bin` while paseo lives under nvm) runs the daemon with the wrong
  npm, and the daemon's self-update fails with "@getpaseo/cli is not
  installed with npm -g on this host" — its `npm -g ls @getpaseo/cli` then
  probes the global prefix of the wrong npm, which does not own the
  install. Re-run `./install.sh` after switching node versions so the
  snapshot tracks the new toolchain.
- **The snapshot contains secrets exported by the shell.** A login shell
  sources `~/.bash_profile` (which on this machine sources `~/.bashrc`), so any
  token `export`ed there lands in `60-paseo.conf` and is visible via
  `systemctl --user show-environment`. Graphical-session variables (`DISPLAY`,
  `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`, …) are dropped so a single
  login is not pinned onto every future user service.
- **`node` must be on the probed `PATH`.** The `paseo` shebang is
  `/usr/bin/env node`. When the probe fails or finds no `node`, the script
  refuses to rewrite the unit.
- **`systemctl --user` cannot connect to the bus?** You are not in a real user
  session (e.g. cron, or an early SSH phase without a session). Run
  `loginctl enable-linger "$USER"` and run `./install.sh` from a normal login
  terminal.
- **After upgrading / switching node versions**, simply re-run `./install.sh`
  to regenerate the unit path.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `systemctl --user status` shows a restart loop | `journalctl --user -u paseo.service -n 50` for the error; often 6767 is held by an old detached instance — `paseo daemon stop`, then `systemctl --user restart`. If the log says `--foreground was removed`, the unit predates CLI 0.9.2: re-run `./install.sh` to regenerate it with `paseo daemon run` |
| `systemctl --user status` shows `active (exited)` / `inactive (dead)` right after start | The unit uses `paseo daemon start`, which exits 0 after spawning the daemon — under `Type=simple` systemd then kills the cgroup. Re-run `./install.sh` so ExecStart becomes `paseo daemon run --home ~/.paseo` |
| `paseo daemon status` shows stale_pid / unresponsive | A leftover pid file after a reboot is normal; starting the service overwrites it |
| GUI still reports socket/connection refused | The local daemon is not running: check `paseo daemon status` shows `localDaemon: running`; the SSH transport will never start it for you |
| The agent cannot find some command | Make sure the command is visible in a fresh login shell, then re-run `./install.sh` to refresh `60-paseo.conf` and restart the service |
