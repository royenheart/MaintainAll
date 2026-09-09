# Agent Note: deploy/proxy OpenResty support for the VLESS TCP backup leg

Status: implemented — deploy/proxy now ships a complete OpenResty server block so the
VLESS-over-WS TCP backup can be fronted by OpenResty, not only by a hand-rolled nginx location.

## Problem

`deploy/proxy` deploys two daed importable nodes: Hysteria2 (UDP, primary) and
VLESS+WS+TLS (TCP 443, backup). The scripts deliberately never touch the reverse
proxy, and only printed an nginx `location` snippet meant to be pasted into the
user's own TLS server block. There was no ready-to-use artifact for hosts that
run **OpenResty** (or no reverse proxy at all yet), so standing up the TCP backup
required hand-writing a full `server { listen 443 ssl; ... }` block, including
WS upgrade headers, long-stream timeouts, and correct cert paths.

On the box that motivated this (an EL9 VM with no reverse proxy installed yet,
self-signed TLS material in the user scope, and sing-box exposing its VLESS
inbound only on a private loopback port), the UDP Hysteria2 leg alone was
carrying all traffic and stalling, so the missing TCP backup was both
unavailable and awkward to add.

## Decision

- New `deploy/proxy/openresty/vless-server.conf.template`: a **complete** `server`
  block (TLS listener + `location = <ws-path>` WS reverse proxy + a
  `location / { return 444; }` catch-all that closes everything but the VLESS
  path) with the same placeholders as the existing templates (`__WS_PATH__`,
  `__VLESS_PORT__`, `__TLS_PORT__`, `__SERVER_NAME__`, `__TLS_CERT_PATH__`,
  `__TLS_KEY_PATH__`). TLS material defaults to the same cert/key the Hysteria2
  inbound uses (`--cert-dir` pair, or the generated self-signed pair) — one cert
  set, one secret.
- `deploy.sh` renders it and prints it right after the nginx snippet, in both
  dry-run and `--install` flows. `ADDR`/`SERVER_NAME` are now computed before
  rendering and shared with the import-link section (no behavior change to links).
- `nginx/certbot-restart-sing-box.sh` now also reloads `openresty`/`nginx` when
  active, so a renewed certificate reaches the WS frontend; user-scope
  (`systemctl --user`) sing-box deployments stay out of scope for the root hook.
- README documents the OpenResty route with EL9 install commands and a security
  group note for the public TLS port.

## Alternatives considered

- Keep only the nginx snippet and document manual OpenResty authoring. Rejected:
  the entire failure mode we were fixing is "backup leg too awkward to enable";
  a copy-paste whole `server` block removes the friction and is syntax-checkable
  (`openresty -t`) before touching the live service.
- Ship a separate `--server nginx|openresty` flag choosing which block to print.
  Rejected as premature: both artifacts are small, and printing both costs nothing.
- Run OpenResty in a docker container on the box. Rejected for the general case:
  systemd-native install matches the rest of `deploy/proxy` and the sing-box layout;
  docker remains only a dryrun vehicle (`openresty -t` in a throwaway container).

## Consequences

- Users of nginx see no change; OpenResty users get a complete block to drop into
  `http{}`. The rendered cert/key paths assume the OpenResty master runs as root
  (it reads the key once at startup), which holds for the standard rpm layout.
- Import links are unchanged, so existing daed nodes keep working; adding the TCP
  node to a daed group is a UI action, not a script concern.
- The self-signed + `allowInsecure=1`/`insecure=1` flow remains supported; a real
  domain + certbot remains the recommended hardening, with the hook now reloading
  the WS frontend too.

## Follow-up: HTTPS subscription component (implemented)

The subscription leg is a separate concern from node serving, so it lives as its
own component under `sub/` plus `openresty/sub-server.conf.template` and is served
over **valid-cert HTTPS on the same 443 via SNI split** instead of a dedicated
plaintext port:

- One `server` block per purpose on `listen 443 ssl`, distinguished by
  `server_name`: the VLESS front keeps its IP/self-signed identity (also marked
  `default_server`), the subscription block uses a domain with a Let's Encrypt
  cert issued through DNS-01 (no port 80 required; renewal via a daily cron plus
  the `restart-sing-box.sh` deploy hook). Deleting either conf file leaves the
  other serving — config-level independence without extra firewall ports.
- The subscription payload is just base64 of the share links (see
  `scripts/make-subscription.sh`), holds node credentials, and has no HTTP auth:
  its security model is HTTPS + unguessable path + `return 444` everywhere else.
  Rotating node secrets means regenerating the payload, never touching daed's URL.
- Plain HTTP on a private high port remains documented as a fallback for hosts
  without a domain; it is not the default because the payload is cleartext.
- Remaining process-level coupling is documented: the reverse proxy hosts both the
  VLESS front and the subscription, and a single sing-box hosts both inbounds;
  instance-level isolation is possible but not the default.

