# Decision: Gitea deployment and address management

Status: implemented — a standalone Python CLI manages the existing Compose deployment and explicit network bindings.

## Problem

Gitea persists its canonical URL and SSH hostname in `/data/gitea/conf/app.ini`. A DHCP change leaves generated URLs pointing at the former address. The original Compose ports publish HTTP and SSH on every host interface, while configuring `ROOT_URL` alone does not restrict that publication. Operators also need repeatable initialization and image updates that retain database credentials and task data.

## Decision

[`deploy/gitea/manage.py`](../../../../../../deploy/gitea/manage.py) manages configuration, startup, status, checking, backups, and Gitea-only image updates. The [base Compose file](../../../../../../deploy/gitea/docker-compose.yml) sends canonical server settings through Gitea's supported environment-to-INI mechanism and advertises the mapped SSH port `3322`, preserving container listener port `22`. The initial administrator is created through Gitea's installation page.

Settings live in an ignored `.env`; existing credential lines and unrelated settings are preserved. New deployments receive a generated database password; existing named volumes with missing credentials cause a failure. Address detection is explicit on refresh. Custom canonical names survive IP changes.

Repeated `--lan-ip` options form an ordered list of arbitrary local IPv4 addresses, including Tailscale addresses without separate classification. Explicit input replaces the entire saved list and defaults to list binding; omitted input preserves the saved list and mode. Every address publishes both service ports, with duplicates removed. The first address supplies the default canonical host. `GITEA_LAN_IPS` stores the comma-separated list and `GITEA_LAN_IP` retains its first address for older configurations. Address discovery uses only the kernel route source and accepts any non-loopback interface. There is no service-specific discovery or separate VPN address setting. Explicit `--bind` supports `lan` (the complete address list), `loopback`, and `all`. Unsupported saved modes fail during configuration with instructions to supply the full desired list; explicit address input replaces that mode. Existing list configurations continue unchanged. Unrelated dotenv lines, including obsolete helper settings, remain preserved but have no effect on address selection.

`init` treats either existing named volume as an existing deployment and exits successfully with an English skip message before modifying configuration, generating credentials, or changing containers. Empty existing volumes receive the same treatment. Existing deployments use `configure`, `up`, or `update` explicitly; missing credentials still block reconfiguration and startup. The CLI code, comments, and messages are English.

A generated, ignored `docker-compose.override.yml` replaces wildcard ports using `!override`. This requires Compose 2.24.4+ and also applies to ordinary Compose invocations that discover the default files. New configurations without explicit addresses use only the route-selected IPv4 address. Additional interfaces are opt-in through the explicit list. Changing the manager does not change live port publication until an operator applies configuration. Container HTTP listening remains `0.0.0.0:3000` because host IPs are not assigned inside its bridge network.

Updates pull only the Gitea image and stop Gitea while archiving `/data` and dumping PostgreSQL. The existing PostgreSQL major version and named volumes remain in place. Backup completion has an explicit marker; failed backups restart a previously running Gitea. Failed upgrades do not automatically downgrade a potentially migrated database. [The deployment guide](../../../../../../deploy/gitea/README.md) describes backup scope and manual recovery requirements.

SSH authentication remains separate from deployment networking. The container's OpenSSH server authorizes keys managed by Gitea; successful HTTP checks and correct port publication do not establish client key access. The [deployment guide](../../../../../../deploy/gitea/README.md#ssh-public-key-authentication) documents fingerprint comparison and explicit client key selection. The manager does not automatically register client keys or grant account access.

## Alternatives considered

- Edit only the persisted INI: fixes one incident but leaves deployment configuration unable to reproduce it and does not manage host bindings.
- Bind container `HTTP_ADDR` to a host IP: the bridge container does not own host LAN/Tailscale addresses; Docker publication is the correct boundary.
- Append restricted ports in an ordinary Compose override: the original wildcard mappings would remain because port merge uniqueness includes the host IP. Full replacement is required.
- Use multiple canonical URLs: Gitea has one `ROOT_URL`; request URL detection does not replace a stable canonical address for background jobs and integrations.
- Automatically refresh on every start or upgrade: could change exposure and canonical URLs unexpectedly. Address refresh is an explicit operation.
- Limit bindings to one LAN address and one Tailscale address: excludes hosts with multiple active interfaces and makes address classification part of basic publication. Explicit lists have no such count or classification restriction. Keeping service-specific discovery and binding modes alongside the list creates overlapping configuration paths and implicit exposure, so the manager uses the list alone.
- Reapply configuration on every `init`: preserves volume contents but can still change exposure, restart services, or run a different locally tagged image. Skipping existing deployments makes repeated initialization a no-op; explicit lifecycle commands carry those changes.
- Automatically upgrade PostgreSQL or roll back failed Gitea migrations: requires separate data migration and restoration decisions beyond a routine application image update.

## Consequences

Operators can refresh DHCP-derived URLs and port bindings together or keep a stable canonical DNS name. Each explicitly bound interface must have its assigned address before the container starts, including VPN interfaces. Canonical links still require a hostname/IP reachable by their recipients; alternate origins may retain a warning. Backups consume local disk until explicitly managed and require off-host copies for host failure recovery. [Focused unittest coverage](../../../../../../tests/test_gitea_manage.py) checks configuration and lifecycle boundaries without mutating the live deployment.
