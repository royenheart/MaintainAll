#!/bin/bash
# Download dnscrypt-proxy official static tarball into ./vendor/
#
# Modes:
#   ./download.sh
#       Normal download (needs working DNS).
#   ./download.sh --broken-dns <github-IP> <objects-IP> [release-assets-IP]
#       For hosts where port 53 is blocked: temporarily append /etc/hosts, download, then remind to clean up.
#   ./download.sh --print-lookup-cmds
#       Print dig/getent commands to run on a healthy host to obtain those IPs.
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
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH_TAG=x86_64 ;;
  aarch64|arm64) ARCH_TAG=arm64 ;;
  *)
    echo "Unsupported arch: $ARCH (edit download.sh / fetch matching release asset)" >&2
    exit 1
    ;;
esac

VENDOR="$KIT_DIR/vendor"
mkdir -p "$VENDOR"
OUT="$VENDOR/dnscrypt-proxy-linux_${ARCH_TAG}-${VER}.tar.gz"
URL="https://github.com/DNSCrypt/dnscrypt-proxy/releases/download/${VER}/dnscrypt-proxy-linux_${ARCH_TAG}-${VER}.tar.gz"
MARKER='# temporary for deploy/doh-dns download'

print_lookup() {
  cat <<'EOF'
Run on a host WITH working DNS (same arch preference not required):

  dig +short github.com A | head -1
  dig +short objects.githubusercontent.com A | head -1
  dig +short release-assets.githubusercontent.com A | head -1

  # or:
  getent ahostsv4 github.com | awk '{print $1; exit}'
  getent ahostsv4 objects.githubusercontent.com | awk '{print $1; exit}'
  getent ahostsv4 release-assets.githubusercontent.com | awk '{print $1; exit}'

Then on the broken host:

  sudo ./download.sh --broken-dns <github-IP> <objects-IP> [release-assets-IP]
EOF
}

append_hosts() {
  local gh="$1" obj="$2" rel="$3"
  if [ "$(id -u)" -ne 0 ]; then
    echo "Root required to write /etc/hosts for --broken-dns" >&2
    exit 1
  fi
  if grep -q "$MARKER" /etc/hosts 2>/dev/null; then
    echo "Hosts marker already present; skipping append."
    return
  fi
  cat >>/etc/hosts <<EOF
$MARKER
$gh github.com
$obj objects.githubusercontent.com
$rel release-assets.githubusercontent.com
EOF
  echo "Appended temporary /etc/hosts entries (marker: $MARKER)"
}

do_curl() {
  echo "Downloading: $URL"
  curl -L --fail --retry 3 --connect-timeout 15 --max-time 600 -o "$OUT" "$URL"
  ls -lh "$OUT"
  echo "Saved: $OUT"
}

mode="${1:-}"
case "$mode" in
  --print-lookup-cmds)
    print_lookup
    exit 0
    ;;
  --broken-dns)
    shift || true
    GH_IP="${1:-${GITHUB_HOST_IP:-}}"
    OBJ_IP="${2:-${OBJECTS_HOST_IP:-}}"
    REL_IP="${3:-${RELEASE_ASSETS_HOST_IP:-$OBJ_IP}}"
    if [ -z "$GH_IP" ] || [ -z "$OBJ_IP" ]; then
      echo "Usage: $0 --broken-dns <github-IP> <objects-IP> [release-assets-IP]" >&2
      print_lookup
      exit 2
    fi
    append_hosts "$GH_IP" "$OBJ_IP" "$REL_IP"
    do_curl
    cat <<EOF

Download OK. Install next:
  sudo ./install.sh

After DoH works, remove temporary hosts lines:
  sudo sed -i '/${MARKER}/,+3d' /etc/hosts
EOF
    ;;
  "")
    do_curl
    echo "Next: sudo ./install.sh"
    ;;
  -h|--help)
    cat <<EOF
Usage:
  $0
  $0 --broken-dns <github-IP> <objects-IP> [release-assets-IP]
  $0 --print-lookup-cmds
EOF
    ;;
  *)
    echo "Unknown option: $mode" >&2
    exit 2
    ;;
esac
