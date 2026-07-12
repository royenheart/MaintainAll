"""IOBinding shared-buffer zero-copy path tests."""

from __future__ import annotations

import numpy as np
import pytest

from video4x.runtime.backends._split_sessions import SplitSessions
from video4x.runtime.backends.base import BackendConfig
from video4x.runtime.backends.registry import create_backend
from video4x.runtime.paths import default_onnx_paths
from video4x.runtime.session import IoBindingBundle, OrtSession, make_ort_slot


@pytest.fixture
def force_cpu_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid DirectML/VitisAI init & probe hangs in unit tests."""
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.default_stage_ep_preferences",
        lambda _plat: (["cpu"], ["cpu"]),
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.probe_vitisai_model_safe",
        lambda *_a, **_k: (False, "skipped in unit test"),
    )
    monkeypatch.setattr(
        "video4x.runtime.backends._split_sessions.probe_execution_providers",
        lambda: type(
            "P",
            (),
            {
                "rocm": False,
                "directml": False,
                "vitisai": False,
                "cpu": True,
                "providers": ("CPUExecutionProvider",),
                "rocm_gpu_agent": False,
            },
        )(),
    )


@pytest.fixture
def cfg_iobind(onnx_dir, force_cpu_stages) -> BackendConfig:
    del force_cpu_stages
    return BackendConfig(
        onnx_paths=default_onnx_paths(onnx_dir),
        ep_preference=["cpu"],
        platform="windows",
        memory_mode="host",
        use_iobinding=True,
    )


def test_ort_slot_shares_data_ptr() -> None:
    slot = make_ort_slot("x", (1, 3, 4, 4))
    assert slot.data_ptr == int(slot.array.ctypes.data)
    assert int(slot.numpy_view().ctypes.data) == slot.data_ptr
    slot.write(np.ones((1, 3, 4, 4), np.float32))
    assert float(slot.numpy_view().reshape(-1)[0]) == 1.0


def test_split_iobinding_same_ptr_a_to_b(cfg_iobind: BackendConfig) -> None:
    """Intermediate OrtValues keep the same data_ptr across Stage A → B."""
    sessions = SplitSessions()
    sessions.init(cfg_iobind)
    img0 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    img1 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    prep = sessions.prepare_pair(img0, img1, 0.5)
    assert sessions.use_iobinding is True
    assert prep.slot is not None
    ptrs_before = prep.slot.intermediate_ptrs()

    a_out = sessions.run_stage_a(prep)
    ptrs_after_a = prep.slot.intermediate_ptrs()
    assert ptrs_before == ptrs_after_a
    for name, view in a_out.items():
        assert int(view.ctypes.data) == ptrs_after_a[name]

    # Stage B must consume the same OrtValue buffers (no intermediate np.copy).
    slot = prep.slot
    merged = sessions.run_stage_b(prep, a_out)
    assert merged.shape == (1, 3, 64, 64)
    assert prep.slot is None  # released after B
    # Slot returned to pool; ptrs still stable on the recycled object.
    assert slot.intermediate_ptrs() == ptrs_before
    sessions.close()


def test_split_iobinding_matches_classic(cfg_iobind: BackendConfig) -> None:
    sessions_io = SplitSessions()
    sessions_io.init(cfg_iobind)
    cfg_classic = BackendConfig(
        onnx_paths=cfg_iobind.onnx_paths,
        ep_preference=["cpu"],
        platform="windows",
        memory_mode="host",
        use_iobinding=False,
    )
    sessions_np = SplitSessions()
    sessions_np.init(cfg_classic)

    rng = np.random.default_rng(0)
    img0 = rng.random((1, 3, 64, 64), dtype=np.float32)
    img1 = rng.random((1, 3, 64, 64), dtype=np.float32)

    prep_io = sessions_io.prepare_pair(img0, img1, 0.5)
    a_io = sessions_io.run_stage_a(prep_io)
    m_io = sessions_io.run_stage_b(prep_io, a_io)

    prep_np = sessions_np.prepare_pair(img0, img1, 0.5)
    a_np = sessions_np.run_stage_a(prep_np)
    m_np = sessions_np.run_stage_b(prep_np, a_np)

    assert sessions_io.use_iobinding is True
    assert sessions_np.use_iobinding is False
    np.testing.assert_allclose(m_io, m_np, rtol=1e-5, atol=1e-5)
    sessions_io.close()
    sessions_np.close()


def test_iobinding_fallback_on_bind_failure(
    cfg_iobind: BackendConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    sessions = SplitSessions()
    sessions.init(cfg_iobind)

    def fail_bind(*, inputs, outputs):  # noqa: ARG001
        return IoBindingBundle(
            inputs=inputs,
            outputs=outputs,
            binding=None,
            fallback_reason="CPUExecutionProvider bind_ortvalue failed: simulated",
        )

    assert sessions.stage_a is not None
    # Force re-init of slots path via shape ensure after clearing state.
    sessions.use_iobinding = False
    sessions._want_iobinding = True
    sessions._slots.clear()
    sessions._free_slots.clear()
    sessions._slot_shape = None

    monkeypatch.setattr(
        sessions.stage_a,
        "probe_iobinding",
        lambda feeds, memory=None: (
            True,
            None,
            {
                "flow": (1, 4, 64, 64),
                "mask": (1, 1, 64, 64),
                "feat": (1, 8, 64, 64),
                "warped_img0": (1, 3, 64, 64),
                "warped_img1": (1, 3, 64, 64),
                "f0": (1, 4, 64, 64),
                "f1": (1, 4, 64, 64),
                "timestep_out": (1, 1, 64, 64),
            },
        ),
    )
    assert sessions.stage_b is not None
    monkeypatch.setattr(
        sessions.stage_b,
        "probe_iobinding",
        lambda feeds, memory=None: (True, None, {"merged": (1, 3, 64, 64)}),
    )
    monkeypatch.setattr(
        sessions.stage_a,
        "run",
        lambda feeds: {
            "flow": np.zeros((1, 4, 64, 64), np.float32),
            "mask": np.zeros((1, 1, 64, 64), np.float32),
            "feat": np.zeros((1, 8, 64, 64), np.float32),
            "warped_img0": feeds["img0"],
            "warped_img1": feeds["img1"],
            "f0": np.zeros((1, 4, 64, 64), np.float32),
            "f1": np.zeros((1, 4, 64, 64), np.float32),
            "timestep_out": feeds["timestep"],
        },
    )
    monkeypatch.setattr(sessions.stage_a, "bind_slots", fail_bind)

    img0 = np.zeros((1, 3, 64, 64), np.float32)
    img1 = np.ones((1, 3, 64, 64), np.float32)
    prep = sessions.prepare_pair(img0, img1, 0.5)
    assert sessions.use_iobinding is False
    assert prep.slot is None
    assert sessions.fallback_reason is not None
    assert "IOBinding fallback" in sessions.fallback_reason
    assert "fallback:" in sessions.iobinding_detail
    sessions.close()


def test_stage_a_fill_slot_preserves_ptrs(cfg_iobind: BackendConfig) -> None:
    """Overlap-safe path: classic A → write slots; B still sees same data_ptr."""
    sessions = SplitSessions()
    sessions.init(cfg_iobind)
    img0 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    img1 = np.random.rand(1, 3, 64, 64).astype(np.float32)
    prep = sessions.prepare_pair(img0, img1, 0.5)
    assert prep.slot is not None
    ptrs = prep.slot.intermediate_ptrs()

    a_out = sessions.run_stage_a(prep, avoid_concurrent_iobinding=True)
    assert prep.slot.intermediate_ptrs() == ptrs
    for name, view in a_out.items():
        assert int(view.ctypes.data) == ptrs[name]

    merged = sessions.run_stage_b(prep, a_out)
    assert merged.shape == (1, 3, 64, 64)
    sessions.close()


def test_dual_stream_pairs_with_iobinding(cfg_iobind: BackendConfig) -> None:
    """IOBinding dual-stream runs pairs sequentially but keeps zero-copy on."""
    backend = create_backend("dual-stream")
    backend.init(cfg_iobind)
    rng = np.random.default_rng(1)
    pairs = [
        (
            rng.random((1, 3, 64, 64), dtype=np.float32),
            rng.random((1, 3, 64, 64), dtype=np.float32),
        )
        for _ in range(8)
    ]
    mids = list(backend.interpolate_pairs(pairs, timestep=0.5))
    assert len(mids) == 8
    assert all(m.shape == (1, 3, 64, 64) for m in mids)
    st = backend.stats()
    assert st.use_iobinding is True
    assert st.fallback_reason is not None
    assert "overlap disabled under IOBinding" in st.fallback_reason
    backend.teardown()


def test_backend_smoke_with_iobinding(cfg_iobind: BackendConfig) -> None:
    for name in ("split-pipeline", "dual-stream"):
        backend = create_backend(name)
        backend.init(cfg_iobind)
        out = backend.interpolate(
            np.random.rand(1, 3, 64, 64).astype(np.float32),
            np.random.rand(1, 3, 64, 64).astype(np.float32),
        )
        assert out.shape == (1, 3, 64, 64)
        st = backend.stats()
        assert st.use_iobinding is True
        assert "iobinding=on" in st.memory_detail
        backend.teardown()


def test_session_probe_iobinding(onnx_dir) -> None:
    path = default_onnx_paths(onnx_dir)["stage_a"]
    sess = OrtSession(path, ep_preference=["cpu"])
    feeds = {
        "img0": np.random.rand(1, 3, 64, 64).astype(np.float32),
        "img1": np.random.rand(1, 3, 64, 64).astype(np.float32),
        "timestep": np.full((1, 1, 64, 64), 0.5, np.float32),
    }
    ok, reason, shapes = sess.probe_iobinding(feeds, memory=None)
    assert ok is True
    assert reason is None
    assert "flow" in shapes
    sess.close()
