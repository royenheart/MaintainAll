"""Layer 2: Integration tests — Mock Client + cuactl relay.

Tests the full chain: cuactl CLI → HTTP → Mock Client Control Plane.
Verifies request/response correctness, error handling, and fault injection.

Requirements:
    - Mock client running: python mock_client.py --port 9110
    - Set CUACTL_ENDPOINT=http://localhost:9110
    - Set CUACTL_TOKEN=test-mock-token
"""

import os
import subprocess
import sys
import time

import httpx
import pytest

# Default: assume mock is on localhost
MOCK_URL = os.environ.get("CUACTL_ENDPOINT", "http://127.0.0.1:19110")
MOCK_TOKEN = os.environ.get("CUACTL_TOKEN", "test-mock-token")

# Skip if mock is not reachable
def _mock_is_up() -> bool:
    try:
        resp = httpx.get(f"{MOCK_URL}/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


requires_mock = pytest.mark.skipif(
    not _mock_is_up(),
    reason=f"Mock client not reachable at {MOCK_URL}. Start with: python mock_client.py --port 19110"
)


@pytest.fixture
def client():
    """HTTP client pointed at mock."""
    return httpx.Client(
        base_url=MOCK_URL,
        headers={"Authorization": f"Bearer {MOCK_TOKEN}"},
        timeout=10,
    )


@pytest.fixture
def admin_client():
    """HTTP client for admin endpoints (no auth needed)."""
    return httpx.Client(base_url=MOCK_URL, timeout=10)


class TestMockHealth:
    @requires_mock
    def test_health(self):
        resp = httpx.get(f"{MOCK_URL}/health", timeout=5)
        assert resp.status_code == 200
        assert resp.json()["service"] == "mock-cua-control-plane"

    @requires_mock
    def test_admin_reset(self, admin_client):
        resp = admin_client.post(f"{MOCK_URL}/_admin/reset")
        assert resp.status_code == 200


class TestCuaOperations:
    @requires_mock
    def test_capture(self, client):
        resp = client.post("/api/v1/cua/capture")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "base64" in data
        assert data["mime_type"] == "image/png"

    @requires_mock
    def test_click(self, client):
        resp = client.post("/api/v1/cua/click", json={"x": 500, "y": 300, "button": "right"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["x"] == 500
        assert data["y"] == 300
        assert data["button"] == "right"

    @requires_mock
    def test_type(self, client):
        resp = client.post("/api/v1/cua/type", json={"text": "hello world"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["text"] == "hello world"

    @requires_mock
    def test_press_key(self, client):
        resp = client.post("/api/v1/cua/press_key", json={"key": "enter"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @requires_mock
    def test_move(self, client):
        resp = client.post("/api/v1/cua/move", json={"x": 100, "y": 200})
        assert resp.status_code == 200

    @requires_mock
    def test_scroll(self, client):
        resp = client.post("/api/v1/cua/scroll", json={"dx": 0, "dy": -100})
        assert resp.status_code == 200

    @requires_mock
    def test_drag(self, client):
        resp = client.post("/api/v1/cua/drag", json={
            "from_x": 100, "from_y": 100, "to_x": 500, "to_y": 300,
        })
        assert resp.status_code == 200


class TestDopsOperations:
    @requires_mock
    def test_list_apps(self, client):
        resp = client.post("/api/v1/dops/list_apps", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["apps"]) == 4

    @requires_mock
    def test_app_info_found(self, client):
        resp = client.post("/api/v1/dops/app_info", json={"app_name": "chrome"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["info"]["name"] == "chrome"

    @requires_mock
    def test_app_info_not_found(self, client):
        resp = client.post("/api/v1/dops/app_info", json={"app_name": "nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    @requires_mock
    def test_open_app(self, client):
        resp = client.post("/api/v1/dops/open_app", json={"app_name": "notepad"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @requires_mock
    def test_list_installed_apps(self, client):
        resp = client.post("/api/v1/dops/list_installed_apps", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["apps"]) == 3


class TestAuthAndErrors:
    @requires_mock
    def test_wrong_token(self):
        resp = httpx.post(
            f"{MOCK_URL}/api/v1/cua/capture",
            headers={"Authorization": "Bearer wrong-token"},
            timeout=5,
        )
        assert resp.status_code == 401

    @requires_mock
    def test_no_token(self):
        resp = httpx.post(f"{MOCK_URL}/api/v1/dops/list_apps", json={}, timeout=5)
        assert resp.status_code == 401


class TestFaultInjection:
    @requires_mock
    def test_capture_failure(self, admin_client, client):
        # Inject fault
        admin_client.post(f"{MOCK_URL}/_admin/faults", json={"capture_fail": True})
        resp = client.post("/api/v1/cua/capture")
        assert resp.json()["success"] is False

        # Reset
        admin_client.post(f"{MOCK_URL}/_admin/reset")

    @requires_mock
    def test_click_failure(self, admin_client, client):
        admin_client.post(f"{MOCK_URL}/_admin/faults", json={"click_fail": True})
        resp = client.post("/api/v1/cua/click", json={"x": 0, "y": 0})
        assert resp.json()["success"] is False
        admin_client.post(f"{MOCK_URL}/_admin/reset")

    @requires_mock
    def test_auth_rejection(self, admin_client, client):
        admin_client.post(f"{MOCK_URL}/_admin/faults", json={"auth_reject": True})
        resp = client.post("/api/v1/cua/capture")
        assert resp.status_code == 403
        admin_client.post(f"{MOCK_URL}/_admin/reset")
