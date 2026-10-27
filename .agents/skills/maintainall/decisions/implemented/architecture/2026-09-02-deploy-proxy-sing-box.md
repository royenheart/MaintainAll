# Decision: deploy/proxy — generic sing-box private proxy template for daed

Status: implemented — `deploy/proxy/` is a generic sing-box template (Hysteria2 + VLESS-WS) with generate-only default and an optional `--install` that never touches nginx

## Problem

The operator wanted a private overseas proxy node for daed, first with deployment scripts written into `deploy/proxy`. An initial version hard-coded the operator's host/domain/IP and made `--apply-nginx` edit a concrete nginx server block. That embedded personal data in the repo and gave a deploy script write access to nginx, which is too invasive for a reusable template.

## Decision

Make `deploy/proxy/` generic and side-effect-free by default:

- `scripts/deploy.sh` with no flags only renders `config.json`, the nginx `location` snippet, and daed import links; it touches neither local services nor the remote host.
- `--install` uploads and installs sing-box + systemd on the remote only. It never reads or edits nginx; the nginx snippet is always printed for the operator to apply manually.
- All identity removed from templates/scripts: no ssh alias, no public IP, no domain, no cert path. Values come from CLI flags or environment variables (`--host`, `--ip`, `--sni`, `--cert-dir`, ports, version).
- If `--cert-dir` is not provided, the installer generates a self-signed cert on the remote and the printed Hysteria2 link uses `insecure=1`; with `--cert-dir` it uses the operator's `fullchain.pem`/`privkey.pem` and links stay verifiable.
- VLESS remains WS+TLS behind the operator's own nginx: the operator pastes the printed `location` into their TLS server block and reloads nginx themselves.

## Alternatives considered

- **Keep auto-applying nginx**: less manual work, but a generic script must not assume nginx paths or service names, and the operator explicitly asked to remove direct nginx modification. Rejected.
- **Keep hard-coded node identity**: made the first version immediately useful for the operator's host but leaked personal info and was not reusable. Rejected after operator feedback.
- **Use Reality instead of VLESS-WS**: still the best TCP throughput, but requires nginx to move off 443. Rejected (operator declined nginx listener changes).
- **Single Hysteria2 only**: simplest, but no TCP fallback. Rejected as the sole protocol; kept as primary.
- **Drop nginx/WS entirely**: would make the template simpler but removes the only safe TCP backup when UDP is blocked. Rejected.

## Consequences

- The script is reusable across hosts; all host-specific values are supplied at run time.
- nginx is only changed by the operator, after reviewing the printed snippet.
- Self-signed Hysteria2 requires either `allow_insecure=true` in daed or supplying a valid cert via `--cert-dir`.
- The operator must ensure the remote firewall/security group allows the chosen UDP port (default 443) and that TCP 443 reaches nginx for VLESS-WS.
