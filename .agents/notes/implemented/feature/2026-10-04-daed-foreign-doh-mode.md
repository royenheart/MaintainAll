# Agent Note: daed foreign-IP DoH mode

Status: implemented — `deploy/daed` can seed or switch a foreign IP-literal DoH mode without touching `deploy/doh-dns`

## Problem

UDP port 53 answers can arrive before the real reply. daed was sending foreign lookups to `tcp+udp://8.8.8.8:53`, so an injected packet was accepted. After MagicDNS is off, `systemd-resolved` is `must_direct` and falls back to the router, whose upstream is still plaintext UDP. A domestic DoH forwarder (`deploy/doh-dns`, `dns.conf.doh`) encrypts the query but still asks resolvers inside China, which can answer blocked names incorrectly.

## Decision

Two modes live in `deploy/daed`. The split is who resolves, not Tailscale versus DoH. Tailscale only used to occupy the system resolver.

- `direct` stays the default: `geosite:cn` uses `udp://223.5.5.5:53`, everything else uses `tcp+udp://8.8.8.8:53`, `fallback_resolver` stays `223.5.5.5:53`, and `systemd-resolved` stays `must_direct`.
- `doh` is optional at first seed (`init --dns-mode doh`) and switchable later (`dns-mode doh`). Foreign lookups use `https://8.8.8.8/dns-query` or `https://1.1.1.1/dns-query`. `fallback_resolver` moves to that address's port 53. The selected routing row drops `systemd-resolved` from the `must_direct` process rule so its port 53 queries enter daed.
- `dns.conf.doh` and `deploy/doh-dns` stay the separate "port 53 is blocked, borrow `127.0.0.1:5353`" path. They are not this mode and are not the default.
- `init` still inserts only into empty tables. `dns-mode` copies `wing.db` with SQLite's backup API, then updates the selected DNS row, `fallback_resolver`, and that one routing line in one transaction. Other rows, including private rules, are not rewritten. A lock error aborts with the database unchanged. daed must be restarted afterwards.

## Alternatives considered

- **Foreign lookups over TCP 53 only.** Injected UDP cannot enter that connection, but a reset fails the lookup and `fallback_resolver` was still `223.5.5.5:53`. Rejected as the durable fix; direct mode keeps `tcp+udp` so the default behavior does not change.
- **Reuse `dns.conf.doh` / `deploy/doh-dns`.** Those upstreams are domestic and can return the wrong address for blocked names. Rejected for this mode.
- **A second script.** `daed-init.py` already owns `wing.db`. A subcommand keeps the empty-database rule on `init`. Rejected as a new file.
- **Rewrite whole `dns` / `configs` / `routings` tables on an existing database.** That would discard Web UI edits to nodes, groups, and routing. Rejected. The switch replaces only the selected DNS text and patches two fields.
- **Write `bootstrap_resolver` or `subnode()` rules.** daed 1.27.0 has `fallback_resolver` and `https://` upstreams, and does not contain those newer keys. Writing them could make daed refuse the config. Rejected.

## Consequences

- A cut TLS connection to `8.8.8.8:443` or `1.1.1.1:443` fails resolution instead of dialing a forged address such as `2406:cb42::`.
- `fallback_resolver` is still plaintext UDP because dae accepts only `ip:port` there. It no longer points at `223.5.5.5`. The query path is DoH.
- `udp_check_dns` is unchanged. Node health checks can still flap between hy2 and vless because of latency.
- Domestic names still use AliDNS UDP.
- Switching modes replaces the selected DNS row with the mode template. Other edits in that row are overwritten. `lan_interface` and private routing rules stay.
- Template files on disk stay in the direct-mode shape. DoH patches are applied to the text inserted or updated in `wing.db`.
