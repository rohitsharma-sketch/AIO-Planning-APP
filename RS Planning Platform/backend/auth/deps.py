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
    user_dict = {"id": str(user.id), "username": user.username, "role": user.role, "is_admin": user.is_admin,
                 "must_change_password": user.must_change_password}
    request.session["user"] = user_dict
    return user_dict


def _current(user: dict) -> dict | None:
    """The session's user as the database has them NOW - None if deleted or switched off; role / admin refreshed
    (audit 2026-10-06: the signed cookie was trusted as-is, so a switched-off leaver kept access and a demoted admin
    stayed admin until they signed out). One primary-key lookup per request."""
    try:
        user_id = uuid.UUID(str(user.get("id")))
    except ValueError:
        return None
    session = SessionLocal()
    try:
        u = session.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
    finally:
        session.close()
    if u is None:
        return None
    if user.get("signed_in_by"):   # an admin's sign-in-as: no admin rights, never forced to change their password
        return {**user, "username": u.username, "role": u.role}
    return {**user, "username": u.username, "role": u.role, "is_admin": u.is_admin,
            "must_change_password": u.must_change_password}


def get_session_user(request: Request) -> dict | None:
    user = request.session.get("user")  # {"id": str, "username": str, "role": str, "is_admin": bool} or None
    if user is not None:
        fresh = _current(user)
        if fresh is None:
            request.session.pop("user", None)
            return None
        if fresh != user:
            request.session["user"] = fresh
        return fresh
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
