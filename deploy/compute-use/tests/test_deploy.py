"""Tests for the compute-use deploy script and stack definition.

This stack owns the computer-use capability only: the client control
plane and the cuactl relay. It must not carry LLM credentials or agent
configuration — those belong to other stacks.
"""

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import deploy  # noqa: E402
from deploy import (  # noqa: E402
    SCRIPT_DIR,
    _status_cmd,
    deploy_client,
    deploy_server,
    generate_token,
    read_env,
    setup_env_interactive,
    write_env,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture
def env_dir(tmp_path, monkeypatch):
    """Point SCRIPT_DIR at a temp dir so .env I/O stays isolated."""
    monkeypatch.setattr(deploy, "SCRIPT_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------


class TestEnvIO:
    def test_generate_token_length(self):
        assert len(generate_token()) == 64

    def test_roundtrip(self, env_dir):
        write_env(
            {
                "CLIENT_TOKEN": "client-token-456",
                "CUACTL_ENDPOINT": "https://192.168.1.100:9111",
            }
        )
        data = read_env()
        assert data["CLIENT_TOKEN"] == "client-token-456"
        assert data["CUACTL_ENDPOINT"] == "https://192.168.1.100:9111"

    def test_relay_token_defaults_to_client_token(self, env_dir):
        write_env({"CLIENT_TOKEN": "abc"})
        assert "CUACTL_TOKEN=${CLIENT_TOKEN}" in (env_dir / ".env").read_text()

    def test_read_env_ignores_comments(self, env_dir):
        (env_dir / ".env").write_text("# Comment\nCLIENT_TOKEN=abc123\n")
        assert read_env()["CLIENT_TOKEN"] == "abc123"

    @pytest.mark.parametrize(
        "forbidden",
        ["HERMES_ACCESS_TOKEN", "ASTRBOT_DASHBOARD_PASSWORD", "ANTHROPIC_API_KEY",
         "OPENAI_API_KEY", "BRIDGE_AUTH_TOKEN", "ASTRBOT_PROVIDER_MODEL"],
    )
    def test_no_foreign_secrets(self, env_dir, forbidden):
        """This stack holds no agent or LLM credentials."""
        write_env({})
        assert forbidden not in (env_dir / ".env").read_text()


# ---------------------------------------------------------------------------
# compose
# ---------------------------------------------------------------------------


class TestCompose:
    def test_compose_file_exists(self):
        assert (ROOT / "docker-compose.yml").exists()

    def test_relay_service_defined(self):
        content = (ROOT / "docker-compose.yml").read_text()
        assert "cuactl:" in content
        assert "server/cua-relay/Dockerfile.http" in content

    def test_relay_not_published_to_host(self):
        """The relay is intra-network only; no host port mapping."""
        content = (ROOT / "docker-compose.yml").read_text()
        assert "ports:" not in content

    def test_network_name_is_overridable(self):
        content = (ROOT / "docker-compose.yml").read_text()
        assert "name: ${CUA_NETWORK:-cua-net}" in content

    def test_no_agent_services(self):
        """hermes / astrbot / bridge live in their own stacks."""
        content = (ROOT / "docker-compose.yml").read_text()
        for gone in ["hermes-api", "hermes-bridge", "astrbot", "8420", "8421"]:
            assert gone not in content

    def test_dockerignore_excludes_external(self):
        assert "external/" in (ROOT / ".dockerignore").read_text()


# ---------------------------------------------------------------------------
# script surface
# ---------------------------------------------------------------------------


class TestScriptSurface:
    def test_expected_functions_exist(self):
        for fn in (setup_env_interactive, deploy_server, deploy_client, _status_cmd):
            assert callable(fn)

    def test_server_signature(self):
        params = inspect.signature(deploy_server).parameters
        assert "bind_address" in params
        assert "interactive" in params

    @pytest.mark.parametrize(
        "forbidden",
        ["_configure_astrbot_providers", "_configure_hermes_env",
         "PROVIDER_REGISTRY", "_install_hermes_connector_plugin",
         "_start_hapi_hub_and_configure", "_install_skills",
         "ASTRBOT_CONFIG_PATH", "_conf_schema.json"],
    )
    def test_no_agent_config_injection(self, forbidden):
        """Deploy only: this script must never configure an agent."""
        assert forbidden not in (ROOT / "deploy.py").read_text()

    def test_cli_exposes_expected_commands(self):
        content = (ROOT / "deploy.py").read_text()
        for cmd in ['"setup-env"', '"server"', '"client"', '"status"', '"down"']:
            assert cmd in content


class TestEnvExample:
    REQUIRED = ["CLIENT_TOKEN", "CUACTL_ENDPOINT", "CUACTL_TOKEN", "CUA_NETWORK"]

    def test_required_keys_present(self):
        content = (ROOT / ".env.example").read_text()
        for key in self.REQUIRED:
            assert f"{key}=" in content

    def test_no_foreign_keys(self):
        content = (ROOT / ".env.example").read_text()
        assert "HERMES" not in content
        assert "ASTRBOT" not in content
