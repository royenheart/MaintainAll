import base64
from unittest.mock import patch

from MaintainAll.notify.oauth import (
    GMAIL_SCOPES,
    OUTLOOK_SCOPES,
    build_xoauth2_string,
    encode_xoauth2_sasl,
    provider_oauth_endpoints,
    refresh_access_token,
)


def test_api_scopes_not_smtp():
    assert "gmail.send" in GMAIL_SCOPES
    assert "graph.microsoft.com/Mail.Send" in OUTLOOK_SCOPES
    assert "SMTP.Send" not in OUTLOOK_SCOPES


def test_xoauth2_helpers_still_available():
    raw = build_xoauth2_string("u@example.com", "tok")
    assert raw == "user=u@example.com\x01auth=Bearer tok\x01\x01"
    b64 = encode_xoauth2_sasl("u@example.com", "tok")
    assert base64.b64decode(b64).decode() == raw


def test_endpoints_gmail_outlook():
    g = provider_oauth_endpoints("gmail")
    assert "accounts.google.com" in g["authorize"]
    assert g["scopes"] == GMAIL_SCOPES
    o = provider_oauth_endpoints("outlook", tenant_id="contoso")
    assert "login.microsoftonline.com/contoso" in o["authorize"]
    assert "Mail.Send" in o["scopes"]


def test_refresh_access_token_gmail():
    class Resp:
        status = 200

        def read(self):
            return b'{"access_token":"AT","expires_in":3600}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("MaintainAll.notify.oauth.urlopen", return_value=Resp()):
        tok = refresh_access_token(
            provider="gmail",
            client_id="cid",
            refresh_token="rt",
            client_secret=None,
            tenant_id="common",
        )
    assert tok == "AT"
