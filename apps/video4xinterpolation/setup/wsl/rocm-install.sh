#!/usr/bin/env bash
# WSL2 GPU：ROCm 7.2.3 + librocdxg
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROCM_APT_VER="${ROCM_APT_VER:-7.2.3}"

_is_wsl() { grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; }

_detect_apt_suite() {
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID}:${VERSION_CODENAME}" in
    ubuntu:noble|debian:trixie|debian:sid) echo noble ;;
    *) echo jammy ;;
  esac
}

_find_win_sdk() {
  local base="/mnt/c/Program Files (x86)/Windows Kits/10/Include"
  [[ -d "${base}" ]] || return 1
  ls -1d "${base}/"* 2>/dev/null | sort -V | tail -1
}

# amdgpu-install / --accept-eula 会留下 404 源 amdgpu/7.2.3/ubuntu（见 ROCm#5881）
_fix_apt_sources() {
  local suite="$1"
  local keyring="/etc/apt/keyrings/rocm.gpg"
  sudo mkdir -p /etc/apt/keyrings
  if [[ ! -f "${keyring}" ]]; then
    wget -q -O - "https://repo.radeon.com/rocm/rocm.gpg.key" \
      | gpg --dearmor | sudo tee "${keyring}" >/dev/null
  fi
  # 必须删掉：这是 404 的直接来源
  sudo rm -f /etc/apt/sources.list.d/amdgpu-proprietary.list
  sudo rm -f /etc/apt/sources.list.d/amdgpu.list.dpkg-old
  sudo rm -f /etc/apt/sources.list.d/archive_uri-*repo_radeon_com*.list 2>/dev/null || true
  sudo tee /etc/apt/sources.list.d/rocm.list >/dev/null <<EOF
deb [arch=amd64 signed-by=${keyring}] https://repo.radeon.com/rocm/apt/${ROCM_APT_VER} ${suite} main
deb [arch=amd64 signed-by=${keyring}] https://repo.radeon.com/graphics/${ROCM_APT_VER}/ubuntu ${suite} main
EOF
  sudo tee /etc/apt/sources.list.d/amdgpu.list >/dev/null <<EOF
deb [arch=amd64 signed-by=${keyring}] https://repo.radeon.com/amdgpu/latest/ubuntu ${suite} main
EOF
  sudo find /etc/apt/sources.list.d -maxdepth 1 -name '*.list' -exec \
    sed -i \
      -e '/repo\.radeon\.com\/amdgpu\/6\./d' \
      -e '/repo\.radeon\.com\/amdgpu\/7\.2\.3\/ubuntu/d' \
      -e '/repo\.radeon\.com\/amdgpu\/7\.2\/ubuntu/d' \
      -e '/repo\.radeon\.com\/amdgpu\/30\./d' \
      {} + 2>/dev/null || true
  echo "apt sources fixed (suite=${suite}, rocm=${ROCM_APT_VER})"
}

_install_rocm() {
  local suite="$1" deb_file="/tmp/amdgpu-install.deb"
  local deb_url="https://repo.radeon.com/amdgpu-install/${ROCM_APT_VER}/ubuntu/${suite}/amdgpu-install_${ROCM_APT_VER}.70203-1_all.deb"
  wget -q --spider "${deb_url}" 2>/dev/null || \
    deb_url="https://repo.radeon.com/amdgpu-install/7.2/ubuntu/${suite}/amdgpu-install_7.2.70200-1_all.deb"

  echo "== amdgpu-install deb =="
  wget -O "${deb_file}" "${deb_url}"
  export DEBIAN_FRONTEND=noninteractive
  sudo apt-get install -y -o Dpkg::Options::="--force-confnew" "${deb_file}"

  echo "== fix apt sources (7.2.3 amdgpu/7.2.x/ubuntu → 404) =="
  _fix_apt_sources "${suite}"
  sudo apt-get update

  echo "== ROCm packages =="
  # 不要用 --accept-eula（会重建 amdgpu-proprietary.list → 404）
  sudo amdgpu-install -y --usecase=rocm --no-dkms 2>/dev/null \
    || sudo amdgpu-install -y --usecase=rocm --no-dkms
  _fix_apt_sources "${suite}"
  sudo apt-get update
}

_build_librocdxg() {
  local win_sdk="$1" build_dir="${HOME}/.cache/librocdxg-build"
  rm -rf "${build_dir}"
  git clone --depth 1 --branch develop https://github.com/ROCm/librocdxg.git "${build_dir}/src"
  cmake -S "${build_dir}/src" -B "${build_dir}/build" -DWIN_SDK="${win_sdk}/shared"
  cmake --build "${build_dir}/build" -j"$(nproc)"
  sudo cmake --install "${build_dir}/build"
}

_write_env() {
  local rocm_lib="/opt/rocm/lib"
  for d in /opt/rocm-7.2.3/lib /opt/rocm-7.2.0/lib /opt/rocm/lib; do
    [[ -d "${d}" ]] && rocm_lib="${d}" && break
  done
  cat >"${SCRIPT_DIR}/rocm-wsl.env" <<EOF
export HSA_ENABLE_DXG_DETECTION=1
export LD_LIBRARY_PATH=${rocm_lib}:\${LD_LIBRARY_PATH:-}
export PATH=/opt/rocm/bin:\${PATH}
EOF
}

main() {
  local suite
  suite="$(_detect_apt_suite)"

  if [[ "${1:-}" == "--fix-apt-only" ]]; then
    _fix_apt_sources "${suite}"
    sudo apt-get update
    exit 0
  fi

  _is_wsl || { echo "ERROR: WSL2 only." >&2; exit 1; }
  local win_sdk
  win_sdk="$(_find_win_sdk)" || { echo "ERROR: Windows SDK not found." >&2; exit 1; }
  echo "NOTE: apt suite=${suite} (ROCm ${ROCM_APT_VER})"
  _fix_apt_sources "${suite}"
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends \
    cmake gcc g++ git make libatomic1 libquadmath0 pkg-config wget gpg
  _install_rocm "${suite}"
  echo "== librocdxg ==" && _build_librocdxg "${win_sdk}"
  _write_env
  sudo usermod -aG render,video "$USER" 2>/dev/null || true
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/rocm-wsl.env"
  rocminfo 2>/dev/null | grep -q "Device Type:.*GPU" \
    && echo "OK: GPU agent in rocminfo" \
    || echo "WARN: no GPU agent — wsl --shutdown on Windows, then: source setup/wsl/rocm-wsl.env"
}

main "$@"
