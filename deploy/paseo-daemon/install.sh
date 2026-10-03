#!/usr/bin/env bash
# Paseo daemon one-shot deploy: install the CLI -> harden the persisted config
# (loopback-only listen + password by default, explicitly optional) -> systemd
# --user service
# (enabled at boot) -> verify. Also installs a supervisor-refresh watcher:
# a .path unit on the installed @getpaseo package + an oneshot that restarts
# paseo.service after an update (skipping while agents are busy), because an
# updated package alone never refreshes the running supervisor process.
#
# Hardening, in one paragraph: without a password every connection admitted by
# the daemon is the "owner" principal (see Paseo session-admission-auth), and
# 127.0.0.1 is host-wide, so on a multi-user machine every local user can
# control the daemon. This installer therefore always writes
# daemon.listen=127.0.0.1:<port> (a non-loopback persisted value is reset,
# never propagated; there is intentionally no way to deploy 0.0.0.0 here),
# sets a password by default (opt out interactively with "n" or unattended
# with PASEO_DEPLOY_NO_PASSWORD=1; rotate with PASEO_DEPLOY_PASSWORD=<new>),
# and always strips the hosted-web-app origin
# https://app.paseo.sh from daemon.cors.allowedOrigins (we do not extend trust
# to that deployment; native clients are unaffected). The plaintext is never
# persisted: the interactive path reads it from /dev/tty, the unattended path
# generates a random one and prints it exactly once (never to a file, unit,
# or env dump); only the bcrypt hash lands in ~/.paseo/config.json. Rotate
# later with `paseo daemon set-password`.
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
# Env: PASEO_HOME (default ~/.paseo), PASEO_PORT or --port (default 6767 or the
#      port already persisted in ~/.paseo/config.json),
#      PASEO_DEPLOY_PASSWORD (unattended: set/rotate the password; always wins)
#      or PASEO_DEPLOY_NO_PASSWORD=1 (unattended: remove the hash; mutually
#      exclusive with PASEO_DEPLOY_PASSWORD). Interactive runs otherwise
#      prompt on /dev/tty: default to setting a password, allow opting out.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_NAME="paseo.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"
REFRESH_SERVICE_NAME="paseo-supervisor-refresh.service"
REFRESH_PATH_NAME="paseo-supervisor-refresh.path"
REFRESH_SCRIPT="$SCRIPT_DIR/supervisor_refresh.py"
HARDEN_PY="$SCRIPT_DIR/harden_daemon_config.py"
PKG_SCOPE_DIR="" # resolved from PASEO_BIN by resolve_pkg_scope()
PASEO_HOME="${PASEO_HOME:-$HOME/.paseo}"
PID_FILE="$PASEO_HOME/paseo.pid"
LOG_FILE="$PASEO_HOME/daemon.log"
LISTEN_ADDR="127.0.0.1"          # hard policy: this deploy is loopback-only
LISTEN_PORT="6767"               # readiness probe target; reset by harden_daemon_config

DO_INSTALL=1    # 0 = --no-install
DO_SYSTEMD=1    # 0 = --no-systemd
DRY_RUN=0
PORT=""         # --port / PASEO_PORT; empty = keep the persisted port, else 6767
CONFIG_HARDENED=0 # 1 = config.json changed; force a daemon (re)start

usage() {
  cat <<'EOF'
Usage:
  ./install.sh                  # npm i -g if paseo is missing; harden the config
                                # (loopback listen + mandatory password); sniff the
                                # login shell; write ~/.config/environment.d/60-paseo.conf;
                                # generate and enable paseo.service
  ./install.sh --port 6800      # bind 127.0.0.1:6800 (loopback only; 0.0.0.0 is refused)
  ./install.sh --no-install     # skip npm install (paseo must already be on PATH)
  ./install.sh --no-systemd     # no unit, no sniffing: only npm i -g + hardened
                                # config + `paseo daemon start`
                                #   (detached; inherits this terminal; no boot autostart)
  ./install.sh --dry-run        # sniff and print the unit / commands; write nothing
  ./install.sh -h | --help

Password input, in priority order:
  1. PASEO_DEPLOY_PASSWORD env var (unattended: set/rotate; always wins) or
     PASEO_DEPLOY_NO_PASSWORD=1 (unattended: remove the hash — mutually
     exclusive with the password var)
  2. interactive prompt on /dev/tty:
       - no hash yet: asked whether to set one (Enter = set, "n" = no
         password; empty new-password input auto-generates)
       - hash exists: [k]eep (Enter) / [r]eset / [d]isable
  3. no tty: an existing hash is kept, and one is generated only when no
     hash is set at all
Passwords are recommended but optional; running without one means every
connection the daemon admits is the owner principal (see
session-admission-auth), and 127.0.0.1 is host-wide. The plaintext is never
written to disk; only its bcrypt hash is stored.

Port selection, in priority order:
  1. --port 6800 or PASEO_PORT=6800
  2. interactive prompt on /dev/tty (Enter keeps the persisted/default port)
  3. the port already persisted in config.json (else 6767)

A re-run that changes nothing (same port, password kept, CORS origin already
stripped) does not restart the daemon.
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
  local q_bin q_home
  q_bin="$(systemd_quote "$PASEO_BIN")" || die "paseo path is not encodable in a systemd unit: $PASEO_BIN"
  q_home="$(systemd_quote "$PASEO_HOME")" || die "PASEO_HOME is not encodable in a systemd unit: $PASEO_HOME"
  cat <<EOF
[Unit]
Description=Paseo daemon (user service, generated by deploy/paseo-daemon/install.sh)
After=default.target

[Service]
Type=simple
# Generated by install.sh — do not hand-edit ExecStart; re-run the installer.
# Login-shell environment: ~/.config/environment.d/60-paseo.conf
ExecStart=$q_bin daemon run --home $q_home
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

# [Path] settings take the value literally: unlike ExecStart lines, systemd
# does not strip quotes in PathModified (a leading " makes the path
# non-absolute and the unit fails to load with "bad unit file setting"), so
# the scope dir is written unquoted. Reject what that literal syntax cannot
# carry; % is a unit-file specifier even in [Path] values.
validate_path_setting() {
  local value="$1"
  [[ "$value" == /* ]] || return 1
  [[ "$value" != [[:space:]]* && "$value" != *[[:space:]] ]] || return 1
  case "$value" in
    *$'\n'*|*$'\r'*|*\\*|*\"*|*\'*|*%*) return 1 ;;
  esac
  return 0
}

refresh_path_body() {
  validate_path_setting "$PKG_SCOPE_DIR" \
    || die "package scope path is not encodable in a [Path] unit (must be absolute, no whitespace/quotes/backslash/percent): $PKG_SCOPE_DIR"
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
  local q_python q_script q_home q_scope q_bin
  q_python="$(systemd_quote "$PYTHON_BIN")" || die "python3 path is not encodable in a systemd unit: $PYTHON_BIN"
  q_script="$(systemd_quote "$REFRESH_SCRIPT")" || die "refresh script path is not encodable in a systemd unit: $REFRESH_SCRIPT"
  q_home="$(systemd_quote "$PASEO_HOME")" || die "PASEO_HOME is not encodable in a systemd unit: $PASEO_HOME"
  q_scope="$(systemd_quote "$PKG_SCOPE_DIR")" || die "package scope path is not encodable in a systemd unit: $PKG_SCOPE_DIR"
  q_bin="$(systemd_quote "$PASEO_BIN")" || die "paseo path is not encodable in a systemd unit: $PASEO_BIN"
  cat <<EOF
[Unit]
Description=Restart $UNIT_NAME when the installed @getpaseo package is newer than the running supervisor

[Service]
Type=oneshot
# Above the quiescence wait budget in supervisor_refresh.py: the default 90s
# would kill the oneshot while it legitimately waits for the daemon's npm
# install (node-pty build) or its post-install worker restart.
TimeoutStartSec=1500
ExecStart=$q_python $q_script --home $q_home --watch-dir $q_scope --paseo-bin $q_bin --service $UNIT_NAME
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

# Quote one argument for systemd unit syntax. CR/LF cannot be encoded on a
# single unit line and a trailing backslash would escape the closing quote,
# so such values are rejected instead of writing a malformed unit.
systemd_quote() {
  local value="$1"
  case "$value" in
    *$'\n'*|*$'\r'*|*\\) return 1 ;;
  esac
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"\n' "$value"
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

# --- config hardening: loopback listen + mandatory password ------------------
# Policy lives in two places: this script decides WHAT to enforce (loopback
# only, password always set, nothing persisted in plaintext), and
# harden_daemon_config.py does the JSON merge atomically while refusing
# non-loopback listen targets on its own — so even a careless caller cannot
# persist a 0.0.0.0 bind through it.

# Echoes the normalized port or dies. Pure (unit-tested via extraction).
validate_port_value() {
  local value="$1"
  [[ "$value" =~ ^[0-9]+$ ]] || die "port must be a positive integer, got: '$value'"
  (( value >= 1 && value <= 65535 )) || die "port out of range 1-65535: $value"
  printf '%s\n' "$value"
}

# Effective port: --port > PASEO_PORT > the port already persisted (so a
# re-run without flags keeps the previous choice) > 6767.
resolve_effective_port() {
  if [[ -n "$PORT" ]]; then
    validate_port_value "$PORT"
    return
  fi
  if [[ -n "${PASEO_PORT:-}" ]]; then
    validate_port_value "$PASEO_PORT"
    return
  fi
  local persisted=""
  persisted="$(python3 "$HARDEN_PY" --home "$PASEO_HOME" get-listen 2>/dev/null || true)"
  local persisted_port=""
  persisted_port="$(python3 - "$persisted" <<'PY' || true
import sys
value = sys.argv[1].strip()
tail = value.rsplit("]:", 1) if value.startswith("[") else value.rsplit(":", 1)
print(tail[1] if len(tail) == 2 and tail[1].isdigit() else "")
PY
)"
  if [[ -n "$persisted_port" ]]; then
    validate_port_value "$persisted_port"
  else
    printf '6767\n'
  fi
}

# Hash a password with the installed CLI's own bcryptjs (same cost as
# DAEMON_PASSWORD_BCRYPT_COST). Plaintext arrives on stdin and never touches
# argv or a file; the bcrypt hash goes to stdout. Resolution order: hoisted
# next to the @getpaseo scope, then the global npm root, then a bounded find.
hash_password() {
  local scope_parent="" candidates=() found="" node_bin=""
  if resolve_pkg_scope 2>/dev/null; then
    scope_parent="$(dirname "$PKG_SCOPE_DIR")"
    candidates+=("$scope_parent/bcryptjs")
  fi
  local npm_root=""
  npm_root="$(npm root -g 2>/dev/null || true)"
  [[ -n "$npm_root" ]] && candidates+=("$npm_root/bcryptjs")
  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate/package.json" ]]; then
      found="$candidate"
      break
    fi
  done
  if [[ -z "$found" && -n "$scope_parent" ]]; then
    found="$(find "$scope_parent" -maxdepth 4 -type d -name bcryptjs -print -quit 2>/dev/null || true)"
  fi
  [[ -n "$found" ]] || die "cannot locate bcryptjs next to the installed @getpaseo packages; set the password manually with 'paseo daemon set-password'"
  node_bin="$(dirname "$PASEO_BIN")/node"
  [[ -x "$node_bin" ]] || node_bin="$(command -v node 2>/dev/null || true)"
  [[ -n "$node_bin" ]] || die "node not found; needed to hash the daemon password"
  "$node_bin" -e 'const bcrypt = require(process.argv[1]);
let input = "";
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => process.stdout.write(bcrypt.hashSync(input.replace(/\s+$/, ""), 12)));' "$found"
}

# True only when /dev/tty can actually be opened — a plain -r/-w test is not
# enough: /dev/tty is a world-writable device node, so the test passes even
# for a process with no controlling terminal (cron, CI, agent shells), whose
# open then fails with ENXIO.
have_tty() { ( exec 9<>/dev/tty ) 2>/dev/null; }

# Reads a secret from /dev/tty without echo; returns nonzero when no tty is
# available so callers can fall back to generation. $1 = prompt.
read_secret() {
  local prompt="$1" value
  have_tty || return 1
  # shellcheck disable=SC2162 # -r is given; the space in IFS trim is intended
  IFS= read -r -s -p "$prompt" value </dev/tty || return 1
  printf '\n' >/dev/tty
  printf '%s' "$value"
}

# Pure decision helper for harden_daemon_config's password flow (unit-tested
# via extraction). $1 = a password hash is already persisted (0/1),
# $2 = PASEO_DEPLOY_PASSWORD is set (0/1), $3 = PASEO_DEPLOY_NO_PASSWORD=1
# (0/1), $4 = a /dev/tty is available (0/1). Echoes exactly one action:
#   env        — set/rotate to PASEO_DEPLOY_PASSWORD (explicit, always wins)
#   clear      — remove the hash (PASEO_DEPLOY_NO_PASSWORD=1)
#   ask        — interactive: keep / reset / disable when a hash exists
#   ask-fresh  — interactive: offer to set one (Enter) or none ("n")
#   prompt-new — interactive: prompt for a new password (chosen by ask*)
#   keep       — leave the existing hash untouched (unattended re-run)
#   generate   — no hash and no tty: mint a random one, printed once
# Setting wins over clearing; the contradiction is rejected before this runs.
decide_password_action() {
  local existing="$1" has_env="$2" has_clear="$3" has_tty_flag="$4"
  if [[ "$has_env" -eq 1 ]]; then
    printf 'env\n'; return
  fi
  if [[ "$has_clear" -eq 1 ]]; then
    printf 'clear\n'; return
  fi
  if [[ "$has_tty_flag" -eq 1 ]]; then
    if [[ "$existing" -eq 1 ]]; then
      printf 'ask\n'
    else
      printf 'ask-fresh\n'
    fi
    return
  fi
  if [[ "$existing" -eq 1 ]]; then
    printf 'keep\n'
  else
    printf 'generate\n'
  fi
}

warn_passwordless() {
  warn "without a password, every connection the daemon admits is the owner"
  warn "principal (Paseo session-admission-auth), and 127.0.0.1 is host-wide,"
  warn "so every local user (or anyone forwarding a port) can control it."
}

# Offer the current effective port on /dev/tty when no explicit port was
# requested; Enter keeps it. Any accepted answer lands in PORT, so the
# regular --port > PASEO_PORT > persisted chain picks it up.
prompt_port_override() {  # $1 = current effective port
  local current="$1" answer=""
  [[ -z "$PORT" && -z "${PASEO_PORT:-}" ]] || return 0
  have_tty || return 0
  printf 'The daemon binds loopback only (127.0.0.1); LAN/mobile access is relay-only.\n' >/dev/tty
  read -r -p "Listen port [$current] (Enter = keep): " answer </dev/tty || return 0
  printf '\n' >/dev/tty
  answer="${answer// /}"
  [[ -n "$answer" ]] || return 0
  PORT="$(validate_port_value "$answer")"  # dies on invalid input
  ok "listen port: $current -> $PORT"
}

print_generated_password() {
  local password="$1" interactive="$2"
  # Never let xtrace capture the plaintext even when the script runs under
  # `bash -x` — `set +x` inside the script wins for everything after it.
  case "$-" in
    *x*) set +x ;;
  esac
  if [[ "$interactive" -eq 1 ]]; then
    {
      printf '\n\033[1;33m==============================================================\n'
      printf 'AUTO-GENERATED DAEMON PASSWORD — shown ONCE, never saved anywhere.\n\n'
      printf '    %s\n\n' "$password"
      printf 'Copy it into your password manager, then press Enter to hide it.\n'
      printf 'If lost: re-run this script or `paseo daemon set-password`.\n'
      printf '==============================================================\033[0m\n'
    } >/dev/tty
    IFS= read -r -s -p "Copied? Press Enter to clear the screen." _ </dev/tty || true
    printf '\n' >/dev/tty
    clear >/dev/tty 2>&1 || true
  else
    # Unattended deploy (agent/CI): stdout is the only channel the operator
    # sees, so print plainly and say so.
    printf '\nAUTO-GENERATED DAEMON PASSWORD (printed once; not saved anywhere):\n\n    %s\n\nStore it now; this is the only copy. Rotate with `paseo daemon set-password`.\n' "$password"
  fi
}

# Always runs. Writes daemon.listen=127.0.0.1:<port> and manages
# daemon.auth.password (bcrypt) in config.json: set by default, but the
# operator can explicitly run without one (interactive "n" when fresh, "d"
# when a hash exists, or PASEO_DEPLOY_NO_PASSWORD=1 unattended). CONFIG_HARDENED
# is set only when something actually changed, so an idle re-run never restarts
# the daemon (restarting kills running agents). Plaintext password handling:
# PASEO_DEPLOY_PASSWORD > PASEO_DEPLOY_NO_PASSWORD > /dev/tty prompt
# (set / keep-reset-disable) > keep an existing hash (unattended) > generation.
harden_daemon_config() {
  step "Hardening daemon config: loopback listen + password"
  local hardened_changed=0

  local persisted_port
  persisted_port="$(resolve_effective_port)"
  prompt_port_override "$persisted_port"
  EFFECTIVE_PORT="$(resolve_effective_port)"
  LISTEN_PORT="$EFFECTIVE_PORT"
  local target_listen="$LISTEN_ADDR:$EFFECTIVE_PORT"

  local summary previous previous_loopback
  summary="$(python3 "$HARDEN_PY" --home "$PASEO_HOME" set-listen "$target_listen")" \
    || die "failed to write listen target $target_listen (refusing non-loopback is intentional)"
  previous="$(python3 - "$summary" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["previous"] or "")
PY
)"
  previous_loopback="$(python3 - "$summary" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["previous_loopback"])
PY
)"
  if [[ "$previous" != "$target_listen" ]]; then
    hardened_changed=1
  fi
  if [[ "$previous_loopback" == "False" ]]; then
    warn "previous bind was non-loopback ($previous); reset to $target_listen."
    warn "Direct mobile/LAN access is not supported by this deploy — use relay pairing."
  elif [[ -n "$previous" && "$previous" != "$target_listen" ]]; then
    ok "listen: $previous -> $target_listen"
  elif [[ -z "$previous" ]]; then
    ok "listen: $target_listen (written)"
  else
    ok "listen: $target_listen (unchanged)"
  fi

  local existing_password=0
  if [[ "$(python3 "$HARDEN_PY" --home "$PASEO_HOME" has-password 2>/dev/null || true)" == "True" ]]; then
    existing_password=1
  fi

  local password="" generated=0 interactive=0
  local set_env_flag=0 clear_env_flag=0 tty_flag=0
  [[ -n "${PASEO_DEPLOY_PASSWORD:-}" ]] && set_env_flag=1
  [[ "${PASEO_DEPLOY_NO_PASSWORD:-}" == "1" ]] && clear_env_flag=1
  have_tty && tty_flag=1
  if [[ "$set_env_flag" -eq 1 && "$clear_env_flag" -eq 1 ]]; then
    die "PASEO_DEPLOY_PASSWORD and PASEO_DEPLOY_NO_PASSWORD=1 contradict each other — pick one"
  fi

  local action
  action="$(decide_password_action "$existing_password" "$set_env_flag" "$clear_env_flag" "$tty_flag")"

  case "$action" in
    ask-fresh)
      interactive=1
      printf 'A daemon password is recommended; without one every connection\n' >/dev/tty
      printf 'admits as the owner principal (see the warning after opting out).\n' >/dev/tty
      local answer=""
      read -r -p "Set a daemon password? [Y/n] " answer </dev/tty || answer=""
      printf '\n' >/dev/tty
      case "$answer" in
        n|N) action="none" ;;
        *) action="prompt-new" ;;
      esac
      ;;
    ask)
      interactive=1
      printf '\033[1mA daemon password is already set.\033[0m Every client saved\n' >/dev/tty
      printf 'with the old one stops working when you rotate or remove it.\n' >/dev/tty
      local answer=""
      read -r -p "Password: [k]eep (Enter) / [r]eset / [d]isable: " answer </dev/tty || answer=""
      printf '\n' >/dev/tty
      case "$answer" in
        r|R) action="prompt-new" ;;
        d|D) action="clear" ;;
        *) action="keep" ;;
      esac
      ;;
  esac

  case "$action" in
    env)
      password="$PASEO_DEPLOY_PASSWORD"
      ok "password: taken from PASEO_DEPLOY_PASSWORD"
      ;;
    keep)
      ok "password: keeping existing hash (rotate with 'paseo daemon set-password' or re-run with PASEO_DEPLOY_PASSWORD=<new>)"
      ;;
    none)
      ok "password: none will be stored"
      warn_passwordless
      ;;
    clear)
      python3 "$HARDEN_PY" --home "$PASEO_HOME" clear-password \
        || die "failed to clear the password hash"
      hardened_changed=1
      ok "password: hash removed — the daemon no longer asks for one"
      warn_passwordless
      ;;
    prompt-new)
      interactive=1
      local first second
      first="$(read_secret "Daemon password [empty = auto-generate]")" || first=""
      if [[ -n "$first" ]]; then
        second="$(read_secret "Confirm password")" || die "could not read password confirmation"
        [[ "$first" == "$second" ]] || die "passwords do not match"
        password="$first"
      fi
      unset first second
      ;;
  esac

  if [[ "$action" == "prompt-new" || "$action" == "generate" ]] && [[ -z "$password" ]]; then
    password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    generated=1
  fi

  if [[ -n "$password" ]]; then
    local hash
    hash="$(printf '%s' "$password" | hash_password)" \
      || die "failed to hash the daemon password"
    python3 "$HARDEN_PY" --home "$PASEO_HOME" set-password-hash "$hash" \
      || die "failed to persist the password hash"
    hardened_changed=1
    if [[ "$generated" -eq 1 ]]; then
      # Shown exactly once here, then dropped: nothing on disk, in any unit, or
      # in the environment snapshot ever carries the plaintext.
      print_generated_password "$password" "$interactive"
    else
      ok "password: stored as bcrypt hash in $PASEO_HOME/config.json"
      warn "restart is required — applied when the service starts below."
    fi
    unset password hash
  fi

  # The hosted web app origin is Paseo's shipped default. We do not extend
  # trust to that deployment: a page served from it must not be able to
  # drive this daemon from any browser that can reach the machine. Native
  # clients (CLI, desktop, mobile, relay) send no Origin header and are
  # unaffected. Stripped on every run; re-adding it by hand lasts only until
  # the next run.
  local cors_summary cors_removed
  cors_summary="$(python3 "$HARDEN_PY" --home "$PASEO_HOME" remove-cors-origin "https://app.paseo.sh")" \
    || die "failed to strip the hosted-web-app origin from cors.allowedOrigins"
  cors_removed="$(python3 - "$cors_summary" <<'PY'
import json, sys
print(json.loads(sys.argv[1])["removed"])
PY
)"
  if [[ "$cors_removed" == "True" ]]; then
    ok "cors: removed https://app.paseo.sh (hosted web app can no longer reach this daemon)"
    hardened_changed=1
  else
    ok "cors: https://app.paseo.sh not present (unchanged)"
  fi

  CONFIG_HARDENED="$hardened_changed"
  if [[ "$hardened_changed" -eq 0 ]]; then
    ok "config unchanged — the running daemon keeps its current config (no restart)"
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
    if [[ "${CONFIG_HARDENED:-0}" -eq 1 ]]; then
      step "config changed -> restarting the detached daemon (PID $pid)"
      "$PASEO_BIN" daemon stop || true
      wait_port_closed 10 \
        || warn "old daemon may still be listening; if the new instance fails to start, see the tail of $LOG_FILE"
      step "paseo daemon start (detached)"
      "$PASEO_BIN" daemon start
    else
      warn "daemon already running (PID $pid); skipping start"
    fi
  else
    step "paseo daemon start (detached)"
    "$PASEO_BIN" daemon start
  fi
  sleep 1
  show_status
  warn "detached mode has no boot autostart: re-run this script (without --no-systemd) after a reboot."
}

run_systemctl() {
  local out
  if out="$(systemctl --user "$@" 2>&1)"; then
    [[ -n "$out" ]] && printf '%s\n' "$out"
    return 0
  fi
  local rc=$?
  [[ -n "$out" ]] && printf '%s\n' "$out" >&2
  if grep -qiE 'failed to connect to bus|no such file or directory.*systemd|user.*bus' <<<"$out"; then
    die "systemctl --user failed ($*): run this script from a real login session (a normal SSH/desktop terminal, not an environment without a user bus)."
  fi
  die "systemctl --user failed ($*): rc=$rc — see the output above."
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
    warn "cannot derive the @getpaseo package scope from $PASEO_BIN (or $REFRESH_SCRIPT missing); retiring any previously installed refresh watcher"
    retire_refresh_units
  fi

  step "systemctl --user daemon-reload"
  run_systemctl daemon-reload
  push_manager_path

  if systemctl --user is-active --quiet "$UNIT_NAME" 2>/dev/null; then
    if [[ "$main_wrote" -eq 1 ]]; then
      step "paseo.service is active and the unit changed -> restart"
      run_systemctl restart "$UNIT_NAME"
    elif [[ "${CONFIG_HARDENED:-0}" -eq 1 ]]; then
      step "unit unchanged but the hardened config needs a reload -> restart"
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
    # PathModified only reports changes after the watcher exists; run the
    # guarded check once so an update that landed beforehand is still
    # refreshed (the script skips while agents are busy).
    step "Run the guarded refresh check once (catches updates that predate the watcher)"
    systemctl --user start "$REFRESH_SERVICE_NAME" \
      || warn "initial refresh check failed; run 'systemctl --user start $REFRESH_SERVICE_NAME' later"
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

Security posture (enforced by this installer):
  - Binds $LISTEN_ADDR:$LISTEN_PORT only. The listen address lives in
    $PASEO_HOME/config.json (daemon.listen); a non-loopback value is reset
    on every run. There is no supported way to deploy 0.0.0.0 here.
  - A password is set (bcrypt hash under daemon.auth.password). Local CLI and
    desktop clients authenticate automatically via $PASEO_HOME/local-credential;
    everyone else — other OS users, mobile apps — must provide it. Rotate with:
      paseo daemon set-password && systemctl --user restart $UNIT_NAME
  - https://app.paseo.sh is stripped from daemon.cors.allowedOrigins on every
    run: the hosted web app is not a trusted client of this deployment.
    Native clients (CLI/desktop/mobile/relay) send no Origin header and are
    unaffected. To use the hosted web UI anyway, re-add the origin by hand
    (it will be stripped again on the next run of this installer).
  - If the password was auto-generated, it exists only where you copied it;
    the installer kept no copy. Lost it = run set-password.
  - Relay pairing (paseo daemon pair) for mobile is still available and is
    the supported remote path; keep the pairing link private (it grants access
    like a password; current daemon builds still admit credential-less relay
    clients during a compat window).

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
    --port)
      [[ $# -ge 2 ]] || die "--port needs a value"
      PORT="$(validate_port_value "$2")"
      shift 2 ;;
    -h|--help) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 1 ;;
  esac
done

# Disable and drop a refresh watcher from an earlier installation. Without
# this, a stale watcher would keep watching an old package path with old
# script arguments while the new installation has no watcher at all.
retire_refresh_units() {
  systemctl --user stop "$REFRESH_PATH_NAME" 2>/dev/null || true
  systemctl --user disable "$REFRESH_PATH_NAME" 2>/dev/null || true
  rm -f "$UNIT_DIR/$REFRESH_PATH_NAME" "$UNIT_DIR/$REFRESH_SERVICE_NAME"
}

# ---- dry-run: print only; write nothing, start nothing ----
if [[ "$DRY_RUN" -eq 1 ]]; then
  if [[ "$DO_SYSTEMD" -eq 1 ]]; then
    compute_sync_extra_args
    sync_login_env
  else
    echo "skipping login-shell sniff (--no-systemd inherits this terminal)"
  fi
  EFFECTIVE_PORT="$(resolve_effective_port)"
  echo "planned listen : $LISTEN_ADDR:$EFFECTIVE_PORT (loopback only; non-loopback persisted values are reset)"
  if [[ -n "${PASEO_DEPLOY_PASSWORD:-}" ]]; then
    echo "planned password: taken from PASEO_DEPLOY_PASSWORD"
  elif have_tty; then
    echo "planned password: interactive prompt (empty input = auto-generate, printed once)"
  else
    echo "planned password: auto-generate random and print once (no tty for prompting)"
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
    echo "systemctl --user start $REFRESH_SERVICE_NAME"
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

harden_daemon_config

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
