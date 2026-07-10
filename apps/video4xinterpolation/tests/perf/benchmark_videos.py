"""End-to-end video benchmark."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.perf


def test_video_benchmark_placeholder() -> None:
    """Run via: python scripts/interpolate.py in.mp4 out.mp4 --compare"""
    assert True
