"""RRDBNet matching BasicSR / Real-ESRGAN weight layouts."""

from __future__ import annotations

from typing import Any

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover
    raise ImportError("torch required for Real-ESRGAN model export") from exc


def make_layer(block: type[nn.Module], n_layers: int, **kwargs: Any) -> nn.Sequential:
    return nn.Sequential(*[block(**kwargs) for _ in range(n_layers)])


def pixel_unshuffle(x: torch.Tensor, scale: int) -> torch.Tensor:
    """Downsample spatially, expand channels (inverse of pixel shuffle)."""
    b, c, h, w = x.shape
    if h % scale != 0 or w % scale != 0:
        raise ValueError(f"H/W must be divisible by {scale}, got {h}x{w}")
    x = x.view(b, c, h // scale, scale, w // scale, scale)
    x = x.permute(0, 1, 3, 5, 2, 4).contiguous()
    return x.view(b, c * scale * scale, h // scale, w // scale)


class ResidualDenseBlock(nn.Module):
    def __init__(self, num_feat: int = 64, num_grow_ch: int = 32) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
        self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
        self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, num_feat: int = 64, num_grow_ch: int = 32) -> None:
        super().__init__()
        self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
        self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.rdb1(x)
        out = self.rdb2(out)
        out = self.rdb3(out)
        return out * 0.2 + x


class RRDBNet(nn.Module):
    """ESRGAN / Real-ESRGAN generator."""

    def __init__(
        self,
        num_in_ch: int = 3,
        num_out_ch: int = 3,
        scale: int = 4,
        num_feat: int = 64,
        num_block: int = 23,
        num_grow_ch: int = 32,
    ) -> None:
        super().__init__()
        self.scale = scale
        in_ch = num_in_ch
        if scale == 2:
            in_ch = num_in_ch * 4
        elif scale == 1:
            in_ch = num_in_ch * 16
        self.conv_first = nn.Conv2d(in_ch, num_feat, 3, 1, 1)
        self.body = make_layer(RRDB, num_block, num_feat=num_feat, num_grow_ch=num_grow_ch)
        self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
        self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def _prep(self, x: torch.Tensor) -> torch.Tensor:
        if self.scale == 2:
            return pixel_unshuffle(x, scale=2)
        if self.scale == 1:
            return pixel_unshuffle(x, scale=4)
        return x

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        feat = self.conv_first(self._prep(x))
        body_feat = self.conv_body(self.body(feat))
        feat = feat + body_feat
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


class RRDBBody(nn.Module):
    """Stage A: prep + conv_first + RRDB body + residual (NPU candidate)."""

    def __init__(self, net: RRDBNet) -> None:
        super().__init__()
        self.scale = net.scale
        self.conv_first = net.conv_first
        self.body = net.body
        self.conv_body = net.conv_body

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.scale == 2:
            feat = pixel_unshuffle(x, scale=2)
        elif self.scale == 1:
            feat = pixel_unshuffle(x, scale=4)
        else:
            feat = x
        feat = self.conv_first(feat)
        body_feat = self.conv_body(self.body(feat))
        return feat + body_feat


class RRDBUpsample(nn.Module):
    """Stage B: upsample + HR + last (GPU / DML)."""

    def __init__(self, net: RRDBNet) -> None:
        super().__init__()
        self.conv_up1 = net.conv_up1
        self.conv_up2 = net.conv_up2
        self.conv_hr = net.conv_hr
        self.conv_last = net.conv_last
        self.lrelu = net.lrelu

    def forward(self, feat: torch.Tensor) -> torch.Tensor:
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


# Official model presets (name → ctor kwargs + download URL)
MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "x2plus": {
        "file": "RealESRGAN_x2plus.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        "scale": 2,
        "num_block": 23,
        "aliases": ("RealESRGAN_x2plus", "x2"),
    },
    "x4plus": {
        "file": "RealESRGAN_x4plus.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "scale": 4,
        "num_block": 23,
        "aliases": ("RealESRGAN_x4plus", "x4"),
    },
    "x4plus_anime": {
        "file": "RealESRGAN_x4plus_anime_6B.pth",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        "scale": 4,
        "num_block": 6,
        "aliases": ("RealESRGAN_x4plus_anime_6B", "anime", "x4plus_anime_6B"),
    },
}


def resolve_model_name(name: str) -> str:
    key = name.strip().lower().replace("-", "_")
    if key in MODEL_PRESETS:
        return key
    for k, meta in MODEL_PRESETS.items():
        aliases = {a.lower() for a in meta.get("aliases", ())}
        if key in aliases or key == meta["file"].lower().removesuffix(".pth"):
            return k
    raise KeyError(f"Unknown Real-ESRGAN model '{name}'. Choose: {', '.join(MODEL_PRESETS)}")


def build_rrdbnet(model_name: str) -> RRDBNet:
    key = resolve_model_name(model_name)
    meta = MODEL_PRESETS[key]
    return RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        scale=int(meta["scale"]),
        num_feat=64,
        num_block=int(meta["num_block"]),
        num_grow_ch=32,
    )


def load_rrdbnet_weights(model: RRDBNet, pth: Any) -> RRDBNet:
    """Load official .pth (params_ema or params or raw state_dict)."""
    from pathlib import Path

    path = Path(pth)
    ckpt = torch.load(str(path), map_location="cpu", weights_only=False)
    if isinstance(ckpt, dict):
        if "params_ema" in ckpt:
            state = ckpt["params_ema"]
        elif "params" in ckpt:
            state = ckpt["params"]
        else:
            state = ckpt
    else:
        state = ckpt
    model.load_state_dict(state, strict=True)
    model.eval()
    return model
