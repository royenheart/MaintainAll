"""Tests for deploy.py core logic."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from deploy import read_env, write_env, generate_token, SCRIPT_DIR


class TestEnvIO:
    def test_generate_token_length(self):
        token = generate_token()
        assert len(token) == 64

    def test_write_and_read_env(self, tmp_path):
        import deploy
        orig = deploy.SCRIPT_DIR
        deploy.SCRIPT_DIR = tmp_path
        try:
            data = {
                "HERMES_ACCESS_TOKEN": "hermes-token-123",
                "CLIENT_TOKEN": "client-token-456",
                "CUACTL_ENDPOINT": "https://192.168.1.100:9111",
                "ANTHROPIC_API_KEY": "sk-ant-test",
                "OPENAI_API_KEY": "",
                "OPENAI_BASE_URL": "",
                "ASTRBOT_DASHBOARD_PASSWORD": "admin123",
            }
            write_env(data)
            raw = (tmp_path / ".env").read_text()
            assert "HERMES_ACCESS_TOKEN=hermes-token-123" in raw
            assert "CLIENT_TOKEN=client-token-456" in raw
            assert "CUACTL_TOKEN=${CLIENT_TOKEN}" in raw
        finally:
            deploy.SCRIPT_DIR = orig

    def test_brg_auth_not_in_default_env(self, tmp_path):
        import deploy
        orig = deploy.SCRIPT_DIR
        deploy.SCRIPT_DIR = tmp_path
        try:
            write_env({})
            raw = (tmp_path / ".env").read_text()
            assert "BRIDGE_AUTH_TOKEN" not in raw
        finally:
            deploy.SCRIPT_DIR = orig

    def test_hermes_access_in_default_env(self, tmp_path):
        import deploy
        orig = deploy.SCRIPT_DIR
        deploy.SCRIPT_DIR = tmp_path
        try:
            write_env({})
            raw = (tmp_path / ".env").read_text()
            assert "HERMES_ACCESS_TOKEN" in raw
        finally:
            deploy.SCRIPT_DIR = orig

    def test_read_env_ignores_comments(self, tmp_path):
        (tmp_path / ".env").write_text("# Comment\nCLIENT_TOKEN=abc123\n")
        import deploy
        orig = deploy.SCRIPT_DIR
        deploy.SCRIPT_DIR = tmp_path
        try:
            result = read_env()
            assert result["CLIENT_TOKEN"] == "abc123"
        finally:
            deploy.SCRIPT_DIR = orig


class TestDockerComposeConfig:
    def test_compose_file_exists(self):
        assert (Path(__file__).parent.parent / "docker-compose.yml").exists()

    def test_hermes_bridge_has_profile(self):
        compose = Path(__file__).parent.parent / "docker-compose.yml"
        idx = compose.read_text().index("hermes-bridge:")
        assert "profiles:" in compose.read_text()[idx:]
        assert "bridge" in compose.read_text()[idx:]

    def test_hermes_access_token_env(self):
        content = (Path(__file__).parent.parent / "docker-compose.yml").read_text()
        assert "HERMES_ACCESS_TOKEN=${HERMES_ACCESS_TOKEN}" in content

    def test_plugin_not_mounted_from_external(self):
        """Plugin installed by deploy.py (docker cp), not volume mount."""
        content = (Path(__file__).parent.parent / "docker-compose.yml").read_text()
        assert "external/astrbot_plugin_hermes_connector" not in content

    def test_hermes_agent_mounted_ro(self):
        content = (Path(__file__).parent.parent / "docker-compose.yml").read_text()
        assert "hermes-agent:/opt/hermes-agent:ro" in content


class TestDockerfile:
    def test_dockerfile_exists(self):
        assert (Path(__file__).parent.parent / "server/hermes-api/Dockerfile").exists()

    def test_hub_cloned_during_build(self):
        """Hub cloned by Dockerfile RUN git clone, not COPY/mount."""
        content = (Path(__file__).parent.parent / "server/hermes-api/Dockerfile").read_text()
        assert "git clone" in content
        assert "astrbot_plugin_hermes_connector" in content
        assert "/app/hub" in content

    def test_python_jose_in_req(self):
        req = Path(__file__).parent.parent / "server/hermes-api/requirements.txt"
        assert "python-jose" in req.read_text()

    def test_hub_entrypoint(self):
        df = Path(__file__).parent.parent / "server/hermes-api/Dockerfile"
        assert "hub.main" in df.read_text()

    def test_hermes_host_port_env(self):
        df = Path(__file__).parent.parent / "server/hermes-api/Dockerfile"
        content = df.read_text()
        assert "HERMES_HOST=0.0.0.0" in content
        assert "HERMES_PORT=8420" in content


class TestDockerignore:
    def test_external_excluded(self):
        """external/ can be blanket-excluded; nothing depends on it at build time."""
        text = (Path(__file__).parent.parent / ".dockerignore").read_text()
        assert "external/" in text

import pytest


class TestHubModule:

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub").is_dir(),
        reason="external/ not present (cloned by Docker during build, not version-controlled)"
    )
    def test_all_hub_modules_compile(self):
        hub = Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub"
        for f in hub.glob("*.py"):
            compile(f.read_text(), str(f), "exec")

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub/__init__.py").exists(),
        reason="external/ not present"
    )
    def test_hub_has_init(self):
        p = Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub/__init__.py"
        assert p.exists()

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub").is_dir(),
        reason="external/ not present"
    )
    def test_runner_defines_binary(self):
        content = (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub/hermes_runner.py").read_text()
        assert "HERMES_BINARY" in content

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub").is_dir(),
        reason="external/ not present"
    )
    def test_auth_uses_jose(self):
        content = (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub/auth.py").read_text()
        assert "from jose import" in content
        assert "create_jwt" in content

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub").is_dir(),
        reason="external/ not present"
    )
    def test_sessions_router_endpoints(self):
        content = (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub/sessions_router.py").read_text()
        for path in ["/sessions/{session_id}/messages", "/sessions/{session_id}/stop",
                      "/sessions/{session_id}/rename", "/sessions/prune"]:
            assert path in content

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub").is_dir(),
        reason="external/ not present"
    )
    def test_sse_pubsub(self):
        content = (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub/sse_manager.py").read_text()
        assert "publish" in content
        assert "subscribe" in content

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub").is_dir(),
        reason="external/ not present"
    )
    def test_main_lifespan(self):
        content = (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hub/main.py").read_text()
        assert "init_access_token" in content
        assert "lifespan" in content


class TestEnvExample:
    def test_hermes_access_token_present(self):
        assert "HERMES_ACCESS_TOKEN=" in (Path(__file__).parent.parent / ".env.example").read_text()

    def test_brg_auth_not_present(self):
        assert "BRIDGE_AUTH_TOKEN" not in (Path(__file__).parent.parent / ".env.example").read_text()

    def test_required_keys_present(self):
        content = (Path(__file__).parent.parent / ".env.example").read_text()
        for key in ["HERMES_ACCESS_TOKEN", "CLIENT_TOKEN", "CUACTL_ENDPOINT",
                     "CUACTL_TOKEN", "ANTHROPIC_API_KEY", "ASTRBOT_DASHBOARD_PASSWORD"]:
            assert f"{key}=" in content


class TestResetFlag:
    def test_deploy_server_accepts_reset(self):
        from deploy import deploy_server
        import inspect
        assert "reset" in list(inspect.signature(deploy_server).parameters)

    def test_server_cmd_has_reset_option(self):
        content = (Path(__file__).parent.parent / "deploy.py").read_text()
        idx = content.index("@click.option(\"--reset\"")
        assert "def server" in content[idx:idx + 500]

    def test_full_cmd_has_reset_option(self):
        content = (Path(__file__).parent.parent / "deploy.py").read_text()
        full_idx = content.index("def full(ctx, bind, reset):")
        assert "deploy_server(bind, reset=reset)" in content[full_idx:full_idx + 200]


class TestExternalPlugin:

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/metadata.yaml").exists(),
        reason="external/ not present"
    )
    def test_metadata_valid(self):
        import yaml
        meta = yaml.safe_load(
            (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/metadata.yaml").read_text()
        )
        assert meta["name"] == "astrbot_plugin_hermes_connector"
        assert "version" in meta

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector").is_dir(),
        reason="external/ not present"
    )
    def test_main_has_plugin_class(self):
        content = (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/main.py").read_text()
        assert "class HermesConnectorPlugin" in content

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector").is_dir(),
        reason="external/ not present"
    )
    def test_cli_client_has_service_classes(self):
        content = (Path(__file__).parent.parent / "external/astrbot_plugin_hermes_connector/hermes_cli_client.py").read_text()
        assert "class LocalHermesService" in content
        assert "class HubHermesService" in content
        assert "configure_service" in content
        assert "is_hub_mode" in content


class TestDeployPluginInstaller:
    """Tests for the plugin auto-install logic in deploy.py."""

    def test_install_function_exists(self):
        content = (Path(__file__).parent.parent / "deploy.py").read_text()
        assert "_install_hermes_connector_plugin" in content

    def test_zip_url_is_github_archive(self):
        content = (Path(__file__).parent.parent / "deploy.py").read_text()
        assert "PLUGIN_ZIP_URL" in content
        assert "archive/master.zip" in content

    def test_docker_cp_in_installer(self):
        content = (Path(__file__).parent.parent / "deploy.py").read_text()
        assert "docker cp" in content
        assert "docker restart" in content

    def test_plugin_install_before_wait_loop(self):
        """Plugin install must happen before health-check wait (restart→wait catches recovery)."""
        content = (Path(__file__).parent.parent / "deploy.py").read_text()
        install_idx = content.index("_install_hermes_connector_plugin()")
        wait_idx = content.index("Waiting for services")
        assert install_idx < wait_idx, "Plugin install must happen BEFORE health check wait loop"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
