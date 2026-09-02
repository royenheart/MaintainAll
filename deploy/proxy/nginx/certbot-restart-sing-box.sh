#!/usr/bin/env bash
# Certbot deploy hook: restart sing-box after the Hysteria2 certificate is renewed.
# Install: install -Dm755 deploy/proxy/nginx/certbot-restart-sing-box.sh \
#            /etc/letsencrypt/renewal-hooks/deploy/restart-sing-box.sh
set -euo pipefail

if systemctl is-active --quiet sing-box 2>/dev/null; then
    systemctl restart sing-box
fi
