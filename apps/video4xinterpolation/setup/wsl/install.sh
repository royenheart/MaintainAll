#!/usr/bin/env bash
# WSL / Linux 安装入口
#   sudo ./install.sh            # 完整（ROCDXG + Python）
#   sudo ./install.sh --cpu-only # 仅 CPU
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV="${PROJECT_ROOT}/.venv"
CPU_ONLY=false
[[ "${1:-}" == "--cpu-only" ]] && CPU_ONLY=true

_is_wsl() { grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; }

_ensure_venv() {
  local -a args=()
  [[ "${PROJECT_ROOT}" == /mnt/* ]] && args+=(--copies)
  if [[ ! -x "${VENV}/bin/python" ]] || ! "${VENV}/bin/python" -m pip --version >/dev/null 2>&1; then
    rm -rf "${VENV}"
    python3 -m venv "${args[@]}" "${VENV}"
  fi
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  python -m pip install --upgrade pip wheel -q
}

echo "Windows host (WSL GPU passthrough): powershell -ExecutionPolicy Bypass -File setup/wsl/windows-host.ps1"
echo ""

if [[ "${CPU_ONLY}" == false ]] && _is_wsl; then
  bash "${SCRIPT_DIR}/rocm-install.sh" --fix-apt-only
fi

sudo apt-get update
export DEBIAN_FRONTEND=noninteractive
sudo apt-get install -y --no-install-recommends python3 python3-venv python3-pip wget ffmpeg

if [[ "${CPU_ONLY}" == false ]] && _is_wsl; then
  bash "${SCRIPT_DIR}/rocm-install.sh"
fi

_ensure_venv
pip install -e "${PROJECT_ROOT}[export,dev]" -q

if [[ "${CPU_ONLY}" == false ]]; then
  pip install onnxruntime-rocm==1.22.2.post1 -q && pip uninstall -y onnxruntime 2>/dev/null || pip install onnxruntime -q
else
  pip install onnxruntime -q
fi

[[ -n "${VAI_RT_WHEEL:-}" && -f "${VAI_RT_WHEEL}" ]] && pip install "${VAI_RT_WHEEL}" -q
pip install amd-quark 2>/dev/null || true

bash "${SCRIPT_DIR}/verify.sh" || true
echo "Done: source ${VENV}/bin/activate && source ${SCRIPT_DIR}/rocm-wsl.env"
