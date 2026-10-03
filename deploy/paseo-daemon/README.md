# paseo-daemon deployment

Installs the [Paseo](https://paseo.sh) daemon on this machine (headless, driven
via Remote/SSH from the GUI) and keeps it running **across reboots**.

It follows the "user systemd manages the daemon" approach (the old
`deploy/systemd/install-user-daemon.sh` was removed together with the old
MaintainAll daemon). This directory matches the actual environment of the
target machine (single-user Linux desktop, bash login shell, node via nvm).

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

## Security model (enforced, not optional)

Paseo's admission model makes a password effectively mandatory on a shared
host: with no password configured, every connection the daemon admits is the
`owner` principal (see Paseo's `session-admission-auth`), and `127.0.0.1` is
host-wide — so every local user, and anyone who can forward a port to the
machine, gets full control. This installer therefore enforces, on every run:

1. **Loopback-only bind.** `daemon.listen` is (re)written to
   `127.0.0.1:<port>` in `~/.paseo/config.json`. A persisted non-loopback
   value (e.g. `0.0.0.0` set by hand) is reported and reset, and
   `harden_daemon_config.py` refuses to write one in the first place. There
   is deliberately no `--listen` flag. Port selection: `--port N` /
   `PASEO_PORT=N` > interactive prompt on `/dev/tty` (Enter keeps the
   current port) > the port already persisted in `config.json` > 6767 — so a
   host previously deployed on any port can be moved by answering one
   prompt. Direct LAN/mobile access is out of scope for this deployment;
   remote access goes through relay pairing (end-to-end encrypted,
   outbound-only, no open ports).
2. **A password is set by default, and can be removed later.** When no hash
   exists yet you are asked `Set a daemon password? [Y/n]` (Enter → set,
   empty new-password input auto-generates, `n` → none). When a hash already
   exists, a re-run never rotates or removes it silently: interactively you
   get `[k]eep (Enter) / [r]eset / [d]isable`, and unattended runs keep the
   existing hash — `PASEO_DEPLOY_PASSWORD=<new>` sets/rotates without a
   prompt, `PASEO_DEPLOY_NO_PASSWORD=1` removes it (mutually exclusive).
   The plaintext is never written anywhere: not `config.json`, not the
   unit, not `60-paseo.conf`, not any log. Only its bcrypt hash is stored.
   An auto-generated password is printed exactly once; interactive runs hide
   it behind an Enter-to-clear screen. Lost it? `paseo daemon set-password`.
3. **Restart on change.** The daemon is restarted only when the hardened
   config actually changed (listen port, rotated password, stripped CORS
   origin), even when the unit file is unchanged — "the old process never
   reloaded it" is not a loophole. (Paseo only reloads config on demand or at
   process start; there is no file watcher, so a restart is the reliable way
   to make a persisted change effective.) An idle re-run leaves the running
   daemon alone — restarting kills its agents.
4. **No hosted-web-app origin.** `https://app.paseo.sh` under
   `daemon.cors.allowedOrigins` is Paseo's shipped default so the hosted web
   app can drive the daemon from a browser. This deployment does not extend
   that trust: the origin is stripped on every run (an emptied list stays
   empty — an explicit deny of all cross-origin browser access). Native
   clients (CLI, desktop, mobile, relay) send no `Origin` header and are
   unaffected. If you ever want the hosted web UI back, re-add the origin by
   hand; the next installer run removes it again.

One thing this script does **not** manage, on purpose:

- **Relay pairing.** `paseo daemon pair` stays available and is the supported
  mobile path. Treat the pairing link like a password — any holder can
  connect — and note that current daemon builds still admit credential-less
  relay clients during a compatibility window; password enforcement for relay
  tightens in a future Paseo release.

Local clients (CLI, desktop app) keep working without typing the password —
they authenticate via `~/.paseo/local-credential` (mode 0600). Everyone else
— other OS users, mobile apps — must provide it.

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
   supervisor's start time from `/proc/<pid>/stat` field 22 plus `/proc/stat`
   `btime`), so unrelated touches and reinstalls that predate the supervisor
   are no-ops.
3. The daemon must be **quiescent** — no `npm install` inside the service
   cgroup (the GUI "update daemon" flow runs its install there) and a worker
   that has been up for at least a minute (the update flow restarts the
   worker right after installing; restarting the service inside either
   window breaks the update). The watcher waits, bounded (20 minutes; the
   oneshot unit gets a matching `TimeoutStartSec=1500`), then proceeds, so a
   successful self-update still ends with a refreshed supervisor.
4. No agent may be `running` or `initializing` — restarting the daemon
   kills the worker and its child agent processes. When the agent list
   cannot be fetched, the refresh is skipped too; the next package change
   retries. Idle agents do not block the restart; their sessions are
   terminated and can be resumed afterwards.

The installer also runs the guarded check once at install time — `PathModified`
only reports changes that happen after the watcher exists, so an update that
predates the watcher would otherwise sit unrefreshed — and retires (stops,
disables, removes) a watcher from an earlier installation when it can no
longer derive the package scope, instead of leaving it pointed at an old path.

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
| 2 | `harden_daemon_config.py` | Writes `daemon.listen=127.0.0.1:<port>` and manages a bcrypt password hash in `~/.paseo/config.json`. `--port N` / `PASEO_PORT` pick the port (otherwise an interactive prompt offers the current one, Enter keeps). Password: set by default — fresh installs are asked `Set a daemon password? [Y/n]`; existing hashes get `[k]eep / [r]eset / [d]isable`; unattended uses `PASEO_DEPLOY_PASSWORD=<new>` or `PASEO_DEPLOY_NO_PASSWORD=1`. See [Security model](#security-model-enforced-not-optional) |
| 3 | `sync_login_env.py` | Runs a clean login shell once and writes its environment to `~/.config/environment.d/60-paseo.conf` (an existing file is first copied to `60-paseo.conf.bak`) |
| 4 | Generate `~/.config/systemd/user/paseo.service` | `ExecStart` uses the resolved real absolute path (nvm symlinks are expanded with `readlink -f`); the unit sets no `PATH`. Re-runs leave an active daemon running when the unit is unchanged |
| 5 | Generate the supervisor-refresh units + `systemctl --user daemon-reload` + `enable --now paseo-supervisor-refresh.path` | See [Supervisor auto-refresh on update](#supervisor-auto-refresh-on-update); skipped when the `@getpaseo` scope cannot be derived from the resolved binary |
| 6 | `systemctl --user enable --now paseo.service` (when not active) | If an old detached instance is detected it is stopped first with `paseo daemon stop` so it cannot hold the port; restarted when the hardened config changed even if the unit is unchanged |
| 7 | `loginctl enable-linger "$USER"` | Skipped when already enabled |
| 8 | Readiness probe + `paseo daemon status` | Verifies the configured port is listening / `localDaemon: running` |

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
./install.sh --port 6800    # bind 127.0.0.1:6800 (loopback only; 0.0.0.0 is refused,
                            # and a persisted non-loopback listen is reset)
./install.sh --no-install   # skip npm install (paseo must already be on PATH)
./install.sh --no-systemd   # no unit, no sniffing: only npm i -g + hardened config
                            # + `paseo daemon start` (detached; no boot autostart)
./install.sh --dry-run      # sniff and print the generated unit / commands; write nothing, start nothing

PASEO_PORT=6800 ./install.sh              # same as --port 6800
PASEO_DEPLOY_PASSWORD=secret ./install.sh # unattended: set/rotate the password (always wins)
PASEO_DEPLOY_NO_PASSWORD=1 ./install.sh   # unattended: remove the password hash;
                                          # mutually exclusive with PASEO_DEPLOY_PASSWORD
                                          # without either, an existing hash is kept on re-run

python3 -m unittest test_sync_login_env test_supervisor_refresh test_install_sh test_harden_daemon_config   # in this directory; synthetic inputs only, no real login shell or daemon is touched
```

## Notes

- **nvm shims are often invisible to systemd.** The unit's `ExecStart` is
  generated from the resolved real path — do not hand-edit it (the reference
  `paseo.service` in this directory is only an example). `PATH` is not written
  into the unit: `Environment=PATH=...` would replace the user manager's whole
  `PATH`, and `$PATH` is not expanded in a unit.
- **Login-shell snapshot.** `sync_login_env.py` probes the configured login
  shell with a clean environment (`env -i $SHELL -l -c 'env -0'`; the short
  `-l` because ksh/mksh lack `--login`) and writes the result to
  `~/.config/environment.d/60-paseo.conf` (mode `0600`). A plain
  non-interactive login shell stops at the `case $- in *i*)` guard at the
  top of `~/.bashrc` (Debian/Ubuntu dotfiles source it from `~/.profile`, and
  custom `~/.bash_profile` files may not source it at all), so everything
  exported there — nvm, PATH additions, API tokens — would stay invisible.
  Three probes therefore run, each in its own shell so one failing rc cannot
  take down the others: login non-interactive (the base; its failure is a
  hard error), non-login interactive, and login interactive (which wins on
  conflicts). The probes use `TERM=xterm` (some rc files return early on
  `TERM=dumb`) and `HISTFILE=/dev/null` (an interactive probe must never
  touch the real shell history). An existing file is first copied to
  `60-paseo.conf.bak` (not a `.conf`, so systemd ignores it). After
  `daemon-reload`, **every user service started afterwards** inherits this
  snapshot, not only `paseo.service`. Already-running processes are not
  affected. Re-run `./install.sh` after changing `~/.bashrc` /
  `~/.bash_profile` to refresh the snapshot. One caveat: `daemon-reload`
  does **not** override variables the user manager already holds — `PATH` is
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
  snapshot tracks the new toolchain. The installer also *discovers* paseo
  when it is not on PATH at all — installed under an nvm version that is not
  the nvm default, or shadowed by a system node — by scanning the nvm
  versions directory, and deploys with the newest toolchain that provides
  it.
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
