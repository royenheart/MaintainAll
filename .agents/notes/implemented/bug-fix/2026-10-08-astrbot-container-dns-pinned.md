# Agent Note: deploy/astrbot — pin container DNS to public resolvers

Status: implemented — `deploy/astrbot/docker-compose.yml` pins `dns:` to Tencent Cloud public resolvers so container DNS never inherits transient host resolver state

## Problem

On 2026-10-07 the operator disabled Tailscale MagicDNS. Long-lived containers had captured MagicDNS addresses (`100.100.100.100`, `fd7a:115c:a1e0::53`) as their embedded-DNS upstreams at create time; Docker never refreshes them, so the `cua-astrbot` container lost all name resolution. The QQ official websocket, the WeChat poll, and both LLM providers failed on DNS for roughly 24h before the outage was noticed; the container log held ~200k DNS error lines in a 5-second reconnect loop. Root cause sat in Docker's DNS snapshot behavior, not in AstrBot.

## Decision

Pin `dns:` in `deploy/astrbot/docker-compose.yml` to `183.60.83.19` / `183.60.82.98` — the resolvers a Tencent Cloud CVM receives via DHCP, verified reachable from the host — exposed as `ASTRBOT_DNS_1` / `ASTRBOT_DNS_2` so a non-Tencent host can substitute its own resolver pair in `.env`. Documented in the README Configuration section. Applied on tencent-brain via `docker compose up -d --force-recreate` after a full backup: volume export, `docker commit` of the writable layer, full container logs, and compose/.env snapshots under `/root/astrbot-backup-20261008/` on that host.

## Alternatives considered

- **Plain `docker restart`**: the container's resolv.conf is generated at container *create* time; restart reuses it. Verified: the managed resolv.conf still carried the September-era MagicDNS upstreams. Insufficient.
- **`docker network disconnect` + `connect`**: rewrites the container's resolv.conf, but it is not guaranteed to rebuild upstreams from the host's *current* resolver, and it adds a network blip while leaving DNS coupled to whatever the host happens to use. Rejected in favour of the deterministic pin.
- **Re-enable Tailscale MagicDNS**: zero-touch recovery (the captured upstreams start answering again), but it conflicts with the operator's reason for disabling it and keeps container DNS coupled to tailnet state. Documented as a valid no-change fallback, not the fix.
- **Pin a public recursive resolver pair instead** (e.g. AliDNS `223.5.5.5` / `223.6.6.6`): arguably more generic, but the host is a Tencent Cloud CVM whose DHCP resolvers are the pinned pair, so keeping them preserves pre-outage behavior exactly and avoids routing DNS to a third party. Kept configurable via `ASTRBOT_DNS_1`/`ASTRBOT_DNS_2` instead.
- **Leave DNS inherited from the host**: zero configuration, but recreates the same outage whenever the host resolver changes. Rejected.

## Consequences

- Container DNS is decoupled from host/Tailscale resolver state; toggling MagicDNS or switching VPN DNS can no longer break AstrBot's QQ/WeChat/LLM connectivity.
- The defaults are Tencent Cloud VPC DNS (documented by Tencent as VPC resolvers, not public recursive DNS for arbitrary clients); a non-Tencent host must set `ASTRBOT_DNS_1` / `ASTRBOT_DNS_2` in `.env` before `up`. The compose interpolation renders the same values the running tencent-brain deployment already uses, so adopting this change there needs no recreation.
- The pin only takes effect on (re)creation: `docker compose up -d --force-recreate`. Recreation is safe — all state lives in the data volume, and the report pipeline's `bootstrap.sh` re-heals the container layer (playwright, CJK fonts, pip deps) on its next run.
- `docker commit` does not include volume content, so volume backups must always accompany a commit-based image backup.
