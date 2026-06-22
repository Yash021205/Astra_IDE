"""
Google OAuth 2.0 (Authorization Code flow) — "Sign in with Google".

Browser -> /auth/google/login -> Google consent -> Google redirects to
/auth/google/callback?code=... -> we exchange the code for tokens, read the
user's profile, then find-or-create a local user and issue our own JWT.

Credentials come from settings (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in
.env). If unset, is_configured() is False and the endpoints return a clear 503
so the rest of the app keeps working.
"""
from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

settings = get_settings()

_AUTH_ENDPOINT  = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO       = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPES         = "openid email profile"


def is_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def make_state() -> str:
    """Opaque anti-CSRF state token echoed through the round-trip."""
    return secrets.token_urlsafe(24)


def build_auth_url(state: str, redirect_uri: str | None = None) -> str:
    params = {
        "client_id":     settings.google_client_id,
        "redirect_uri":  redirect_uri or settings.google_redirect_uri,
        "response_type": "code",
        "scope":         _SCOPES,
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str | None = None) -> dict:
    """Exchange an auth code for tokens, then fetch the user's profile.

    `redirect_uri` MUST match the one used in build_auth_url (Google checks it).
    Returns {"email", "name", "sub", "picture", "email_verified"}.
    Raises httpx.HTTPStatusError on a failed exchange.
    """
    with httpx.Client(timeout=15) as client:
        tok = client.post(_TOKEN_ENDPOINT, data={
            "code":          code,
            "client_id":     settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri":  redirect_uri or settings.google_redirect_uri,
            "grant_type":    "authorization_code",
        })
        tok.raise_for_status()
        access_token = tok.json()["access_token"]

        info = client.get(_USERINFO, headers={"Authorization": f"Bearer {access_token}"})
        info.raise_for_status()
        return info.json()
