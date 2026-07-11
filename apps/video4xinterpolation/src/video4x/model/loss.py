"""Training-only loss stubs — not used during ONNX export."""

from __future__ import annotations

import torch
import torch.nn as nn


class EPE(nn.Module):
    def forward(self, flow: torch.Tensor, gt: torch.Tensor) -> torch.Tensor:
        return (flow - gt).abs().mean()


class SOBEL(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(1, 1, 3, padding=1, bias=False)

    def forward(self, x: torch.Tensor, _dummy: torch.Tensor) -> torch.Tensor:
        return self.conv(x)
