"""Super-resolution engine: tile + ONNX backends (fixed tiles for NPU)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Self

import numpy as np

from video4x.inference.progress import ProgressCallback, ProgressEvent, ProgressTracker
from video4x.ops.base import OperatorStats
from video4x.ops.superresolve.backends import SrFullBackend, SrSplitBackend, create_sr_backend
from video4x.ops.superresolve.export import default_onnx_root, resolve_sr_onnx_paths
from video4x.ops.superresolve.model import MODEL_PRESETS, resolve_model_name
from video4x.ops.superresolve.tile import iter_tiles, merge_tile, pad_to_mod, suggest_tile
from video4x.runtime.resources import create_resource_sampler
from video4x.runtime.video_io import detect_video_fps, read_frames, write_video


@dataclass
class SuperResolveConfig:
    model: str = "x4plus"
    backend: str = "split-pipeline"
    platform: str | None = "auto"
    fp16: bool = False
    memory_mode: str = "auto"
    onnx_dir: Path | None = None
    tile: int = 0  # 0 = auto (prefer 512 when fixed NPU models exist)
    tile_pad: int = 10
    auto_tile_max: int = 256  # prefer 256 fixed NPU tiles when available; 512 also supported


def _pad_to_hw(patch: np.ndarray, th: int, tw: int) -> tuple[np.ndarray, int, int]:
    """Pad NCHW patch to exactly th×tw (reflect). Returns (padded, pad_h, pad_w)."""
    _, _, h, w = patch.shape
    pad_h, pad_w = th - h, tw - w
    if pad_h < 0 or pad_w < 0:
        raise ValueError(f"patch {h}x{w} larger than fixed tile {th}x{tw}")
    if pad_h == 0 and pad_w == 0:
        return patch, 0, 0
    return np.pad(patch, ((0, 0), (0, 0), (0, pad_h), (0, pad_w)), mode="reflect"), pad_h, pad_w


class SuperResolveEngine:
    """Frame / video Real-ESRGAN via ONNX Runtime."""

    name = "superresolve"

    def __init__(
        self,
        config: SuperResolveConfig | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._config = config or SuperResolveConfig()
        self._backend: SrFullBackend | SrSplitBackend | None = None
        self._on_progress = on_progress
        self._scale = int(MODEL_PRESETS[resolve_model_name(self._config.model)]["scale"])
        self._ready = False
        self._fixed_tile: int | None = None

    @property
    def scale(self) -> int:
        return self._scale

    def init(self) -> None:
        key = resolve_model_name(self._config.model)
        self._scale = int(MODEL_PRESETS[key]["scale"])
        root = Path(self._config.onnx_dir or default_onnx_root())
        tile = self._config.tile
        if tile == 0:
            # Prefer smallest available fixed tile (NPU-friendly)
            for cand in (256, 512, self._config.auto_tile_max):
                fixed = root / key / "fixed" / f"{cand}x{cand}" / "realesrgan_body.onnx"
                if fixed.is_file():
                    tile = int(cand)
                    break
            else:
                tile = self._config.auto_tile_max
        paths = resolve_sr_onnx_paths(root, key, tile=tile, prefer_fixed=True)
        self._fixed_tile = None
        if "fixed_tile" in paths:
            self._fixed_tile = int(str(paths.pop("fixed_tile")))
        self._backend = create_sr_backend(self._config.backend)
        self._backend.init(
            onnx_paths=paths,
            platform=self._config.platform,
            fp16=self._config.fp16,
            memory_mode=self._config.memory_mode,
        )
        self._ready = True

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        if not self._ready:
            self.init()
        assert self._backend is not None
        x = np.asarray(frame, dtype=np.float32)
        if x.ndim == 3:
            x = x[np.newaxis, ...]
        mod = 2 if self._scale == 2 else 1
        padded, pad_h, pad_w = pad_to_mod(x, mod)
        _, _, h, w = padded.shape
        tile = self._config.tile
        pad = self._config.tile_pad
        if self._fixed_tile:
            # Extracted patch is up to tile+2*pad; must fit fixed ONNX HxW.
            max_core = max(self._fixed_tile - 2 * pad, 32) if pad > 0 else self._fixed_tile
            if tile <= 0 or tile > max_core:
                tile = max_core
        elif tile == 0:
            tile = suggest_tile(h, w, max_side=self._config.auto_tile_max)
        scale = self._scale
        out_h, out_w = h * scale, w * scale
        canvas = np.zeros((1, 3, out_h, out_w), dtype=np.float32)
        for ey0, ey1, ex0, ex1, y, y1, x0, x1 in iter_tiles(h, w, tile, pad):
            patch = padded[:, :, ey0:ey1, ex0:ex1]
            ph, pw = patch.shape[2], patch.shape[3]
            if self._fixed_tile:
                patch, _, _ = _pad_to_hw(patch, self._fixed_tile, self._fixed_tile)
            hr = self._backend.run(patch)
            # Crop back to the extracted (unpadded-to-fixed) region size
            hr = hr[:, :, : ph * scale, : pw * scale]
            merge_tile(
                canvas,
                hr,
                scale=scale,
                ey0=ey0,
                ey1=ey1,
                ex0=ex0,
                ex1=ex1,
                y=y,
                y1=y1,
                x=x0,
                x1=x1,
            )
        if pad_h or pad_w:
            oh = (h - pad_h) * scale
            ow = (w - pad_w) * scale
            canvas = canvas[:, :, :oh, :ow]
        return canvas

    def process_pair(self, img0: np.ndarray, img1: np.ndarray, *, timestep: float = 0.5) -> np.ndarray:
        raise NotImplementedError("superresolve is a single-frame operator")

    def enhance_video(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        fps: float | None = None,
    ) -> dict:
        if not self._ready:
            self.init()
        inp = Path(input_path)
        out = Path(output_path)
        frames = list(read_frames(inp))
        if not frames:
            raise ValueError(f"No frames in {inp}")
        out_fps = float(fps) if fps is not None else detect_video_fps(inp)
        n = len(frames)

        tr = ProgressTracker(
            self._on_progress,
            sampler=create_resource_sampler(self._config.platform) if self._on_progress else None,
        )
        try:
            fb = ""
            if self._backend is not None:
                st0 = self._backend.stats()
                fb = getattr(st0, "fallback_reason", None) or ""
            tr.emit(
                ProgressEvent(
                    phase="init",
                    message=(
                        f"sr model={resolve_model_name(self._config.model)} "
                        f"fixed_tile={self._fixed_tile} {fb}"
                    ).strip(),
                    total=n,
                    mode=f"sr:{self._config.backend}",
                    providers=dict(self._backend.stats().providers) if self._backend else {},
                )
            )
            enhanced: list[np.ndarray] = []
            for i, fr in enumerate(frames):
                hr = self.process_frame(fr)
                enhanced.append(hr)
                st = self._backend.stats() if self._backend else None
                tr.emit(
                    ProgressEvent(
                        phase="superresolve",
                        message=f"frame {i + 1}/{n}",
                        current=i + 1,
                        total=n,
                        mode=f"sr:{self._config.backend}",
                        providers=dict(st.providers) if st else {},
                        gpu_hits=st.gpu_hits if st else 0,
                        npu_hits=st.npu_hits if st else 0,
                        last_ms=(st.total_ms / max(st.total_calls, 1)) if st else 0.0,
                        elapsed_s=tr.elapsed(),
                    )
                )
            _, _, oh, ow = enhanced[0].shape
            tr.emit(
                ProgressEvent(
                    phase="encode",
                    message=f"writing {out.name}",
                    current=n,
                    total=n,
                    elapsed_s=tr.elapsed(),
                )
            )
            write_video(out, (f for f in enhanced), fps=out_fps, width=ow, height=oh)
            tr.emit(
                ProgressEvent(
                    phase="done",
                    message="ok",
                    current=n,
                    total=n,
                    elapsed_s=tr.elapsed(),
                )
            )
            return {
                "output_frames": n,
                "scale": self._scale,
                "model": resolve_model_name(self._config.model),
                "fixed_tile": self._fixed_tile,
                "stats": self.stats().__dict__,
            }
        finally:
            tr.close()

    def stats(self) -> OperatorStats:
        st = self._backend.stats() if self._backend else None
        return OperatorStats(
            name=self.name,
            total_calls=st.total_calls if st else 0,
            total_ms=st.total_ms if st else 0.0,
            gpu_hits=st.gpu_hits if st else 0,
            npu_hits=st.npu_hits if st else 0,
            providers=dict(st.providers) if st else {},
            extra={
                "model": resolve_model_name(self._config.model),
                "scale": self._scale,
                "fixed_tile": self._fixed_tile,
                "fallback": getattr(st, "fallback_reason", None) if st else None,
            },
        )

    def close(self) -> None:
        if self._backend is not None:
            self._backend.close()
            self._backend = None
        self._ready = False

    def __enter__(self) -> Self:
        self.init()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
