"""Inference configuration and mode enumeration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from video4x.runtime.backends.base import BackendConfig
from video4x.runtime.paths import default_onnx_paths
from video4x.runtime.platform import default_ep_preference, resolve_platform


class InferenceMode(str, Enum):
    """Registered inference backends (maps 1:1 to runtime backend names)."""

    CPU_BASELINE = "cpu-baseline"
    SINGLE_EP = "single-ep"
    SPLIT_PIPELINE = "split-pipeline"
    DUAL_STREAM = "dual-stream"

    @classmethod
    def from_str(cls, name: str) -> InferenceMode:
        normalized = name.strip().lower()
        for mode in cls:
            if mode.value == normalized:
                return mode
        raise ValueError(f"Unknown inference mode '{name}'. Valid: {[m.value for m in cls]}")


@dataclass
class InferenceConfig:
    """Upper-layer config; translated to BackendConfig for the runtime layer."""

    mode: str | InferenceMode = InferenceMode.SPLIT_PIPELINE
    onnx_dir: Path = field(default_factory=lambda: Path("models/onnx"))
    fp16: bool = False
    # Empty → platform defaults (Windows: dml,vitisai,cpu / WSL: rocm,vitisai,cpu)
    ep_preference: list[str] = field(default_factory=list)
    platform: str = "auto"
    uvm_zero_copy: bool = False
    memory_mode: str = "auto"  # auto|host|pinned|shared
    vai_config: str | None = None
    cache_dir: Path = field(default_factory=lambda: Path("./vitisai_cache"))

    def __post_init__(self) -> None:
        if isinstance(self.mode, InferenceMode):
            self.mode = self.mode.value
        self.onnx_dir = Path(self.onnx_dir)
        self.cache_dir = Path(self.cache_dir)
        plat = resolve_platform(self.platform)
        self.platform = plat.value
        if not self.ep_preference:
            self.ep_preference = default_ep_preference(plat)
        if self.uvm_zero_copy and self.memory_mode in ("", "auto", "host"):
            self.memory_mode = "shared"

    @property
    def mode_enum(self) -> InferenceMode:
        return InferenceMode.from_str(str(self.mode))

    def to_backend_config(self) -> BackendConfig:
        return BackendConfig(
            onnx_paths=default_onnx_paths(self.onnx_dir),
            ep_preference=list(self.ep_preference),
            platform=self.platform,
            fp16=self.fp16,
            uvm_zero_copy=self.uvm_zero_copy,
            memory_mode=self.memory_mode,
            vai_config=self.vai_config,
            cache_dir=self.cache_dir,
        )
