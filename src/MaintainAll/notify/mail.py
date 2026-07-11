from __future__ import annotations

import shutil
import smtplib
import subprocess
from email.message import EmailMessage
from typing import Literal

from MaintainAll.config import Settings

NotifyChannel = Literal["gmail", "outlook", "smtp", "local", "none"]


def redact_secrets(text: str, settings: Settings) -> str:
    for secret in (
        settings.api_key,
        settings.smtp_password,
        settings.smtp_refresh_token,
        settings.smtp_client_secret,
    ):
        if secret is None:
            continue
        value = secret.get_secret_value()
        if value:
            text = text.replace(value, "***")
    return text


def _send_smtp(subject: str, body: str, settings: Settings) -> None:
    """Traditional SMTP (custom provider only) — username/password."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp.from_addr or settings.smtp.user
    msg["To"] = ", ".join(settings.smtp.to)
    msg.set_content(body)

    password = (
        settings.smtp_password.get_secret_value()
        if settings.smtp_password is not None
        else None
    )
    host = settings.smtp.host
    port = settings.smtp.port
    if settings.smtp.security == "ssl":
        with smtplib.SMTP_SSL(host, port) as smtp:
            if settings.smtp.user:
                smtp.login(settings.smtp.user, password or "")
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port) as smtp:
        if settings.smtp.user:
            smtp.starttls()
            smtp.login(settings.smtp.user, password or "")
        smtp.send_message(msg)


def _send_local(subject: str, body: str, settings: Settings) -> bool:
    recipients = settings.smtp.to
    sendmail = shutil.which("sendmail")
    if sendmail:
        headers = [f"Subject: {subject}"]
        if recipients:
            headers.append(f"To: {', '.join(recipients)}")
        payload = "\r\n".join(headers) + "\r\n\r\n" + body
        subprocess.run(
            [sendmail, "-t", "-i"],
            input=payload,
            text=True,
            check=True,
            capture_output=True,
        )
        return True

    mail = shutil.which("mail")
    if mail:
        cmd = [mail, "-s", subject]
        if recipients:
            cmd.extend(recipients)
        subprocess.run(
            cmd,
            input=body,
            text=True,
            check=True,
            capture_output=True,
        )
        return True

    return False


def send_notification(subject: str, body: str, settings: Settings) -> NotifyChannel:
    subject = redact_secrets(subject, settings)
    body = redact_secrets(body, settings)

    provider = settings.smtp.provider
    if provider == "gmail":
        from MaintainAll.notify.api_mail import send_via_gmail_api

        send_via_gmail_api(subject, body, settings)
        return "gmail"

    if provider == "outlook":
        from MaintainAll.notify.api_mail import send_via_graph_api

        send_via_graph_api(subject, body, settings)
        return "outlook"

    # custom (or legacy): traditional SMTP when host is set
    if settings.smtp.host:
        _send_smtp(subject, body, settings)
        return "smtp"

    if _send_local(subject, body, settings):
        return "local"

    return "none"


def mail_notify_allowed() -> bool:
    """Hard stop for accidental real sends (tests / explicit disable)."""
    import os

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    flag = (os.environ.get("MAINTAINALL_DISABLE_NOTIFY") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return False
    return True


def mail_is_configured(settings: Settings) -> bool:
    """True when a send path other than local/none is likely available."""
    provider = settings.smtp.provider
    if provider == "gmail":
        return bool(
            settings.smtp.client_id
            and settings.smtp.to
            and settings.smtp_refresh_token
            and settings.smtp_refresh_token.get_secret_value()
        )
    if provider == "outlook":
        return bool(
            settings.smtp.client_id
            and settings.smtp.to
            and settings.smtp_refresh_token
            and settings.smtp_refresh_token.get_secret_value()
        )
    return bool(settings.smtp.host)


def maybe_notify_mission(
    *,
    draft: dict,
    validation_ok: bool | None,
    body: str,
    settings: Settings,
) -> NotifyChannel | None:
    """Send mail when mission notify flags say so. Returns channel or None if skipped."""
    if not mail_notify_allowed():
        return None
    notify = draft.get("notify") if isinstance(draft.get("notify"), dict) else {}
    on_complete = bool(notify.get("on_complete", False))
    on_failure = bool(notify.get("on_failure", False))
    ok = bool(validation_ok)
    if ok and not on_complete:
        return None
    if not ok and not on_failure:
        return None
    mission_id = str(draft.get("id") or "unknown")
    status = "OK" if ok else "FAILED"
    subject = f"MaintainAll mission {mission_id}: {status}"
    return send_notification(subject, body, settings)
