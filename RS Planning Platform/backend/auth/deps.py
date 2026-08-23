"""FastAPI dependencies that read the signed session cookie (set by
Starlette's SessionMiddleware, configured in the main app.py)."""
from fastapi import HTTPException, Request


def get_session_user(request: Request) -> dict | None:
    return request.session.get("user")  # {"id": str, "username": str, "role": str, "is_admin": bool} or None


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
