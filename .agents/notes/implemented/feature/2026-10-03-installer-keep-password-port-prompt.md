# Agent Note: install.sh keeps an existing daemon password and only restarts on real changes

Status: implemented — re-running the installer used to rotate the password on
every pass and restart the daemon unconditionally; now it offers keep-vs-reset,
can move the port interactively, and leaves a running daemon alone when nothing
changed.

## Problem

Two re-run footguns in `deploy/paseo-daemon/install.sh`:

- Every pass generated or prompted for a password and overwrote
  `daemon.auth.password`. An unattended re-run (no tty, no env) silently
  rotated the hash, breaking every saved client; the new random password only
  appeared in stdout, easily missed in agent/CI logs.
- `CONFIG_HARDENED=1` was unconditional, so every re-run restarted
  `paseo.service` even when nothing changed — killing running agents for no
  reason.

There was also no discoverable way to move a host to a different port: it
worked via `--port`/`PASEO_PORT`, but only for operators who already knew the
flag.

## Decision

- New pure helper `decide_password_action(existing, has_env, has_tty)`
  selects: `env` (PASEO_DEPLOY_PASSWORD always wins = the non-interactive
  rotate path) → `ask` (interactive keep-vs-reset when a hash exists) →
  `prompt-new` (interactive, none set) → `keep` (unattended re-run) →
  `generate` (unattended fresh install). `harden_daemon_config.py` gained a
  `has-password` subcommand so the script never parses `config.json` itself.
- New `prompt_port_override(current)`: when no explicit port was requested
  and a tty exists, offer the current effective port; Enter keeps it, any
  other validated input lands in `PORT` and flows through the existing
  `--port > PASEO_PORT > persisted > 6767` chain.
- `CONFIG_HARDENED` now reflects reality: set only when the listen target
  changed, a password was rotated, or the CORS origin was stripped. An idle
  re-run prints "config unchanged" and does not touch the daemon.

## Alternatives considered

- **Always rotate on re-run, print the new password**: current behavior;
  breaks saved clients silently and panics operators who lost the printed
  password, rejected.
- **`--reset-password` flag instead of an env var**: an env var composes with
  unattended tooling; a flag would need argv plumbing in the same wrappers
  that already pass env. The interactive `n` answer covers humans.
- **Rotate unattended when no tty**: rejected — there is no one to read the
  freshly printed password in that context, and a hash you cannot hand to
  clients is a liability, not a rotation.
- **Keep the unconditional restart as a safety net**: "restarted" is not a
  config-propagation strategy when nothing changed; the remaining triggers
  (listen/password/CORS) are exactly the persisted inputs the daemon reads at
  start.

## Consequences

- Interactive re-runs ask one extra question (keep-vs-reset) — the cost of
  not invalidating clients by default.
- Unattended tooling that *depended* on the old silent rotation must now pass
  `PASEO_DEPLOY_PASSWORD=<new>` explicitly.
- The port prompt only fires without `--port`/`PASEO_PORT`, so scripted runs
  are unaffected.
- Verified with a pty harness (kept out of the repo: it needs the real nvm
  bcryptjs, so it is not hermetic) plus unit tests for `decide_password_action`
  and `has-password` in `test_install_sh.py` / `test_harden_daemon_config.py`.
