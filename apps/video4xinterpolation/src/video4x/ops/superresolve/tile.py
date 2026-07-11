"""Tile helpers for large-frame Real-ESRGAN inference."""

from __future__ import annotations

import math

import numpy as np


def suggest_tile(height: int, width: int, *, max_side: int = 512) -> int:
    """Return tile size (0 = full frame) when either side exceeds max_side."""
    if max(height, width) <= max_side:
        return 0
    return max_side


def iter_tiles(
    h: int,
    w: int,
    tile: int,
    tile_pad: int,
) -> list[tuple[int, int, int, int, int, int, int, int]]:
    """
    Yield tile boxes.

    Each item: (y0, y1, x0, x1, iy0, iy1, ix0, ix1)
    - y0:y1,x0:x1 = region to extract from input (with pad, clipped)
    - iy0:iy1,ix0:ix1 = where the *core* (unpadded) lands in the output canvas
      expressed in input-space coordinates (caller scales by net scale).
    """
    if tile <= 0:
        return [(0, h, 0, w, 0, h, 0, w)]
    tiles: list[tuple[int, int, int, int, int, int, int, int]] = []
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            y1 = min(y + tile, h)
            x1 = min(x + tile, w)
            ey0 = max(y - tile_pad, 0)
            ex0 = max(x - tile_pad, 0)
            ey1 = min(y1 + tile_pad, h)
            ex1 = min(x1 + tile_pad, w)
            tiles.append((ey0, ey1, ex0, ex1, y, y1, x, x1))
    return tiles


def merge_tile(
    canvas: np.ndarray,
    tile_out: np.ndarray,
    *,
    scale: int,
    ey0: int,
    ey1: int,
    ex0: int,
    ex1: int,
    y: int,
    y1: int,
    x: int,
    x1: int,
) -> None:
    """Paste upscaled tile core into canvas (NCHW)."""
    # Offsets of core inside padded tile (input space)
    top = y - ey0
    left = x - ex0
    # Output crop in upscaled tile
    ot0 = top * scale
    ol0 = left * scale
    oh = (y1 - y) * scale
    ow = (x1 - x) * scale
    cy0 = y * scale
    cx0 = x * scale
    canvas[:, :, cy0 : cy0 + oh, cx0 : cx0 + ow] = tile_out[:, :, ot0 : ot0 + oh, ol0 : ol0 + ow]


def pad_to_mod(frame: np.ndarray, mod: int) -> tuple[np.ndarray, int, int]:
    """Pad NCHW frame so H,W divisible by mod. Returns (padded, pad_h, pad_w)."""
    if mod <= 1:
        return frame, 0, 0
    _, _, h, w = frame.shape
    nh = int(math.ceil(h / mod) * mod)
    nw = int(math.ceil(w / mod) * mod)
    pad_h, pad_w = nh - h, nw - w
    if pad_h == 0 and pad_w == 0:
        return frame, 0, 0
    return np.pad(frame, ((0, 0), (0, 0), (0, pad_h), (0, pad_w)), mode="reflect"), pad_h, pad_w
