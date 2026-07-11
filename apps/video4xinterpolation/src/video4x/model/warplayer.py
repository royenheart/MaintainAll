""" Backward warping via grid_sample (Practical-RIFE compatible).

Default path uses ``flow*0+1`` so fixed-HW export does not bake giant Constants.
For VitisAI Stage-B export, set ``FORCE_ONES_LIKE=True`` so folding produces
ones/arange Constants that are then rewritten to ConstantOfShape (see onnx_rewrite).
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

# Set True only during Stage-B fixed-HW export (VitisAI-friendly fold → rewrite).
FORCE_ONES_LIKE = False


def warp(ten_input: torch.Tensor, ten_flow: torch.Tensor) -> torch.Tensor:
    """Warp *ten_input* with optical flow *ten_flow* (pixel units)."""
    flow_x = ten_flow[:, :1]
    if FORCE_ONES_LIKE:
        ones = torch.ones_like(flow_x)
    else:
        ones = flow_x * 0.0 + 1.0
    horiz = torch.cumsum(ones, dim=3) - 1.0  # 0 .. W-1
    vert = torch.cumsum(ones, dim=2) - 1.0  # 0 .. H-1
    w_m1 = torch.amax(horiz, dim=3, keepdim=True).clamp(min=1.0)
    h_m1 = torch.amax(vert, dim=2, keepdim=True).clamp(min=1.0)
    base = torch.cat([horiz / w_m1 * 2.0 - 1.0, vert / h_m1 * 2.0 - 1.0], dim=1)

    flow_norm = torch.cat(
        [
            ten_flow[:, 0:1] / (w_m1 / 2.0),
            ten_flow[:, 1:2] / (h_m1 / 2.0),
        ],
        dim=1,
    )
    grid = (base + flow_norm).permute(0, 2, 3, 1)
    return F.grid_sample(
        ten_input,
        grid,
        mode="bilinear",
        padding_mode="border",
        align_corners=True,
    )
