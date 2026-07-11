"""Frame padding helpers for RIFE (spatial dims must be multiples of 32)."""

from __future__ import annotations

import numpy as np

from video4x.runtime.preprocess import crop_hw, pack_frame_batch, pad_to_multiple


def test_pad_to_multiple_1080() -> None:
    x = np.zeros((1, 3, 1080, 1920), dtype=np.float32)
    padded, (h, w) = pad_to_multiple(x, 32)
    assert (h, w) == (1080, 1920)
    assert padded.shape == (1, 3, 1088, 1920)
    assert padded.flags["C_CONTIGUOUS"]
    cropped = crop_hw(padded, h, w)
    assert cropped.shape == (1, 3, 1080, 1920)
    assert np.array_equal(cropped, x)


def test_pad_to_multiple_already_aligned() -> None:
    x = np.zeros((1, 3, 64, 128), dtype=np.float32)
    padded, orig = pad_to_multiple(x, 32)
    assert padded.shape == x.shape
    assert orig == (64, 128)


def test_pack_frame_batch_once() -> None:
    frames = [np.random.rand(1, 3, 1080, 1920).astype(np.float32) for _ in range(4)]
    batch, (h, w) = pack_frame_batch(frames)
    assert batch.shape == (4, 3, 1088, 1920)
    assert batch.flags["C_CONTIGUOUS"]
    assert (h, w) == (1080, 1920)
    # views into batch are usable as NCHW pairs without copy of full video
    pair0 = batch[0:1]
    pair1 = batch[1:2]
    assert pair0.shape == (1, 3, 1088, 1920)
    assert pair0.flags["C_CONTIGUOUS"] or pair0.base is not None
