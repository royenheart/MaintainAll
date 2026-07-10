"""RifeInferenceEngine — upper-level facade for mode switching and inference."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

import numpy as np

from rife_amd.inference.config import InferenceConfig, InferenceMode
from rife_amd.inference.progress import ProgressCallback, ProgressEvent, ProgressTracker
from rife_amd.runtime.backends.base import BackendStats, InterpolationBackend
from rife_amd.runtime.backends.registry import create_backend, list_backends
from rife_amd.runtime.preprocess import crop_hw, pack_frame_batch, pad_to_multiple
from rife_amd.runtime.resolutions import resolve_onnx_paths_for_hw, size_tag
from rife_amd.runtime.resources import create_resource_sampler
from rife_amd.runtime.video_io import read_frames, write_video


@dataclass
class InferenceResult:
    output_frames: int
    mode: str
    stats: dict


class RifeInferenceEngine:
    """
    Upper-level inference facade.

    Wraps the runtime backend layer (middle tier) and exposes a stable API for
    application code: switch modes, run frame/video inference, read stats.

    Progress (optional ``on_progress``) is emitted here — decode / init /
    interpolate / encode — not inside individual backends.
    """

    def __init__(
        self,
        config: InferenceConfig | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._config = config or InferenceConfig()
        self._backend: InterpolationBackend | None = None
        self._active_mode: str | None = None
        self._on_progress = on_progress
        self._onnx_key: tuple | None = None
        self._model_kind: str = "unset"

    @property
    def mode(self) -> str:
        if self._active_mode is None:
            return str(self._config.mode)
        return self._active_mode

    @property
    def available_modes(self) -> list[str]:
        return list_backends()

    @property
    def is_ready(self) -> bool:
        return self._backend is not None

    def switch_mode(self, mode: str | InferenceMode) -> None:
        """Hot-swap inference backend without recreating the engine."""
        name = mode.value if isinstance(mode, InferenceMode) else str(mode)
        if name not in list_backends():
            raise KeyError(f"Unknown mode '{name}'. Available: {self.available_modes}")
        if self._active_mode == name and self._backend is not None and self._onnx_key is not None:
            return
        self.close()
        self._backend = create_backend(name)
        self._backend.init(self._config.to_backend_config())
        self._active_mode = name
        # Default dynamic paths until bind_onnx_for_hw selects a fixed tier.
        self._onnx_key = ("default", name)
        self._model_kind = "dynamic"

    def bind_onnx_for_hw(self, height: int, width: int) -> str:
        """Load Stage A/B (prefer fixed-tier + quant) matching padded H×W."""
        paths, (fh, fw), kind = resolve_onnx_paths_for_hw(
            self._config.onnx_dir, height, width, prefer_fixed=True
        )
        mode_name = self._active_mode or str(self._config.mode)
        key = (fh, fw, kind, mode_name, str(paths["stage_a"]), str(paths.get("stage_b_quant")))
        if self._backend is not None and self._onnx_key == key:
            return kind
        self.close()
        self._backend = create_backend(mode_name)
        cfg = self._config.to_backend_config()
        cfg.onnx_paths = paths
        self._backend.init(cfg)
        self._active_mode = mode_name
        self._onnx_key = key
        self._model_kind = kind
        quant = paths.get("stage_b_quant")
        if kind == "fixed" and quant is not None and Path(quant).is_file():
            self._model_kind = "fixed+quant"
        return self._model_kind

    def use(self, mode: str | InferenceMode) -> Self:
        """Fluent alias for switch_mode."""
        self.switch_mode(mode)
        return self

    def _ensure_backend(self) -> InterpolationBackend:
        if self._backend is None:
            self.switch_mode(self._config.mode)
        assert self._backend is not None
        return self._backend

    @property
    def device_hint(self) -> str:
        if self._backend is None:
            return "unknown"
        return self._backend.device_hint

    def warmup(self, shape: tuple[int, ...] = (1, 3, 1080, 1920)) -> None:
        self._ensure_backend().warmup(shape)

    def _progress_base(self, tracker: ProgressTracker, phase: str, **kwargs: object) -> ProgressEvent:
        st = self.stats()
        return ProgressEvent(
            phase=phase,
            mode=self.mode,
            device_hint=self.device_hint,
            providers=dict(st.providers),
            gpu_hits=st.gpu_hits,
            npu_hits=st.npu_hits,
            stage_a_ms=st.stage_a_ms,
            stage_b_ms=st.stage_b_ms,
            memory_mode=st.memory_mode,
            memory_detail=st.memory_detail,
            elapsed_s=tracker.elapsed(),
            **kwargs,  # type: ignore[arg-type]
        )

    def interpolate(
        self,
        img0: np.ndarray,
        img1: np.ndarray,
        timestep: float = 0.5,
        scale: float = 1.0,
    ) -> np.ndarray:
        """Single frame-pair interpolation (NCHW float32 [0,1] in/out)."""
        img0p, (h, w) = pad_to_multiple(img0)
        img1p, _ = pad_to_multiple(img1)
        self.bind_onnx_for_hw(img0p.shape[2], img0p.shape[3])
        mid = self._ensure_backend().interpolate(img0p, img1p, timestep, scale)
        return crop_hw(mid, h, w)

    def interpolate_frames(
        self,
        frames: list[np.ndarray],
        multiplier: int = 2,
        *,
        tracker: ProgressTracker | None = None,
    ) -> list[np.ndarray]:
        """Insert mid-frames between consecutive input frames (2x only)."""
        if multiplier != 2:
            raise ValueError("Only 2x interpolation supported in v0.1")
        owns_tracker = tracker is None
        tr = tracker or ProgressTracker(
            self._on_progress,
            sampler=create_resource_sampler(self._config.platform) if self._on_progress else None,
        )
        try:
            pairs = max(0, len(frames) - 1)
            tr.emit(
                ProgressEvent(
                    phase="init",
                    message="packing frames into contiguous host buffer",
                    current=0,
                    total=pairs,
                    mode=str(self._config.mode),
                )
            )
            batch, (h, w) = pack_frame_batch(frames)
            ph, pw = int(batch.shape[2]), int(batch.shape[3])
            mb = batch.nbytes / (1024 * 1024)
            kind = self.bind_onnx_for_hw(ph, pw)
            st0 = self.stats()
            mem_label = st0.memory_mode or self._config.memory_mode or "host"
            tr.emit(
                self._progress_base(
                    tr,
                    "init",
                    message=(
                        f"packed {batch.shape[0]}@{size_tag(ph, pw)} ({mb:.0f}MB) "
                        f"models={kind} mem={mem_label}"
                    ),
                    current=0,
                    total=pairs,
                )
            )
            backend = self._ensure_backend()
            out: list[np.ndarray] = []
            for i in range(len(frames)):
                out.append(frames[i])
                if i < pairs:
                    img0 = np.ascontiguousarray(batch[i : i + 1])
                    img1 = np.ascontiguousarray(batch[i + 1 : i + 2])
                    mid = backend.interpolate(img0, img1, timestep=0.5)
                    mid = crop_hw(mid, h, w)
                    out.append(mid[np.newaxis, ...] if mid.ndim == 3 else mid)
                    st = self.stats()
                    done = i + 1
                    last_ms, avg_ms, _ = tr.pair_timing(st.total_ms, done)
                    tr.emit(
                        self._progress_base(
                            tr,
                            "interpolate",
                            message=f"pair {done}/{pairs}",
                            current=done,
                            total=pairs,
                            last_ms=last_ms,
                            avg_ms=avg_ms,
                            eta_s=tr.eta(done, pairs, avg_ms),
                        )
                    )
            return out
        finally:
            if owns_tracker:
                tr.close()

    def interpolate_video(
        self,
        input_path: Path | str,
        output_path: Path | str,
        fps: float = 30.0,
    ) -> InferenceResult:
        """End-to-end video decode → interpolate → encode."""
        input_path = Path(input_path)
        output_path = Path(output_path)
        tr = ProgressTracker(
            self._on_progress,
            sampler=create_resource_sampler(self._config.platform) if self._on_progress else None,
        )
        try:
            tr.emit(ProgressEvent(phase="decode", message=f"reading {input_path.name}"))
            frames = list(read_frames(input_path))
            if not frames:
                raise ValueError(f"No frames decoded from {input_path}")
            tr.emit(
                ProgressEvent(
                    phase="decode",
                    message=f"decoded {len(frames)} frames",
                    current=len(frames),
                    total=len(frames),
                    elapsed_s=tr.elapsed(),
                )
            )

            out_frames = self.interpolate_frames(frames, tracker=tr)
            _, _, h, w = frames[0].shape

            tr.emit(
                self._progress_base(
                    tr,
                    "encode",
                    message=f"writing {output_path.name}",
                    current=len(out_frames),
                    total=len(out_frames),
                )
            )
            write_video(output_path, (f[0] for f in out_frames), fps=fps * 2, width=w, height=h)

            st = self.stats()
            tr.emit(
                self._progress_base(
                    tr,
                    "done",
                    message=f"wrote {output_path}",
                    current=len(out_frames),
                    total=len(out_frames),
                )
            )
            return InferenceResult(
                output_frames=len(out_frames),
                mode=self.mode,
                stats={
                    "total_calls": st.total_calls,
                    "total_ms": st.total_ms,
                    "stage_a_ms": st.stage_a_ms,
                    "stage_b_ms": st.stage_b_ms,
                    "npu_hits": st.npu_hits,
                    "gpu_hits": st.gpu_hits,
                    "fallback_reason": st.fallback_reason,
                    "device_hint": self._ensure_backend().device_hint,
                    "providers": dict(st.providers),
                    "model_kind": self._model_kind,
                    "memory_mode": st.memory_mode,
                    "memory_detail": st.memory_detail,
                },
            )
        finally:
            tr.close()

    def stats(self) -> BackendStats:
        if self._backend is None:
            return BackendStats()
        return self._backend.stats()

    def close(self) -> None:
        if self._backend is not None:
            self._backend.teardown()
            self._backend = None
            self._active_mode = None
            self._onnx_key = None

    def __enter__(self) -> Self:
        # Lazy ORT load: bind_onnx_for_hw selects fixed-tier after frame size is known.
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
