"""Password hashing and session-cookie helpers.

Uses the `bcrypt` library directly rather than passlib's CryptContext —
passlib 1.7.4 (its last release, unmaintained) breaks against bcrypt>=4.1's
API (it probes `bcrypt.__about__`, removed upstream), so passlib is not used
here despite being the more commonly-reached-for wrapper."""
import os

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Same env var/default as app.py's SessionMiddleware secret_key (each entrypoint
# reads it independently rather than threading it through imports, matching how
# AOP Forecaster's own app.py already does this for its SessionMiddleware).
SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me")

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
