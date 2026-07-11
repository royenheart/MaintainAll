"""OAuth2 helpers for Gmail API / Microsoft Graph mail send."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable
from urllib.request import Request, urlopen

# Gmail API send (not full mail.google.com SMTP scope)
GMAIL_SCOPES = "https://www.googleapis.com/auth/gmail.send"
# Microsoft Graph send mail
OUTLOOK_SCOPES = (
    "https://graph.microsoft.com/Mail.Send offline_access openid email"
)


def provider_oauth_endpoints(
    provider: str, *, tenant_id: str = "common"
) -> dict[str, str]:
    if provider == "gmail":
        return {
            "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
            "token": "https://oauth2.googleapis.com/token",
            "scopes": GMAIL_SCOPES,
        }
    if provider == "outlook":
        tenant = (tenant_id or "common").strip() or "common"
        base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
        return {
            "authorize": f"{base}/authorize",
            "token": f"{base}/token",
            "scopes": OUTLOOK_SCOPES,
        }
    raise ValueError(f"OAuth not supported for provider {provider!r}")


def pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_xoauth2_string(user: str, access_token: str) -> str:
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"


def encode_xoauth2_sasl(user: str, access_token: str) -> str:
    return base64.b64encode(
        build_xoauth2_string(user, access_token).encode("utf-8")
    ).decode("ascii")


def build_authorize_url(
    *,
    provider: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    tenant_id: str = "common",
    login_hint: str = "",
    state: str = "",
) -> str:
    ep = provider_oauth_endpoints(provider, tenant_id=tenant_id)
    params: dict[str, str] = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": ep["scopes"],
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if state:
        params["state"] = state
    if login_hint:
        params["login_hint"] = login_hint
    if provider == "outlook":
        params["response_mode"] = "query"
    return ep["authorize"] + "?" + urllib.parse.urlencode(params)


def _token_request(token_url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = Request(
        token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"token endpoint HTTP {exc.code}: {detail}") from exc
    if "error" in payload:
        raise RuntimeError(
            f"token error: {payload.get('error')} — {payload.get('error_description')}"
        )
    return payload


def exchange_code_for_tokens(
    *,
    provider: str,
    client_id: str,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_secret: str | None = None,
    tenant_id: str = "common",
) -> dict[str, Any]:
    ep = provider_oauth_endpoints(provider, tenant_id=tenant_id)
    data = {
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    return _token_request(ep["token"], data)


def refresh_access_token(
    *,
    provider: str,
    client_id: str,
    refresh_token: str,
    client_secret: str | None = None,
    tenant_id: str = "common",
) -> str:
    if provider == "custom":
        raise ValueError("OAuth refresh requires gmail or outlook provider")
    if not client_id:
        raise ValueError("smtp.client_id is required for OAuth")
    if not refresh_token:
        raise ValueError("smtp refresh token is missing — authorize in Settings")
    ep = provider_oauth_endpoints(provider, tenant_id=tenant_id)
    data = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if client_secret:
        data["client_secret"] = client_secret
    # Gmail refresh often needs scope again
    if provider == "gmail":
        data["scope"] = ep["scopes"]
    payload = _token_request(ep["token"], data)
    access = payload.get("access_token")
    if not access:
        raise RuntimeError("token response missing access_token")
    return str(access)


def run_localhost_oauth_flow(
    *,
    provider: str,
    client_id: str,
    client_secret: str | None = None,
    tenant_id: str = "common",
    login_hint: str = "",
    timeout_s: float = 180.0,
    on_ready: Callable[[str, int], None] | None = None,
) -> str:
    """Run PKCE authorize with localhost redirect; return refresh_token.

    *on_ready(authorize_url, callback_port)* is called after the listener is up.
    The browser is opened only when safe (no Cursor/VS Code remote BROWSER).
    On headless/remote, the caller should show *authorize_url* and optionally
    SSH-forward *callback_port*.
    """
    from MaintainAll.browser_open import try_open_url

    if provider not in ("gmail", "outlook"):
        raise ValueError("OAuth authorize only supports gmail and outlook")
    if not client_id.strip():
        raise ValueError("client_id is required")

    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    result: dict[str, Any] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("state", [None])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"invalid state")
                result["error"] = "invalid state"
                done.set()
                return
            if "error" in qs:
                result["error"] = qs["error"][0]
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"authorization denied")
                done.set()
                return
            code = qs.get("code", [None])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"missing code")
                result["error"] = "missing code"
                done.set()
                return
            result["code"] = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h3>MaintainAll authorized.</h3>"
                b"<p>You can close this tab.</p></body></html>"
            )
            done.set()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = int(server.server_address[1])
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    url = build_authorize_url(
        provider=provider,
        client_id=client_id.strip(),
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        tenant_id=tenant_id,
        login_hint=login_hint,
        state=state,
    )

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    opened = try_open_url(url)
    if on_ready is not None:
        on_ready(url, port)
    elif not opened:
        print(
            f"\nOpen this URL to authorize (callback port {port}):\n{url}\n",
            flush=True,
        )
    if not done.wait(timeout_s):
        server.server_close()
        raise TimeoutError(
            "OAuth authorize timed out — no browser redirect received. "
            f"If remote/SSH, forward port {port}: "
            f"ssh -L {port}:127.0.0.1:{port} <user>@<host> "
            "then open the authorize URL on your laptop."
        )
    server.server_close()
    if result.get("error"):
        raise RuntimeError(f"OAuth authorize failed: {result['error']}")
    tokens = exchange_code_for_tokens(
        provider=provider,
        client_id=client_id.strip(),
        code=result["code"],
        redirect_uri=redirect_uri,
        code_verifier=verifier,
        client_secret=client_secret,
        tenant_id=tenant_id,
    )
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise RuntimeError(
            "token response missing refresh_token "
            "(ensure offline_access / mail scope is granted)"
        )
    return str(refresh)
