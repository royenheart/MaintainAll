"""Backend registry tests."""

from __future__ import annotations

import pytest

from rife_amd.runtime.backends.registry import create_backend, get_backend, list_backends


def test_list_backends() -> None:
    names = list_backends()
    for want in ("single-ep", "split-pipeline", "cpu-baseline", "dual-stream"):
        assert want in names


def test_unknown_backend() -> None:
    with pytest.raises(KeyError):
        get_backend("nonexistent-backend")


def test_create_cpu_baseline() -> None:
    bk = create_backend("cpu-baseline")
    assert bk.name == "cpu-baseline"
