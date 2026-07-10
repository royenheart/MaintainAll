"""Dual-stream concurrent GPU+NPU — skeleton only."""

from __future__ import annotations

import numpy as np

from rife_amd.runtime.backends.base import BackendConfig, BackendStats
from rife_amd.runtime.backends.registry import register_backend


@register_backend("dual-stream")
class DualStreamBackend:
    """
    Placeholder for true concurrent dual-stream scheduling.

    TODO: overlap stage A (GPU) of frame N+1 with stage B (NPU) of frame N
    using separate ORT sessions + thread pool + shared pinned host buffers.
    """

    #BLOCKER: ORT IOBinding async + VitisAI compile cache coordination not
    # validated on WSL2 amdxdna; needs profiling on target hardware.

    name = "dual-stream"
    supports_npu = False
    supports_gpu = False
    device_hint = "mixed"

    def init(self, cfg: BackendConfig) -> None:
        del cfg
        raise NotImplementedError(
            "dual-stream backend is a skeleton. See dual_stream.py TODO comments."
        )

    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray:
        del img0, img1, timestep, scale
        raise NotImplementedError("dual-stream not implemented")

    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None:
        del shape
        raise NotImplementedError("dual-stream not implemented")

    def teardown(self) -> None:
        pass

    def stats(self) -> BackendStats:
        return BackendStats()
