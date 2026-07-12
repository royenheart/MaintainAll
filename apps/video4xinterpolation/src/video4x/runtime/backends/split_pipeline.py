"""Split pipeline: Stage A on GPU, Stage B on NPU, with CPU fallbacks.

Platform defaults:
  - Windows: Stage A = DirectML, Stage B = VitisAI (subprocess-probed)
  - WSL/Linux: Stage A = ROCm, Stage B = VitisAI
    TODO(WSL): NPU device node usually missing — Stage B falls back to CPU.
"""

from __future__ import annotations

import numpy as np

from video4x.runtime.backends._split_sessions import SplitSessions, is_gpu_provider
from video4x.runtime.backends.base import BackendConfig, BackendStats
from video4x.runtime.backends.registry import register_backend


@register_backend("split-pipeline")
class SplitPipelineBackend:
    name = "split-pipeline"
    supports_npu = False
    supports_gpu = False
    device_hint = "mixed"

    def __init__(self) -> None:
        self._sessions = SplitSessions()
        self._stats = BackendStats()

    def init(self, cfg: BackendConfig) -> None:
        self._sessions.init(cfg)
        self.supports_gpu = self._sessions.supports_gpu
        self.supports_npu = self._sessions.supports_npu
        self._sessions.apply_stats_meta(self._stats)

    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray:
        del scale
        prep = self._sessions.prepare_pair(img0, img1, timestep)
        try:
            a_out = self._sessions.run_stage_a(prep)
            a_ms = self._sessions.stage_a_ms()
            self._stats.stage_a_ms += a_ms
            assert self._sessions.stage_a is not None
            if is_gpu_provider(self._sessions.stage_a.active_provider):
                self._stats.gpu_hits += 1

            merged = self._sessions.run_stage_b(prep, a_out)
            b_ms = self._sessions.stage_b_ms()
            self._stats.stage_b_ms += b_ms
            assert self._sessions.stage_b is not None
            if "VitisAI" in self._sessions.stage_b.active_provider:
                self._stats.npu_hits += 1

            self._stats.total_calls += 1
            self._stats.total_ms += a_ms + b_ms
            return merged
        except Exception:
            prep.release()
            raise

    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None:
        self.interpolate(
            np.random.rand(*shape).astype(np.float32),
            np.random.rand(*shape).astype(np.float32),
        )

    def teardown(self) -> None:
        self._sessions.close()

    def stats(self) -> BackendStats:
        self._sessions.apply_stats_meta(self._stats)
        return self._stats
