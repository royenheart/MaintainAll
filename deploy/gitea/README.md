# Gitea deployment

[`manage.py`](manage.py) manages the existing `gitea` Docker Compose project and its `gitea_gitea` and `gitea_gitea_pg` named volumes. Requirements: Linux, Python 3.10+, Docker access, Docker Compose 2.24.4+, and `ip` for automatic route-source detection. The script uses only the Python standard library and can be called from any working directory.

## Initialize and configure

```sh
cd deploy/gitea
python3 manage.py init --lan-ip auto
```

Initialization generates a strong PostgreSQL password only for a new deployment, saves settings in `.env`, generates `docker-compose.override.yml`, and starts both services. Open the displayed URL and complete Gitea's installation page to create the initial administrator. Initialization automates deployment preparation; administrator setup remains in Gitea. Existing `.env` credentials are preserved. Reconfiguration of existing volumes requires the original credentials; the script never generates replacement credentials for existing data.

If either named volume already exists, `init` prints `init skipped` and exits successfully before changing files, generating credentials, pulling images, or starting/recreating containers. This also applies to `--no-start` and other initialization options; even an existing empty volume is treated as an existing deployment. Use `configure` for an existing deployment, `up` to apply saved configuration, or `update` for a backed-up application image upgrade. Configuration changes on an existing deployment require its original database credentials in `.env`.

Without explicit options, initialization binds only to the IPv4 source address selected by the kernel route lookup. Additional local addresses must be supplied explicitly; no VPN service is queried. `init --no-start` writes configuration without starting services. `--dry-run` previews public settings and port mappings without changing files or containers.

`--lan-ip` is repeatable and accepts any local IPv4 address, including addresses on multiple physical interfaces and Tailscale. Supplying it selects the explicit address list by default; the first address supplies the default canonical host. Each address publishes HTTP `3300` and SSH `3322`. Duplicate addresses are removed while retaining their order. Every explicit address must be assigned to this host when Docker applies the configuration.

If this host has multiple usable IPv4 addresses, such as a LAN address and a VPN address, list each explicitly:

```sh
python3 manage.py configure --lan-ip <LAN_IP> --lan-ip <VPN_IP> --dry-run
python3 manage.py configure --lan-ip <LAN_IP> --lan-ip <VPN_IP> --apply

# Add an address from another local interface.
python3 manage.py configure --lan-ip <LAN_IP> --lan-ip <OTHER_LAN_IP> --lan-ip <VPN_IP> --apply
```

`configure` only saves settings by default; `--apply` recreates Gitea with the locally available image and checks it afterward. It does not pull images or recreate PostgreSQL. Existing configuration is copied into `backups/*-config/` before modification. A Compose validation failure restores the previous configuration files. Applying a saved configuration does not automatically undo it after a runtime failure.

The ignored override completely replaces the original wildcard ports using Compose's `!override` tag. Ordinary `docker compose up -d` from this directory also discovers this override. If using explicit `-f` flags, include both files; selecting only the base file bypasses the restricted bindings. The manager always includes the override when present. It refuses to replace an override it did not generate.

Binding modes apply to **both** HTTP port `3300` and Git SSH port `3322`. An explicit `--bind` overrides the address-list default:

| `--bind` | Host addresses accepting published connections |
| --- | --- |
| `lan` | All addresses in the list, including any explicitly listed Tailscale addresses |
| `loopback` | `127.0.0.1` only, suitable for a host reverse proxy |
| `all` | Docker's wildcard publication, including IPv6 where enabled |

These are destination bindings, not client allowlists. Tailnet access still follows Tailscale grants/ACLs, and routed LAN access depends on the host and network. Docker publishes unspecified host addresses to all interfaces; do not assume a host firewall automatically blocks Docker-published ports. See [Docker port publication](https://docs.docker.com/reference/compose-file/services/#ports).

Gitea **inside the container** continues to listen on `0.0.0.0:3000`; the host addresses belong in Docker's port mappings. Setting container `HTTP_ADDR` to a host LAN/Tailscale IP would fail because that address is not assigned inside the bridge-network container. The external SSH clone port is `3322`, while the container SSH listener remains on `22`.

## Address changes and one canonical URL

```sh
# Refresh the route-selected address and explicitly retain another binding.
python3 manage.py configure --lan-ip auto --lan-ip <VPN_IP> --apply

# Replace the complete address list with one explicit address.
python3 manage.py configure --lan-ip <NEW_LAN_IP> --apply

# Use a stable canonical name after arranging DNS and any HTTPS proxy.
python3 manage.py configure --domain git.example.com --root-url https://git.example.com/ --apply
```

Supplying `--lan-ip` replaces the complete saved list and selects list binding unless `--bind` is also provided; this applies even when only one address is supplied. Omit `--lan-ip` to retain the saved list and binding mode. Consequently, `--lan-ip auto` alone replaces a previous multi-address list with the route-selected address; repeat the other addresses to keep them. `auto` uses a kernel route lookup for `1.1.1.1`, without sending packets, and does not hardcode a physical interface. With multiple routes or a VPN, use explicit addresses if that route is not the desired interface.

Addresses are stored in the ordered, comma-separated `GITEA_LAN_IPS` setting. `GITEA_LAN_IP` retains the first address for compatibility; older single-address configurations load without manual migration. Automatic detection occurs only when requested or when no saved addresses exist. IP-derived `DOMAIN`, `ROOT_URL`, and `SSH_DOMAIN` follow the first address; custom canonical domains/URLs and separate SSH hostnames are preserved. `--root-url`, `--domain`, and `--ssh-domain` override them explicitly. The manager currently supports IPv4 binding options.

There are no Tailscale-specific options, discovery calls, or interface exclusions. The `lan` name is retained for compatibility and means the complete explicit IPv4 list. Old `both` and `tailscale` saved modes are rejected by `configure` before writing files: migrate with `configure --lan-ip <LAN_IP> --lan-ip <VPN_IP> --apply`, using the full desired address list. Existing `lan` configurations already containing both addresses need no migration. A leftover `GITEA_TAILSCALE_IP` line in `.env` is ignored and may be removed. To remove a binding, supply the full desired list without that address.

Reserve the server's DHCP lease on the router to keep the LAN IP stable. For a lasting URL, use a stable DNS name instead of an IP and keep DNS current. When binding specific IPs, refresh the saved bindings too: DNS alone cannot repair a stale Docker host binding. Tailscale must have its assigned address available when Docker starts a container bound to it; if startup fails, start Tailscale and rerun `up`.

`ROOT_URL` describes the canonical external site URL; it does not control listening sockets and accepts one URL. Gitea receives `PUBLIC_URL_DETECTION=auto` so supported request-generated links can follow the request host, but canonical links and background-generated email/webhook URLs still need a stable, reachable `ROOT_URL`. Visiting the alternate IP may still show a mismatch warning. This setting does not create two canonical sites. See the [Gitea 1.25 server settings](https://docs.gitea.com/1.25/administration/config-cheat-sheet/#server-server).

For a stable canonical name, arrange DNS that resolves to an address reachable by each client. When using a VPN-provided DNS name, enable and verify that DNS before switching. A shared name must also resolve for LAN clients that do not use the VPN.

Existing local Git remotes using a previous address, OAuth callback registrations, webhook destinations pointing to this Gitea, and third-party integrations require their own address updates. Changing `ROOT_URL` does not rewrite external clients. For example:

```sh
git remote set-url origin http://<LAN_IP>:3300/OWNER/REPOSITORY.git
# Or use the other reachable host explicitly for Git SSH:
git remote set-url origin ssh://git@<VPN_IP>:3322/OWNER/REPOSITORY.git
```

## SSH public-key authentication

The host publishes `3322` to the container's OpenSSH listener on `22`. The SSH user is `git`; Gitea identifies the account from its registered public key. Browser/HTTP authentication does not register a client SSH key. `Permission denied (publickey)` indicates rejection during SSH authentication, before repository access is checked. See [Gitea SSH troubleshooting](https://docs.gitea.com/1.25/help/faq/#ssh-issues).

Run these commands on the same client that runs `git clone`:

```sh
ssh -vT -p 3322 git@<LAN_IP>
ssh-keygen -lf ~/.ssh/id_ed25519.pub

# Select a nondefault key explicitly; use its actual private-key path.
ssh -vT -o IdentitiesOnly=yes -i ~/.ssh/gitea_ed25519 -p 3322 git@<LAN_IP>
git -c core.sshCommand='ssh -o IdentitiesOnly=yes -i ~/.ssh/gitea_ed25519' clone ssh://git@<LAN_IP>:3322/OWNER/REPOSITORY.git
```

Compare the `Offering public key` fingerprint with the key listed under the intended Gitea account's Settings → SSH / GPG Keys (`/user/settings/keys`). Register the matching `.pub` file if it is absent, or select the private key corresponding to an existing registration. A key registered at another Git service or installed for host SSH access does not automatically authorize this Gitea account. Keep private keys on the client. If `git clone` selects a different SSH executable or key, inspect `git config --show-origin --get core.sshCommand` and the client's `GIT_SSH` / `GIT_SSH_COMMAND` settings.

A successful `ssh -T` prints Gitea's account authentication greeting and explains that shell access is unavailable. It may exit with a nonzero status; inspect the greeting. Then retry the clone.

For server-side comparison without printing key contents:

```sh
docker exec gitea ssh-keygen -lf /data/git/.ssh/authorized_keys
```

The manager's `check` verifies HTTP responses and published port configuration; it does not authenticate an SSH client. A successful check therefore does not establish that a particular client's SSH key is registered.

## Start, inspect, and update

```sh
python3 manage.py up          # Apply saved configuration; use local images.
python3 manage.py status      # Actual container status/ports and desired ROOT_URL.
python3 manage.py check       # Compare running port bindings and probe HTTP/ROOT_URL.
python3 manage.py backup      # Temporarily stop Gitea for a consistent backup.
python3 manage.py update      # Pull the configured Gitea image and update Gitea only.
python3 manage.py update --image docker.gitea.com/gitea:1.25.5
```

`update` pulls only the Gitea image, stops Gitea while taking a `/data` archive and a PostgreSQL custom-format dump, recreates only Gitea, and waits for HTTP checks. PostgreSQL remains on major version 14. Use an explicit compatible Gitea tag or digest when controlling an upgrade; consult [Gitea's upgrade guidance](https://docs.gitea.com/installation/upgrade-from-old-gitea). A fresh initialization may pull missing images; `up` and `configure --apply` use local images.

Backups live in `backups/<UTC timestamp>-data/`: `data.tar`, `postgres.dump`, `.env`, Compose files, the prior running image ID, and a `COMPLETE` marker written only after both data copies succeed. Gitea is restarted after a standalone backup, or if backup fails. During an update, it stays stopped after a successful backup until the new image starts. A later startup/check failure is reported without silently downgrading a potentially migrated database. Inspect `status` and logs and recover from the matching data/database backup if necessary.

All backup files contain private data and are excluded from Git. No backup pruning or volume deletion is performed. Allow space for an uncompressed `/data` archive, copy successful backups off-host, and test restoration separately. Custom external storage outside `/data` is outside this backup's scope.

For recovery, preserve the failed state first, restore the backed-up configuration, use the recorded old image (retain/tag that local image before pruning), stop Gitea, and restore **both** data stores from the same completed backup. With the existing containers present and PostgreSQL running, the data operations are:

```sh
# Recovery commands replace data. Set BACKUP_DIR to a completed backup first.
docker compose stop server
# Empty the existing Gitea /data volume before extraction to remove post-backup files.
# Use a temporary container mounting gitea_gitea at /restore; retain a copy first.
docker cp - gitea:/data < "$BACKUP_DIR/data.tar"
docker compose exec -T db sh -c 'exec pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$BACKUP_DIR/postgres.dump"
python3 manage.py up
```

The archive extraction command does not delete files absent from the archive. Restore into an emptied volume or a separate recovery deployment; do not treat overlaying the archive onto newer data as a complete rollback. Reconcile the old image tag and restored `.env` before `up`. Host-level backup and restore commands are deliberately separate from routine initialization and updates.

## Verification

```sh
python3 -m unittest discover -s tests -p test_gitea_manage.py -v
```

Run the test command from the repository root. Tests cover configuration preservation, explicit address lists, obsolete-mode rejection, route-interface independence, credential protection, backup failure recovery, update ordering, and actual Compose merge behavior without starting containers or pulling images. See [the management decision](../../.agents/skills/maintainall/decisions/implemented/feature/2026-10-19-gitea-management.md).
