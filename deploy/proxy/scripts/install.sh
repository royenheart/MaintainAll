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
#   SERVICE_SCOPE      system (default) or user
#   SERVICE_USER       account that owns the user unit (required when scope=user)
#   KEEP_CONFIG        1 = do not replace an existing config.json
#   REPLACE_MANUAL     1 = stop a sing-box that was started by hand on this config
#                      before the user unit binds its ports
#   SKIP_BINARY        1 = keep the binary already installed for this scope

set -euo pipefail

SING_BOX_VERSION="${SING_BOX_VERSION:-1.14.0}"
BIN_DIR="${BIN_DIR:-/usr/local/bin}"
CONFIG_DIR="${CONFIG_DIR:-/etc/sing-box}"
TLS_DIR="${TLS_DIR:-${CONFIG_DIR}/tls}"
HY2_CERT_PATH="${HY2_CERT_PATH:-${TLS_DIR}/server.crt}"
HY2_KEY_PATH="${HY2_KEY_PATH:-${TLS_DIR}/server.key}"
GEN_SELF_SIGNED="${GEN_SELF_SIGNED:-1}"
CERTBOT_HOOK_DIR="${CERTBOT_HOOK_DIR:-}"
SERVICE_SCOPE="${SERVICE_SCOPE:-system}"
SERVICE_USER="${SERVICE_USER:-}"
KEEP_CONFIG="${KEEP_CONFIG:-0}"
REPLACE_MANUAL="${REPLACE_MANUAL:-0}"
SKIP_BINARY="${SKIP_BINARY:-0}"
DEPLOY_DIR="/tmp/sing-box-deploy"

if [[ $EUID -ne 0 ]]; then
    echo "[deploy/proxy] must run as root on the remote host" >&2
    exit 1
fi

if [[ "${SERVICE_SCOPE}" != "system" && "${SERVICE_SCOPE}" != "user" ]]; then
    echo "[deploy/proxy] SERVICE_SCOPE must be system or user" >&2
    exit 1
fi

if [[ "${SERVICE_SCOPE}" == "user" ]]; then
    if [[ -z "${SERVICE_USER}" ]]; then
        echo "[deploy/proxy] SERVICE_USER is required for user systemd" >&2
        exit 1
    fi
    APP_HOME="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)"
    APP_UID="$(id -u "${SERVICE_USER}")"
    if [[ -z "${APP_HOME}" || -z "${APP_UID}" ]]; then
        echo "[deploy/proxy] no account named ${SERVICE_USER}" >&2
        exit 1
    fi
    # Stock system paths mean "use this user's own directories".
    if [[ "${BIN_DIR}" == "/usr/local/bin" ]]; then
        BIN_DIR="${APP_HOME}/.local/bin"
    fi
    if [[ "${CONFIG_DIR}" == "/etc/sing-box" ]]; then
        CONFIG_DIR="${APP_HOME}/.config/sing-box"
        TLS_DIR="${CONFIG_DIR}/tls"
        HY2_CERT_PATH="${TLS_DIR}/server.crt"
        HY2_KEY_PATH="${TLS_DIR}/server.key"
    fi
fi

echo "[deploy/proxy] installing sing-box v${SING_BOX_VERSION}"

# ── arch mapping ──────────────────────────────────────────────────────────
case "$(uname -m)" in
    x86_64) ARCH="amd64" ;;
    aarch64) ARCH="arm64" ;;
    *) echo "[deploy/proxy] unsupported arch: $(uname -m)" >&2; exit 1 ;;
esac

# ── install sing-box binary ───────────────────────────────────────────────
if [[ "${SKIP_BINARY}" == "1" && -x "${BIN_DIR}/sing-box" ]]; then
    echo "[deploy/proxy] keeping existing binary: $("${BIN_DIR}/sing-box" version | head -1)"
elif [[ ! -x "${BIN_DIR}/sing-box" ]] || ! "${BIN_DIR}/sing-box" version 2>/dev/null | grep -q " ${SING_BOX_VERSION}$"; then
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
if [[ "${KEEP_CONFIG}" == "1" ]]; then
    echo "[deploy/proxy] keeping existing config: ${CONFIG_DIR}/config.json"
elif [[ "${GEN_SELF_SIGNED}" == "1" ]]; then
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
if [[ "${KEEP_CONFIG}" == "1" ]]; then
    if [[ ! -f "${CONFIG_DIR}/config.json" ]]; then
        echo "[deploy/proxy] KEEP_CONFIG=1 but missing ${CONFIG_DIR}/config.json" >&2
        exit 1
    fi
else
    install -m600 "${DEPLOY_DIR}/config.json" "${CONFIG_DIR}/config.json"
fi
if [[ "${SERVICE_SCOPE}" == "user" ]]; then
    chown "${SERVICE_USER}" "${CONFIG_DIR}/config.json"
fi

echo "[deploy/proxy] validating config"
"${BIN_DIR}/sing-box" check -c "${CONFIG_DIR}/config.json"

# UDP 443 is privileged. A user service needs this capability on the binary.
if python3 -c 'import json,sys
ports=[]
for item in json.load(open(sys.argv[1])).get("inbounds",[]):
    port=item.get("listen_port")
    if isinstance(port,int):
        ports.append(port)
sys.exit(0 if any(port<1024 for port in ports) else 1)' "${CONFIG_DIR}/config.json"; then
    setcap 'cap_net_bind_service=+ep' "${BIN_DIR}/sing-box"
    echo "[deploy/proxy] granted cap_net_bind_service on ${BIN_DIR}/sing-box"
fi

if [[ "${SERVICE_SCOPE}" == "user" ]]; then
    unit_dir="${APP_HOME}/.config/systemd/user"
    install -d -m700 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${unit_dir}"
    if [[ ! -f "${DEPLOY_DIR}/sing-box.user.service" ]]; then
        echo "[deploy/proxy] missing ${DEPLOY_DIR}/sing-box.user.service" >&2
        exit 1
    fi
    sed \
        -e "s#%h/.local/bin/sing-box#${BIN_DIR}/sing-box#" \
        -e "s#%h/.config/sing-box/config.json#${CONFIG_DIR}/config.json#" \
        "${DEPLOY_DIR}/sing-box.user.service" > "${unit_dir}/sing-box.service"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${unit_dir}/sing-box.service"
    chmod 644 "${unit_dir}/sing-box.service"

    loginctl enable-linger "${SERVICE_USER}"
    systemctl start "user@${APP_UID}.service"

    if [[ "${REPLACE_MANUAL}" == "1" ]]; then
        echo "[deploy/proxy] stopping sing-box processes that are not the user unit"
        for pid in $(ps -eo pid=,cmd= | awk '/sing-box run -c/ && !/awk/ {print $1}'); do
            if [[ ! -r "/proc/${pid}/cgroup" ]] || ! grep -q 'sing-box.service' "/proc/${pid}/cgroup"; then
                kill "${pid}" 2>/dev/null || true
            fi
        done
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            if ! ss -ulnp | grep -q ':443 '; then
                break
            fi
            sleep 0.3
        done
    fi

    runuser -u "${SERVICE_USER}" -- env "XDG_RUNTIME_DIR=/run/user/${APP_UID}" \
        systemctl --user daemon-reload
    runuser -u "${SERVICE_USER}" -- env "XDG_RUNTIME_DIR=/run/user/${APP_UID}" \
        systemctl --user enable --now sing-box
    sleep 1
    runuser -u "${SERVICE_USER}" -- env "XDG_RUNTIME_DIR=/run/user/${APP_UID}" \
        systemctl --user --no-pager --lines=5 status sing-box || true
else
    install -m644 "${DEPLOY_DIR}/sing-box.service" /etc/systemd/system/sing-box.service
    systemctl daemon-reload
    systemctl enable --now sing-box
    sleep 1
    systemctl --no-pager --lines=5 status sing-box || true
fi

# ── optional certbot deploy hook ──────────────────────────────────────────
if [[ -n "${CERTBOT_HOOK_DIR}" && -d "${CERTBOT_HOOK_DIR}" ]]; then
    install -Dm755 "${DEPLOY_DIR}/certbot-restart-sing-box.sh" \
        "${CERTBOT_HOOK_DIR}/restart-sing-box.sh"
    echo "[deploy/proxy] certbot deploy hook installed: ${CERTBOT_HOOK_DIR}/restart-sing-box.sh"
fi

echo "[deploy/proxy] done"
