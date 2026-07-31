#!/bin/bash
# Remove DoH kit install (keeps vendor/ tarball in the repo copy).
set -euo pipefail

PREFIX="${INSTALL_PREFIX:-/opt/doh-dns}"
UNIT=/etc/systemd/system/doh-dns.service

if [ -f "$PREFIX/config.env" ]; then
  # shellcheck disable=SC1091
  set -a
  source "$PREFIX/config.env"
  set +a
  PREFIX="${INSTALL_PREFIX:-$PREFIX}"
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo $0" >&2
  exit 1
fi

systemctl disable --now doh-dns.service 2>/dev/null || true
# ExecStopPost should restore DNS; call explicitly if unit already gone
if [ -x "$PREFIX/doh-dns-apply" ]; then
  "$PREFIX/doh-dns-apply" off 2>/dev/null || true
fi

rm -f "$UNIT" /usr/local/sbin/dohctl
rm -rf "$PREFIX" /var/lib/doh-dns
systemctl daemon-reload
echo "doh-dns removed."
