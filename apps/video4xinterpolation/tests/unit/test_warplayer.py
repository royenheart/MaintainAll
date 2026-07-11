"""Warp consistency: torch vs reference grid_sample; ONNX dynamic H/W."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torch.nn as nn

from video4x.model.warplayer import warp


def test_warp_identity_flow() -> None:
    img = torch.rand(1, 3, 32, 32)
    flow = torch.zeros(1, 2, 32, 32)
    out = warp(img, flow)
    assert torch.allclose(out, img, atol=1e-5)


def test_warp_numpy_roundtrip() -> None:
    img = torch.rand(1, 3, 16, 16)
    flow = torch.randn(1, 2, 16, 16) * 0.5
    out = warp(img, flow)
    assert out.shape == img.shape
    assert out.min() >= -0.01 and out.max() <= 1.01


def test_warp_matches_linspace_grid() -> None:
    """Dynamic cumsum grid must match classic linspace(-1,1) + align_corners."""
    torch.manual_seed(0)
    img = torch.rand(1, 3, 40, 56)
    flow = torch.randn(1, 2, 40, 56) * 2.0

    # Reference: linspace grid (export-hostile but numerically correct)
    h, w = 40, 56
    horiz = torch.linspace(-1.0, 1.0, w).view(1, 1, 1, w).expand(1, -1, h, w)
    vert = torch.linspace(-1.0, 1.0, h).view(1, 1, h, 1).expand(1, -1, h, w)
    base = torch.cat([horiz, vert], dim=1)
    flow_norm = torch.cat(
        [
            flow[:, 0:1] / ((w - 1.0) / 2.0),
            flow[:, 1:2] / ((h - 1.0) / 2.0),
        ],
        dim=1,
    )
    grid = (base + flow_norm).permute(0, 2, 3, 1)
    ref = torch.nn.functional.grid_sample(
        img, grid, mode="bilinear", padding_mode="border", align_corners=True
    )
    out = warp(img, flow)
    assert torch.allclose(out, ref, atol=1e-5, rtol=1e-5)


def test_warp_onnx_runs_at_different_resolution() -> None:
    """Export at 32x32 must run at 48x64 without baked-grid Add broadcast errors."""

    class WarpMod(nn.Module):
        def forward(self, x: torch.Tensor, flow: torch.Tensor) -> torch.Tensor:
            return warp(x, flow)

    model = WarpMod().eval()
    x0 = torch.rand(1, 3, 32, 32)
    f0 = torch.zeros(1, 2, 32, 32)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "warp.onnx"
        torch.onnx.export(
            model,
            (x0, f0),
            str(path),
            input_names=["x", "flow"],
            output_names=["y"],
            dynamic_axes={
                "x": {0: "b", 2: "h", 3: "w"},
                "flow": {0: "b", 2: "h", 3: "w"},
                "y": {0: "b", 2: "h", 3: "w"},
            },
            opset_version=17,
            do_constant_folding=True,
            dynamo=False,
        )
        m = onnx.load(str(path))
        # No fixed HxW identity grids from export size
        for node in m.graph.node:
            if node.op_type != "Constant":
                continue
            for attr in node.attribute:
                if attr.name != "value":
                    continue
                dims = list(attr.t.dims)
                if len(dims) == 4 and dims[1] == 2 and dims[2] == 32 and dims[3] == 32:
                    raise AssertionError(f"baked warp grid Constant still present: {dims}")

        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        x1 = np.random.rand(1, 3, 48, 64).astype(np.float32)
        f1 = np.zeros((1, 2, 48, 64), dtype=np.float32)
        y = sess.run(None, {"x": x1, "flow": f1})[0]
        assert y.shape == (1, 3, 48, 64)
        assert np.allclose(y, x1, atol=1e-4)
