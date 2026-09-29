#!/usr/bin/env bash
# Paseo daemon one-shot deploy: install the CLI -> systemd --user service
# (enabled at boot) -> verify. Also installs a supervisor-refresh watcher:
# a .path unit on the installed @getpaseo package + an oneshot that restarts
# paseo.service after an update (skipping while agents are busy), because an
# updated package alone never refreshes the running supervisor process.
#
# Background: the Paseo GUI's Remote/SSH only connects to a daemon that is
# already running; it never installs, starts, or configures one remotely, and
# `paseo daemon start` merely detaches a background supervisor (writing
# ~/.paseo/paseo.pid and daemon.log) without registering boot autostart — so
# after a reboot nothing listens on 6767 again.
# This script follows the "user systemd manages the daemon" approach (the old
# install-user-daemon.sh from this repo was removed together with the old
# MaintainAll daemon): hand the daemon to systemd --user plus
# `loginctl enable-linger`, so crashes and reboots bring it back automatically.
#
# Env: PASEO_HOME (default ~/.paseo), PASEO_LISTEN_ADDR (default 127.0.0.1),
#      and PASEO_PORT (default 6767) override the readiness probe target.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="paseo.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"
REFRESH_SERVICE_NAME="paseo-supervisor-refresh.service"
REFRESH_PATH_NAME="paseo-supervisor-refresh.path"
REFRESH_SCRIPT="$SCRIPT_DIR/supervisor_refresh.py"
PKG_SCOPE_DIR="" # resolved from PASEO_BIN by resolve_pkg_scope()
PASEO_HOME="${PASEO_HOME:-$HOME/.paseo}"
PID_FILE="$PASEO_HOME/paseo.pid"
LOG_FILE="$PASEO_HOME/daemon.log"
LISTEN_ADDR="${PASEO_LISTEN_ADDR:-127.0.0.1}"
LISTEN_PORT="${PASEO_PORT:-6767}"

DO_INSTALL=1    # 0 = --no-install
DO_SYSTEMD=1    # 0 = --no-systemd
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  ./install.sh                  # npm i -g if paseo is missing; sniff the login shell;
                                # write ~/.config/environment.d/60-paseo.conf;
                                # generate and enable paseo.service
  ./install.sh --no-install     # skip npm install (paseo must already be on PATH)
  ./install.sh --no-systemd     # no unit, no sniffing: only npm i -g + `paseo daemon start`
                                #   (detached; inherits this terminal; no boot autostart)
  ./install.sh --dry-run        # sniff and print the unit / commands; write nothing
  ./install.sh -h | --help
EOF
  exit "${1:-0}"
}

step() { printf '\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn] %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31m[error] %s\033[0m\n' "$*" >&2; exit 1; }

# command -v + readlink -f: resolve the real absolute path of a binary (nvm's
# bin entries are symlinks).
resolve_bin() {
  local p
  p="$(command -v "$1" 2>/dev/null || true)"
  if [[ -z "$p" ]]; then return 1; fi
  readlink -f "$p" 2>/dev/null || realpath "$p" 2>/dev/null || printf '%s\n' "$p"
}

# paseo may be installed under an nvm version that is not active: a system
# node shadows nvm on PATH, or the nvm default points elsewhere. The package
# is on disk but `command -v paseo` fails. Fall back to the newest nvm
# version that provides a paseo shim.
discover_paseo() {
  local found=""
  found="$(command -v paseo 2>/dev/null || true)"
  if [[ -n "$found" ]]; then
    printf '%s\n' "$found"
    return 0
  fi
  local versions_dir="${NVM_DIR:-$HOME/.nvm}/versions/node"
  [[ -d "$versions_dir" ]] || return 1
  local version candidate
  while IFS= read -r version; do
    candidate="$versions_dir/$version/bin/paseo"
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(ls -1 "$versions_dir" 2>/dev/null | sort -rV)
  return 1
}

# Non-interactive environments often lack npm on PATH (nvm); fall back to
# sourcing nvm when node/npm are missing.
ensure_nvm() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    return 0
  fi
  local nvm_sh="${NVM_DIR:-$HOME/.nvm}/nvm.sh"
  if [[ -s "$nvm_sh" ]]; then
    # shellcheck disable=SC1090
    . "$nvm_sh"
  fi
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1
}

# Read the PID from ~/.paseo/paseo.pid (written by the daemon; empty output when unset).
daemon_pid() {
  [[ -f "$PID_FILE" ]] || return 0
  python3 - "$PID_FILE" <<'PY' || true
import json, sys
try:
    pid = json.load(open(sys.argv[1])).get("pid")
    print(pid if isinstance(pid, int) and pid > 0 else "")
except Exception:
    pass
PY
}

port_open() {
  timeout 1 bash -c "exec 3<>/dev/tcp/$LISTEN_ADDR/$LISTEN_PORT" 2>/dev/null
}

wait_port_open() {  # $1 = max seconds to wait
  local i
  for ((i = 0; i < $1; i++)); do
    if port_open; then return 0; fi
    sleep 1
  done
  return 1
}

wait_port_closed() {  # $1 = max seconds to wait
  local i
  for ((i = 0; i < $1; i++)); do
    if ! port_open; then return 0; fi
    sleep 1
  done
  return 1
}

# The unit body is expanded at call time; the global PASEO_BIN must be set.
# PATH is not written into the unit: Environment= replaces the whole variable
# and does not expand $PATH. The login-shell environment is written to
# ~/.config/environment.d/60-paseo.conf by sync_login_env.py; after
# daemon-reload the user manager hands it to user services started afterwards.
# daemon-reload alone does NOT refresh variables the manager already holds
# (PATH is pinned when the user manager starts, long before this file exists),
# so systemd_install also pushes the probed PATH via set-environment.
# `paseo daemon run` keeps the daemon in the foreground (CLI >= 0.9.2; the old
# `--foreground` flag of `daemon start` was removed).
unit_body() {
  cat <<EOF
[Unit]
Description=Paseo daemon (user service, generated by deploy/paseo-daemon/install.sh)
After=default.target

[Service]
Type=simple
# Generated by install.sh — do not hand-edit ExecStart; re-run the installer.
# Login-shell environment: ~/.config/environment.d/60-paseo.conf
ExecStart=$PASEO_BIN daemon run --home $PASEO_HOME
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
}

# --- supervisor auto-refresh units -----------------------------------------
# The daemon is two processes: a long-lived supervisor and a worker. Updating
# the npm package on disk only restarts the worker; the supervisor keeps its
# original in-memory code until its launcher (paseo.service) replaces the
# whole process. The .path unit watches the installed @getpaseo npm scope
# directory; when an update rewrites it, the oneshot service restarts
# paseo.service via supervisor_refresh.py, which skips the restart while any
# agent is running or initializing (restarting kills the worker and its
# child agent processes).
resolve_pkg_scope() {
  local bin_dir pkg_dir
  bin_dir="$(dirname "$PASEO_BIN")"     # .../@getpaseo/cli/bin
  pkg_dir="$(dirname "$bin_dir")"       # .../@getpaseo/cli
  PKG_SCOPE_DIR="$(dirname "$pkg_dir")" # .../node_modules/@getpaseo
  [[ "$(basename "$pkg_dir")" == "cli" && "$(basename "$PKG_SCOPE_DIR")" == "@getpaseo" ]]
}

refresh_path_body() {
  cat <<EOF
[Unit]
Description=Watch the installed @getpaseo npm package for Paseo updates

[Path]
PathModified=$PKG_SCOPE_DIR
Unit=$REFRESH_SERVICE_NAME

[Install]
WantedBy=default.target
EOF
}

refresh_service_body() {
  cat <<EOF
[Unit]
Description=Restart $UNIT_NAME when the installed @getpaseo package is newer than the running supervisor

[Service]
Type=oneshot
# Above the quiescence wait budget in supervisor_refresh.py: the default 90s
# would kill the oneshot while it legitimately waits for the daemon's npm
# install (node-pty build) or its post-install worker restart.
TimeoutStartSec=1500
ExecStart=$PYTHON_BIN $REFRESH_SCRIPT --home $PASEO_HOME --watch-dir $PKG_SCOPE_DIR --paseo-bin $PASEO_BIN --service $UNIT_NAME
EOF
}

# Write $1 with content $2; sets UNIT_WROTE=1 when the file changed, 0 when
# identical, so a re-run never restarts a healthy daemon for no reason.
write_unit() {
  local path="$1" content="$2" existing=""
  UNIT_WROTE=0
  if [[ -f "$path" ]]; then
    existing="$(cat "$path")"
  fi
  if [[ "$existing" == "$content" ]]; then
    return 0
  fi
  printf '%s\n' "$content" >"$path"
  UNIT_WROTE=1
}

sync_login_env() {
  local -a args=()
  if [[ "$DRY_RUN" -eq 1 ]]; then
    args+=(--dry-run)
  fi
  python3 "$SCRIPT_DIR/sync_login_env.py" "${SYNC_EXTRA_ARGS[@]}" "${args[@]}"
}

# Bin directories of the toolchain that owns the resolved paseo install.
# The daemon's self-update runs `npm -g ls @getpaseo/cli` with its own PATH;
# it must resolve to the npm whose global prefix owns @getpaseo/cli. A bare
# login-shell probe can miss these dirs entirely or see a different node
# first (a system node in /usr/bin), which fails the check with
# "@getpaseo/cli is not installed with npm -g on this host".
compute_sync_extra_args() {
  SYNC_EXTRA_ARGS=()
  local entry
  entry="$(command -v paseo 2>/dev/null || true)"
  if [[ -n "$entry" ]]; then
    SYNC_EXTRA_ARGS+=(--ensure-path-dir "$(dirname "$entry")")
  fi
  entry="$(command -v node 2>/dev/null || true)"
  if [[ -n "$entry" ]]; then
    SYNC_EXTRA_ARGS+=(--ensure-path-dir "$(dirname "$entry")")
  fi
}

show_status() {
  "$PASEO_BIN" daemon status --no-color 2>&1 || true
  echo
  systemctl --user status "$UNIT_NAME" --no-pager 2>&1 | sed -n '1,8p' || true
}

install_cli() {
  step "Install @getpaseo/cli: npm install -g @getpaseo/cli"
  npm install -g @getpaseo/cli
  ok "installed: $(command -v paseo)"
}

start_detached() {
  local pid
  pid="$(daemon_pid)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    warn "daemon already running (PID $pid); skipping start"
  else
    step "paseo daemon start (detached)"
    "$PASEO_BIN" daemon start
  fi
  sleep 1
  show_status
  warn "detached mode has no boot autostart: re-run this script (without --no-systemd) after a reboot."
}

run_systemctl() {
  systemctl --user "$@" 2>&1 \
    || die "systemctl --user failed ($*): run this script from a real login session (a normal SSH/desktop terminal, not an environment without a user bus)."
}

# daemon-reload re-runs the environment generators but does not override
# variables the user manager already holds; PATH in practice is pinned when
# the user manager starts (at boot/login), long before 60-paseo.conf exists.
# Push the freshly probed PATH into the manager so this and later services
# actually get it. Non-fatal: without it services keep the stale manager PATH.
push_manager_path() {
  step "Refreshing the user manager PATH from the login shell"
  local probed
  if ! probed="$(python3 "$SCRIPT_DIR/sync_login_env.py" "${SYNC_EXTRA_ARGS[@]}" --emit-env PATH 2>/dev/null)"; then
    warn "login-shell PATH probe failed; leaving the user manager PATH untouched"
    return 0
  fi
  if [[ -z "$probed" ]]; then
    warn "login-shell PATH probe returned empty; leaving the user manager PATH untouched"
    return 0
  fi
  if systemctl --user set-environment "PATH=$probed" 2>/dev/null; then
    ok "user manager PATH refreshed"
  else
    warn "systemctl --user set-environment PATH failed; services may keep a stale PATH"
  fi
}

systemd_install() {
  step "Generate units in $UNIT_DIR"
  mkdir -p "$UNIT_DIR"

  write_unit "$UNIT_PATH" "$(unit_body)"
  local main_wrote=$UNIT_WROTE
  if [[ "$main_wrote" -eq 1 ]]; then
    ok "$UNIT_NAME written"
  else
    ok "$UNIT_NAME unchanged"
  fi

  local refresh_units=0
  if resolve_pkg_scope && [[ -f "$REFRESH_SCRIPT" ]]; then
    PYTHON_BIN="/usr/bin/python3"
    [[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3)"
    write_unit "$UNIT_DIR/$REFRESH_PATH_NAME" "$(refresh_path_body)"
    if [[ "$UNIT_WROTE" -eq 1 ]]; then ok "$REFRESH_PATH_NAME written"; else ok "$REFRESH_PATH_NAME unchanged"; fi
    write_unit "$UNIT_DIR/$REFRESH_SERVICE_NAME" "$(refresh_service_body)"
    if [[ "$UNIT_WROTE" -eq 1 ]]; then ok "$REFRESH_SERVICE_NAME written"; else ok "$REFRESH_SERVICE_NAME unchanged"; fi
    refresh_units=1
  else
    warn "cannot derive the @getpaseo package scope from $PASEO_BIN (or $REFRESH_SCRIPT missing); skipping $REFRESH_PATH_NAME"
  fi

  step "systemctl --user daemon-reload"
  run_systemctl daemon-reload
  push_manager_path

  if systemctl --user is-active --quiet "$UNIT_NAME" 2>/dev/null; then
    if [[ "$main_wrote" -eq 1 ]]; then
      step "paseo.service is active and the unit changed -> restart"
      run_systemctl restart "$UNIT_NAME"
    else
      ok "paseo.service is active and the unit is unchanged; leaving it running"
    fi
  else
    local pid
    pid="$(daemon_pid)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      warn "found an old unmanaged daemon (PID $pid); stopping it so it cannot hold $LISTEN_ADDR:$LISTEN_PORT"
      "$PASEO_BIN" daemon stop || true
      wait_port_closed 10 \
        || warn "old daemon may still be listening; if the new instance fails to start, see the tail of $LOG_FILE"
    fi
    step "systemctl --user enable --now $UNIT_NAME"
    run_systemctl enable --now "$UNIT_NAME"
  fi

  if [[ "$refresh_units" -eq 1 ]]; then
    step "enable --now $REFRESH_PATH_NAME (supervisor refresh watcher)"
    run_systemctl enable --now "$REFRESH_PATH_NAME"
  fi
}

enable_linger() {
  step "loginctl enable-linger \"$USER\" (start at boot even when not logged in)"
  if loginctl enable-linger "$USER" 2>/dev/null; then
    ok "linger: $(loginctl show-user "$USER" -p Linger 2>/dev/null | cut -d= -f2)"
  else
    warn "enable-linger failed; run this in a session with sudo: sudo loginctl enable-linger \"$USER\""
  fi
}

verify() {
  step "Waiting for the daemon to become ready ($LISTEN_ADDR:$LISTEN_PORT)"
  local ready=0
  if wait_port_open 30; then
    ready=1
  elif systemctl --user is-active --quiet "$UNIT_NAME" 2>/dev/null \
    && "$PASEO_BIN" daemon status --no-color 2>/dev/null | grep -qiE 'localDaemon:[[:space:]]*running'; then
    ready=1
  fi
  if [[ "$ready" -eq 0 ]]; then
    warn "port probe failed; diagnostics:"
    show_status || true
    tail -n 30 "$LOG_FILE" 2>/dev/null || true
    journalctl --user -u "$UNIT_NAME" -n 30 --no-pager 2>/dev/null || true
    die "daemon is not ready; see the logs above"
  fi
  ok "daemon is ready"
  show_status
}

print_cheatsheet() {
  cat <<EOF

Installed. Common commands:
  paseo daemon status                         # the daemon's own view
  systemctl --user status $UNIT_NAME          # systemd's view
  systemctl --user restart $UNIT_NAME         # restart manually
  systemctl --user start $REFRESH_SERVICE_NAME  # refresh the supervisor now (safe: skips busy agents)
  journalctl --user -u $UNIT_NAME -f          # systemd journal
  tail -f $LOG_FILE                            # daemon log
  # Login-shell snapshot: ~/.config/environment.d/60-paseo.conf
  # Re-run this script after changing ~/.bashrc / ~/.bash_profile, then restart paseo.service

Updates: $REFRESH_PATH_NAME watches the installed @getpaseo package and
restarts $UNIT_NAME after an update, unless an agent is running.

The GUI/SSH transport only connects to a daemon that is already running; it does
not install or start one. As long as the local daemon runs, remote connects work.
Relay/QR pairing is a separate thing: paseo daemon pair.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-install) DO_INSTALL=0; shift ;;
    --no-systemd) DO_SYSTEMD=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
done

# ---- dry-run: print only; write nothing, start nothing ----
if [[ "$DRY_RUN" -eq 1 ]]; then
  if [[ "$DO_SYSTEMD" -eq 1 ]]; then
    compute_sync_extra_args
    sync_login_env
  else
    echo "skipping login-shell sniff (--no-systemd inherits this terminal)"
  fi
  PASEO_ENTRY="$(discover_paseo 2>/dev/null || true)"
  if [[ -z "$PASEO_ENTRY" ]]; then
    echo "planned: npm install -g @getpaseo/cli"
    echo "(run --dry-run again once paseo is installed to preview the unit)"
    exit 0
  fi
  PASEO_BIN="$(resolve_bin paseo 2>/dev/null || readlink -f "$PASEO_ENTRY" 2>/dev/null || printf '%s\n' "$PASEO_ENTRY")"
  echo "paseo (real): $PASEO_BIN"
  echo "ensure path dirs: ${SYNC_EXTRA_ARGS[*]:-(none - paseo or node not on this shell PATH)}"
  if [[ "$DO_SYSTEMD" -eq 1 ]]; then
    echo "unit path : $UNIT_PATH"
    echo "---- unit ----"
    unit_body
    if resolve_pkg_scope && [[ -f "$REFRESH_SCRIPT" ]]; then
      PYTHON_BIN="/usr/bin/python3"
      [[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3)"
      echo "---- $REFRESH_PATH_NAME ----"
      refresh_path_body
      echo "---- $REFRESH_SERVICE_NAME ----"
      refresh_service_body
    else
      echo "(supervisor refresh units skipped: cannot derive the @getpaseo scope from $PASEO_BIN)"
    fi
    echo "---- planned commands ----"
    echo "systemctl --user daemon-reload"
    probed_path="$(python3 "$SCRIPT_DIR/sync_login_env.py" "${SYNC_EXTRA_ARGS[@]}" --emit-env PATH 2>/dev/null)" || probed_path=""
    if [[ -n "$probed_path" ]]; then
      echo "systemctl --user set-environment PATH=$probed_path"
    else
      echo "systemctl --user set-environment PATH=<probe failed; will be skipped at runtime>"
    fi
    echo "systemctl --user enable --now $UNIT_NAME"
    echo "systemctl --user enable --now $REFRESH_PATH_NAME"
    echo "loginctl enable-linger \"$USER\""
  else
    echo "planned: $PASEO_BIN daemon start && $PASEO_BIN daemon status"
  fi
  exit 0
fi

# ---- real flow ----
ensure_nvm || die "node/npm not on PATH (this script tried sourcing \$NVM_DIR/nvm.sh). First: source ~/.nvm/nvm.sh"

PASEO_ENTRY=""
if ! PASEO_ENTRY="$(discover_paseo)"; then
  if [[ "$DO_INSTALL" -eq 0 ]]; then
    die "--no-install given but paseo is not on PATH and not found under any nvm version"
  fi
  install_cli
  PASEO_ENTRY="$(discover_paseo)" || die "paseo still not found after npm install -g @getpaseo/cli"
fi
step "paseo: $PASEO_ENTRY"
# Make the discovered toolchain visible to the rest of the script: the env
# snapshot, the watcher --paseo-bin, and every status probe must use the
# same node/npm pairing that owns this install.
export PATH="$(dirname "$PASEO_ENTRY"):$PATH"
PASEO_BIN="$(resolve_bin paseo)" || die "cannot resolve the paseo executable"
compute_sync_extra_args

if [[ "$DO_SYSTEMD" -eq 1 ]]; then
  step "Sniffing the login shell; writing environment.d"
  sync_login_env
  systemd_install
  enable_linger
  verify
else
  start_detached
fi

print_cheatsheet
