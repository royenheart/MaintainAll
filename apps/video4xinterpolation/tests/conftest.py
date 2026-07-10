"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PKL_PATH = PROJECT_ROOT / "models" / "RIFEv4.26_0921" / "train_log" / "flownet.pkl"
ONNX_DIR = PROJECT_ROOT / "models" / "onnx"


@pytest.fixture(scope="session")
def pkl_path() -> Path:
    if not PKL_PATH.exists():
        pytest.skip(f"Model weights missing: {PKL_PATH}")
    return PKL_PATH


@pytest.fixture(scope="session")
def onnx_dir(pkl_path: Path) -> Path:
    ONNX_DIR.mkdir(parents=True, exist_ok=True)
    stage_a = ONNX_DIR / "rife_stage_encode_block01.onnx"
    if not stage_a.exists():
        from rife_amd.onnx_export import export_full, export_stages

        export_stages(pkl_path, ONNX_DIR, height=64, width=64)
        export_full(pkl_path, ONNX_DIR, height=64, width=64)
    return ONNX_DIR
