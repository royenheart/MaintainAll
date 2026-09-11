#!/usr/bin/env bash
set -eo pipefail

# =============================================================
# AstrBot — Data Export
# =============================================================
#
# AstrBot keeps everything that matters inside its data volume:
# dashboard credentials, IM platform logins, the session database,
# workspaces, the knowledge base and installed plugin state. The
# container is disposable; the volume is not. Back it up before
# touching the stack.
#
# Exports:
#   - the astrbot data volume (as named in .env ASTRBOT_VOLUME)
#   - .env
#
# Output: export-astrbot-YYYYMMDD-HHMMSS.tar.gz
#
# Usage:
#   ./export.sh                      # Export volume + .env
#   ./export.sh --no-volumes         # Skip the volume
#   ./export.sh --volume NAME        # Override the volume name
#   ./export.sh --output /tmp/backup # Custom output directory

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR}"
ARCHIVE_NAME="export-astrbot-${TIMESTAMP}.tar.gz"
TEMP_DIR=$(mktemp -d -t astrbot-export-XXXXXX)
SKIP_VOLUMES=false
VOLUME_OVERRIDE=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-volumes) SKIP_VOLUMES=true; shift ;;
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --volume) VOLUME_OVERRIDE="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--no-volumes] [--output DIR] [--volume NAME]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

cleanup() { rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

mkdir -p "$TEMP_DIR/data"
EXPORT_DATA="$TEMP_DIR/data"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  AstrBot — Data Export${NC}"
echo -e "${GREEN}============================================${NC}"
echo

# ------------------------------------------------------------------
# Resolve the volume name: --volume > .env ASTRBOT_VOLUME > default
# ------------------------------------------------------------------
if [ -n "$VOLUME_OVERRIDE" ]; then
    VOLUME="$VOLUME_OVERRIDE"
elif [ -f .env ] && grep -q '^ASTRBOT_VOLUME=' .env; then
    VOLUME=$(grep '^ASTRBOT_VOLUME=' .env | head -1 | cut -d= -f2-)
else
    VOLUME="astrbot_data"
fi

# ------------------------------------------------------------------
# 1. Export the data volume
# ------------------------------------------------------------------
if $SKIP_VOLUMES; then
    echo -e "${YELLOW}[1/3] Data volume: SKIPPED (--no-volumes)${NC}"
else
    echo -e "${YELLOW}[1/3] Exporting data volume: ${VOLUME}${NC}"
    if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
        mkdir -p "$EXPORT_DATA/volumes"
        OUT="$EXPORT_DATA/volumes/${VOLUME}.tar.gz"
        docker run --rm \
            -v "${VOLUME}:/volume:ro" \
            alpine \
            tar czf - -C /volume . > "$OUT" 2>/dev/null \
            && echo -e "    ${GREEN}✓${NC} $VOLUME ($(du -h "$OUT" | cut -f1))" \
            || echo -e "    ${RED}✗${NC} $VOLUME export failed"
    else
        echo -e "    ${RED}✗${NC} Volume '$VOLUME' not found."
        echo -e "      Set ASTRBOT_VOLUME in .env, or pass --volume NAME."
        echo -e "      Known volumes:"
        docker volume ls --format '        {{.Name}}' | grep -i astrbot || true
    fi
fi

# ------------------------------------------------------------------
# 2. Configuration
# ------------------------------------------------------------------
echo -e "${YELLOW}[2/3] Collecting configuration...${NC}"
mkdir -p "$EXPORT_DATA/configs"

# .env holds the dashboard password. It is archived, but restore.sh
# will not overwrite a live .env with it — see the restore notes.
if [ -f .env ]; then
    cp .env "$EXPORT_DATA/configs/"
    echo -e "    ${GREEN}✓${NC} .env (contains the dashboard password)"
else
    echo -e "    ${YELLOW}⊘${NC} .env not found"
fi

# AstrBot's own cmd_config.json lives in the data volume and is
# already captured above.

# ------------------------------------------------------------------
# 3. Manifest and archive
# ------------------------------------------------------------------
echo -e "${YELLOW}[3/3] Writing manifest and archive...${NC}"

cat > "$EXPORT_DATA/manifest.json" << EOFMAN
{
    "export_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "stack": "astrbot",
    "version": "1.0",
    "volume": "$VOLUME",
    "contents": {
        "volumes": $(if $SKIP_VOLUMES; then echo "false"; else echo "true"; fi),
        "configs": true
    }
}
EOFMAN

ARCHIVE_PATH="$OUTPUT_DIR/$ARCHIVE_NAME"
tar czf "$ARCHIVE_PATH" -C "$TEMP_DIR" data

echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Export complete${NC}"
echo -e "${GREEN}============================================${NC}"
echo
echo -e "  Archive: ${GREEN}$ARCHIVE_PATH${NC}"
echo -e "  Size:    $(du -h "$ARCHIVE_PATH" | cut -f1)"
echo -e "  Volume:  $VOLUME"
echo
echo -e "  Restore on another host with:"
echo -e "    ./restore.sh $(basename "$ARCHIVE_PATH")"
echo
