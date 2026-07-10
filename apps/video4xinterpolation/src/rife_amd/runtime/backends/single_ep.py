"""Single ORT session with multi-EP fallback (full or stage-a only)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rife_amd.runtime.backends._ep_probe import probe_execution_providers
from rife_amd.runtime.backends.base import BackendConfig, BackendStats
from rife_amd.runtime.backends.registry import register_backend
from rife_amd.runtime.session import OrtSession, make_timestep_array


@register_backend("single-ep")
class SingleEpBackend:
    name = "single-ep"
    supports_npu: bool = False
    supports_gpu: bool = False
    device_hint = "mixed"

    def __init__(self) -> None:
        self._session: OrtSession | None = None
        self._stats = BackendStats()
        self._cfg: BackendConfig | None = None

    def init(self, cfg: BackendConfig) -> None:
        self._cfg = cfg
        probe = probe_execution_providers()
        self.supports_gpu = probe.rocm or probe.directml
        self.supports_npu = probe.vitisai

        full = cfg.onnx_paths.get("full")
        if not full or not Path(full).exists():
            raise FileNotFoundError(
                "single-ep needs models/onnx/rife_full.onnx. Run: python scripts/export_onnx.py --full"
            )
        model = full

        pref = list(cfg.ep_preference) if cfg.ep_preference else ["cpu"]
        if cfg.fp16 and "rocm" in pref:
            pref = ["rocm", "cpu"]
        self._session = OrtSession(model, ep_preference=pref, fp16=cfg.fp16)
        prov = self._session.active_provider
        if "ROCM" in prov or "Dml" in prov:
            self.device_hint = "gpu"
        elif "VitisAI" in prov:
            self.device_hint = "npu"
        else:
            self.device_hint = "cpu"
        self._stats.providers = {"session": self._session.active_provider}
    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray:
        del scale  # scale baked into exported graph for v4.26 default
        assert self._session is not None
        _, _, h, w = img0.shape
        ts = make_timestep_array(1, h, w, timestep)
        feeds = {"img0": img0.astype(np.float32), "img1": img1.astype(np.float32), "timestep": ts}
        out = self._session.run(feeds)
        self._stats.total_calls += 1
        self._stats.total_ms += self._session.last_elapsed_ms()
        if "ROCM" in self._session.active_provider or "Dml" in self._session.active_provider:
            self._stats.gpu_hits += 1
        if "VitisAI" in self._session.active_provider:
            self._stats.npu_hits += 1
        return out["merged"]

    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None:
        img0 = np.random.rand(*shape).astype(np.float32)
        img1 = np.random.rand(*shape).astype(np.float32)
        self.interpolate(img0, img1)

    def teardown(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def stats(self) -> BackendStats:
        return self._stats
