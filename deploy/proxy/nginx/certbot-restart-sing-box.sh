#!/usr/bin/env bash
# Certbot deploy hook: restart/reload proxy frontends after a certificate renewal.
# - sing-box (Hysteria2 TLS) is restarted when the system unit is active.
#   Lingering users with a user unit are restarted too, so a logout does not
#   leave a renewed certificate unloaded.
# - openresty / nginx are reloaded when active, so the VLESS-over-WS TLS
#   frontend picks up the renewed certificate.
#
# Install:
#   install -Dm755 deploy/proxy/nginx/certbot-restart-sing-box.sh \
#             /etc/letsencrypt/renewal-hooks/deploy/restart-sing-box.sh
set -euo pipefail

if systemctl is-active --quiet sing-box 2>/dev/null; then
    systemctl restart sing-box
fi

linger_dir=/var/lib/systemd/linger
if [[ -d "${linger_dir}" ]]; then
    for linger_file in "${linger_dir}"/*; do
        [[ -f "${linger_file}" ]] || continue
        user="$(basename "${linger_file}")"
        home="$(getent passwd "${user}" | cut -d: -f6)"
        uid="$(id -u "${user}" 2>/dev/null || true)"
        if [[ -z "${home}" || -z "${uid}" ]]; then
            continue
        fi
        if [[ ! -f "${home}/.config/systemd/user/sing-box.service" ]]; then
            continue
        fi
        runuser -u "${user}" -- env "XDG_RUNTIME_DIR=/run/user/${uid}" \
            systemctl --user restart sing-box || true
    done
fi

for svc in openresty nginx; do
    if systemctl is-active --quiet "${svc}" 2>/dev/null; then
        systemctl reload "${svc}" 2>/dev/null || systemctl restart "${svc}"
    fi
done
