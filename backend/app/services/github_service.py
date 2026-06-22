"""
GitHub OAuth 2.0 (Authorization Code flow) — \"Sign in with GitHub\" + repo access.

Flow:
  Browser → /auth/github/login → GitHub consent → GitHub redirects to
  /auth/github/callback?code=... → exchange code for access token, read profile,
  find-or-create local user, store encrypted token, mint JWT.

Credentials come from settings (GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET in .env).
If unset, is_configured() is False and endpoints return a clear error.

Token encryption:
  GitHub access tokens are stored Fernet-encrypted in the DB using
  GITHUB_TOKEN_ENCRYPTION_KEY. If the key is absent (local dev), tokens are stored
  as-is (still protected by the JWT auth on every endpoint, but not encrypted at rest).
"""
from __future__ import annotations

import base64
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

settings = get_settings()

# ── GitHub API constants ────────────────────────────────────────────────────

_AUTH_ENDPOINT  = "https://github.com/login/oauth/authorize"
_TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
_API_BASE       = "https://api.github.com"
# read:user → profile, user:email → email, repo → full private repo read/write
_SCOPES = "read:user user:email repo"


# ── Configuration ───────────────────────────────────────────────────────────

def is_configured() -> bool:
    return bool(settings.github_client_id and settings.github_client_secret)


def make_state() -> str:
    """Opaque anti-CSRF state token echoed through the round-trip."""
    return secrets.token_urlsafe(24)


def build_auth_url(state: str, redirect_uri: str | None = None) -> str:
    params = {
        "client_id":    settings.github_client_id,
        "redirect_uri": redirect_uri or settings.github_redirect_uri,
        "scope":        _SCOPES,
        "state":        state,
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


# ── Token encryption (Fernet, graceful fallback) ────────────────────────────

def _fernet():
    """Return a Fernet instance if a key is configured, else None."""
    key = settings.github_token_encryption_key
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        # Accept both raw-bytes keys and base64-url-encoded strings
        if not key.endswith("="):
            key = key + "=" * (4 - len(key) % 4) if len(key) % 4 else key
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_token(token: str) -> str:
    """Encrypt a GitHub access token for storage. Falls back to plaintext."""
    f = _fernet()
    if f is None:
        return token
    return f.encrypt(token.encode()).decode()


def decrypt_token(stored: str) -> str:
    """Decrypt a stored GitHub token. Falls back to returning it as-is."""
    f = _fernet()
    if f is None:
        return stored
    try:
        return f.decrypt(stored.encode()).decode()
    except Exception:
        # If decryption fails (e.g. key changed) return as-is so we get a
        # 401 from GitHub rather than a silent crash.
        return stored


# ── OAuth code exchange ─────────────────────────────────────────────────────

def exchange_code(code: str, redirect_uri: str | None = None) -> dict[str, Any]:
    """
    Exchange an auth code for a GitHub access token, then fetch the user profile.

    Returns {
        "access_token": str,
        "id": int,          ← GitHub user ID
        "login": str,       ← GitHub username
        "email": str | None,
        "avatar_url": str | None,
        "name": str | None,
    }.
    Raises httpx.HTTPStatusError on failure.
    """
    with httpx.Client(timeout=15) as client:
        tok_resp = client.post(
            _TOKEN_ENDPOINT,
            data={
                "client_id":     settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code":          code,
                "redirect_uri":  redirect_uri or settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        tok_resp.raise_for_status()
        tok_data = tok_resp.json()
        access_token = tok_data.get("access_token", "")
        if not access_token:
            raise ValueError(f"GitHub did not return an access token: {tok_data}")

        # Fetch user profile
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
        profile = client.get(f"{_API_BASE}/user", headers=headers)
        profile.raise_for_status()
        user_data = profile.json()

        # Fetch primary verified email if not in profile
        email = user_data.get("email")
        if not email:
            emails_resp = client.get(f"{_API_BASE}/user/emails", headers=headers)
            if emails_resp.is_success:
                for e in emails_resp.json():
                    if e.get("primary") and e.get("verified"):
                        email = e.get("email")
                        break

        return {
            "access_token": access_token,
            "id":           user_data["id"],
            "login":        user_data["login"],
            "email":        email,
            "avatar_url":   user_data.get("avatar_url"),
            "name":         user_data.get("name"),
        }


# ── GitHub REST API helpers ─────────────────────────────────────────────────

def _gh_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_user_repos(
    access_token: str,
    page: int = 1,
    per_page: int = 50,
    sort: str = "updated",
) -> list[dict]:
    """List authenticated user's repos (public + private), sorted by last update."""
    with httpx.Client(timeout=20) as client:
        resp = client.get(
            f"{_API_BASE}/user/repos",
            headers=_gh_headers(access_token),
            params={"sort": sort, "per_page": per_page, "page": page, "affiliation": "owner,collaborator,organization_member"},
        )
        resp.raise_for_status()
        return [
            {
                "id":             r["id"],
                "name":           r["name"],
                "full_name":      r["full_name"],
                "private":        r["private"],
                "description":    r.get("description"),
                "default_branch": r.get("default_branch", "main"),
                "clone_url":      r["clone_url"],
                "html_url":       r["html_url"],
                "updated_at":     r.get("updated_at"),
                "language":       r.get("language"),
                "stargazers_count": r.get("stargazers_count", 0),
                "forks_count":    r.get("forks_count", 0),
            }
            for r in resp.json()
        ]


def get_repo_branches(access_token: str, owner: str, repo: str) -> list[dict]:
    """List branches for a given repo."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/branches",
            headers=_gh_headers(access_token),
            params={"per_page": 100},
        )
        resp.raise_for_status()
        return [{"name": b["name"], "sha": b["commit"]["sha"]} for b in resp.json()]


def get_branch_sha(access_token: str, owner: str, repo: str, branch: str) -> str:
    """Get the HEAD commit SHA for a branch."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/branches/{branch}",
            headers=_gh_headers(access_token),
        )
        resp.raise_for_status()
        return resp.json()["commit"]["sha"]


def create_branch(access_token: str, owner: str, repo: str, new_branch: str, from_branch: str) -> dict:
    """Create a new branch from the HEAD of `from_branch`."""
    sha = get_branch_sha(access_token, owner, repo, from_branch)
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{_API_BASE}/repos/{owner}/{repo}/git/refs",
            headers=_gh_headers(access_token),
            json={"ref": f"refs/heads/{new_branch}", "sha": sha},
        )
        resp.raise_for_status()
        return {"name": new_branch, "sha": sha}


def get_file_sha(
    access_token: str, owner: str, repo: str, path: str, branch: str
) -> str | None:
    """Get the blob SHA of an existing file (needed for updates). Returns None if not found."""
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/contents/{path}",
            headers=_gh_headers(access_token),
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("sha")


def commit_file(
    access_token: str,
    owner: str,
    repo: str,
    path: str,
    content: str,
    branch: str,
    message: str,
) -> dict:
    """
    Create or update a single file in a GitHub repo and commit the change.
    `content` is the raw UTF-8 string; we base64-encode it for the API.
    Returns {"commit_sha": str, "html_url": str}.
    """
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    existing_sha = get_file_sha(access_token, owner, repo, path, branch)
    payload: dict[str, Any] = {
        "message": message,
        "content": encoded,
        "branch":  branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha  # required for updates

    with httpx.Client(timeout=20) as client:
        resp = client.put(
            f"{_API_BASE}/repos/{owner}/{repo}/contents/{path}",
            headers=_gh_headers(access_token),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "commit_sha": data["commit"]["sha"],
            "html_url":   data["content"]["html_url"],
        }


def build_clone_url(access_token: str, clone_url: str) -> str:
    """
    Inject the OAuth token into a clone URL for authenticated HTTPS cloning
    of private repos.  clone_url is like https://github.com/owner/repo.git
    Result: https://<token>@github.com/owner/repo.git
    """
    if "github.com" in clone_url:
        return clone_url.replace("https://", f"https://{access_token}@")
    return clone_url
