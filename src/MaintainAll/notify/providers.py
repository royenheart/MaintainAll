"""Mail provider presets: Gmail/Outlook use HTTP APIs; custom uses SMTP."""

from __future__ import annotations

from typing import Any, Literal

SmtpProvider = Literal["gmail", "outlook", "custom"]
SmtpAuth = Literal["password", "oauth"]
SmtpSecurity = Literal["starttls", "ssl"]

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "gmail": {
        # Sent via Gmail API — host unused
        "host": "",
        "port": 587,
        "security": "starttls",
        "auth_default": "oauth",
        "transport": "gmail_api",
    },
    "outlook": {
        # Sent via Microsoft Graph sendMail — host unused
        "host": "",
        "port": 587,
        "security": "starttls",
        "auth_default": "oauth",
        "tenant_id_default": "common",
        "transport": "graph_api",
    },
    "custom": {
        "auth_default": "password",
        "transport": "smtp",
    },
}

PROVIDER_SETUP_LINKS: dict[str, dict[str, str]] = {
    "gmail": {
        "console": "https://console.cloud.google.com/apis/credentials",
        "consent": "https://console.cloud.google.com/apis/credentials/consent",
        "api_enable": "https://console.cloud.google.com/apis/library/gmail.googleapis.com",
        "hint_oauth": (
            "Uses Gmail API (not SMTP).\n"
            "1) Enable Gmail API → OAuth Desktop client\n"
            "2) Paste Client ID → Authorize (scope gmail.send)"
        ),
        "hint_password": "",
    },
    "outlook": {
        # Need any Entra directory. Azure free is the reliable default;
        # M365 Developer Program often rejects applicants ("don't qualify").
        "get_directory": "https://azure.microsoft.com/free/",
        "get_directory_m365_dev": (
            "https://developer.microsoft.com/microsoft-365/dev-program"
        ),
        "console": (
            "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/"
            "ApplicationsListBlade"
        ),
        "new_app": (
            "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/"
            "CreateApplicationBlade/quickStartType~/null/isMSAApp~/false"
        ),
        "hint_oauth": (
            "Uses Microsoft Graph (not SMTP).\n"
            "1) Create a free Azure account (gets an Entra directory).\n"
            "2) Entra → App registration → desktop redirect http://127.0.0.1\n"
            "3) Mail.Send + offline_access → paste Client ID → Authorize"
        ),
        "hint_password": "",
    },
}


def provider_setup_hint(provider: str, *, auth: str = "oauth") -> str:
    links = PROVIDER_SETUP_LINKS.get(provider) or {}
    if provider in ("gmail", "outlook"):
        return links.get("hint_oauth", "")
    key = "hint_oauth" if auth == "oauth" else "hint_password"
    return links.get(key, "")


def apply_provider_preset(smtp: dict[str, Any], provider: SmtpProvider) -> dict[str, Any]:
    """Apply preset fields for *provider*. Preserves user/from/to/client_id."""
    if provider not in PROVIDER_PRESETS:
        raise ValueError(f"unknown mail provider: {provider!r}")
    out = dict(smtp)
    out["provider"] = provider
    preset = PROVIDER_PRESETS[provider]
    if provider != "custom":
        out["host"] = preset.get("host", "")
        out["port"] = preset.get("port", 587)
        out["security"] = preset.get("security", "starttls")
        out["auth"] = preset["auth_default"]
        if "tenant_id_default" in preset:
            out["tenant_id"] = out.get("tenant_id") or preset["tenant_id_default"]
    else:
        out["auth"] = preset["auth_default"]
    return out
