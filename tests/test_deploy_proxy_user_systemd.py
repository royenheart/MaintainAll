"""deploy/proxy can install sing-box as a lingering user systemd service."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROXY = ROOT / "deploy" / "proxy"


def test_user_unit_stays_in_the_user_manager():
    text = (PROXY / "sing-box" / "sing-box.user.service").read_text(encoding="utf-8")
    assert "WantedBy=default.target" in text
    assert "WantedBy=multi-user.target" not in text
    assert "%h/.local/bin/sing-box" in text
    assert "%h/.config/sing-box/config.json" in text
    assert "/etc/sing-box" not in text


def test_installer_enables_linger_and_does_not_replace_system_mode():
    text = (PROXY / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert 'SERVICE_SCOPE:-system' in text or 'SERVICE_SCOPE:-system' in text.replace(" ", "")
    assert "loginctl enable-linger" in text
    assert "systemctl --user enable --now sing-box" in text
    assert "systemctl enable --now sing-box" in text
    assert "KEEP_CONFIG" in text
    assert "cap_net_bind_service=+ep" in text


def test_deploy_script_accepts_user_scope():
    text = (PROXY / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert "--user" in text
    assert "--service-user" in text
    assert "sing-box.user.service" in text
    assert "SERVICE_SCOPE=user" in text


def test_certbot_hook_restarts_lingering_user_units():
    text = (PROXY / "nginx" / "certbot-restart-sing-box.sh").read_text(encoding="utf-8")
    assert "/var/lib/systemd/linger" in text
    assert "systemctl --user restart sing-box" in text
