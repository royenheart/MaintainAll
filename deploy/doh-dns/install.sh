#!/bin/bash
# Install reusable DoH DNS kit (dnscrypt-proxy + systemd unit).
set -euo pipefail

KIT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$KIT_DIR"

if [ -f "$KIT_DIR/config.env" ]; then
  # shellcheck disable=SC1091
  set -a
  source "$KIT_DIR/config.env"
  set +a
elif [ -f "$KIT_DIR/config.env.example" ]; then
  # shellcheck disable=SC1091
  set -a
  source "$KIT_DIR/config.env.example"
  set +a
fi

VER="${DNSCRYPT_PROXY_VERSION:-2.1.18}"
PREFIX="${INSTALL_PREFIX:-/opt/doh-dns}"
LISTEN_ADDR="${DOH_LISTEN_ADDR:-127.0.0.1}"
LISTEN_PORT="${DOH_LISTEN_PORT:-5353}"
ENABLE_ON_INSTALL="${ENABLE_ON_INSTALL:-0}"
UNIT_DST=/etc/systemd/system/doh-dns.service
STATE_DIR=/var/lib/doh-dns

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo $0" >&2
  exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH_TAG=x86_64 ;;
  aarch64|arm64) ARCH_TAG=arm64 ;;
  *)
    echo "Unsupported arch: $ARCH" >&2
    exit 1
    ;;
esac

TAR=""
shopt -s nullglob
candidates=(
  "$KIT_DIR/vendor/dnscrypt-proxy-linux_${ARCH_TAG}-${VER}.tar.gz"
  "$KIT_DIR/dnscrypt-proxy-linux_${ARCH_TAG}-${VER}.tar.gz"
  "$KIT_DIR/vendor/dnscrypt-proxy-linux_${ARCH_TAG}-"*.tar.gz
  "$KIT_DIR/dnscrypt-proxy-linux_${ARCH_TAG}-"*.tar.gz
)
shopt -u nullglob
for f in "${candidates[@]+"${candidates[@]}"}"; do
  if [ -f "$f" ]; then
    TAR="$f"
    break
  fi
done

if [ -z "$TAR" ]; then
  cat >&2 <<EOF
Missing dnscrypt-proxy tarball for ${ARCH_TAG}.

Fetch it first:
  ./download.sh
  # or on a DNS-broken host:
  ./download.sh --print-lookup-cmds
  sudo ./download.sh --broken-dns <github-IP> <objects-IP>

Expected:
  vendor/dnscrypt-proxy-linux_${ARCH_TAG}-${VER}.tar.gz
EOF
  exit 1
fi
echo "Using: $TAR"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
tar -xzf "$TAR" -C "$tmpdir"

bin=""
if [ -x "$tmpdir/linux-${ARCH_TAG}/dnscrypt-proxy" ]; then
  bin="$tmpdir/linux-${ARCH_TAG}/dnscrypt-proxy"
elif [ -x "$tmpdir/linux-x86_64/dnscrypt-proxy" ]; then
  bin="$tmpdir/linux-x86_64/dnscrypt-proxy"
else
  bin="$(find "$tmpdir" -type f -name dnscrypt-proxy | head -1 || true)"
fi
if [ -z "$bin" ] || [ ! -x "$bin" ]; then
  echo "dnscrypt-proxy binary not found in tarball" >&2
  exit 1
fi

install -d -m 0755 "$PREFIX" "$STATE_DIR" "$PREFIX"
install -m 0755 "$bin" "$PREFIX/dnscrypt-proxy"
install -m 0755 "$KIT_DIR/doh-dns-apply" "$PREFIX/doh-dns-apply"
install -m 0755 "$KIT_DIR/dohctl" /usr/local/sbin/dohctl
install -m 0644 "$KIT_DIR/doh-dns.service" "$UNIT_DST"
install -m 0644 "$KIT_DIR/README.md" "$PREFIX/README.md"

# Materialize config.env for runtime
cat >"$PREFIX/config.env" <<EOF
DNSCRYPT_PROXY_VERSION=$VER
DOH_LISTEN_ADDR=$LISTEN_ADDR
DOH_LISTEN_PORT=$LISTEN_PORT
DOH_DNS_IFACE=${DOH_DNS_IFACE:-}
INSTALL_PREFIX=$PREFIX
ENABLE_ON_INSTALL=$ENABLE_ON_INSTALL
EOF
chmod 0644 "$PREFIX/config.env"

# Render listen address into toml
sed "s/listen_addresses = \\['[^']*'\\]/listen_addresses = ['${LISTEN_ADDR}:${LISTEN_PORT}']/" \
  "$KIT_DIR/dnscrypt-proxy.toml" >"$PREFIX/dnscrypt-proxy.toml"
chmod 0644 "$PREFIX/dnscrypt-proxy.toml"

"$PREFIX/dnscrypt-proxy" -config "$PREFIX/dnscrypt-proxy.toml" -check
systemctl daemon-reload

if [ "$ENABLE_ON_INSTALL" = "1" ]; then
  systemctl enable --now doh-dns.service
  echo "Enabled and started doh-dns.service"
else
  cat <<EOF

Installed to $PREFIX
Unit: doh-dns.service

Start (manual):
  sudo systemctl start doh-dns
  dohctl status
  dohctl test

Autostart later:
  sudo systemctl enable doh-dns
EOF
fi
