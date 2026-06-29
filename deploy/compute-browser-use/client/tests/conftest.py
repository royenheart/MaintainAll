"""Pytest fixtures for CUA Control Plane tests."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure client package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory and patch config paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir) / "cua-control-plane"
        config_dir.mkdir()
        with patch(
            "cua_control_plane.config._config_dir",
            return_value=config_dir,
        ):
            yield config_dir


@pytest.fixture
def mock_control_plane_config(temp_config_dir):
    """Create a test config with known values."""
    from cua_control_plane.config import ControlPlaneConfig

    cfg = ControlPlaneConfig()
    cfg.api_port = 19110  # Non-standard port for testing
    cfg.permission_level = "full"
    cfg.local_token = "test-token-123"
    cfg.save()

    # Reload to pick up saved values
    ControlPlaneConfig._config = None
    import cua_control_plane.config as config_mod
    config_mod._config = None

    yield cfg

    # Cleanup
    ControlPlaneConfig._config = None
    config_mod._config = None


@pytest.fixture
def test_app():
    """Create a FastAPI TestClient for the control plane API."""
    from cua_control_plane.api import app
    from fastapi.testclient import TestClient

    return TestClient(app, headers={"Authorization": "Bearer test-token-123"})


@pytest.fixture
def test_app_no_auth():
    """Create a TestClient without auth headers."""
    from cua_control_plane.api import app
    from fastapi.testclient import TestClient

    return TestClient(app)
