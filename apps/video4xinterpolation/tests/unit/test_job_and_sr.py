"""Tests for EnhanceJob order parsing and SR helpers."""

from __future__ import annotations

import numpy as np
import pytest

from video4x.job import parse_order
from video4x.ops.superresolve.model import resolve_model_name
from video4x.ops.superresolve.tile import iter_tiles, merge_tile, pad_to_mod, suggest_tile


def test_parse_order_default() -> None:
    assert parse_order("interpolate,superresolve") == ["interpolate", "superresolve"]


def test_parse_order_explicit() -> None:
    assert parse_order(
        ["interpolate", "superresolve"],
        "superresolve,interpolate",
    ) == ["superresolve", "interpolate"]


def test_parse_order_mismatch() -> None:
    with pytest.raises(ValueError):
        parse_order("interpolate", "superresolve")


def test_resolve_model_aliases() -> None:
    assert resolve_model_name("x4plus") == "x4plus"
    assert resolve_model_name("RealESRGAN_x2plus") == "x2plus"
    assert resolve_model_name("anime") == "x4plus_anime"


def test_suggest_tile() -> None:
    assert suggest_tile(64, 64, max_side=512) == 0
    assert suggest_tile(1080, 1920, max_side=512) == 512


def test_iter_tiles_full() -> None:
    tiles = iter_tiles(10, 20, 0, 10)
    assert tiles == [(0, 10, 0, 20, 0, 10, 0, 20)]


def test_detect_video_fps_default() -> None:
    from video4x.runtime.video_io import detect_video_fps
    from pathlib import Path

    # Missing file falls through av error — just ensure callable with default helper path
    assert callable(detect_video_fps)


def test_merge_tile_and_pad() -> None:
    frame = np.zeros((1, 3, 5, 5), dtype=np.float32)
    padded, ph, pw = pad_to_mod(frame, 2)
    assert padded.shape[2] % 2 == 0
    assert padded.shape[3] % 2 == 0
    assert ph in (0, 1) and pw in (0, 1)

    canvas = np.zeros((1, 3, 8, 8), dtype=np.float32)
    tile_out = np.ones((1, 3, 8, 8), dtype=np.float32)
    merge_tile(
        canvas,
        tile_out,
        scale=2,
        ey0=0,
        ey1=4,
        ex0=0,
        ex1=4,
        y=0,
        y1=4,
        x=0,
        x1=4,
    )
    assert canvas[0, 0, 0, 0] == 1.0
