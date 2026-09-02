#!/usr/bin/env bash
# deploy/proxy: render a sing-box server config for a private daed node.
#
# By default this script only GENERATES files/links and prints them; it does
# not touch the local machine or the remote server. Use `--install` to install
# sing-box + systemd on a remote host over SSH. nginx is never modified: the
# script always prints the nginx snippet for you to apply manually.
#
# Usage:
#   ./scripts/deploy.sh                 # generate + print (no remote change)
#   ./scripts/deploy.sh --install \
#       --host <ssh-alias> --ip <server-public-ip> \
#       [--sni <domain>] [--cert-dir <remote-cert-dir>]
#
# Common options:
#   --host HOST          SSH alias/hostname for --install (env SSH_HOST)
#   --ip IP              Server public IP used in import links (env REMOTE_IP)
#   --sni DOMAIN         Optional TLS SNI/domain for links and nginx (env SNI_DOMAIN)
#   --cert-dir DIR       Remote dir with fullchain.pem + privkey.pem for
#                        Hysteria2 TLS. When omitted, a self-signed cert is
#                        generated on the remote and links use insecure=1.
#   --hysteria-port N    UDP port for Hysteria2 (default 443)
#   --vless-port N       TCP port sing-box listens on 127.0.0.1 (default 8443)
#   --tls-port N         Public TCP TLS port for the nginx/vless link (default 443)
#   --version V          sing-box version to install (default 1.14.0)
#   --install            Upload config + service and install sing-box on remote
#   --dry-run            Alias for default (generate + print only)
#
# Everything above can also be set via environment variables:
#   SSH_HOST, REMOTE_IP, SNI_DOMAIN, CERT_DIR, HYSTERIA_PORT, VLESS_PORT,
#   TLS_PORT, SING_BOX_VERSION, SSH_ARGS, BIN_DIR, CONFIG_DIR, TLS_DIR,
#   MASQUERADE_URL, CERTBOT_HOOK_DIR

set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_DIR="${DEPLOY_DIR}/sing-box"
SCRIPT_DIR="${DEPLOY_DIR}/scripts"
NGINX_DIR="${DEPLOY_DIR}/nginx"

SSH_HOST="${SSH_HOST:-}"
REMOTE_IP="${REMOTE_IP:-}"
SNI_DOMAIN="${SNI_DOMAIN:-}"
CERT_DIR="${CERT_DIR:-}"
SING_BOX_VERSION="${SING_BOX_VERSION:-1.14.0}"
HYSTERIA_PORT="${HYSTERIA_PORT:-443}"
VLESS_PORT="${VLESS_PORT:-8443}"
TLS_PORT="${TLS_PORT:-443}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
CONFIG_DIR="${CONFIG_DIR:-/etc/sing-box}"
TLS_DIR="${TLS_DIR:-${CONFIG_DIR}/tls}"
MASQUERADE_URL="${MASQUERADE_URL:-https://www.microsoft.com}"
CERTBOT_HOOK_DIR="${CERTBOT_HOOK_DIR:-}"

INSTALL=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install) INSTALL=1 ;;
        --dry-run) INSTALL=0 ;;
        --host) SSH_HOST="${2:-}"; shift 2 ;;
        --host=*) SSH_HOST="${1#*=}"; shift 1 ;;
        --ip) REMOTE_IP="${2:-}"; shift 2 ;;
        --ip=*) REMOTE_IP="${1#*=}"; shift 1 ;;
        --sni) SNI_DOMAIN="${2:-}"; shift 2 ;;
        --sni=*) SNI_DOMAIN="${1#*=}"; shift 1 ;;
        --cert-dir) CERT_DIR="${2:-}"; shift 2 ;;
        --cert-dir=*) CERT_DIR="${1#*=}"; shift 1 ;;
        --hysteria-port) HYSTERIA_PORT="${2:-}"; shift 2 ;;
        --hysteria-port=*) HYSTERIA_PORT="${1#*=}"; shift 1 ;;
        --vless-port) VLESS_PORT="${2:-}"; shift 2 ;;
        --vless-port=*) VLESS_PORT="${1#*=}"; shift 1 ;;
        --tls-port) TLS_PORT="${2:-}"; shift 2 ;;
        --tls-port=*) TLS_PORT="${1#*=}"; shift 1 ;;
        --version) SING_BOX_VERSION="${2:-}"; shift 2 ;;
        --version=*) SING_BOX_VERSION="${1#*=}"; shift 1 ;;
        --help|-h)
            sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "unknown option: $1" >&2
            sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
            exit 1
            ;;
    esac
done

# ── secrets ────────────────────────────────────────────────────────────────
VLESS_UUID="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')"
HY2_PASSWORD="$(openssl rand -hex 16 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(16))')"
WS_PATH="/vless-$(openssl rand -hex 8 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(8))')"

# ── Hysteria2 TLS material decision ────────────────────────────────────────
GEN_SELF_SIGNED=0
if [[ -n "${CERT_DIR}" ]]; then
    HY2_CERT_PATH="${CERT_DIR}/fullchain.pem"
    HY2_KEY_PATH="${CERT_DIR}/privkey.pem"
else
    HY2_CERT_PATH="${TLS_DIR}/server.crt"
    HY2_KEY_PATH="${TLS_DIR}/server.key"
    GEN_SELF_SIGNED=1
fi

# ── render files ───────────────────────────────────────────────────────────
TMPDIR="$(mktemp -d)"
trap 'rm -rf "${TMPDIR}"' EXIT

render() {
    local src="$1" dst="$2"
    HY2_PASSWORD="${HY2_PASSWORD}" \
    VLESS_UUID="${VLESS_UUID}" \
    WS_PATH="${WS_PATH}" \
    HYSTERIA_PORT="${HYSTERIA_PORT}" \
    VLESS_PORT="${VLESS_PORT}" \
    HY2_CERT_PATH="${HY2_CERT_PATH}" \
    HY2_KEY_PATH="${HY2_KEY_PATH}" \
    MASQUERADE_URL="${MASQUERADE_URL}" \
    python3 -c '
import os, sys
src, dst = sys.argv[1], sys.argv[2]
with open(src, encoding="utf-8") as f:
    text = f.read()
subs = {
    "__HY2_PASSWORD__": os.environ["HY2_PASSWORD"],
    "__VLESS_UUID__": os.environ["VLESS_UUID"],
    "__WS_PATH__": os.environ["WS_PATH"],
    "__HYSTERIA_PORT__": os.environ["HYSTERIA_PORT"],
    "__VLESS_PORT__": os.environ["VLESS_PORT"],
    "__HY2_CERT_PATH__": os.environ["HY2_CERT_PATH"],
    "__HY2_KEY_PATH__": os.environ["HY2_KEY_PATH"],
    "__MASQUERADE_URL__": os.environ["MASQUERADE_URL"],
}
for k, v in subs.items():
    text = text.replace(k, v)
with open(dst, "w", encoding="utf-8") as f:
    f.write(text)
' "${src}" "${dst}"
}

render "${TEMPLATE_DIR}/config.json.template" "${TMPDIR}/config.json"
render "${NGINX_DIR}/proxy-location.conf.template" "${TMPDIR}/proxy-location.conf"
cp "${TEMPLATE_DIR}/sing-box.service" "${TMPDIR}/sing-box.service"

# ── import links ───────────────────────────────────────────────────────────
ADDR="${REMOTE_IP:-__SERVER_IP__}"
HOST_VALUE="${SNI_DOMAIN:-${ADDR}}"
WS_PATH_ENCODED="%2F${WS_PATH#/}"

HY2_QUERY=""
if [[ -n "${SNI_DOMAIN}" ]]; then
    HY2_QUERY="?sni=${SNI_DOMAIN}"
    if [[ "${GEN_SELF_SIGNED}" == "1" ]]; then
        HY2_QUERY="${HY2_QUERY}&insecure=1"
    fi
else
    if [[ "${GEN_SELF_SIGNED}" == "1" ]]; then
        HY2_QUERY="?insecure=1"
    fi
fi
HY2_LINK="hysteria2://${HY2_PASSWORD}@${ADDR}:${HYSTERIA_PORT}/${HY2_QUERY}#proxy-hysteria2"

VLESS_QUERY="encryption=none&security=tls&type=ws&host=${HOST_VALUE}&path=${WS_PATH_ENCODED}"
if [[ -n "${SNI_DOMAIN}" ]]; then
    VLESS_QUERY="${VLESS_QUERY}&sni=${SNI_DOMAIN}"
else
    VLESS_QUERY="${VLESS_QUERY}&allowInsecure=1"
fi
VLESS_LINK="vless://${VLESS_UUID}@${ADDR}:${TLS_PORT}?${VLESS_QUERY}#proxy-vless"

# ── output ─────────────────────────────────────────────────────────────────
echo
echo "=== rendered sing-box config (${TMPDIR}/config.json) ==="
cat "${TMPDIR}/config.json"
echo
echo "=== nginx snippet — add it to YOUR TLS server block, then reload nginx ==="
cat "${TMPDIR}/proxy-location.conf"
echo
echo "=== import links (fill __SERVER_IP__/host/sni if still placeholders) ==="
echo "${HY2_LINK}"
echo "${VLESS_LINK}"
echo

if [[ "${GEN_SELF_SIGNED}" == "1" ]]; then
    echo "NOTE: no --cert-dir provided; the Hysteria2 node uses a self-signed cert and"
    echo "      the link contains insecure=1. If your daed/dae sets allow_insecure=false,"
    echo "      either provide --cert-dir with a valid cert or allow insecure in daed."
    echo
fi

if [[ "${INSTALL}" != "1" ]]; then
    echo "Dry-run only. To install sing-box on the remote host over SSH, run:"
    echo "  ${BASH_SOURCE[0]} --install --host <ssh-alias> --ip <server-public-ip> \\"
    echo "      [--sni <domain>] [--cert-dir <remote-cert-dir>]"
    echo
    exit 0
fi

# ── remote install (sing-box only; nginx is never modified) ────────────────
if [[ -z "${SSH_HOST}" ]]; then
    echo "error: --install requires --host <ssh-alias> (or SSH_HOST env)" >&2
    exit 1
fi

SSH_ARGS=(${SSH_ARGS:--o BatchMode=yes -o ConnectTimeout=10})
ssh_run() {
    ssh "${SSH_ARGS[@]}" "${SSH_HOST}" "$@"
}

echo "[deploy/proxy] checking ssh ${SSH_HOST} ..."
ssh_run 'echo ok' >/dev/null

if [[ -z "${REMOTE_IP}" ]]; then
    REMOTE_IP="$(ssh_run 'curl -sS -m 10 -4 ifconfig.me')"
    if [[ -z "${REMOTE_IP}" ]]; then
        echo "[deploy/proxy] unable to detect remote public IP; pass --ip" >&2
        exit 1
    fi
fi

if [[ -n "${CERT_DIR}" ]]; then
    if ! ssh_run "test -f '${HY2_CERT_PATH}' && test -f '${HY2_KEY_PATH}'"; then
        echo "[deploy/proxy] cert files not found on remote: ${HY2_CERT_PATH} ${HY2_KEY_PATH}" >&2
        echo "[deploy/proxy] re-run without --cert-dir to generate a self-signed cert, or fix --cert-dir" >&2
        exit 1
    fi
fi

echo "[deploy/proxy] uploading files"
ssh_run 'rm -rf /tmp/sing-box-deploy && mkdir -p /tmp/sing-box-deploy' >/dev/null
for file in config.json sing-box.service; do
    ssh_run "cat > /tmp/sing-box-deploy/${file}" < "${TMPDIR}/${file}"
done

echo "[deploy/proxy] running remote installer (sing-box only)"
ssh_run "SING_BOX_VERSION=${SING_BOX_VERSION} BIN_DIR=${BIN_DIR} CONFIG_DIR=${CONFIG_DIR} TLS_DIR=${TLS_DIR} HY2_CERT_PATH=${HY2_CERT_PATH} HY2_KEY_PATH=${HY2_KEY_PATH} GEN_SELF_SIGNED=${GEN_SELF_SIGNED} CERTBOT_HOOK_DIR=${CERTBOT_HOOK_DIR} bash -s" \
    < "${SCRIPT_DIR}/install.sh"

echo
echo "Done. sing-box is installed. Apply the nginx snippet printed above manually:"
echo "  - insert it into your TLS server block"
echo "  - run: nginx -t && systemctl reload nginx   # or your nginx service name"
echo
echo "Then import the two links printed above into daed."
