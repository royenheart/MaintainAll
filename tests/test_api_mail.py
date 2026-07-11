from unittest.mock import patch

from pydantic import SecretStr

from MaintainAll.config import Settings, SmtpSettings
from MaintainAll.notify.api_mail import send_via_gmail_api, send_via_graph_api


def test_gmail_api_posts_raw_message():
    settings = Settings(
        smtp=SmtpSettings(
            provider="gmail",
            auth="oauth",
            user="me@gmail.com",
            from_addr="me@gmail.com",
            to=["a@example.com"],
            client_id="cid",
        ),
        smtp_refresh_token=SecretStr("rt"),
    )
    with (
        patch("MaintainAll.notify.api_mail.refresh_access_token", return_value="AT"),
        patch("MaintainAll.notify.api_mail._http_json") as http,
    ):
        send_via_gmail_api("Hello", "Body", settings)
    assert http.call_args[0][0] == "POST"
    assert "gmail.googleapis.com" in http.call_args[0][1]
    payload = http.call_args[1]["payload"]
    assert "raw" in payload


def test_graph_api_posts_send_mail():
    settings = Settings(
        smtp=SmtpSettings(
            provider="outlook",
            auth="oauth",
            user="me@contoso.com",
            to=["a@example.com", "b@example.com"],
            client_id="cid",
        ),
        smtp_refresh_token=SecretStr("rt"),
    )
    with (
        patch("MaintainAll.notify.api_mail.refresh_access_token", return_value="AT"),
        patch("MaintainAll.notify.api_mail._http_json") as http,
    ):
        send_via_graph_api("Hello", "Body", settings)
    assert "graph.microsoft.com" in http.call_args[0][1]
    payload = http.call_args[1]["payload"]
    assert payload["message"]["subject"] == "Hello"
    assert len(payload["message"]["toRecipients"]) == 2
