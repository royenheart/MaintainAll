# AstrBot — minimal deployment

Deploys AstrBot and nothing else.

```sh
cp .env.example .env      # or: ./deploy.py setup-env
./deploy.py up            # pull image, start, wait for the dashboard
```

Then open the dashboard (default <http://127.0.0.1:6185>) and configure
it there.

## Scope: deploy only

This stack deliberately does **not** configure AstrBot.

- No custom image. The upstream `soulter/astrbot` image is used
  directly, so updating is a plain image pull.
- No pre-installed plugins. Install them from the dashboard or the
  plugin market; AstrBot persists them in its data volume.
- No configuration injection. `deploy.py` never writes
  `cmd_config.json`, never touches a plugin's `_conf_schema.json`, and
  never injects LLM providers.

The one exception is `./deploy.py status`, which reads
`cmd_config.json` to report what is configured. It opens the file
read-only and writes nothing.

Why so strict: the previous generation of this deploy script injected
providers and patched plugin schema defaults at deploy time. Those
writes were only applied once, so later manual edits in the dashboard
silently diverged from what the script believed, and re-running it
could not reconcile them. Configuration is now owned entirely by the
operator.

## Layout

```
docker-compose.yml   AstrBot service (upstream image, one volume)
deploy.py            setup-env / up / down / status / logs / shell
export.sh            back up the data volume + .env
restore.sh           restore that archive
.env                 local config (gitignored)
```

## Commands

| Command | Effect |
| --- | --- |
| `./deploy.py setup-env` | Generate `.env`, including a dashboard password |
| `./deploy.py up` | `compose pull` + `up -d`, then wait for the dashboard |
| `./deploy.py down` | Stop and remove the container. **Volume kept.** |
| `./deploy.py down --wipe` | Also delete the volume (asks first) |
| `./deploy.py status` | Read-only health check and config summary |
| `./deploy.py logs -f` | Tail container logs |
| `./deploy.py shell` | Shell inside the container |

`up --no-pull` skips the pull when you want a fast restart on the
current image.

## Updating

The image tag is configurable, and updating is one command:

```sh
./deploy.py up              # pulls, recreates, waits
```

For anything you depend on, pin the tag rather than tracking `latest`:

```sh
./deploy.py setup-env --tag v4.26.2
```

Pinning is recommended because a plugin or provider schema change
upstream can need a manual config migration. The image is never built
locally, so there is no build cache to invalidate — a pull plus a
recreate is the whole update.

## Configuration

Everything lives in `.env`:

| Variable | Default | Notes |
| --- | --- | --- |
| `ASTRBOT_DASHBOARD_PASSWORD` | — | Applied **only** on first init of the volume |
| `ASTRBOT_TAG` | `latest` | Image tag |
| `ASTRBOT_CONTAINER` | `astrbot` | Container name |
| `ASTRBOT_PORT` | `6185` | Host port |
| `ASTRBOT_VOLUME` | `astrbot_data` | Data volume name |
| `TZ` | `Asia/Shanghai` | Container timezone |

### The dashboard password is first-boot only

`ASTRBOT_DASHBOARD_INITIAL_PASSWORD` is honoured when AstrBot
initialises its data directory. Once the volume exists, changing this
value has **no effect** — the password lives in the volume. Change it
in the dashboard instead, or start from a fresh volume.

AstrBot rejects passwords without an upper case letter, a lower case
letter and a digit; `setup-env` enforces this.

## The data volume

`AstrBot/data` is the only stateful thing in this stack. It holds the
dashboard credentials, IM platform logins, the session database,
workspaces, the knowledge base and installed plugin state. The
container is disposable — recreate it freely.

Back it up before changing anything:

```sh
./export.sh                        # → export-astrbot-<timestamp>.tar.gz
./deploy.py down
./restore.sh export-astrbot-*.tar.gz --dry-run
./restore.sh export-astrbot-*.tar.gz
./deploy.py up
```

`restore.sh` replaces the volume wholesale and never overwrites a live
`.env` — it writes `.env.restored` for you to review and merge.

## Adopting an existing volume

Compose names volumes after the project unless told otherwise, so a
previous deployment under a different directory produced a
project-scoped volume name such as
`compute-browser-use_astrbot_data`. Point `ASTRBOT_VOLUME` at it to
keep the existing data:

```sh
./deploy.py setup-env --volume compute-browser-use_astrbot_data
./deploy.py up
./deploy.py status          # confirm platforms and providers are intact
```

Find candidate volumes with:

```sh
docker volume ls | grep -i astrbot
```

## Migrating from the old combined stack

If this host previously ran AstrBot as part of the combined
`compute-browser-use` stack, `migrate-from-compute-browser-use.sh` moves
it over in one shot:

```sh
./migrate-from-compute-browser-use.sh --dry-run   # preview, changes nothing
./migrate-from-compute-browser-use.sh             # interactive
```

It backs up the data volume and `.env`, stops and removes the dead
hermes-api / hermes-bridge / cuactl containers, repairs the `hapi-hub`
systemd unit, and recreates AstrBot here while adopting the existing
volume and container name.

It never deletes the volume, never touches HAPI, and does not pull — so
migrating cannot quietly upgrade AstrBot. Useful flags:

| Flag | Effect |
| --- | --- |
| `--dry-run` | Print every action, change nothing |
| `--yes` | No prompts (for non-interactive runs) |
| `--skip-backup` | Skip the volume backup |
| `--disable-hermes-plugin` | Move the orphaned hermes plugin into `plugins.disabled/` |
| `--keep-images` | Leave the orphaned images alone |
| `--pull` | Also pull the image (upgrades AstrBot) |
| `--prune-builder` | Also prune the docker build cache |

## Not managed here

Providers, plugins, IM platform connections, agents and personas are
all configured in the dashboard. Nothing in this directory needs to
know about them, which is what keeps updates boring.
