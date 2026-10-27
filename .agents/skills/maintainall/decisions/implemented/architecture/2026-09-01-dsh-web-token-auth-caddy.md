# Decision: dsh web token auth through Caddy — 401-aware probes and proxy-injected session cookies (plan B)

Status: implemented — `deploy.py` mints dsh web session cookies per instance and Caddy injects them upstream; `deploy.py`/`manage.py` also recognize the 401 auth challenge; instances resolve `DSH_HOME` through `instances.yml`

## Problem

Newer `dsh web` mints a per-process launch token and prints a login URL
(`http://127.0.0.1:3080/?token=...`, plus a LAN variant). Any request without a
valid token or the resulting session cookie gets
`401 dsh web authentication required; reopen the URL printed by dsh web.`
This broke three deploy/ds-harness assumptions:

- `deploy.py scan` / `--auto` only recognized dsh web by the `__DSH_BOOT__`
  marker in a 200 index document, so an auth-gated instance was invisible.
- `manage.py` reported the same instance as unreachable (HTTP 401).
- The CLI/README still said “dsh has no authentication layer”, which hid both
  the first-login URL shape and the fact that every new device needed a token.

The operator then asked for an intranet “trust zone”: devices that can reach
the proxy should not have to type or even see the dsh web token. dsh has no
native IP/CIDR auth bypass, so the trust zone has to live in the proxy.

## Decision

Two layers:

1. **401-aware probing.** `deploy.py probe_dsh_port` and `manage.py probe_dsh`
   treat a 401 body containing the dsh auth challenge as proof that dsh web is
   up. The manage card shows “在线 · 需 token” (or “在线 · 代理免token” when
   injection is active) instead of “不可达”.

2. **Plan B: Caddy-injected session cookie.** `deploy.py up` / `reload` reads
   each instance's `$DSH_HOME/.credentials.yaml`, extracts the persistent
   `client-connection/browser-session` signing secret, and mints dsh's
   `v1.<payload>.<hmac>` cookie for authority `127.0.0.1:<dsh-port>`. The
   generated Caddyfile adds `header_up Cookie "dsh-auth-...=v1...."` inside
   the dsh upstream block, next to the existing Host/Origin rewrite. Every
   proxied request therefore arrives at dsh already authenticated, and
   intranet devices never see the token gate.

   - Per-port `DSH_HOME` resolution comes from `instances.yml` (the same file
     manage.py already reads); ports missing from it fall back to `~/.dsh`
     with a warning when several dsh ports are proxied.
   - `--auth-cookie-days` (default 30) controls the minted cookie lifetime.
     dsh validates `expiresAt - issuedAt <= cookieMaxAgeDays`, so deployments
     that raise the flag must also patch the profile's `connection` row to a
     matching or larger `cookieMaxAgeDays`.
   - The generated Caddyfile now carries a bearer cookie, so it is written
     `0600`.
   - `--preserve-host` mode skips injection: the cookie authority would no
     longer be loopback and the host rewrite is what makes the minted cookie
     valid.
   - `manage.py` parses the generated Caddyfile for `header_up Cookie` and
     exposes `auth_injected` per instance so the UI shows the right guidance.

## Alternatives considered

- **Add the launch token upstream in Caddy** — rejected: the token is
  per-process random and only exists in dsh web's stdout; Caddy never sees it.
- **Let deploy.py launch dsh web to capture the printed token and run a
  `/login` redirect endpoint** — rejected as the primary plan because it still
  requires every browser to perform a token exchange and only removes the
  typing step, while plan B removes the token gate entirely for proxied
  devices. It remains a viable fallback if dsh changes its cookie format.
- **Native CIDR/trusted-host auth bypass** — does not exist in dsh; nothing to
  configure.
- **Caddy `basic_auth` instead** — not a replacement; dsh still enforces its
  own auth. basic_auth remains an optional extra layer on top.
- **Keep the earlier “token URL through the proxy” only** — works but the
  operator explicitly rejected per-device token entry, so it was demoted to
  the fallback path (`--preserve-host` or before the first `.credentials.yaml`
  exists).

## Consequences

- `scan`, `--auto`, and the manage dashboard work with both old (marker in 200)
  and new (401 challenge) dsh web.
- Default `up` / `reload` now injects a 30-day signed cookie for every dsh
  instance that has already booted once; proxied devices get straight in.
- The proxy is once again the sole trust boundary: anyone who can reach it can
  use dsh. Bind it to a trusted network, use `--listen`, a firewall, or Caddy
  `basic_auth`.
- The implementation duplicates dsh's cookie format (`v1.<payload>.<hmac>`);
  if dsh changes it, `build_upstream_auth_cookies` in `deploy.py` is the single
  place to update.
- Multi-instance correctness depends on `instances.yml` mapping each dsh port
  to the right `DSH_HOME`; a missing entry falls back to `~/.dsh` and may mint
  a cookie the instance rejects.
