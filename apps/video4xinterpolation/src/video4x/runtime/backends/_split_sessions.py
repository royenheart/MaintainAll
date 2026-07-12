"""Shared Stage A/B ORT session init + run helpers for split / dual-stream."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

import numpy as np

from video4x.runtime.backends._ep_probe import probe_execution_providers
from video4x.runtime.backends.base import BackendConfig, BackendStats
from video4x.runtime.backends.vitisai_probe import probe_vitisai_model_safe
from video4x.runtime.memory import MemoryMode, MemoryPlanner, create_memory_planner
from video4x.runtime.platform import (
    HostPlatform,
    default_stage_ep_preferences,
    detect_platform,
    resolve_platform,
)
from video4x.runtime.session import (
    OrtSession,
    OrtTensorSlot,
    make_ort_slot,
    make_timestep_array,
)

# Stage A output name → Stage B input name (timestep_out → timestep).
_A_TO_B: dict[str, str] = {
    "flow": "flow",
    "mask": "mask",
    "feat": "feat",
    "warped_img0": "warped_img0",
    "warped_img1": "warped_img1",
    "f0": "f0",
    "f1": "f1",
    "timestep_out": "timestep",
}

# Dual-stream overlaps A(N+1) with B(N); need two independent buffer sets.
_DEFAULT_SLOT_COUNT = 2


def is_gpu_provider(name: str) -> bool:
    return "ROCM" in name or "Dml" in name or "DML" in name or "MIGraphX" in name


@dataclass(eq=False)
class SharedFrameSlot:
    """One reusable host-pinned frame of OrtValues shared across Stage A/B."""

    shape_nchw: tuple[int, int, int, int]
    img0: OrtTensorSlot
    img1: OrtTensorSlot
    timestep: OrtTensorSlot
    intermediates: dict[str, OrtTensorSlot]  # Stage A output names
    merged: OrtTensorSlot
    # Live IOBinding objects rebound each run (OrtValues stay fixed).
    binding_a: object | None = None
    binding_b: object | None = None

    def intermediate_ptrs(self) -> dict[str, int]:
        return {k: v.data_ptr for k, v in self.intermediates.items()}


@dataclass
class PreparedPair:
    """Host feeds ready for Stage A / Stage B."""

    img0: np.ndarray
    img1: np.ndarray
    timestep: np.ndarray
    slot: SharedFrameSlot | None = None
    _owner: SplitSessions | None = field(default=None, repr=False, compare=False)

    def release(self) -> None:
        if self.slot is not None and self._owner is not None:
            self._owner._release_slot(self.slot)
            self.slot = None


@dataclass
class SplitSessions:
    """Two-stage RIFE sessions sharing one memory planner (+ optional IOBinding)."""

    stage_a: OrtSession | None = None
    stage_b: OrtSession | None = None
    memory: MemoryPlanner | None = None
    stage_b_on_npu: bool = False
    supports_gpu: bool = False
    supports_npu: bool = False
    fallback_reason: str | None = None
    providers: dict[str, str] = field(default_factory=dict)
    memory_mode: str = "host"
    memory_detail: str = ""
    use_iobinding: bool = False
    iobinding_detail: str = ""
    _want_iobinding: bool = False
    _slot_count: int = _DEFAULT_SLOT_COUNT
    _slots: list[SharedFrameSlot] = field(default_factory=list)
    _free_slots: deque[SharedFrameSlot] = field(default_factory=deque)
    _slot_lock: Lock = field(default_factory=Lock)
    # DirectML (and cross-EP) run_with_iobinding is not safe concurrently with
    # another session's IOBinding; serialize IOBinding entry points.
    _iobinding_lock: Lock = field(default_factory=Lock)
    _slot_shape: tuple[int, int, int, int] | None = None
    _out_shapes: dict[str, tuple[int, ...]] = field(default_factory=dict)

    def init(self, cfg: BackendConfig) -> None:
        plat = resolve_platform(cfg.platform) if cfg.platform else detect_platform()
        probe = probe_execution_providers()
        self.supports_gpu = probe.rocm or probe.directml
        self.supports_npu = probe.vitisai

        self.memory = create_memory_planner(plat.value)
        mode = self.memory.resolve_mode(cfg.memory_mode)
        prof = self.memory.profile()
        self.memory_mode = mode.value
        self.memory_detail = (
            f"ram={prof.system_ram_mb:.0f}MB shared={prof.gpu_shared_mb} "
            f"ded={prof.gpu_dedicated_mb} apu={prof.unified_apu} ({prof.detail})"
        )

        # Enable IOBinding zero-copy when shared memory is requested, or forced.
        if cfg.use_iobinding is True or cfg.uvm_zero_copy:
            self._want_iobinding = True
        elif cfg.use_iobinding is False:
            self._want_iobinding = False
        else:
            self._want_iobinding = mode == MemoryMode.SHARED

        stage_a_path = cfg.onnx_paths.get("stage_a")
        stage_b_path = cfg.onnx_paths.get("stage_b")
        stage_b_quant = cfg.onnx_paths.get("stage_b_quant")

        if not stage_a_path or not Path(stage_a_path).exists():
            raise FileNotFoundError("split-pipeline needs stage_a ONNX")
        if not stage_b_path or not Path(stage_b_path).exists():
            raise FileNotFoundError("split-pipeline needs stage_b ONNX")

        stage_a_pref, stage_b_pref = default_stage_ep_preferences(plat)

        self.stage_a = OrtSession(
            stage_a_path,
            ep_preference=stage_a_pref,
            fp16=cfg.fp16,
            memory=self.memory,
        )
        if not is_gpu_provider(self.stage_a.active_provider):
            note = f"stage A on {self.stage_a.active_provider} (wanted {stage_a_pref})"
            self.fallback_reason = note

        npu_candidates: list[Path] = []
        if stage_b_quant and Path(stage_b_quant).exists():
            npu_candidates.append(Path(stage_b_quant))
        npu_candidates.append(Path(stage_b_path))

        stage_b_pref_eff = list(stage_b_pref)
        chosen_b: Path | None = None
        # VitisAI aborts on dynamic H/W (-1). Only probe/load it for fixed-tier graphs.
        stage_b_is_fixed = "fixed" in Path(stage_b_path).parts
        if (
            stage_b_is_fixed
            and "vitisai" in [p.lower() for p in stage_b_pref_eff]
            and probe.vitisai
        ):
            for cand in npu_candidates:
                ok, detail = probe_vitisai_model_safe(cand, cache_dir=cfg.cache_dir)
                if ok:
                    chosen_b = cand
                    break
                short = detail.splitlines()[0][:160] if detail else "unknown"
                reason = f"VitisAI probe failed for {cand.name}: {short}"
                self.fallback_reason = (
                    f"{self.fallback_reason}; {reason}" if self.fallback_reason else reason
                )
            if chosen_b is None:
                stage_b_pref_eff = [
                    p for p in stage_b_pref_eff if p.lower() not in ("vitisai", "npu", "vai")
                ]
                if not stage_b_pref_eff:
                    stage_b_pref_eff = (
                        ["dml", "cpu"] if plat == HostPlatform.WINDOWS else ["cpu"]
                    )
                chosen_b = Path(stage_b_path)
                reason = f"no VitisAI-safe Stage B; prefs={stage_b_pref_eff}"
                self.fallback_reason = (
                    f"{self.fallback_reason}; {reason}" if self.fallback_reason else reason
                )
        else:
            chosen_b = npu_candidates[0]
            if not stage_b_is_fixed and "vitisai" in [p.lower() for p in stage_b_pref_eff]:
                stage_b_pref_eff = [
                    p for p in stage_b_pref_eff if p.lower() not in ("vitisai", "npu", "vai")
                ]
                if not stage_b_pref_eff:
                    stage_b_pref_eff = (
                        ["dml", "cpu"] if plat == HostPlatform.WINDOWS else ["cpu"]
                    )
                reason = (
                    "VitisAI skipped for dynamic ONNX "
                    f"(path={Path(stage_b_path).name}); use fixed-tier models"
                )
                self.fallback_reason = (
                    f"{self.fallback_reason}; {reason}" if self.fallback_reason else reason
                )

        try:
            self.stage_b = OrtSession(
                chosen_b,
                ep_preference=stage_b_pref_eff,
                memory=self.memory,
            )
            self.stage_b_on_npu = "VitisAI" in self.stage_b.active_provider
            if not self.stage_b_on_npu:
                reason = f"stage B on {self.stage_b.active_provider} (wanted NPU)"
                if plat == HostPlatform.WSL:
                    reason += " (TODO: WSL2 NPU passthrough incomplete)"
                self.fallback_reason = (
                    f"{self.fallback_reason}; {reason}" if self.fallback_reason else reason
                )
        except Exception as exc:  # noqa: BLE001
            self.fallback_reason = f"stage B NPU init failed: {exc}"
            self.stage_b = OrtSession(stage_b_path, ep_preference=["cpu"], memory=self.memory)

        self.providers = {
            "stage_a": self.stage_a.active_provider,
            "stage_b": self.stage_b.active_provider,
        }
        if self._want_iobinding:
            self.iobinding_detail = "pending_warmup"
        else:
            self.iobinding_detail = "disabled"
            self.use_iobinding = False

    def apply_stats_meta(self, stats: BackendStats) -> None:
        stats.memory_mode = self.memory_mode
        detail = self.memory_detail
        if self.iobinding_detail:
            detail = f"{detail}; iobinding={self.iobinding_detail}"
        stats.memory_detail = detail
        # Merge so backend-only notes (e.g. dual-stream Windows-only) survive refresh.
        session_fb = self.fallback_reason
        existing = stats.fallback_reason
        if session_fb and existing:
            parts: list[str] = []
            for chunk in (session_fb, existing):
                for bit in chunk.split("; "):
                    bit = bit.strip()
                    if bit and bit not in parts:
                        parts.append(bit)
            stats.fallback_reason = "; ".join(parts)
        elif session_fb:
            stats.fallback_reason = session_fb
        stats.providers = dict(self.providers)
        stats.use_iobinding = self.use_iobinding

    def _append_fallback(self, reason: str) -> None:
        self.fallback_reason = (
            f"{self.fallback_reason}; {reason}" if self.fallback_reason else reason
        )

    def _disable_iobinding(self, reason: str) -> None:
        self.use_iobinding = False
        self._want_iobinding = False
        self.iobinding_detail = f"fallback:{reason}"
        self._append_fallback(f"IOBinding fallback: {reason}")
        with self._slot_lock:
            self._slots.clear()
            self._free_slots.clear()
            self._slot_shape = None

    def _ensure_iobinding_ready(self, nchw: tuple[int, int, int, int]) -> bool:
        """Allocate shared slots + probe both EPs. Returns True if IOBinding is active."""
        if not self._want_iobinding:
            return False
        if self.use_iobinding and self._slot_shape == nchw and self._slots:
            return True
        assert self.stage_a is not None and self.stage_b is not None

        n, c, h, w = nchw
        img0 = np.zeros((n, c, h, w), dtype=np.float32)
        img1 = np.zeros((n, c, h, w), dtype=np.float32)
        ts = make_timestep_array(n, h, w, 0.5)

        # Probe uses unlocked temps; real pinned slots are allocated only after success.
        ok_a, reason_a, out_shapes = self.stage_a.probe_iobinding(
            {"img0": img0, "img1": img1, "timestep": ts},
            memory=None,
        )
        if not ok_a:
            self._disable_iobinding(reason_a or "stage A probe failed")
            return False

        # Build Stage B feeds from classic A outputs once to probe B.
        a_classic = self.stage_a.run({"img0": img0, "img1": img1, "timestep": ts})
        b_feeds = {
            "img0": img0,
            "img1": img1,
            "flow": a_classic["flow"],
            "mask": a_classic["mask"],
            "feat": a_classic["feat"],
            "warped_img0": a_classic["warped_img0"],
            "warped_img1": a_classic["warped_img1"],
            "f0": a_classic["f0"],
            "f1": a_classic["f1"],
            "timestep": a_classic.get("timestep_out", ts),
        }
        ok_b, reason_b, b_out_shapes = self.stage_b.probe_iobinding(b_feeds, memory=None)
        if not ok_b:
            self._disable_iobinding(reason_b or "stage B probe failed")
            return False

        self._out_shapes = dict(out_shapes)
        merged_shape = b_out_shapes.get("merged", (n, c, h, w))
        if not self._allocate_slots(nchw, out_shapes, merged_shape):
            return False
        self.use_iobinding = True
        self.iobinding_detail = (
            f"on slots={len(self._slots)} shape={nchw} "
            f"A={self.stage_a.active_provider} B={self.stage_b.active_provider}"
        )
        return True

    def _allocate_slots(
        self,
        nchw: tuple[int, int, int, int],
        a_out_shapes: dict[str, tuple[int, ...]],
        merged_shape: tuple[int, ...],
    ) -> bool:
        assert self.stage_a is not None and self.stage_b is not None
        n, c, h, w = nchw
        built: list[SharedFrameSlot] = []
        for _ in range(self._slot_count):
            img0 = make_ort_slot("img0", (n, c, h, w), memory=self.memory)
            img1 = make_ort_slot("img1", (n, c, h, w), memory=self.memory)
            timestep = make_ort_slot("timestep", (n, 1, h, w), memory=self.memory)
            intermediates: dict[str, OrtTensorSlot] = {}
            for name, shape in a_out_shapes.items():
                intermediates[name] = make_ort_slot(name, shape, memory=self.memory)
            merged = make_ort_slot("merged", merged_shape, memory=self.memory)

            slot = SharedFrameSlot(
                shape_nchw=nchw,
                img0=img0,
                img1=img1,
                timestep=timestep,
                intermediates=intermediates,
                merged=merged,
            )
            a_in = {"img0": img0, "img1": img1, "timestep": timestep}
            a_bundle = self.stage_a.bind_slots(inputs=a_in, outputs=intermediates)
            if not a_bundle.ok:
                self._disable_iobinding(a_bundle.fallback_reason or "stage A bind")
                return False
            b_in: dict[str, OrtTensorSlot] = {"img0": img0, "img1": img1}
            for a_name, b_name in _A_TO_B.items():
                if a_name not in intermediates:
                    self._disable_iobinding(f"missing intermediate '{a_name}'")
                    return False
                b_in[b_name] = intermediates[a_name]
            b_bundle = self.stage_b.bind_slots(inputs=b_in, outputs={"merged": merged})
            if not b_bundle.ok:
                self._disable_iobinding(b_bundle.fallback_reason or "stage B bind")
                return False
            slot.binding_a = a_bundle.binding
            slot.binding_b = b_bundle.binding
            built.append(slot)

        with self._slot_lock:
            self._slots = built
            self._free_slots = deque(built)
            self._slot_shape = nchw
        return True

    def _acquire_slot(self, nchw: tuple[int, int, int, int]) -> SharedFrameSlot | None:
        if not self._ensure_iobinding_ready(nchw):
            return None
        with self._slot_lock:
            if not self._free_slots:
                # Should not happen with dual-stream depth 2; grow once as safety.
                return None
            return self._free_slots.popleft()

    def _release_slot(self, slot: SharedFrameSlot) -> None:
        with self._slot_lock:
            # Identity checks: SharedFrameSlot holds numpy views; default dataclass
            # __eq__ would raise on array comparison.
            if any(s is slot for s in self._free_slots):
                return
            if any(s is slot for s in self._slots):
                self._free_slots.append(slot)

    def prepare_pair(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
    ) -> PreparedPair:
        img0f = np.ascontiguousarray(img0, dtype=np.float32)
        img1f = np.ascontiguousarray(img1, dtype=np.float32)
        _, _, h, w = img0f.shape
        nchw = (int(img0f.shape[0]), int(img0f.shape[1]), int(h), int(w))

        if self._want_iobinding or self.use_iobinding:
            slot = self._acquire_slot(nchw)
            if slot is not None:
                slot.img0.write(img0f)
                slot.img1.write(img1f)
                slot.timestep.array.fill(float(timestep))
                return PreparedPair(
                    img0=slot.img0.array,
                    img1=slot.img1.array,
                    timestep=slot.timestep.array,
                    slot=slot,
                    _owner=self,
                )

        # Classic host / pinned path (may allocate+lock via ensure).
        if self.memory is not None:
            img0f = self.memory.ensure(img0f)
            img1f = self.memory.ensure(img1f)
        ts = make_timestep_array(1, h, w, timestep)
        if self.memory is not None:
            ts = self.memory.ensure(ts)
        return PreparedPair(img0=img0f, img1=img1f, timestep=ts)

    def _run_stage_a_fill_slot(self, prep: PreparedPair) -> dict[str, np.ndarray]:
        """Classic Stage A, then write outputs into the pair's shared OrtValue slots.

        Used when dual-stream overlaps A(N+1) with B(N): concurrent
        ``run_with_iobinding`` across DirectML + VitisAI is unsafe, but classic
        Stage A can overlap Stage B IOBinding. One host write into pinned slots
        keeps Stage B on the zero-copy OrtValue path.
        """
        assert self.stage_a is not None and prep.slot is not None
        outs = self.stage_a.run(
            {"img0": prep.img0, "img1": prep.img1, "timestep": prep.timestep}
        )
        for name, arr in outs.items():
            slot = prep.slot.intermediates.get(name)
            if slot is not None:
                slot.write(arr)
        return {name: s.numpy_view() for name, s in prep.slot.intermediates.items()}

    def run_stage_a(
        self,
        prep: PreparedPair,
        *,
        avoid_concurrent_iobinding: bool = False,
    ) -> dict[str, np.ndarray]:
        assert self.stage_a is not None
        if self.use_iobinding and prep.slot is not None and prep.slot.binding_a is not None:
            if avoid_concurrent_iobinding:
                return self._run_stage_a_fill_slot(prep)
            with self._iobinding_lock:
                self.stage_a.run_iobinding(prep.slot.binding_a)
            # Views into the same OrtValue host buffers (no A→host copy).
            return {name: slot.numpy_view() for name, slot in prep.slot.intermediates.items()}
        return self.stage_a.run(
            {"img0": prep.img0, "img1": prep.img1, "timestep": prep.timestep}
        )

    def run_stage_b(
        self,
        prep: PreparedPair,
        a_out: dict[str, np.ndarray],
        *,
        release_slot: bool = True,
    ) -> np.ndarray:
        assert self.stage_b is not None
        try:
            if self.use_iobinding and prep.slot is not None and prep.slot.binding_b is not None:
                # Same intermediate OrtValues Stage A wrote (IOBinding or fill_slot).
                with self._iobinding_lock:
                    self.stage_b.run_iobinding(prep.slot.binding_b)
                # One allowed host takeout for the encoder / caller.
                return np.copy(prep.slot.merged.numpy_view())

            b_feeds = {
                "img0": prep.img0,
                "img1": prep.img1,
                "flow": a_out["flow"],
                "mask": a_out["mask"],
                "feat": a_out["feat"],
                "warped_img0": a_out["warped_img0"],
                "warped_img1": a_out["warped_img1"],
                "f0": a_out["f0"],
                "f1": a_out["f1"],
                "timestep": a_out.get("timestep_out", prep.timestep),
            }
            b_out = self.stage_b.run(b_feeds)
            return b_out["merged"]
        finally:
            if release_slot:
                prep.release()

    def stage_a_ms(self) -> float:
        assert self.stage_a is not None
        return self.stage_a.last_elapsed_ms()

    def stage_b_ms(self) -> float:
        assert self.stage_b is not None
        return self.stage_b.last_elapsed_ms()

    def close(self) -> None:
        with self._slot_lock:
            self._slots.clear()
            self._free_slots.clear()
            self._slot_shape = None
        for s in (self.stage_a, self.stage_b):
            if s:
                s.close()
        self.stage_a = self.stage_b = None
        self.use_iobinding = False
        if self.memory is not None:
            self.memory.close()
            self.memory = None
