"""IFNet HDv3 (RIFE v4.26) — inference + staged export wrappers."""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from video4x.model.warplayer import warp


def conv(
    in_planes: int,
    out_planes: int,
    kernel_size: int = 3,
    stride: int = 1,
    padding: int = 1,
    dilation: int = 1,
) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(
            in_planes,
            out_planes,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            bias=True,
        ),
        nn.LeakyReLU(0.2, True),
    )


class Head(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.cnn0 = nn.Conv2d(3, 16, 3, 2, 1)
        self.cnn1 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn2 = nn.Conv2d(16, 16, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(16, 4, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.relu(self.cnn0(x))
        x = self.relu(self.cnn1(x))
        x = self.relu(self.cnn2(x))
        return self.cnn3(x)


class ResConv(nn.Module):
    def __init__(self, c: int, dilation: int = 1) -> None:
        super().__init__()
        self.conv = nn.Conv2d(c, c, 3, 1, dilation, dilation=dilation, groups=1)
        self.beta = nn.Parameter(torch.ones((1, c, 1, 1)), requires_grad=True)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(self.conv(x) * self.beta + x)


class IFBlock(nn.Module):
    def __init__(self, in_planes: int, c: int = 64) -> None:
        super().__init__()
        self.conv0 = nn.Sequential(
            conv(in_planes, c // 2, 3, 2, 1),
            conv(c // 2, c, 3, 2, 1),
        )
        self.convblock = nn.Sequential(*[ResConv(c) for _ in range(8)])
        self.lastconv = nn.Sequential(
            nn.ConvTranspose2d(c, 4 * 13, 4, 2, 1),
            nn.PixelShuffle(2),
        )

    def forward(
        self,
        x: torch.Tensor,
        flow: torch.Tensor | None = None,
        scale: float = 1,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        x = F.interpolate(x, scale_factor=1.0 / scale, mode="bilinear", align_corners=False)
        if flow is not None:
            flow_down = F.interpolate(
                flow, scale_factor=1.0 / scale, mode="bilinear", align_corners=False
            ) * (1.0 / scale)
            x = torch.cat((x, flow_down), dim=1)
        feat = self.conv0(x)
        feat = self.convblock(feat)
        tmp = self.lastconv(feat)
        tmp = F.interpolate(tmp, scale_factor=scale, mode="bilinear", align_corners=False)
        flow_delta = tmp[:, :4] * scale
        mask = tmp[:, 4:5]
        feat_out = tmp[:, 5:]
        return flow_delta, mask, feat_out


class IFNet(nn.Module):
    """Full RIFE IFNet for reference inference and export validation."""

    def __init__(self) -> None:
        super().__init__()
        self.block0 = IFBlock(7 + 8, c=192)
        self.block1 = IFBlock(8 + 4 + 8 + 8, c=128)
        self.block2 = IFBlock(8 + 4 + 8 + 8, c=96)
        self.block3 = IFBlock(8 + 4 + 8 + 8, c=64)
        self.block4 = IFBlock(8 + 4 + 8 + 8, c=32)
        self.encode = Head()

    def forward(
        self,
        x: torch.Tensor,
        timestep: torch.Tensor | float = 0.5,
        scale_list: list[float] | None = None,
    ) -> torch.Tensor:
        if scale_list is None:
            scale_list = [8, 4, 2, 1, 1]
        channel = x.shape[1] // 2
        img0 = x[:, :channel]
        img1 = x[:, channel : channel * 2]

        if not torch.is_tensor(timestep):
            ts = (x[:, :1].clone() * 0 + 1) * float(timestep)
        else:
            ts = timestep
        if ts.shape[-2:] != img0.shape[-2:]:
            ts = ts.repeat(1, 1, img0.shape[2], img0.shape[3])

        f0 = self.encode(img0[:, :3])
        f1 = self.encode(img1[:, :3])
        warped_img0 = img0
        warped_img1 = img1
        flow: torch.Tensor | None = None
        mask: torch.Tensor | None = None
        feat: torch.Tensor | None = None
        blocks = [self.block0, self.block1, self.block2, self.block3, self.block4]

        for i, block in enumerate(blocks):
            if flow is None:
                flow, mask, feat = block(
                    torch.cat((img0[:, :3], img1[:, :3], f0, f1, ts), dim=1),
                    None,
                    scale=scale_list[i],
                )
            else:
                wf0 = warp(f0, flow[:, :2])
                wf1 = warp(f1, flow[:, 2:4])
                fd, m0, feat = block(
                    torch.cat(
                        (warped_img0[:, :3], warped_img1[:, :3], wf0, wf1, ts, mask, feat),
                        dim=1,
                    ),
                    flow,
                    scale=scale_list[i],
                )
                mask = m0
                flow = flow + fd
            warped_img0 = warp(img0, flow[:, :2])
            warped_img1 = warp(img1, flow[:, 2:4])

        assert mask is not None
        merged = warped_img0 * torch.sigmoid(mask) + warped_img1 * (1 - torch.sigmoid(mask))
        return merged


class RIFEStageEncodeBlock01(nn.Module):
    """Stage A: Head.encode + block0 + block1 (GPU-heavy)."""

    def __init__(self, ifnet: IFNet) -> None:
        super().__init__()
        self.encode = ifnet.encode
        self.block0 = ifnet.block0
        self.block1 = ifnet.block1

    def forward(
        self,
        img0: torch.Tensor,
        img1: torch.Tensor,
        timestep: torch.Tensor,
    ) -> tuple[torch.Tensor, ...]:
        scale_list = [8, 4]
        ts = timestep
        if ts.dim() == 1 or ts.shape[-2:] != img0.shape[-2:]:
            ts = ts.reshape(-1, 1, 1, 1).expand(-1, 1, img0.shape[2], img0.shape[3])

        f0 = self.encode(img0)
        f1 = self.encode(img1)
        warped_img0 = img0
        warped_img1 = img1
        flow: torch.Tensor | None = None
        mask: torch.Tensor | None = None
        feat: torch.Tensor | None = None

        for i, block in enumerate([self.block0, self.block1]):
            if flow is None:
                flow, mask, feat = block(
                    torch.cat((img0, img1, f0, f1, ts), dim=1),
                    None,
                    scale=scale_list[i],
                )
            else:
                wf0 = warp(f0, flow[:, :2])
                wf1 = warp(f1, flow[:, 2:4])
                fd, m0, feat = block(
                    torch.cat(
                        (warped_img0, warped_img1, wf0, wf1, ts, mask, feat),
                        dim=1,
                    ),
                    flow,
                    scale=scale_list[i],
                )
                mask = m0
                flow = flow + fd
            warped_img0 = warp(img0, flow[:, :2])
            warped_img1 = warp(img1, flow[:, 2:4])

        assert flow is not None and mask is not None and feat is not None
        return flow, mask, feat, warped_img0, warped_img1, f0, f1, ts


class RIFEStageBlock234(nn.Module):
    """Stage B: block2 + block3 + block4 + merge (NPU candidate)."""

    def __init__(self, ifnet: IFNet) -> None:
        super().__init__()
        self.block2 = ifnet.block2
        self.block3 = ifnet.block3
        self.block4 = ifnet.block4

    def forward(
        self,
        img0: torch.Tensor,
        img1: torch.Tensor,
        flow: torch.Tensor,
        mask: torch.Tensor,
        feat: torch.Tensor,
        warped_img0: torch.Tensor,
        warped_img1: torch.Tensor,
        f0: torch.Tensor,
        f1: torch.Tensor,
        timestep: torch.Tensor,
    ) -> torch.Tensor:
        scale_list = [2, 1, 1]
        ts = timestep
        blocks = [self.block2, self.block3, self.block4]

        for i, block in enumerate(blocks):
            wf0 = warp(f0, flow[:, :2])
            wf1 = warp(f1, flow[:, 2:4])
            fd, m0, feat = block(
                torch.cat(
                    (warped_img0, warped_img1, wf0, wf1, ts, mask, feat),
                    dim=1,
                ),
                flow,
                scale=scale_list[i],
            )
            mask = m0
            flow = flow + fd
            warped_img0 = warp(img0, flow[:, :2])
            warped_img1 = warp(img1, flow[:, 2:4])

        merged = warped_img0 * torch.sigmoid(mask) + warped_img1 * (1 - torch.sigmoid(mask))
        return merged


def load_ifnet_from_pkl(pkl_path: str, device: torch.device | str = "cpu") -> IFNet:
    """Load flownet.pkl weights into IFNet."""
    net = IFNet()
    state = torch.load(pkl_path, map_location=device, weights_only=True)
    if any(k.startswith("module.") for k in state):
        cleaned = {k.replace("module.", ""): v for k, v in state.items()}
    else:
        cleaned = state
    model_keys = set(net.state_dict().keys())
    cleaned = {k: v for k, v in cleaned.items() if k in model_keys}
    net.load_state_dict(cleaned, strict=True)
    net.eval()
    return net
