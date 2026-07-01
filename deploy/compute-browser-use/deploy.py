#!/usr/bin/env python3
"""CUA Remote Computer Use — Interactive Deploy Tool.

Usage:
    python deploy.py                          # Interactive mode
    python deploy.py server                   # Deploy server non-interactively
    python deploy.py client                   # Deploy client (auto-detect OS)
    python deploy.py server -b 192.168.1.100  # Specific bind address
    python deploy.py server -y                # CI mode (skip prompts)
    python deploy.py list-addresses           # List network interfaces
    python deploy.py setup-env                # Configure .env interactively

Requirements:
    pip install .
"""

from __future__ import annotations

import os
import platform
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

from pathlib import Path

import click

SCRIPT_DIR = Path(__file__).resolve().parent
os.chdir(SCRIPT_DIR)


class DeployAborted(Exception):
    """Raised when user cancels deployment (Ctrl+C)."""

    pass


# ---------------------------------------------------------------------------
# Network utilities
# ---------------------------------------------------------------------------


def get_network_interfaces():
    """Discover active network interfaces with IPv4 addresses.

    Each entry: {name, ip, iface, kind}
    - name: hostname (fallback) or interface name
    - iface: actual NIC name (e.g. eth0, wlan0, docker0)
    - kind: "ethernet", "wifi", "docker", "vpn", "loopback", "unknown"
    """
    # Build a map: IP -> iface name from `ip addr` (most reliable source)
    ip_to_iface = {}
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in out.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                iface = parts[1]
                ip = parts[3].split("/")[0]
                ip_to_iface[ip] = iface
    except Exception:
        pass

    def _kind(iface_name):
        if iface_name.startswith("docker") or iface_name.startswith("br-"):
            return "docker"
        if iface_name.startswith("veth") or iface_name.startswith("virbr"):
            return "vm"
        if iface_name.startswith("tun") or iface_name.startswith("tap"):
            return "vpn"
        if iface_name.startswith("wg"):
            return "vpn"
        if iface_name.startswith("wl") or iface_name.startswith("wlan"):
            return "wifi"
        if iface_name.startswith("en") or iface_name.startswith("eth"):
            return "ethernet"
        if iface_name == "lo":
            return "loopback"
        return "unknown"

    interfaces, seen = [], set()

    # Source 1: `ip addr` (most accurate — gives real interface name)
    for ip, iface in sorted(ip_to_iface.items()):
        if ip in seen or ip.startswith("127."):
            continue
        seen.add(ip)
        interfaces.append(
            {
                "name": iface,
                "ip": ip,
                "iface": iface,
                "kind": _kind(iface),
            }
        )

    # Source 2: hostname addrinfo (catch any IPs `ip addr` missed)
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip in seen or ip.startswith("127."):
                continue
            seen.add(ip)
            iface = ip_to_iface.get(ip, hostname)
            interfaces.append(
                {
                    "name": hostname,
                    "ip": ip,
                    "iface": iface,
                    "kind": _kind(iface) if iface in ip_to_iface else "unknown",
                }
            )
    except Exception:
        pass

    return interfaces


def _get_hostname_addrs():
    results = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            results.append({"name": socket.gethostname(), "ip": info[4][0]})
    except Exception:
        pass
    return results


def _get_ip_addr():
    results = []
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in out.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                results.append({"name": parts[1], "ip": parts[3].split("/")[0]})
    except Exception:
        pass
    return results


def _get_ifconfig():
    results, current = [], None
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5)
        for line in out.stdout.split("\n"):
            if line and line[0] not in ("\t", " "):
                current = line.split(":")[0] if ":" in line else line.split()[0]
            elif "inet " in line and current:
                m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                if m and m.group(1) != "127.0.0.1":
                    results.append({"name": current, "ip": m.group(1)})
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------


def docker_available():
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5
            ).returncode
            == 0
        )
    except Exception:
        return False


def docker_compose_available():
    try:
        return (
            subprocess.run(
                ["docker", "compose", "version"], capture_output=True, timeout=5
            ).returncode
            == 0
        )
    except Exception:
        return False


def _http_get(path, port):
    try:
        r = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                f"http://127.0.0.1:{port}{path}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return "err"


def _http_reachable(port, timeout=5):
    try:
        r = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                f"http://127.0.0.1:{port}/",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout.strip() not in ("", "000", "err")
    except Exception:
        return False


def _container_running(container_name):
    """Check if a Docker container is in 'running' state."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip() == "true"
    except Exception:
        return False


def _wait_http_200(port, path="/", max_attempts=20, interval=5, label="service"):
    """Poll until an HTTP endpoint returns 200. Returns True if ready."""
    for attempt in range(max_attempts):
        time.sleep(interval)
        code = _http_get(path, port)
        if code == "200":
            click.secho(f"  [ok] {label} is up (HTTP 200)", fg="green")
            return True
        if attempt < max_attempts - 1:
            click.echo(
                f"  Waiting for {label}... ({attempt+1}/{max_attempts}, HTTP {code})"
            )
    click.secho(
        f"  [warn] {label} did not return 200 after {max_attempts * interval}s",
        fg="yellow",
    )
    return False


# ---------------------------------------------------------------------------
# questionary
# ---------------------------------------------------------------------------


def _q():
    try:
        import questionary

        return questionary
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------


def read_env():
    env_path = SCRIPT_DIR / ".env"
    if not env_path.exists():
        return {}
    result = {}
    for line in env_path.read_text().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        result[k.strip()] = v.strip()
    return result


def write_env(data: dict):
    env_path = SCRIPT_DIR / ".env"
    lines = [
        "# Remote Computer Use — Environment (generated by deploy.py)",
        "",
        "# --- Authentication Tokens ---",
        f"HERMES_ACCESS_TOKEN={data.get('HERMES_ACCESS_TOKEN', '')}",
        f"CLIENT_TOKEN={data.get('CLIENT_TOKEN', '')}",
        "",
        "# --- Client Connection ---",
        f"CUACTL_ENDPOINT={data.get('CUACTL_ENDPOINT', '')}",
        "CUACTL_TOKEN=${CLIENT_TOKEN}",
        "",
        "# --- LLM Provider ---",
        "# Only one provider key is needed. deploy.py auto-detects which one",
        "# is set and configures both AstrBot and hermes-api accordingly.",
    ]
    for name, info in PROVIDER_REGISTRY.items():
        env_key = info["env_key_name"]
        val = data.get(env_key, "")
        if val or env_key in data:
            lines.append(f"{env_key}={val}")
    lines += [
        f"OPENAI_BASE_URL={data.get('OPENAI_BASE_URL', '')}",
        "",
        "# --- AstrBot ---",
        f"ASTRBOT_PROVIDER_MODEL={data.get('ASTRBOT_PROVIDER_MODEL', '')}",
        f"ASTRBOT_DASHBOARD_PASSWORD={data.get('ASTRBOT_DASHBOARD_PASSWORD', '')}",
        "",
        "# --- AstrBot ---",
        f"ASTRBOT_DASHBOARD_PASSWORD={data.get('ASTRBOT_DASHBOARD_PASSWORD', '')}",
        "",
    ]
    env_path.write_text("\n".join(lines) + "\n")


def generate_token():
    return secrets.token_hex(32)


def setup_env_interactive():
    try:
        _setup_env_impl()
    except KeyboardInterrupt:
        click.echo()
        click.secho("Configuration cancelled.", fg="yellow")
        raise DeployAborted()


def _setup_env_impl():
    q = _q()
    click.secho("\n=== Configure Environment (.env) ===", fg="cyan", bold=True)
    click.echo()
    data = read_env()
    for key in ("HERMES_ACCESS_TOKEN", "CLIENT_TOKEN"):
        if not data.get(key):
            data[key] = generate_token()
            click.secho(f"  [generated] {key}", fg="green")
        else:
            click.echo(f"  [existing]  {key}")
    click.echo()

    current_ep = data.get("CUACTL_ENDPOINT", "")
    if q:
        endpoints = ["https://your-client-ip:9111 (set later)"]
        for iface in get_network_interfaces():
            endpoints.append(f"https://{iface['ip']}:9111 ({iface['name']})")
        ep = q.select(
            "Client Control Plane endpoint:",
            choices=[q.Choice(e, value=e.split()[0]) for e in endpoints],
            default=current_ep if current_ep else endpoints[0].split()[0],
        ).ask()
        if ep:
            data["CUACTL_ENDPOINT"] = ep
    else:
        new_ep = click.prompt(
            "Client Control Plane endpoint",
            default=current_ep or "https://your-client-ip:9111",
        )
        data["CUACTL_ENDPOINT"] = new_ep
    click.echo()

    click.secho("LLM Providers", fg="yellow")
    click.echo(_configured_provider_summary(data))
    click.echo()
    if q:
        while True:
            remaining = [n for n in PROVIDER_REGISTRY if PROVIDER_REGISTRY[n]["env_key_name"] not in data or not data[PROVIDER_REGISTRY[n]["env_key_name"]].strip()]
            if not remaining:
                click.secho("  All providers configured. Skipping.", fg="green")
                break
            if not q.confirm("Add another provider?", default=bool(not _resolve_providers_from_env(data))).ask():
                break
            provider = q.select("Select provider:", choices=_provider_choices()).ask()
            if not provider or provider == "skip":
                break
            info = PROVIDER_REGISTRY.get(provider, {})
            env_key = info.get("env_key_name", "OPENAI_API_KEY")
            label = info.get("label", provider)
            key = q.password(f"Enter {label} API key:").ask()
            if key:
                data[env_key] = key
                if provider == "ollama":
                    data[env_key] = "ollama"
                    base = q.text("Base URL:", default=info.get("base_url", "http://127.0.0.1:11434/v1")).ask()
                    if base:
                        data["OLLAMA_BASE_URL"] = base
                models = info.get("models", [])
                if models:
                    if q.confirm(f"Default model: {models[0][1]}. Select a different one?", default=False).ask():
                        model = q.select("Choose model:", choices=[
                            q.Choice(m[1], value=m[0]) for m in models
                        ]).ask()
                    else:
                        model = models[0][0]
                    if not data.get("ASTRBOT_PROVIDER_MODEL"):
                        data["ASTRBOT_PROVIDER_MODEL"] = model
                click.secho(f"  [ok] {label} configured", fg="green")
                click.echo(_configured_provider_summary(data))
                click.echo()
            else:
                click.secho("  [skip] No key entered", fg="yellow")
    else:
        if click.confirm("Configure LLM key now?", default=False):
            key = click.prompt("API Key (or Enter to skip)", default="", show_default=False)
            if key:
                provider = click.prompt(
                    "Provider (deepseek/zhipu/minimax/openrouter/kimi/longcat/siliconflow/opencode-go/anthropic/openai)",
                    default="deepseek",
                )
                info = PROVIDER_REGISTRY.get(provider)
                if info:
                    data[info["env_key_name"]] = key
                    models = info.get("models", [])
                    if models and not data.get("ASTRBOT_PROVIDER_MODEL"):
                        data["ASTRBOT_PROVIDER_MODEL"] = models[0][0]
                else:
                    data["OPENAI_API_KEY"] = key
    click.echo()

    if not data.get("ASTRBOT_DASHBOARD_PASSWORD"):
        if q:
            pwd = q.password(
                "AstrBot dashboard password (empty = auto-generate):"
            ).ask()
            if pwd:
                data["ASTRBOT_DASHBOARD_PASSWORD"] = pwd
            else:
                # Auto-generate: must meet astrbot requirements (>=8 chars, upper+lower+digit)
                pwd = secrets.token_urlsafe(12) + "A1"
                data["ASTRBOT_DASHBOARD_PASSWORD"] = pwd
                click.secho(f"  Auto-generated password: {pwd}", fg="cyan")
                click.secho("  (save this — it won't be shown again)", fg="yellow")
        else:
            pwd = click.prompt(
                "AstrBot dashboard password", default="", show_default=False
            )
            if pwd:
                data["ASTRBOT_DASHBOARD_PASSWORD"] = pwd
            else:
                pwd = secrets.token_urlsafe(12) + "A1"
                data["ASTRBOT_DASHBOARD_PASSWORD"] = pwd
                click.secho(f"  Auto-generated password: {pwd}", fg="cyan")

    write_env(data)
    if not mode and not address:  # not reached normally, but safe
        pass
    click.secho("\n.env saved.", fg="green")

    if not data.get("ANTHROPIC_API_KEY") and not data.get("OPENAI_API_KEY"):
        click.echo()
        click.secho(
            "LLM key not configured — set later via: python deploy.py setup-env",
            fg="yellow",
        )


PLUGIN_REPO = "https://github.com/konodiodaaaaa1/astrbot_plugin_hermes_connector"
PLUGIN_ZIP_URL = f"{PLUGIN_REPO}/archive/master.zip"
PLUGIN_DIR_NAME = "astrbot_plugin_hermes_connector-master"
ASTRBOT_CONTAINER = "cua-astrbot"
ASTRBOT_PLUGIN_PATH = "/AstrBot/data/plugins/astrbot_plugin_hermes_connector"
HAPI_PLUGIN_REPO = "https://github.com/LiJinHao999/astrbot_plugin_hapi_connector"
HAPI_PLUGIN_PATH = "/AstrBot/data/plugins/astrbot_plugin_hapi_connector"
ASTRBOT_CONFIG_PATH = "/AstrBot/data/cmd_config.json"


# Provider registry: human name → (astrbot_type, default_model)
# Unified provider registry — single source of truth for all LLM providers.
# Each entry drives: .env key names, AstrBot native provider_source config,
# hermes config.yaml model.provider + .env key, and the interactive picker.
#
# Fields:
#   label:         Display name for the interactive picker
#   astrbot:       AstrBot native provider_source template (id/type/api_base/etc.)
#                  — type and api_base match AstrBot v4.26.x default.py
#   hermes:        hermes config.yaml model.provider value + .env key name
#                  — provider matches hermes plugins/model-providers/<name>/
#                  — env_var matches the provider profile's env_vars tuple
#   models:        List of (model_id, display_name) — first is default
#   env_key_name:  The .env variable name deploy.py writes the API key into
#                  (also used as the canonical key in the .env file)
#   base_url:      The api_base URL (shared by AstrBot source + hermes config)
#   api_format:    "openai" or "anthropic" — determines AstrBot type + hermes wire
PROVIDER_REGISTRY = {
    "deepseek": {
        "label": "DeepSeek (深度求索)",
        "base_url": "https://api.deepseek.com/v1",
        "env_key_name": "DEEPSEEK_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "openai_chat_completion",
            "id": "deepseek",
        },
        "hermes": {
            "provider": "deepseek",
        },
        "models": [
            ("deepseek-v4-flash", "DeepSeek V4 Flash (快速)"),
            ("deepseek-v4-pro", "DeepSeek V4 Pro (思考)"),
        ],
    },
    "zhipu": {
        "label": "Zhipu GLM (智谱 / Z.AI)",
        "base_url": "https://api.z.ai/api/paas/v4",
        "env_key_name": "GLM_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "zhipu_chat_completion",
            "id": "zhipu",
            "api_base_override": "https://open.bigmodel.cn/api/paas/v4/",
        },
        "hermes": {
            "provider": "zai",
        },
        "models": [
            ("glm-5.2", "GLM-5.2 (旗舰)"),
            ("glm-5.1", "GLM-5.1"),
            ("glm-4.5-flash", "GLM-4.5 Flash (快速)"),
        ],
    },
    "minimax": {
        "label": "MiniMax",
        "base_url": "https://api.minimax.io/anthropic",
        "env_key_name": "MINIMAX_API_KEY",
        "api_format": "anthropic",
        "astrbot": {
            "type": "openai_chat_completion",
            "id": "minimax",
            "api_base_override": "https://api.minimaxi.com/v1",
        },
        "hermes": {
            "provider": "minimax",
        },
        "models": [
            ("MiniMax-M3", "MiniMax M3 (1M 上下文)"),
            ("MiniMax-M2.7", "MiniMax M2.7"),
        ],
    },
    "openrouter": {
        "label": "OpenRouter (400+ 模型聚合)",
        "base_url": "https://openrouter.ai/api/v1",
        "env_key_name": "OPENROUTER_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "openrouter_chat_completion",
            "id": "openrouter",
        },
        "hermes": {
            "provider": "openrouter",
        },
        "models": [
            ("anthropic/claude-opus-4.8", "Claude Opus 4.8 (via OpenRouter)"),
            ("openai/gpt-5.5", "GPT-5.5 (via OpenRouter)"),
            ("deepseek/deepseek-chat", "DeepSeek Chat (via OpenRouter)"),
        ],
    },
    "kimi": {
        "label": "Moonshot Kimi (月之暗面)",
        "base_url": "https://api.moonshot.ai/v1",
        "env_key_name": "KIMI_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "openai_chat_completion",
            "id": "moonshot",
            "api_base_override": "https://api.moonshot.cn/v1",
        },
        "hermes": {
            "provider": "kimi-coding",
        },
        "models": [
            ("kimi-k2.7-code", "Kimi K2.7 Code (编程优化)"),
            ("kimi-k2.6", "Kimi K2.6 (256K 上下文)"),
        ],
    },
    "longcat": {
        "label": "LongCat (美团)",
        "base_url": "https://api.longcat.chat/openai",
        "env_key_name": "LONGCAT_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "longcat_chat_completion",
            "id": "longcat",
        },
        "hermes": {
            "provider": "custom",
        },
        "models": [
            ("LongCat-2.0", "LongCat 2.0 (旗舰)"),
            ("LongCat-Flash-Chat", "LongCat Flash Chat (快速)"),
        ],
    },
    "siliconflow": {
        "label": "SiliconFlow (硅基流动)",
        "base_url": "https://api.siliconflow.cn/v1",
        "env_key_name": "SILICONFLOW_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "openai_chat_completion",
            "id": "aihubmix",
            "api_base_override": "https://api.siliconflow.cn/v1",
        },
        "hermes": {
            "provider": "custom",
        },
        "models": [
            ("Qwen/Qwen2.5-72B-Instruct", "Qwen 2.5 72B"),
            ("Pro/deepseek-ai/DeepSeek-R1", "DeepSeek R1 (Pro)"),
        ],
    },
    "opencode-go": {
        "label": "OpenCode Go (订阅制，含 GLM/Kimi/DeepSeek/MiniMax 等)",
        "base_url": "https://opencode.ai/zen/go/v1",
        "env_key_name": "OPENCODE_GO_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "openai_chat_completion",
            "id": "opencode-go",
        },
        "hermes": {
            "provider": "opencode-go",
        },
        "models": [
            ("kimi-k2.7-code", "Kimi K2.7 Code (via Go)"),
            ("glm-5.2", "GLM-5.2 (via Go)"),
            ("deepseek-v4-pro", "DeepSeek V4 Pro (via Go)"),
            ("minimax-m3", "MiniMax M3 (via Go, Anthropic wire)"),
        ],
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1",
        "env_key_name": "ANTHROPIC_API_KEY",
        "api_format": "anthropic",
        "astrbot": {
            "type": "anthropic_chat_completion",
            "id": "anthropic",
        },
        "hermes": {
            "provider": "anthropic",
        },
        "models": [
            ("claude-opus-4.8", "Claude Opus 4.8"),
            ("claude-sonnet-4-20250514", "Claude Sonnet 4"),
        ],
    },
    "openai": {
        "label": "OpenAI (GPT)",
        "base_url": "https://api.openai.com/v1",
        "env_key_name": "OPENAI_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "openai_chat_completion",
            "id": "openai",
        },
        "hermes": {
            "provider": "openrouter",
        },
        "models": [
            ("gpt-5.5", "GPT-5.5"),
            ("gpt-4o", "GPT-4o"),
        ],
    },
    "ollama": {
        "label": "Ollama (本地)",
        "base_url": "http://127.0.0.1:11434/v1",
        "env_key_name": "OPENAI_API_KEY",
        "api_format": "openai",
        "astrbot": {
            "type": "openai_chat_completion",
            "id": "ollama",
        },
        "hermes": {
            "provider": "custom",
        },
        "models": [],
    },
}


def _provider_choices():
    q = _q()
    if not q:
        return []
    cloud = [q.Choice(f"{info['label']}", value=name)
             for name, info in PROVIDER_REGISTRY.items()
             if name not in ("ollama",)]
    ollama_info = PROVIDER_REGISTRY.get("ollama", {})
    ollama_label = ollama_info.get("label", "Ollama (local)")
    local = [q.Choice(ollama_label, value="ollama")]
    return [
        q.Separator("— Cloud —"), *cloud,
        q.Separator("— Local —"), *local,
        q.Separator(""), q.Choice("Skip (configure later)", value="skip"),
    ]


def _provider_models(provider: str):
    info = PROVIDER_REGISTRY.get(provider)
    if not info:
        return []
    return info.get("models", [])


def _install_hermes_connector_plugin():
    """Install the Hermes Connector plugin into the running AstrBot.

    Skips if the plugin is already present (from a previous deploy).
    Restarts astrbot after copying so the plugin is detected on the next scan.
    """
    # Check if plugin is already installed in the container
    try:
        r = subprocess.run(
            ["docker", "exec", ASTRBOT_CONTAINER, "test", "-d", ASTRBOT_PLUGIN_PATH],
            capture_output=True,
            timeout=5,
        )
        if r.returncode == 0:
            click.secho("\nHermes Connector plugin already installed", fg="green")
            return
    except Exception:
        pass  # Container might not be running yet, proceed with install

    click.secho("\nInstalling Hermes Connector plugin...", fg="yellow")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        zip_path = tmp / "plugin.zip"

        try:
            click.echo(f"  Downloading {PLUGIN_ZIP_URL} ...")
            urllib.request.urlretrieve(PLUGIN_ZIP_URL, zip_path)
        except Exception as e:
            click.secho(f"  Download failed: {e}", fg="yellow")
            click.secho(
                f"  Install manually in AstrBot Dashboard → Plugins → {PLUGIN_REPO}",
                fg="yellow",
            )
            return

        # Verify download: check file size and zip integrity
        zip_size = zip_path.stat().st_size
        if zip_size < 1024:
            click.secho(
                f"  Download corrupted: file too small ({zip_size} bytes)", fg="red"
            )
            click.secho(
                f"  Install manually in AstrBot Dashboard -> Plugins -> {PLUGIN_REPO}",
                fg="yellow",
            )
            return
        click.echo(f"  Downloaded {zip_size // 1024} KB, verifying integrity...")

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Check zip structural integrity
                bad_file = zf.testzip()
                if bad_file is not None:
                    raise zipfile.BadZipFile(f"corrupt entry: {bad_file}")
                zf.extractall(tmp)
            extracted = tmp / PLUGIN_DIR_NAME
            if not extracted.is_dir():
                raise FileNotFoundError(PLUGIN_DIR_NAME)
        except Exception as e:
            click.secho(f"  Extract failed: {e}", fg="yellow")
            return

        # Verify critical plugin files exist
        required = ["main.py"]
        for fname in required:
            if not (extracted / fname).is_file():
                click.secho(
                    f"  Plugin package missing required file: {fname}", fg="yellow"
                )
                click.secho(
                    f"  Install manually in AstrBot Dashboard -> Plugins -> {PLUGIN_REPO}",
                    fg="yellow",
                )
                return
        click.secho("  Verified: plugin files intact", fg="green")

        try:
            subprocess.run(
                [
                    "docker",
                    "cp",
                    str(extracted) + "/.",
                    f"{ASTRBOT_CONTAINER}:{ASTRBOT_PLUGIN_PATH}",
                ],
                check=True,
                capture_output=True,
            )
            click.secho(
                "  Plugin installed — AstrBot will detect it automatically", fg="green"
            )
            click.secho(
                "  Triggering docker restart to load the plugin...", fg="yellow"
            )
            subprocess.run(
                ["docker", "restart", ASTRBOT_CONTAINER],
                check=True,
                capture_output=True,
            )
            click.secho("  AstrBot restarted — plugin should now be active", fg="green")
        except subprocess.CalledProcessError as e:
            click.secho(f"  docker cp failed: {e.stderr.decode()[:200]}", fg="yellow")
            click.secho(
                f"  Install manually in AstrBot Dashboard → Plugins → {PLUGIN_REPO}",
                fg="yellow",
            )


def _resolve_providers_from_env(data: dict):
    """Return all PROVIDER_REGISTRY entries that have a key set in .env.

    Returns list of (provider_name, api_key, model), vendor-specific keys
    first, generic OPENAI_API_KEY last. Empty if no keys configured.
    """
    deferred = []
    result = []
    for name, info in PROVIDER_REGISTRY.items():
        env_key = info["env_key_name"]
        key_val = data.get(env_key, "").strip()
        if not key_val:
            continue
        if env_key == "OPENAI_API_KEY":
            deferred.append((name, key_val))
            continue
        models = info.get("models", [])
        model = models[0][0] if models else ""
        result.append((name, key_val, model))
    for name, key_val in deferred:
        models = PROVIDER_REGISTRY[name].get("models", [])
        model = models[0][0] if models else ""
        result.append((name, key_val, model))
    return result


def _resolve_provider_from_env(data: dict):
    """Return the first (preferred) provider from .env, or (None, None, None)."""
    all_providers = _resolve_providers_from_env(data)
    if all_providers:
        return all_providers[0]
    return None, None, None


def _configured_provider_summary(data: dict):
    """Return a human-readable summary of configured providers for display."""
    all_p = _resolve_providers_from_env(data)
    if not all_p:
        return "  (none configured)"
    lines = []
    for name, _key, model in all_p:
        info = PROVIDER_REGISTRY.get(name, {})
        label = info.get("label", name)
        model_disp = f" → {model}" if model else ""
        lines.append(f"  ✓ {label}{model_disp}")
    return "\n".join(lines)


def _configure_hermes_env(data: dict):
    """Write ~/.hermes/.env + config.yaml inside the hermes-api container.

    Uses hermes's native provider names (from PROVIDER_REGISTRY) so hermes
    picks up the correct env var and base_url automatically — no hostname
    derivation needed.
    """
    provider_name, api_key, model = _resolve_provider_from_env(data)
    if not provider_name:
        click.secho("  [skip] No LLM key in .env — hermes won't be able to call LLMs", fg="yellow")
        return

    info = PROVIDER_REGISTRY[provider_name]
    env_key = info["env_key_name"]
    base_url = info["base_url"]
    hermes_provider = info["hermes"]["provider"]

    lines = [f"{env_key}={api_key}"]
    if provider_name == "openai":
        lines.append(f"OPENAI_API_KEY={api_key}")
    env_content = "\n".join(lines) + "\n"

    inner_script = (
        "import os\n"
        "env_path = '/home/hermes/.hermes/.env'\n"
        "config_path = '/home/hermes/.hermes/config.yaml'\n"
        f"env_content = {env_content!r}\n"
        f"model_default = {model!r}\n"
        f"model_provider = {hermes_provider!r}\n"
        f"model_base_url = {base_url!r}\n"
        "os.makedirs(os.path.dirname(env_path), exist_ok=True)\n"
        "with open(env_path, 'w') as f:\n"
        "    f.write(env_content)\n"
        "with open(config_path, 'r') as f:\n"
        "    content = f.read()\n"
        "lines = content.split(chr(10))\n"
        "new_lines = []\n"
        "in_model = False\n"
        "model_written = False\n"
        "for line in lines:\n"
        "    stripped = line.lstrip()\n"
        "    if stripped and not stripped.startswith('#') and not line.startswith(' '):\n"
        "        if stripped.startswith('model:'):\n"
        "            in_model = True\n"
        "            model_written = True\n"
        "            new_lines.append('model:')\n"
        "            new_lines.append('  default: ' + repr(model_default))\n"
        "            new_lines.append('  provider: ' + repr(model_provider))\n"
        "            new_lines.append('  base_url: ' + repr(model_base_url))\n"
        "            continue\n"
        "        else:\n"
        "            in_model = False\n"
        "    if in_model:\n"
        "        continue\n"
        "    new_lines.append(line)\n"
        "if not model_written:\n"
        "    new_lines.insert(0, 'model:')\n"
        "    new_lines.insert(1, '  default: ' + repr(model_default))\n"
        "    new_lines.insert(2, '  provider: ' + repr(model_provider))\n"
        "    new_lines.insert(3, '  base_url: ' + repr(model_base_url))\n"
        "    new_lines.insert(4, '')\n"
        "with open(config_path, 'w') as f:\n"
        "    f.write(chr(10).join(new_lines))\n"
        "n = env_content.count(chr(10)) - (1 if env_content.endswith(chr(10)) else 0)\n"
        "print(f'wrote ' + str(n) + ' env keys + patched model block in config.yaml (provider=' + str(model_provider) + ')')\n"
    )

    try:
        r = subprocess.run(
            ["docker", "exec", "cua-hermes-api", "python3", "-c", inner_script],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            click.secho(f"  [ok] Hermes configured: {r.stdout.strip()}", fg="green")
            subprocess.run(["docker", "restart", "cua-hermes-api"], capture_output=True)
            click.secho("  [ok] hermes-api restarted to load new credentials", fg="green")
        else:
            click.secho(f"  [warn] Hermes config write failed: {r.stderr[:200]}", fg="yellow")
    except Exception as e:
        click.secho(f"  [warn] Hermes config failed: {e}", fg="yellow")


def _configure_astrbot_providers(data: dict):
    """Inject all configured LLM providers into AstrBot using native provider_sources.

    Iterates over every provider that has a key in .env and writes them all
    into AstrBot's cmd_config.json. The first provider becomes the default.
    Uses AstrBot's built-in source IDs (deepseek, zhipu, minimax, etc.).
    """
    all_providers = _resolve_providers_from_env(data)
    if not all_providers:
        click.secho("\n  [skip] No LLM key configured — run setup-env first", fg="yellow")
        return

    import json as _json
    sources_to_write = []
    models_to_write = []
    default_provider_id = None

    for provider_name, api_key, model in all_providers:
        info = PROVIDER_REGISTRY[provider_name]
        astrbot = info["astrbot"]
        base_url = astrbot.get("api_base_override", info["base_url"])
        source_type = astrbot["type"]
        source_id = astrbot["id"]
        provider_id = f"cua_{source_id}"

        source_config = {
            "id": source_id,
            "type": source_type,
            "provider_type": "chat_completion",
            "enable": True,
            "key": [api_key],
            "api_base": base_url,
            "timeout": 120,
            "proxy": "",
            "custom_headers": {},
        }
        model_config = {
            "id": provider_id,
            "model": model,
            "enable": True,
            "provider_source_id": source_id,
            "modalities": [],
            "custom_extra_body": {},
        }
        sources_to_write.append((source_id, _json.dumps(source_config, ensure_ascii=False)))
        models_to_write.append((provider_id, _json.dumps(model_config, ensure_ascii=False)))
        if default_provider_id is None:
            default_provider_id = provider_id

        click.secho(f"  → {info.get('label', provider_name)}: {source_id} ({model})", fg="cyan")

    sources_json_items = ", ".join(f'json.loads({sj!r})' for _, sj in sources_to_write)
    models_json_items = ", ".join(f'json.loads({mj!r})' for _, mj in models_to_write)
    source_ids = [sid for sid, _ in sources_to_write]
    provider_ids = [pid for pid, _ in models_to_write]

    cfg_path = ASTRBOT_CONFIG_PATH
    inner_script = (
        "import json\n"
        f"cfg_path = {cfg_path!r}\n"
        f"new_sources = [{sources_json_items}]\n"
        f"new_models = [{models_json_items}]\n"
        f"source_ids = {source_ids!r}\n"
        f"provider_ids = {provider_ids!r}\n"
        "with open(cfg_path, 'r', encoding='utf-8-sig') as f:\n"
        "    config = json.load(f)\n"
        "old_sources = [s for s in config.get('provider_sources', []) if s.get('id') not in source_ids]\n"
        "config['provider_sources'] = old_sources + new_sources\n"
        "old_models = [p for p in config.get('provider', []) if p.get('id') not in provider_ids]\n"
        "config['provider'] = old_models + new_models\n"
        "config.setdefault('provider_settings', {})['enable'] = True\n"
        f"config['provider_settings']['default_provider_id'] = {default_provider_id!r}\n"
        "with open(cfg_path, 'w', encoding='utf-8') as f:\n"
        "    json.dump(config, f, indent=2, ensure_ascii=False)\n"
        f"print('providers configured: ' + str(len(new_sources)) + ' sources, default=' + {default_provider_id!r})\n"
    )
    try:
        r = subprocess.run(
            ["docker", "exec", ASTRBOT_CONTAINER, "python3", "-c", inner_script],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            click.secho(f"  [ok] {r.stdout.strip()}", fg="green")
        else:
            click.secho(f"  [warn] Provider config failed: {r.stderr[:200]}", fg="yellow")
    except Exception as e:
        click.secho(f"  [warn] Provider config failed: {e}", fg="yellow")


def _configure_astrbot_provider(data: dict):
    """Backward-compat wrapper — delegates to _configure_astrbot_providers."""
    _configure_astrbot_providers(data)


def _install_cuactl_host():
    """Install cuactl CLI on the Docker host for multi-agent access."""
    relay_script = SCRIPT_DIR / "server" / "cua-relay" / "relay_server.py"
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    cuactl_dest = local_bin / "cuactl"
    if cuactl_dest.exists():
        click.secho(f"  cuactl already at {cuactl_dest}", fg="green")
        return
    click.secho(
        "\n  Installing cuactl on host (for codex / multi-agent)...", fg="yellow"
    )
    env_file = SCRIPT_DIR / ".env"
    wrapper = f'#!/bin/bash\nset -a\nsource "{env_file}"\nset +a\nexec python3 "{relay_script}" "$@"\n'
    cuactl_dest.write_text(wrapper)
    cuactl_dest.chmod(0o755)
    click.secho(f"  [ok] cuactl → {cuactl_dest}", fg="green")
    # Warn if ~/.local/bin not in PATH
    path_dirs = os.environ.get("PATH", "").split(":")
    if str(local_bin) not in path_dirs:
        click.secho(
            f"  [warn] {local_bin} not in PATH — add to your shell rc:", fg="yellow"
        )
        click.secho(
            f"         echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc",
            fg="yellow",
        )


def _ensure_node_npm():
    """Ensure Node.js + npm are available. Install via nvm if missing.

    Returns (npm_bin, node_bin_dir) — absolute paths to npm and the node bin
    directory, or (None, None) if installation failed.
    """
    nvm_dir = Path.home() / ".nvm"

    def _has_npm():
        try:
            return (
                subprocess.run(
                    ["npm", "--version"], capture_output=True, timeout=5
                ).returncode
                == 0
            )
        except Exception:
            return False

    if _has_npm():
        versions = sorted((nvm_dir / "versions" / "node").glob("*"), reverse=True)
        if versions:
            node_bin_dir = versions[0] / "bin"
            npm_bin = (
                str(node_bin_dir / "npm") if (node_bin_dir / "npm").exists() else "npm"
            )
            return npm_bin, node_bin_dir
        return "npm", None

    click.secho("  npm not found — need Node.js for HAPI / opencode-ai", fg="yellow")
    if not click.confirm(
        "  Install Node.js via nvm (user-level, no sudo)?", default=True
    ):
        click.secho(
            "  [skip] Skipped Node.js install — HAPI / opencode not available",
            fg="yellow",
        )
        return None, None

    if not (nvm_dir / "nvm.sh").exists():
        click.secho("  Installing nvm...", fg="yellow")
        try:
            nvm_install_url = (
                "https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh"
            )
            r = subprocess.run(
                ["curl", "-sSL", nvm_install_url],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            r2 = subprocess.run(
                ["bash"], input=r.stdout, capture_output=True, text=True, timeout=60
            )
            if r2.returncode != 0:
                raise subprocess.CalledProcessError(r2.returncode, "nvm install")
            click.secho("  [ok] nvm installed", fg="green")
        except Exception as e:
            click.secho(f"  [warn] nvm install failed: {e}", fg="yellow")
            click.secho(
                "  Install manually: https://nodejs.org/en/download", fg="yellow"
            )
            return None, None

    click.secho("  Installing Node.js via nvm (this may take a minute)...", fg="yellow")
    try:
        nvm_sh = f'source "{nvm_dir}/nvm.sh" && nvm install --lts && nvm use --lts'
        r = subprocess.run(
            ["bash", "-c", nvm_sh], capture_output=True, text=True, timeout=300
        )
        if r.returncode != 0:
            raise subprocess.CalledProcessError(r.returncode, "nvm install node")
        click.secho("  [ok] Node.js installed via nvm", fg="green")
        versions = sorted((nvm_dir / "versions" / "node").glob("*"), reverse=True)
        if versions:
            node_bin_dir = versions[0] / "bin"
            npm_bin = str(node_bin_dir / "npm")
            click.secho(
                f"  [ok] Node.js {versions[0].name}, npm at {npm_bin}", fg="green"
            )
            return npm_bin, node_bin_dir
        click.secho("  [warn] No Node.js version found after nvm install", fg="yellow")
        return None, None
    except subprocess.CalledProcessError as e:
        click.secho(f"  [warn] Node.js install failed: {e}", fg="yellow")
        click.secho(
            "  Install Node.js manually: https://nodejs.org/en/download", fg="yellow"
        )
        return None, None
    except KeyboardInterrupt:
        click.echo()
        click.secho("  [skip] Cancelled", fg="yellow")
        return None, None


def _npm_env(node_bin_dir):
    env = os.environ.copy()
    if node_bin_dir and str(node_bin_dir) not in env.get("PATH", ""):
        env["PATH"] = f"{node_bin_dir}:{env.get('PATH', '')}"
    return env


def _check_codex_cli():
    """Check if Codex CLI is installed. Install via npm if not found.

    Codex CLI runs on the host (not containerized) because it needs
    filesystem access for coding tasks. AstrBot connects to it via
    the HAPI connector plugin (host.docker.internal:3006).
    """
    try:
        r = subprocess.run(
            ["codex", "--version"], capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            ver = r.stdout.strip().split("\n")[0] if r.stdout else "unknown"
            click.secho(f"  [ok] Codex CLI found: {ver}", fg="green")
            return
    except Exception:
        pass

    for path in [
        Path.home() / ".nvm" / "versions" / "node" / "v24.14.0" / "bin" / "codex",
        Path("/usr/local/bin/codex"),
        Path("/usr/bin/codex"),
    ]:
        if path.exists():
            click.secho(f"  [ok] Codex CLI found at {path}", fg="green")
            return

    npm_bin, node_bin_dir = _ensure_node_npm()
    if npm_bin is None:
        return

    click.secho("  Installing Codex CLI via npm...", fg="yellow")
    env = _npm_env(node_bin_dir)
    try:
        subprocess.run(
            [npm_bin, "install", "-g", "@openai/codex"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        click.secho("  [ok] Codex CLI installed", fg="green")
    except subprocess.CalledProcessError as e:
        click.secho(
            f"  [warn] npm install failed: {e.stderr[:200] if e.stderr else e}",
            fg="yellow",
        )
        click.secho("  Install manually: npm install -g @openai/codex", fg="yellow")
    except Exception as e:
        click.secho(f"  [warn] Codex install failed: {e}", fg="yellow")


def _check_opencode(non_interactive=False):
    try:
        r = subprocess.run(
            ["opencode", "--version"], capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            ver = r.stdout.strip().split("\n")[0] if r.stdout else "unknown"
            click.secho(f"  [ok] OpenCode found: {ver}", fg="green")
            return
    except Exception:
        pass

    click.secho("  OpenCode not found — installing via curl installer...", fg="yellow")
    if not non_interactive:
        if not click.confirm("  Install OpenCode now?", default=True):
            click.secho("  [skip] OpenCode skipped", fg="yellow")
            return

    try:
        r = subprocess.run(
            ["curl", "-fsSL", "https://opencode.ai/install"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        r2 = subprocess.run(
            ["bash"], input=r.stdout, capture_output=True, text=True, timeout=120
        )
        if r2.returncode != 0:
            raise subprocess.CalledProcessError(r2.returncode, "opencode install")
        click.secho("  [ok] OpenCode installed", fg="green")
        click.secho(
            "  Next: run `opencode` in a project dir, /connect to configure LLM",
            fg="cyan",
        )
    except Exception as e:
        click.secho(f"  [warn] OpenCode install failed: {e}", fg="yellow")
        click.secho("  Alt: npm install -g opencode-ai  (needs Node.js)", fg="yellow")


def _check_hapi():
    """Check / install HAPI Hub (npm @twsxtd/hapi) — the 3006 service that
    hapi_connector connects to. HAPI wraps codex / opencode / claude-code CLIs.
    """
    npm_bin, node_bin_dir = _ensure_node_npm()
    if npm_bin is None:
        return

    # Check if hapi already installed
    hapi_bin = None
    if node_bin_dir:
        hapi_path = node_bin_dir / "hapi"
        if hapi_path.exists():
            hapi_bin = str(hapi_path)
    if not hapi_bin:
        try:
            r = subprocess.run(
                ["hapi", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env=_npm_env(node_bin_dir),
            )
            if r.returncode == 0:
                hapi_bin = "hapi"
        except Exception:
            pass

    if hapi_bin:
        click.secho(f"  [ok] HAPI Hub found: {hapi_bin}", fg="green")
        return

    click.secho("  Installing HAPI Hub via npm (@twsxtd/hapi)...", fg="yellow")
    env = _npm_env(node_bin_dir)
    try:
        subprocess.run(
            [npm_bin, "install", "-g", "@twsxtd/hapi"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        click.secho("  [ok] HAPI Hub installed", fg="green")
        click.secho(
            "  Start:  hapi hub --no-relay  (listens on 0.0.0.0:3006)", fg="cyan"
        )
        click.secho(
            "  Token:  cat ~/.hapi/settings.json  (auto-generated on first run)",
            fg="cyan",
        )
    except subprocess.CalledProcessError as e:
        click.secho(
            f"  [warn] HAPI install failed: {e.stderr[:200] if e.stderr else e}",
            fg="yellow",
        )
        click.secho("  Manual: npm install -g @twsxtd/hapi", fg="yellow")


HAPI_HOME = Path.home() / ".hapi"
HAPI_SETTINGS = HAPI_HOME / "settings.json"


def _hapi_token() -> str | None:
    if not HAPI_SETTINGS.exists():
        return None
    try:
        import json as _json

        with open(HAPI_SETTINGS) as f:
            s = _json.load(f)
        return s.get("cliApiToken") or None
    except Exception:
        return None


def _start_hapi_hub_and_configure():
    """Start HAPI Hub in background and inject its token into AstrBot's hapi_connector.

    Pre-generates a cliApiToken + listenHost=0.0.0.0 in ~/.hapi/settings.json so
    the Hub binds to all interfaces (reachable from the AstrBot container via
    host.docker.internal) and uses a known token. Then starts the Hub with nohup
    if not already running, and writes the token into the hapi_connector plugin
    config inside the AstrBot container.

    Skips gracefully if HAPI is not installed or the container is not running.
    """
    import json as _json

    npm_bin, node_bin_dir = _ensure_node_npm()
    if npm_bin is None:
        return
    env = _npm_env(node_bin_dir)
    hapi_bin = (
        str(node_bin_dir / "hapi")
        if node_bin_dir and (node_bin_dir / "hapi").exists()
        else "hapi"
    )
    try:
        r = subprocess.run(
            [hapi_bin, "--version"], capture_output=True, text=True, timeout=10, env=env
        )
        if r.returncode != 0:
            click.secho(
                "  [skip] HAPI Hub not installed — run deploy again or `npm install -g @twsxtd/hapi`",
                fg="yellow",
            )
            return
    except Exception:
        click.secho("  [skip] HAPI Hub not reachable", fg="yellow")
        return

    HAPI_HOME.mkdir(parents=True, exist_ok=True)
    (HAPI_HOME / "logs").mkdir(parents=True, exist_ok=True)
    existing = {}
    if HAPI_SETTINGS.exists():
        try:
            with open(HAPI_SETTINGS) as f:
                existing = _json.load(f)
        except Exception:
            existing = {}
    token = existing.get("cliApiToken") or secrets.token_hex(24)
    existing["listenHost"] = "0.0.0.0"
    existing["listenPort"] = existing.get("listenPort", 3006)
    existing["cliApiToken"] = token
    with open(HAPI_SETTINGS, "w") as f:
        _json.dump(existing, f, indent=2)
    click.secho(
        f"  [ok] HAPI settings: {HAPI_SETTINGS} (listenHost=0.0.0.0:{existing['listenPort']})",
        fg="green",
    )

    import urllib.request

    try:
        urllib.request.urlopen("http://127.0.0.1:3006/", timeout=2)
        hub_running = True
        click.secho("  [ok] HAPI Hub already running on :3006", fg="green")
    except Exception:
        hub_running = False

    if not hub_running:
        click.secho("  Starting HAPI Hub in background (nohup)...", fg="yellow")
        log_file = HAPI_HOME / "logs" / "hub.log"
        try:
            with open(log_file, "w") as lf:
                p = subprocess.Popen(
                    ["nohup", hapi_bin, "hub", "--no-relay"],
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    start_new_session=True,
                )
            for _ in range(15):
                time.sleep(1)
                try:
                    urllib.request.urlopen("http://127.0.0.1:3006/", timeout=1)
                    hub_running = True
                    break
                except Exception:
                    continue
            if hub_running:
                click.secho(
                    f"  [ok] HAPI Hub started (pid={p.pid}, log={log_file})", fg="green"
                )
            else:
                click.secho(
                    f"  [warn] HAPI Hub did not bind :3006 within 15s — check {log_file}",
                    fg="yellow",
                )
                click.secho(
                    "  Manual: nohup hapi hub --no-relay > ~/.hapi/logs/hub.log 2>&1 &",
                    fg="yellow",
                )
        except Exception as e:
            click.secho(f"  [warn] Failed to start HAPI Hub: {e}", fg="yellow")
            click.secho(
                "  Manual: nohup hapi hub --no-relay > ~/.hapi/logs/hub.log 2>&1 &",
                fg="yellow",
            )
            return

    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", ASTRBOT_CONTAINER],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.stdout.strip() != "true":
            click.secho(
                "  [skip] AstrBot container not running — configure HAPI token via Dashboard later",
                fg="yellow",
            )
            click.secho(f"  Token (save for Dashboard): {token}", fg="cyan")
            return
    except Exception:
        click.secho(
            "  [skip] Cannot reach AstrBot container — configure HAPI token via Dashboard later",
            fg="yellow",
        )
        click.secho(f"  Token (save for Dashboard): {token}", fg="cyan")
        return

    patch_script = (
        "import json\n"
        "schema_p = '/AstrBot/data/plugins/astrbot_plugin_hapi_connector/_conf_schema.json'\n"
        "with open(schema_p) as f:\n"
        "    s = json.load(f)\n"
        "s['hapi_endpoint']['default'] = 'http://host.docker.internal:3006'\n"
        f"s['access_token']['default'] = {token!r}\n"
        "with open(schema_p, 'w') as f:\n"
        "    json.dump(s, f, indent=2)\n"
        f"print('schema patched: token={token[:8]}...')\n"
        "cfg_p = '/AstrBot/data/config/astrbot_plugin_hapi_connector_config.json'\n"
        "try:\n"
        "    with open(cfg_p, encoding='utf-8-sig') as f:\n"
        "        cfg = json.load(f)\n"
        "except Exception:\n"
        "    cfg = {}\n"
        "cfg['hapi_endpoint'] = 'http://host.docker.internal:3006'\n"
        f"cfg['access_token'] = {token!r}\n"
        "with open(cfg_p, 'w', encoding='utf-8') as f:\n"
        "    json.dump(cfg, f, indent=2, ensure_ascii=False)\n"
        f"print('config patched: token={token[:8]}...')\n"
    )
    r = subprocess.run(
        ["docker", "exec", ASTRBOT_CONTAINER, "python3", "-c", patch_script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode == 0:
        click.secho(
            f"  [ok] HAPI connector configured: endpoint=host.docker.internal:3006, token injected",
            fg="green",
        )
        if r.stdout.strip():
            click.secho(f"  {r.stdout.strip()}", fg="cyan")
    else:
        click.secho(f"  [warn] Config patch failed: {r.stderr[:200]}", fg="yellow")
        click.secho(f"  Token (configure via Dashboard): {token}", fg="cyan")
        return

    click.secho("  Restarting AstrBot to apply HAPI connector config...", fg="yellow")
    subprocess.run(["docker", "restart", ASTRBOT_CONTAINER], capture_output=True)
    click.secho(
        "  [ok] AstrBot restarted — HAPI connector should connect to Hub on next boot",
        fg="green",
    )


def _check_coding_agents(non_interactive=False):
    """Check / install all coding agents + HAPI Hub for the hapi_connector.

    Installs (idempotent — skips if already present):
      1. Node.js + npm (via nvm, user-level)
      2. Codex CLI (npm @openai/codex) — HAPI spawns `codex app-server` (stdio)
      3. OpenCode (curl installer) — used by `hapi opencode`
      4. HAPI Hub (npm @twsxtd/hapi) — the :3006 service hapi_connector connects to

    Note: codex standalone install (chatgpt.com/codex/install.sh) is NOT needed.
    It only provides `codex remote-control` / `codex app-server daemon`, which
    are codex's own remote-control features — HAPI uses `codex app-server` in
    stdio mode, which the npm package supports.
    """
    click.secho("  [1/3] Node.js + npm:", fg="cyan")
    npm_bin, node_bin_dir = _ensure_node_npm()
    if npm_bin is None:
        click.secho(
            "  [skip] Cannot install coding agents without Node.js", fg="yellow"
        )
        return

    click.secho("\n  [2/3] Codex CLI + OpenCode:", fg="cyan")
    _check_codex_cli()
    _check_opencode(non_interactive=non_interactive)

    click.secho("\n  [3/3] HAPI Hub:", fg="cyan")
    _check_hapi()


def _install_skills():
    """Install CUA desktop-control skills into codex, hermes, and astrbot."""
    src_skill = SCRIPT_DIR / "skills" / "cua-desktop-control"
    if not src_skill.is_dir():
        click.secho("  [warn] cua-desktop-control skill source not found", fg="yellow")
        return
    click.secho("\n  Installing CUA skills for agents...", fg="yellow")
    # Codex
    codex_skills = Path.home() / ".codex" / "skills" / "cua-desktop-control"
    try:
        codex_skills.mkdir(parents=True, exist_ok=True)
        for f in src_skill.glob("*"):
            if f.is_file():
                dest = codex_skills / f.name
                dest.write_text(f.read_text())
        click.secho(
            "  [ok] Codex skill: ~/.codex/skills/cua-desktop-control/", fg="green"
        )
    except Exception as e:
        click.secho(f"  [warn] Codex skill failed: {e}", fg="yellow")
    # Hermes (already mounted, just verify)
    if (SCRIPT_DIR / "skills" / "cua-desktop-control").is_dir():
        click.secho("  [ok] Hermes skill: ./skills/cua-desktop-control/", fg="green")
    # AstrBot
    try:
        subprocess.run(
            [
                "docker",
                "exec",
                ASTRBOT_CONTAINER,
                "mkdir",
                "-p",
                "/AstrBot/data/skills/cua-desktop-control",
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        for f in src_skill.glob("*"):
            if f.is_file():
                subprocess.run(
                    [
                        "docker",
                        "cp",
                        str(f),
                        f"{ASTRBOT_CONTAINER}:/AstrBot/data/skills/cua-desktop-control/",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
        click.secho(
            "  [ok] AstrBot skill: /AstrBot/data/skills/cua-desktop-control/",
            fg="green",
        )
    except Exception as e:
        click.secho(f"  [warn] AstrBot skill failed: {e}", fg="yellow")


# ---------------------------------------------------------------------------
# Service summary table
# ---------------------------------------------------------------------------


def print_service_summary(bind_address: str, has_llm: bool):
    services = [
        ("AstrBot Dashboard", 6185, "/", "Web UI: platform + plugins + LLM config"),
        ("Hermes Hub", 8420, "/health", "AI Agent (Hermes CLI + REST API + SSE)"),
        ("Hermes Bridge", 8421, "/health", "Fallback forwarding (--profile bridge)"),
        ("cuactl (host)", None, None, "Desktop control relay (codex + hermes)"),
        ("Codex CLI (host)", None, None, "Coding agent (npm global)"),
    ]
    health = {}
    for name, port, path, _desc in services:
        if port is None:
            health[name] = "internal"
        else:
            code = _http_get(path or "/health", port)
            health[name] = {
                "200": click.style("UP", fg="green"),
                "err": click.style("DOWN", fg="red"),
                "000": click.style("DOWN", fg="red"),
            }.get(code, click.style(f"HTTP {code}", fg="yellow"))

    click.secho("\n" + "=" * 60, fg="cyan")
    click.secho("  Multi-Agent Service Summary", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan")
    click.echo(f"  {'Service':<24s} {'Address':<36s} {'Status':<10s}")
    click.echo(f"  {'-'*24} {'-'*36} {'-'*10}")
    for name, port, path, _desc in services:
        addr = (
            f"http://{bind_address}:{port}{path or ''}" if port else "Docker internal"
        )
        click.echo(f"  {name:<24s} {addr:<36s} {health.get(name, '?'):<16s}")

    click.echo()
    if not has_llm:
        click.secho(
            "  Hermes Agent: no LLM key — configure via: python deploy.py setup-env",
            fg="yellow",
        )
    else:
        click.secho("  Hermes Agent: LLM key configured, ready.", fg="green")
    click.echo()
    click.echo("  Commands: docker compose ps | logs -f hermes-api | down")

    # Multi-agent hints
    click.echo()
    click.secho("  Plugins (pre-configured):", fg="cyan")
    click.echo("    Hermes Connector — hub mode → hermes-api:8420 (auto-configured)")
    click.echo(
        "    HAPI Connector  — Codex / OpenCode via HAPI Hub (install + configure)"
    )
    click.echo()
    click.secho("  Skills installed:", fg="cyan")
    click.echo("    cua-desktop-control → codex, hermes, astrbot (auto-installed)")
    click.echo()
    click.secho("  cuactl:", fg="cyan")
    click.echo("    Installed at ~/.local/bin/cuactl (no sudo needed)")
    click.echo("    Hermes container also has cuactl via Dockerfile")
    click.echo()
    click.secho("  Dashboard:", fg="cyan")
    click.echo(f"    http://{bind_address}:6185")
    click.echo(f"    Password: (from .env ASTRBOT_DASHBOARD_PASSWORD)")
    click.echo()
    click.secho("  HAPI Connector (coding via Codex / OpenCode):", fg="cyan")
    click.echo(
        "    HAPI connector lets you drive Codex / OpenCode / Claude Code from chat."
    )
    click.echo("    It is independent of the Hermes connector (Computer Use).")
    click.echo()
    click.secho("    Architecture:", fg="yellow")
    click.echo("      AstrBot hapi_connector ──> HAPI Hub (:3006) ──> wraps agent CLIs")
    click.echo(
        "      HAPI Hub is an npm package (@twsxtd/hapi), NOT codex remote-control."
    )
    click.echo(
        "      It manages sessions for codex / opencode / claude-code in one place."
    )
    click.echo()
    hapi_running = False
    try:
        import urllib.request as _u

        _u.urlopen("http://127.0.0.1:3006/", timeout=2)
        hapi_running = True
    except Exception:
        pass
    if hapi_running:
        click.secho(
            "    Status: HAPI Hub running on :3006, connector auto-configured.",
            fg="green",
        )
        click.echo("      Endpoint + access_token injected into hapi_connector plugin.")
        click.echo("      Token also saved at: ~/.hapi/settings.json (cliApiToken)")
        click.echo()
        click.secho(
            "    What's left — authenticate the agents (one-time, on host):",
            fg="yellow",
        )
        click.echo("      Codex:     codex login           (writes ~/.codex/auth.json)")
        click.echo(
            "      OpenCode:  opencode  → /connect  (configure LLM provider in TUI)"
        )
        click.echo(
            "      Claude:    claude                (if installed, auto-detected by HAPI)"
        )
        click.echo()
        click.secho("    Start a coding session:", fg="yellow")
        click.echo("      From chat:    /hapi create        (interactive wizard)")
        click.echo(
            "      From host:    hapi codex          /  hapi opencode  /  hapi claude"
        )
        click.echo("      For background:  screen -S hapi → hapi codex → Ctrl+A Ctrl+D")
    else:
        click.secho("    Status: HAPI Hub NOT running on :3006.", fg="yellow")
        click.echo(
            "      deploy.py attempted to start it but failed, or HAPI not installed."
        )
        click.echo()
        click.secho("    Manual setup:", fg="yellow")
        click.echo("      1. Install:  npm install -g @twsxtd/hapi")
        click.echo(
            "      2. Start:    nohup hapi hub --no-relay > ~/.hapi/logs/hub.log 2>&1 &"
        )
        click.echo("      3. Token:    cat ~/.hapi/settings.json  (cliApiToken field)")
        click.echo("      4. Dashboard → Plugins → HAPI控制器:")
        click.echo(f"           http://{bind_address}:6185")
        click.echo("         Set hapi_endpoint = http://host.docker.internal:3006")
        click.echo("         Set access_token  = <token from step 3>")
        click.echo("      5. Restart cua-astrbot:  docker restart cua-astrbot")
    click.echo()
    click.secho("    Disable HAPI entirely (silence SSE reconnect noise):", fg="yellow")
    click.echo(
        "      Dashboard → Plugins → HAPI控制器 → toggle off, then restart cua-astrbot."
    )
    click.echo()
    click.secho("    Reboot persistence note:", fg="yellow")
    click.echo("      nohup-started HAPI Hub does NOT survive reboot. Wrap in systemd:")
    click.echo("mkdir -p ~/.config/systemd/user")
    click.echo("cat > ~/.config/systemd/user/hapi-hub.service <<'EOF'")
    click.echo("[Unit]")
    click.echo("Description=HAPI Hub")
    click.echo("After=network.target")
    click.echo("[Service]")
    click.echo("ExecStart=/path/to/hapi hub --no-relay")
    click.echo("Restart=always")
    click.echo("[Install]")
    click.echo("WantedBy=default.target")
    click.echo("EOF")
    click.echo("systemctl --user enable --now hapi-hub")
    click.echo()

    click.secho("  Manual configuration (if deploy didn't fully configure things):", fg="cyan")
    click.echo()
    click.secho("    AstrBot Dashboard:", fg="yellow")
    click.echo(f"      http://{bind_address}:6185  (password in .env ASTRBOT_DASHBOARD_PASSWORD)")
    click.echo("      → Providers: add/edit provider sources (DeepSeek, Zhipu, MiniMax, etc.)")
    click.echo("      → Plugins: enable/disable Hermes Connector / HAPI Connector")
    click.echo("      → Model: pick default model, switch models per-session")
    click.echo()
    click.secho("    Hermes CLI (inside hermes-api container):", fg="yellow")
    click.echo("      docker exec -it cua-hermes-api hermes model")
    click.echo("        # Interactive provider + model picker (writes config.yaml + .env)")
    click.echo("      docker exec -it cua-hermes-api hermes config show")
    click.echo("        # Show current config (check if provider/model are correct)")
    click.echo("      docker exec -it cua-hermes-api hermes config set model.default <model>")
    click.echo("        # Override default model without the wizard")
    click.echo("      docker exec -it cua-hermes-api hermes doctor")
    click.echo("        # Diagnose config issues, missing keys, broken providers")
    click.echo("      docker exec -it cua-hermes-api hermes chat -q 'test' --cli")
    click.echo("        # Quick test: send a single message, check if LLM responds")
    click.echo()
    click.secho("    HAPI Hub (on host, for coding via Codex/OpenCode):", fg="yellow")
    click.echo("      hapi hub --no-relay          # Start Hub (if not already running)")
    click.echo("      cat ~/.hapi/settings.json    # Read access_token for AstrBot plugin")
    click.echo("      hapi codex                   # Start a Codex coding session")
    click.echo("      hapi opencode                # Start an OpenCode coding session")
    click.echo()
    click.secho("    Restart after manual config changes:", fg="yellow")
    click.echo("      docker restart cua-astrbot    # Apply AstrBot config changes")
    click.echo("      docker restart cua-hermes-api # Apply hermes config changes")
    click.echo()


# ---------------------------------------------------------------------------
# Server deployment
# ---------------------------------------------------------------------------
def _prompt_llm_key(data: dict):
    """Prompt for LLM API key. Raises DeployAborted on Ctrl+C."""
    click.echo()
    click.secho("LLM Providers", fg="yellow")
    click.echo(_configured_provider_summary(data))
    click.echo()
    q = _q()
    if not q:
        return
    while True:
        remaining = [n for n in PROVIDER_REGISTRY if PROVIDER_REGISTRY[n]["env_key_name"] not in data or not data[PROVIDER_REGISTRY[n]["env_key_name"]].strip()]
        if not remaining:
            click.secho("  All providers configured.", fg="green")
            break
        first_round = not _resolve_providers_from_env(data)
        if not q.confirm("Add a provider?", default=first_round).ask():
            break
        provider = q.select("Select provider:", choices=_provider_choices()).ask()
        if provider is None:
            raise DeployAborted()
        if provider == "skip":
            break
        info = PROVIDER_REGISTRY.get(provider, {})
        env_key = info.get("env_key_name", "OPENAI_API_KEY")
        label = info.get("label", provider)
        key = q.password(f"Enter {label} API key:").ask()
        if key is None:
            raise DeployAborted()
        if not key:
            continue
        data[env_key] = key
        models = info.get("models", [])
        if models:
            if q.confirm(f"Default model: {models[0][1]}. Select a different one?", default=False).ask():
                model = q.select("Choose model:", choices=[
                    q.Choice(m[1], value=m[0]) for m in models
                ]).ask()
            else:
                model = models[0][0]
            if not data.get("ASTRBOT_PROVIDER_MODEL"):
                data["ASTRBOT_PROVIDER_MODEL"] = model
        click.secho(f"  [ok] {label} configured", fg="green")
        click.echo(_configured_provider_summary(data))
        click.echo()


def deploy_server(bind_address, interactive=True, reset=False):
    click.secho("\n=== Server Deployment ===", fg="cyan", bold=True)

    if reset:
        click.secho("Resetting (removing volumes)...", fg="yellow")
        subprocess.run(["docker", "compose", "down", "-v"], cwd=str(SCRIPT_DIR))
        click.secho("[OK] Reset complete.", fg="green")

    if not docker_available():
        click.secho(
            "Docker required: https://docs.docker.com/engine/install/", fg="red"
        )
        sys.exit(1)
    if not docker_compose_available():
        click.secho("Docker Compose required.", fg="red")
        sys.exit(1)
    click.secho("[OK] Docker + Compose", fg="green")

    # Ensure .env exists and has critical values
    if not (SCRIPT_DIR / ".env").exists():
        click.secho("\n.env not found — creating...", fg="yellow")
        write_env({})

    data = read_env()

    # Check and prompt for missing critical values
    needs_update = False

    # CLIENT_TOKEN — from client's config.json
    if not data.get("CLIENT_TOKEN"):
        click.echo()
        click.secho("CLIENT_TOKEN is required (from client's config.json)", fg="yellow")
        click.echo("  The client auto-generates this token on first run.")
        click.echo("  Find it at: %APPDATA%\\cua-control-plane\\config.json (Windows)")
        click.echo("             ~/.config/cua-control-plane/config.json (Linux)")
        if interactive:
            try:
                token = click.prompt(
                    "Paste CLIENT_TOKEN (or Enter to skip)",
                    default="",
                    show_default=False,
                )
            except click.exceptions.Abort:
                raise DeployAborted()
            if token:
                data["CLIENT_TOKEN"] = token
                needs_update = True

    # CUACTL_ENDPOINT — where the client is reachable
    if not data.get("CUACTL_ENDPOINT"):
        click.echo()
        click.secho("Client endpoint not configured", fg="yellow")
        click.echo("  This is the URL the server will use to reach the client.")
        if interactive:
            try:
                ep = click.prompt(
                    "Client endpoint URL (e.g. https://192.168.1.100:9111)",
                    default="",
                    show_default=False,
                )
            except click.exceptions.Abort:
                raise DeployAborted()
            if ep:
                data["CUACTL_ENDPOINT"] = ep
                needs_update = True

    # HERMES_ACCESS_TOKEN — auto-generate if missing (Hub auth)
    if not data.get("HERMES_ACCESS_TOKEN"):
        data["HERMES_ACCESS_TOKEN"] = generate_token()
        needs_update = True

    # LLM key
    has_llm = bool(_resolve_providers_from_env(data))
    if interactive:
        try:
            _prompt_llm_key(data)
            has_llm = bool(_resolve_providers_from_env(data))
            if has_llm:
                needs_update = True
        except DeployAborted:
            click.echo()
            click.secho("Deployment cancelled.", fg="yellow")
            raise
        except KeyboardInterrupt:
            click.echo()
            click.secho("Deployment cancelled.", fg="yellow")
            raise DeployAborted()
        except Exception:
            pass

    # Auto-generate astrbot dashboard password if empty
    # (empty string would cause ValueError in astrbot's validate_dashboard_password)
    if not data.get("ASTRBOT_DASHBOARD_PASSWORD", "").strip():
        pwd = generate_token()[:16] + "aA1"
        data["ASTRBOT_DASHBOARD_PASSWORD"] = pwd
        click.secho(f"  Auto-generated AstrBot dashboard password: {pwd}", fg="cyan")
        click.secho("  (save this — shown only once)", fg="yellow")
        needs_update = True

    if needs_update:
        write_env(data)

    # Pre-flight summary
    click.echo()
    click.secho("Pre-flight check:", fg="cyan")
    ep_ok = bool(data.get("CUACTL_ENDPOINT", "")) and "your-client-ip" not in data.get(
        "CUACTL_ENDPOINT", ""
    )
    items = [
        ("CLIENT_TOKEN", bool(data.get("CLIENT_TOKEN", "").strip())),
        ("HERMES_ACCESS_TOKEN", bool(data.get("HERMES_ACCESS_TOKEN", "").strip())),
        ("Client endpoint", ep_ok),
        ("LLM API key", has_llm),
    ]
    for label, ok in items:
        status = (
            click.style("[OK]", fg="green")
            if ok
            else click.style("[MISSING]", fg="yellow")
        )
        click.echo(f"  {status} {label}")

    if not has_llm or not data.get("CLIENT_TOKEN"):
        click.echo()
        click.secho("Missing critical items — cannot proceed.", fg="yellow")
        click.echo("  Configure: python deploy.py setup-env")
        click.echo("  Then:     python deploy.py server")
        return

    # Generate server/hermes/config.yaml from template (config.yaml.example).
    # config.yaml is gitignored — it's runtime data patched by _configure_hermes_env().
    # If it already exists (from a previous deploy), leave it — the patch step will update it.
    config_template = SCRIPT_DIR / "server" / "hermes" / "config.yaml.example"
    config_live = SCRIPT_DIR / "server" / "hermes" / "config.yaml"
    if not config_live.exists() and config_template.exists():
        config_live.write_text(config_template.read_text())
        click.secho(f"  [ok] Generated {config_live.name} from template", fg="green")

    click.secho(f"\n[1/8] Building images... (Ctrl+C to cancel)", fg="yellow")
    try:
        subprocess.run(["docker", "compose", "build"], cwd=str(SCRIPT_DIR), check=False)
    except KeyboardInterrupt:
        raise

    click.secho(f"\n[2/8] Starting services... (Ctrl+C to cancel)", fg="yellow")
    try:
        r = subprocess.run(["docker", "compose", "up", "-d"], cwd=str(SCRIPT_DIR))
    except KeyboardInterrupt:
        raise
    if r.returncode != 0:
        click.secho("Startup failed. Check: docker compose logs", fg="red")
        sys.exit(1)

    # [3/8] Check/install coding agents (Codex + OpenCode + HAPI) on host
    click.secho(
        f"\n[3/8] Checking coding agents (Codex / OpenCode / HAPI)...", fg="yellow"
    )
    _check_coding_agents(non_interactive=not interactive)

    # [4/8] Install cuactl on host for multi-agent access
    click.secho(f"\n[4/8] Setting up cuactl on host...", fg="yellow")
    _install_cuactl_host()

    # [5/10] Install skills for all agents
    click.secho(f"\n[5/10] Installing CUA skills for agents...", fg="yellow")
    _install_skills()

    click.secho(f"\n[6/10] Waiting for services...", fg="yellow")
    for name, port, path in [
        ("cua-astrbot", 6185, "/"),
        ("cua-hermes-api", 8420, "/health"),
    ]:
        for _ in range(6):
            if _container_running(name):
                break
            time.sleep(5)
        _wait_http_200(port, path=path, max_attempts=15, interval=4, label=name)

    # [7/10] Configure Hermes Agent .env (LLM keys for hermes CLI)
    click.secho(f"\n[7/10] Configuring Hermes Agent LLM credentials...", fg="yellow")
    _configure_hermes_env(data)

    # [8/10] Configure AstrBot LLM provider
    click.secho(f"\n[8/10] Configuring AstrBot LLM provider...", fg="yellow")
    _configure_astrbot_provider(data)

    # [9/10] Start HAPI Hub + inject token into hapi_connector
    click.secho(
        f"\n[9/10] Starting HAPI Hub and configuring HAPI connector...", fg="yellow"
    )
    _start_hapi_hub_and_configure()

    # [10/10] Restart AstrBot to pick up provider + plugin configs
    click.secho(f"\n[10/10] Restarting AstrBot to apply config...", fg="yellow")
    subprocess.run(["docker", "restart", ASTRBOT_CONTAINER], capture_output=True)
    # Wait for container to be running, then poll for HTTP 200
    for _ in range(6):
        if _container_running(ASTRBOT_CONTAINER):
            break
        time.sleep(5)
    _wait_http_200(6185, path="/", max_attempts=15, interval=4, label="AstrBot")

    print_service_summary(bind_address, has_llm)


# ---------------------------------------------------------------------------
# Client deployment (OS-aware)
# ---------------------------------------------------------------------------


def deploy_client():
    """Detect current OS and deploy the appropriate client."""
    system = platform.system()
    click.secho(f"\n=== Client Deployment ({system}) ===", fg="cyan", bold=True)

    # Ensure client/ is on Python path
    if str(SCRIPT_DIR / "client") not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR / "client"))

    # Select bind address first (same flow as server)
    click.echo()
    address = interactive_select_address()
    if address is None:
        return

    # Persist to config & show token
    try:
        import cua_control_plane.config as cfg

        c = cfg.get_config()
        c.api_host = address
        c.save()
        click.secho(f"  Bind address: {address} (saved to config)", fg="green")
        click.echo()
        click.secho("  === Client Token (copy this for .env) ===", fg="cyan")
        click.echo(f"  CLIENT_TOKEN={c.local_token}")
        click.echo()
        click.echo("  On the server, run: python deploy.py setup-env")
        click.echo("  Paste this token when prompted for CLIENT_TOKEN.")
    except Exception:
        click.secho(f"  Bind address: {address}", fg="green")

    if system == "Windows":
        _deploy_client_windows(address)
    elif system == "Linux":
        _deploy_client_linux(address)
    elif system == "Darwin":
        _deploy_client_macos(address)
    else:
        click.secho(f"Unsupported platform: {system}", fg="red")


def _deploy_client_windows(address):
    client_dir = SCRIPT_DIR / "client"
    if str(client_dir) not in sys.path:
        sys.path.insert(0, str(client_dir))
    click.echo()

    click.secho("[1/6] Installing dependencies...", fg="yellow")
    deps_ok = True
    try:
        import fastapi, uvicorn  # noqa: F401
    except ImportError:
        deps_ok = False
    if not deps_ok:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", f"{SCRIPT_DIR}[client]"],
            cwd=str(SCRIPT_DIR),
            check=False,
        )

    click.secho("[2/6] Checking cua-driver...", fg="yellow")
    ps_check = (
        '$d=join-path $env:LOCALAPPDATA "Programs\\Cua\\cua-driver\\bin\\cua-driver.exe"; '
        '$h=join-path $env:USERPROFILE ".cua-driver\\packages\\current\\cua-driver.exe"; '
        "if ((Test-Path $d) -or (Test-Path $h) -or (Get-Command cua-driver -ea 0)) { "
        '  Write-Host "  already installed" '
        "} else { "
        '  Write-Host "  downloading from GitHub..."; '
        '  $ProgressPreference="SilentlyContinue"; '
        "  $s=irm https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1; "
        '  $t="$env:TEMP\\install-cua-driver.ps1"; '
        "  [IO.File]::WriteAllText($t,$s); "
        "  & powershell -NoProfile -ExecutionPolicy Bypass -File $t -NoAutoStart; "
        "  Remove-Item $t -ErrorAction SilentlyContinue "
        "}"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_check,
        ],
        cwd=str(client_dir),
        check=False,
        timeout=120,
    )
    click.secho("  cua-driver ok", fg="green")

    click.secho("[3/6] Saving configuration...", fg="yellow")
    try:
        import cua_control_plane.config as cfg

        c2 = cfg.get_config()
        c2.api_host = address
        c2.save()
        click.secho(f"  Bind address: {address}", fg="green")
        click.echo()
        click.secho("  === CLIENT TOKEN (copy to server .env) ===", fg="cyan")
        click.secho(f"  CLIENT_TOKEN={c2.local_token}", fg="cyan")
    except Exception as e:
        click.secho(f"  Config error: {e}", fg="red")

    click.secho("[4/6] Creating startup shortcut...", fg="yellow")
    # Resolve pythonw.exe (windowless Python) next to python.exe so the
    # autostart shortcut does NOT spawn a console window on reboot.
    # Falling back to python.exe + WindowStyle=7 (minimized) if pythonw is absent.
    ps_resolve_pythonw = (
        "$pw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source; "
        "if (-not $pw) { "
        "  $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source; "
        "  if ($py) { $pw = Join-Path (Split-Path $py) 'pythonw.exe'; "
        "    if (-not (Test-Path $pw)) { $pw = $null } "
        "  } "
        "}"
    )
    ps_cmd = (
        ps_resolve_pythonw + "; "
        '$ws = New-Object -ComObject WScript.Shell; '
        '$sc = $ws.CreateShortcut([Environment]::GetFolderPath("Startup") + "\\CUA-Control-Plane.lnk"); '
        'if ($pw) { $sc.TargetPath = $pw } else { $sc.TargetPath = "python.exe"; $sc.WindowStyle = 7 }; '
        '$sc.Arguments = "-m cua_control_plane.main"; '
        f'$sc.WorkingDirectory = "{client_dir}"; '
        "$sc.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        cwd=str(client_dir),
        check=False,
        timeout=10,
    )
    click.secho("  Startup shortcut created (windowless)", fg="green")

    click.secho("[5/6] Stopping existing instance...", fg="yellow")
    ps_kill = (
        "try { $r = Invoke-WebRequest http://127.0.0.1:9111/health -TimeoutSec 2 -UseBasicParsing; "
        "if ($r.StatusCode -eq 200) { "
        '  Write-Host "  previous instance found - stopping..."; '
        '  $conns = netstat -ano | Select-String ":9111.*LISTENING"; '
        '  foreach ($c in $conns) { $p = ($c -split "\\s+" | Where-Object {$_})[-1]; Stop-Process -Id $p -Force }; '
        "  Start-Sleep 2 "
        "} } catch {}; exit 0"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_kill],
        cwd=str(client_dir),
        check=False,
        timeout=10,
    )

    click.secho("[6/6] Starting background service...", fg="yellow")
    # Use pythonw.exe if available so the live-launched process has no console
    # window. Falls back to python.exe -WindowStyle Hidden when pythonw is missing.
    ps_start = (
        "$pw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source; "
        "if (-not $pw) { $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source; "
        "  if ($py) { $cand = Join-Path (Split-Path $py) 'pythonw.exe'; "
        "    if (Test-Path $cand) { $pw = $cand } } }; "
        "if ($pw) { "
        f'  $p = Start-Process $pw -ArgumentList "-m","cua_control_plane.main" -WorkingDirectory "{client_dir}" -PassThru'
        "; if ($p) { Write-Host ('  pid=' + $p.Id) } else { Write-Host '  WARN: Start-Process returned null' } "
        "} else { "
        f'  $p = Start-Process python.exe -ArgumentList "-m","cua_control_plane.main" -WorkingDirectory "{client_dir}" -WindowStyle Hidden -PassThru'
        "; if ($p) { Write-Host ('  pid=' + $p.Id) } else { Write-Host '  WARN: Start-Process returned null' } "
        "}"
    )
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_start,
        ],
        cwd=str(client_dir),
        check=False,
        timeout=10,
    )
    click.secho(f"  Background service running on http://{address}:9111", fg="green")

    click.echo()
    click.secho("=== Installation Complete ===", fg="green", bold=True)
    click.echo(f"  API:      http://{address}:9111")
    click.echo(f"  Health:   http://{address}:9111/health")
    click.echo(f"  Test UI:  http://{address}:9111/tests")
    click.echo()
    click.secho("Tips:", fg="cyan")
    click.echo("  [UIAccess] Right-click tray icon -> Enable UIAccess")
    click.echo("             Grants admin elevation for cleaner clicks on")
    click.echo("             Chrome / VSCode (Chromium-based apps).")
    click.echo("  [VSCode / Chrome] Chromium apps may briefly grab focus")
    click.echo("             during clicks — this is a known UIA limitation.")
    click.echo("             Workaround: switch to Solo mode via tray menu")
    click.echo("             for predictable full-control behavior.")
    click.echo("  [Tray]    Right-click tray icon to switch modes:")
    click.echo("             Collaborative = non-intrusive (default)")
    click.echo("             Solo = full control with idle detection")
    click.echo("  [Restart] python -m cua_control_plane.main")
    click.echo("  [Stop]    kill the python process or reboot")


def _deploy_client_linux(address):
    if str(SCRIPT_DIR / "client") not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR / "client"))
    click.echo()

    deps_ok = True
    try:
        import fastapi  # noqa: F401
    except ImportError:
        deps_ok = False
    if not deps_ok:
        click.secho("[1/2] Installing dependencies...", fg="yellow")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", f"{SCRIPT_DIR}[client]"],
            cwd=str(SCRIPT_DIR),
            check=False,
        )

    click.secho("[2/2] Checking existing instance...", fg="yellow")
    try:
        import httpx

        r = httpx.get(f"http://127.0.0.1:9111/health", timeout=2)
        if r.status_code == 200:
            click.secho("  Already running on :9111", fg="yellow")
            return
    except Exception:
        pass

    q = _q()
    start_srv = (
        q.confirm("Start Client Control Plane now?").ask()
        if q
        else click.confirm("Start Client Control Plane now?", default=True)
    )

    if start_srv:
        click.secho(f"  Starting on http://{address}:9111 (Ctrl+C to stop)", fg="green")
        import uvicorn

        uvicorn.run(
            "cua_control_plane.api:app", host=address, port=9111, log_level="info"
        )
    else:
        click.echo(
            f"  Start manually: python -m cua_control_plane.main --host {address}"
        )


def _deploy_client_macos(address):
    click.echo()
    click.secho(f"  Client will bind to: {address}", fg="cyan")
    click.echo("  macOS: install manually —")
    click.echo('    cd client && pip install ".[client]"')
    click.echo(f"    python -m cua_control_plane.main --host {address}")
    click.echo()
    click.echo(
        "  Token stored in: ~/Library/Application Support/cua-control-plane/config.json"
    )


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def interactive_select_address():
    q = _q()
    interfaces = get_network_interfaces()

    if q and interfaces:
        kind_labels = {
            "ethernet": "eth",
            "wifi": "wifi",
            "docker": "docker",
            "vm": "vm",
            "vpn": "vpn",
            "loopback": "lo",
            "unknown": "net",
        }
        choices = [q.Separator("-- Detected interfaces --")]
        for iface in interfaces:
            kind = iface.get("kind", "unknown")
            label = (
                f"{iface['ip']:15s} ({iface['iface']}, {kind_labels.get(kind, kind)})"
            )
            choices.append(q.Choice(label, value=iface["ip"]))
        choices.append(q.Separator("-- Other --"))
        choices.append(q.Choice("0.0.0.0 (all interfaces)", value="0.0.0.0"))
        choices.append(q.Choice("127.0.0.1 (localhost only)", value="127.0.0.1"))
        choices.append(q.Choice("Custom...", value="__custom__"))
        result = q.select("Server bind address:", choices=choices).ask()
        if result is None:
            raise DeployAborted()
        if result == "__custom__":
            result = q.text(
                "IP:",
                validate=lambda x: bool(
                    re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", x)
                ),
            ).ask()
            if result is None:
                raise DeployAborted()
        return result or "0.0.0.0"

    click.echo("\nDetected interfaces:")
    if interfaces:
        for i, iface in enumerate(interfaces):
            click.echo(f"  [{i+1}] {iface['ip']}")
    click.echo("  [0] 0.0.0.0 (all)")
    try:
        choice = click.prompt("Select", type=int, default=0)
        if 1 <= choice <= len(interfaces):
            return interfaces[choice - 1]["ip"]
    except Exception:
        pass
    return "0.0.0.0"


def interactive_select_mode():
    q = _q()
    if q:
        result = q.select(
            "What to deploy?",
            choices=[
                q.Choice("Server (Docker on this machine)", value="server"),
                q.Choice(
                    f"Client ({platform.system()} — this machine)", value="client"
                ),
                q.Choice("Full (Server + Client)", value="full"),
            ],
        ).ask()
        if result is None:
            raise DeployAborted()
        return result
    click.echo(f"\nModes: [s]erver  [c]lient ({platform.system()})  [f]ull")
    return {"s": "server", "c": "client", "f": "full"}.get(
        click.prompt("Choose", type=str, default="s").lower(), "server"
    )


def interactive_deploy():
    try:
        _interactive_deploy_impl()
    except KeyboardInterrupt:
        click.echo()
        click.secho("Deployment cancelled.", fg="yellow")
        raise DeployAborted()


def _interactive_deploy_impl():
    click.secho("Remote Computer Use -- Deploy", fg="cyan", bold=True)
    click.secho("=" * 50, fg="cyan")
    mode = interactive_select_mode()
    if not mode:
        raise DeployAborted()
    if mode == "client":
        deploy_client()
        return
    # Optionally reset before deploying
    try:
        do_reset = click.confirm(
            "Reset before deploying? (deletes all Docker volumes / data)", default=False
        )
    except click.exceptions.Abort:
        raise DeployAborted()
    address = interactive_select_address()
    if not address:
        raise DeployAborted()
    try:
        deploy_server(address, reset=do_reset)
    except KeyboardInterrupt:
        click.echo()
        click.secho("Server deployment interrupted.", fg="yellow")
        raise DeployAborted()
    if mode == "full":
        click.echo()
        deploy_client()


# ---------------------------------------------------------------------------
# Click CLI
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Remote Computer Use -- Deploy Tool."""
    if ctx.invoked_subcommand is None:
        try:
            interactive_deploy()
        except (KeyboardInterrupt, DeployAborted):
            ctx.exit(130)


@cli.command()
@click.option("--bind", "-b", default="0.0.0.0", help="Server bind address")
@click.option("--yes", "-y", is_flag=True, help="Skip prompts (CI mode)")
@click.option("--reset", is_flag=True, help="Delete Docker volumes (full data wipe)")
@click.pass_context
def server(ctx, bind, yes, reset):
    """Deploy server Docker services."""
    try:
        deploy_server(bind, interactive=not yes, reset=reset)
    except (KeyboardInterrupt, DeployAborted):
        ctx.exit(130)


@cli.command()
@click.pass_context
def client(ctx):
    """Deploy client (auto-detect OS)."""
    try:
        deploy_client()
    except (KeyboardInterrupt, DeployAborted):
        ctx.exit(130)


@cli.command()
@click.option("--bind", "-b", default="0.0.0.0", help="Server bind address")
@click.option("--reset", is_flag=True, help="Delete Docker volumes (full data wipe)")
@click.pass_context
def full(ctx, bind, reset):
    """Deploy server + client."""
    try:
        deploy_server(bind, reset=reset)
        click.echo()
        deploy_client()
    except (KeyboardInterrupt, DeployAborted):
        ctx.exit(130)


@cli.command("list-addresses")
def list_addresses():
    """List detected network interfaces."""
    kind_icons = {
        "ethernet": "🖧",
        "wifi": "📶",
        "docker": "🐳",
        "vm": "📦",
        "vpn": "🔒",
        "loopback": "↩",
        "unknown": "🖧",
    }
    interfaces = get_network_interfaces()
    if interfaces:
        click.secho("Detected interfaces:", fg="cyan")
        for i in interfaces:
            icon = kind_icons.get(i.get("kind", "unknown"), "🖧")
            click.echo(f"  {icon} {i['ip']:15s} ({i['iface']}, {i['kind']})")
    else:
        click.echo("No non-loopback interfaces found.")
    click.echo("Always available: 0.0.0.0 (all), 127.0.0.1 (localhost)")


@cli.command("setup-env")
@click.pass_context
def setup_env(ctx):
    """Interactively configure .env (tokens, endpoints, LLM keys)."""
    try:
        setup_env_interactive()
    except (KeyboardInterrupt, DeployAborted):
        ctx.exit(130)


@cli.command("configure-plugins")
@click.pass_context
def configure_plugins(ctx):
    """Update hermes + HAPI plugin configs in a running AstrBot container.

    Use this to fix plugin configuration without rebuilding the Docker image.
    Requires the astrbot container to be running.
    """
    # Check container is running
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", ASTRBOT_CONTAINER],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.stdout.strip() != "true":
            click.secho(f"Container {ASTRBOT_CONTAINER} is not running.", fg="red")
            click.echo("Start it first: docker compose up -d")
            ctx.exit(1)
    except Exception:
        click.secho(f"Cannot reach container {ASTRBOT_CONTAINER}.", fg="red")
        ctx.exit(1)

    data = read_env()
    if not data.get("HERMES_ACCESS_TOKEN"):
        data["HERMES_ACCESS_TOKEN"] = generate_token()
        write_env(data)
        click.secho("Generated new HERMES_ACCESS_TOKEN", fg="green")

    # Patch hermes connector _conf_schema.json inside the container
    click.secho("Patching hermes connector config for hub mode...", fg="yellow")
    patch_script = """
import json
p = '/AstrBot/data/plugins/astrbot_plugin_hermes_connector/_conf_schema.json'
with open(p) as f:
    s = json.load(f)
s['remote_mode']['default'] = 'hub'
s['hub_endpoint']['default'] = 'http://hermes-api:8420'
s['hub_verify_ssl']['default'] = False
s['access_token']['default'] = os.environ.get('HERMES_ACCESS_TOKEN', '')
with open(p, 'w') as f:
    json.dump(s, f, indent=2)
print('hermes connector schema patched')
"""
    r = subprocess.run(
        ["docker", "exec", ASTRBOT_CONTAINER, "python3", "-c", patch_script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode == 0:
        click.secho("  [ok] Hermes connector: hub mode → hermes-api:8420", fg="green")
    else:
        click.secho(f"  [warn] {r.stderr[:200]}", fg="yellow")

    # Patch HAPI connector _conf_schema.json
    hapi_script = """
import json
p = '/AstrBot/data/plugins/astrbot_plugin_hapi_connector/_conf_schema.json'
with open(p) as f:
    s = json.load(f)
s['hapi_endpoint']['default'] = 'http://host.docker.internal:3006'
with open(p, 'w') as f:
    json.dump(s, f, indent=2)
print('hapi connector schema patched')
"""
    r = subprocess.run(
        ["docker", "exec", ASTRBOT_CONTAINER, "python3", "-c", hapi_script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode == 0:
        click.secho("  [ok] HAPI connector: host.docker.internal:3006", fg="green")
    else:
        click.secho(f"  [warn] {r.stderr[:200]}", fg="yellow")

    # Configure AstrBot LLM provider
    click.secho("Configuring AstrBot LLM provider...", fg="yellow")
    _configure_astrbot_provider(data)

    # Restart to apply
    click.secho("Restarting AstrBot to apply config...", fg="yellow")
    subprocess.run(["docker", "restart", ASTRBOT_CONTAINER], capture_output=True)
    click.secho("[ok] AstrBot restarted — plugins + provider configured", fg="green")
    click.echo()
    click.echo(
        "Verify: open http://localhost:6185 → Plugins → Hermes控制器 / HAPI控制器"
    )


if __name__ == "__main__":
    cli()
