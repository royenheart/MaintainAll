#!/usr/bin/env bash
set -euo pipefail

# =============================================================
# Migrate from the old combined compute-browser-use stack
# =============================================================
#
# One-shot, explicit, dry-runnable. This is NOT part of normal
# deployment — `deploy.py` deploys, this script migrates once.
#
# What it does:
#   - backs up the AstrBot data volume and .env
#   - stops and removes the dead hermes-api / hermes-bridge / cuactl
#     containers
#   - optionally moves the orphaned hermes_connector plugin aside
#   - repairs the hapi-hub systemd unit so HAPI survives a reboot
#   - recreates AstrBot under the new deploy/astrbot stack, adopting
#     the existing volume and container name
#   - optionally reclaims the now-unused images
#
# What it will never do:
#   - delete or replace the AstrBot data volume
#   - touch HAPI itself, its settings, or its port
#   - write AstrBot's cmd_config.json or any plugin configuration
#
# Usage:
#   ./migrate-from-compute-browser-use.sh --dry-run     # preview, changes nothing
#   ./migrate-from-compute-browser-use.sh               # interactive
#
# Flags:
#   --dry-run                 Print every action, change nothing
#   --yes                     Do not prompt
#   --skip-backup             Skip the volume backup (not recommended)
#   --disable-hermes-plugin   Move the orphaned hermes_connector plugin
#                             into data/plugins.disabled/ (reversible)
#   --keep-images             Do not remove the orphaned images
#   --pull                    Also pull the image (upgrades AstrBot). Off
#                             by default: a migration should move the
#                             stack, not change its version.
#   --prune-builder           Also run `docker builder prune` to reclaim
#                             build cache (3 GB+ on the reference host)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- Old stack identifiers (override via environment if needed) ---
OLD_PROJECT="${OLD_PROJECT:-compute-browser-use}"
ASTRBOT_CONTAINER="${ASTRBOT_CONTAINER:-cua-astrbot}"
ASTRBOT_VOLUME="${ASTRBOT_VOLUME:-${OLD_PROJECT}_astrbot_data}"
ASTRBOT_PORT="${ASTRBOT_PORT:-6185}"
HERMES_CONTAINERS=("cua-hermes-bridge" "cua-hermes-api")
CUACTL_CONTAINER="cua-cuactl"
OLD_IMAGES=(
    "${OLD_PROJECT}-hermes-api"
    "${OLD_PROJECT}-hermes-bridge"
    "${OLD_PROJECT}-cuactl"
    "${OLD_PROJECT}-cua-relay"
    # The old stack built AstrBot from a local Dockerfile with two
    # plugins baked in. The new stack runs the upstream image, so this
    # is orphaned as well — and it is the largest of the five.
    "${OLD_PROJECT}-astrbot"
)
OLD_NETWORK="${OLD_PROJECT}_cua-net"
HAPI_UNIT="${HOME}/.config/systemd/user/hapi-hub.service"
BACKUP_DIR="${BACKUP_DIR:-${HOME}/backup}"

DRY_RUN=false
ASSUME_YES=false
SKIP_BACKUP=false
DISABLE_HERMES_PLUGIN=false
KEEP_IMAGES=false
PRUNE_BUILDER=false
# Off by default: the image tag is `latest`, so pulling here would
# upgrade AstrBot as a side effect of migrating it. Opt in with --pull.
PULL=false

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --yes|-y) ASSUME_YES=true; shift ;;
        --skip-backup) SKIP_BACKUP=true; shift ;;
        --disable-hermes-plugin) DISABLE_HERMES_PLUGIN=true; shift ;;
        --keep-images) KEEP_IMAGES=true; shift ;;
        --pull) PULL=true; shift ;;
        --prune-builder) PRUNE_BUILDER=true; shift ;;
        --help|-h)
            sed -n '4,45p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

step() { echo; echo -e "${BOLD}${BLUE}[$1] $2${NC}"; }
info() { echo -e "  $*"; }
ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}!${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }

# Run a command, or just print it under --dry-run.
run() {
    if $DRY_RUN; then
        echo -e "  ${YELLOW}[dry-run]${NC} $*"
    else
        echo -e "  ${BLUE}+${NC} $*"
        "$@"
    fi
}

# Same, but through a shell (for pipes and redirects).
run_sh() {
    if $DRY_RUN; then
        echo -e "  ${YELLOW}[dry-run]${NC} sh -c '$1'"
    else
        echo -e "  ${BLUE}+${NC} sh -c '$1'"
        sh -c "$1"
    fi
}

confirm() {
    $ASSUME_YES && return 0
    $DRY_RUN && return 0
    echo
    echo -n "  $1 [y/N] "
    read -r reply
    [[ "$reply" == "y" || "$reply" == "Y" ]]
}

container_exists() { docker inspect "$1" >/dev/null 2>&1; }
container_running() { [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == "true" ]]; }
volume_exists() { docker volume inspect "$1" >/dev/null 2>&1; }
image_exists() { docker image inspect "$1" >/dev/null 2>&1; }

http_ok() {
    python3 - "$1" "$2" <<'PY' 2>/dev/null
import sys, urllib.request
port, path = sys.argv[1], sys.argv[2]
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
}

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Migrate off the combined compute-browser-use stack${NC}"
echo -e "${GREEN}============================================${NC}"
$DRY_RUN && echo && echo -e "${YELLOW}${BOLD}  DRY RUN — nothing will be changed${NC}"

# ---------------------------------------------------------------------------
step "1/8" "Preflight"
# ---------------------------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    fail "docker not available"; exit 1
fi
ok "docker present"

if [[ ! -f "$SCRIPT_DIR/docker-compose.yml" ]]; then
    fail "docker-compose.yml not found next to this script"
    exit 1
fi
ok "new stack present: $SCRIPT_DIR"

if ! volume_exists "$ASTRBOT_VOLUME"; then
    fail "volume '$ASTRBOT_VOLUME' not found."
    info "  Known volumes:"
    docker volume ls --format '    {{.Name}}' | grep -i astrbot || info "    (none)"
    info "  Set ASTRBOT_VOLUME=... to target the right one."
    exit 1
fi
ok "data volume '$ASTRBOT_VOLUME' found"

if container_running "$ASTRBOT_CONTAINER"; then
    ok "AstrBot container '$ASTRBOT_CONTAINER' is running"
else
    warn "AstrBot container '$ASTRBOT_CONTAINER' is not running"
fi

# HAPI must stay untouched. Report what we see so the operator can confirm.
echo
info "${BOLD}HAPI (preserved by this migration):${NC}"
if command -v hapi >/dev/null 2>&1; then
    info "  binary   : $(command -v hapi)"
else
    warn "  binary   : not on PATH"
fi
if python3 - <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(); s.settimeout(2)
sys.exit(0 if s.connect_ex(("127.0.0.1", 3006)) == 0 else 1)
PY
then
    ok "  hub      : listening on :3006"
else
    warn "  hub      : not listening on :3006"
fi
# `systemctl is-active` prints its state *and* exits non-zero when the
# unit is not running, so the state must be captured separately or the
# fallback text gets appended to it.
hapi_active="$(systemctl --user is-active hapi-hub.service 2>/dev/null | head -1 || true)"
hapi_enabled="$(systemctl --user is-enabled hapi-hub.service 2>/dev/null | head -1 || true)"
info "  systemd  : ${hapi_active:-unknown} / ${hapi_enabled:-unknown}"

# ---------------------------------------------------------------------------
step "2/8" "Backup"
# ---------------------------------------------------------------------------

if $SKIP_BACKUP; then
    warn "skipped (--skip-backup)"
else
    TS="$(date +%Y%m%d-%H%M%S)"
    VOL_TAR="${BACKUP_DIR}/astrbot_data-${TS}.tar.gz"
    run mkdir -p "$BACKUP_DIR"
    info "volume -> $VOL_TAR"
    run_sh "docker run --rm -v '${ASTRBOT_VOLUME}:/v:ro' -v '${BACKUP_DIR}:/b' alpine tar czf '/b/$(basename "$VOL_TAR")' -C /v ."
    if [[ -f "$SCRIPT_DIR/.env" ]]; then
        run cp "$SCRIPT_DIR/.env" "${BACKUP_DIR}/astrbot-env-${TS}"
        info ".env   -> ${BACKUP_DIR}/astrbot-env-${TS}"
    fi
    ok "backup complete"
fi

# ---------------------------------------------------------------------------
# Everything below changes state.
# ---------------------------------------------------------------------------
if ! $DRY_RUN && ! $ASSUME_YES; then
    echo
    echo -e "  ${BOLD}About to:${NC}"
    echo "    - stop and remove AstrBot, ${HERMES_CONTAINERS[*]} and $CUACTL_CONTAINER"
    if $DISABLE_HERMES_PLUGIN; then
        echo "    - move the hermes_connector plugin into plugins.disabled/"
    fi
    echo "    - repair the hapi-hub systemd unit"
    echo "    - recreate AstrBot from the new stack (volume '$ASTRBOT_VOLUME' is kept)"
    $KEEP_IMAGES || echo "    - remove the orphaned ${OLD_PROJECT}-* images"
    $PRUNE_BUILDER && echo "    - prune the docker build cache"
    confirm "Proceed?" || { echo "  Aborted — nothing was changed."; exit 0; }
fi

# ---------------------------------------------------------------------------
step "3/8" "Stop AstrBot (volume kept)"
# ---------------------------------------------------------------------------

if container_exists "$ASTRBOT_CONTAINER"; then
    run docker stop "$ASTRBOT_CONTAINER"
    ok "stopped"
else
    info "not present, nothing to stop"
fi
# The container is removed in step 7, after volume-level work is done.

# ---------------------------------------------------------------------------
step "4/8" "Orphaned hermes_connector plugin"
# ---------------------------------------------------------------------------

PLUGIN_IN_VOLUME="/AstrBot/data/plugins/astrbot_plugin_hermes_connector"
PLUGIN_DISABLED="/AstrBot/data/plugins.disabled"

has_plugin() {
    docker run --rm -v "${ASTRBOT_VOLUME}:/v:ro" alpine \
        test -d "/v/plugins/astrbot_plugin_hermes_connector" 2>/dev/null
}

if $DRY_RUN; then
    info "would check for the plugin inside the volume"
elif has_plugin; then
    warn "hermes_connector is still installed; its backend is being removed,"
    warn "so it will log reconnect failures until uninstalled."
    if $DISABLE_HERMES_PLUGIN; then
        run_sh "docker run --rm -v '${ASTRBOT_VOLUME}:/v' alpine sh -c 'mkdir -p /v/plugins.disabled && mv /v/plugins/astrbot_plugin_hermes_connector /v/plugins.disabled/'"
        ok "moved to ${PLUGIN_DISABLED}/ (move it back to reinstall)"
    else
        info "  Leave it alone with the default; re-run with"
        info "  ${BOLD}--disable-hermes-plugin${NC} to move it aside, or uninstall it in the dashboard."
    fi
else
    ok "plugin not installed"
fi

# ---------------------------------------------------------------------------
step "5/8" "Remove the dead containers"
# ---------------------------------------------------------------------------

for c in "${HERMES_CONTAINERS[@]}"; do
    if container_exists "$c"; then
        run docker rm -f "$c"
        ok "removed $c"
    else
        info "$c not present"
    fi
done

if container_exists "$CUACTL_CONTAINER"; then
    run docker rm -f "$CUACTL_CONTAINER"
    ok "removed $CUACTL_CONTAINER"
else
    info "$CUACTL_CONTAINER not present"
fi

# AstrBot itself is recreated in step 7, so remove it here too.
if container_exists "$ASTRBOT_CONTAINER"; then
    run docker rm -f "$ASTRBOT_CONTAINER"
    ok "removed $ASTRBOT_CONTAINER (will be recreated from the new stack)"
fi

if docker network inspect "$OLD_NETWORK" >/dev/null 2>&1; then
    run docker network rm "$OLD_NETWORK" 2>/dev/null && ok "removed network $OLD_NETWORK" \
        || warn "network $OLD_NETWORK still in use, left in place"
fi

# ---------------------------------------------------------------------------
step "6/8" "Repair the hapi-hub systemd unit"
# ---------------------------------------------------------------------------

# HAPI was originally launched by the old deploy.py with nohup
# (start_new_session=True), which is why it shows PPID 1 and its own
# session id. That code is gone from this repository, so the systemd unit
# is now the only thing that brings HAPI back after a reboot — and it was
# written with a literal placeholder path, so it never worked. The
# running process only survived because the host has not rebooted since
# it was started by hand.
#
# Two directives have to be right, not one:
#
#   1. ExecStart must name the real binary.
#   2. PATH must include the nvm bin directory. The hapi shim starts with
#      `#!/usr/bin/env node`, and a systemd --user unit gets a minimal
#      PATH (/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin) with no
#      nvm on it, so a *correct* ExecStart still dies with
#      "env: node: No such file or directory". HAPI also spawns the agent
#      CLIs it manages (codex, opencode), so those directories have to be
#      reachable too or sessions cannot start at all.

HAPI_BIN="$(command -v hapi || true)"
NODE_BIN="$(command -v node || true)"

if [[ ! -f "$HAPI_UNIT" ]]; then
    warn "no unit at $HAPI_UNIT — create one so HAPI survives a reboot"
    info "  ExecStart=${HAPI_BIN:-/path/to/hapi} hub --no-relay"
elif [[ -z "$HAPI_BIN" ]]; then
    warn "hapi not on PATH; cannot repair the unit automatically"
    info "  fix ExecStart in $HAPI_UNIT manually"
else
    # Build a PATH covering what HAPI needs, without dragging in the
    # interactive shell's conda/direnv entries. Directories are
    # deduplicated because hapi and node usually live in the same nvm
    # bin directory, and a repeated entry would make the comparison
    # below report a difference that is not real.
    unit_path_dirs=()
    add_path_dir() {
        local d="$1" existing
        [[ -d "$d" ]] || return 0
        if (( ${#unit_path_dirs[@]} > 0 )); then
            for existing in "${unit_path_dirs[@]}"; do
                [[ "$existing" == "$d" ]] && return 0
            done
        fi
        unit_path_dirs+=("$d")
    }
    for d in "$(dirname "$HAPI_BIN")" \
             "$(dirname "${NODE_BIN:-$HAPI_BIN}")" \
             "${HOME}/.opencode/bin" \
             "${HOME}/.local/bin" \
             /usr/local/bin /usr/bin /bin; do
        add_path_dir "$d"
    done
    UNIT_PATH="$(IFS=:; echo "${unit_path_dirs[*]}")"

    wanted_exec="ExecStart=${HAPI_BIN} hub --no-relay"
    wanted_path="Environment=PATH=${UNIT_PATH}"

    current_exec="$(grep -m1 '^ExecStart=' "$HAPI_UNIT" || true)"
    current_path="$(grep -m1 '^Environment=PATH=' "$HAPI_UNIT" || true)"

    info "ExecStart  current: ${current_exec:-<none>}"
    info "           wanted : $wanted_exec"
    info "PATH       current: ${current_path:-<none>}"
    info "           wanted : $wanted_path"

    if [[ "$current_exec" == "$wanted_exec" && "$current_path" == "$wanted_path" ]]; then
        ok "unit already correct"
    else
        if [[ "$current_exec" != "$wanted_exec" ]]; then
            warn "ExecStart is wrong — HAPI would not restart after a reboot"
        fi
        if [[ "$current_path" != "$wanted_path" ]]; then
            warn "PATH is missing nvm — the unit would fail with 'node: not found'"
        fi
        if $DRY_RUN; then
            echo -e "  ${YELLOW}[dry-run]${NC} repair $HAPI_UNIT"
        else
            cp "$HAPI_UNIT" "${HAPI_UNIT}.bak-$(date +%Y%m%d-%H%M%S)"
            python3 - "$HAPI_UNIT" "$wanted_exec" "$wanted_path" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
exec_line, env_line = sys.argv[2], sys.argv[3]

out, seen_exec, seen_env = [], False, False
for line in path.read_text().splitlines():
    if line.startswith("ExecStart=") and not seen_exec:
        out.append(exec_line)
        seen_exec = True
    elif line.startswith("Environment=PATH=") and not seen_env:
        out.append(env_line)
        seen_env = True
    else:
        out.append(line)

# Missing directives go at the top of [Service], not at the end of the
# file, which would drop them into [Install] where systemd ignores them.
def service_start(lines):
    for i, line in enumerate(lines):
        if line.strip() == "[Service]":
            return i + 1
    return len(lines)

if not seen_exec:
    out.insert(service_start(out), exec_line)
if not seen_env:
    out.insert(service_start(out), env_line)

path.write_text("\n".join(out) + "\n")
PY
            run systemctl --user daemon-reload
            ok "unit repaired (original saved as ${HAPI_UNIT}.bak-*)"
        fi
        info "  Restart it when convenient:  systemctl --user restart hapi-hub"
        info "  (at the time of writing no HAPI session was running)"
    fi
fi

# ---------------------------------------------------------------------------
step "7/8" "Recreate AstrBot under the new stack"
# ---------------------------------------------------------------------------

# Adopt the existing volume and keep the container name stable.
#
# The password is carried over from the old .env purely so the new file
# is never blank: AstrBot rejects an empty
# ASTRBOT_DASHBOARD_INITIAL_PASSWORD outright, and this compose always
# passes it. The value is ignored on an already-initialised volume — the
# real password lives in the volume.
OLD_ENV_FILE="${SCRIPT_DIR}/../${OLD_PROJECT}/.env"
OLD_PASSWORD=""
if [[ -f "$OLD_ENV_FILE" ]]; then
    OLD_PASSWORD="$(grep -m1 '^ASTRBOT_DASHBOARD_PASSWORD=' "$OLD_ENV_FILE" | cut -d= -f2- || true)"
    if [[ -n "$OLD_PASSWORD" ]]; then
        info "carrying the dashboard password over from $(cd "$(dirname "$OLD_ENV_FILE")" && pwd)/.env"
    fi
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    info "no .env yet — writing one that adopts the existing volume"
    if $DRY_RUN; then
        echo -e "  ${YELLOW}[dry-run]${NC} write $SCRIPT_DIR/.env"
        [[ -z "$OLD_PASSWORD" ]] && \
            info "  (nothing to carry over — ./deploy.py up would generate one)"
    else
        {
            echo "# Written by migrate-from-compute-browser-use.sh"
            echo "# The dashboard password already lives in the volume and is"
            echo "# only honoured when AstrBot initialises a fresh one."
            echo "ASTRBOT_DASHBOARD_PASSWORD=${OLD_PASSWORD}"
            echo "ASTRBOT_TAG=latest"
            echo "ASTRBOT_CONTAINER=${ASTRBOT_CONTAINER}"
            echo "ASTRBOT_PORT=${ASTRBOT_PORT}"
            echo "ASTRBOT_VOLUME=${ASTRBOT_VOLUME}"
            echo "TZ=Asia/Shanghai"
        } > "$SCRIPT_DIR/.env"
        ok "wrote $SCRIPT_DIR/.env"
        [[ -z "$OLD_PASSWORD" ]] && \
            info "  password blank — ./deploy.py up will generate one"
    fi
else
    ok ".env present"
    if grep -q "^ASTRBOT_VOLUME=" "$SCRIPT_DIR/.env"; then
        info "  ASTRBOT_VOLUME=$(grep '^ASTRBOT_VOLUME=' "$SCRIPT_DIR/.env" | cut -d= -f2-)"
    else
        warn "  ASTRBOT_VOLUME not set — the new stack would start from an EMPTY volume"
    fi
    if ! grep -q "^ASTRBOT_DASHBOARD_PASSWORD=..*" "$SCRIPT_DIR/.env"; then
        warn "  ASTRBOT_DASHBOARD_PASSWORD is blank — ./deploy.py up will generate one"
    fi
fi

# Go through deploy.py rather than raw compose: it validates the
# dashboard password (a blank ASTRBOT_DASHBOARD_INITIAL_PASSWORD makes
# AstrBot refuse to start on a fresh volume) and waits for the dashboard
# — the same path a normal deploy takes.
#
# --no-pull keeps the currently installed AstrBot version. The tag is
# `latest`, so pulling here would quietly upgrade AstrBot as a side
# effect of migrating it; upgrading should be a deliberate, separate
# step (`./deploy.py up`).
if $PULL; then
    run ./deploy.py up
else
    run ./deploy.py up --no-pull
fi
ok "AstrBot started from the new stack"

# ---------------------------------------------------------------------------
step "8/8" "Verify and reclaim"
# ---------------------------------------------------------------------------

if $DRY_RUN; then
    info "would wait for the dashboard and run ./deploy.py status"
else
    ready=false
    for _ in $(seq 1 20); do
        http_ok "$ASTRBOT_PORT" "/" && { ready=true; break; }
        sleep 5
    done
    if $ready; then
        ok "dashboard reachable on :${ASTRBOT_PORT}"
    else
        warn "dashboard did not answer on :${ASTRBOT_PORT} — check ./deploy.py logs"
    fi

    echo
    info "Configuration as AstrBot now sees it:"
    ./deploy.py status || warn "status failed"
fi

if ! $KEEP_IMAGES; then
    echo
    for img in "${OLD_IMAGES[@]}"; do
        if image_exists "$img"; then
            run docker rmi "$img" 2>/dev/null && ok "removed image $img" \
                || warn "could not remove $img (still in use?)"
        fi
    done
fi

if $PRUNE_BUILDER; then
    echo
    run docker builder prune -f
    ok "build cache pruned"
fi

echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Migration complete${NC}"
echo -e "${GREEN}============================================${NC}"
echo
info "HAPI was not touched. Confirm it is still reachable:"
info "  ./deploy.py status    # then check the hapi_connector plugin in the dashboard"
echo
