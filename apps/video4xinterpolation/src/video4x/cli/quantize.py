"""Quantize Stage B with AMD Quark or ORT static quant (per fixed size)."""

from __future__ import annotations

import argparse
from pathlib import Path

from video4x.quant.calibrate import generate_calibration_samples, save_calibration_npz
from video4x.quant.quark_quant import quantize_stage_b
from video4x.runtime.resolutions import (
    DEFAULT_FIXED_SIZES,
    fixed_onnx_paths,
    parse_size_list,
    size_tag,
)


def quantize_fixed_size(
    onnx_root: Path,
    height: int,
    width: int,
    *,
    num_pairs: int = 8,
) -> Path:
    paths = fixed_onnx_paths(onnx_root, height, width)
    if not paths["stage_a"].is_file() or not paths["stage_b"].is_file():
        raise FileNotFoundError(
            f"Missing fixed ONNX for {size_tag(height, width)} under {paths['stage_a'].parent}. "
            f"Run: python scripts/export_onnx.py --fixed-tiers"
        )
    calib = paths["stage_b"].parent / "calib_stage_b.npz"
    samples = generate_calibration_samples(
        paths["stage_a"],
        num_pairs=num_pairs,
        height=height,
        width=width,
    )
    save_calibration_npz(samples, calib)
    out = quantize_stage_b(paths["stage_b"], paths["stage_b_quant"], calib)
    # Calibration tensors are huge at 1080p; drop after successful quant.
    try:
        calib.unlink(missing_ok=True)
    except OSError:
        pass
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Quantize RIFE Stage B")
    parser.add_argument("--onnx-dir", type=Path, default=Path("models/onnx"))
    parser.add_argument(
        "--sizes",
        default="",
        help="Comma HxW list (default: 736x1280,1088x1920). Empty with --legacy for old paths.",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Quantize models/onnx/rife_stage_block234.onnx (dynamic / non-tier layout)",
    )
    parser.add_argument(
        "--stage-a",
        type=Path,
        default=None,
        help="Legacy: stage A path",
    )
    parser.add_argument(
        "--stage-b",
        type=Path,
        default=None,
        help="Legacy: stage B path",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Legacy: quantized output path",
    )
    parser.add_argument("--calib", type=Path, default=None)
    parser.add_argument("--num-pairs", type=int, default=8)
    args = parser.parse_args(argv)

    if args.legacy or args.stage_a or args.stage_b:
        stage_a = args.stage_a or (args.onnx_dir / "rife_stage_encode_block01.onnx")
        stage_b = args.stage_b or (args.onnx_dir / "rife_stage_block234.onnx")
        out = args.out or (args.onnx_dir / "rife_stage_block234_quant.onnx")
        calib = args.calib or (args.onnx_dir / "calib_stage_b.npz")
        samples = generate_calibration_samples(stage_a, num_pairs=args.num_pairs)
        save_calibration_npz(samples, calib)
        print(f"Calibration saved: {calib} ({len(samples)} samples)")
        path = quantize_stage_b(stage_b, out, calib)
        print(f"Quantized model: {path}")
        return

    sizes = parse_size_list(args.sizes) if args.sizes else list(DEFAULT_FIXED_SIZES)
    for h, w in sizes:
        print(f"Quantizing Stage B for {size_tag(h, w)} ...")
        out = quantize_fixed_size(args.onnx_dir, h, w, num_pairs=args.num_pairs)
        print(f"  → {out}")


if __name__ == "__main__":
    main()
