"""RIFE video interpolation pipeline (delegates to inference layer)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from rife_amd.inference.comparator import CompareResult, InferenceComparator
from rife_amd.inference.config import InferenceConfig
from rife_amd.inference.engine import RifeInferenceEngine
from rife_amd.runtime.backends.base import BackendConfig, InterpolationBackend
from rife_amd.runtime.paths import default_onnx_paths


@dataclass
class PipelineResult:
    output_frames: int
    backend_name: str
    stats: dict


def run_interpolation(
    backend_name: str,
    frames: list[np.ndarray],
    cfg: BackendConfig | None = None,
    multiplier: int = 2,
) -> tuple[list[np.ndarray], InterpolationBackend]:
    """Interpolate between consecutive frames; multiplier=2 inserts one mid-frame."""
    inf_cfg = _backend_to_inference_cfg(backend_name, cfg)
    engine = RifeInferenceEngine(inf_cfg)
    engine.switch_mode(backend_name)
    out = engine.interpolate_frames(frames, multiplier=multiplier)
    backend = engine._backend
    if backend is None:
        raise RuntimeError("Backend not initialized after interpolation")
    return out, backend


def run_video(
    input_path: Path,
    output_path: Path,
    backend_name: str,
    cfg: BackendConfig | None = None,
    fps: float = 30.0,
) -> PipelineResult:
    inf_cfg = _backend_to_inference_cfg(backend_name, cfg)
    with RifeInferenceEngine(inf_cfg) as engine:
        result = engine.interpolate_video(input_path, output_path, fps=fps)
    return PipelineResult(
        output_frames=result.output_frames,
        backend_name=result.mode,
        stats=result.stats,
    )


def compare_backends(
    frames: list[np.ndarray],
    backend_names: Iterable[str],
    cfg: BackendConfig | None = None,
) -> list[dict]:
    inf_cfg = _backend_to_inference_cfg("cpu-baseline", cfg)
    base = InferenceConfig(
        onnx_dir=inf_cfg.onnx_dir,
        fp16=inf_cfg.fp16,
        ep_preference=inf_cfg.ep_preference,
        platform=inf_cfg.platform,
        uvm_zero_copy=inf_cfg.uvm_zero_copy,
        memory_mode=inf_cfg.memory_mode,
        vai_config=inf_cfg.vai_config,
        cache_dir=inf_cfg.cache_dir,
    )
    comp = InferenceComparator(base)
    results = comp.compare_on_frames(frames, modes=backend_names)
    return [_compare_result_to_dict(r) for r in results]


def _backend_to_inference_cfg(backend_name: str, cfg: BackendConfig | None) -> InferenceConfig:
    if cfg is None:
        return InferenceConfig(mode=backend_name)
    onnx_dir = next(iter(cfg.onnx_paths.values())).parent if cfg.onnx_paths else Path("models/onnx")
    return InferenceConfig(
        mode=backend_name,
        onnx_dir=onnx_dir,
        fp16=cfg.fp16,
        ep_preference=list(cfg.ep_preference),
        platform=cfg.platform or "auto",
        uvm_zero_copy=cfg.uvm_zero_copy,
        memory_mode=cfg.memory_mode,
        vai_config=cfg.vai_config,
        cache_dir=cfg.cache_dir,
    )


def _compare_result_to_dict(r: CompareResult) -> dict:
    if r.error:
        return {"backend": r.mode, "error": r.error}
    return {
        "backend": r.mode,
        "elapsed_ms": r.elapsed_ms,
        "device_hint": r.device_hint,
        "stats": r.stats,
    }
