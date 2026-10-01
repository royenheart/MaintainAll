# Agent Note: optional IPv6 listeners for deploy/proxy

Status: implemented — `--ipv6` adds dual-stack Hysteria2 and an IPv6 OpenResty listen; the default stays IPv4-only.

## Problem

`deploy/proxy` bound Hysteria2 to `0.0.0.0` and OpenResty to `listen 443 ssl`. A host that later gained a global IPv6 address still had no listening socket on that address, and publishing an AAAA record sent clients at a closed port. Binding `::` unconditionally would break hosts with IPv6 disabled.

## Decision

`--ipv6` / `ENABLE_IPV6=1` is opt-in.

- Hysteria2 `listen` becomes `::`. On Linux with `net.ipv6.bindv6only=0` (the usual default) that socket accepts IPv4 and IPv6, so there is no second inbound. sing-box 1.14 confirms this: `listen ::` shows up as `*:port` and a second IPv4 bind fails with EADDRINUSE.
- OpenResty templates add `listen [::]:<tls-port> ssl;` next to the existing IPv4 `listen`. nginx turns `ipv6only` on by default for `[::]` and rejects a repeated `ipv6only=` across server blocks, so the option is left at the default. The VLESS inbound stays on `127.0.0.1`; IPv6 clients terminate TLS on OpenResty.
- Default render output is unchanged aside from an explicit "IPv4 only" line: Hysteria2 stays on `0.0.0.0`, and the IPv6 listen line is empty.

The script still does not edit a running reverse proxy. Applying this on a live host is a listen-address edit plus reload/restart, not a credential rotation.

## Alternatives considered

- Always listen on `::`. Rejected because a kernel with IPv6 disabled cannot bind that address, and existing IPv4-only hosts would fail to start.
- A second Hysteria2 inbound on `::` beside `0.0.0.0`. Rejected after checking sing-box 1.14: its `::` socket is dual-stack, so the second bind cannot succeed.
- OpenResty `listen [::]:443 ipv6only=on` on every server block. Rejected: nginx allows that parameter only on the first listen for a given address, and the split VLESS/subscription blocks both use `[::]:443`. The default is already `ipv6only`.

## Consequences

Operators enable IPv6 only after the host has a global address and `bindv6only=0`. DNS AAAA records stay grey-cloud; Cloudflare's proxy does not carry Hysteria2 UDP. A live edit must not re-run `--install`, which generates new UUID and password.
