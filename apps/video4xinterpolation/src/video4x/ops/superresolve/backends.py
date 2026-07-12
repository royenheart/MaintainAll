"""Real-ESRGAN ONNX backends: single-EP full graph or body(NPU)+upsample(GPU)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from video4x.runtime.backends.vitisai_probe import probe_vitisai_model_safe
from video4x.runtime.memory import create_memory_planner
from video4x.runtime.platform import (
    default_ep_preference,
    default_stage_ep_preferences,
    resolve_platform,
)
from video4x.runtime.session import OrtSession


@dataclass
class SrBackendStats:
    total_calls: int = 0
    total_ms: float = 0.0
    body_ms: float = 0.0
    upsample_ms: float = 0.0
    npu_hits: int = 0
    gpu_hits: int = 0
    fallback_reason: str | None = None
    providers: dict[str, str] = field(default_factory=dict)
    memory_mode: str = "host"
    memory_detail: str = ""


class SrFullBackend:
    """Single ONNX session for realesrgan_full.onnx."""

    name = "single-ep"

    def __init__(self) -> None:
        self._session: OrtSession | None = None
        self._memory = None
        self._stats = SrBackendStats()

    def init(
        self,
        *,
        onnx_paths: dict[str, Path],
        platform: str | None = "auto",
        ep_preference: list[str] | None = None,
        fp16: bool = False,
        memory_mode: str = "auto",
    ) -> None:
        plat = resolve_platform(platform)
        pref = ep_preference or default_ep_preference(plat)
        self._memory = create_memory_planner(plat.value)
        mode = self._memory.resolve_mode(memory_mode)
        prof = self._memory.profile()
        full = onnx_paths.get("full")
        if full is None or not Path(full).is_file():
            raise FileNotFoundError("realesrgan_full.onnx required for single-ep backend")
        self._session = OrtSession(
            Path(full),
            ep_preference=pref,
            fp16=fp16,
            memory=self._memory,
        )
        self._stats.providers = {"full": self._session.active_provider}
        self._stats.memory_mode = mode.value
        self._stats.memory_detail = (
            f"ram={prof.system_ram_mb:.0f}MB shared={prof.gpu_shared_mb} "
            f"ded={prof.gpu_dedicated_mb} apu={prof.unified_apu} ({prof.detail})"
        )

    def run(self, lr: np.ndarray) -> np.ndarray:
        assert self._session is not None
        t0 = time.perf_counter()
        out = self._session.run({"lr": lr.astype(np.float32, copy=False)})
        ms = (time.perf_counter() - t0) * 1000.0
        self._stats.total_calls += 1
        self._stats.total_ms += ms
        prov = self._session.active_provider
        if "VitisAI" in prov:
            self._stats.npu_hits += 1
        elif "Dml" in prov or "ROCM" in prov or "CUDA" in prov:
            self._stats.gpu_hits += 1
        hr = out["hr"]
        return np.clip(hr, 0.0, 1.0)

    def stats(self) -> SrBackendStats:
        return self._stats

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None


class SrSplitBackend:
    """Body on VitisAI (preferred) + upsample on DirectML."""

    name = "split-pipeline"

    def __init__(self) -> None:
        self._body: OrtSession | None = None
        self._up: OrtSession | None = None
        self._memory = None
        self._stats = SrBackendStats()
        self._use_full_fallback: SrFullBackend | None = None

    def init(
        self,
        *,
        onnx_paths: dict[str, Path],
        platform: str | None = "auto",
        ep_preference: list[str] | None = None,
        fp16: bool = False,
        memory_mode: str = "auto",
    ) -> None:
        plat = resolve_platform(platform)
        self._memory = create_memory_planner(plat.value)
        mode = self._memory.resolve_mode(memory_mode)
        prof = self._memory.profile()
        body_path = onnx_paths.get("body")
        up_path = onnx_paths.get("upsample")
        if body_path is None or up_path is None or not Path(body_path).is_file() or not Path(up_path).is_file():
            # Fall back to full graph
            if onnx_paths.get("full") and Path(onnx_paths["full"]).is_file():
                self._use_full_fallback = SrFullBackend()
                self._use_full_fallback.init(
                    onnx_paths=onnx_paths,
                    platform=platform,
                    ep_preference=ep_preference,
                    fp16=fp16,
                    memory_mode=memory_mode,
                )
                self._stats.fallback_reason = "missing body/upsample onnx; using full"
                self._stats.providers = self._use_full_fallback.stats().providers
                return
            raise FileNotFoundError("Need body+upsample or full ONNX for split-pipeline")

        # Body → NPU only; upsample → GPU (dml/rocm). No silent DML body fallback.
        up_pref, _body_pref = default_stage_ep_preferences(plat)
        body_path_p = Path(body_path)
        up_path_p = Path(up_path)

        ok, reason = probe_vitisai_model_safe(body_path_p, timeout_s=1800.0)
        if not ok:
            raise RuntimeError(
                "SR split-pipeline requires VitisAI NPU for body (GPU+NPU co-accel). "
                f"Probe failed: {reason}"
            )

        self._body = OrtSession(
            body_path_p,
            ep_preference=["vitisai"],
            fp16=fp16,
            memory=self._memory,
        )
        if "VitisAI" not in self._body.active_provider:
            raise RuntimeError(
                f"SR body session not on VitisAI (got {self._body.active_provider})"
            )
        self._up = OrtSession(
            up_path_p,
            ep_preference=up_pref,
            fp16=fp16,
            memory=self._memory,
        )
        if not any(k in self._up.active_provider for k in ("Dml", "ROCM", "CUDA")):
            raise RuntimeError(
                f"SR upsample session not on GPU (got {self._up.active_provider})"
            )
        self._stats.providers = {
            "body": self._body.active_provider,
            "upsample": self._up.active_provider,
        }
        self._stats.memory_mode = mode.value
        self._stats.memory_detail = (
            f"ram={prof.system_ram_mb:.0f}MB shared={prof.gpu_shared_mb} "
            f"ded={prof.gpu_dedicated_mb} apu={prof.unified_apu} ({prof.detail})"
        )

    def run(self, lr: np.ndarray) -> np.ndarray:
        if self._use_full_fallback is not None:
            hr = self._use_full_fallback.run(lr)
            st = self._use_full_fallback.stats()
            self._stats = st
            return hr
        assert self._body is not None and self._up is not None
        t0 = time.perf_counter()
        feat = self._body.run({"lr": lr.astype(np.float32, copy=False)})["feat"]
        body_ms = self._body.last_elapsed_ms()
        hr = self._up.run({"feat": feat})["hr"]
        up_ms = self._up.last_elapsed_ms()
        total = (time.perf_counter() - t0) * 1000.0
        self._stats.total_calls += 1
        self._stats.total_ms += total
        self._stats.body_ms += body_ms
        self._stats.upsample_ms += up_ms
        if "VitisAI" in self._body.active_provider:
            self._stats.npu_hits += 1
        if any(k in self._up.active_provider for k in ("Dml", "ROCM", "CUDA")):
            self._stats.gpu_hits += 1
        return np.clip(hr, 0.0, 1.0)

    def stats(self) -> SrBackendStats:
        if self._use_full_fallback is not None:
            return self._use_full_fallback.stats()
        return self._stats

    def close(self) -> None:
        if self._use_full_fallback is not None:
            self._use_full_fallback.close()
            self._use_full_fallback = None
        if self._body is not None:
            self._body.close()
            self._body = None
        if self._up is not None:
            self._up.close()
            self._up = None


def create_sr_backend(name: str) -> SrFullBackend | SrSplitBackend:
    if name in ("split-pipeline", "split"):
        return SrSplitBackend()
    if name in ("single-ep", "full", "cpu-baseline"):
        return SrFullBackend()
    raise KeyError(f"Unknown SR backend '{name}'")
