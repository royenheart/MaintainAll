"""ONNX export schema checks."""

from __future__ import annotations

from pathlib import Path

import onnx
import pytest

from rife_amd.onnx_export import export_stages


def test_onnx_checker(onnx_dir: Path) -> None:
    for name in (
        "rife_stage_encode_block01.onnx",
        "rife_stage_block234.onnx",
        "rife_full.onnx",
    ):
        path = onnx_dir / name
        assert path.exists(), name
        onnx.checker.check_model(onnx.load(str(path)))


def test_stage_io_names(onnx_dir: Path) -> None:
    a = onnx.load(str(onnx_dir / "rife_stage_encode_block01.onnx"))
    b = onnx.load(str(onnx_dir / "rife_stage_block234.onnx"))
    a_ins = {i.name for i in a.graph.input}
    assert {"img0", "img1", "timestep"} <= a_ins
    b_outs = {o.name for o in b.graph.output}
    assert "merged" in b_outs


def test_fixed_hw_export_has_static_spatial(pkl_path: Path, tmp_path: Path) -> None:
    a, b = export_stages(pkl_path, tmp_path, height=64, width=64, fixed_hw=True, opset=17)
    model = onnx.load(str(a))
    img0 = next(i for i in model.graph.input if i.name == "img0")
    dims = [d.dim_value for d in img0.type.tensor_type.shape.dim]
    # NCHW with concrete H,W (batch may be 1)
    assert dims[2] == 64 and dims[3] == 64
    assert b.exists()


def test_fixed_hw_export_avoids_fullframe_constants(pkl_path: Path, tmp_path: Path) -> None:
    """Stage A fixed export must not bake (1,1,H,W) float blobs (DML path)."""
    h, w = 128, 256
    a, b = export_stages(pkl_path, tmp_path / "f", height=h, width=w, fixed_hw=True, opset=17)
    model = onnx.load(str(a))
    big = []
    for init in model.graph.initializer:
        if list(init.dims) in ([1, 1, h, w], [1, 2, h, w]):
            big.append(init.name)
    for n in model.graph.node:
        if n.op_type != "Constant":
            continue
        for attr in n.attribute:
            if attr.name == "value" and list(attr.t.dims) in ([1, 1, h, w], [1, 2, h, w]):
                big.append(n.name)
    assert not big, f"unexpected full-frame constants on Stage A: {big}"
    assert a.stat().st_size < 40_000_000
    assert b.exists()
