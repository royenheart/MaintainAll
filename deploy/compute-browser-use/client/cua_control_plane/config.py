"""Configuration management for CUA Control Plane.

Stores config in %APPDATA%/cua-control-plane/config.json on Windows,
~/.config/cua-control-plane/config.json on Linux/macOS.
"""

import json
import os
import secrets
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

APP_NAME = "cua-control-plane"


def _config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(base) / APP_NAME


def _config_path() -> Path:
    return _config_dir() / "config.json"


@dataclass
class ControlPlaneConfig:
    # Server connection
    server_endpoint: str = ""
    server_token: str = ""

    # Local API
    api_host: str = "127.0.0.1"
    api_port: int = 9110

    # Auth — local token for the API
    local_token: str = field(default_factory=lambda: secrets.token_hex(32))

    # Permission level: off | readonly | full | strict
    permission_level: str = "full"

    # Logging
    log_dir: str = field(default_factory=lambda: str(_config_dir() / "logs"))

    # CUA settings
    cua_api_key: str = ""
    cua_local: bool = True  # Use local CUA sandbox runner

    def save(self) -> None:
        _config_dir().mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls) -> "ControlPlaneConfig":
        path = _config_path()
        if not path.exists():
            cfg = cls()
            cfg.save()
            return cfg
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults for forward compat
        defaults = asdict(cls())
        defaults.update(data)
        return cls(**{k: defaults[k] for k in defaults})


# Global singleton
_config: Optional[ControlPlaneConfig] = None


def get_config() -> ControlPlaneConfig:
    global _config
    if _config is None:
        _config = ControlPlaneConfig.load()
    return _config


def reload_config() -> ControlPlaneConfig:
    global _config
    _config = ControlPlaneConfig.load()
    return _config
