#!/bin/bash
# cuactl — CUA Relay CLI for host-level usage.
# Translates cuactl commands to HTTP calls to the remote Client Control Plane.
#
# Install: cp cuactl-host.sh ~/.local/bin/cuactl && chmod +x ~/.local/bin/cuactl
# Configuration: CUACTL_ENDPOINT and CUACTL_TOKEN env vars (from .env)
exec python3 /home/royenheart/softwares/MaintainAll/deploy/compute-browser-use/server/cua-relay/relay_server.py "$@"
