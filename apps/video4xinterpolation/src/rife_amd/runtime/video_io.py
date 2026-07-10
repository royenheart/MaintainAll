"""Video decode/encode helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Iterator

import numpy as np

try:
    import av
except ImportError as exc:
    raise ImportError("pyav required for video_io") from exc


def read_frames(path: Path, max_frames: int | None = None) -> Generator[np.ndarray, None, None]:
    """Yield RGB float32 NCHW [0,1] frames."""
    container = av.open(str(path))
    count = 0
    for frame in container.decode(video=0):
        img = frame.to_ndarray(format="rgb24").astype(np.float32) / 255.0
        chw = np.transpose(img, (2, 0, 1))
        yield chw[np.newaxis, ...]
        count += 1
        if max_frames is not None and count >= max_frames:
            break
    container.close()


def frame_to_hwc_u8(fr: np.ndarray) -> np.ndarray:
    """Convert float32 CHW or NCHW [0,1] to uint8 HWC for encoding."""
    x = np.asarray(fr)
    if x.ndim == 4:
        if x.shape[0] != 1:
            raise ValueError(f"expected batch=1 NCHW, got shape {x.shape}")
        x = x[0]
    if x.ndim != 3:
        raise ValueError(f"expected CHW or NCHW frame, got shape {fr.shape}")
    # CHW (C,H,W) with C in {1,3,4}
    if x.shape[0] in (1, 3, 4):
        hwc = np.transpose(x, (1, 2, 0))
    elif x.shape[-1] in (1, 3, 4):
        hwc = x
    else:
        raise ValueError(f"cannot infer HWC layout from shape {x.shape}")
    return (np.clip(hwc, 0, 1) * 255.0).astype(np.uint8)


def write_video(
    path: Path,
    frames: Iterator[np.ndarray],
    fps: float,
    width: int,
    height: int,
) -> None:
    """Write float32 CHW or NCHW [0,1] frames to mp4 (libx264)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(path), mode="w")
    stream = container.add_stream("libx264", rate=int(round(fps)))
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    for fr in frames:
        hwc = frame_to_hwc_u8(fr)
        if hwc.shape[0] != height or hwc.shape[1] != width:
            raise ValueError(
                f"frame spatial size {hwc.shape[0]}x{hwc.shape[1]} != expected {height}x{width}"
            )
        video_frame = av.VideoFrame.from_ndarray(hwc, format="rgb24")
        for packet in stream.encode(video_frame):
            container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()


def frame_pairs(
    frames: list[np.ndarray],
) -> Generator[tuple[np.ndarray, np.ndarray, float], None, None]:
    """Generate (I0, I1, t) for 2x interpolation between consecutive frames."""
    for i in range(len(frames) - 1):
        yield frames[i], frames[i + 1], 0.5
