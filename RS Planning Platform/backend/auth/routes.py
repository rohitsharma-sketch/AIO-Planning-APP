from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import select

from auth.deps import require_admin, require_login
from auth.security import hash_password, verify_password
from db.base import SessionLocal
from db.models.auth import ROLES, User

router = APIRouter()


@router.post("/login")
def login(request: Request, body: dict = Body(...)):
    username, password = body.get("username", ""), body.get("password", "")
    session = SessionLocal()
    try:
        user = session.execute(select(User).where(User.username == username, User.is_active.is_(True))).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(401, "Invalid credentials")
        request.session["user"] = {
            "id": str(user.id), "username": user.username, "role": user.role, "is_admin": user.is_admin,
        }
        return request.session["user"]
    finally:
        session.close()


@router.post("/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return {"ok": True}


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
        u = User(username=username, password_hash=hash_password(password), role=role, is_admin=bool(body.get("is_admin", False)))
        session.add(u)
        session.commit()
        return {"id": str(u.id), "username": u.username, "role": u.role, "is_admin": u.is_admin}
    finally:
        session.close()


@router.get("/admin/users")
def list_users(_admin: dict = Depends(require_admin)):
    session = SessionLocal()
    try:
        users = session.execute(select(User)).scalars().all()
        return [{"id": str(u.id), "username": u.username, "role": u.role, "is_admin": u.is_admin, "is_active": u.is_active} for u in users]
    finally:
        session.close()
