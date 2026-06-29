#!/usr/bin/env bash
set -eo pipefail

# =============================================================
# CUA Control Plane — Test Runner
# =============================================================
#
# Runs all test layers:
#   Layer 1: Unit tests (fast, no dependencies)
#   Layer 2: Integration tests (requires mock client)
#   Layer 3: E2E tests (requires CUA + real tools)
#
# Usage:
#   ./run_tests.sh              # Run Layer 1 only (always safe)
#   ./run_tests.sh --layer 1    # Unit tests
#   ./run_tests.sh --layer 2    # Unit + Integration
#   ./run_tests.sh --layer 3    # Unit + Integration + E2E
#   ./run_tests.sh --layer 1 --quick  # Fast subset of Layer 1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIENT_DIR="$SCRIPT_DIR/client"
TESTS_DIR="$CLIENT_DIR/tests"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

LAYER=${LAYER:-1}
QUICK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --layer) LAYER="$2"; shift 2 ;;
        --quick) QUICK=true; shift ;;
        --help|-h)
            echo "Usage: $0 [--layer 1|2|3] [--quick]"
            echo "  --layer 1  Unit tests only (default)"
            echo "  --layer 2  Unit + Integration tests"
            echo "  --layer 3  Unit + Integration + E2E tests"
            echo "  --quick    Run fast subset of tests"
            exit 0
            ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  CUA Control Plane — Test Suite${NC}"
echo -e "${GREEN}  Layer: $LAYER${NC}"
echo -e "${GREEN}============================================${NC}"
echo

# Check Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3 not found${NC}"
    exit 1
fi

# Install test deps if needed
echo -e "${YELLOW}Checking test dependencies...${NC}"
pip install -q pytest pytest-asyncio httpx fastapi 2>/dev/null || true
echo

PYTEST_ARGS="-v --tb=short"
if $QUICK; then
    PYTEST_ARGS="$PYTEST_ARGS -x"
fi

# ------------------------------------------------------------------
# Layer 1: Unit Tests
# ------------------------------------------------------------------
run_layer1() {
    echo -e "${BLUE}━━━ Layer 1: Unit Tests ━━━${NC}"
    cd "$CLIENT_DIR"
    PYTHONPATH="$CLIENT_DIR:${PYTHONPATH:-}" python3 -m pytest \
        $PYTEST_ARGS \
        "$TESTS_DIR/test_permissions.py" \
        "$TESTS_DIR/test_config.py" \
        "$TESTS_DIR/test_deterministic_ops.py" \
        "$TESTS_DIR/test_api.py" \
        -k "not e2e" \
         \
        "$@" 2>&1 || {
        echo -e "${RED}✗ Layer 1 failed${NC}"
        return 1
    }
    echo -e "${GREEN}✓ Layer 1 passed${NC}"
}

# ------------------------------------------------------------------
# Layer 2: Integration Tests (needs mock client)
# ------------------------------------------------------------------
run_layer2() {
    echo -e "${BLUE}━━━ Layer 2: Integration Tests ━━━${NC}"

    MOCK_PORT=19110
    MOCK_PID=""

    # Check if mock client is already running (from docker-compose or standalone)
    if curl -s "http://127.0.0.1:$MOCK_PORT/health" >/dev/null 2>&1; then
        echo -e "${GREEN}  Mock client already running on port $MOCK_PORT${NC}"
    else
        echo -e "${YELLOW}  Starting mock client on port $MOCK_PORT...${NC}"
        cd "$TESTS_DIR"
        python3 mock_client.py --port "$MOCK_PORT" &
        MOCK_PID=$!
        sleep 2

        # Verify it started
        for i in $(seq 1 10); do
            if curl -s "http://127.0.0.1:$MOCK_PORT/health" >/dev/null 2>&1; then
                echo -e "${GREEN}  Mock client ready${NC}"
                break
            fi
            sleep 1
        done
    fi

    cd "$CLIENT_DIR"
    CUACTL_ENDPOINT="http://127.0.0.1:$MOCK_PORT" \
    CUACTL_TOKEN="test-mock-token" \
    PYTHONPATH="$CLIENT_DIR:${PYTHONPATH:-}" \
        python3 -m pytest \
        $PYTEST_ARGS \
        "$TESTS_DIR/test_integration.py" \
         \
        "$@" 2>&1 || {
        LAYER2_EXIT=$?
        # Cleanup mock if we started it
        if [ -n "$MOCK_PID" ]; then
            kill "$MOCK_PID" 2>/dev/null || true
        fi
        echo -e "${RED}✗ Layer 2 failed${NC}"
        return $LAYER2_EXIT
    }

    # Cleanup mock if we started it
    if [ -n "$MOCK_PID" ]; then
        kill "$MOCK_PID" 2>/dev/null || true
    fi
    echo -e "${GREEN}✓ Layer 2 passed${NC}"
}

# ------------------------------------------------------------------
# Layer 3: E2E Tests (needs CUA + real control plane)
# ------------------------------------------------------------------
run_layer3() {
    echo -e "${BLUE}━━━ Layer 3: E2E Tests ━━━${NC}"

    # Check if control plane is running
    API_PORT="${CUA_API_PORT:-9110}"
    if ! curl -s "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
        echo -e "${YELLOW}  Control Plane not running on port $API_PORT${NC}"
        echo -e "${YELLOW}  Start it with: python -m cua_control_plane.main${NC}"
        echo -e "${YELLOW}  Skipping E2E tests${NC}"
        return 0
    fi

    # Check for wmctrl (needed for deterministic ops on Linux)
    if [[ "$(uname -s)" != "MINGW"* && "$(uname -s)" != "MSYS"* ]]; then
        if ! command -v wmctrl &>/dev/null; then
            echo -e "${YELLOW}  wmctrl not installed. Install: sudo apt install wmctrl${NC}"
            echo -e "${YELLOW}  Some E2E tests will be skipped${NC}"
        fi
    fi

    # Get token from config
    API_TOKEN=""
    if [ -f "$HOME/.config/cua-control-plane/config.json" ]; then
        API_TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.config/cua-control-plane/config.json')).get('local_token',''))" 2>/dev/null || echo "")
    elif [ -f "$APPDATA/cua-control-plane/config.json" ]; then
        API_TOKEN=$(python3 -c "import json; print(json.load(open('$APPDATA/cua-control-plane/config.json')).get('local_token',''))" 2>/dev/null || echo "")
    fi

    cd "$CLIENT_DIR"
    CUA_API_URL="http://127.0.0.1:$API_PORT" \
    CUA_API_TOKEN="$API_TOKEN" \
    PYTHONPATH="$CLIENT_DIR:${PYTHONPATH:-}" \
        python3 -m pytest \
        $PYTEST_ARGS \
        "$TESTS_DIR/test_e2e.py" \
        -m e2e \
         \
        "$@" 2>&1 || {
        echo -e "${RED}✗ Layer 3 failed${NC}"
        return 1
    }
    echo -e "${GREEN}✓ Layer 3 passed${NC}"
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
EXIT_CODE=0

run_layer1 || EXIT_CODE=1

if [ "$LAYER" -ge 2 ]; then
    run_layer2 || EXIT_CODE=1
fi

if [ "$LAYER" -ge 3 ]; then
    run_layer3 || EXIT_CODE=1
fi

echo
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}============================================${NC}"
    echo -e "${GREEN}  All tests passed ✓${NC}"
    echo -e "${GREEN}============================================${NC}"
else
    echo -e "${RED}============================================${NC}"
    echo -e "${RED}  Some tests failed ✗${NC}"
    echo -e "${RED}============================================${NC}"
fi
exit $EXIT_CODE
