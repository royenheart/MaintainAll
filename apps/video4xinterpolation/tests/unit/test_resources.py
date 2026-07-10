"""Resource sampler factory / null sampler tests."""

from __future__ import annotations

from rife_amd.inference.progress import ProgressEvent, ProgressTracker, format_progress_line
from rife_amd.runtime.resources import NullResourceSampler, create_resource_sampler
from rife_amd.runtime.resources.base import ResourceSample


def test_create_resource_sampler_returns_protocol() -> None:
    s = create_resource_sampler("auto")
    sample = s.sample()
    assert isinstance(sample, ResourceSample)
    s.close()


def test_null_sampler() -> None:
    s = NullResourceSampler()
    assert s.sample().detail == "null"


def test_format_includes_resource_block() -> None:
    line = format_progress_line(
        ProgressEvent(
            phase="interpolate",
            current=1,
            total=2,
            cpu_percent=55.0,
            gpu_percent=12.0,
            npu_percent=40.0,
            mem_rss_mb=1024.0,
        )
    )
    assert "res=[CPU=55%,GPU=12%,NPU=40%,RSS=1024MB]" in line


def test_format_npu_na_when_vitisai_but_no_counter() -> None:
    line = format_progress_line(
        ProgressEvent(
            phase="interpolate",
            providers={"stage_a": "DmlExecutionProvider", "stage_b": "VitisAIExecutionProvider"},
            cpu_percent=10.0,
            gpu_percent=0.0,
            npu_percent=None,
            mem_rss_mb=100.0,
        )
    )
    assert "NPU=n/a" in line
    assert "GPU=0%" in line


def test_tracker_attaches_sampler_fields() -> None:
    class Fake:
        def sample(self) -> ResourceSample:
            return ResourceSample(cpu_percent=10.0, gpu_percent=20.0, npu_percent=None, mem_rss_mb=100.0)

        def close(self) -> None:
            return None

    events: list[ProgressEvent] = []
    tr = ProgressTracker(events.append, sampler=Fake())
    tr.emit(ProgressEvent(phase="decode", message="x"))
    tr.close()
    assert events[0].cpu_percent == 10.0
    assert events[0].gpu_percent == 20.0
    assert events[0].mem_rss_mb == 100.0
