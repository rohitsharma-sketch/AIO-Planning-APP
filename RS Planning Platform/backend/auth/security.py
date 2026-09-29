"""Password hashing and session-cookie helpers.

Uses the `bcrypt` library directly rather than passlib's CryptContext —
passlib 1.7.4 (its last release, unmaintained) breaks against bcrypt>=4.1's
API (it probes `bcrypt.__about__`, removed upstream), so passlib is not used
here despite being the more commonly-reached-for wrapper."""
import os
import warnings

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

DEV_SESSION_SECRET = "dev-only-change-me"   # development only - public, so never valid in production


def session_secret() -> str:
    """The key that signs session cookies, remember-me cookies and reset links (app.py's SessionMiddleware uses
    this too). With APP_ENV=production a missing, default or short (<32 chars) SESSION_SECRET stops the app from
    starting (2026-09-29: the live server ran on the public default, so anyone with the code could forge an admin
    session). Development falls back to DEV_SESSION_SECRET with a warning."""
    secret = os.environ.get("SESSION_SECRET", "").strip()
    production = os.environ.get("APP_ENV", "").strip().lower() == "production"
    if production and (not secret or secret == DEV_SESSION_SECRET or len(secret) < 32):
        raise RuntimeError("SESSION_SECRET (32+ chars, not the dev default) is required when APP_ENV=production")
    if not secret:
        warnings.warn("SESSION_SECRET not set - using the public development secret", RuntimeWarning)
        return DEV_SESSION_SECRET
    return secret


SESSION_SECRET = session_secret()

REMEMBER_MAX_AGE = 30 * 24 * 60 * 60  # 30 days
_remember_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="remember-me")


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def make_remember_token(user_id: str) -> str:
    return _remember_serializer.dumps({"uid": user_id})


def read_remember_token(token: str) -> str | None:
    """Returns the user id encoded in a still-valid remember-me token, or None
    if the token is missing, tampered with, or older than REMEMBER_MAX_AGE."""
    try:
        data = _remember_serializer.loads(token, max_age=REMEMBER_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")


# Same stateless signed-token pattern as remember-me, above, but salted
# separately so a remember-me cookie can never be replayed as a reset link
# (and vice versa) even though both just wrap {"uid": ...}. Short-lived by
# design - a reset link is meant to be used within minutes of being emailed.
RESET_MAX_AGE = 30 * 60  # 30 minutes
_reset_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="password-reset")


def make_reset_token(user_id: str) -> str:
    return _reset_serializer.dumps({"uid": user_id})


def read_reset_token(token: str) -> str | None:
    """Returns the user id encoded in a still-valid reset token, or None if
    the token is missing, tampered with, or older than RESET_MAX_AGE."""
    try:
        data = _reset_serializer.loads(token, max_age=RESET_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("uid")
