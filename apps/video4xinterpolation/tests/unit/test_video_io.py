"""video_io frame layout tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from video4x.runtime.video_io import frame_to_hwc_u8, write_video

av = pytest.importorskip("av")


def test_frame_to_hwc_u8_chw() -> None:
    chw = np.zeros((3, 8, 12), dtype=np.float32)
    chw[0, 0, 0] = 1.0
    hwc = frame_to_hwc_u8(chw)
    assert hwc.shape == (8, 12, 3)
    assert hwc.dtype == np.uint8
    assert hwc[0, 0, 0] == 255


def test_frame_to_hwc_u8_nchw() -> None:
    nchw = np.zeros((1, 3, 8, 12), dtype=np.float32)
    nchw[0, 1, 0, 0] = 1.0
    hwc = frame_to_hwc_u8(nchw)
    assert hwc.shape == (8, 12, 3)
    assert hwc[0, 0, 1] == 255


def test_write_video_accepts_chw(tmp_path: Path) -> None:
    """Engine passes f[0] (CHW); must not index again as if NCHW."""
    frames = [np.random.rand(3, 16, 16).astype(np.float32) for _ in range(3)]
    path = tmp_path / "out.mp4"
    write_video(path, iter(frames), fps=10.0, width=16, height=16)
    assert path.exists() and path.stat().st_size > 0


def test_write_video_accepts_nchw(tmp_path: Path) -> None:
    frames = [np.random.rand(1, 3, 16, 16).astype(np.float32) for _ in range(2)]
    path = tmp_path / "out2.mp4"
    write_video(path, iter(frames), fps=10.0, width=16, height=16)
    assert path.exists() and path.stat().st_size > 0
