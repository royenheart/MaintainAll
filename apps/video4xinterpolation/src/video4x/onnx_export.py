"""Export RIFE v4.26 to two-stage ONNX graphs."""

from __future__ import annotations

import argparse
from pathlib import Path

import onnx
import torch

from video4x.model import warplayer as warplayer_mod
from video4x.model.rife_hd_v4 import (
    IFNet,
    RIFEStageBlock234,
    RIFEStageEncodeBlock01,
    load_ifnet_from_pkl,
)
from video4x.onnx_rewrite import rewrite_spatial_constants_to_ops, summarize_large_constants
from video4x.runtime.resolutions import (
    DEFAULT_FIXED_SIZES,
    fixed_model_dir,
    parse_size_list,
    size_tag,
)

DEFAULT_PKL = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "RIFEv4.26_0921"
    / "train_log"
    / "flownet.pkl"
)

# Ryzen AI ORT historically caps IR ≤ 11
_MAX_IR_VERSION = 10


def _finalize_onnx(
    path: Path,
    *,
    fixed_hw: bool = False,
    height: int = 0,
    width: int = 0,
    rewrite_spatial: bool = False,
) -> None:
    model = onnx.load(str(path))
    if model.ir_version > _MAX_IR_VERSION:
        model.ir_version = _MAX_IR_VERSION
    if fixed_hw and height > 0 and width > 0:
        if rewrite_spatial:
            n = rewrite_spatial_constants_to_ops(model, height, width)
            leftover = summarize_large_constants(model)
            print(f"  rewrite {path.name}: {n} spatial Constant(s) → ConstantOfShape/CumSum")
            if leftover:
                print(f"  warning: large tensors remain in {path.name}: {leftover[:5]}")
        else:
            _strip_unused_spatial_initializers(model, height, width)
    onnx.save(model, str(path))
    onnx.checker.check_model(onnx.load(str(path)))


def _strip_unused_spatial_initializers(model: onnx.ModelProto, height: int, width: int) -> None:
    """Remove unused full-frame Constant initializers left by folding (if any)."""
    used = {inp for n in model.graph.node for inp in n.input if inp}
    spatial_dim_lists = (
        [1, 1, height, width],
        [1, 2, height, width],
        [1, 3, height, width],
        [1, 4, height, width],
    )
    keep = []
    for init in model.graph.initializer:
        dims = list(init.dims)
        if dims in spatial_dim_lists and init.name not in used:
            continue
        keep.append(init)
    if len(keep) != len(model.graph.initializer):
        del model.graph.initializer[:]
        model.graph.initializer.extend(keep)


def export_stages(
    pkl_path: Path,
    out_dir: Path,
    opset: int = 17,
    height: int = 64,
    width: int = 64,
    *,
    fixed_hw: bool = False,
) -> tuple[Path, Path]:
    """Export Stage A and Stage B ONNX models.

    ``fixed_hw=True``: no dynamic H/W (VitisAI-friendly). Filenames stay generic
    inside ``out_dir`` (use ``fixed/<HxW>/`` as out_dir for tiers).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device("cpu")
    ifnet = load_ifnet_from_pkl(str(pkl_path), device)

    stage_a = RIFEStageEncodeBlock01(ifnet).eval()
    stage_b = RIFEStageBlock234(ifnet).eval()

    img0 = torch.randn(1, 3, height, width)
    img1 = torch.randn(1, 3, height, width)
    ts = torch.full((1, 1, height, width), 0.5)

    with torch.no_grad():
        a_out = stage_a(img0, img1, ts)
        flow, mask, feat, w0, w1, f0, f1, ts_out = a_out
        _ = stage_b(img0, img1, flow, mask, feat, w0, w1, f0, f1, ts_out)

    stage_a_path = out_dir / "rife_stage_encode_block01.onnx"
    stage_b_path = out_dir / "rife_stage_block234.onnx"

    # Stage A (DML): no folding + slim warp — avoid HxW Constant bloat.
    # Stage B (VitisAI): ones_like + folding, then ConstantOfShape rewrite (slim + VAI-safe).
    a_fold = not fixed_hw
    b_fold = True
    _a_kw: dict = dict(opset_version=opset, do_constant_folding=a_fold, dynamo=False)
    _b_kw: dict = dict(opset_version=opset, do_constant_folding=b_fold, dynamo=False)

    a_dynamic = None
    b_dynamic = None
    if not fixed_hw:
        spatial = {
            "img0": {0: "batch", 2: "height", 3: "width"},
            "img1": {0: "batch", 2: "height", 3: "width"},
            "timestep": {0: "batch", 2: "height", 3: "width"},
        }
        a_dynamic = {
            **spatial,
            "flow": {0: "batch", 2: "height", 3: "width"},
            "mask": {0: "batch", 2: "height", 3: "width"},
            "feat": {0: "batch", 2: "height", 3: "width"},
            "warped_img0": {0: "batch", 2: "height", 3: "width"},
            "warped_img1": {0: "batch", 2: "height", 3: "width"},
            "f0": {0: "batch", 2: "height", 3: "width"},
            "f1": {0: "batch", 2: "height", 3: "width"},
            "timestep_out": {0: "batch", 2: "height", 3: "width"},
        }
        b_dynamic = {
            **spatial,
            "flow": {0: "batch", 2: "height", 3: "width"},
            "mask": {0: "batch", 2: "height", 3: "width"},
            "feat": {0: "batch", 2: "height", 3: "width"},
            "warped_img0": {0: "batch", 2: "height", 3: "width"},
            "warped_img1": {0: "batch", 2: "height", 3: "width"},
            "f0": {0: "batch", 2: "height", 3: "width"},
            "f1": {0: "batch", 2: "height", 3: "width"},
            "merged": {0: "batch", 2: "height", 3: "width"},
        }

    torch.onnx.export(
        stage_a,
        (img0, img1, ts),
        str(stage_a_path),
        input_names=["img0", "img1", "timestep"],
        output_names=[
            "flow",
            "mask",
            "feat",
            "warped_img0",
            "warped_img1",
            "f0",
            "f1",
            "timestep_out",
        ],
        dynamic_axes=a_dynamic,
        **_a_kw,
    )

    prev_ones = warplayer_mod.FORCE_ONES_LIKE
    try:
        # Fold ones/arange into Constants so VitisAI sees a stable graph shape,
        # then rewrite those Constants to ConstantOfShape (keeps file slim).
        warplayer_mod.FORCE_ONES_LIKE = bool(fixed_hw)
        torch.onnx.export(
            stage_b,
            (img0, img1, flow, mask, feat, w0, w1, f0, f1, ts_out),
            str(stage_b_path),
            input_names=[
                "img0",
                "img1",
                "flow",
                "mask",
                "feat",
                "warped_img0",
                "warped_img1",
                "f0",
                "f1",
                "timestep",
            ],
            output_names=["merged"],
            dynamic_axes=b_dynamic,
            **_b_kw,
        )
    finally:
        warplayer_mod.FORCE_ONES_LIKE = prev_ones

    _finalize_onnx(stage_a_path, fixed_hw=fixed_hw, height=height, width=width, rewrite_spatial=False)
    _finalize_onnx(
        stage_b_path,
        fixed_hw=fixed_hw,
        height=height,
        width=width,
        rewrite_spatial=bool(fixed_hw),
    )

    return stage_a_path, stage_b_path


def export_full(
    pkl_path: Path,
    out_dir: Path,
    opset: int = 17,
    height: int = 64,
    width: int = 64,
    *,
    fixed_hw: bool = False,
) -> Path:
    """Export single-graph IFNet wrapper for single-ep backend."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ifnet = load_ifnet_from_pkl(str(pkl_path), "cpu")

    class FullWrapper(torch.nn.Module):
        def __init__(self, net: IFNet) -> None:
            super().__init__()
            self.net = net

        def forward(self, img0: torch.Tensor, img1: torch.Tensor, timestep: torch.Tensor):
            x = torch.cat([img0, img1], dim=1)
            return self.net(x, timestep)

    wrapper = FullWrapper(ifnet).eval()
    img0 = torch.randn(1, 3, height, width)
    img1 = torch.randn(1, 3, height, width)
    ts = torch.full((1, 1, height, width), 0.5)

    out_path = out_dir / "rife_full.onnx"
    dyn = None
    if not fixed_hw:
        dyn = {
            "img0": {0: "batch", 2: "height", 3: "width"},
            "img1": {0: "batch", 2: "height", 3: "width"},
            "timestep": {0: "batch", 2: "height", 3: "width"},
            "merged": {0: "batch", 2: "height", 3: "width"},
        }
    torch.onnx.export(
        wrapper,
        (img0, img1, ts),
        str(out_path),
        input_names=["img0", "img1", "timestep"],
        output_names=["merged"],
        dynamic_axes=dyn,
        opset_version=opset,
        do_constant_folding=not fixed_hw,
        dynamo=False,
    )
    _finalize_onnx(out_path, fixed_hw=fixed_hw, height=height, width=width)
    return out_path


def export_fixed_tiers(
    pkl_path: Path,
    onnx_root: Path,
    sizes: list[tuple[int, int]] | None = None,
    opset: int = 17,
    *,
    full: bool = False,
) -> list[tuple[tuple[int, int], Path, Path]]:
    """Export fixed-HW Stage A/B under ``onnx_root/fixed/<HxW>/``."""
    sizes = list(sizes) if sizes is not None else list(DEFAULT_FIXED_SIZES)
    results: list[tuple[tuple[int, int], Path, Path]] = []
    for h, w in sizes:
        out_dir = fixed_model_dir(onnx_root, h, w)
        print(f"Exporting fixed {size_tag(h, w)} → {out_dir}")
        a, b = export_stages(pkl_path, out_dir, opset=opset, height=h, width=w, fixed_hw=True)
        if full:
            export_full(pkl_path, out_dir, opset=opset, height=h, width=w, fixed_hw=True)
        results.append(((h, w), a, b))
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export RIFE ONNX stages")
    parser.add_argument("--pkl", type=Path, default=DEFAULT_PKL)
    parser.add_argument("--out", type=Path, default=Path("models/onnx"))
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--full", action="store_true", help="Also export single-graph model")
    parser.add_argument(
        "--fixed-hw",
        action="store_true",
        help="Export without dynamic H/W (write into --out as-is)",
    )
    parser.add_argument(
        "--fixed-tiers",
        action="store_true",
        help="Export default fixed tiers under --out/fixed/<HxW>/",
    )
    parser.add_argument(
        "--sizes",
        default="",
        help="With --fixed-tiers: comma list HxW (default 736x1280,1088x1920)",
    )
    args = parser.parse_args(argv)

    if args.fixed_tiers:
        sizes = parse_size_list(args.sizes) if args.sizes else list(DEFAULT_FIXED_SIZES)
        for (h, w), a, b in export_fixed_tiers(
            args.pkl, args.out, sizes=sizes, opset=args.opset, full=args.full
        ):
            print(f"[{size_tag(h, w)}] Stage A: {a}")
            print(f"[{size_tag(h, w)}] Stage B: {b}")
        return

    a, b = export_stages(
        args.pkl,
        args.out,
        args.opset,
        args.height,
        args.width,
        fixed_hw=args.fixed_hw,
    )
    print(f"Stage A: {a}")
    print(f"Stage B: {b}")
    if args.full:
        full = export_full(
            args.pkl,
            args.out,
            args.opset,
            args.height,
            args.width,
            fixed_hw=args.fixed_hw,
        )
        print(f"Full:    {full}")


if __name__ == "__main__":
    main()
