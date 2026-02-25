#!/bin/bash

if [ -n "${BASH_SOURCE[0]}" ]; then
    SCRIPT_PATH="${BASH_SOURCE[0]}"
elif [ -n "$0" ]; then
    SCRIPT_PATH="$0"
else
    echo "Unable to locate myself"
fi

# get absolute path
if command -v readlink >/dev/null 2>&1 && [ "$(uname)" != "Darwin" ]; then
    SCRIPT_DIR="$(dirname "$(readlink -f "$SCRIPT_PATH")")"
elif command -v realpath >/dev/null 2>&1; then
    SCRIPT_DIR="$(dirname "$(realpath "$SCRIPT_PATH")")"
else
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
fi

echo "myself ${SCRIPT_PATH} at ${SCRIPT_DIR}"