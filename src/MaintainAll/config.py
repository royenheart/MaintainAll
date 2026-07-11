from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

import keyring
import tomli_w
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from MaintainAll.paths import config_dir, default_data_dir, default_repo_path

KEYRING_SERVICE = "maintainall"
AgentMode = Literal["readonly", "restricted", "unlimited"]


SmtpProvider = Literal["gmail", "outlook", "custom"]
SmtpAuth = Literal["password", "oauth"]
SmtpSecurity = Literal["starttls", "ssl"]


class SmtpSettings(BaseModel):
    provider: SmtpProvider = "custom"
    auth: SmtpAuth = "password"
    host: str = ""
    port: int = 587
    security: SmtpSecurity = "starttls"
    user: str = ""
    from_addr: str = Field(default="", alias="from")
    to: list[str] = Field(default_factory=list)
    client_id: str = ""
    tenant_id: str = "common"

    model_config = {"populate_by_name": True}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MAINTAINALL_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    repo_path: str = str(default_repo_path())
    data_dir: str = str(default_data_dir())
    agent_mode: AgentMode = "readonly"
    report_language: str = "zh-CN"
    rag_top_k: int = 5
    smtp: SmtpSettings = Field(default_factory=SmtpSettings)
    # loaded separately from keyring / env
    api_key: SecretStr | None = None
    smtp_password: SecretStr | None = None
    smtp_refresh_token: SecretStr | None = None
    smtp_client_secret: SecretStr | None = None


def _secrets_fallback_path(cfg: Path | None = None) -> Path:
    return (cfg or config_dir()) / "secrets.toml"


def keyring_available() -> bool:
    try:
        keyring.get_keyring()
        return True
    except Exception:
        return False


def _env_var_for_field(*parts: str) -> str:
    return "MAINTAINALL_" + "__".join(p.upper() for p in parts)


def _field_overridden_by_env(*parts: str) -> bool:
    return _env_var_for_field(*parts) in os.environ


def _merge_file_settings(settings: Settings, file_data: dict) -> Settings:
    updates: dict = {}
    for key, value in file_data.items():
        if key == "smtp" and isinstance(value, dict):
            smtp_updates: dict = {}
            for sub_key, sub_value in value.items():
                # model_copy(update=...) uses field names, not aliases — "from" is ignored.
                field_name = "from_addr" if sub_key == "from" else sub_key
                if field_name not in SmtpSettings.model_fields and sub_key not in {
                    "from",
                    "password",
                }:
                    continue
                if field_name == "password":
                    continue  # secrets loaded separately
                if not _field_overridden_by_env("smtp", field_name):
                    smtp_updates[field_name] = sub_value
            if smtp_updates:
                updates["smtp"] = settings.smtp.model_copy(update=smtp_updates)
        elif not _field_overridden_by_env(key):
            updates[key] = value
    if updates:
        return settings.model_copy(update=updates)
    return settings


def set_secret(name: str, value: str, *, config_dir_path: Path | None = None) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, name, value)
        return
    except Exception:
        pass
    cfg = config_dir_path or config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    path = _secrets_fallback_path(cfg)
    data: dict[str, str] = {}
    if path.exists():
        import tomllib

        data = tomllib.loads(path.read_text())
    data[name] = value
    path.write_text(tomli_w.dumps(data))
    path.chmod(0o600)


def get_secret(name: str, *, config_dir_path: Path | None = None) -> str | None:
    try:
        v = keyring.get_password(KEYRING_SERVICE, name)
        if v:
            return v
    except Exception:
        pass
    env_map = {
        "api_key": "DEEPSEEK_API_KEY",
        "smtp_password": "MAINTAINALL_SMTP_PASSWORD",
        "smtp_refresh_token": "MAINTAINALL_SMTP_REFRESH_TOKEN",
        "smtp_client_secret": "MAINTAINALL_SMTP_CLIENT_SECRET",
    }
    if name in env_map and os.environ.get(env_map[name]):
        return os.environ[env_map[name]]
    path = _secrets_fallback_path(config_dir_path or config_dir())
    if path.exists():
        import tomllib

        return tomllib.loads(path.read_text()).get(name)
    return None


def load_settings(*, config_dir_path: Path | None = None) -> Settings:
    cfg = config_dir_path or config_dir()
    toml_path = cfg / "config.toml"
    s = Settings()
    if toml_path.exists():
        import tomllib

        s = _merge_file_settings(s, tomllib.loads(toml_path.read_text()))
    ak = get_secret("api_key", config_dir_path=cfg)
    if ak:
        s.api_key = SecretStr(ak)
    sp = get_secret("smtp_password", config_dir_path=cfg)
    if sp:
        s.smtp_password = SecretStr(sp)
    rt = get_secret("smtp_refresh_token", config_dir_path=cfg)
    if rt:
        s.smtp_refresh_token = SecretStr(rt)
    cs = get_secret("smtp_client_secret", config_dir_path=cfg)
    if cs:
        s.smtp_client_secret = SecretStr(cs)
    return s


def save_non_secrets(settings: Settings, *, config_dir: Path | None = None) -> Path:
    from MaintainAll.paths import config_dir as default_config_dir

    cfg = config_dir if config_dir is not None else default_config_dir()
    cfg.mkdir(parents=True, exist_ok=True)
    path = cfg / "config.toml"
    data = {
        "model": settings.model,
        "api_base": settings.api_base,
        "repo_path": settings.repo_path,
        "data_dir": settings.data_dir,
        "agent_mode": settings.agent_mode,
        "report_language": settings.report_language,
        "rag_top_k": settings.rag_top_k,
        "smtp": settings.smtp.model_dump(by_alias=True),
    }
    path.write_text(tomli_w.dumps(data))
    return path


def migrate_legacy_json(legacy: Path, *, config_dir: Path) -> None:
    data = json.loads(legacy.read_text())
    config_dir.mkdir(parents=True, exist_ok=True)
    if data.get("api_key"):
        set_secret("api_key", data["api_key"], config_dir_path=config_dir)
    s = Settings(
        api_base=data.get("api_base") or "https://api.deepseek.com",
        model=data.get("model") or "deepseek-v4-flash",
        repo_path=data.get("repo_path") or str(default_repo_path()),
    )
    save_non_secrets(s, config_dir=config_dir)
