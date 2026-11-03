"""Password, session, CSRF and authenticated-user helpers."""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models as m
from .config import (
    AUTH_COOKIE_SECURE,
    AUTH_COOKIE_SAMESITE,
    BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_ADMIN_USERNAME,
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_TTL_MINUTES,
)
from .database import get_db

PASSWORD_ITERATIONS = 600_000
PASSWORD_SALT_BYTES = 16
TOKEN_BYTES = 32


def normalize_username(value: str) -> str:
    return (value or "").strip().casefold()


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Password must be at least 12 characters long")
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(derived).decode("ascii").rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(expected_text + "=" * (-len(expected_text) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (AttributeError, ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def user_public(db: Session, user: m.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "institution_ids": [x.institution_id for x in db.query(m.UserInstitution).filter_by(user_id=user.id).all()],
    }


@dataclass
class AuthContext:
    user: m.User
    session: m.AuthSession


def auth_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = db.query(m.AuthSession).filter_by(token_hash=token_hash(raw_token)).first()
    now = datetime.utcnow()
    if not session or session.revoked_at is not None or session.expires_at <= now:
        if session and session.revoked_at is None:
            session.revoked_at = now
            db.commit()
        raise HTTPException(status_code=401, detail="Authentication required")
    user = db.get(m.User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required")
    session.last_seen_at = now
    return AuthContext(user=user, session=session)


def current_user(context: AuthContext = Depends(auth_context)) -> m.User:
    return context.user


def require_csrf(request: Request, context: AuthContext = Depends(auth_context)) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not supplied or not cookie or not hmac.compare_digest(supplied, cookie):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    if not hmac.compare_digest(token_hash(supplied), context.session.csrf_token_hash):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def create_session(db: Session, user: m.User) -> tuple[str, str, m.AuthSession]:
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    csrf_token = secrets.token_urlsafe(TOKEN_BYTES)
    session = m.AuthSession(
        token_hash=token_hash(raw_token),
        csrf_token_hash=token_hash(csrf_token),
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(minutes=SESSION_TTL_MINUTES),
    )
    db.add(session)
    return raw_token, csrf_token, session


def set_auth_cookies(response, raw_token: str, csrf_token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_token,
        max_age=SESSION_TTL_MINUTES * 60,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=SESSION_TTL_MINUTES * 60,
        httponly=False,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def bootstrap_admin_if_configured(db: Session) -> bool:
    """Create exactly one initial admin only when explicit env credentials exist."""
    if db.query(m.User).count() != 0 or not BOOTSTRAP_ADMIN_USERNAME or not BOOTSTRAP_ADMIN_PASSWORD:
        return False
    username = normalize_username(BOOTSTRAP_ADMIN_USERNAME)
    if len(username) < 3:
        raise RuntimeError("BOOTSTRAP_ADMIN_USERNAME must have at least 3 characters")
    user = m.User(username=username, password_hash=hash_password(BOOTSTRAP_ADMIN_PASSWORD), role="admin", is_active=True)
    db.add(user)
    db.commit()
    return True
