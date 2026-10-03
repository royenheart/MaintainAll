#!/usr/bin/env python3
"""Harden the persisted Paseo daemon config: loopback-only listen + password hash.

Called by install.sh. Rewrites $PASEO_HOME/config.json atomically (exclusive
temp file + rename, mode 0600) and preserves every key it does not own, so a
user's providers, CORS, and relay settings survive a re-run.

The listen target is loopback-only: any non-loopback host is refused, so this
deployment can never persist a 0.0.0.0 bind by accident. Password plaintext
never reaches this tool — install.sh hashes it with the installed CLI's own
bcryptjs and passes the bcrypt hash to set-password-hash.

Subcommands:
  get-listen                      print the current daemon.listen (may be empty)
  set-listen HOST:PORT            enforce loopback, write, print JSON summary
  set-password-hash BCRYPT_HASH   merge daemon.auth.password
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path

CONFIG_FILENAME = "config.json"
LOOPBACK_HOSTS = {"localhost", "::1"}
BCRYPT_HASH_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")
PORT_MIN = 1
PORT_MAX = 65535


class HardenError(Exception):
    pass


def config_path(home: Path) -> Path:
    return home / CONFIG_FILENAME


def load_config(home: Path) -> dict:
    path = config_path(home)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise HardenError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise HardenError(f"{path} must contain a JSON object")
    return raw


def save_config(home: Path, config: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    path = config_path(home)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(config, indent=2, ensure_ascii=False))
            handle.write("\n")
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)


def normalize_port(port: str) -> str:
    if not port.isdigit():
        raise HardenError(f"invalid port in listen value: {port!r}")
    value = int(port, 10)
    if not PORT_MIN <= value <= PORT_MAX:
        raise HardenError(f"port out of range {PORT_MIN}-{PORT_MAX}: {value}")
    return str(value)


def split_listen(listen: str) -> tuple[str, str]:
    """Split HOST:PORT, accepting an optional [v6] bracket on the host."""
    value = listen.strip()
    if not value:
        raise HardenError("empty listen value")
    if value.startswith("["):
        end = value.find("]")
        if end == -1 or end + 1 >= len(value) or value[end + 1] != ":":
            raise HardenError(f"invalid listen value: {listen!r}")
        host, port = value[1:end], value[end + 2 :]
    else:
        if ":" not in value:
            raise HardenError(f"listen value must be HOST:PORT: {listen!r}")
        host, port = value.rsplit(":", 1)
    host = host.strip()
    if not host:
        raise HardenError(f"missing host in listen value: {listen!r}")
    return host, normalize_port(port)


def is_loopback_host(host: str) -> bool:
    candidate = host.strip().lower().strip("[]")
    if candidate in LOOPBACK_HOSTS or candidate.endswith(".localhost"):
        return True
    parts = candidate.split(".")
    if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
        return parts[0] == "127"
    return False


def daemon_section(config: dict) -> dict:
    section = config.get("daemon")
    if not isinstance(section, dict):
        section = {}
    return section


def cmd_get_listen(args: argparse.Namespace) -> None:
    config = load_config(Path(args.home))
    listen = daemon_section(config).get("listen")
    print(listen if isinstance(listen, str) else "")


def cmd_set_listen(args: argparse.Namespace) -> None:
    host, port = split_listen(args.listen)
    if not is_loopback_host(host):
        raise HardenError(
            f"refusing non-loopback listen target {args.listen!r}: "
            "this deployment binds loopback only (use --port to pick a port)"
        )
    listen = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    home = Path(args.home)
    config = load_config(home)
    daemon = daemon_section(config)
    previous = daemon.get("listen") if isinstance(daemon.get("listen"), str) else None
    previous_loopback = None
    if previous:
        try:
            previous_host, _ = split_listen(previous)
            previous_loopback = is_loopback_host(previous_host)
        except HardenError:
            previous_loopback = False
    if previous != listen:
        daemon["listen"] = listen
        config["daemon"] = daemon
        save_config(home, config)
    print(
        json.dumps(
            {
                "previous": previous,
                "previous_loopback": previous_loopback,
                "listen": listen,
            }
        )
    )


def cmd_set_password_hash(args: argparse.Namespace) -> None:
    if not BCRYPT_HASH_RE.match(args.bcrypt_hash):
        raise HardenError("value does not look like a bcrypt hash")
    home = Path(args.home)
    config = load_config(home)
    daemon = daemon_section(config)
    auth = daemon.get("auth")
    if not isinstance(auth, dict):
        auth = {}
    auth["password"] = args.bcrypt_hash
    daemon["auth"] = auth
    config["daemon"] = daemon
    save_config(home, config)
    print(json.dumps({"password": "set"}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", default=os.path.expanduser("~/.paseo"))
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("get-listen", help="print the current daemon.listen")
    set_listen = subcommands.add_parser("set-listen", help="enforce a loopback listen target")
    set_listen.add_argument("listen", metavar="HOST:PORT")
    set_hash = subcommands.add_parser("set-password-hash", help="store a bcrypt password hash")
    set_hash.add_argument("bcrypt_hash", metavar="BCRYPT_HASH")
    args = parser.parse_args(argv)
    handlers = {
        "get-listen": cmd_get_listen,
        "set-listen": cmd_set_listen,
        "set-password-hash": cmd_set_password_hash,
    }
    try:
        handlers[args.command](args)
    except HardenError as exc:
        print(f"harden_daemon_config: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
