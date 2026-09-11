#!/usr/bin/env bash
set -eo pipefail

# =============================================================
# AstrBot — Data Restore
# =============================================================
#
# Restores an archive produced by export.sh. The data volume is
# replaced wholesale, so stop the container first:
#
#   ./deploy.py down
#   ./restore.sh export-astrbot-YYYYMMDD-HHMMSS.tar.gz --dry-run
#   ./restore.sh export-astrbot-YYYYMMDD-HHMMSS.tar.gz
#   ./deploy.py up
#
# .env is never overwritten. It is written to .env.restored for you
# to review and merge, because it holds host-specific values.
#
# Usage:
#   ./restore.sh <archive> [--dry-run] [--no-volumes] [--force] [--volume NAME]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=false
SKIP_VOLUMES=false
FORCE=false
VOLUME_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --no-volumes) SKIP_VOLUMES=true; shift ;;
        --force) FORCE=true; shift ;;
        --volume) VOLUME_OVERRIDE="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 <archive.tar.gz> [--dry-run] [--no-volumes] [--force] [--volume NAME]"
            echo ""
            echo "  --dry-run     Preview what would be restored"
            echo "  --no-volumes  Skip the data volume restore"
            echo "  --force       Skip the confirmation prompt"
            echo "  --volume NAME Restore into this volume instead of ASTRBOT_VOLUME"
            exit 0
            ;;
        -*) echo -e "${RED}Unknown option: $1${NC}"; exit 1 ;;
        *)  ARCHIVE="$1"; shift ;;
    esac
done

if [ -z "${ARCHIVE:-}" ]; then
    echo -e "${RED}Usage: $0 <archive.tar.gz>${NC}"
    echo "Run '$0 --help' for details."
    exit 1
fi

if [ ! -f "$ARCHIVE" ]; then
    echo -e "${RED}Archive not found: $ARCHIVE${NC}"
    exit 1
fi

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  AstrBot — Data Restore${NC}"
echo -e "${GREEN}============================================${NC}"
echo

# ------------------------------------------------------------------
# 1. Extract and inspect
# ------------------------------------------------------------------
echo -e "${YELLOW}[1/3] Reading archive...${NC}"

TEMP_DIR=$(mktemp -d -t astrbot-restore-XXXXXX)
cleanup() { rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

tar xzf "$ARCHIVE" -C "$TEMP_DIR"
EXTRACT_DIR="$TEMP_DIR/data"

if [ ! -f "$EXTRACT_DIR/manifest.json" ]; then
    echo -e "${RED}Invalid archive: manifest.json not found${NC}"
    exit 1
fi

MANIFEST=$(cat "$EXTRACT_DIR/manifest.json")
read_manifest() {
    echo "$MANIFEST" | python3 -c \
        "import sys,json; print(json.load(sys.stdin).get('$1','unknown'))" 2>/dev/null \
        || echo "unknown"
}

EXPORT_TIME=$(read_manifest export_time)
MANIFEST_VOLUME=$(read_manifest volume)
HAS_VOLUMES=$(echo "$MANIFEST" | python3 -c \
    "import sys,json; print(json.load(sys.stdin).get('contents',{}).get('volumes',False))" \
    2>/dev/null || echo "false")

# Target volume: --volume > .env ASTRBOT_VOLUME > manifest > default
if [ -n "$VOLUME_OVERRIDE" ]; then
    TARGET_VOLUME="$VOLUME_OVERRIDE"
elif [ -f .env ] && grep -q '^ASTRBOT_VOLUME=' .env; then
    TARGET_VOLUME=$(grep '^ASTRBOT_VOLUME=' .env | head -1 | cut -d= -f2-)
elif [ "$MANIFEST_VOLUME" != "unknown" ] && [ -n "$MANIFEST_VOLUME" ]; then
    TARGET_VOLUME="$MANIFEST_VOLUME"
else
    TARGET_VOLUME="astrbot_data"
fi

echo -e "  Export time:    ${BLUE}$EXPORT_TIME${NC}"
echo -e "  Has volume:     ${BLUE}$HAS_VOLUMES${NC}"
echo -e "  Archive volume: ${BLUE}$MANIFEST_VOLUME${NC}"
echo -e "  Restore into:   ${BLUE}$TARGET_VOLUME${NC}"
echo

VOL_TAR=$(ls "$EXTRACT_DIR"/volumes/*.tar.gz 2>/dev/null | head -1 || true)

# ------------------------------------------------------------------
# 2. Dry run or restore
# ------------------------------------------------------------------
if $DRY_RUN; then
    echo -e "${BLUE}━━━ DRY RUN — no changes will be made ━━━${NC}"
    echo
    if [ -n "$VOL_TAR" ] && ! $SKIP_VOLUMES; then
        echo -e "  Would replace volume ${BLUE}$TARGET_VOLUME${NC} with"
        echo -e "    $(basename "$VOL_TAR") ($(du -h "$VOL_TAR" | cut -f1))"
        echo
        echo -e "  ${YELLOW}This volume holds the dashboard credentials, IM platform${NC}"
        echo -e "  ${YELLOW}logins, session database, workspaces and plugin state.${NC}"
    elif $SKIP_VOLUMES; then
        echo -e "  Volume restore skipped (--no-volumes)"
    else
        echo -e "  ${YELLOW}No volume found in the archive${NC}"
    fi
    if [ -f "$EXTRACT_DIR/configs/.env" ]; then
        echo
        echo -e "  Would write ${BLUE}.env.restored${NC} for manual review"
    fi
    echo
    exit 0
fi

if ! $SKIP_VOLUMES && [ -n "$VOL_TAR" ]; then
    if ! $FORCE; then
        echo -e "${RED}This replaces the contents of volume '$TARGET_VOLUME'.${NC}"
        echo -e "  Existing dashboard credentials, IM platforms, sessions and"
        echo -e "  workspaces in that volume will be destroyed."
        echo -e "  Stop the container first: ./deploy.py down"
        echo
        echo -n "Continue? [y/N] "
        read -r CONFIRM
        if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
            echo "Aborted."
            exit 0
        fi
    fi

    echo -e "${YELLOW}[2/3] Restoring volume ${TARGET_VOLUME}...${NC}"

    if ! docker volume inspect "$TARGET_VOLUME" >/dev/null 2>&1; then
        docker volume create "$TARGET_VOLUME" >/dev/null
        echo -e "    ${GREEN}✓${NC} created volume"
    fi

    docker run --rm \
        -v "${TARGET_VOLUME}:/volume" \
        -v "$(dirname "$VOL_TAR"):/backup:ro" \
        alpine \
        sh -c "rm -rf /volume/* /volume/.[!.]* /volume/..?* 2>/dev/null; tar xzf /backup/$(basename "$VOL_TAR") -C /volume" 2>/dev/null

    echo -e "    ${GREEN}✓${NC} volume restored"
else
    echo -e "${YELLOW}[2/3] Volume restore: SKIPPED${NC}"
fi

# ------------------------------------------------------------------
# 3. .env for manual merge
# ------------------------------------------------------------------
if [ -f "$EXTRACT_DIR/configs/.env" ]; then
    cp "$EXTRACT_DIR/configs/.env" "$SCRIPT_DIR/.env.restored"
    echo -e "${YELLOW}[3/3] .env written to .env.restored${NC}"
    echo -e "      Review it before use — it belongs to the exporting host:"
    echo -e "        diff .env .env.restored"
else
    echo -e "${YELLOW}[3/3] .env: not in archive${NC}"
fi

echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Restore complete${NC}"
echo -e "${GREEN}============================================${NC}"
echo
echo -e "  Next steps:"
echo -e "    1. Merge .env.restored into .env if needed"
echo -e "    2. Start AstrBot:  ./deploy.py up"
echo -e "    3. Verify:         ./deploy.py status"
echo
