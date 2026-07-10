"""CPU-only baseline backend."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rife_amd.runtime.backends.base import BackendConfig, BackendStats
from rife_amd.runtime.backends.registry import register_backend
from rife_amd.runtime.session import OrtSession, make_timestep_array


@register_backend("cpu-baseline")
class CpuBaselineBackend:
    name = "cpu-baseline"
    supports_npu = False
    supports_gpu = False
    device_hint = "cpu"

    def __init__(self) -> None:
        self._session: OrtSession | None = None
        self._stats = BackendStats()

    def init(self, cfg: BackendConfig) -> None:
        full = cfg.onnx_paths.get("full")
        model = full if full and Path(full).exists() else cfg.onnx_paths.get("stage_a")
        if not model or not Path(model).exists():
            raise FileNotFoundError("cpu-baseline needs exported ONNX. Run export_onnx.py --full")
        self._session = OrtSession(model, ep_preference=["cpu"])
        self._stats.providers = {"session": self._session.active_provider}
    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray:
        del scale
        assert self._session is not None
        _, _, h, w = img0.shape
        ts = make_timestep_array(1, h, w, timestep)
        out = self._session.run(
            {"img0": img0.astype(np.float32), "img1": img1.astype(np.float32), "timestep": ts}
        )
        self._stats.total_calls += 1
        self._stats.total_ms += self._session.last_elapsed_ms()
        return out["merged"]

    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None:
        self.interpolate(
            np.random.rand(*shape).astype(np.float32),
            np.random.rand(*shape).astype(np.float32),
        )

    def teardown(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def stats(self) -> BackendStats:
        return self._stats
