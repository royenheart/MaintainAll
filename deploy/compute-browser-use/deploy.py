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
import time
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
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, timeout=5)
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
        interfaces.append({
            "name": iface,
            "ip": ip,
            "iface": iface,
            "kind": _kind(iface),
        })

    # Source 2: hostname addrinfo (catch any IPs `ip addr` missed)
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip in seen or ip.startswith("127."):
                continue
            seen.add(ip)
            iface = ip_to_iface.get(ip, hostname)
            interfaces.append({
                "name": hostname,
                "ip": ip,
                "iface": iface,
                "kind": _kind(iface) if iface in ip_to_iface else "unknown",
            })
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
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True, timeout=5)
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
        return subprocess.run(["docker", "info"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False

def docker_compose_available():
    try:
        return subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False

def _http_get(path, port):
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"http://127.0.0.1:{port}{path}"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return "err"


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
        f"CLIENT_TOKEN={data.get('CLIENT_TOKEN', '')}",
        f"BRIDGE_AUTH_TOKEN={data.get('BRIDGE_AUTH_TOKEN', '')}",
        "",
        "# --- Client Connection ---",
        f"CUACTL_ENDPOINT={data.get('CUACTL_ENDPOINT', '')}",
        "CUACTL_TOKEN=${CLIENT_TOKEN}",
        "",
        "# --- LLM Provider ---",
        "# Hermes Agent needs an LLM key to process messages.",
        "# Supported: Anthropic, OpenAI, OpenRouter, Google Gemini, DeepSeek,",
        "#            xAI Grok, Qwen, Ollama, LM Studio, Bedrock, and 25+ more.",
        "# Docs: https://github.com/NousResearch/hermes-agent",
        f"ANTHROPIC_API_KEY={data.get('ANTHROPIC_API_KEY', '')}",
        f"OPENAI_API_KEY={data.get('OPENAI_API_KEY', '')}",
        f"OPENAI_BASE_URL={data.get('OPENAI_BASE_URL', '')}",
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

    for key in ("CLIENT_TOKEN", "BRIDGE_AUTH_TOKEN"):
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
        new_ep = click.prompt("Client Control Plane endpoint", default=current_ep or "https://your-client-ip:9111")
        data["CUACTL_ENDPOINT"] = new_ep
    click.echo()

    click.secho("LLM Provider (press Enter / select Skip to leave empty)", fg="yellow")
    if q:
        provider = q.select("Select provider:", choices=[
            q.Separator("— Cloud —"),
            q.Choice("Anthropic (Claude)", value="anthropic"),
            q.Choice("OpenAI (GPT)", value="openai"),
            q.Choice("Google Gemini", value="gemini"),
            q.Choice("DeepSeek", value="deepseek"),
            q.Choice("OpenRouter", value="openrouter"),
            q.Separator("— Local —"),
            q.Choice("Ollama", value="ollama"),
            q.Choice("LM Studio", value="lmstudio"),
            q.Separator(""),
            q.Choice("Skip (configure later)", value="skip"),
        ]).ask()
        if provider and provider != "skip":
            key = q.password(f"Enter {provider.upper()} API key:").ask()
            if key:
                if provider == "anthropic":
                    data["ANTHROPIC_API_KEY"] = key
                elif provider in ("openai", "openrouter", "deepseek"):
                    data["OPENAI_API_KEY"] = key
                    if provider == "openrouter":
                        base = q.text("Base URL:", default="https://openrouter.ai/api/v1").ask()
                        if base:
                            data["OPENAI_BASE_URL"] = base
                    elif provider == "deepseek":
                        base = q.text("Base URL:", default="https://api.deepseek.com/v1").ask()
                        if base:
                            data["OPENAI_BASE_URL"] = base
                elif provider == "gemini":
                    data["OPENAI_API_KEY"] = key
                elif provider in ("ollama", "lmstudio"):
                    default_base = "http://localhost:11434/v1" if provider == "ollama" else "http://localhost:1234/v1"
                    data["OPENAI_API_KEY"] = "ollama" if provider == "ollama" else "lmstudio"
                    base = q.text("Base URL:", default=default_base).ask()
                    if base:
                        data["OPENAI_BASE_URL"] = base
                click.secho(f"  [ok] {provider.upper()} configured", fg="green")
            else:
                click.secho("  [skip] No key entered — set later in .env", fg="yellow")
    else:
        if click.confirm("Configure LLM key now?", default=False):
            key = click.prompt("API Key (or Enter to skip)", default="", show_default=False)
            if key:
                provider = click.prompt("Provider (anthropic/openai/gemini/deepseek)", default="anthropic")
                if provider == "anthropic":
                    data["ANTHROPIC_API_KEY"] = key
                else:
                    data["OPENAI_API_KEY"] = key
    click.echo()

    if not data.get("ASTRBOT_DASHBOARD_PASSWORD"):
        if q:
            pwd = q.password("AstrBot dashboard password (empty = auto-generate):").ask()
            data["ASTRBOT_DASHBOARD_PASSWORD"] = pwd or ""
        else:
            data["ASTRBOT_DASHBOARD_PASSWORD"] = click.prompt("AstrBot dashboard password", default="", show_default=False)

    write_env(data)
    if not mode and not address:  # not reached normally, but safe
        pass
    click.secho("\n.env saved.", fg="green")

    if not data.get("ANTHROPIC_API_KEY") and not data.get("OPENAI_API_KEY"):
        click.echo()
        click.secho("LLM key not configured — set later via: python deploy.py setup-env", fg="yellow")


# ---------------------------------------------------------------------------
# Service summary table
# ---------------------------------------------------------------------------

def print_service_summary(bind_address: str, has_llm: bool):
    services = [
        ("AstrBot Dashboard",  6185, "/",         "Web UI for platform & plugin management"),
        ("Hermes API",         8420, "/health",   "AI Agent HTTP wrapper (headless Hermes)"),
        ("Hermes Bridge",      8421, "/health",   "Message forwarding: AstrBot -> Hermes"),
        ("CUA Relay (cuactl)", None,  None,       "CLI bridge: Hermes -> Client (internal only)"),
    ]
    health = {}
    for name, port, path, _desc in services:
        if port is None:
            health[name] = "internal"
        else:
            code = _http_get(path or "/health", port)
            health[name] = {"200": click.style("UP", fg="green"), "err": click.style("DOWN", fg="red"), "000": click.style("DOWN", fg="red")}.get(code, click.style(f"HTTP {code}", fg="yellow"))

    click.secho("\n" + "=" * 60, fg="cyan")
    click.secho("  Service Summary", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan")
    click.echo(f"  {'Service':<24s} {'Address':<36s} {'Status':<10s}")
    click.echo(f"  {'-'*24} {'-'*36} {'-'*10}")
    for name, port, path, _desc in services:
        addr = f"http://{bind_address}:{port}{path or ''}" if port else "Docker internal"
        click.echo(f"  {name:<24s} {addr:<36s} {health.get(name, '?'):<16s}")

    click.echo()
    if not has_llm:
        click.secho("  Hermes Agent: no LLM key — configure via: python deploy.py setup-env", fg="yellow")
    else:
        click.secho("  Hermes Agent: LLM key configured, ready.", fg="green")
    click.echo()
    click.echo("  Commands: docker compose ps | logs -f hermes-api | down")


# ---------------------------------------------------------------------------
# Server deployment
# ---------------------------------------------------------------------------
def _prompt_llm_key(data: dict):
    """Prompt for LLM API key. Raises DeployAborted on Ctrl+C."""
    click.echo()
    click.secho("LLM API key not configured", fg="yellow")
    click.echo("  Hermes Agent needs this to process chat messages.")
    click.echo("  Supported: Anthropic, OpenAI, OpenRouter, Google Gemini, DeepSeek, ...")
    q = _q()
    if not q:
        return
    provider = q.select("Add an API key now?", choices=[
        q.Choice("Anthropic (Claude)", value="anthropic"),
        q.Choice("OpenAI (GPT)", value="openai"),
        q.Choice("Google Gemini", value="gemini"),
        q.Choice("DeepSeek", value="deepseek"),
        q.Choice("OpenRouter", value="openrouter"),
        q.Choice("Skip (configure later)", value="skip"),
    ]).ask()
    if provider is None:
        raise DeployAborted()
    if provider == "skip":
        return
    key = q.password(f"Enter {provider.upper()} API key:").ask()
    if key is None:
        raise DeployAborted()
    if not key:
        return
    if provider == "anthropic":
        data["ANTHROPIC_API_KEY"] = key
    elif provider in ("openai", "openrouter", "deepseek"):
        data["OPENAI_API_KEY"] = key
        if provider == "openrouter":
            base = q.text("Base URL:", default="https://openrouter.ai/api/v1").ask()
            if base:
                data["OPENAI_BASE_URL"] = base
        elif provider == "deepseek":
            base = q.text("Base URL:", default="https://api.deepseek.com/v1").ask()
            if base:
                data["OPENAI_BASE_URL"] = base
    elif provider == "gemini":
        data["OPENAI_API_KEY"] = key


def deploy_server(bind_address, interactive=True):
    click.secho("\n=== Server Deployment ===", fg="cyan", bold=True)

    if not docker_available():
        click.secho("Docker required: https://docs.docker.com/engine/install/", fg="red")
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
                token = click.prompt("Paste CLIENT_TOKEN (or Enter to skip)", default="", show_default=False)
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
                ep = click.prompt("Client endpoint URL (e.g. https://192.168.1.100:9111)", default="", show_default=False)
            except click.exceptions.Abort:
                raise DeployAborted()
            if ep:
                data["CUACTL_ENDPOINT"] = ep
                needs_update = True

    # BRIDGE_AUTH_TOKEN — will be generated by docker-compose or setup-env

    # LLM key
    has_llm = bool(data.get("ANTHROPIC_API_KEY") or data.get("OPENAI_API_KEY"))
    if not has_llm and interactive:
        try:
            _prompt_llm_key(data)
            has_llm = bool(data.get("ANTHROPIC_API_KEY") or data.get("OPENAI_API_KEY"))
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
            pass  # questionary not available, skip

    if needs_update:
        write_env(data)

    # Pre-flight summary
    click.echo()
    click.secho("Pre-flight check:", fg="cyan")
    ep_ok = bool(data.get("CUACTL_ENDPOINT", "")) and "your-client-ip" not in data.get("CUACTL_ENDPOINT", "")
    items = [
        ("CLIENT_TOKEN", bool(data.get("CLIENT_TOKEN", "").strip())),
        ("Client endpoint", ep_ok),
        ("BRIDGE_AUTH_TOKEN", bool(data.get("BRIDGE_AUTH_TOKEN", "").strip())),
        ("LLM API key", has_llm),
    ]
    for label, ok in items:
        status = click.style("[OK]", fg="green") if ok else click.style("[MISSING]", fg="yellow")
        click.echo(f"  {status} {label}")

    if not has_llm or not data.get("CLIENT_TOKEN"):
        click.echo()
        click.secho("Missing critical items — cannot proceed.", fg="yellow")
        click.echo("  Configure: python deploy.py setup-env")
        click.echo("  Then:     python deploy.py server")
        return  # Always stop if CLIENT_TOKEN or LLM key missing, regardless of mode

    click.secho(f"\n[1/3] Building images... (Ctrl+C to cancel)", fg="yellow")
    try:
        subprocess.run(["docker", "compose", "build"], cwd=str(SCRIPT_DIR), check=False)
    except KeyboardInterrupt:
        raise

    click.secho(f"\n[2/3] Starting services... (Ctrl+C to cancel)", fg="yellow")
    try:
        r = subprocess.run(["docker", "compose", "up", "-d"], cwd=str(SCRIPT_DIR))
    except KeyboardInterrupt:
        raise
    if r.returncode != 0:
        click.secho("Startup failed. Check: docker compose logs", fg="red")
        sys.exit(1)

    click.secho(f"\n[3/3] Waiting for services...", fg="yellow")
    time.sleep(3)
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
            cwd=str(SCRIPT_DIR), check=False,
        )

    click.secho("[2/6] Checking cua-driver...", fg="yellow")
    ps_check = (
        '$d=join-path $env:LOCALAPPDATA "Programs\\Cua\\cua-driver\\bin\\cua-driver.exe"; '
        '$h=join-path $env:USERPROFILE ".cua-driver\\packages\\current\\cua-driver.exe"; '
        'if ((Test-Path $d) -or (Test-Path $h) -or (Get-Command cua-driver -ea 0)) { '
        '  Write-Host "  already installed" '
        '} else { '
        '  Write-Host "  downloading from GitHub..."; '
        '  $ProgressPreference="SilentlyContinue"; '
        '  $s=irm https://raw.githubusercontent.com/trycua/cua/main/libs/cua-driver/scripts/install.ps1; '
        '  $t="$env:TEMP\\install-cua-driver.ps1"; '
        '  [IO.File]::WriteAllText($t,$s); '
        '  & powershell -NoProfile -ExecutionPolicy Bypass -File $t -NoAutoStart; '
        '  Remove-Item $t -ErrorAction SilentlyContinue '
        '}'
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_check],
                   cwd=str(client_dir), check=False, timeout=120)
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
    ps_cmd = (
        '$ws = New-Object -ComObject WScript.Shell; '
        '$sc = $ws.CreateShortcut([Environment]::GetFolderPath("Startup") + "\\CUA-Control-Plane.lnk"); '
        '$sc.TargetPath = "python.exe"; '
        '$sc.Arguments = "-m cua_control_plane.main"; '
        f'$sc.WorkingDirectory = "{client_dir}"; '
        '$sc.Save()'
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                   cwd=str(client_dir), check=False, timeout=10)
    click.secho("  Startup shortcut created", fg="green")

    click.secho("[5/6] Stopping existing instance...", fg="yellow")
    ps_kill = (
        'try { $r = Invoke-WebRequest http://127.0.0.1:9111/health -TimeoutSec 2 -UseBasicParsing; '
        'if ($r.StatusCode -eq 200) { '
        '  Write-Host "  previous instance found - stopping..."; '
        '  $conns = netstat -ano | Select-String ":9111.*LISTENING"; '
        '  foreach ($c in $conns) { $p = ($c -split "\\s+" | Where-Object {$_})[-1]; Stop-Process -Id $p -Force }; '
        '  Start-Sleep 2 '
        '} } catch {}; exit 0'
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_kill],
                   cwd=str(client_dir), check=False, timeout=10)

    click.secho("[6/6] Starting background service...", fg="yellow")
    ps_start = (
        'Start-Process python -ArgumentList "-m","cua_control_plane.main" '
        f'-WorkingDirectory "{client_dir}" -WindowStyle Hidden'
    )
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_start],
                   cwd=str(client_dir), check=False, timeout=10)
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
            cwd=str(SCRIPT_DIR), check=False,
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
    start_srv = q.confirm("Start Client Control Plane now?").ask() if q else click.confirm("Start Client Control Plane now?", default=True)

    if start_srv:
        click.secho(f"  Starting on http://{address}:9111 (Ctrl+C to stop)", fg="green")
        import uvicorn
        uvicorn.run("cua_control_plane.api:app", host=address, port=9111, log_level="info")
    else:
        click.echo(f"  Start manually: python -m cua_control_plane.main --host {address}")

def _deploy_client_macos(address):
    click.echo()
    click.secho(f"  Client will bind to: {address}", fg="cyan")
    click.echo("  macOS: install manually —")
    click.echo('    cd client && pip install ".[client]"')
    click.echo(f"    python -m cua_control_plane.main --host {address}")
    click.echo()
    click.echo("  Token stored in: ~/Library/Application Support/cua-control-plane/config.json")


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------

def interactive_select_address():
    q = _q()
    interfaces = get_network_interfaces()

    if q and interfaces:
        kind_labels = {"ethernet": "eth", "wifi": "wifi", "docker": "docker", "vm": "vm", "vpn": "vpn", "loopback": "lo", "unknown": "net"}
        choices = [q.Separator("-- Detected interfaces --")]
        for iface in interfaces:
            kind = iface.get("kind", "unknown")
            label = f"{iface['ip']:15s} ({iface['iface']}, {kind_labels.get(kind, kind)})"
            choices.append(q.Choice(label, value=iface["ip"]))
        choices.append(q.Separator("-- Other --"))
        choices.append(q.Choice("0.0.0.0 (all interfaces)", value="0.0.0.0"))
        choices.append(q.Choice("127.0.0.1 (localhost only)", value="127.0.0.1"))
        choices.append(q.Choice("Custom...", value="__custom__"))
        result = q.select("Server bind address:", choices=choices).ask()
        if result is None:
            raise DeployAborted()
        if result == "__custom__":
            result = q.text("IP:", validate=lambda x: bool(re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", x))).ask()
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
        result = q.select("What to deploy?", choices=[
            q.Choice("Server (Docker on this machine)", value="server"),
            q.Choice(f"Client ({platform.system()} — this machine)", value="client"),
            q.Choice("Full (Server + Client)", value="full"),
        ]).ask()
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
    address = interactive_select_address()
    if not address:
        raise DeployAborted()
    try:
        deploy_server(address)
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
@click.pass_context
def server(ctx, bind, yes):
    """Deploy server Docker services."""
    try:
        deploy_server(bind, interactive=not yes)
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
@click.pass_context
def full(ctx, bind):
    """Deploy server + client."""
    try:
        deploy_server(bind)
        click.echo()
        deploy_client()
    except (KeyboardInterrupt, DeployAborted):
        ctx.exit(130)


@cli.command("list-addresses")
def list_addresses():
    """List detected network interfaces."""
    kind_icons = {"ethernet": "🖧", "wifi": "📶", "docker": "🐳", "vm": "📦", "vpn": "🔒", "loopback": "↩", "unknown": "🖧"}
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


if __name__ == "__main__":
    cli()
