import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import select

from auth.deps import REMEMBER_COOKIE, require_admin, require_login
from auth.email import send_reset_email, smtp_configured
from auth.security import REMEMBER_MAX_AGE, hash_password, make_remember_token, make_reset_token, read_reset_token, verify_password
from db.base import SessionLocal
from db.models.auth import ROLES, User

router = APIRouter()


@router.post("/login")
def login(request: Request, response: Response, body: dict = Body(...)):
    username, password = body.get("username", ""), body.get("password", "")
    session = SessionLocal()
    try:
        user = session.execute(select(User).where(User.username == username, User.is_active.is_(True))).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(401, "Invalid credentials")
        request.session["user"] = {
            "id": str(user.id), "username": user.username, "role": user.role, "is_admin": user.is_admin,
        }
        # "Remember me on this device" — a separate long-lived cookie so this
        # machine skips the login screen on return visits even after the
        # (session-only) login cookie itself has expired. Opt-in: unchecked,
        # the session still ends when the browser closes, same as before.
        if body.get("remember"):
            response.set_cookie(
                REMEMBER_COOKIE, make_remember_token(str(user.id)),
                max_age=REMEMBER_MAX_AGE, httponly=True, samesite="lax", path="/",
            )
        return request.session["user"]
    finally:
        session.close()


@router.post("/logout")
def logout(request: Request, response: Response):
    request.session.pop("user", None)
    response.delete_cookie(REMEMBER_COOKIE, path="/")
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(body: dict = Body(...)):
    username = (body.get("username") or "").strip()
    session = SessionLocal()
    try:
        user = session.execute(select(User).where(User.username == username, User.is_active.is_(True))).scalar_one_or_none()
        # Same {"ok": True} whether or not the account/email exists — this
        # endpoint must not let a caller enumerate valid usernames.
        if user is None or not user.email:
            return {"ok": True}
        if not smtp_configured():
            raise HTTPException(503, "Password reset email is not configured yet (SMTP_HOST/SMTP_USER/SMTP_PASSWORD) — contact an admin.")
        send_reset_email(user.email, user.username, make_reset_token(str(user.id)))
        return {"ok": True}
    finally:
        session.close()


@router.post("/reset-password")
def reset_password(body: dict = Body(...)):
    token, new_password = body.get("token"), body.get("new_password")
    if not token or not new_password:
        raise HTTPException(422, "token and new_password required")
    raw_user_id = read_reset_token(token)
    if raw_user_id is None:
        raise HTTPException(400, "This reset link is invalid or has expired — request a new one.")
    try:
        user_id = uuid.UUID(raw_user_id)
    except ValueError:
        raise HTTPException(400, "This reset link is invalid or has expired — request a new one.")
    session = SessionLocal()
    try:
        user = session.execute(select(User).where(User.id == user_id, User.is_active.is_(True))).scalar_one_or_none()
        if user is None:
            raise HTTPException(400, "This reset link is invalid or has expired — request a new one.")
        user.password_hash = hash_password(new_password)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.get("/me")
def me(user: dict = Depends(require_login)):
    return user


@router.post("/admin/users")
def create_user(body: dict = Body(...), _admin: dict = Depends(require_admin)):
    username, password, role = body.get("username"), body.get("password"), body.get("role")
    if not username or not password or role not in ROLES:
        raise HTTPException(422, f"username, password required; role must be one of {ROLES}")
    session = SessionLocal()
    try:
        if session.execute(select(User).where(User.username == username)).scalar_one_or_none():
            raise HTTPException(409, "Username already exists")
        u = User(username=username, email=body.get("email") or None, password_hash=hash_password(password),
                  role=role, is_admin=bool(body.get("is_admin", False)))
        session.add(u)
        session.commit()
        return {"id": str(u.id), "username": u.username, "email": u.email, "role": u.role, "is_admin": u.is_admin}
    finally:
        session.close()


@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, body: dict = Body(...), _admin: dict = Depends(require_admin)):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(422, "Invalid user id")
    session = SessionLocal()
    try:
        user = session.get(User, uid)
        if user is None:
            raise HTTPException(404, "User not found")
        if "email" in body:
            user.email = body["email"] or None
        if "role" in body:
            if body["role"] not in ROLES:
                raise HTTPException(422, f"role must be one of {ROLES}")
            user.role = body["role"]
        if "is_admin" in body:
            user.is_admin = bool(body["is_admin"])
        if "is_active" in body:
            user.is_active = bool(body["is_active"])
        if body.get("password"):
            user.password_hash = hash_password(body["password"])
        session.commit()
        return {"id": str(user.id), "username": user.username, "email": user.email,
                "role": user.role, "is_admin": user.is_admin, "is_active": user.is_active}
    finally:
        session.close()


@router.get("/admin/users")
def list_users(_admin: dict = Depends(require_admin)):
    session = SessionLocal()
    try:
        users = session.execute(select(User)).scalars().all()
        return [{"id": str(u.id), "username": u.username, "email": u.email, "role": u.role, "is_admin": u.is_admin, "is_active": u.is_active} for u in users]
    finally:
        session.close()
