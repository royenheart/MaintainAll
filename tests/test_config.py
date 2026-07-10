from pathlib import Path
from unittest.mock import patch
import tomllib

from MaintainAll.config import Settings, save_non_secrets, set_secret, get_secret, migrate_legacy_json


def test_default_model_is_v4_flash(tmp_path, monkeypatch):
    monkeypatch.setenv("MAINTAINALL_CONFIG_DIR", str(tmp_path))
    s = Settings(_env_file=None)
    assert s.model == "deepseek-v4-flash"


def test_save_non_secrets_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MAINTAINALL_CONFIG_DIR", str(tmp_path))
    s = Settings(model="deepseek-v4-pro", api_base="https://api.deepseek.com")
    path = save_non_secrets(s, config_dir=tmp_path)
    data = tomllib.loads(path.read_text())
    assert data["model"] == "deepseek-v4-pro"
    assert "api_key" not in data


def test_secret_via_keyring_mock(tmp_path, monkeypatch):
    store = {}
    monkeypatch.setenv("MAINTAINALL_CONFIG_DIR", str(tmp_path))
    with patch("MaintainAll.config.keyring.set_password", side_effect=lambda s, u, p: store.__setitem__((s, u), p)):
        with patch("MaintainAll.config.keyring.get_password", side_effect=lambda s, u: store.get((s, u))):
            set_secret("api_key", "sk-test")
            assert get_secret("api_key") == "sk-test"


def test_migrate_legacy_json(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.json"
    legacy.write_text('{"api_key":"sk-old","model":"deepseek-v4-flash","api_base":"https://api.deepseek.com"}')
    monkeypatch.setenv("MAINTAINALL_CONFIG_DIR", str(tmp_path / "cfg"))
    store = {}
    with patch("MaintainAll.config.keyring.set_password", side_effect=lambda s, u, p: store.__setitem__((s, u), p)):
        with patch("MaintainAll.config.keyring.get_password", side_effect=lambda s, u: store.get((s, u))):
            migrate_legacy_json(legacy, config_dir=tmp_path / "cfg")
    assert store[("maintainall", "api_key")] == "sk-old"
    assert (tmp_path / "cfg" / "config.toml").exists()
