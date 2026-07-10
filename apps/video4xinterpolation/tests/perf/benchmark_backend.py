"""Performance benchmarks (not in default pytest suite)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.perf


def test_benchmark_import() -> None:
    from scripts import benchmark  # noqa: F401
