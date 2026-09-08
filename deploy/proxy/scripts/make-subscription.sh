#!/usr/bin/env bash
# deploy/proxy: compose a plain daed/dae subscription from share links —
# no web panel, no converter. A dae subscription URL just needs to return the
# base64 of the node link list, one link per line.
#
# Usage:
#   ./scripts/make-subscription.sh <links-file> [<out-file>]
#
#   <links-file>  text file with one share link per line
#                 (comments starting with '#' and blank lines are skipped)
#   <out-file>    where to write the single-line base64 payload
#                 (default: <links-file>.b64)
#
# Output: prints the base64 payload and reminders on serving it.
#
# Serving options (pick one; the URL you give daed must return this payload):
#   - static file over your own nginx/OpenResty (see openresty/ template),
#   - any static HTTPS host you control.
# Then in daed: Subscriptions -> add that URL (+ optional cron). If the URL is
# HTTPS with a self-signed certificate, daed's fetch may reject the TLS cert —
# either serve over plain HTTP on a private port, use a valid certificate, or
# test first.

set -euo pipefail

LINKS_FILE="${1:-}"
OUT_FILE="${2:-}"
if [[ -z "${LINKS_FILE}" || ! -f "${LINKS_FILE}" ]]; then
    echo "usage: $0 <links-file> [<out-file>]" >&2
    exit 1
fi
if [[ -z "${OUT_FILE}" ]]; then
    OUT_FILE="${LINKS_FILE}.b64"
fi

# strip comments/blank lines, trim whitespace, drop empty
grep -vE '^\s*(#|$)' "${LINKS_FILE}" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | grep -v '^$' > "${OUT_FILE}.plain"
# single-line, unpadded-style tolerant base64 (dae decodes standard base64)
base64 -w0 "${OUT_FILE}.plain" > "${OUT_FILE}"
rm -f "${OUT_FILE}.plain"

echo "== base64 payload written to ${OUT_FILE} =="
cat "${OUT_FILE}"
echo
echo "== next steps =="
echo "1. Serve ${OUT_FILE} at an URL (static file is enough, e.g. an exact"
echo "   location = /<unguessable-path> in your openresty/nginx TLS server)."
echo "2. daed Web UI -> Subscriptions -> add that URL, set a cron (or '0 4 * * *')."
echo "3. In daed Groups, use the subscription nodes as usual."
