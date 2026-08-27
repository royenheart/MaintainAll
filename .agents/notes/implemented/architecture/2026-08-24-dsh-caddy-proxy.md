# Agent Note: deploy/ds-harness becomes a Caddy Docker reverse proxy

Status: implemented — `deploy/ds-harness` deploys a Caddy Docker reverse proxy for dsh web and, separately, manages dsh plugins via `plugins.yml`

## Problem

`deploy/ds-harness` previously installed/uninstalled the MaintainAll dsh plugin
set from `plugins.yaml`. The operator instead needs a fast way to reach dsh web
from another machine: dsh web binds `127.0.0.1` only (`--host 0.0.0.0` is
rejected by the CLI), so non-local access previously meant hand-writing nginx
or using `ssh -L`. A local nginx is awkward to configure, so the request is a
one-script Caddy Docker deployment with configurable proxy ports, support for
several dsh instances, and an optional auto-scan of running dsh services.
Plugin management was later re-added as a separate action set (`install` /
`update`) on top of the proxy script; see
[`2026-08-25-dsh-deploy-plugin-management.md`](../feature/2026-08-25-dsh-deploy-plugin-management.md).

## Decision

`deploy/ds-harness/deploy.py` is rewritten as a dependency-free Python 3
script that generates a Caddyfile and runs the `caddy:2` Docker image with
`--network host` (mounting the directory read-only at `/etc/caddy`). Port
mappings use `PORT` or `PROXY:DSH` specs; the default is `3080`, the dsh web
default. `--auto`/`scan` enumerates listening loopback/wildcard TCP ports with
`ss -ltnH`, probes each with a short `GET /`, and treats a response body
containing dsh web's `__DSH_BOOT__` marker as a dsh service (skipping
`Server: Caddy` responses so the proxy does not discover itself).

Each generated site rewrites `Host` and `Origin` to the loopback upstream
authority by default, and when the listen host is a concrete IP the site uses
Caddy's `bind` directive so the proxy can share a port with dsh's
`127.0.0.1` listener (a wildcard `0.0.0.0` bind would conflict with it):

```caddyfile
http://:3080 {
    bind 192.168.31.143
    reverse_proxy 127.0.0.1:3080 {
        header_up Host 127.0.0.1:3080
        header_up Origin http://127.0.0.1:3080
    }
}
```

The default listen host is the default-route source IPv4 (fallback first
global IPv4, then `0.0.0.0`); a wildcard listen with a conflicting loopback
listener is rejected before `docker run` with a remediation hint.

`--tls` switches every site to HTTPS with Caddy's `tls internal` (site address
carries the concrete listen IP, because the internal issuer needs a subject
name). This fixes `crypto.randomUUID is not a function` in browsers, which only
expose `crypto.randomUUID` in secure contexts; plain HTTP on a LAN IP is not
one. TLS mode also emits an explicit `http://IP:80` redirect site per listen IP
and disables Caddy's automatic redirects, so `http://<IP>/` 308s to
`https://<IP>:<proxy-port>/`. Native Caddy cannot multiplex HTTP and HTTPS on
the same port, so `http://<IP>:<proxy-port>` still returns 400; when several
proxy ports share one IP the port-80 redirect targets the first mapping, and
when port 80 is already bound `up` warns and generates HTTPS-only sites.

`--listen` is repeatable: HTTP sites bind all given IPs in one `bind`
directive, while TLS sites emit one site block per IP so each address gets its
own internal certificate.

This is required because dsh's `/api` browser-trust fence rejects non-loopback
Hosts, and privileged methods (`settings`, `credentials`, `host.openPath`, …)
are loopback-only even with `--trusted-host`. The rewrite makes the dsh web
API work through the proxy, which means the proxy is the trust boundary;
`--listen`/`--preserve-host` exist as escapes. The script supports `up`,
`down`, `status`, `scan`, `reload`, and `--dry-run`.

Host/Origin rewriting does NOT make the browser settings UI work through a
LAN proxy. The dsh client disables the settings domain for any non-loopback
`location.hostname` (memory mode, no `settings.describe`), so the Models
settings page reports `settings are unavailable in this browser` even though
the proxied RPCs themselves would pass the rewritten server-side fence. Full
settings access therefore requires a loopback browser URL: local access, or
`--listen 127.0.0.1` with an `ssh -L` forward. `deploy.py up`/`reload` now
probes the served `dsh-client-ui-settings` bundle for that loopback gate and
prints a settings-availability note only when the gate is still present
(silent when a future dsh removes it, and a softer "could not probe" note
when dsh is unreachable); the README documents the workaround.

## Alternatives considered

- **Bind dsh to `0.0.0.0` through a profile patch**: dsh's webserver schema
  accepts `0.0.0.0`, but the web CLI intentionally rejects it for safety and
  the `/api` fence still needs non-loopback `--trusted-host` plus leaves
  privileged methods loopback-only. Rejected: a proxy is the deployment
  boundary the operator actually asked for.
- **Bridge network with `-p` mappings per port**: requires knowing every port
  up front and restarting the container to add one, and reaching host loopback
  needs extra `--add-host`/host-gateway handling. Host networking matches the
  "any number of arbitrary ports" requirement directly. Rejected for this
  deployment.
- **Preserve the original Host header and tell dsh to trust the external
  authority**: keeps dsh's fence in play but forces every dsh instance to be
  restarted with the right `--trusted-host`, and settings/credentials stay
  loopback-only through the proxy. Kept as the `--preserve-host` option
  instead of the default.
- **Keep the old `plugins.yaml` management around**: originally rejected to
  make the directory a pure proxy service; a later change re-added plugin
  management as a separate `plugins.yml`-driven `install`/`update` action set
  (see the plugin-management note).

## Consequences

- `deploy/ds-harness/plugins.yaml` is deleted; deployment actions have no
  runtime dependencies, while `install`/`update` lazy-load PyYAML from
  `plugins.yml`.
- Generated `Caddyfile` is git-ignored in `deploy/ds-harness/.gitignore`.
- Security posture: by default anyone who can reach a proxy port can use the
  full dsh web UI (agent tools included). Operators must restrict `--listen`
  or add Caddy `basic_auth`; the script prints a warning on every `up`.
