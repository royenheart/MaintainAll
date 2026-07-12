"""Unit tests for platform EP defaults."""

from __future__ import annotations

from video4x.inference.config import InferenceConfig
from video4x.runtime.platform import (
    HostPlatform,
    default_ep_preference,
    default_stage_ep_preferences,
    resolve_platform,
)


def test_resolve_platform_auto():
    p = resolve_platform("auto")
    assert p in HostPlatform


def test_windows_defaults():
    assert default_ep_preference(HostPlatform.WINDOWS) == ["dml", "vitisai", "cpu"]
    a, b = default_stage_ep_preferences(HostPlatform.WINDOWS)
    assert a == ["dml", "cpu"]
    assert b == ["vitisai", "dml", "cpu"]


def test_wsl_defaults():
    assert default_ep_preference(HostPlatform.WSL)[0] == "rocm"
    a, b = default_stage_ep_preferences(HostPlatform.WSL)
    assert a[0] == "rocm"
    assert b[0] == "vitisai"


def test_inference_config_platform_override():
    cfg = InferenceConfig(platform="windows")
    assert cfg.platform == "windows"
    assert cfg.ep_preference == ["dml", "vitisai", "cpu"]


def test_inference_config_ep_override():
    cfg = InferenceConfig(platform="windows", ep_preference=["cpu"])
    assert cfg.ep_preference == ["cpu"]
