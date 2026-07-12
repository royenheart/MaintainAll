"""Interpolate operator wrapping RifeInferenceEngine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from video4x.inference.config import InferenceConfig
from video4x.inference.engine import RifeInferenceEngine
from video4x.inference.progress import ProgressCallback
from video4x.ops.base import OperatorStats


class InterpolateOperator:
    name = "interpolate"

    def __init__(
        self,
        *,
        backend: str = "split-pipeline",
        platform: str | None = "auto",
        fp16: bool = False,
        memory_mode: str = "auto",
        onnx_dir: Path | None = None,
        on_progress: ProgressCallback | None = None,
        **extras: Any,
    ) -> None:
        cfg = InferenceConfig(
            mode=backend,  # type: ignore[arg-type]
            platform=platform,
            fp16=fp16,
            memory_mode=memory_mode,
        )
        if onnx_dir is not None:
            cfg.onnx_dir = Path(onnx_dir)
        self._engine = RifeInferenceEngine(cfg, on_progress=on_progress)
        self._extras = extras

    def init(self, **kwargs: Any) -> None:
        # Do not load ORT here: switch_mode used to init with dynamic ONNX and
        # VitisAI aborts on H/W=-1. Fixed-tier bind happens in interpolate_*.
        mode = kwargs.get("backend")
        if mode is not None:
            self._engine._config.mode = str(mode)

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        raise NotImplementedError("interpolate requires a frame pair")

    def process_pair(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        *,
        timestep: float = 0.5,
    ) -> np.ndarray:
        return self._engine.interpolate(img0, img1, timestep=timestep)

    def process_video(self, input_path: str | Path, output_path: str | Path, **kwargs: Any) -> dict:
        result = self._engine.interpolate_video(input_path, output_path, **kwargs)
        return {
            "output_frames": result.output_frames,
            "mode": result.mode,
            "stats": result.stats,
        }

    def stats(self) -> OperatorStats:
        st = self._engine.stats()
        return OperatorStats(
            name=self.name,
            total_calls=st.total_calls,
            total_ms=st.total_ms,
            gpu_hits=st.gpu_hits,
            npu_hits=st.npu_hits,
            providers=dict(st.providers),
        )

    def close(self) -> None:
        self._engine.close()

    @property
    def engine(self) -> RifeInferenceEngine:
        return self._engine
