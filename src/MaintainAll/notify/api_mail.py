"""Send mail via provider HTTP APIs (Gmail API / Microsoft Graph)."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any
from urllib.request import Request, urlopen

from MaintainAll.config import Settings
from MaintainAll.notify.oauth import refresh_access_token


def _access_token(settings: Settings) -> str:
    refresh = (
        settings.smtp_refresh_token.get_secret_value()
        if settings.smtp_refresh_token is not None
        else ""
    )
    client_secret = (
        settings.smtp_client_secret.get_secret_value()
        if settings.smtp_client_secret is not None
        else None
    )
    return refresh_access_token(
        provider=settings.smtp.provider,
        client_id=settings.smtp.client_id,
        refresh_token=refresh,
        client_secret=client_secret or None,
        tenant_id=settings.smtp.tenant_id,
    )


def _build_email_message(subject: str, body: str, settings: Settings) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    from_addr = settings.smtp.from_addr or settings.smtp.user
    # Gmail rejects bare display names without @; fall back to account.
    if from_addr and "@" not in from_addr and settings.smtp.user:
        from_addr = settings.smtp.user
    msg["From"] = from_addr
    msg["To"] = ", ".join(settings.smtp.to)
    msg.set_content(body)
    return msg


def _http_json(
    method: str,
    url: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} → HTTP {exc.code}: {detail}") from exc


def send_via_gmail_api(subject: str, body: str, settings: Settings) -> None:
    if not settings.smtp.to:
        raise ValueError("smtp.to is required for Gmail API send")
    token = _access_token(settings)
    msg = _build_email_message(subject, body, settings)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")
    _http_json(
        "POST",
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        token=token,
        payload={"raw": raw},
    )


def send_via_graph_api(subject: str, body: str, settings: Settings) -> None:
    if not settings.smtp.to:
        raise ValueError("smtp.to is required for Microsoft Graph send")
    token = _access_token(settings)
    to_recipients = [
        {"emailAddress": {"address": addr}} for addr in settings.smtp.to if addr
    ]
    message: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "Text", "content": body},
        "toRecipients": to_recipients,
    }
    from_addr = settings.smtp.from_addr or settings.smtp.user
    if from_addr:
        message["from"] = {"emailAddress": {"address": from_addr}}
    _http_json(
        "POST",
        "https://graph.microsoft.com/v1.0/me/sendMail",
        token=token,
        payload={"message": message, "saveToSentItems": True},
    )
