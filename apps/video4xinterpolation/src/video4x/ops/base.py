"""Operator protocol shared by interpolate / super-resolve."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np


@dataclass
class OperatorStats:
    name: str = ""
    total_calls: int = 0
    total_ms: float = 0.0
    gpu_hits: int = 0
    npu_hits: int = 0
    providers: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class FrameOperator(Protocol):
    """Process one or more RGB float32 NCHW [0,1] frames."""

    name: str

    def init(self, **kwargs: Any) -> None: ...

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """Single-frame ops (e.g. super-resolve)."""
        ...

    def process_pair(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        *,
        timestep: float = 0.5,
    ) -> np.ndarray:
        """Pair ops (e.g. interpolate mid-frame). Default: not supported."""
        ...

    def stats(self) -> OperatorStats: ...

    def close(self) -> None: ...


@dataclass
class OpSpec:
    """Declarative operator selection for a job."""

    op: str  # interpolate | superresolve
    model: str | None = None
    backend: str = "split-pipeline"
    platform: str | None = "auto"
    fp16: bool = False
    memory_mode: str = "auto"
    onnx_dir: Path | None = None
    # Super-resolve extras
    tile: int = 0
    tile_pad: int = 10
    extras: dict[str, Any] = field(default_factory=dict)
