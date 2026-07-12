"""Fixed-resolution tier helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from video4x.runtime.resolutions import (
    DEFAULT_FIXED_SIZES,
    fixed_onnx_paths,
    match_fixed_size,
    parse_size,
    parse_size_list,
    resolve_onnx_paths_for_hw,
    size_tag,
)


def test_default_tiers() -> None:
    assert (736, 1280) in DEFAULT_FIXED_SIZES
    assert (1088, 1920) in DEFAULT_FIXED_SIZES


def test_parse_size_list() -> None:
    assert parse_size("1088x1920") == (1088, 1920)
    assert parse_size_list("736x1280,1088x1920") == [(736, 1280), (1088, 1920)]


def test_match_fixed_size() -> None:
    assert match_fixed_size(1088, 1920) == (1088, 1920)
    with pytest.raises(ValueError, match="No fixed-tier"):
        match_fixed_size(1120, 1920)


def test_resolve_prefers_fixed(tmp_path: Path) -> None:
    paths = fixed_onnx_paths(tmp_path, 1088, 1920)
    paths["stage_a"].parent.mkdir(parents=True)
    paths["stage_a"].write_bytes(b"a")
    paths["stage_b"].write_bytes(b"b")
    got, hw, kind = resolve_onnx_paths_for_hw(tmp_path, 1088, 1920)
    assert kind == "fixed"
    assert hw == (1088, 1920)
    assert got["stage_a"] == paths["stage_a"]


def test_resolve_falls_back_dynamic(onnx_dir: Path) -> None:
    # 64x64 is not a default tier; session fixtures provide dynamic graphs
    got, hw, kind = resolve_onnx_paths_for_hw(onnx_dir, 64, 64)
    assert kind == "dynamic"
    assert got["stage_a"].is_file()
    assert size_tag(*hw) == "64x64"
