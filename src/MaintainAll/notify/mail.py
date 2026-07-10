from __future__ import annotations

import shutil
import smtplib
import subprocess
from email.message import EmailMessage
from typing import Literal

from MaintainAll.config import Settings

NotifyChannel = Literal["smtp", "local", "none"]


def redact_secrets(text: str, settings: Settings) -> str:
    for secret in (settings.api_key, settings.smtp_password):
        if secret is None:
            continue
        value = secret.get_secret_value()
        if value:
            text = text.replace(value, "***")
    return text


def _send_smtp(subject: str, body: str, settings: Settings) -> None:
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
    with smtplib.SMTP(settings.smtp.host, settings.smtp.port) as smtp:
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

    if settings.smtp.host:
        _send_smtp(subject, body, settings)
        return "smtp"

    if _send_local(subject, body, settings):
        return "local"

    return "none"
