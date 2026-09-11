# Compute Use — client + relay

The computer-use capability: control a remote desktop from an agent.

Two halves, deployed separately:

| Piece | Runs on | Role |
| --- | --- | --- |
| **client** (`client/`) | the machine being controlled (Windows primary; Linux/macOS supported) | Client Control Plane — FastAPI service on `:9111`, with tray app, permissions and deterministic ops |
| **relay** (`server/cua-relay/`) | a Docker host | `cuactl` microservice translating `/cuactl/<command>` into HTTPS + token calls against the client |

The relay publishes no host port by design. It exists so that
containers can drive the desktop without holding the client's token.

This stack holds no LLM credentials and no agent configuration. Which
agent drives the desktop — and how — is out of scope.

## Quick start

### 1. Client (on the machine to be controlled)

```sh
./deploy.py client
```

Detects the OS, installs dependencies, prompts for a bind address and
prints the `CLIENT_TOKEN`. On Windows this also covers the tray app and
permission modes.

### 2. Relay (on the Docker host)

```sh
./deploy.py setup-env      # paste the CLIENT_TOKEN, set the endpoint
./deploy.py server         # build + start the relay, install the host CLI
```

## Commands

| Command | Effect |
| --- | --- |
| `./deploy.py client` | Deploy the control plane on this machine |
| `./deploy.py setup-env` | Generate `.env` (client token, endpoint) |
| `./deploy.py server` | Build and start the relay container |
| `./deploy.py status` | Read-only health check |
| `./deploy.py down` | Stop the relay |

## Configuration

`.env`:

| Variable | Notes |
| --- | --- |
| `CLIENT_TOKEN` | Shared secret between relay and client |
| `CUACTL_ENDPOINT` | `https://<client-host>:9111` |
| `CUACTL_TOKEN` | Defaults to `${CLIENT_TOKEN}` |
| `CUACTL_CONTAINER` | Container name (default `cuactl`) |
| `CUA_NETWORK` | Docker network (default `cua-net`) |

## Giving an agent desktop access

Two options.

**Host-side** — `./deploy.py server` installs a `cuactl` wrapper into
`~/.local/bin` that talks to the client directly:

```sh
cuactl list-apps
cuactl open-app --app_name Chrome
cuactl capture
```

`skills/cua-desktop-control/SKILL.md` documents the full command
surface for an agent.

**In-network** — attach any agent stack to the relay's network:

```yaml
networks:
  cua-net:
    external: true
```

Then call `http://cuactl:8000/cuactl/<command>` from that container.

## Status

`./deploy.py status` is read-only. It reports whether the relay
container is running, what the relay's own `/health` says, and whether
the client endpoint answers. A client that is offline, or whose
control plane is not running, shows up here.

## Security

- The client control plane holds the real authority over the desktop;
  its permission mode (`readonly` / `full` / `strict`) is set on the
  client, in the tray.
- The relay is only reachable from containers on `CUA_NETWORK`.
- `CUACTL_ENDPOINT` is HTTPS; the client presents a self-signed
  certificate, so callers disable verification or pin the certificate
  in the agent stack.

## Tests

```sh
python3 -m pytest tests/test_deploy.py       # deployment script
cd client && python3 -m pytest tests/        # client control plane
```
