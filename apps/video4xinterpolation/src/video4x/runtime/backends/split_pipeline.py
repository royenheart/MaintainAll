"""Split pipeline: Stage A on GPU, Stage B on NPU, with CPU fallbacks.

Platform defaults:
  - Windows: Stage A = DirectML, Stage B = VitisAI (subprocess-probed)
  - WSL/Linux: Stage A = ROCm, Stage B = VitisAI
    TODO(WSL): NPU device node usually missing — Stage B falls back to CPU.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from video4x.runtime.backends._ep_probe import probe_execution_providers
from video4x.runtime.backends.base import BackendConfig, BackendStats
from video4x.runtime.backends.registry import register_backend
from video4x.runtime.backends.vitisai_probe import probe_vitisai_model_safe
from video4x.runtime.memory import create_memory_planner
from video4x.runtime.platform import (
    HostPlatform,
    default_stage_ep_preferences,
    detect_platform,
    resolve_platform,
)
from video4x.runtime.session import OrtSession, make_timestep_array


def _is_gpu_provider(name: str) -> bool:
    return "ROCM" in name or "Dml" in name or "DML" in name or "MIGraphX" in name


@register_backend("split-pipeline")
class SplitPipelineBackend:
    name = "split-pipeline"
    supports_npu = False
    supports_gpu = False
    device_hint = "mixed"

    def __init__(self) -> None:
        self._stage_a: OrtSession | None = None
        self._stage_b: OrtSession | None = None
        self._stats = BackendStats()
        self._cfg: BackendConfig | None = None
        self._stage_b_on_npu = False
        self._memory = None

    def init(self, cfg: BackendConfig) -> None:
        self._cfg = cfg
        plat = resolve_platform(cfg.platform) if cfg.platform else detect_platform()
        probe = probe_execution_providers()
        self.supports_gpu = probe.rocm or probe.directml
        self.supports_npu = probe.vitisai

        self._memory = create_memory_planner(plat.value)
        mode = self._memory.resolve_mode(cfg.memory_mode)
        prof = self._memory.profile()
        self._stats.memory_mode = mode.value
        self._stats.memory_detail = (
            f"ram={prof.system_ram_mb:.0f}MB shared={prof.gpu_shared_mb} "
            f"ded={prof.gpu_dedicated_mb} apu={prof.unified_apu} ({prof.detail})"
        )

        stage_a_path = cfg.onnx_paths.get("stage_a")
        stage_b_path = cfg.onnx_paths.get("stage_b")
        stage_b_quant = cfg.onnx_paths.get("stage_b_quant")

        if not stage_a_path or not Path(stage_a_path).exists():
            raise FileNotFoundError("split-pipeline needs stage_a ONNX")
        if not stage_b_path or not Path(stage_b_path).exists():
            raise FileNotFoundError("split-pipeline needs stage_b ONNX")

        stage_a_pref, stage_b_pref = default_stage_ep_preferences(plat)

        self._stage_a = OrtSession(
            stage_a_path,
            ep_preference=stage_a_pref,
            fp16=cfg.fp16,
            memory=self._memory,
        )
        if not _is_gpu_provider(self._stage_a.active_provider):
            note = f"stage A on {self._stage_a.active_provider} (wanted {stage_a_pref})"
            self._stats.fallback_reason = note

        if plat in (HostPlatform.WSL, HostPlatform.LINUX) and not probe.vitisai:
            pass

        npu_candidates: list[Path] = []
        if stage_b_quant and Path(stage_b_quant).exists():
            npu_candidates.append(Path(stage_b_quant))
        npu_candidates.append(Path(stage_b_path))

        stage_b_pref_eff = list(stage_b_pref)
        chosen_b: Path | None = None
        if "vitisai" in [p.lower() for p in stage_b_pref_eff] and probe.vitisai:
            for cand in npu_candidates:
                ok, detail = probe_vitisai_model_safe(cand, cache_dir=cfg.cache_dir)
                if ok:
                    chosen_b = cand
                    break
                short = detail.splitlines()[0][:160] if detail else "unknown"
                reason = f"VitisAI probe failed for {cand.name}: {short}"
                self._stats.fallback_reason = (
                    f"{self._stats.fallback_reason}; {reason}"
                    if self._stats.fallback_reason
                    else reason
                )
            if chosen_b is None:
                stage_b_pref_eff = [
                    p for p in stage_b_pref_eff if p.lower() not in ("vitisai", "npu", "vai")
                ]
                if not stage_b_pref_eff:
                    stage_b_pref_eff = ["dml", "cpu"] if plat == HostPlatform.WINDOWS else ["cpu"]
                chosen_b = Path(stage_b_path)
                reason = f"no VitisAI-safe Stage B; prefs={stage_b_pref_eff}"
                self._stats.fallback_reason = (
                    f"{self._stats.fallback_reason}; {reason}"
                    if self._stats.fallback_reason
                    else reason
                )
        else:
            chosen_b = npu_candidates[0]

        try:
            self._stage_b = OrtSession(
                chosen_b,
                ep_preference=stage_b_pref_eff,
                memory=self._memory,
            )
            self._stage_b_on_npu = "VitisAI" in self._stage_b.active_provider
            if not self._stage_b_on_npu:
                reason = f"stage B on {self._stage_b.active_provider} (wanted NPU)"
                if plat == HostPlatform.WSL:
                    reason += " (TODO: WSL2 NPU passthrough incomplete)"
                self._stats.fallback_reason = (
                    f"{self._stats.fallback_reason}; {reason}"
                    if self._stats.fallback_reason
                    else reason
                )
        except Exception as exc:  # noqa: BLE001
            self._stats.fallback_reason = f"stage B NPU init failed: {exc}"
            self._stage_b = OrtSession(stage_b_path, ep_preference=["cpu"], memory=self._memory)

        self._stats.providers = {
            "stage_a": self._stage_a.active_provider,
            "stage_b": self._stage_b.active_provider,
        }

    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray:
        del scale
        assert self._stage_a is not None and self._stage_b is not None
        img0f = img0.astype(np.float32)
        img1f = img1.astype(np.float32)
        if self._memory is not None:
            img0f = self._memory.ensure(img0f)
            img1f = self._memory.ensure(img1f)
        _, _, h, w = img0f.shape
        ts = make_timestep_array(1, h, w, timestep)
        if self._memory is not None:
            ts = self._memory.ensure(ts)

        a_out = self._stage_a.run({"img0": img0f, "img1": img1f, "timestep": ts})
        self._stats.stage_a_ms += self._stage_a.last_elapsed_ms()
        if _is_gpu_provider(self._stage_a.active_provider):
            self._stats.gpu_hits += 1

        b_feeds = {
            "img0": img0f,
            "img1": img1f,
            "flow": a_out["flow"],
            "mask": a_out["mask"],
            "feat": a_out["feat"],
            "warped_img0": a_out["warped_img0"],
            "warped_img1": a_out["warped_img1"],
            "f0": a_out["f0"],
            "f1": a_out["f1"],
            "timestep": a_out.get("timestep_out", ts),
        }
        b_out = self._stage_b.run(b_feeds)
        self._stats.stage_b_ms += self._stage_b.last_elapsed_ms()
        if "VitisAI" in self._stage_b.active_provider:
            self._stats.npu_hits += 1

        self._stats.total_calls += 1
        self._stats.total_ms += self._stage_a.last_elapsed_ms() + self._stage_b.last_elapsed_ms()
        return b_out["merged"]

    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None:
        self.interpolate(
            np.random.rand(*shape).astype(np.float32),
            np.random.rand(*shape).astype(np.float32),
        )

    def teardown(self) -> None:
        for s in (self._stage_a, self._stage_b):
            if s:
                s.close()
        self._stage_a = self._stage_b = None
        if self._memory is not None:
            self._memory.close()
            self._memory = None

    def stats(self) -> BackendStats:
        return self._stats
