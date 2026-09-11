# Agent Note: split compute-use and AstrBot into separate deploy stacks

Status: implemented — the combined stack deployed an agent, an LLM
provider injector and a desktop relay that had nothing to do with each
other, and its deploy script rewrote live configuration.

## Problem

`deploy/compute-browser-use/` was one directory holding four coupled
services: `astrbot`, `hermes-api`, `cuactl` and a `hermes-bridge`
fallback. Its `deploy.py` (2722 lines) did far more than deploy:

- It injected every LLM provider found in `.env` into AstrBot's
  `cmd_config.json`, rewriting `provider_sources`, `provider` and
  `provider_settings.default_provider_id`.
- It patched plugin `_conf_schema.json` files inside the container to
  change their `default` values, for both the hermes and HAPI
  connectors.
- It deployed the Hermes Agent, cloned two AstrBot plugins into a
  custom image, installed coding-agent CLIs on the host and started a
  HAPI hub.

Two properties made this fragile:

1. **Config writes were one-shot and invisible.** Patching a schema
   `default` only takes effect when the key is absent. AstrBot's
   `AstrBotConfig` inserts missing keys from the schema but lets an
   existing value in `data/config/<plugin>_config.json` win. So once an
   operator saved anything in the dashboard, later deploys silently
   stopped applying, and re-running the script could not reconcile the
   difference.
2. **Rollback was coupled to data.** The only way to re-apply an
   injected default was often to recreate the volume, which also
   destroyed the dashboard credentials, IM platform logins, session
   database and installed plugins — none of which the script owned.

A production instance on `tencent-brain` confirmed the cost. Only
AstrBot was in use; `hermes-api` had an empty `sessions/` directory and
a `state.db` untouched for 70 days, and `cuactl` had served nothing but
its own health checks across 200k log lines. Meanwhile AstrBot itself
was live behind two IM platforms that the deploy script never
configured — it left `platform_sources` untouched — and the operator
had built on top of the injected provider source, so the injected
config could not simply be removed.

## Decision

Split the stack in two, and make deployment stop writing configuration.

- `deploy/compute-use/` owns the computer-use capability: the client
  control plane (`client/`) and the `cuactl` relay
  (`server/cua-relay/`). It holds no LLM credentials and no agent
  config.
- `deploy/astrbot/` owns AstrBot and nothing else. It uses the upstream
  `soulter/astrbot` image directly — no custom image, no pre-installed
  plugins, no config injection.
- The Hermes Agent, the hermes→AstrBot bridge and the HAPI connector
  wiring are deleted. `hermes_connector` and `hapi_connector` are
  installed from the dashboard when wanted.

`deploy/astrbot/deploy.py` reports but never writes: `up`, `down`,
`logs`, `shell`, and a `status` command that reads `cmd_config.json`
read-only to summarise platforms, providers and dashboard state.

Supporting decisions:

- **The data volume name is explicit and overridable**
  (`ASTRBOT_VOLUME`), because a compose project renaming itself would
  otherwise silently start from a fresh volume. Adoption of an existing
  volume is a documented one-liner.
- **`down` keeps volumes; only `down --wipe` removes them**, and it
  asks first. The volume holds state the script did not create.
- **`extra_hosts: host.docker.internal:host-gateway` is kept.** A
  "minimal" compose would drop it, but `hapi_connector` reaches the HAPI
  hub at `http://host.docker.internal:3006`, where HAPI runs as a host
  process. Without the mapping the name does not resolve and that plugin
  stops working silently — no error, just an endpoint that never
  answers. A test now guards the directive.
- **`ensure_dashboard_password()` runs before `up`.** AstrBot's
  `_resolve_initial_dashboard_password()` passes the env value to
  `validate_dashboard_password()`, which rejects an empty string. This
  compose always passes `ASTRBOT_DASHBOARD_INITIAL_PASSWORD`, so a blank
  value in `.env` — which is exactly what `.env.example` ships — made
  the container refuse to start on a fresh volume. Substituting a valid
  password before starting removes the failure mode; on an initialised
  volume the value is ignored anyway.

Update is an image pull: the tag is configurable (`ASTRBOT_TAG`) so a
host can pin instead of tracking `latest`.

## Migrating the live instance

`deploy/astrbot/migrate-from-compute-browser-use.sh` is a separate,
one-shot script rather than a mode of `deploy.py`, because it exists to
tear down one specific historical deployment and will be irrelevant
afterwards. It is explicit, dry-runnable, and never deletes the volume.

Four behaviours are deliberate:

- **It does not pull.** The default tag is `latest`, so a migration that
  pulled would silently upgrade AstrBot as a side effect of moving it.
  Upgrading stays a separate, deliberate `./deploy.py up`; `--pull`
  opts in.
- **It goes through `./deploy.py up`** rather than raw `docker compose`,
  so the password guard above applies to the migration too.
- **It repairs the `hapi-hub` systemd unit.** See below.
- **It never removes volumes.** The orphaned `hermes_data` volume is
  reported, not deleted.

### The hapi-hub unit had two independent defects

HAPI was previously started by the old `deploy.py` with
`Popen(..., start_new_session=True)` behind `nohup`. That is why the
live process showed `PPID 1`, its own session id, and a `cwd` inside the
deployment directory. Since that code is deleted here, the systemd unit
is the only thing that brings HAPI back after a reboot — and it had
never worked, for two unrelated reasons:

1. `ExecStart=/path/to/hapi hub --no-relay` was a literal placeholder.
2. Even with a correct `ExecStart`, the `hapi` shim begins with
   `#!/usr/bin/env node` while a `systemd --user` unit gets a minimal
   PATH with no nvm on it, so it died with `node: No such file or
   directory`. HAPI also spawns the agent CLIs it manages (codex,
   opencode), which must be reachable for any session to start.

The script therefore repairs both directives, and the repair was
validated on the live host: the unit starts, `/api/auth` returns a JWT
from inside the AstrBot container, the plugin's SSE listener reconnects,
and a `SIGKILL` of the main process is recovered by `Restart=always`.

The running process was only ever alive because the host had not
rebooted in 72 days, which is what hid both defects.

## Alternatives considered

- **Keep one stack, just delete the injection code.** Rejected: the two
  halves have different lifecycles, credentials and blast radii. A
  desktop relay that needs the client's HTTPS endpoint has no reason to
  share an `.env` or a compose project with a chat gateway.
- **Keep writing config, but idempotently and with a migration step.**
  Rejected: the failure mode is not staleness, it is ownership. Two
  writers of the same file — the script and the dashboard — diverge no
  matter how careful the script is, because the operator's edits are
  not visible to it.
- **Have the astrbot stack keep building a custom image with the two
  plugins baked in.** Rejected: it removes the ability to update by
  pulling, and plugin installation is exactly what the plugin market
  already does.
- **Have `deploy.py` help "update" AstrBot's config.** Rejected:
  deployment is run by hand on hosts outside this repo's control, so an
  automatic writer can rewrite a live instance on a mistaken run.
  Config stays with the operator; the script only reports.
- **Drop the `cuactl` relay too, keeping only the client.** Considered
  seriously, since on the live host the relay had no consumer. Rejected
  because it is the in-network entry point a containerised agent needs,
  and it costs one small container to keep.

## Consequences

- Deploying AstrBot can no longer change provider or plugin settings.
  `deploy/astrbot/tests/test_deploy.py` asserts this: the source must
  not contain `json.dump(`, `_conf_schema`, `docker cp` or
  `docker restart`, and the inspection script both opens read-only and
  tolerates AstrBot's UTF-8 BOM.
- A fresh AstrBot deploy is bare. There is no automatic provider, no
  plugin and no IM platform — the README states this and `status`
  reports "(none configured)" for platforms, since that is the single
  most likely reason a new instance receives no messages.
- Existing installs need `ASTRBOT_VOLUME` pointed at their old
  project-scoped volume to keep their data; the old name is documented
  in `.env.example` and the README.
- `export.sh` and `restore.sh` moved to `deploy/astrbot/` and now cover
  the AstrBot volume only. `restore.sh` writes `.env.restored` rather
  than overwriting `.env`, because the archive's `.env` belongs to the
  exporting host.
- The `cuactl` relay publishes no host port and joins a named, joinable
  network (`CUA_NETWORK`, default `cua-net`) so an agent stack can
  attach with `external: true`.
- Untracked research material under the old path (`external/`, 1.2 GB
  of cloned upstreams) was left in place rather than deleted; the
  directory is otherwise empty.
- Deleting the old `.gitignore` while moving files out would have
  un-ignored that 1.2 GB and made it stageable, so the old directory kept
  a small `.gitignore` guarding its remaining scratch.
- Migrating the reference host reclaimed roughly 13 GB: images fell from
  5.6 GB to 2.9 GB and container layers from 10.6 GB to 56 MB. The
  orphaned images include the old custom `compute-browser-use-astrbot`
  image, which is the largest of them and was easy to overlook because it
  does not carry a service name.
- Three defects surfaced only by running the migration against a real
  host: the missing `extra_hosts`, the blank-password crash, and a
  missing execute bit on `deploy.py` — the last aborted the migration
  midway, after it had already removed the container. The executable-bit
  check is now a test.
