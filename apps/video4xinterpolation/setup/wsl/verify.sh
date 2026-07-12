#!/usr/bin/env bash
# WSL 轻量自检（缺失不失败，只汇总 WARN）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FAIL=0

warn() { echo "[WARN] $*"; FAIL=$((FAIL + 1)); }
ok()   { echo "[OK]   $*"; }
info() { echo "[INFO] $*"; }

cd "${PROJECT_ROOT}"
# shellcheck disable=SC1091
[[ -f "${SCRIPT_DIR}/rocm-wsl.env" ]] && source "${SCRIPT_DIR}/rocm-wsl.env" 2>/dev/null || true

echo "=== verify (WSL) ==="

if python3 -c "import numpy, av, onnxruntime as ort; print('ORT', ort.__version__, ort.get_available_providers())" 2>/dev/null; then
  ok "python + onnxruntime"
else
  warn "python runtime (activate .venv?)"
fi

if command -v rocminfo >/dev/null 2>&1; then
  if rocminfo 2>/dev/null | grep -q "Device Type:.*GPU"; then
    ok "rocminfo GPU agent"
  else
    warn "rocminfo: no GPU agent (setup/wsl/windows-host.ps1 + rocm-install.sh + source rocm-wsl.env)"
  fi
else
  warn "rocminfo not found"
fi

[[ -e /dev/dxg ]] && ok "/dev/dxg (WSL DXCore)" || info "/dev/dxg missing"

if python3 -c "import onnxruntime as ort; raise SystemExit(0 if 'ROCMExecutionProvider' in ort.get_available_providers() else 1)" 2>/dev/null; then
  ok "ROCMExecutionProvider listed"
else
  warn "ROCMExecutionProvider not in ORT (pip install onnxruntime-rocm)"
fi

# TODO(WSL): XDNA usually not passed through — expect WARN
if [[ -e /dev/accel/accel0 ]]; then
  ok "/dev/accel/accel0 (NPU device node)"
else
  warn "/dev/accel/accel0 missing — WSL2 通常不透传 XDNA；Stage B 走 CPU"
fi

if python3 -c "import onnxruntime as ort; raise SystemExit(0 if 'VitisAIExecutionProvider' in ort.get_available_providers() else 1)" 2>/dev/null; then
  ok "VitisAIExecutionProvider listed"
else
  warn "VitisAIExecutionProvider missing (WSL NPU incomplete; set VAI_RT_WHEEL if bare-metal)"
fi

[[ "${FAIL}" -gt 0 ]] && echo "Verify: ${FAIL} warning(s)."
exit 0
