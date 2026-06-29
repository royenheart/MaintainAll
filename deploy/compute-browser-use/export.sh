#!/usr/bin/env bash
set -eo pipefail

# =============================================================
# Remote Computer Use — Data Export
# =============================================================
#
# Exports all deploy data into a timestamped archive:
#   - Docker volumes (astrbot_data, hermes_data)
#   - Configuration files (.env, server configs)
#   - Custom skills
#
# Output: export-cua-YYYYMMDD-HHMMSS.tar.gz
#
# Usage:
#   ./export.sh                    # Export all data
#   ./export.sh --no-volumes       # Skip Docker volumes
#   ./export.sh --output /tmp/cua  # Custom output directory
#   ./export.sh --client           # Export client config too (run on Windows)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR}"
ARCHIVE_NAME="export-cua-${TIMESTAMP}.tar.gz"
TEMP_DIR=$(mktemp -d -t cua-export-XXXXXX)
SKIP_VOLUMES=false
EXPORT_CLIENT=false

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-volumes) SKIP_VOLUMES=true; shift ;;
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --client) EXPORT_CLIENT=true; shift ;;
        --help|-h)
            echo "Usage: $0 [--no-volumes] [--output DIR] [--client]"
            exit 0
            ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

cleanup() { rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

mkdir -p "$TEMP_DIR/data"
EXPORT_DATA="$TEMP_DIR/data"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  CUA Deploy — Data Export${NC}"
echo -e "${GREEN}============================================${NC}"
echo

# ------------------------------------------------------------------
# 1. Export Docker volumes
# ------------------------------------------------------------------
export_docker_volume() {
    local volume=$1
    local output_file="$EXPORT_DATA/volumes/${volume}.tar.gz"

    mkdir -p "$(dirname "$output_file")"

    if docker volume inspect "$volume" >/dev/null 2>&1; then
        echo -e "${YELLOW}  Exporting Docker volume: $volume${NC}"
        docker run --rm \
            -v "${volume}:/volume:ro" \
            alpine \
            tar czf - -C /volume . > "$output_file" 2>/dev/null && \
            echo -e "    ${GREEN}✓${NC} $volume ($(du -h "$output_file" | cut -f1))" || \
            echo -e "    ${RED}✗${NC} $volume export failed (may be empty)"
    else
        echo -e "    ${YELLOW}⊘${NC} Volume $volume not found — skipping"
    fi
}

if $SKIP_VOLUMES; then
    echo -e "${YELLOW}[1/4] Docker volumes: SKIPPED (--no-volumes)${NC}"
else
    echo -e "${YELLOW}[1/4] Exporting Docker volumes...${NC}"
    # Try both compose project names (default and test)
    for volume in cua-astrbot_data astrbot_data \
                  compute-browser-use_astrbot_data \
                  cua-hermes_data hermes_data \
                  compute-browser-use_hermes_data; do
        export_docker_volume "$volume"
    done
fi

# ------------------------------------------------------------------
# 2. Configuration files
# ------------------------------------------------------------------
echo -e "${YELLOW}[2/4] Collecting configuration files...${NC}"

mkdir -p "$EXPORT_DATA/configs"

# .env (if exists, mask secrets for safety report)
if [ -f .env ]; then
    cp .env "$EXPORT_DATA/configs/"
    echo -e "    ${GREEN}✓${NC} .env"
else
    echo -e "    ${YELLOW}⊘${NC} .env not found"
fi

# Server configs
# Note: astrbot's cmd_config.json is stored in the astrbot_data Docker volume
# and is already included in the volume export above.
for conf in server/hermes/config.yaml; do
    if [ -f "$conf" ]; then
        mkdir -p "$EXPORT_DATA/configs/$(dirname "$conf")"
        cp "$conf" "$EXPORT_DATA/configs/$conf"
        echo -e "    ${GREEN}✓${NC} $conf"
    fi
done

# ------------------------------------------------------------------
# 3. Skills
# ------------------------------------------------------------------
echo -e "${YELLOW}[3/4] Collecting custom skills...${NC}"

if [ -d skills ] && [ "$(ls -A skills 2>/dev/null)" ]; then
    mkdir -p "$EXPORT_DATA/skills"
    cp -r skills/* "$EXPORT_DATA/skills/"
    SKILL_COUNT=$(find "$EXPORT_DATA/skills" -name "SKILL.md" | wc -l)
    echo -e "    ${GREEN}✓${NC} $SKILL_COUNT skill(s)"
else
    echo -e "    ${YELLOW}⊘${NC} No custom skills found"
fi

# ------------------------------------------------------------------
# 4. Client config (Windows only)
# ------------------------------------------------------------------
if $EXPORT_CLIENT; then
    echo -e "${YELLOW}[4/4] Exporting client configuration...${NC}"
    CLIENT_CONFIG=""
    if [ -n "$APPDATA" ]; then
        CLIENT_CONFIG="$APPDATA/cua-control-plane/config.json"
    elif [ -f "$HOME/.config/cua-control-plane/config.json" ]; then
        CLIENT_CONFIG="$HOME/.config/cua-control-plane/config.json"
    fi

    if [ -n "$CLIENT_CONFIG" ] && [ -f "$CLIENT_CONFIG" ]; then
        mkdir -p "$EXPORT_DATA/client"
        cp "$CLIENT_CONFIG" "$EXPORT_DATA/client/"
        echo -e "    ${GREEN}✓${NC} Client config from $(dirname "$CLIENT_CONFIG")"
    else
        echo -e "    ${YELLOW}⊘${NC} Client config not found"
    fi
else
    echo -e "${YELLOW}[4/4] Client config: SKIPPED (use --client to include)${NC}"
fi

# ------------------------------------------------------------------
# 5. Generate manifest
# ------------------------------------------------------------------
cat > "$EXPORT_DATA/manifest.json" << EOFMAN
{
    "export_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "version": "1.0",
    "contents": {
        "volumes": $(if $SKIP_VOLUMES; then echo "false"; else echo "true"; fi),
        "configs": true,
        "skills": $([ -d "$EXPORT_DATA/skills" ] && echo "true" || echo "false"),
        "client": $EXPORT_CLIENT
    }
}
EOFMAN

# ------------------------------------------------------------------
# 6. Create archive
# ------------------------------------------------------------------
ARCHIVE_PATH="$OUTPUT_DIR/$ARCHIVE_NAME"
tar czf "$ARCHIVE_PATH" -C "$TEMP_DIR" data

SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)

echo
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Export complete${NC}"
echo -e "${GREEN}============================================${NC}"
echo
echo -e "  Archive: ${GREEN}$ARCHIVE_PATH${NC}"
echo -e "  Size:    $SIZE"
echo
echo -e "  Transfer to target server:"
echo -e "    scp $ARCHIVE_NAME user@target-server:/path/to/deploy/"
echo
echo -e "  On target server, restore with:"
echo -e "    ./restore.sh $ARCHIVE_NAME"
echo
