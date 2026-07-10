from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from MaintainAll.config import Settings, SmtpSettings
from MaintainAll.notify.mail import redact_secrets, send_notification
from MaintainAll.notify.report import write_report


def test_write_report_creates_file(tmp_path: Path):
    reports_root = tmp_path / "reports"
    path = write_report("daily-check", "# Report\nok", reports_root)
    assert path.exists()
    assert path.parent == reports_root
    assert path.name.startswith("daily-check-")
    assert path.name.endswith(".md")
    assert path.read_text(encoding="utf-8") == "# Report\nok"


def test_redact_secrets_api_key():
    settings = Settings(api_key=SecretStr("sk-super-secret"))
    text = "Log: api_key=sk-super-secret and more"
    assert redact_secrets(text, settings) == "Log: api_key=*** and more"


def test_redact_secrets_no_key():
    settings = Settings()
    assert redact_secrets("plain text", settings) == "plain text"


def test_send_notification_no_smtp_no_local():
    settings = Settings(smtp=SmtpSettings(host=""))
    with patch("MaintainAll.notify.mail.shutil.which", return_value=None):
        assert send_notification("subj", "body", settings) == "none"


def test_send_notification_local_sendmail(tmp_path: Path):
    settings = Settings(smtp=SmtpSettings(host="", to=["ops@example.com"]))
    with patch("MaintainAll.notify.mail.shutil.which") as which:
        which.side_effect = lambda cmd: "/usr/bin/sendmail" if cmd == "sendmail" else None
        with patch("MaintainAll.notify.mail.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            assert send_notification("Alert", "body text", settings) == "local"
            run.assert_called_once()
            assert run.call_args[0][0][0] == "/usr/bin/sendmail"


def test_send_notification_smtp():
    settings = Settings(
        smtp=SmtpSettings(
            host="smtp.example.com",
            port=587,
            user="user",
            from_addr="from@example.com",
            to=["to@example.com"],
        ),
        smtp_password=SecretStr("pass"),
    )
    with patch("MaintainAll.notify.mail.smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp
        assert send_notification("Subject", "Body", settings) == "smtp"
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("user", "pass")
        smtp.send_message.assert_called_once()


def test_send_notification_redacts_api_key_in_body():
    settings = Settings(
        api_key=SecretStr("sk-leak"),
        smtp=SmtpSettings(host="smtp.example.com", to=["a@b.com"]),
    )
    with patch("MaintainAll.notify.mail.smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp
        send_notification("Sub", "token sk-leak here", settings)
        msg = smtp.send_message.call_args[0][0]
        assert "sk-leak" not in msg.get_content()
        assert "***" in msg.get_content()
