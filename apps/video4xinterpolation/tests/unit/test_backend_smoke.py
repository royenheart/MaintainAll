"""Smoke tests per backend."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from video4x.runtime.backends.base import BackendConfig
from video4x.runtime.backends.dual_stream import DualStreamBackend
from video4x.runtime.backends.registry import create_backend
from video4x.runtime.paths import default_onnx_paths
from video4x.runtime.platform import HostPlatform


@pytest.fixture
def cfg(onnx_dir) -> BackendConfig:
    return BackendConfig(onnx_paths=default_onnx_paths(onnx_dir))


@pytest.mark.parametrize("name", ["cpu-baseline", "single-ep", "split-pipeline", "dual-stream"])
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


def test_dual_stream_pairs_smoke(cfg: BackendConfig) -> None:
    backend = create_backend("dual-stream")
    backend.init(cfg)
    assert backend.name == "dual-stream"
    frames = [np.random.rand(1, 3, 64, 64).astype(np.float32) for _ in range(4)]
    pairs = [(frames[i], frames[i + 1]) for i in range(3)]
    mids = list(backend.interpolate_pairs(pairs, timestep=0.5))
    assert len(mids) == 3
    for mid in mids:
        assert mid.shape == (1, 3, 64, 64)
        assert mid.dtype == np.float32
    backend.teardown()


def test_dual_stream_overlap_scheduling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stage A(N+1) should run while Stage B(N) is in flight on Windows."""
    backend = DualStreamBackend()
    events: list[tuple[str, float]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2, timeout=5.0)

    def fake_init(self, cfg: BackendConfig) -> None:  # noqa: ARG001
        self.supports_gpu = False
        self.supports_npu = False
        self.memory_mode = "host"
        self.memory_detail = "test"
        self.providers = {"stage_a": "CPUExecutionProvider", "stage_b": "CPUExecutionProvider"}
        self.fallback_reason = None
        self.stage_a = MagicMock()
        self.stage_b = MagicMock()
        self.stage_a.active_provider = "CPUExecutionProvider"
        self.stage_b.active_provider = "CPUExecutionProvider"
        self.stage_a.last_elapsed_ms = MagicMock(return_value=10.0)
        self.stage_b.last_elapsed_ms = MagicMock(return_value=20.0)

    def fake_prepare(self, img0, img1, timestep=0.5):  # noqa: ARG001
        from video4x.runtime.backends._split_sessions import PreparedPair

        return PreparedPair(img0=img0, img1=img1, timestep=np.zeros((1, 1, 1, 1), np.float32))

    a_calls = {"n": 0}
    b_calls = {"n": 0}

    def fake_stage_a(self, prep, **_kwargs):  # noqa: ARG001
        a_calls["n"] += 1
        idx = a_calls["n"]
        with lock:
            events.append((f"A{idx}_start", time.perf_counter()))
        if idx == 2:
            # Only A2 rendezvous with B1 — later pairs must not reuse the barrier.
            barrier.wait()
        time.sleep(0.05)
        with lock:
            events.append((f"A{idx}_end", time.perf_counter()))
        return {
            "flow": np.zeros((1, 4, 1, 1), np.float32),
            "mask": np.zeros((1, 1, 1, 1), np.float32),
            "feat": np.zeros((1, 1, 1, 1), np.float32),
            "warped_img0": prep.img0,
            "warped_img1": prep.img1,
            "f0": np.zeros((1, 1, 1, 1), np.float32),
            "f1": np.zeros((1, 1, 1, 1), np.float32),
        }

    def fake_stage_b(self, prep, a_out, **_kwargs):  # noqa: ARG001
        b_calls["n"] += 1
        idx = b_calls["n"]
        with lock:
            events.append((f"B{idx}_start", time.perf_counter()))
        if idx == 1:
            barrier.wait()
        time.sleep(0.05)
        with lock:
            events.append((f"B{idx}_end", time.perf_counter()))
        return np.zeros_like(prep.img0)

    monkeypatch.setattr(
        "video4x.runtime.backends.dual_stream.resolve_platform",
        lambda _=None: HostPlatform.WINDOWS,
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.SplitSessions.init",
        fake_init,
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.SplitSessions.prepare_pair",
        fake_prepare,
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.SplitSessions.run_stage_a",
        fake_stage_a,
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.SplitSessions.run_stage_b",
        fake_stage_b,
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.SplitSessions.stage_a_ms",
        lambda self: 10.0,
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.SplitSessions.stage_b_ms",
        lambda self: 20.0,
    )

    backend.init(BackendConfig())
    assert backend.supports_pair_pipeline is True

    pairs = [
        (np.zeros((1, 3, 4, 4), np.float32), np.ones((1, 3, 4, 4), np.float32)),
        (np.ones((1, 3, 4, 4), np.float32), np.zeros((1, 3, 4, 4), np.float32)),
        (np.zeros((1, 3, 4, 4), np.float32), np.ones((1, 3, 4, 4), np.float32)),
    ]
    mids = list(backend.interpolate_pairs(pairs))
    assert len(mids) == 3
    names = [e[0] for e in events]
    # B1 must start before A2 ends (overlap); barrier enforces concurrent rendezvous.
    assert "B1_start" in names and "A2_start" in names
    b1_start = next(t for n, t in events if n == "B1_start")
    a2_end = next(t for n, t in events if n == "A2_end")
    b1_end = next(t for n, t in events if n == "B1_end")
    a2_start = next(t for n, t in events if n == "A2_start")
    assert a2_start < b1_end
    assert b1_start < a2_end
    backend.teardown()


def test_dual_stream_non_windows_fallback(monkeypatch: pytest.MonkeyPatch, cfg: BackendConfig) -> None:
    monkeypatch.setattr(
        "video4x.runtime.backends.dual_stream.resolve_platform",
        lambda _=None: HostPlatform.LINUX,
    )
    backend = create_backend("dual-stream")
    backend.init(cfg)
    assert backend.supports_pair_pipeline is False
    assert backend.stats().fallback_reason is not None
    assert "Windows-only" in (backend.stats().fallback_reason or "")
    img0 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    img1 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    out = backend.interpolate(img0, img1)
    assert out.shape == (1, 3, 64, 64)
    backend.teardown()
