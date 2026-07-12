"""Split stage timing benchmark."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.perf


def test_split_stages_placeholder() -> None:
    """Run via: python scripts/benchmark.py --backends split-pipeline"""
    assert True
