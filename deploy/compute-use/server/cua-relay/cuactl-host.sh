#!/bin/bash
# cuactl — CUA Relay CLI for host-level usage.
# Translates cuactl commands to HTTP calls to the remote Client Control Plane.
#
# Preferred install: run `./deploy.py server` in deploy/compute-use. It
# writes a wrapper into ~/.local/bin with the correct absolute path for
# that checkout, so nothing needs configuring here.
#
# Manual install:
#   cp server/cua-relay/cuactl-host.sh ~/.local/bin/cuactl
#   chmod +x ~/.local/bin/cuactl
#   export CUA_HOME=/path/to/deploy/compute-use   # the checkout holding .env
#
# Configuration: CUACTL_ENDPOINT and CUACTL_TOKEN, read from $CUA_HOME/.env
set -euo pipefail

if [ -z "${CUA_HOME:-}" ]; then
    echo "cuactl: CUA_HOME is not set." >&2
    echo "  Point it at the deploy/compute-use checkout, or just run" >&2
    echo "  ./deploy.py server there to install this wrapper for you." >&2
    exit 1
fi

# Load .env if present so CUACTL_ENDPOINT / CUACTL_TOKEN are available.
if [ -f "$CUA_HOME/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$CUA_HOME/.env"
    set +a
fi

exec python3 "$CUA_HOME/server/cua-relay/relay_server.py" "$@"
