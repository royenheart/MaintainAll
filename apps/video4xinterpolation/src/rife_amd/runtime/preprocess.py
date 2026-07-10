"""Spatial pad/crop so RIFE stages see H,W multiples of 32."""

from __future__ import annotations

import numpy as np

# scale_list starts at 8 and IFBlock does two stride-2 convs → /32.
RIFE_ALIGN = 32


def pad_to_multiple(
    x: np.ndarray,
    multiple: int = RIFE_ALIGN,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Pad NCHW array on bottom/right to a multiple of *multiple*.

    Returns (padded contiguous array, (orig_h, orig_w)).
    """
    if x.ndim != 4:
        raise ValueError(f"expected NCHW, got shape {x.shape}")
    _, _, h, w = x.shape
    ph = (multiple - h % multiple) % multiple
    pw = (multiple - w % multiple) % multiple
    if ph or pw:
        x = np.pad(x, ((0, 0), (0, 0), (0, ph), (0, pw)), mode="edge")
    return np.ascontiguousarray(x, dtype=np.float32), (h, w)


def crop_hw(x: np.ndarray, height: int, width: int) -> np.ndarray:
    """Crop NCHW (or CHW) tensor back to original spatial size."""
    return x[..., :height, :width]


def pack_frame_batch(
    frames: list[np.ndarray],
    multiple: int = RIFE_ALIGN,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Pad every frame once and stack into one contiguous (N,3,H',W') buffer.

    Host-side batching: avoids re-padding on each pair. Device-resident /
    IOBinding zero-copy is a separate path (not implemented here).
    """
    if not frames:
        raise ValueError("pack_frame_batch: empty frame list")
    chw_list: list[np.ndarray] = []
    orig_hw: tuple[int, int] | None = None
    for i, fr in enumerate(frames):
        padded, hw = pad_to_multiple(fr, multiple)
        if orig_hw is None:
            orig_hw = hw
        elif hw != orig_hw:
            raise ValueError(f"frame {i} size {hw} != first frame {orig_hw}")
        if padded.shape[0] != 1:
            raise ValueError(f"frame {i}: expected batch=1, got {padded.shape}")
        chw_list.append(padded[0])
    assert orig_hw is not None
    batch = np.ascontiguousarray(np.stack(chw_list, axis=0), dtype=np.float32)
    return batch, orig_hw
