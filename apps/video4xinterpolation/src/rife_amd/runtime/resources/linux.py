"""Linux / WSL resource sampler (process CPU/RSS; GPU via rocm-smi when present)."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any

from rife_amd.runtime.resources.base import ResourceSample


class LinuxResourceSampler:
    """Sample this process on Linux/WSL.

    NPU utilization is reserved (usually unavailable under WSL2).
    GPU uses ``rocm-smi`` when on PATH (system-wide GPU busy %, not always per-PID).
    """

    def __init__(self, wsl: bool = False, min_interval_s: float = 0.75) -> None:
        self._wsl = wsl
        self._min_interval = min_interval_s
        self._last_t = 0.0
        self._cached = ResourceSample(detail="linux:init")
        self._proc: Any = None
        try:
            import psutil

            self._proc = psutil.Process()
            self._proc.cpu_percent(None)
        except Exception:
            self._proc = None

    def sample(self) -> ResourceSample:
        now = time.perf_counter()
        if now - self._last_t < self._min_interval and self._last_t > 0:
            return self._cached
        self._last_t = now

        cpu = mem = None
        detail = ["wsl" if self._wsl else "linux"]
        if self._proc is not None:
            try:
                cpu = float(self._proc.cpu_percent(None))
                mem = float(self._proc.memory_info().rss) / (1024 * 1024)
            except Exception:
                detail.append("psutil_fail")
        else:
            detail.append("no_psutil")

        gpu = _rocm_gpu_busy()
        if gpu is None:
            detail.append("no_rocm_smi")
        npu = None
        if self._wsl:
            detail.append("npu_unsupported")

        self._cached = ResourceSample(
            cpu_percent=cpu,
            gpu_percent=gpu,
            npu_percent=npu,
            mem_rss_mb=mem,
            detail="+".join(detail),
        )
        return self._cached

    def close(self) -> None:
        self._proc = None


def _rocm_gpu_busy() -> float | None:
    if not shutil.which("rocm-smi"):
        return None
    try:
        proc = subprocess.run(
            ["rocm-smi", "--showuse", "--csv"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # CSV varies by version; take first percentage-looking token after header.
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    for ln in lines[1:]:
        for part in ln.replace("%", "").split(","):
            part = part.strip()
            try:
                return float(part)
            except ValueError:
                continue
    return None
