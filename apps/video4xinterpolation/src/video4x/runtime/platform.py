"""Host platform detection for EP defaults (Windows / WSL / Linux)."""

from __future__ import annotations

import os
import platform
from enum import Enum
from functools import lru_cache


class HostPlatform(str, Enum):
    WINDOWS = "windows"
    WSL = "wsl"
    LINUX = "linux"


@lru_cache(maxsize=1)
def detect_platform() -> HostPlatform:
    """Detect runtime host. Cached for process lifetime."""
    system = platform.system().lower()
    if system == "windows":
        return HostPlatform.WINDOWS
    if system == "linux":
        try:
            with open("/proc/version", encoding="utf-8", errors="ignore") as f:
                ver = f.read().lower()
            if "microsoft" in ver or "wsl" in ver:
                return HostPlatform.WSL
        except OSError:
            pass
        if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
            return HostPlatform.WSL
        return HostPlatform.LINUX
    # macOS / other → treat as linux-like for EP defaults (CPU)
    return HostPlatform.LINUX


def resolve_platform(name: str | HostPlatform | None = None) -> HostPlatform:
    """Resolve CLI/config platform override. ``auto`` / None → detect."""
    if name is None or name == "" or str(name).lower() == "auto":
        return detect_platform()
    if isinstance(name, HostPlatform):
        return name
    key = str(name).strip().lower()
    for p in HostPlatform:
        if p.value == key:
            return p
    raise ValueError(f"Unknown platform '{name}'. Valid: auto, windows, wsl, linux")


def default_ep_preference(plat: HostPlatform | None = None) -> list[str]:
    """Default EP preference for single-ep / config."""
    p = plat or detect_platform()
    if p == HostPlatform.WINDOWS:
        # DirectML GPU + VitisAI NPU (system / Ryzen AI ORT); minimal pip deps.
        return ["dml", "vitisai", "cpu"]
    # WSL / Linux: ROCm GPU; VitisAI only if device+wheel present (often missing on WSL).
    return ["rocm", "vitisai", "cpu"]


def default_stage_ep_preferences(
    plat: HostPlatform | None = None,
) -> tuple[list[str], list[str]]:
    """(stage_a_pref, stage_b_pref) for split-pipeline."""
    p = plat or detect_platform()
    if p == HostPlatform.WINDOWS:
        # Stage A: DirectML GPU. Stage B: VitisAI NPU (subprocess-probed; DML/CPU fallback).
        return (["dml", "cpu"], ["vitisai", "dml", "cpu"])
    # TODO(WSL/Linux): NPU passthrough incomplete on WSL2 — Stage B usually CPU.
    return (["rocm", "cpu"], ["vitisai", "cpu"])
