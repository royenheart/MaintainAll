"""Smoke tests per backend."""

from __future__ import annotations

import numpy as np
import pytest

from video4x.runtime.backends.base import BackendConfig
from video4x.runtime.backends.registry import create_backend
from video4x.runtime.paths import default_onnx_paths


@pytest.fixture
def cfg(onnx_dir) -> BackendConfig:
    return BackendConfig(onnx_paths=default_onnx_paths(onnx_dir))


@pytest.mark.parametrize("name", ["cpu-baseline", "single-ep", "split-pipeline"])
def test_backend_smoke(name: str, cfg: BackendConfig) -> None:
    backend = create_backend(name)
    backend.init(cfg)
    img0 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    img1 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    out = backend.interpolate(img0, img1)
    assert out.shape == (1, 3, 64, 64)
    assert out.dtype == np.float32
    assert out.min() >= -0.05 and out.max() <= 1.05
    backend.teardown()


def test_dual_stream_not_implemented(cfg: BackendConfig) -> None:
    backend = create_backend("dual-stream")
    with pytest.raises(NotImplementedError):
        backend.init(cfg)
