"""Export Real-ESRGAN RRDBNet to ONNX (full + body/upsample; fixed tiles for NPU)."""

from __future__ import annotations

import argparse
from pathlib import Path

import torch

from video4x.ops.superresolve.install import download_model, weight_path, weights_dir
from video4x.ops.superresolve.model import (
    MODEL_PRESETS,
    RRDBBody,
    RRDBUpsample,
    build_rrdbnet,
    load_rrdbnet_weights,
    resolve_model_name,
)

# VitisAI-friendly fixed tile (matches default auto_tile_max / CLI --tile)
DEFAULT_FIXED_TILES = (256, 512)


def default_onnx_root() -> Path:
    return weights_dir().parent / "onnx" / "realesrgan"


def model_onnx_dir(model_name: str, root: Path | None = None) -> Path:
    key = resolve_model_name(model_name)
    d = (root or default_onnx_root()) / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _export_one(
    net: torch.nn.Module,
    *,
    dest: Path,
    height: int,
    width: int,
    opset: int,
    dynamic: bool,
) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, height, width, dtype=torch.float32)
    full_path = dest / "realesrgan_full.onnx"
    body_path = dest / "realesrgan_body.onnx"
    up_path = dest / "realesrgan_upsample.onnx"

    dyn_lr = {"lr": {2: "H", 3: "W"}, "hr": {2: "H_out", 3: "W_out"}} if dynamic else None
    dyn_body = {"lr": {2: "H", 3: "W"}, "feat": {2: "H", 3: "W"}} if dynamic else None
    dyn_up = {"feat": {2: "H", 3: "W"}, "hr": {2: "H_out", 3: "W_out"}} if dynamic else None

    with torch.no_grad():
        torch.onnx.export(
            net,
            dummy,
            str(full_path),
            input_names=["lr"],
            output_names=["hr"],
            dynamic_axes=dyn_lr,
            opset_version=opset,
            do_constant_folding=True,
        )
        body = RRDBBody(net)
        feat = body(dummy)
        torch.onnx.export(
            body,
            dummy,
            str(body_path),
            input_names=["lr"],
            output_names=["feat"],
            dynamic_axes=dyn_body,
            opset_version=opset,
            do_constant_folding=True,
        )
        up = RRDBUpsample(net)
        torch.onnx.export(
            up,
            feat,
            str(up_path),
            input_names=["feat"],
            output_names=["hr"],
            dynamic_axes=dyn_up,
            opset_version=opset,
            do_constant_folding=True,
        )
    return {"full": full_path, "body": body_path, "upsample": up_path}


def export_model(
    model_name: str,
    *,
    out_dir: Path | None = None,
    height: int = 64,
    width: int = 64,
    opset: int = 17,
    download: bool = True,
    fixed_tiles: tuple[int, ...] | list[int] | None = DEFAULT_FIXED_TILES,
) -> dict[str, Path | int]:
    key = resolve_model_name(model_name)
    meta = MODEL_PRESETS[key]
    scale = int(meta["scale"])
    if download:
        pth = download_model(key)
    else:
        pth = weight_path(key)
        if not pth.exists():
            raise FileNotFoundError(f"Missing weights: {pth}")

    net = build_rrdbnet(key)
    load_rrdbnet_weights(net, pth)
    net.eval()

    if scale == 2 and (height % 2 or width % 2):
        height += height % 2
        width += width % 2

    dest = model_onnx_dir(key, out_dir)
    # Dynamic (GPU-friendly fallback) + fixed tiles (NPU)
    paths = _export_one(net, dest=dest, height=height, width=width, opset=opset, dynamic=True)
    for tile in fixed_tiles or ():
        t = int(tile)
        if scale == 2 and t % 2:
            t += 1
        fixed_dir = dest / "fixed" / f"{t}x{t}"
        _export_one(net, dest=fixed_dir, height=t, width=t, opset=opset, dynamic=False)
        paths[f"fixed_{t}"] = fixed_dir  # type: ignore[assignment]
    paths["scale"] = scale  # type: ignore[assignment]
    return paths  # type: ignore[return-value]


def resolve_sr_onnx_paths(
    onnx_dir: Path,
    model_name: str,
    *,
    tile: int | None = None,
    prefer_fixed: bool = True,
) -> dict[str, Path]:
    """Resolve ONNX paths; prefer fixed/{tile}x{tile} for VitisAI when available."""
    key = resolve_model_name(model_name)
    base = Path(onnx_dir)
    roots = [base / key, base]

    if prefer_fixed and tile and tile > 0:
        for root in roots:
            fixed = root / "fixed" / f"{tile}x{tile}"
            body = fixed / "realesrgan_body.onnx"
            up = fixed / "realesrgan_upsample.onnx"
            full = fixed / "realesrgan_full.onnx"
            if body.is_file() and up.is_file():
                out: dict[str, Path] = {"body": body, "upsample": up, "fixed_tile": Path(str(tile))}
                if full.is_file():
                    out["full"] = full
                return out

    for d in roots:
        full = d / "realesrgan_full.onnx"
        body = d / "realesrgan_body.onnx"
        up = d / "realesrgan_upsample.onnx"
        if full.is_file() or (body.is_file() and up.is_file()):
            out = {}
            if full.is_file():
                out["full"] = full
            if body.is_file():
                out["body"] = body
            if up.is_file():
                out["upsample"] = up
            return out
    raise FileNotFoundError(
        f"No Real-ESRGAN ONNX for '{key}' under {onnx_dir}. "
        f"Run: video4x export realesrgan --models {key}"
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Export Real-ESRGAN to ONNX")
    p.add_argument("--models", default="x2plus,x4plus,x4plus_anime")
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--height", type=int, default=64)
    p.add_argument("--width", type=int, default=64)
    p.add_argument(
        "--fixed-tiles",
        default="512",
        help="Comma list of fixed HxW tiles for VitisAI (default 512). Empty to skip.",
    )
    p.add_argument("--no-download", action="store_true")
    args = p.parse_args(argv)
    tiles = [int(x) for x in args.fixed_tiles.split(",") if x.strip()] if args.fixed_tiles else []
    for name in [x.strip() for x in args.models.split(",") if x.strip()]:
        paths = export_model(
            name,
            out_dir=args.out_dir,
            height=args.height,
            width=args.width,
            download=not args.no_download,
            fixed_tiles=tiles,
        )
        print(f"Exported {name}: {paths}")


if __name__ == "__main__":
    main()
