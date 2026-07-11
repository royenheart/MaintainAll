"""AMD Quark / ORT static quantization for Stage B."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def quantize_stage_b(
    input_onnx: Path,
    output_onnx: Path,
    calibration_npz: Path | None = None,
) -> Path:
    """
    Quantize Stage B to QDQ INT8 weights (AIE-ML / VitisAI friendly).

    Prefers ``amd-quark``; falls back to ``onnxruntime.quantization`` static quant.
    """
    output_onnx.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _quantize_quark(input_onnx, output_onnx, calibration_npz)
    except ImportError:
        return _quantize_ort(input_onnx, output_onnx, calibration_npz)


def _quantize_quark(
    input_onnx: Path,
    output_onnx: Path,
    calibration_npz: Path | None,
) -> Path:
    from quark.onnx import quantize as quark_quantize  # type: ignore[import-untyped]

    kwargs: dict = {
        "input_model_path": str(input_onnx),
        "output_model_path": str(output_onnx),
        "quant_format": "QDQ",
        "activation_type": "fp16",
        "weight_type": "int8",
    }
    if calibration_npz and calibration_npz.exists():
        kwargs["calibration_data_path"] = str(calibration_npz)
    quark_quantize(**kwargs)
    return output_onnx


def _quantize_ort(
    input_onnx: Path,
    output_onnx: Path,
    calibration_npz: Path | None,
) -> Path:
    from onnxruntime.quantization import (  # type: ignore[import-untyped]
        CalibrationDataReader,
        QuantFormat,
        QuantType,
        quantize_static,
    )

    class _Reader(CalibrationDataReader):
        def __init__(self, samples: list[dict[str, np.ndarray]]) -> None:
            self._samples = samples
            self._i = 0

        def get_next(self) -> dict[str, np.ndarray] | None:
            if self._i >= len(self._samples):
                return None
            item = self._samples[self._i]
            self._i += 1
            return item

    samples = _load_calib_samples(calibration_npz)
    if not samples:
        raise RuntimeError(
            "ORT static quant needs calibration npz. Generate via quantize CLI first."
        )
    reader = _Reader(samples)
    # Only quantize weight-heavy matmul/conv ops; Resize/GridSample break under QDQ here.
    quantize_static(
        model_input=str(input_onnx),
        model_output=str(output_onnx),
        calibration_data_reader=reader,
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=False,
        op_types_to_quantize=["Conv", "MatMul", "Gemm"],
    )
    return output_onnx


def _load_calib_samples(path: Path | None) -> list[dict[str, np.ndarray]]:
    if path is None or not path.exists():
        return []
    data = np.load(path, allow_pickle=True)
    raw = data["samples"]
    out: list[dict[str, np.ndarray]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append({k: np.asarray(v) for k, v in item.items()})
        else:
            # object array of dicts
            d = item.item() if hasattr(item, "item") else item
            out.append({k: np.asarray(v) for k, v in d.items()})
    return out
