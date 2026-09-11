"""Layer 1: API endpoint tests (with mock dependencies)."""

import json
from unittest.mock import AsyncMock, patch

import pytest


class TestHealthEndpoint:
    def test_health_no_auth(self, test_app_no_auth, mock_control_plane_config):
        """Health check should work without auth."""
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.save()

        resp = test_app_no_auth.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "cua-control-plane"

    def test_health_returns_permissions(self, test_app_no_auth, mock_control_plane_config):
        mock_control_plane_config.permission_level = "readonly"
        mock_control_plane_config.save()

        resp = test_app_no_auth.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["permissions"]["permission_level"] == "readonly"


class TestAuthMiddleware:
    def test_missing_token_returns_401(self, test_app_no_auth):
        resp = test_app_no_auth.post("/api/v1/dops/list_apps", json={})
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, test_app_no_auth):
        resp = test_app_no_auth.post(
            "/api/v1/dops/list_apps",
            json={},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_off_permission_returns_403(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "off"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        resp = test_app.post("/api/v1/dops/list_apps", json={})
        assert resp.status_code == 403
        data = resp.json()
        assert "Access Denied" in data["error"]

    def test_readonly_blocks_write(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "readonly"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        resp = test_app.post("/api/v1/cua/click", json={"x": 100, "y": 200})
        assert resp.status_code == 403


class TestDopsEndpoints:
    def test_list_apps(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        with patch("cua_control_plane.api.deterministic_ops.list_apps", return_value=[]):
            resp = test_app.post("/api/v1/dops/list_apps", json={})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "apps" in data

    def test_app_info_not_found(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        with patch("cua_control_plane.api.deterministic_ops.app_info", return_value=None):
            resp = test_app.post("/api/v1/dops/app_info", json={"app_name": "nonexistent"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is False

    def test_open_app(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        with patch("cua_control_plane.api.deterministic_ops.open_app",
                   return_value={"success": True, "action": "launched"}):
            resp = test_app.post("/api/v1/dops/open_app", json={"app_name": "firefox"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True


class TestCuaEndpoints:
    def test_capture(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        mock_result = {"success": True, "base64": "AAAA", "mime_type": "image/png"}
        with patch("cua_control_plane.api.cua_core.capture", new=AsyncMock(return_value=mock_result)):
            resp = test_app.post("/api/v1/cua/capture")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    def test_click(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        mock_result = {"success": True, "x": 100, "y": 200, "button": "left"}
        with patch("cua_control_plane.api.cua_core.click", new=AsyncMock(return_value=mock_result)):
            resp = test_app.post("/api/v1/cua/click", json={"x": 100, "y": 200})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    def test_type_text(self, test_app, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.local_token = "test-token-123"
        mock_control_plane_config.save()

        mock_result = {"success": True, "text": "hello"}
        with patch("cua_control_plane.api.cua_core.type_text", new=AsyncMock(return_value=mock_result)):
            resp = test_app.post("/api/v1/cua/type", json={"text": "hello"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
