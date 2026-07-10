"""Quark quant optional test."""

from __future__ import annotations

import pytest


def test_quark_import_optional() -> None:
    try:
        import quark.onnx  # noqa: F401
    except ImportError:
        pytest.skip("amd-quark not installed")
