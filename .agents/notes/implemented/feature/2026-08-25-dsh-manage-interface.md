# Agent Note: dsh manage interface

Status: implemented — deploy/ds-harness serves a /manage UI from an independent Python backend for monitoring dsh instances and recovering from broken external plugin loads.

## Problem

A remotely-installed dsh plugin can make `dsh` fail to boot (broken module,
malformed bundle `cordis.patch.yml`, unresolvable bundle, or a plugin written
against an older dsh). When that happens, the proxied dsh web UI is down and
the only recovery path is shell access to the server — editing the profile's
`dsh.profile.bundles` or running `dsh plugin remove`. A user travelling with
only the proxy URL has no way back in.

## Decision

- `deploy.py` generates Caddy sites with `/manage/` routed to a new loopback
  Python management backend (`manage.py`, default `127.0.0.1:9090`), started
  and stopped together with the Caddy container. `/manage` is served by the
  proxy, not by dsh, so it survives dsh boot failures.
- Monitoring is best-effort and component-isolated: dsh web probe
  (`__DSH_BOOT__` marker), session count from `$DSH_HOME/sessions/`, process
  metrics via `ss`/`ps`, and per-site traffic from Caddy JSON access logs
  (`data/logs/access-*.json`). Each metric returns `{ok, ...}` and the UI
  degrades only the failed card.
- External-loading control edits the profile `package.json` directly:
  - Per-plugin enable/disable adds/removes the package name in
    `dsh.profile.bundles`. Enabling validates that the dependency is installed
    and declares `dsh.bundle`. Disabling never runs pnpm and never reads the
    plugin's own files, so it works even when the plugin's bundle patch or
    package directory is unreadable.
  - Instance safe mode narrows `dsh.profile.bundles` to the in-box bundles and
    stores the previous list in `data/manage-state.json`; turning it off
    restores that list.
- `instances.yml` optionally declares per-instance `port` / `profile` / `home`;
  when empty, manage falls back to a default instance (3080 / web / ~/.dsh)
  merged with the Caddyfile port mappings.
- The UI is a dependency-free single page (embedded HTML/CSS/JS), styled with
  the same font stack and light/dark neutral-blue palette as the dsh web UI,
  and responsive for phone and desktop.
- The generated Caddyfile also applies proxy-side loading optimizations without
  touching dsh or plugins: `encode zstd gzip` for everything except the event
  streams, long immutable `Cache-Control` for hashed `/plugins/*` and
  `/assets/*` assets, and `Cache-Control: no-cache` for `/` and `/api/*`.

## Alternatives considered

- **Only edit `cordis.patch.yml` to disable plugin rows**: rejected — a plugin
  whose own bundle patch is malformed (or whose package cannot resolve) fails
  during profile composition before the user patch layer can apply. Removing
  the bundle from `dsh.profile.bundles` is the reliable recovery.
- **Use `dsh plugin remove` for per-plugin disable**: rejected for the UI path —
  it depends on pnpm and on reading package metadata; direct manifest editing
  is the smallest operation that always succeeds on disk. `dsh plugin remove`
  remains the supported path for actual uninstall.
- **Let manage.py start/stop dsh processes**: rejected by the user's explicit
  choice — manage does configuration and monitoring only; dsh processes stay
  under the existing launch mechanism.
- **Serve /manage from dsh itself**: rejected — exactly the failure mode this
  feature must survive.

## Consequences

- `up`/`reload` now require a free `--manage-port` (default 9097) and write
  JSON access logs per site; `down` stops the manage backend.
- `manage.py` writes only to `data/manage-state.json` and to the target
  profile's `package.json`; it reads profile metadata best-effort.
- The generated Caddyfile now uses `handle`/`handle_path` blocks so `/manage/`
  routes before the dsh reverse proxy.
- Caddy runs as the host user (`--user`, `--cap-add NET_BIND_SERVICE`) so
  log files and TLS storage are host-readable; upgrading from a root-run
  container requires one `up` run (the old `data/caddy` is renamed aside and a
  new internal CA is generated). As a transitional fallback, the traffic card
  reads unreadable logs via `docker exec`.
- The process card falls back to a `ps`-based `dsh web` match when the
  listening socket cannot be mapped to a pid through `ss`/`/proc` (e.g. a
  non-dumpable dsh process).
- README documents the recovery flow and the `instances.yml` contract.
