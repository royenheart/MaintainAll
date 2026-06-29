#!/usr/bin/env bash
set -eo pipefail

# =============================================================
# Remote Computer Use — Data Restore
# =============================================================
#
# Restores an export archive created by export.sh.
#
# Usage:
#   ./restore.sh export-cua-YYYYMMDD-HHMMSS.tar.gz
#   ./restore.sh export-cua-YYYYMMDD-HHMMSS.tar.gz --dry-run
#   ./restore.sh export-cua-YYYYMMDD-HHMMSS.tar.gz --no-volumes
#   ./restore.sh export-cua-YYYYMMDD-HHMMSS.tar.gz --force

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

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --no-volumes) SKIP_VOLUMES=true; shift ;;
        --force) FORCE=true; shift ;;
        --help|-h)
            echo "Usage: $0 <archive.tar.gz> [--dry-run] [--no-volumes] [--force]"
            echo ""
            echo "  --dry-run     Preview what would be restored"
            echo "  --no-volumes  Skip Docker volume restore"
            echo "  --force       Skip confirmation prompt"
            exit 0
            ;;
        -*)
            # Must be an unknown flag - could also be an issue with the archive path
            if [ ! -f "$1" ]; then
                echo -e "${RED}Unknown option or file not found: $1${NC}"
                exit 1
            fi
            ARCHIVE="$1"; shift
            ;;
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
echo -e "${GREEN}  CUA Deploy — Data Restore${NC}"
echo -e "${GREEN}============================================${NC}"
echo

# ------------------------------------------------------------------
# 1. Extract and inspect
# ------------------------------------------------------------------
echo -e "${YELLOW}[1/5] Reading archive...${NC}"

TEMP_DIR=$(mktemp -d -t cua-restore-XXXXXX)
cleanup() { rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

tar xzf "$ARCHIVE" -C "$TEMP_DIR"
EXTRACT_DIR="$TEMP_DIR/data"

if [ ! -f "$EXTRACT_DIR/manifest.json" ]; then
    echo -e "${RED}Invalid archive: manifest.json not found${NC}"
    exit 1
fi

# Read manifest
MANIFEST=$(cat "$EXTRACT_DIR/manifest.json")
EXPORT_TIME=$(echo "$MANIFEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('export_time','unknown'))" 2>/dev/null || echo "unknown")
HAS_VOLUMES=$(echo "$MANIFEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('contents',{}).get('volumes',False))" 2>/dev/null || echo "false")
HAS_CONFIGS=$(echo "$MANIFEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('contents',{}).get('configs',False))" 2>/dev/null || echo "false")
HAS_SKILLS=$(echo "$MANIFEST" | python3 -c "import sys,json; print(json.load(sys.stdin).get('contents',{}).get('skills',False))" 2>/dev/null || echo "false")

echo -e "  Export time:   ${BLUE}$EXPORT_TIME${NC}"
echo -e "  Has volumes:   ${BLUE}$HAS_VOLUMES${NC}"
echo -e "  Has configs:   ${BLUE}$HAS_CONFIGS${NC}"
echo -e "  Has skills:    ${BLUE}$HAS_SKILLS${NC}"
echo

# ------------------------------------------------------------------
# 2. Preview / dry-run
# ------------------------------------------------------------------
if $DRY_RUN; then
    echo -e "${BLUE}━━━ DRY RUN — no changes will be made ━━━${NC}"
    echo

    if [ -d "$EXTRACT_DIR/volumes" ] && [ "$(ls -A "$EXTRACT_DIR/volumes" 2>/dev/null)" ]; then
        echo "  Docker volumes that would be restored:"
        for vol_tar in "$EXTRACT_DIR/volumes"/*.tar.gz; do
            [ -f "$vol_tar" ] || continue
            vol_name=$(basename "$vol_tar" .tar.gz)
            vol_name=$(echo "$vol_name" | sed 's/^cua-//')
            echo "    - $vol_name ($(du -h "$vol_tar" | cut -f1))"
        done
    fi

    if [ -d "$EXTRACT_DIR/configs" ]; then
        echo "  Config files that would be restored:"
        find "$EXTRACT_DIR/configs" -type f | sed 's|.*/configs/||' | while read -r f; do
            echo "    - $f"
        done
    fi

    if [ -d "$EXTRACT_DIR/skills" ]; then
        echo "  Skills that would be restored:"
        find "$EXTRACT_DIR/skills" -name "SKILL.md" | while read -r f; do
            skill_name=$(basename "$(dirname "$f")")
            echo "    - $skill_name"
        done
    fi

    echo
    exit 0
fi

# ------------------------------------------------------------------
# 3. Confirmation
# ------------------------------------------------------------------
if ! $FORCE; then
    echo -e "${RED}This will overwrite existing data!${NC}"
    echo "  Docker volumes will be replaced."
    echo "  Config files (.env, cmd_config.json, config.yaml) will be overwritten."
    echo "  Running containers should be stopped first."
    echo
    echo -n "Continue? [y/N] "
    read -r CONFIRM
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "Aborted."
        exit 0
    fi
fi

echo

# ------------------------------------------------------------------
# 4. Restore Docker volumes
# ------------------------------------------------------------------
restore_docker_volume() {
    local archive_vol=$1
    local target_volume=$2

    if [ ! -f "$archive_vol" ]; then
        return
    fi

    echo -e "    Restoring volume: ${BLUE}$target_volume${NC}"

    # Create volume if it doesn't exist
    if ! docker volume inspect "$target_volume" >/dev/null 2>&1; then
        docker volume create "$target_volume" >/dev/null
    fi

    # Extract into volume
    docker run --rm \
        -v "${target_volume}:/volume" \
        -v "$(dirname "$archive_vol"):/backup:ro" \
        alpine \
        sh -c "rm -rf /volume/* /volume/.[!.]* /volume/..?* 2>/dev/null; tar xzf /backup/$(basename "$archive_vol") -C /volume" 2>/dev/null

    echo -e "      ${GREEN}✓${NC} done"
}

if ! $SKIP_VOLUMES && [ -d "$EXTRACT_DIR/volumes" ]; then
    echo -e "${YELLOW}[2/5] Restoring Docker volumes...${NC}"

    VOLUME_COUNT=0
    for vol_tar in "$EXTRACT_DIR/volumes"/*.tar.gz; do
        [ -f "$vol_tar" ] || continue
        VOLUME_COUNT=$((VOLUME_COUNT + 1))
        raw_name=$(basename "$vol_tar" .tar.gz)

        # Map compose-prefixed names to canonical names
        case "$raw_name" in
            *astrbot_data*)   target="astrbot_data" ;;
            *hermes_data*)    target="hermes_data" ;;
            *)                target="$raw_name" ;;
        esac

        # Check if prefix exists in current compose project
        PROJECT=$(docker compose ls 2>/dev/null | grep compute-browser-use | awk '{print $1}' | head -1)
        if [ -n "$PROJECT" ]; then
            prefixed="${PROJECT}_${target}"
            if docker volume inspect "$prefixed" >/dev/null 2>&1; then
                target="$prefixed"
            fi
        fi

        restore_docker_volume "$vol_tar" "$target"
    done

    if [ "$VOLUME_COUNT" -eq 0 ]; then
        echo -e "    ${YELLOW}⊘${NC} No volumes in archive"
    fi
else
    echo -e "${YELLOW}[2/5] Docker volumes: SKIPPED${NC}"
fi

# ------------------------------------------------------------------
# 5. Restore configuration files
# ------------------------------------------------------------------
if [ -d "$EXTRACT_DIR/configs" ]; then
    echo -e "${YELLOW}[3/5] Restoring configuration files...${NC}"

    RESTORE_DIR="$SCRIPT_DIR"

    # Create backups of existing files
    BACKUP_DIR="$SCRIPT_DIR/.restore-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"

    restore_file() {
        local src="$EXTRACT_DIR/configs/$1"
        local dst="$RESTORE_DIR/$1"

        if [ ! -f "$src" ]; then
            return
        fi

        # Backup existing file
        if [ -f "$dst" ]; then
            mkdir -p "$(dirname "$BACKUP_DIR/$1")"
            cp "$dst" "$BACKUP_DIR/$1"
        fi

        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        echo -e "    ${GREEN}✓${NC} $1"
    }

    # Never restore .env blindly — warn if it contains secrets
    if [ -f "$EXTRACT_DIR/configs/.env" ]; then
        echo -e "    ${YELLOW}!${NC} .env found in archive"
        echo -e "      The .env file may contain API keys specific to the old server."
        echo -e "      It has been copied to ${BLUE}${SCRIPT_DIR}/.env.restored${NC}"
        echo -e "      Please review and merge manually into your current .env"
        cp "$EXTRACT_DIR/configs/.env" "$RESTORE_DIR/.env.restored"
    fi

    # Restore server configs
    for conf in server/astrbot/cmd_config.json server/hermes/config.yaml; do
        restore_file "$conf"
    done

    echo -e "    ${GREEN}✓${NC} Backups saved to $(basename "$BACKUP_DIR")/"
else
    echo -e "${YELLOW}[3/5] Config files: none in archive${NC}"
fi

# ------------------------------------------------------------------
# 6. Restore skills
# ------------------------------------------------------------------
if [ -d "$EXTRACT_DIR/skills" ]; then
    echo -e "${YELLOW}[4/5] Restoring custom skills...${NC}"

    # Backup existing skills
    if [ -d "$SCRIPT_DIR/skills" ] && [ "$(ls -A "$SCRIPT_DIR/skills" 2>/dev/null)" ]; then
        cp -r "$SCRIPT_DIR/skills" "$BACKUP_DIR/skills"
    fi

    rm -rf "$SCRIPT_DIR/skills"
    cp -r "$EXTRACT_DIR/skills" "$SCRIPT_DIR/skills"
    SKILL_COUNT=$(find "$SCRIPT_DIR/skills" -name "SKILL.md" | wc -l)
    echo -e "    ${GREEN}✓${NC} $SKILL_COUNT skill(s) restored"
else
    echo -e "${YELLOW}[4/5] Skills: none in archive${NC}"
fi

# ------------------------------------------------------------------
# 7. Summary
# ------------------------------------------------------------------
echo -e "${YELLOW}[5/5] Restore complete${NC}"
echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Restore complete${NC}"
echo -e "${GREEN}============================================${NC}"
echo
echo -e "  Previous files backed up to: ${BLUE}$(basename "$BACKUP_DIR")/${NC}"
echo

if [ -f "$SCRIPT_DIR/.env.restored" ]; then
    echo -e "  ${YELLOW}⚠  .env.restored needs manual review:${NC}"
    echo -e "     diff .env .env.restored"
    echo -e "     # Merge API keys and tokens, then:"
    echo -e "     mv .env.restored .env"
    echo
fi

echo -e "  Next steps:"
echo -e "    1. Review restored configs"
echo -e "    2. If .env was updated, reload: source .env"
echo -e "    3. Start services:  docker compose up -d"
echo -e "    4. Or rebuild:      docker compose up -d --build"
echo
