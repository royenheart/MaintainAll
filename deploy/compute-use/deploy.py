#!/usr/bin/env python3
"""Remote Computer Use — deployment helper (client + relay).

This stack is the computer-use capability only:

  client/   the Client Control Plane that runs on the machine being
            controlled (Windows primary; Linux/macOS supported)
  relay     a thin HTTP microservice (server/cua-relay) that translates
            /cuactl/<command> calls into HTTPS + token calls against the
            client's control plane

It holds no LLM credentials and no agent configuration. Any agent that
wants to drive the desktop attaches to the relay's docker network, or
uses the `cuactl` CLI this script installs on the host.

Commands:
    setup-env    Generate .env (client token, endpoint)
    server       Build and start the relay container
    client       Deploy the control plane on this machine
    status       Read-only health check
    down         Stop the relay (volumes kept)
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
import urllib.request
from pathlib import Path

import click

SCRIPT_DIR = Path(__file__).resolve().parent


class DeployAborted(Exception):
    """Raised when user cancels deployment (Ctrl+C)."""

    pass


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


def _q():
    try:
        import questionary

        return questionary
    except ImportError:
        return None


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


def generate_token():
    return secrets.token_hex(32)


def _install_cuactl_host():
    """Install a cuactl CLI wrapper on the host for host-side agents."""
    relay_script = SCRIPT_DIR / "server" / "cua-relay" / "relay_server.py"
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)
    cuactl_dest = local_bin / "cuactl"
    if cuactl_dest.exists():
        click.secho(f"  cuactl already at {cuactl_dest}", fg="green")
        return
    click.secho(
        "\n  Installing cuactl on host (for host-side agents)...", fg="yellow"
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

    click.secho("[4/6] Creating startup task (background, survives reboot)...", fg="yellow")
    # Resolve pythonw.exe (windowless Python) next to python.exe so the
    # autostart does NOT spawn a console window on reboot.
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
    # Register a Scheduled Task that runs at user logon, fully in the background.
    # This is more robust than a Startup-folder .lnk: the task survives terminal
    # closure (no console attached) and can be managed via Task Scheduler UI.
    # We ALSO keep the Startup .lnk as a fallback in case Task Scheduler is disabled.
    task_name = "CUA-Control-Plane"
    ps_register_task = (
        ps_resolve_pythonw + "; "
        f"$taskName = '{task_name}'; "
        # Build the command to launch
        "$exe = if ($pw) { $pw } else { 'python.exe' }; "
        "$arg = '-m cua_control_plane.main'; "
        # Delete existing task if present (idempotent re-deploy)
        f"Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue; "
        # Action: run pythonw/python with -m cua_control_plane.main
        "$action = New-ScheduledTaskAction -Execute $exe -Argument $arg "
        f"-WorkingDirectory '{client_dir}'; "
        # Trigger: at user logon
        "$trigger = New-ScheduledTaskTrigger -AtLogOn; "
        # Settings: allow start on battery, don't stop on idle, restart on failure
        "$settings = New-ScheduledTaskSettingsSet "
        "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1); "
        # Principal: run as current user, no elevation (tray icon needs user session)
        "$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME "
        "-LogonType Interactive -RunLevel Limited; "
        # Register (may fail with Access Denied under restricted group policy)
        "try { "
        "Register-ScheduledTask -TaskName $taskName -Action $action "
        "-Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null; "
        "Write-Host '  Scheduled task registered (logon, background)' "
        "} catch { "
        "Write-Host ('  WARN: Task Scheduler registration failed: ' + $_.Exception.Message); "
        "Write-Host '  Falling back to Startup-folder shortcut only' "
        "}"
    )
    task_result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_register_task],
        cwd=str(client_dir),
        check=False,
        timeout=15,
        capture_output=True, text=True,
    )
    if task_result.stdout:
        for line in task_result.stdout.strip().splitlines():
            click.echo(f"  {line}")
    if "WARN" in (task_result.stdout or ""):
        click.secho("  (Startup shortcut will still handle autostart)", fg="cyan")
    # Also keep the Startup .lnk as a fallback (in case Task Scheduler is disabled).
    # WindowStyle=7 (minimized) is set on BOTH branches for defense-in-depth:
    # - pythonw.exe: no console anyway, but WindowStyle=7 is harmless
    # - python.exe fallback: minimized so any flash is less visible
    ps_cmd = (
        ps_resolve_pythonw + "; "
        '$ws = New-Object -ComObject WScript.Shell; '
        '$sc = $ws.CreateShortcut([Environment]::GetFolderPath("Startup") + "\\CUA-Control-Plane.lnk"); '
        'if ($pw) { $sc.TargetPath = $pw; $sc.WindowStyle = 7 } '
        'else { $sc.TargetPath = "python.exe"; $sc.WindowStyle = 7 }; '
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
    click.secho("  Startup task + fallback shortcut created (windowless)", fg="green")

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
        f'  $p = Start-Process $pw -ArgumentList "-m","cua_control_plane.main" -WorkingDirectory "{client_dir}" -WindowStyle Hidden -PassThru'
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
    click.echo(f"  Settings: http://{address}:9111/settings")
    click.echo()
    click.secho("Tips:", fg="cyan")
    click.echo(f"  [Settings] Open http://{address}:9111/settings in browser")
    click.echo("             Fine-grained control: per-operation toggles,")
    click.echo("             region restriction (drag on canvas), app allowlist.")
    click.echo("             Or right-click tray icon -> 'Open Settings...'")
    if address not in ("127.0.0.1", "localhost"):
        click.secho(f"  Note: client binds to {address}, not 127.0.0.1.", fg="yellow")
        click.echo("        Local browser/tray must use the address above to reach the UI.")
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


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------


def write_env(data: dict) -> None:
    """Write .env.

    Only client and relay variables live here. This stack holds no LLM
    credentials and no AstrBot secrets — those belong to their own stacks.
    """
    env_path = SCRIPT_DIR / ".env"
    lines = [
        "# Remote Computer Use — Environment (generated by deploy.py)",
        "",
        "# --- Authentication ---",
        f"CLIENT_TOKEN={data.get('CLIENT_TOKEN', '')}",
        "",
        "# --- Client Control Plane (the machine being controlled) ---",
        f"CUACTL_ENDPOINT={data.get('CUACTL_ENDPOINT', '')}",
        f"CUACTL_TOKEN={data.get('CUACTL_TOKEN', '${CLIENT_TOKEN}')}",
        "",
        "# --- Relay container ---",
        f"CUACTL_CONTAINER={data.get('CUACTL_CONTAINER', 'cuactl')}",
        f"CUA_NETWORK={data.get('CUA_NETWORK', 'cua-net')}",
        f"TZ={data.get('TZ', 'Asia/Shanghai')}",
        "",
    ]
    env_path.write_text("\n".join(lines) + "\n")


def setup_env_interactive():
    try:
        _setup_env_impl()
    except KeyboardInterrupt:
        click.echo()
        click.secho("Configuration cancelled.", fg="yellow")
        raise DeployAborted()


PLACEHOLDER_ENDPOINT = "https://REPLACE-ME:9111"


def _setup_env_impl():
    q = _q()
    click.secho("\n=== Configure Environment (.env) ===", fg="cyan", bold=True)
    click.echo()

    data = read_env()

    if not data.get("CLIENT_TOKEN"):
        data["CLIENT_TOKEN"] = generate_token()
        click.secho("  [generated] CLIENT_TOKEN", fg="green")
    else:
        click.echo("  [existing]  CLIENT_TOKEN")

    click.echo()
    current = data.get("CUACTL_ENDPOINT", "")

    if q:
        choices = [
            q.Choice("Set later (placeholder endpoint)", value="__later__"),
            q.Separator("-- Detected interfaces --"),
        ]
        for iface in get_network_interfaces():
            choices.append(
                q.Choice(
                    f"https://{iface['ip']}:9111 ({iface['iface']})",
                    value=f"https://{iface['ip']}:9111",
                )
            )
        choices.append(q.Separator("-- Other --"))
        choices.append(q.Choice("Custom...", value="__custom__"))

        picked = q.select("Client Control Plane endpoint:", choices=choices).ask()
        if picked is None:
            raise DeployAborted()

        if picked == "__later__":
            data["CUACTL_ENDPOINT"] = current or PLACEHOLDER_ENDPOINT
        elif picked == "__custom__":
            typed = q.text("Endpoint (https://host:9111):").ask()
            if typed is None:
                raise DeployAborted()
            data["CUACTL_ENDPOINT"] = typed.strip()
        else:
            data["CUACTL_ENDPOINT"] = picked
    else:
        typed = click.prompt(
            "Client Control Plane endpoint",
            default=current or PLACEHOLDER_ENDPOINT,
        )
        data["CUACTL_ENDPOINT"] = typed.strip()

    data.setdefault("CUACTL_TOKEN", "${CLIENT_TOKEN}")
    data.setdefault("CUACTL_CONTAINER", "cuactl")
    data.setdefault("CUA_NETWORK", "cua-net")
    data.setdefault("TZ", "Asia/Shanghai")

    write_env(data)
    click.secho("\n.env saved.", fg="green")

    if data["CUACTL_ENDPOINT"] == PLACEHOLDER_ENDPOINT:
        click.secho(
            "  Endpoint is a placeholder — set the real one once the client "
            "is running.",
            fg="yellow",
        )
    click.echo()
    click.echo("  Point the relay at the client by editing CUACTL_ENDPOINT,")
    click.echo("  or re-run: ./deploy.py setup-env")


# ---------------------------------------------------------------------------
# Server (relay container)
# ---------------------------------------------------------------------------


def deploy_server(bind_address: str = "0.0.0.0", interactive: bool = True):
    """Build and start the cuactl relay container, then install the host CLI."""
    click.secho("\n=== Relay Deployment ===", fg="cyan", bold=True)

    if not docker_available() or not docker_compose_available():
        click.secho("Docker and Docker Compose are required.", fg="red")
        sys.exit(1)

    if not (SCRIPT_DIR / ".env").exists():
        click.secho("\n.env not found — creating...", fg="yellow")
        if interactive:
            setup_env_interactive()
        else:
            write_env({"CLIENT_TOKEN": generate_token()})

    data = read_env()
    if not data.get("CLIENT_TOKEN"):
        data["CLIENT_TOKEN"] = generate_token()
        write_env(data)
        click.secho("  [generated] CLIENT_TOKEN", fg="green")

    if not data.get("CUACTL_ENDPOINT"):
        click.secho(
            "  [warn] CUACTL_ENDPOINT is empty — the relay will start but "
            "cannot reach any client.",
            fg="yellow",
        )

    click.secho("\n[1/3] Building relay image...", fg="yellow")
    subprocess.run(["docker", "compose", "build"], cwd=str(SCRIPT_DIR), check=False)

    click.secho("[2/3] Starting relay...", fg="yellow")
    r = subprocess.run(["docker", "compose", "up", "-d"], cwd=str(SCRIPT_DIR))
    if r.returncode != 0:
        click.secho("Startup failed. Check: docker compose logs", fg="red")
        sys.exit(1)

    click.secho("[3/3] Installing cuactl CLI on host...", fg="yellow")
    _install_cuactl_host()

    print_service_summary(data)


def print_service_summary(data: dict):
    click.echo()
    click.secho("=== Compute Use ===", fg="cyan", bold=True)
    click.echo(f"  Relay container : {data.get('CUACTL_CONTAINER', 'cuactl')} (:8000, internal)")
    click.echo(f"  Network         : {data.get('CUA_NETWORK', 'cua-net')}")
    click.echo(f"  Client endpoint : {data.get('CUACTL_ENDPOINT') or '(unset)'}")
    click.echo()
    click.echo("  The relay publishes no host port by design: it is reachable")
    click.echo("  only from containers attached to the network above.")
    click.echo("  For host-side use, call the CLI installed by this script:")
    click.echo("    cuactl list-apps")
    click.echo()


# ---------------------------------------------------------------------------
# Status (read-only)
# ---------------------------------------------------------------------------


def _status_cmd():
    """Read-only health check. Never writes anything."""
    import json as _json

    data = read_env()
    name = data.get("CUACTL_CONTAINER", "cuactl")
    endpoint = data.get("CUACTL_ENDPOINT", "")

    def ok(flag):
        return (
            click.style("[OK]", fg="green")
            if flag
            else click.style("[--]", fg="yellow")
        )

    running = False
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=10,
        )
        running = r.stdout.strip() == "true"
    except Exception:
        pass

    relay_health = None
    if running:
        try:
            r = subprocess.run(
                ["docker", "exec", name, "python3", "-c",
                 "import urllib.request;print(urllib.request.urlopen("
                 "'http://127.0.0.1:8000/health',timeout=3).read().decode())"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                relay_health = r.stdout.strip()
        except Exception:
            pass

    click.secho("Compute Use", bold=True)
    click.echo(f"  {ok(running)} relay container `{name}` running")
    if relay_health:
        click.echo(f"       {relay_health}")

    if not endpoint:
        click.echo()
        click.secho("  Client endpoint not configured.", fg="yellow")
        return

    reachable = False
    detail = ""
    try:
        with urllib.request.urlopen(f"{endpoint.rstrip('/')}/health", timeout=5) as resp:
            reachable = resp.status == 200
            detail = resp.read().decode()[:200]
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"

    click.echo(f"  {ok(reachable)} client reachable at {endpoint}")
    if detail:
        click.echo(f"       {detail}")

    if not reachable:
        click.echo()
        click.secho(
            "  The client PC is offline, or its control plane is not running.",
            fg="yellow",
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Remote Computer Use — client + relay deployment."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command("setup-env")
def setup_env_cmd():
    """Generate .env interactively."""
    setup_env_interactive()


@cli.command("server")
@click.option("--bind", "-b", default="0.0.0.0", help="Unused; kept for parity")
@click.option("--yes", "-y", is_flag=True, help="Skip prompts (CI mode)")
@click.pass_context
def server_cmd(ctx, bind, yes):
    """Build and start the relay container."""
    try:
        deploy_server(bind, interactive=not yes)
    except (KeyboardInterrupt, DeployAborted):
        ctx.exit(130)


@cli.command("client")
@click.pass_context
def client_cmd(ctx):
    """Deploy the control plane on this machine."""
    try:
        deploy_client()
    except (KeyboardInterrupt, DeployAborted):
        ctx.exit(130)


@cli.command("status")
def status_cmd():
    """Read-only health check — writes nothing."""
    _status_cmd()


@cli.command("down")
def down_cmd():
    """Stop the relay container (volumes kept)."""
    subprocess.run(["docker", "compose", "down"], cwd=str(SCRIPT_DIR))


if __name__ == "__main__":
    cli()
