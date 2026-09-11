"""Layer 1: Unit tests for config management."""

import json

from cua_control_plane.config import ControlPlaneConfig


class TestConfig:
    def test_default_values(self, temp_config_dir):
        cfg = ControlPlaneConfig()
        assert cfg.api_host == "127.0.0.1"
        assert cfg.api_port == 9110
        assert cfg.permission_level == "full"
        assert cfg.cua_local is True
        assert len(cfg.local_token) == 64  # secrets.token_hex(32)

    def test_save_and_load(self, temp_config_dir):
        cfg = ControlPlaneConfig()
        cfg.api_port = 9999
        cfg.permission_level = "readonly"
        cfg.local_token = "custom-token"
        cfg.save()

        # Load should restore values
        loaded = ControlPlaneConfig.load()
        assert loaded.api_port == 9999
        assert loaded.permission_level == "readonly"
        assert loaded.local_token == "custom-token"

    def test_forward_compat(self, temp_config_dir):
        """Loading a config with missing keys should merge defaults."""
        config_path = temp_config_dir / "config.json"
        config_path.write_text(json.dumps({"api_port": 5555}))
        # Missing keys like local_token, permission_level etc

        loaded = ControlPlaneConfig.load()
        assert loaded.api_port == 5555  # From file
        assert loaded.permission_level == "full"  # Default
        assert len(loaded.local_token) == 64  # Auto-generated

    def test_config_persistence(self, temp_config_dir):
        """Multiple saves and loads maintain consistency."""
        cfg = ControlPlaneConfig()
        cfg.server_endpoint = "https://example.com"
        cfg.save()

        loaded = ControlPlaneConfig.load()
        assert loaded.server_endpoint == "https://example.com"

        loaded.server_endpoint = "https://changed.com"
        loaded.save()

        reloaded = ControlPlaneConfig.load()
        assert reloaded.server_endpoint == "https://changed.com"

    def test_token_is_random(self, temp_config_dir):
        """Each new config should get a unique token."""
        cfg1 = ControlPlaneConfig()
        cfg2 = ControlPlaneConfig()
        assert cfg1.local_token != cfg2.local_token
        assert len(cfg1.local_token) == 64
