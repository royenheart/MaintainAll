"""Stage split vs full IFNet consistency."""

from __future__ import annotations

import numpy as np
import torch

from video4x.model.rife_hd_v4 import (
    IFNet,
    RIFEStageBlock234,
    RIFEStageEncodeBlock01,
    load_ifnet_from_pkl,
)


def test_stage_consistency(pkl_path) -> None:
    ifnet = load_ifnet_from_pkl(str(pkl_path))
    stage_a = RIFEStageEncodeBlock01(ifnet).eval()
    stage_b = RIFEStageBlock234(ifnet).eval()

    img0 = torch.rand(1, 3, 64, 64)
    img1 = torch.rand(1, 3, 64, 64)
    ts = torch.full((1, 1, 64, 64), 0.5)
    x = torch.cat([img0, img1], dim=1)

    with torch.no_grad():
        full = ifnet(x, ts)
        a_out = stage_a(img0, img1, ts)
        flow, mask, feat, w0, w1, f0, f1, ts_out = a_out
        split = stage_b(img0, img1, flow, mask, feat, w0, w1, f0, f1, ts_out)

    assert torch.allclose(full, split, atol=1e-3), (
        f"max diff {(full - split).abs().max().item()}"
    )
