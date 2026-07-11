from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from MaintainAll.config import Settings, SmtpSettings
from MaintainAll.notify.mail import _send_smtp, send_notification


def test_send_custom_smtp_uses_login():
    settings = Settings(
        smtp=SmtpSettings(
            provider="custom",
            auth="password",
            host="smtp.example.com",
            port=587,
            security="starttls",
            user="u@example.com",
            from_addr="u@example.com",
            to=["t@example.com"],
        ),
        smtp_password=SecretStr("secret-pass"),
    )
    smtp = MagicMock()
    with patch("MaintainAll.notify.mail.smtplib.SMTP") as SMTP:
        SMTP.return_value.__enter__.return_value = smtp
        _send_smtp("subj", "body", settings)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("u@example.com", "secret-pass")
    smtp.send_message.assert_called_once()


def test_send_notification_gmail_uses_api():
    settings = Settings(
        smtp=SmtpSettings(
            provider="gmail",
            auth="oauth",
            user="u@gmail.com",
            to=["t@example.com"],
            client_id="cid",
        ),
        smtp_refresh_token=SecretStr("rt"),
    )
    with patch("MaintainAll.notify.api_mail.send_via_gmail_api") as send:
        assert send_notification("s", "b", settings) == "gmail"
        send.assert_called_once()


def test_send_notification_outlook_uses_graph():
    settings = Settings(
        smtp=SmtpSettings(
            provider="outlook",
            auth="oauth",
            user="u@contoso.com",
            to=["t@example.com"],
            client_id="cid",
        ),
        smtp_refresh_token=SecretStr("rt"),
    )
    with patch("MaintainAll.notify.api_mail.send_via_graph_api") as send:
        assert send_notification("s", "b", settings) == "outlook"
        send.assert_called_once()
