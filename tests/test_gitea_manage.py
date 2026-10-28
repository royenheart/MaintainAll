"""Acceptance checks for the standalone Gitea deployment manager."""

import importlib.util
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/gitea/manage.py"


class GiteaManagerAcceptance(unittest.TestCase):
    def test_script_text_is_english(self):
        self.assertNotRegex(SCRIPT.read_text(), r"[\u3400-\u4dbf\u4e00-\u9fff]")

    def test_management_entrypoint_exists(self):
        self.assertTrue(SCRIPT.is_file(), "Gitea deployment has no management CLI")

    def test_cli_explains_deployment_commands(self):
        result = subprocess.run(["python3", str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("init", "configure", "up", "update", "backup", "status", "check"):
            self.assertIn(command, result.stdout)


@unittest.skipUnless(SCRIPT.exists(), "Entrypoint acceptance fails before implementation")
class GiteaManagerBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("gitea_manage", SCRIPT)
        cls.manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.manager)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        shutil.copy(SCRIPT.parent / "docker-compose.yml", self.directory)

    def arguments(self, *args):
        return self.manager.parser().parse_args(["configure", *args])

    def settings(self, existing=None, *args):
        with patch.object(self.manager, "detect_lan", return_value="192.0.2.10"):
            return self.manager.build_settings(existing or {}, self.arguments(*args))

    def test_defaults_bind_only_the_route_selected_address(self):
        settings = self.settings()
        self.assertEqual(settings["GITEA_BIND_MODE"], "lan")
        self.assertEqual(settings["GITEA_ROOT_URL"], "http://192.0.2.10:3300/")
        self.assertEqual(self.manager.bind_addresses(settings), ["192.0.2.10"])
        self.assertNotIn("GITEA_TAILSCALE_IP", settings)

    def test_auto_accepts_any_route_interface(self):
        routes = [{"dev": "tailscale0", "prefsrc": "203.0.113.30"}]
        with patch.object(self.manager.subprocess, "check_output", return_value=json.dumps(routes)):
            self.assertEqual(self.manager.detect_lan(), "203.0.113.30")

    def test_auto_rejects_missing_source_and_loopback(self):
        for route in ({"dev": "eth0"}, {"dev": "lo", "prefsrc": "127.0.0.1"}):
            with self.subTest(route=route), patch.object(
                self.manager.subprocess, "check_output", return_value=json.dumps([route])
            ), self.assertRaises(ValueError):
                self.manager.detect_lan()

    def test_removed_network_specific_cli_options_are_rejected(self):
        for args in (("--tailscale-ip", "auto"), ("--bind", "both"), ("--bind", "tailscale")):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.arguments(*args)

    def test_repeated_lan_ip_binds_every_explicit_address(self):
        settings = self.settings(None, "--lan-ip", "192.0.2.10", "--lan-ip", "198.51.100.20",
                                 "--lan-ip", "203.0.113.30")
        self.assertEqual(self.manager.bind_addresses(settings), ["192.0.2.10", "198.51.100.20", "203.0.113.30"])
        self.assertEqual(settings["GITEA_ROOT_URL"], "http://192.0.2.10:3300/")

    def test_multiple_addresses_survive_save_and_reload(self):
        settings = self.settings(None, "--lan-ip", "192.0.2.10", "--lan-ip", "198.51.100.20")
        self.manager.write_env(self.directory / ".env", settings)
        reloaded = self.settings(self.manager.read_env(self.directory / ".env"))
        self.assertEqual(self.manager.bind_addresses(reloaded), ["192.0.2.10", "198.51.100.20"])

    def test_repeated_addresses_are_deduplicated(self):
        settings = self.settings(None, "--lan-ip", "192.0.2.10", "--lan-ip", "192.0.2.10",
                                 "--lan-ip", "203.0.113.30")
        self.assertEqual(self.manager.bind_addresses(settings), ["192.0.2.10", "203.0.113.30"])

    def test_auto_can_be_combined_with_additional_addresses(self):
        settings = self.settings(None, "--lan-ip", "auto", "--lan-ip", "198.51.100.20")
        self.assertEqual(self.manager.bind_addresses(settings), ["192.0.2.10", "198.51.100.20"])

    def test_new_explicit_list_replaces_saved_addresses_and_preserves_custom_domain(self):
        old = self.settings()
        old.update(GITEA_DOMAIN="git.example.com", GITEA_ROOT_URL="https://git.example.com/")
        new = self.settings(old, "--lan-ip", "192.0.2.11", "--lan-ip", "198.51.100.20")
        self.assertEqual(self.manager.bind_addresses(new), ["192.0.2.11", "198.51.100.20"])
        self.assertEqual(new["GITEA_ROOT_URL"], "https://git.example.com/")

    def test_one_explicit_address_also_replaces_old_binding_mode(self):
        old = self.settings()
        new = self.settings(old, "--lan-ip", "192.0.2.11")
        self.assertEqual(self.manager.bind_addresses(new), ["192.0.2.11"])

    def test_legacy_single_address_configuration_loads_without_migration_steps(self):
        old = {"GITEA_LAN_IP": "192.0.2.12", "GITEA_BIND_MODE": "lan",
               "GITEA_DOMAIN": "192.0.2.12", "GITEA_ROOT_URL": "http://192.0.2.12:3300/"}
        self.assertEqual(self.manager.bind_addresses(self.settings(old)), ["192.0.2.12"])

    def test_obsolete_saved_modes_require_an_explicit_address_list(self):
        for mode in ("both", "tailscale"):
            old = {"GITEA_LAN_IP": "192.0.2.10", "GITEA_TAILSCALE_IP": "203.0.113.30",
                   "GITEA_BIND_MODE": mode}
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "--lan-ip"):
                self.settings(old)
            migrated = self.settings(old, "--lan-ip", "192.0.2.10", "--lan-ip", "203.0.113.30")
            self.assertEqual(self.manager.bind_addresses(migrated), ["192.0.2.10", "203.0.113.30"])
            self.assertNotIn("GITEA_TAILSCALE_IP", migrated)

    def test_unused_legacy_helper_does_not_add_an_address(self):
        old = {"GITEA_LAN_IPS": "192.0.2.10,203.0.113.30", "GITEA_BIND_MODE": "lan",
               "GITEA_TAILSCALE_IP": "203.0.113.31"}
        self.assertEqual(self.manager.bind_addresses(self.settings(old)), ["192.0.2.10", "203.0.113.30"])

    def test_obsolete_mode_rejection_does_not_change_saved_configuration(self):
        original = "GITEA_BIND_MODE=both\nGITEA_LAN_IP=192.0.2.10\n"
        (self.directory / ".env").write_text(original)
        with patch.object(self.manager, "compose") as compose, self.assertRaisesRegex(ValueError, "--lan-ip"):
            self.manager.configure(self.directory, self.arguments())
        self.assertEqual((self.directory / ".env").read_text(), original)
        self.assertFalse((self.directory / "docker-compose.override.yml").exists())
        self.assertFalse((self.directory / "backups").exists())
        compose.assert_not_called()

    def test_each_repeated_address_is_validated(self):
        with self.assertRaises(ValueError):
            self.settings(None, "--lan-ip", "192.0.2.10", "--lan-ip", "not-an-ip")

    def test_auto_address_refresh_updates_derived_urls(self):
        old = self.settings()
        old.update(GITEA_LAN_IP="192.0.2.12", GITEA_DOMAIN="192.0.2.12",
                   GITEA_ROOT_URL="http://192.0.2.12:3300/", GITEA_SSH_DOMAIN="192.0.2.12")
        new = self.settings(old, "--lan-ip", "auto")
        self.assertEqual(new["GITEA_ROOT_URL"], "http://192.0.2.10:3300/")
        self.assertEqual(new["GITEA_SSH_DOMAIN"], "192.0.2.10")

    def test_refresh_preserves_custom_canonical_domain(self):
        old = self.settings()
        old.update(GITEA_DOMAIN="git.example.com", GITEA_ROOT_URL="https://git.example.com/",
                   GITEA_SSH_DOMAIN="ssh.example.com")
        new = self.settings(old, "--lan-ip", "192.0.2.11")
        self.assertEqual(new["GITEA_ROOT_URL"], old["GITEA_ROOT_URL"])
        self.assertEqual(new["GITEA_SSH_DOMAIN"], old["GITEA_SSH_DOMAIN"])

    def test_adopting_custom_domain_without_old_lan_keeps_it(self):
        new = self.settings({"GITEA_DOMAIN": "git.example.com", "GITEA_ROOT_URL": "https://git.example.com/"})
        self.assertEqual(new["GITEA_DOMAIN"], "git.example.com")

    def test_loopback_and_wildcard_modes(self):
        for mode, addresses in (("loopback", ["127.0.0.1"]), ("all", [""])):
            with self.subTest(mode=mode):
                settings = self.settings(None, "--bind", mode)
                self.assertEqual(self.manager.bind_addresses(settings), addresses)
                self.assertEqual(self.manager.bind_addresses(self.settings(settings)), addresses)
        self.assertEqual(self.settings(None, "--bind", "loopback")["GITEA_DOMAIN"], "127.0.0.1")

    def test_wildcard_address_requires_explicit_mode(self):
        with self.assertRaises(ValueError):
            self.settings(None, "--lan-ip", "0.0.0.0")

    def test_invalid_url_fails_before_writing(self):
        for url in ("ftp://git.example.com/", "http://user:secret@git.example.com/", "http://git.example.com/?token=secret"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.settings(None, "--root-url", url)

    def test_existing_credentials_comments_and_permissions_are_preserved(self):
        env = self.directory / ".env"
        env.write_text("# private settings\nGITEA__database__PASSWD='existing$secret#value'\nEXTRA=value\n")
        self.manager.write_env(env, self.settings())
        self.assertIn("GITEA__database__PASSWD='existing$secret#value'", env.read_text())
        self.assertIn("# private settings\n", env.read_text())
        self.assertIn("EXTRA=value\n", env.read_text())
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_missing_credentials_with_existing_data_are_not_regenerated(self):
        with self.assertRaisesRegex(ValueError, "credentials"):
            self.manager.ensure_credentials({}, existing_data=True)

    def test_fresh_credentials_are_generated_once(self):
        settings = self.manager.ensure_credentials({}, existing_data=False)
        self.assertGreaterEqual(len(settings["GITEA__database__PASSWD"]), 32)
        self.assertEqual(self.manager.ensure_credentials(settings, existing_data=True), settings)

    def test_empty_database_values_receive_fresh_defaults(self):
        settings = self.manager.ensure_credentials({key: "" for key in self.manager.DB_KEYS}, existing_data=False)
        self.assertTrue(all(settings[key] for key in self.manager.DB_KEYS))

    def test_backup_failure_restarts_the_existing_server(self):
        commands = []

        def compose(directory, *args, **kwargs):
            commands.append(args)
            if args[0] == "ps":
                return Mock(stdout="server\ndb\n")
            if args[0] == "exec":
                raise subprocess.CalledProcessError(1, ["pg_dump"])
            return Mock()

        with patch.object(self.manager, "compose", side_effect=compose), patch.object(
            self.manager.subprocess, "check_output", return_value="sha256:old-image\n"
        ), self.assertRaises(subprocess.CalledProcessError):
            self.manager.backup(self.directory, keep_stopped=True)
        self.assertIn(("stop", "server"), commands)
        self.assertEqual(commands[-1], ("start", "server"))
        self.assertFalse(list((self.directory / "backups").glob("*/COMPLETE")))

    def test_successful_upgrade_backup_stays_stopped_and_records_both_stores(self):
        commands = []

        def compose(directory, *args, **kwargs):
            commands.append(args)
            if args[0] == "ps":
                return Mock(stdout="server\ndb\n")
            if args[0] == "exec":
                kwargs["stdout"].write(b"database snapshot")
            return Mock()

        def docker(command, **kwargs):
            self.assertEqual(command, ["docker", "cp", "gitea:/data/.", "-"])
            kwargs["stdout"].write(b"gitea archive")

        with contextlib.redirect_stdout(io.StringIO()), patch.object(self.manager, "compose", side_effect=compose), patch.object(
            self.manager.subprocess, "check_output", return_value="sha256:old-image\n"
        ), patch.object(self.manager.subprocess, "run", side_effect=docker):
            destination = self.manager.backup(self.directory, keep_stopped=True)
        self.assertEqual((destination / "postgres.dump").read_bytes(), b"database snapshot")
        self.assertEqual((destination / "data.tar").read_bytes(), b"gitea archive")
        self.assertTrue((destination / "COMPLETE").exists())
        self.assertNotIn(("start", "server"), commands)

    def test_compose_validation_failure_restores_previous_configuration(self):
        env = self.directory / ".env"
        original = "# keep\n" + "".join(f"{key}=existing\n" for key in self.manager.DB_KEYS)
        env.write_text(original)
        with patch.object(self.manager, "existing_data", return_value=True), patch.object(
            self.manager, "compose", side_effect=subprocess.CalledProcessError(1, ["compose", "config"])
        ), patch.object(self.manager, "detect_lan", return_value="192.0.2.10"), self.assertRaises(subprocess.CalledProcessError):
            self.manager.configure(self.directory, self.arguments())
        self.assertEqual(env.read_text(), original)
        self.assertFalse((self.directory / "docker-compose.override.yml").exists())

    def test_check_rejects_unapplied_restricted_bindings(self):
        config = {"environment": {"GITEA__server__ROOT_URL": "http://192.0.2.10:3300/"},
                  "ports": [{"target": 3000, "published": "3300", "host_ip": "192.0.2.10"}]}
        with patch.object(self.manager, "effective_settings", return_value=config), patch.object(
            self.manager.subprocess, "check_output", return_value='{"3000/tcp":[{"HostIp":"","HostPort":"3300"}]}'
        ), self.assertRaisesRegex(ValueError, "port bindings differ"):
            self.manager.check(self.directory)

    def test_check_accepts_first_time_installation_page(self):
        config = {"environment": {"GITEA__server__ROOT_URL": "http://192.0.2.10:3300/"},
                  "ports": [{"target": 3000, "published": "3300", "host_ip": "192.0.2.10"}]}
        response = Mock()
        response.read.return_value = b"Installation"
        response.geturl.return_value = "http://192.0.2.10:3300/install"
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(self.manager, "effective_settings", return_value=config), patch.object(
            self.manager.subprocess, "check_output", return_value='{"3000/tcp":[{"HostIp":"192.0.2.10","HostPort":"3300"}]}'
        ), patch.object(self.manager.urllib.request, "build_opener", return_value=opener):
            self.manager.check(self.directory)
        self.assertEqual(opener.open.call_count, 1)

    def test_update_pulls_then_backs_up_then_recreates_only_gitea(self):
        operations = []
        (self.directory / ".env").write_text("".join(f"{key}=existing\n" for key in self.manager.DB_KEYS))
        with patch.object(self.manager, "DIRECTORY", self.directory), patch.object(
            self.manager, "compose", side_effect=lambda directory, *args, **kwargs: operations.append(args)
        ), patch.object(self.manager, "backup", side_effect=lambda *args, **kwargs: operations.append(("backup", kwargs))), patch.object(
            self.manager, "check"
        ):
            self.assertEqual(self.manager.main(["update"]), 0)
        self.assertEqual(operations, [("config", "--quiet"), ("pull", "server"),
                                    ("backup", {"keep_stopped": True}),
                                    ("up", "-d", "--no-deps", "--pull", "never", "server")])

    def test_up_requires_saved_credentials_before_deployment(self):
        with contextlib.redirect_stderr(io.StringIO()), patch.object(self.manager, "DIRECTORY", self.directory), patch.object(
            self.manager, "compose"
        ) as compose:
            self.assertEqual(self.manager.main(["up"]), 1)
        compose.assert_not_called()

    def test_init_skips_existing_deployment_without_changing_files_or_containers(self):
        original_env = "# private settings\nGITEA__database__PASSWD='existing-secret'\n"
        original_override = "# operator configuration\nservices: {}\n"
        (self.directory / ".env").write_text(original_env)
        (self.directory / "docker-compose.override.yml").write_text(original_override)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(self.manager, "DIRECTORY", self.directory), patch.object(
            self.manager, "existing_data", return_value=True
        ), patch.object(self.manager, "compose") as compose, patch.object(self.manager, "build_settings") as build_settings:
            self.assertEqual(self.manager.main(["init", "--lan-ip", "192.0.2.11"]), 0)
        self.assertIn("init skipped", output.getvalue())
        self.assertIn("configure", output.getvalue())
        self.assertEqual((self.directory / ".env").read_text(), original_env)
        self.assertEqual((self.directory / "docker-compose.override.yml").read_text(), original_override)
        self.assertFalse((self.directory / "backups").exists())
        compose.assert_not_called()
        build_settings.assert_not_called()

    def test_init_with_existing_volumes_and_missing_env_does_not_generate_credentials(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(self.manager, "DIRECTORY", self.directory), patch.object(
            self.manager, "existing_data", return_value=True
        ), patch.object(self.manager, "compose") as compose:
            self.assertEqual(self.manager.main(["init", "--no-start"]), 0)
        self.assertFalse((self.directory / ".env").exists())
        self.assertFalse((self.directory / "docker-compose.override.yml").exists())
        compose.assert_not_called()

    def test_init_prepares_a_new_deployment_without_starting_when_requested(self):
        args = self.manager.parser().parse_args(["init", "--no-start", "--lan-ip", "192.0.2.10"])
        with contextlib.redirect_stdout(io.StringIO()), patch.object(self.manager, "existing_data", return_value=False), patch.object(
            self.manager, "compose"
        ) as compose:
            self.manager.configure(self.directory, args)
        saved = self.manager.read_env(self.directory / ".env")
        self.assertGreaterEqual(len(saved["GITEA__database__PASSWD"]), 32)
        self.assertEqual(saved["GITEA_DOMAIN"], "192.0.2.10")
        self.assertTrue((self.directory / "docker-compose.override.yml").exists())
        compose.assert_called_once_with(self.directory, "config", "--quiet")

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required for schema validation")
    def test_real_compose_replaces_wildcard_ports(self):
        settings = self.settings(None, "--lan-ip", "192.0.2.10", "--lan-ip", "203.0.113.30")
        self.manager.write_env(self.directory / ".env", settings)
        self.manager.write_override(self.directory, settings)
        config = self.manager.compose(self.directory, "config", "--format", "json", capture=True)
        server = json.loads(config.stdout)["services"]["server"]
        self.assertEqual(len(server["ports"]), 4)
        self.assertEqual({p["host_ip"] for p in server["ports"]}, {"192.0.2.10", "203.0.113.30"})
        self.assertEqual(server["environment"]["GITEA__server__SSH_PORT"], "3322")

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required for schema validation")
    def test_real_compose_publishes_both_ports_on_every_address_in_the_list(self):
        addresses = ["192.0.2.10", "198.51.100.20", "203.0.113.30"]
        settings = self.settings(None, *(arg for address in addresses for arg in ("--lan-ip", address)))
        self.manager.write_env(self.directory / ".env", settings)
        self.manager.write_override(self.directory, settings)
        config = json.loads(self.manager.compose(self.directory, "config", "--format", "json", capture=True).stdout)
        ports = config["services"]["server"]["ports"]
        self.assertEqual({(p["host_ip"], p["published"], p["target"]) for p in ports},
                         {(ip, external, internal) for ip in addresses for external, internal in (("3300", 3000), ("3322", 22))})
        self.assertEqual(len(ports), 6)

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required for schema validation")
    def test_shell_variables_do_not_override_saved_configuration(self):
        settings = self.settings()
        self.manager.write_env(self.directory / ".env", settings)
        with patch.dict(os.environ, {"GITEA_DOMAIN": "wrong.example.com", "COMPOSE_PROJECT_NAME": "wrong"}):
            config = self.manager.compose(self.directory, "config", "--format", "json", capture=True)
        config = json.loads(config.stdout)
        self.assertEqual(config["name"], "gitea")
        self.assertEqual(config["services"]["server"]["environment"]["GITEA__server__DOMAIN"], settings["GITEA_DOMAIN"])

    def test_dry_run_does_not_write_or_deploy(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(self.manager, "detect_lan", return_value="192.0.2.10"), patch.object(
            self.manager, "existing_data", return_value=False
        ), patch.object(self.manager, "compose") as compose:
            self.manager.configure(self.directory, self.arguments("--dry-run"))
        self.assertFalse((self.directory / ".env").exists())
        self.assertFalse((self.directory / "docker-compose.override.yml").exists())
        compose.assert_not_called()
