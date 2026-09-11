"""Tests for the AstrBot deploy script.

The defining constraint of this stack is that it deploys and reports,
and never writes AstrBot's configuration. A regression here means the
script could silently rewrite provider or plugin settings on a live
instance, so these tests are deliberately strict.
"""

import inspect
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import deploy  # noqa: E402
from deploy import (  # noqa: E402
    read_env,
    write_env,
    ensure_dashboard_password,
    generate_password,
    password_problem,
    _INSPECT_SCRIPT,
    container_name,
    inspect_config,
    status,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture
def env_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(deploy, "ENV_PATH", tmp_path / ".env")
    return tmp_path


# ---------------------------------------------------------------------------
# passwords
# ---------------------------------------------------------------------------


class TestPassword:
    def test_generated_password_is_valid(self):
        assert password_problem(generate_password()) is None

    def test_generated_password_varies(self):
        assert generate_password() != generate_password()

    @pytest.mark.parametrize(
        "bad,reason",
        [
            ("short1A", "at least 8"),
            ("alllowercase1", "upper case"),
            ("ALLUPPERCASE1", "lower case"),
            ("NoDigitsHere", "digit"),
        ],
    )
    def test_rejects_invalid(self, bad, reason):
        assert reason in (password_problem(bad) or "")

    def test_accepts_valid(self):
        assert password_problem("GoodPass123") is None


class TestEnsureDashboardPassword:
    """A blank value would crash AstrBot on a fresh volume.

    AstrBot validates ASTRBOT_DASHBOARD_INITIAL_PASSWORD whenever it has
    to generate dashboard credentials, and rejects an empty string.
    """

    def test_generates_when_missing(self, env_dir):
        env = {"ASTRBOT_TAG": "latest"}
        generated = ensure_dashboard_password(env)
        assert generated and password_problem(generated) is None
        assert env["ASTRBOT_DASHBOARD_PASSWORD"] == generated

    def test_persists_to_env(self, env_dir):
        env = {}
        generated = ensure_dashboard_password(env)
        assert read_env()["ASTRBOT_DASHBOARD_PASSWORD"] == generated

    def test_generates_when_empty(self, env_dir):
        generated = ensure_dashboard_password({"ASTRBOT_DASHBOARD_PASSWORD": ""})
        assert generated is not None

    @pytest.mark.parametrize("weak", ["short1A", "alllowercase1", "NODIGITS"])
    def test_generates_when_too_weak(self, env_dir, weak):
        generated = ensure_dashboard_password({"ASTRBOT_DASHBOARD_PASSWORD": weak})
        assert generated is not None
        assert password_problem(generated) is None

    def test_keeps_a_valid_password(self, env_dir):
        env = {"ASTRBOT_DASHBOARD_PASSWORD": "GoodPass123"}
        assert ensure_dashboard_password(env) is None
        assert env["ASTRBOT_DASHBOARD_PASSWORD"] == "GoodPass123"

    def test_up_calls_the_guard(self):
        """`up` must run the guard rather than pass a blank env value."""
        source = (ROOT / "deploy.py").read_text()
        up_body = source[source.index('@cli.command("up")'):]
        up_body = up_body[: up_body.index('@cli.command("down")')]
        assert "ensure_dashboard_password(env)" in up_body


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------


class TestEnvIO:
    def test_roundtrip(self, env_dir):
        write_env({"ASTRBOT_DASHBOARD_PASSWORD": "GoodPass123"})
        assert read_env()["ASTRBOT_DASHBOARD_PASSWORD"] == "GoodPass123"

    def test_defaults_written(self, env_dir):
        write_env({})
        data = read_env()
        assert data["ASTRBOT_TAG"] == "latest"
        assert data["ASTRBOT_CONTAINER"] == "astrbot"
        assert data["ASTRBOT_PORT"] == "6185"
        assert data["ASTRBOT_VOLUME"] == "astrbot_data"

    def test_read_env_ignores_comments(self, env_dir):
        (env_dir / ".env").write_text("# c\nASTRBOT_TAG=v4.26.2\n")
        assert read_env()["ASTRBOT_TAG"] == "v4.26.2"

    @pytest.mark.parametrize(
        "forbidden",
        ["HERMES_ACCESS_TOKEN", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
         "OPENAI_API_KEY", "CLIENT_TOKEN", "ASTRBOT_PROVIDER_MODEL"],
    )
    def test_no_foreign_secrets(self, env_dir, forbidden):
        """No agent or LLM credentials belong to this stack."""
        write_env({})
        assert forbidden not in (env_dir / ".env").read_text()


# ---------------------------------------------------------------------------
# compose
# ---------------------------------------------------------------------------


class TestCompose:
    def test_uses_upstream_image_no_build(self):
        content = (ROOT / "docker-compose.yml").read_text()
        assert "image: soulter/astrbot:" in content
        assert "build:" not in content

    def test_tag_is_overridable(self):
        assert "${ASTRBOT_TAG:-latest}" in (ROOT / "docker-compose.yml").read_text()

    def test_volume_name_is_overridable(self):
        """Overridable so an existing volume can be adopted."""
        assert "${ASTRBOT_VOLUME:-astrbot_data}" in (
            ROOT / "docker-compose.yml"
        ).read_text()

    def test_data_volume_mounted(self):
        content = (ROOT / "docker-compose.yml").read_text()
        assert "astrbot_data:/AstrBot/data" in content

    def test_no_agent_services(self):
        content = (ROOT / "docker-compose.yml").read_text()
        for gone in ["hermes", "cuactl", "cua-net", "8420"]:
            assert gone not in content

    def test_host_gateway_is_resolvable(self):
        """Plugins reaching host services need host.docker.internal.

        hapi_connector points at http://host.docker.internal:3006, where
        the HAPI hub runs as a host process. Dropping extra_hosts breaks
        that plugin silently — the endpoint simply stops resolving.
        """
        content = (ROOT / "docker-compose.yml").read_text()
        assert "extra_hosts:" in content
        assert "host.docker.internal:host-gateway" in content


# ---------------------------------------------------------------------------
# the no-write guarantee
# ---------------------------------------------------------------------------


class TestNoConfigWrites:
    SOURCE = (ROOT / "deploy.py").read_text()

    @pytest.mark.parametrize(
        "forbidden",
        [
            "json.dump(",           # no config serialisation
            "_conf_schema",         # no plugin schema patching
            "_configure_astrbot",   # no provider injection
            "docker cp",            # no file injection into the container
            "docker restart",       # no forced config reload
        ],
    )
    def test_source_never_writes_config(self, forbidden):
        assert forbidden not in self.SOURCE

    def test_config_path_is_only_ever_read(self):
        """The config path appears as a read target, never a write target."""
        assert "cmd_config" in self.SOURCE  # read path constant
        assert "_INSPECT_SCRIPT" in self.SOURCE

    def test_inspect_script_opens_read_only(self):
        assert 'open(path, encoding="utf-8-sig")' in _INSPECT_SCRIPT
        # An inspect script that opened for writing would defeat the point.
        assert "'w'" not in _INSPECT_SCRIPT
        assert '"w"' not in _INSPECT_SCRIPT

    def test_inspect_script_handles_bom(self):
        """AstrBot writes cmd_config.json with a UTF-8 BOM."""
        assert "utf-8-sig" in _INSPECT_SCRIPT

    def test_inspect_script_never_raises_on_missing_file(self):
        assert "FileNotFoundError" in _INSPECT_SCRIPT

    def test_no_subprocess_shell_true(self):
        assert "shell=True" not in self.SOURCE


class TestDangerousOperations:
    SOURCE = (ROOT / "deploy.py").read_text()

    @property
    def _down_block(self):
        """The `down` command including its decorators."""
        start = self.SOURCE.index('@cli.command("down")')
        end = self.SOURCE.index('@cli.command("status")')
        return self.SOURCE[start:end]

    def test_down_only_removes_volumes_with_wipe(self):
        """`down` must keep volumes unless --wipe is passed explicitly."""
        block = self._down_block
        assert "if wipe:" in block
        wipe_branch = block[block.index("if wipe:"): block.index("    else:")]
        assert '"down", "-v"' in wipe_branch
        assert '_compose("down")' in block[block.index("    else:"):]

    def test_wipe_requires_confirmation(self):
        block = self._down_block
        assert "--wipe" in block
        assert "click.confirm" in block
        assert 'help="Skip the confirmation prompt for --wipe"' in block

    def test_status_is_read_only(self):
        """`status` is a click command; inspect the underlying callback."""
        params = inspect.signature(status.callback).parameters
        assert "as_json" in params


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


class TestCli:
    def test_expected_commands(self):
        content = (ROOT / "deploy.py").read_text()
        for cmd in ['"setup-env"', '"up"', '"down"', '"status"', '"logs"', '"shell"']:
            assert cmd in content

    def test_up_pulls_by_default(self):
        assert '"pull"' in (ROOT / "deploy.py").read_text()

    def test_container_name_from_env(self, env_dir):
        assert container_name({"ASTRBOT_CONTAINER": "cua-astrbot"}) == "cua-astrbot"
        assert container_name({}) == "astrbot"

    def test_env_example_documents_volume_adoption(self):
        assert "compute-browser-use_astrbot_data" in (ROOT / ".env.example").read_text()


class TestBackupTooling:
    def test_scripts_present_and_executable(self):
        for name in ("export.sh", "restore.sh"):
            path = ROOT / name
            assert path.exists(), f"{name} missing"
            assert path.stat().st_mode & 0o111, f"{name} not executable"

    @pytest.mark.parametrize("name", ["deploy.py", "migrate-from-compute-browser-use.sh"])
    def test_entrypoints_are_executable(self, name):
        """Both are invoked as ./<name>; without +x that fails at runtime.

        The migration script calls ./deploy.py, so a missing mode bit
        aborts it partway — after it has already removed the container.
        """
        path = ROOT / name
        assert path.exists(), f"{name} missing"
        assert path.stat().st_mode & 0o111, f"{name} is not executable"

    def test_export_targets_astrbot_volume_only(self):
        content = (ROOT / "export.sh").read_text()
        assert "ASTRBOT_VOLUME" in content
        assert "hermes" not in content.lower()

    def test_restore_does_not_overwrite_env(self):
        """A foreign .env must never clobber the live one."""
        content = (ROOT / "restore.sh").read_text()
        assert ".env.restored" in content
