from MaintainAll.notify.providers import PROVIDER_PRESETS, apply_provider_preset


def test_gmail_preset_uses_api_not_smtp_host():
    p = PROVIDER_PRESETS["gmail"]
    assert p["host"] == ""
    assert p["auth_default"] == "oauth"
    assert p["transport"] == "gmail_api"


def test_outlook_preset_uses_graph():
    p = PROVIDER_PRESETS["outlook"]
    assert p["host"] == ""
    assert p["transport"] == "graph_api"
    assert p["tenant_id_default"] == "common"


def test_apply_preset_overwrites_host_keeps_user():
    base = {
        "provider": "custom",
        "host": "old.example",
        "port": 25,
        "security": "starttls",
        "auth": "password",
        "user": "a@b.com",
        "from_addr": "a@b.com",
        "to": ["x@y.com"],
        "client_id": "cid",
        "tenant_id": "common",
    }
    out = apply_provider_preset(base, "gmail")
    assert out["provider"] == "gmail"
    assert out["host"] == ""
    assert out["auth"] == "oauth"
    assert out["user"] == "a@b.com"
    assert out["client_id"] == "cid"


def test_apply_custom_sets_password_auth():
    base = {
        "provider": "gmail",
        "host": "",
        "port": 587,
        "auth": "oauth",
    }
    out = apply_provider_preset(base, "custom")
    assert out["provider"] == "custom"
    assert out["auth"] == "password"


def test_provider_setup_links_and_hints():
    from MaintainAll.notify.providers import PROVIDER_SETUP_LINKS, provider_setup_hint

    assert "console.cloud.google.com" in PROVIDER_SETUP_LINKS["gmail"]["console"]
    assert "entra.microsoft.com" in PROVIDER_SETUP_LINKS["outlook"]["console"]
    assert "azure.microsoft.com/free" in PROVIDER_SETUP_LINKS["outlook"]["get_directory"]
    assert "gmail.send" in provider_setup_hint("gmail", auth="oauth")
    assert "Microsoft Graph" in provider_setup_hint("outlook", auth="oauth")
    assert "Azure" in provider_setup_hint("outlook", auth="oauth")
    assert provider_setup_hint("custom") == ""


def test_smtp_settings_roundtrip(tmp_path):
    from MaintainAll.config import Settings, SmtpSettings, load_settings, save_non_secrets

    s = Settings(
        smtp=SmtpSettings(
            provider="outlook",
            auth="oauth",
            host="",
            port=587,
            client_id="app-id",
            tenant_id="common",
            user="u@contoso.com",
            to=["ops@contoso.com"],
        )
    )
    save_non_secrets(s, config_dir=tmp_path)
    loaded = load_settings(config_dir_path=tmp_path)
    assert loaded.smtp.provider == "outlook"
    assert loaded.smtp.auth == "oauth"
    assert loaded.smtp.client_id == "app-id"
