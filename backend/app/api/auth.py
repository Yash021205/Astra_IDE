"""Authentication endpoints: register, login, current user, Google OAuth."""
import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import Token, UserCreate, UserOut, UpdateProfile
from app.services import oauth_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _unique_username(db: Session, base: str) -> str:
    """Derive a unique username from an email local-part (foo, foo1, foo2…)."""
    base = "".join(c for c in base if c.isalnum() or c in "._-")[:48] or "user"
    name = base
    i = 0
    while db.query(User).filter(User.username == name).first() is not None:
        i += 1
        name = f"{base}{i}"
    return name


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    existing = (
        db.query(User)
        .filter(or_(User.email == payload.email, User.username == payload.username))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already registered",
        )

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db:        Session = Depends(get_db),
) -> Token:
    # OAuth2PasswordRequestForm.username can be either email or username
    user = (
        db.query(User)
        .filter(or_(User.email == form_data.username, User.username == form_data.username))
        .first()
    )
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
def update_me(payload: UpdateProfile, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)) -> UserOut:
    """Update the current user's profile (e.g. avatar_url after an imgbb upload)."""
    if payload.avatar_url is not None:
        current_user.avatar_url = payload.avatar_url or None
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


# ── Google OAuth (Sign in with Google) ──────────────────────────────────────

def _public_base(request: Request) -> str:
    """The public origin the user actually hit (e.g. https://astraide.tech),
    honouring the reverse-proxy headers Caddy sets. Lets OAuth work on whatever
    domain the user came from — astraide.tech, the sslip host, etc."""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = (request.headers.get("x-forwarded-host")
            or request.headers.get("host")
            or request.url.netloc)
    return f"{proto}://{host}"


def _redirect_uri(request: Request) -> str:
    # Browser-facing callback path (Caddy/Next proxy /api -> backend /api/v1).
    return f"{_public_base(request)}/api/auth/google/callback"


@router.get("/google/login")
def google_login(request: Request) -> RedirectResponse:
    """Kick off the OAuth flow — redirect the browser to Google's consent page."""
    base = _public_base(request)
    if not oauth_service.is_configured():
        # Not configured: bounce back to the login page with a clear message.
        return RedirectResponse(f"{base}/login?error=google_not_configured")
    state = oauth_service.make_state()
    resp = RedirectResponse(oauth_service.build_auth_url(state, _redirect_uri(request)))
    # Stash state in a short-lived cookie for CSRF protection on callback.
    resp.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return resp


@router.get("/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None,
                    error: str | None = None, db: Session = Depends(get_db)):
    """Handle Google's redirect: exchange the code, find/create the user, mint a JWT."""
    base = _public_base(request)
    if error or not code:
        return RedirectResponse(f"{base}/login?error=google_denied")
    if not oauth_service.is_configured():
        return RedirectResponse(f"{base}/login?error=google_not_configured")

    try:
        profile = oauth_service.exchange_code(code, _redirect_uri(request))
    except httpx.HTTPError:
        return RedirectResponse(f"{base}/login?error=google_exchange_failed")

    email = (profile.get("email") or "").lower()
    if not email:
        return RedirectResponse(f"{base}/login?error=google_no_email")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            username=_unique_username(db, email.split("@")[0]),
            # OAuth users have no usable password (random, never revealed).
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(subject=user.id)
    # Hand the JWT to the SPA on the SAME origin the user came from.
    return RedirectResponse(f"{base}/oauth/callback?token={token}")


# ── GitHub OAuth (Sign in with GitHub + repo access) ────────────────────────

from app.services import github_service  # noqa: E402 (after router definition)


def _github_redirect_uri(request: Request) -> str:
    return f"{_public_base(request)}/api/auth/github/callback"


@router.get("/github/login")
def github_login(request: Request) -> RedirectResponse:
    """Kick off the GitHub OAuth flow — redirect to GitHub's consent page."""
    base = _public_base(request)
    if not github_service.is_configured():
        return RedirectResponse(f"{base}/login?error=github_not_configured")
    state = github_service.make_state()
    resp = RedirectResponse(github_service.build_auth_url(state, _github_redirect_uri(request)))
    resp.set_cookie("github_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return resp


@router.get("/github/callback")
def github_callback(
    request: Request,
    code:    str | None = None,
    state:   str | None = None,
    error:   str | None = None,
    db:      Session = Depends(get_db),
):
    """
    Handle GitHub's redirect: exchange the code, find/create the user,
    store the encrypted GitHub token, mint a JWT, redirect to the SPA.
    """
    base = _public_base(request)
    if error or not code:
        return RedirectResponse(f"{base}/login?error=github_denied")
    if not github_service.is_configured():
        return RedirectResponse(f"{base}/login?error=github_not_configured")

    try:
        profile = github_service.exchange_code(code, _github_redirect_uri(request))
    except (httpx.HTTPError, ValueError):
        return RedirectResponse(f"{base}/login?error=github_exchange_failed")

    github_id    = profile["id"]
    github_login = profile["login"]
    email        = (profile.get("email") or "").lower() or None
    avatar_url   = profile.get("avatar_url")
    raw_token    = profile["access_token"]
    enc_token    = github_service.encrypt_token(raw_token)

    # 1. Look up by GitHub ID (returning user who connected via GitHub)
    user = db.query(User).filter(User.github_id == github_id).first()

    # 2. Fall back to matching by email (merge with existing password/Google account)
    if user is None and email:
        user = db.query(User).filter(User.email == email).first()

    # 3. Brand-new user — create one
    if user is None:
        if not email:
            return RedirectResponse(f"{base}/login?error=github_no_email")
        user = User(
            email=email,
            username=_unique_username(db, github_login),
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            avatar_url=avatar_url,
        )
        db.add(user)
        db.flush()  # get id before commit

    # Always refresh GitHub fields
    user.github_id           = github_id
    user.github_login        = github_login
    user.github_access_token = enc_token
    if avatar_url and not user.avatar_url:
        user.avatar_url = avatar_url

    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.id)
    return RedirectResponse(f"{base}/oauth/callback?token={token}")


@router.get("/github/status")
def github_status(current_user: User = Depends(get_current_user)):
    """Return whether the current user has a linked GitHub account."""
    return {
        "connected":    current_user.github_login is not None,
        "github_login": current_user.github_login,
        "avatar_url":   current_user.avatar_url,
    }


@router.delete("/github/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def github_disconnect(
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> None:
    """Remove the stored GitHub token and unlink the account."""
    current_user.github_id           = None
    current_user.github_login        = None
    current_user.github_access_token = None
    db.commit()

