# Agent Note: Hardened paseo-daemon deployment (loopback-only + mandatory password)

Status: implemented — a no-password Paseo daemon admits every connection as the owner principal, and loopback is host-wide; on this shared machine other users could see and control the deployer's daemon, so the deploy script now enforces the baseline instead of documenting it.

## Problem

`deploy/paseo-daemon/install.sh` installed and ran the daemon but left two
security properties to chance:

- The listen address. Paseo defaults to `127.0.0.1:6767`, and loopback feels
  private but is host-wide: any local user (and anyone who can forward a port
  to the machine) connects to the first daemon that binds the port.
- The daemon password. Paseo's `resolveSessionAdmission` admits any connection
  as `principalId: "owner"` with full permissions when no password is set.

On this multi-user machine that combination let other users see and operate
the deployer's workspaces and agents. The fix had to live in the deploy path:
anything that is not enforced on every run silently decays.

## Decision

`install.sh` now hardens the persisted config on every run, before the daemon
is (re)started:

1. **Loopback only.** `daemon.listen` is rewritten to `127.0.0.1:<port>` in
   `~/.paseo/config.json`. `--port N` / `PASEO_PORT` select the port (default:
   the persisted port, else 6767). A persisted non-loopback value is reported
   and reset. `harden_daemon_config.py` refuses to write a non-loopback target
   at all, so there is no supported path to a `0.0.0.0` deploy from this
   script. Direct LAN/mobile access is deliberately out of scope; remote access
   uses relay pairing.
2. **Password always set.** Input priority: `PASEO_DEPLOY_PASSWORD` (agents /
   unattended) → interactive prompt on `/dev/tty` → auto-generated random
   password printed exactly once. Plaintext never reaches disk, the units, or
   `60-paseo.conf`; only a bcrypt hash (cost 12, via the installed CLI's own
   bcryptjs) is stored in `config.json`. Interactive auto-generation hides the
   value behind an Enter-to-clear screen.
3. **Restart on change.** `CONFIG_HARDENED` forces a daemon restart whenever
   the config changed, even when the unit file is unchanged, so hardened
   settings cannot sit un-loaded by a long-running worker.

Local CLI/desktop clients stay passwordless via `~/.paseo/local-credential`
(0600). Two adjacent concerns are documented but not managed: the
`https://app.paseo.sh` CORS entry is Paseo's shipped default for the hosted
web app, and relay pairing stays enabled as the mobile path (its pairing link
is a credential; current daemon builds still admit credential-less relay
clients during a compat window).

## Alternatives considered

- **Document the hardening, don't enforce it.** Lost: the incident that
  motivated this note happened with documentation available. Enforcement on
  every run is the only variant that survives.
- **A `--listen` flag with host validation.** Lost: keeps a footgun in the
  interface; anyone can still hand-edit `config.json`. Writing the loopback
  target from the installer (and refusing anything else in the helper) closes
  the path instead of guarding it.
- **`PASEO_PASSWORD` in the `60-paseo.conf` environment snapshot.** Lost: the
  plaintext would persist on disk in an environment file — exactly the record
  the no-plaintext rule exists to avoid. The bcrypt hash in `config.json` is
  the durable form.
- **Use `paseo daemon set-password` for every path.** Lost: it requires a TTY
  and cannot express the generate-and-print-once flow. It remains the
  documented rotation command.
- **Bind a Unix socket instead of TCP.** Lost: phones and the desktop
  Remote/SSH transport cannot reach a socket file; TCP on a distinct loopback
  port is the only mode that serves both local multi-user isolation and
  relay-based mobile access.

## Consequences

- Re-running `install.sh` never weakens the posture: the listen is re-asserted
  and the password is only ever replaced, never removed.
- Losing an auto-generated password means running `paseo daemon set-password`
  (local clients self-authenticate, so only remote/mobile users notice).
- Mobile clients are prompted for the password when pairing/connecting; relay
  remains the only supported remote transport for this deployment.
- Hardening depends on `harden_daemon_config.py` and on bcryptjs shipping next
  to the installed `@getpaseo` scope; both are covered by hermetic unit tests
  (`test_harden_daemon_config.py`, `test_install_sh.py`).
