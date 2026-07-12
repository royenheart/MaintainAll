"""Windows memory profile (system RAM + GPU dedicated/shared)."""

from __future__ import annotations

import subprocess

from video4x.runtime.memory.locking import BaseMemoryPlanner
from video4x.runtime.memory.types import MemoryProfile


class WindowsMemoryPlanner(BaseMemoryPlanner):
    def _detect(self) -> MemoryProfile:
        system_ram = _system_ram_mb()
        ded, shared, detail = _gpu_memory_mb()
        # Ryzen AI / 780M: large "shared GPU memory" ≈ unified APU pool with NPU
        unified = bool(shared and shared >= 4096 and (ded is None or ded < shared))
        return MemoryProfile(
            system_ram_mb=system_ram,
            gpu_dedicated_mb=ded,
            gpu_shared_mb=shared,
            unified_apu=unified,
            detail=detail or "windows",
        )


def _system_ram_mb() -> float:
    try:
        import psutil

        return float(psutil.virtual_memory().total) / (1024 * 1024)
    except Exception:
        pass
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return float(stat.ullTotalPhys) / (1024 * 1024)
    except Exception:
        return 0.0


def _gpu_memory_mb() -> tuple[float | None, float | None, str]:
    """Return (dedicated_mb, shared_mb, detail) via CIM / dxdiag-ish WMI."""
    script = r"""
$ded = 0; $shared = 0; $n = 0
try {
  Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.Name -match 'AMD|Radeon|NVIDIA|Intel') {
      $n++
      if ($_.AdapterRAM -and $_.AdapterRAM -gt 0 -and $_.AdapterRAM -lt [uint64]::MaxValue) {
        $ded = [Math]::Max($ded, [double]$_.AdapterRAM / 1MB)
      }
    }
  }
} catch {}
# Shared GPU memory is not always in WMI; approximate from Perf / registry is flaky.
# On Windows Task Manager, Shared GPU Memory ≈ system RAM for APUs.
# Expose a heuristic: if AdapterRAM is small (<2GB) treat most system RAM as shared pool.
Write-Output ("DED={0};N={1}" -f $ded, $n)
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        line = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
    except (OSError, subprocess.TimeoutExpired):
        return None, None, "gpu_probe_fail"

    ded = None
    import re

    m = re.search(r"DED=([0-9.]+);N=(\d+)", line)
    if m:
        ded_v = float(m.group(1))
        if ded_v > 0:
            ded = ded_v
    # Heuristic shared pool for APU: Task Manager "Shared GPU memory" ≈ system RAM
    sys_mb = _system_ram_mb()
    shared = None
    detail = "windows+wmi"
    if ded is not None and ded < 2048 and sys_mb > 8192:
        # iGPU / APU: dedicated small, shared ≈ system RAM (user reported ~14GB+)
        shared = max(0.0, sys_mb - 2048)
        detail = "windows+apu_shared_heuristic"
    elif sys_mb > 0:
        # Still expose a conservative shared estimate
        shared = sys_mb * 0.5
        detail = "windows+shared_estimate"
    return ded, shared, detail
