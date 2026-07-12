"""Inference engine upper-layer tests."""

from __future__ import annotations

import numpy as np
import pytest

from video4x.inference import (
    InferenceComparator,
    InferenceConfig,
    InferenceMode,
    RifeInferenceEngine,
)


@pytest.fixture
def inf_config(onnx_dir) -> InferenceConfig:
    return InferenceConfig(mode=InferenceMode.CPU_BASELINE, onnx_dir=onnx_dir)


def test_engine_switch_mode(inf_config: InferenceConfig) -> None:
    with RifeInferenceEngine(inf_config) as engine:
        assert engine.mode == "cpu-baseline"
        img0 = np.random.rand(1, 3, 64, 64).astype(np.float32)
        img1 = np.random.rand(1, 3, 64, 64).astype(np.float32)
        out = engine.interpolate(img0, img1)
        assert out.shape == (1, 3, 64, 64)

        engine.switch_mode(InferenceMode.SPLIT_PIPELINE)
        assert engine.mode == "split-pipeline"
        out2 = engine.interpolate(img0, img1)
        assert out2.shape == (1, 3, 64, 64)


def test_engine_use_fluent(inf_config: InferenceConfig) -> None:
    engine = RifeInferenceEngine(inf_config)
    engine.use(InferenceMode.CPU_BASELINE)
    assert engine.mode == "cpu-baseline"
    # ORT loads lazily in bind_onnx_for_hw / interpolate — not on switch_mode.
    assert engine.is_ready is False
    engine.close()


def test_comparator_benchmark(inf_config: InferenceConfig) -> None:
    comp = InferenceComparator(inf_config)
    results = comp.benchmark(
        modes=[InferenceMode.CPU_BASELINE, InferenceMode.SPLIT_PIPELINE],
        shape=(1, 3, 64, 64),
        iterations=2,
    )
    assert len(results) == 2
    assert results[0].error is None
