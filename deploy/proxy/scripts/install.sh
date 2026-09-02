#!/usr/bin/env bash
# Remote installer for deploy/proxy (run as root on the target host).
# Deploys sing-box + systemd only. It never touches nginx or any other service.
#
# Expected to be executed by deploy/proxy/scripts/deploy.sh with files already
# uploaded to /tmp/sing-box-deploy/{config.json,sing-box.service}.
#
# Environment variables:
#   SING_BOX_VERSION   e.g. 1.14.0
#   BIN_DIR            directory for the sing-box binary (default /usr/local/bin)
#   CONFIG_DIR         sing-box config directory (default /etc/sing-box)
#   TLS_DIR            directory for self-signed Hysteria2 TLS material
#   HY2_CERT_PATH      fullchain/cert path used by config.json
#   HY2_KEY_PATH       private key path used by config.json
#   GEN_SELF_SIGNED    1 = generate a self-signed cert when files are missing
#   CERTBOT_HOOK_DIR   optional certbot deploy-hook directory (skipped when empty)

set -euo pipefail

SING_BOX_VERSION="${SING_BOX_VERSION:-1.14.0}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
CONFIG_DIR="${CONFIG_DIR:-/etc/sing-box}"
TLS_DIR="${TLS_DIR:-${CONFIG_DIR}/tls}"
HY2_CERT_PATH="${HY2_CERT_PATH:-${TLS_DIR}/server.crt}"
HY2_KEY_PATH="${HY2_KEY_PATH:-${TLS_DIR}/server.key}"
GEN_SELF_SIGNED="${GEN_SELF_SIGNED:-1}"
CERTBOT_HOOK_DIR="${CERTBOT_HOOK_DIR:-}"
DEPLOY_DIR="/tmp/sing-box-deploy"

if [[ $EUID -ne 0 ]]; then
    echo "[deploy/proxy] must run as root on the remote host" >&2
    exit 1
fi

echo "[deploy/proxy] installing sing-box v${SING_BOX_VERSION}"

# ── arch mapping ──────────────────────────────────────────────────────────
case "$(uname -m)" in
    x86_64) ARCH="amd64" ;;
    aarch64) ARCH="arm64" ;;
    *) echo "[deploy/proxy] unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac

# ── install sing-box binary ───────────────────────────────────────────────
if [[ ! -x "${BIN_DIR}/sing-box" ]] || ! "${BIN_DIR}/sing-box" version 2>/dev/null | grep -q " ${SING_BOX_VERSION}$"; then
    TARBALL="/tmp/sing-box-${SING_BOX_VERSION}-linux-${ARCH}.tar.gz"
    RELEASE_PATH="SagerNet/sing-box/releases/download/v${SING_BOX_VERSION}/sing-box-${SING_BOX_VERSION}-linux-${ARCH}.tar.gz"
    if [[ ! -f "${TARBALL}" ]]; then
        download_ok=0
        for base in "https://github.com/" "https://ghfast.top/" "https://gh-proxy.com/"; do
            url="${base}${RELEASE_PATH}"
            echo "[deploy/proxy] downloading ${url}"
            if curl -fL --retry 2 --connect-timeout 15 --speed-time 20 --speed-limit 1024 \
                -o "${TARBALL}" "${url}"; then
                download_ok=1
                break
            fi
            rm -f "${TARBALL}"
        done
        if [[ "${download_ok}" != "1" ]]; then
            echo "[deploy/proxy] failed to download sing-box ${SING_BOX_VERSION}" >&2
            exit 1
        fi
    fi
    EXTRACT_DIR="/tmp/sing-box-${SING_BOX_VERSION}-linux-${ARCH}"
    rm -rf "${EXTRACT_DIR}"
    mkdir -p "${EXTRACT_DIR}"
    tar xzf "${TARBALL}" -C "${EXTRACT_DIR}" --strip-components=1
    install -Dm755 "${EXTRACT_DIR}/sing-box" "${BIN_DIR}/sing-box"
    echo "[deploy/proxy] sing-box installed: $("${BIN_DIR}/sing-box" version | head -1)"
else
    echo "[deploy/proxy] sing-box already at target version"
fi

# ── Hysteria2 TLS material ────────────────────────────────────────────────
if [[ "${GEN_SELF_SIGNED}" == "1" ]]; then
    if [[ ! -f "${HY2_CERT_PATH}" || ! -f "${HY2_KEY_PATH}" ]]; then
        echo "[deploy/proxy] generating self-signed certificate: ${HY2_CERT_PATH}"
        install -d -m700 "$(dirname "${HY2_CERT_PATH}")"
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
            -keyout "${HY2_KEY_PATH}" \
            -out "${HY2_CERT_PATH}" \
            -subj "/CN=sing-box-self-signed" \
            -addext "subjectAltName=DNS:sing-box" >/dev/null 2>&1
        chmod 600 "${HY2_KEY_PATH}"
    else
        echo "[deploy/proxy] TLS material already present"
    fi
else
    if [[ ! -f "${HY2_CERT_PATH}" || ! -f "${HY2_KEY_PATH}" ]]; then
        echo "[deploy/proxy] cert/key not found: ${HY2_CERT_PATH} ${HY2_KEY_PATH}" >&2
        exit 1
    fi
fi

# ── install config + systemd service ──────────────────────────────────────
install -d -m700 "${CONFIG_DIR}"
install -m600 "${DEPLOY_DIR}/config.json" "${CONFIG_DIR}/config.json"
install -m644 "${DEPLOY_DIR}/sing-box.service" /etc/systemd/system/sing-box.service

echo "[deploy/proxy] validating config"
"${BIN_DIR}/sing-box" check -c "${CONFIG_DIR}/config.json"

systemctl daemon-reload
systemctl enable --now sing-box
sleep 1
systemctl --no-pager --lines=5 status sing-box || true

# ── optional certbot deploy hook ──────────────────────────────────────────
if [[ -n "${CERTBOT_HOOK_DIR}" && -d "${CERTBOT_HOOK_DIR}" ]]; then
    install -Dm755 "${DEPLOY_DIR}/certbot-restart-sing-box.sh" \
        "${CERTBOT_HOOK_DIR}/restart-sing-box.sh"
    echo "[deploy/proxy] certbot deploy hook installed: ${CERTBOT_HOOK_DIR}/restart-sing-box.sh"
fi

echo "[deploy/proxy] done"
