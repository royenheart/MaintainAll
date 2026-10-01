"""deploy/proxy --ipv6 is opt-in and does not drop the IPv4 listeners."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "proxy" / "scripts" / "deploy.sh"


def render(*args: str) -> str:
    proc = subprocess.run(
        [str(DEPLOY), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def test_default_is_ipv4_only():
    out = render("--sni", "example.com", "--ip", "203.0.113.10")
    assert '"listen": "0.0.0.0"' in out
    assert '"listen": "::"' not in out
    assert '"listen": "127.0.0.1"' in out
    assert "listen 443 ssl;" in out
    assert "[::]" not in out
    assert "Listen mode: IPv4 only" in out


def test_ipv6_flag_adds_dual_stack_listeners():
    out = render("--ipv6", "--tls-port", "8443", "--sni", "example.com")
    assert '"listen": "::"' in out
    assert '"listen": "0.0.0.0"' not in out
    assert '"listen": "127.0.0.1"' in out
    assert "listen 8443 ssl;" in out
    assert "listen [::]:8443 ssl;" in out
    assert "ipv6only" not in out
    assert "Listen mode: IPv4+IPv6" in out
