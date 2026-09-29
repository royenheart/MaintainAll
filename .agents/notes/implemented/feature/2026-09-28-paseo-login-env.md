# Agent Note: paseo user service inherits a login-shell snapshot

Status: implemented — `deploy/paseo-daemon/install.sh` no longer pins `PATH` in the unit; `sync_login_env.py` writes a login-shell snapshot to `~/.config/environment.d/60-paseo.conf`.

## Problem

`paseo.service` set `Environment=PATH` to a short literal list (node, `~/.local/bin`, `~/bin`, and the system directories). systemd does not expand `$PATH` in a unit, so that line replaces the user manager environment instead of extending it. Agent CLIs installed only via `~/.bashrc` / `~/.bash_profile`, such as `~/.kimi-code/bin`, stay invisible to the daemon and to processes it spawns. The user manager itself never reads shell startup files; a graphical login imports them once, and that snapshot goes stale until the next login.

## Decision

Keep the installer in user config only. On each systemd install:

- Probe `$SHELL -l` (the short flag: ksh/mksh lack `--login`) under `env -i` (home, user, a minimal `PATH`, `TERM=xterm` — some rc files return early on `TERM=dumb` — and `HISTFILE=/dev/null` so an interactive probe cannot touch the real history) and capture `env -0`.
- Probe twice more, each in its own shell so one failing rc cannot take down the others: non-login interactive (`$SHELL -i`, reads ~/.bashrc directly, covering dotfiles where ~/.bash_profile does not source it) and login interactive (`$SHELL -l -i`, the full login context). Merge into the plain result with the login interactive probe winning on conflicts; a failing soft probe is skipped. Without these, a plain non-interactive login shell never gets past the `case $- in *i*)` guard at the top of `~/.bashrc` (Debian/Ubuntu dotfiles source it from `~/.profile`), and everything exported after the guard — nvm, PATH additions, API tokens — stays missing from the snapshot (on nebusec-dev: 9 variables instead of 17, no `NVM_DIR`).
- Drop session variables (`DISPLAY`, `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`, and the rest of that set) and shell bookkeeping.
- Escape `$` and `\` so `environment.d` does not expand or line-continue them.
- If `60-paseo.conf` already exists, copy it to `60-paseo.conf.bak` (not a `.conf`, so the generator ignores it), then atomically replace the file mode `0600`.
- Generate the unit without `Environment=PATH`. `ExecStart` stays an absolute `paseo` path. Refuse to rewrite the unit when the probed `PATH` has no `node`, because the `paseo` shebang is `/usr/bin/env node`.
- Merge the install-time toolchain into the exported PATH. `install.sh` passes the bin directories of the resolved `paseo` and `node` to `sync_login_env.py --ensure-path-dir`, and the snapshot prepends them when missing (de-duplicated). The daemon's self-update runs `npm -g ls @getpaseo/cli` with this PATH, so it must resolve the npm whose global prefix owns the install. On a host where a bare login-shell probe sees a system node first (or no node at all), the probe alone picks the wrong npm and the update fails with "@getpaseo/cli is not installed with npm -g on this host" — see [paseo daemon env npm pairing](../bug-fix/2026-09-30-paseo-daemon-env-npm-pairing.md).

`daemon-reload` re-runs the user environment generators, so services started afterwards inherit the snapshot — with one exception: it does not override variables the user manager already holds, and `PATH` is pinned when the user manager starts (at boot/login), long before `60-paseo.conf` exists. The installer therefore pushes the freshly probed PATH into the manager explicitly (`systemctl --user set-environment PATH=…`, via `sync_login_env.py --emit-env PATH`) right after `daemon-reload`. Already-running processes are not affected.

## Alternatives considered

- Keep appending directories to the unit `PATH`. A unit assignment replaces the variable and does not expand `$PATH`, so the service would still miss the user manager's existing toolchain unless every directory is copied by hand.
- `ExecStart=/bin/bash -lc 'exec paseo …'`. That re-reads the shell on every start, including `Restart=on-failure`, and a prompt or a failing `bashrc` takes the service down with it.
- A user environment generator under `/etc/systemd/user-environment-generators`. That is system configuration, runs for every user, and a bad stdout can fail the user manager on its next cold start.
- Prepend only `~/.kimi-code/bin` in `environment.d`. That fixes one binary and leaves later shell exports (and non-`PATH` variables the shell sets) out until someone edits the file again.
- Tell users to "export things before the `.bashrc` guard". Dotfile layout is out of the deploy's control; the multi-probe merge gets the same result without touching user files.
- Probe with `bash -l -i` only. That covers the Debian `~/.profile` → `~/.bashrc` chain, but not hosts whose custom `~/.bash_profile` never sources `~/.bashrc`; the non-login interactive probe reads it directly.
- Force-source `~/.bashrc` from the probe command (`bash -c '. ~/.bashrc; env -0'`). The same `case $-` guard still returns early in a non-interactive shell, so this buys nothing without `-i`.
- Run the interactive probes with `TERM=dumb`. Some rc files return early on `TERM=dumb`, so a regular terminal type is set instead; stray stdout would be discarded by the `env -0` parser anyway, and job-control chatter goes to stderr.
- Let an interactive probe use the real `HISTFILE`. `bash -i` may save history on exit; pointing `HISTFILE` at `/dev/null` makes that a no-op.

## Consequences

The snapshot applies to every user service started after `daemon-reload`, not only `paseo.service`. Secrets exported by the login shell are stored in `60-paseo.conf` and are visible through `systemctl --user show-environment`. Refreshing the shell means re-running `install.sh`, which restarts the daemon only when the regenerated unit actually differs (see [paseo supervisor auto-refresh](2026-09-29-paseo-supervisor-auto-refresh.md)); the PATH half of the refresh is the explicit `set-environment` push, so a stale manager PATH cannot silently survive a re-install. `--no-systemd` does not probe; a detached `paseo daemon start` keeps inheriting the terminal that launched it.
