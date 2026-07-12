"""Host / shared / pinned memory detection and buffer planning."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

from video4x.runtime.memory.types import MemoryMode, MemoryProfile, parse_memory_mode

__all__ = [
    "MemoryMode",
    "MemoryProfile",
    "MemoryPlanner",
    "create_memory_planner",
    "parse_memory_mode",
]


@runtime_checkable
class MemoryPlanner(Protocol):
    def profile(self) -> MemoryProfile: ...
    def resolve_mode(self, requested: str | MemoryMode = MemoryMode.AUTO) -> MemoryMode: ...
    def allocate(self, shape: tuple[int, ...], *, dtype=np.float32) -> np.ndarray: ...
    def ensure(self, arr: np.ndarray) -> np.ndarray: ...
    def close(self) -> None: ...

    @property
    def mode(self) -> MemoryMode: ...


def create_memory_planner(platform: str | None = None) -> MemoryPlanner:
    from video4x.runtime.platform import HostPlatform, resolve_platform

    plat = resolve_platform(platform)
    if plat == HostPlatform.WINDOWS:
        from video4x.runtime.memory.windows import WindowsMemoryPlanner

        return WindowsMemoryPlanner()
    from video4x.runtime.memory.posix import PosixMemoryPlanner

    return PosixMemoryPlanner(wsl=(plat == HostPlatform.WSL))
