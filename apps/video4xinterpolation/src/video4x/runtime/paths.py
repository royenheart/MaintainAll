"""ONNX model path helpers."""

from __future__ import annotations

from pathlib import Path


def default_onnx_paths(root: Path | None = None) -> dict[str, Path]:
    root = root or Path("models/onnx")
    return {
        "stage_a": root / "rife_stage_encode_block01.onnx",
        "stage_b": root / "rife_stage_block234.onnx",
        "stage_b_quant": root / "rife_stage_block234_quant.onnx",
        "full": root / "rife_full.onnx",
    }
