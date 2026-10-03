# Agent Note: paseo-daemon password is default-on and removable, not mandatory

Status: implemented — the deploy's password policy changed from "always set"
to "set by default, explicitly removable", on fresh installs and on re-runs.

## Problem

The installer enforced a password on every run: fresh installs could not opt
out, and a re-run could keep or rotate but never remove the hash. The
operator's requirement is weaker policy with the same safe defaults: default
to a password, allow choosing none on first install, and allow resetting or
fully disabling it later, interactively and unattended.

## Decision

- `decide_password_action()` gained a fourth input (has_clear) and two new
  actions. Priority is unchanged at the top — `env` (PASEO_DEPLOY_PASSWORD)
  still wins — followed by the new `clear` (PASEO_DEPLOY_NO_PASSWORD=1).
  Interactive: `ask-fresh` (no hash: `Set a daemon password? [Y/n]`, Enter =
  set) and `ask` (hash exists: `[k]eep (Enter) / [r]eset / [d]isable`).
  Unattended behavior is unchanged: keep an existing hash; generate only when
  none is set.
- Setting and clearing env vars together is a hard error (`die` before the
  decision), not a precedence call — silently ignoring one would rotate or
  wipe a password the operator thought they had set.
- `harden_daemon_config.py` gained `clear-password`: it drops
  `daemon.auth.password` and removes an emptied `auth` section, so the config
  reads as if no password had ever existed. Clearing counts as a config
  change (`CONFIG_HARDENED=1`), so the daemon restarts and actually stops
  asking.
- Opting out (fresh "n") and clearing both print the standing warning about
  the owner-principal admission model via a shared `warn_passwordless()`.

## Alternatives considered

- **`PASEO_DEPLOY_PASSWORD=` (empty) as the clear signal**: an unset and an
  empty var are indistinguishable to operators at a glance; a separate
  positively-named flag is self-documenting and lets "unset" keep its current
  meaning.
- **Clear silently wins over set (or vice versa)**: two explicit, opposite
  instructions in one environment are a contradiction; guessing wrong
  silently rotates or wipes authentication. Loud failure is cheaper.
- **Keep an emptied `auth: {}` like the CORS explicit-deny**: unlike an empty
  allowedOrigins, an empty auth section carries no semantic difference from
  absent; dropping it keeps the config minimal and matches "as if never set".
- **Interactive sub-menu loops until valid input**: one-shot with a safe
  default (keep) was enough; a typo landing on "keep" never destroys access.

## Consequences

- An unattended re-run on a host whose password was intentionally cleared
  regenerates one (existing=0 + no env + no tty → `generate`). That is the
  stated "default on" policy; operators who want no password must leave
  `PASEO_DEPLOY_NO_PASSWORD=1` in their unattended invocation.
- Removing the password invalidates every client saved with it, same as a
  rotation — the keep/reset/disable prompt says so.
- Verified with unit tests for `decide_password_action` (new signature) and
  `clear-password`, plus the pty flow harness (kept out of the repo: it needs
  the real nvm bcryptjs, so it is not hermetic).
