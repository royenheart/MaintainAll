"""Layer 1: Unit tests for permission control."""

import pytest

from cua_control_plane.permissions import (
    AccessDeniedError,
    PermissionLevel,
    check_permission,
    get_allowed_ops,
    READ_OPS,
    WRITE_OPS,
)


class TestPermissionLevels:
    def test_off_denies_all(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "off"
        mock_control_plane_config.save()

        # Even read ops should be denied
        with pytest.raises(AccessDeniedError, match="disabled"):
            check_permission("capture")

    def test_readonly_allows_read(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "readonly"
        mock_control_plane_config.save()

        # Read ops should pass
        for op in READ_OPS:
            check_permission(op)  # Should not raise

    def test_readonly_denies_write(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "readonly"
        mock_control_plane_config.save()

        for op in WRITE_OPS:
            with pytest.raises(AccessDeniedError, match="write access"):
                check_permission(op)

    def test_full_allows_all(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.save()

        for op in READ_OPS | WRITE_OPS:
            check_permission(op)  # Should not raise

    def test_strict_allows_all(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "strict"
        mock_control_plane_config.save()

        for op in READ_OPS | WRITE_OPS:
            check_permission(op)  # Should not raise in automated mode

    def test_get_allowed_ops_off(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "off"
        mock_control_plane_config.save()
        ops = get_allowed_ops()
        assert ops["permission_level"] == "off"
        assert ops["allowed_operations"] == []

    def test_get_allowed_ops_readonly(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "readonly"
        mock_control_plane_config.save()
        ops = get_allowed_ops()
        assert ops["permission_level"] == "readonly"
        for o in READ_OPS:
            assert o in ops["allowed_operations"]
        for o in WRITE_OPS:
            assert o not in ops["allowed_operations"]

    def test_get_allowed_ops_full(self, mock_control_plane_config):
        mock_control_plane_config.permission_level = "full"
        mock_control_plane_config.save()
        ops = get_allowed_ops()
        assert ops["permission_level"] == "full"
        for o in READ_OPS | WRITE_OPS:
            assert o in ops["allowed_operations"]


class TestPermissionEnum:
    def test_permission_level_values(self):
        assert PermissionLevel.OFF.value == "off"
        assert PermissionLevel.READONLY.value == "readonly"
        assert PermissionLevel.FULL.value == "full"
        assert PermissionLevel.STRICT.value == "strict"

    def test_str_to_enum(self):
        assert PermissionLevel("off") == PermissionLevel.OFF
        assert PermissionLevel("readonly") == PermissionLevel.READONLY
        assert PermissionLevel("full") == PermissionLevel.FULL
        assert PermissionLevel("strict") == PermissionLevel.STRICT

    def test_invalid_level_raises(self):
        with pytest.raises(ValueError):
            PermissionLevel("invalid")
