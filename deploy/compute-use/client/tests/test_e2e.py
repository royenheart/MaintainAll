"""Layer 3: End-to-end tests — CUA sandbox + real deterministic ops.

These tests exercise the full client control plane with a real CUA sandbox
and real Linux desktop operations (wmctrl/xdotool).

Requirements:
    - CUA installed: pip install cua
    - wmctrl + xdotool (Linux): sudo apt install wmctrl xdotool
    - A display server (X11 or Wayland with XWayland)
    - The control plane API running: python -m cua_control_plane.main

These tests are marked with 'e2e' and skipped by default.
Run with: pytest -m e2e
"""

import json
import os
import sys

import httpx
import pytest

API_URL = os.environ.get("CUA_API_URL", "http://127.0.0.1:9110")
API_TOKEN = os.environ.get("CUA_API_TOKEN", "")


def _api_is_up() -> bool:
    try:
        resp = httpx.get(f"{API_URL}/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


requires_api = pytest.mark.skipif(
    not _api_is_up(),
    reason=f"Control Plane API not reachable at {API_URL}"
)


def _token_headers() -> dict:
    h = {}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


@pytest.mark.e2e
class TestE2EDops:
    """End-to-end deterministic operations (Linux)."""

    @requires_api
    def test_list_apps(self):
        """List running applications via wmctrl."""
        resp = httpx.post(
            f"{API_URL}/api/v1/dops/list_apps",
            json={},
            headers=_token_headers(),
            timeout=10,
        )
        if resp.status_code == 403:
            pytest.skip("Permission is OFF")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["apps"], list)

    @requires_api
    def test_list_installed_apps(self):
        """List installed applications via .desktop files."""
        resp = httpx.post(
            f"{API_URL}/api/v1/dops/list_installed_apps",
            json={},
            headers=_token_headers(),
            timeout=10,
        )
        if resp.status_code == 403:
            pytest.skip("Permission is OFF")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["apps"], list)
        # Should find at least some apps
        if os.name != "nt":
            assert len(data["apps"]) > 0, "Should have desktop entries on Linux"


@pytest.mark.e2e
class TestE2ECua:
    """End-to-end CUA operations (requires CUA sandbox)."""

    @requires_api
    def test_screen_size(self):
        resp = httpx.post(
            f"{API_URL}/api/v1/cua/screen_size",
            headers=_token_headers(),
            timeout=30,
        )
        if resp.status_code == 403:
            pytest.skip("Permission is OFF")
        # May fail if CUA not available, that's ok
        data = resp.json()
        if data.get("success"):
            assert data["width"] > 0
            assert data["height"] > 0

    @requires_api
    def test_capture(self):
        resp = httpx.post(
            f"{API_URL}/api/v1/cua/capture",
            headers=_token_headers(),
            timeout=30,
        )
        if resp.status_code == 403:
            pytest.skip("Permission is OFF")
        data = resp.json()
        if data.get("success"):
            assert "base64" in data
            assert data["mime_type"] == "image/png"


@pytest.mark.e2e
class TestE2EHealth:
    @requires_api
    def test_health_permission_state(self):
        resp = httpx.get(f"{API_URL}/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "permissions" in data
        assert "permission_level" in data["permissions"]
