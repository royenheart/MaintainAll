"""Linux / WSL memory profile."""

from __future__ import annotations

from rife_amd.runtime.memory.locking import BaseMemoryPlanner
from rife_amd.runtime.memory.types import MemoryProfile


class PosixMemoryPlanner(BaseMemoryPlanner):
    def __init__(self, wsl: bool = False) -> None:
        super().__init__()
        self._wsl = wsl

    def _detect(self) -> MemoryProfile:
        ram = 0.0
        try:
            import psutil

            ram = float(psutil.virtual_memory().total) / (1024 * 1024)
        except Exception:
            try:
                with open("/proc/meminfo", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            ram = float(line.split()[1]) / 1024.0
                            break
            except OSError:
                pass
        detail = "wsl" if self._wsl else "linux"
        # ROCm discrete GPU VRAM not queried here; shared pool uncommon on dGPU Linux
        return MemoryProfile(
            system_ram_mb=ram,
            gpu_dedicated_mb=None,
            gpu_shared_mb=None,
            unified_apu=False,
            detail=detail,
        )
