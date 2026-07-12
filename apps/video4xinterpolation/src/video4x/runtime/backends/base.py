"""Backend base types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass
class BackendConfig:
    onnx_paths: dict[str, Path] = field(default_factory=dict)
    # None → filled from platform defaults at engine/config layer
    ep_preference: list[str] = field(default_factory=list)
    platform: str | None = None  # auto|windows|wsl|linux
    fp16: bool = False
    stage_split_idx: int = 1
    uvm_zero_copy: bool = False  # legacy alias; prefer memory_mode=shared
    memory_mode: str = "auto"  # auto|host|pinned|shared
    # None → enable when memory_mode resolves to shared; True/False force on/off
    use_iobinding: bool | None = None
    vai_config: str | None = None
    cache_dir: Path = field(default_factory=lambda: Path("./vitisai_cache"))


@dataclass
class BackendStats:
    total_calls: int = 0
    total_ms: float = 0.0
    stage_a_ms: float = 0.0
    stage_b_ms: float = 0.0
    npu_hits: int = 0
    gpu_hits: int = 0
    fallback_reason: str | None = None
    # Optional EP map filled by backends, e.g. {"stage_a": "Dml...", "stage_b": "VitisAI..."}
    providers: dict[str, str] = field(default_factory=dict)
    memory_mode: str = "host"
    memory_detail: str = ""
    use_iobinding: bool = False


@runtime_checkable
class InterpolationBackend(Protocol):
    name: str
    supports_npu: bool
    supports_gpu: bool
    device_hint: str

    def init(self, cfg: BackendConfig) -> None: ...
    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray: ...
    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None: ...
    def teardown(self) -> None: ...
    def stats(self) -> BackendStats: ...
