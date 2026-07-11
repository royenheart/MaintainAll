"""Shared memory mode / profile types (no planner imports)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MemoryMode(str, Enum):
    """How frame tensors are held before ORT run."""

    AUTO = "auto"
    HOST = "host"  # plain numpy (pageable)
    PINNED = "pinned"  # page-locked host pages (faster DMA to GPU/NPU)
    SHARED = "shared"  # on APU: treat as pinned when GPU shared pool is large


@dataclass(frozen=True)
class MemoryProfile:
    """Detected machine memory configuration (MB)."""

    system_ram_mb: float
    gpu_dedicated_mb: float | None = None
    gpu_shared_mb: float | None = None
    unified_apu: bool = False  # Ryzen AI / iGPU style shared pool
    detail: str = ""

    @property
    def has_large_shared_pool(self) -> bool:
        return bool(self.gpu_shared_mb and self.gpu_shared_mb >= 2048)


def parse_memory_mode(text: str | MemoryMode | None) -> MemoryMode:
    if text is None or text == "":
        return MemoryMode.AUTO
    if isinstance(text, MemoryMode):
        return text
    key = str(text).strip().lower()
    for m in MemoryMode:
        if m.value == key:
            return m
    raise ValueError(f"Unknown memory mode '{text}'. Valid: auto, host, pinned, shared")
