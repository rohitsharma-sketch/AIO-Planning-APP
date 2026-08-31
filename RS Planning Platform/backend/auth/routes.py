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
            "must_change_password": user.must_change_password,
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


@router.post("/change-password")
def change_password(request: Request, body: dict = Body(...), user: dict = Depends(require_login)):
    """For an ALREADY-LOGGED-IN user (session cookie), unlike /reset-password
    which is for a logged-OUT user with an emailed token. Requires the
    current password so a hijacked/left-open session can't be used to lock
    the real owner out. Clears must_change_password so the forced
    change-password gate (see login's response) only fires once."""
    current_password, new_password = body.get("current_password"), body.get("new_password")
    email = (body.get("email") or "").strip() or None
    if not current_password or not new_password:
        raise HTTPException(422, "current_password and new_password required")
    session = SessionLocal()
    try:
        u = session.get(User, uuid.UUID(user["id"]))
        if u is None or not verify_password(current_password, u.password_hash):
            raise HTTPException(401, "Current password is incorrect")
        u.password_hash = hash_password(new_password)
        u.must_change_password = False
        # Optional: the user registers their OWN recovery email here rather
        # than an admin assigning one - only set if provided, and only
        # overwrites what's on file if they actually typed something (an
        # already-set email from a prior visit isn't cleared by leaving this
        # field blank on a later, voluntary password change).
        if email:
            u.email = email
        session.commit()
        request.session["user"] = {
            "id": str(u.id), "username": u.username, "role": u.role, "is_admin": u.is_admin,
            "must_change_password": False,
        }
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
        # Admin-issued accounts start with a password the admin themselves
        # chose (so it's necessarily "known"/shared, unlike a self-service
        # signup) - default True so the new owner is forced to pick their
        # own on first login, unless the caller explicitly opts out.
        must_change = bool(body.get("must_change_password", True))
        u = User(username=username, email=body.get("email") or None, password_hash=hash_password(password),
                  role=role, is_admin=bool(body.get("is_admin", False)), must_change_password=must_change)
        session.add(u)
        session.commit()
        return {"id": str(u.id), "username": u.username, "email": u.email, "role": u.role,
                "is_admin": u.is_admin, "must_change_password": u.must_change_password}
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
            # Same reasoning as creation: an admin-reset password is a new
            # known/shared value, so force a change again unless told not to.
            user.must_change_password = bool(body.get("must_change_password", True))
        elif "must_change_password" in body:
            user.must_change_password = bool(body["must_change_password"])
        session.commit()
        return {"id": str(user.id), "username": user.username, "email": user.email,
                "role": user.role, "is_admin": user.is_admin, "is_active": user.is_active,
                "must_change_password": user.must_change_password}
    finally:
        session.close()


@router.get("/admin/users")
def list_users(_admin: dict = Depends(require_admin)):
    session = SessionLocal()
    try:
        users = session.execute(select(User)).scalars().all()
        return [{"id": str(u.id), "username": u.username, "email": u.email, "role": u.role, "is_admin": u.is_admin,
                 "is_active": u.is_active, "must_change_password": u.must_change_password} for u in users]
    finally:
        session.close()
