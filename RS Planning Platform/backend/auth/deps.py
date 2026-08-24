"""FastAPI dependencies that read the signed session cookie (set by
Starlette's SessionMiddleware, configured in the main app.py)."""
import uuid

from fastapi import HTTPException, Request
from sqlalchemy import select

from auth.security import read_remember_token
from db.base import SessionLocal
from db.models.auth import User

REMEMBER_COOKIE = "remember_token"


def _restore_from_remember_cookie(request: Request) -> dict | None:
    """"Remember me on this device": if there's no active session but a valid
    remember-me cookie names a still-active user, re-establish the session
    transparently so the same machine skips the login screen next time."""
    token = request.cookies.get(REMEMBER_COOKIE)
    if not token:
        return None
    raw_user_id = read_remember_token(token)
    if raw_user_id is None:
        return None
    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError:
        return None
    session = SessionLocal()
    try:
        user = session.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
    finally:
        session.close()
    if user is None:
        return None
    user_dict = {"id": str(user.id), "username": user.username, "role": user.role, "is_admin": user.is_admin}
    request.session["user"] = user_dict
    return user_dict


def get_session_user(request: Request) -> dict | None:
    user = request.session.get("user")  # {"id": str, "username": str, "role": str, "is_admin": bool} or None
    if user is not None:
        return user
    return _restore_from_remember_cookie(request)


def require_login(request: Request) -> dict:
    user = get_session_user(request)
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


def require_role(*roles: str):
    def _check(request: Request) -> dict:
        user = require_login(request)
        if user["role"] not in roles:
            raise HTTPException(403, f"Forbidden — requires role in {roles}")
        return user
    return _check


def require_admin(request: Request) -> dict:
    user = require_login(request)
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden — admin only")
    return user
