"""Execution provider detection for AMD GPU / NPU (and Windows DirectML)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import onnxruntime as ort

from rife_amd.runtime.platform import HostPlatform, default_ep_preference, detect_platform


@dataclass(frozen=True)
class EPProbeResult:
    rocm: bool
    directml: bool
    vitisai: bool
    cpu: bool
    providers: tuple[str, ...]
    rocm_gpu_agent: bool
    platform: HostPlatform


def has_rocm_gpu_agent() -> bool:
    """True when rocminfo lists at least one HSA GPU agent (not CPU-only WSL stub)."""
    try:
        proc = subprocess.run(
            ["rocminfo"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0:
        return False
    for line in proc.stdout.splitlines():
        if "Device Type:" in line and "GPU" in line:
            return True
    return False


def probe_execution_providers() -> EPProbeResult:
    providers = tuple(ort.get_available_providers())
    plat = detect_platform()
    rocm_listed = "ROCMExecutionProvider" in providers
    gpu_agent = has_rocm_gpu_agent() if plat != HostPlatform.WINDOWS else False
    # ORT may list ROCM EP while HIP has no device (legacy roc4wsl on 8845H WSL).
    rocm_usable = bool(rocm_listed and gpu_agent)
    return EPProbeResult(
        rocm=rocm_usable,
        directml="DmlExecutionProvider" in providers,
        vitisai="VitisAIExecutionProvider" in providers,
        cpu="CPUExecutionProvider" in providers,
        providers=providers,
        rocm_gpu_agent=gpu_agent,
        platform=plat,
    )


def _vitisai_provider_options(cache_dir: str = "./vitisai_cache") -> dict:
    """Build VitisAI EP options; Hawk Point (PHX/HPT) needs xclbin on Windows."""
    opts: dict = {
        "config_file": "",
        "cache_dir": cache_dir,
        "cache_key": "",
    }
    # Ryzen AI Software sets this; Phoenix/Hawk Point need target=X1 + 4x4.xclbin.
    install = os.environ.get("RYZEN_AI_INSTALLATION_PATH", "")
    if install:
        xclbin = (
            Path(install)
            / "voe-4.0-win_amd64"
            / "xclbins"
            / "phoenix"
            / "4x4.xclbin"
        )
        if xclbin.is_file():
            opts["target"] = "X1"
            opts["xclbin"] = str(xclbin)
            opts["xlnx_enable_py3_round"] = 0
    return opts


def build_provider_list(
    preference: list[str] | None = None,
    fp16: bool = False,
    cache_dir: str = "./vitisai_cache",
) -> list[str | tuple[str, dict]]:
    """Map preference names to ORT provider entries with options."""
    probe = probe_execution_providers()
    pref = preference or default_ep_preference(probe.platform)
    out: list[str | tuple[str, dict]] = []

    for name in pref:
        key = name.lower().replace("_", "").replace("-", "")
        if key in ("rocm",):
            if probe.rocm:
                opts: dict = {}
                if fp16:
                    opts["tunable_op_enable"] = 1
                out.append(("ROCMExecutionProvider", opts) if opts else "ROCMExecutionProvider")
        elif key in ("dml", "directml"):
            if probe.directml:
                out.append("DmlExecutionProvider")
        elif key in ("gpu",):
            # Platform-aware alias: Windows → DML, else ROCm.
            if probe.platform == HostPlatform.WINDOWS and probe.directml:
                out.append("DmlExecutionProvider")
            elif probe.rocm:
                opts = {}
                if fp16:
                    opts["tunable_op_enable"] = 1
                out.append(("ROCMExecutionProvider", opts) if opts else "ROCMExecutionProvider")
        elif key in ("vitisai", "npu", "vai"):
            if probe.vitisai:
                # BLOCKER: VitisAI needs compile cache / xclbin; WSL often has no /dev/accel.
                out.append(("VitisAIExecutionProvider", _vitisai_provider_options(cache_dir)))
        elif key == "cpu":
            if probe.cpu:
                out.append("CPUExecutionProvider")

    if not out and probe.cpu:
        out.append("CPUExecutionProvider")
    return out
