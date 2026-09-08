#!/usr/bin/env bash
# Certbot deploy hook: restart/reload proxy frontends after a certificate renewal.
# - sing-box (Hysteria2 TLS) is restarted when the systemd unit exists
#   (user-scope sing-box deployments are left alone — restart them manually,
#    e.g. `systemctl --user restart sing-box` for the owning user).
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

for svc in openresty nginx; do
    if systemctl is-active --quiet "${svc}" 2>/dev/null; then
        systemctl reload "${svc}" 2>/dev/null || systemctl restart "${svc}"
    fi
done
