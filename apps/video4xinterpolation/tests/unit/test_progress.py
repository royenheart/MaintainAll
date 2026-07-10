"""Progress reporter unit tests."""

from __future__ import annotations

import io

import numpy as np

from rife_amd.inference import (
    InferenceConfig,
    InferenceMode,
    ProgressEvent,
    RifeInferenceEngine,
    format_progress_line,
)
from rife_amd.inference.progress import StdoutProgressReporter


def test_format_progress_line_includes_resources() -> None:
    ev = ProgressEvent(
        phase="interpolate",
        message="pair 2/10",
        current=2,
        total=10,
        mode="split-pipeline",
        device_hint="mixed",
        providers={"stage_a": "DmlExecutionProvider", "stage_b": "VitisAIExecutionProvider"},
        last_ms=400,
        avg_ms=420,
        gpu_hits=2,
        npu_hits=2,
        stage_a_ms=200,
        stage_b_ms=220,
        eta_s=3.36,
        cpu_percent=80.0,
        gpu_percent=15.0,
    )
    line = format_progress_line(ev)
    assert "[interpolate]" in line
    assert "2/10" in line
    assert "ep=[stage_a=Dml,stage_b=VitisAI]" in line
    assert "gpu_hits=2" in line
    assert "ETA=" in line
    assert "res=[CPU=80%,GPU=15%,NPU=n/a]" in line


def test_engine_emits_progress_on_interpolate_frames(onnx_dir) -> None:
    events: list[ProgressEvent] = []
    cfg = InferenceConfig(mode=InferenceMode.CPU_BASELINE, onnx_dir=onnx_dir)
    with RifeInferenceEngine(cfg, on_progress=events.append) as engine:
        frames = [np.random.rand(1, 3, 64, 64).astype(np.float32) for _ in range(3)]
        out = engine.interpolate_frames(frames)
    assert len(out) == 5  # 3 input + 2 mids
    phases = [e.phase for e in events]
    assert "init" in phases
    assert phases.count("interpolate") == 2
    assert events[-1].providers.get("session") == "CPUExecutionProvider"
    assert events[-1].current == 2
    assert events[-1].total == 2


def test_stdout_reporter_writes(onnx_dir) -> None:
    buf = io.StringIO()
    rep = StdoutProgressReporter(stream=buf)
    cfg = InferenceConfig(mode=InferenceMode.CPU_BASELINE, onnx_dir=onnx_dir)
    with RifeInferenceEngine(cfg, on_progress=rep) as engine:
        frames = [np.random.rand(1, 3, 64, 64).astype(np.float32) for _ in range(2)]
        engine.interpolate_frames(frames)
    text = buf.getvalue()
    assert "[init]" in text
    assert "[interpolate]" in text
