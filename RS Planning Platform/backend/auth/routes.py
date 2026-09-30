import json
import os
import time
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy import func, select

from auth.deps import REMEMBER_COOKIE, require_admin, require_login
from auth.email import send_reset_email, smtp_configured
from auth.rights import RIGHTS, load_revoked, rights_for, save_revoked
from auth.security import REMEMBER_MAX_AGE, hash_password, make_remember_token, make_reset_token, read_reset_token, verify_password
from db.base import SessionLocal
from db.models.auth import ROLES, User

router = APIRouter()


def password_ok(plain, hashed) -> bool:
    """The password as typed, or without spaces at either end (a temporary password copied from the admin page often
    picks up a trailing space - 2026-09-30, "it is not accepting temp password set by admin")."""
    plain = plain or ""
    return verify_password(plain, hashed) or (plain != plain.strip() and verify_password(plain.strip(), hashed))


def find_login_user(session, name):
    """The active account a sign-in name means: its username (exact, else ignoring capitals - accounts were renamed
    Planning01 etc. while people still type planning01), else its email; only when exactly one account matches."""
    active = User.is_active.is_(True)
    u = session.execute(select(User).where(User.username == name, active)).scalar_one_or_none()
    if u is not None:
        return u
    for col in (User.username, User.email) if "@" in name else (User.username,):
        hits = session.execute(select(User).where(func.lower(col) == name.lower(), active)).scalars().all()
        if len(hits) == 1:
            return hits[0]
    return None


@router.post("/login")
def login(request: Request, response: Response, body: dict = Body(...)):
    username, password = (body.get("username") or "").strip(), body.get("password", "")
    session = SessionLocal()
    try:
        user = find_login_user(session, username)   # username or email (2026-09-30)
        if user is None or not password_ok(password, user.password_hash):
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
        if user is None and "@" in username:   # people type their email here (2026-09-30) - same silent answer either way
            user = session.execute(select(User).where(func.lower(User.email) == username.lower(),
                                                      User.is_active.is_(True))).scalars().first()
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
        if u is None or not password_ok(current_password, u.password_hash):
            raise HTTPException(401, "Current password is incorrect")
        u.password_hash = hash_password(new_password)
        u.must_change_password = False
        # Optional: the user registers their OWN recovery email here rather
        # than an admin assigning one - only set if provided, and only
        # overwrites what's on file if they actually typed something (an
        # already-set email from a prior visit isn't cleared by leaving this
        # field blank on a later, voluntary password change).
        if email:
            if email_taken(session, email, u.id):
                raise HTTPException(409, "Another account already has this email - use your own.")
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


@router.get("/rights")
def my_rights(user: dict = Depends(require_login)):
    """The signed-in person's rights right now (Landing checks this before a guarded action) + what each means."""
    return {"rights": rights_for(user["id"]), "labels": RIGHTS}


SIGN_IN_AS_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sign_in_as.log")


def sign_in_as_refusal(me_id, target_id, target_is_admin, target_is_active):
    """Why an admin may not sign in as this person, or None (2026-09-30)."""
    if str(target_id) == str(me_id):
        return "That's you already."
    if target_is_admin:
        return "You can't sign in as another admin."
    if not target_is_active:
        return "This account is switched off - switch it back on first."
    return None


def _log_sign_in_as(event, admin, target):
    os.makedirs(os.path.dirname(SIGN_IN_AS_LOG), exist_ok=True)
    with open(SIGN_IN_AS_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event, "admin": admin, "as": target}) + "\n")


@router.post("/admin/sign-in-as/{user_id}")
def sign_in_as(user_id: str, request: Request, _admin: dict = Depends(require_admin)):
    """An admin opens the suite as this person, without their password, to see or fix their work. Every use is
    logged; the session remembers the admin so "Back to admin" returns without signing in again."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(422, "Invalid user id")
    session = SessionLocal()
    try:
        u = session.get(User, uid)
        by_name = session.get(User, uuid.UUID(_admin["id"])).username   # current name, not the session's copy
    finally:
        session.close()
    if u is None:
        raise HTTPException(404, "User not found")
    refusal = sign_in_as_refusal(_admin["id"], u.id, u.is_admin, u.is_active)
    if refusal:
        raise HTTPException(409, refusal)
    # must_change_password off: the admin isn't forced to pick this person's password for them
    request.session["user"] = {"id": str(u.id), "username": u.username, "role": u.role, "is_admin": False,
                               "must_change_password": False,
                               "signed_in_by": {"id": _admin["id"], "username": by_name}}
    _log_sign_in_as("start", by_name, u.username)
    return request.session["user"]


@router.post("/stop-sign-in-as")
def stop_sign_in_as(request: Request, user: dict = Depends(require_login)):
    """Back to the admin's own session (checked fresh: still an active admin, else signed out)."""
    by = user.get("signed_in_by")
    if not by:
        raise HTTPException(409, "You're not signed in as someone else.")
    session = SessionLocal()
    try:
        a = session.get(User, uuid.UUID(by["id"]))
    finally:
        session.close()
    if a is None or not a.is_admin or not a.is_active:
        request.session.pop("user", None)
        raise HTTPException(403, "Your admin access has ended - sign in again.")
    request.session["user"] = {"id": str(a.id), "username": a.username, "role": a.role, "is_admin": True,
                               "must_change_password": a.must_change_password}
    _log_sign_in_as("stop", a.username, user["username"])
    return request.session["user"]


@router.get("/admin/sign-in-as-log")
def sign_in_as_log(_admin: dict = Depends(require_admin)):
    """The latest 50 Sign in as / Back to admin events, newest first."""
    try:
        with open(SIGN_IN_AS_LOG, encoding="utf-8") as fh:
            lines = fh.readlines()[-50:]
    except OSError:
        return []
    return [json.loads(x) for x in reversed(lines) if x.strip()]


@router.get("/admin/rights")
def all_rights(_admin: dict = Depends(require_admin)):
    return {"labels": RIGHTS, "revoked": load_revoked()}


@router.put("/admin/rights/{user_id}")
def set_rights(user_id: str, body: dict = Body(...), _admin: dict = Depends(require_admin)):
    """body {"revoked": [right, ...]} - the rights this person no longer has (empty list = everything back)."""
    try:
        uid = str(uuid.UUID(user_id))
        return {"revoked": save_revoked(uid, body.get("revoked") or [])}
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/admin/users")
def create_user(body: dict = Body(...), _admin: dict = Depends(require_admin)):
    username, password, role = body.get("username"), body.get("password"), body.get("role")
    username, password = (username or "").strip(), (password or "").strip()
    if not username or not password or role not in ROLES:
        raise HTTPException(422, f"username, password required; role must be one of {ROLES}")
    session = SessionLocal()
    try:
        if session.execute(select(User).where(User.username == username)).scalar_one_or_none():
            raise HTTPException(409, "Username already exists")
        if email_taken(session, body.get("email")):
            raise HTTPException(409, "Another account already has this email - each person needs their own.")
        # Admin-issued accounts start with a password the admin themselves
        # chose (so it's necessarily "known"/shared, unlike a self-service
        # signup) - default True so the new owner is forced to pick their
        # own on first login, unless the caller explicitly opts out.
        must_change = bool(body.get("must_change_password", True))
        u = User(username=username, email=body.get("email") or None, password_hash=hash_password(password.strip()),
                  role=role, is_admin=bool(body.get("is_admin", False)), must_change_password=must_change)
        session.add(u)
        session.commit()
        return {"id": str(u.id), "username": u.username, "email": u.email, "role": u.role,
                "is_admin": u.is_admin, "must_change_password": u.must_change_password}
    finally:
        session.close()


def admin_change_refusal(me_id, target_id, target_is_admin, target_is_active, body, active_admins):
    """Why an admin edit must be refused, or None (lock-out guards, 2026-09-30): an admin can't remove their own admin
    rights or switch off their own account, and the platform is never left without an active admin."""
    drops_admin = "is_admin" in body and not body["is_admin"]
    switches_off = "is_active" in body and not body["is_active"]
    if str(target_id) == str(me_id) and (drops_admin or switches_off):
        return "You can't remove your own admin rights or switch off your own account - ask another admin."
    if target_is_admin and target_is_active and (drops_admin or switches_off) and active_admins <= 1:
        return "This is the last active admin - make someone else an admin first."
    return None


@router.get("/admin/email-status")
def email_status(_admin: dict = Depends(require_admin)):
    """Whether forgot-password emails can be sent (SMTP settings present) - never the settings themselves."""
    return {"configured": smtp_configured()}


def email_taken(session, email, except_id=None):
    """Another account already has this email (ignoring case)? Emails are a sign-in name too, so one per person."""
    if not email:
        return False
    q = select(User.id).where(func.lower(User.email) == email.strip().lower())
    if except_id is not None:
        q = q.where(User.id != except_id)
    return session.execute(q).first() is not None


def username_refusal(new, taken):
    """Why a rename must be refused, or None (2026-09-30). `taken` = the other accounts' usernames; compared ignoring
    case so "Admin" and "admin" can't both exist and be mixed up at sign-in."""
    if not new:
        return "The username can't be blank."
    if len(new) > 64:
        return "Keep the username to 64 characters or fewer."
    if new.lower() in {t.lower() for t in taken}:
        return f'"{new}" is already someone\'s username.'
    return None


@router.patch("/admin/users/{user_id}")
def update_user(user_id: str, request: Request, body: dict = Body(...), _admin: dict = Depends(require_admin)):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(422, "Invalid user id")
    session = SessionLocal()
    try:
        user = session.get(User, uid)
        if user is None:
            raise HTTPException(404, "User not found")
        admins = session.execute(select(func.count()).select_from(User).where(User.is_admin.is_(True),
                                                                               User.is_active.is_(True))).scalar()
        refusal = admin_change_refusal(_admin["id"], user.id, user.is_admin, user.is_active, body, admins)
        if refusal:
            raise HTTPException(409, refusal)
        if "username" in body:
            new = str(body["username"] or "").strip()
            others = session.execute(select(User.username).where(User.id != user.id)).scalars().all()
            refusal = username_refusal(new, others)
            if refusal:
                raise HTTPException(422, refusal)
            user.username = new
        if "email" in body:
            if email_taken(session, body["email"], user.id):
                raise HTTPException(409, "Another account already has this email - each person needs their own.")
            user.email = (body["email"] or "").strip() or None
        if "role" in body:
            if body["role"] not in ROLES:
                raise HTTPException(422, f"role must be one of {ROLES}")
            user.role = body["role"]
        if "is_admin" in body:
            user.is_admin = bool(body["is_admin"])
        if "is_active" in body:
            user.is_active = bool(body["is_active"])
        if body.get("password"):
            if len(body["password"].strip()) < 8:
                raise HTTPException(422, "The password needs at least 8 characters (spaces at the ends don't count).")
            user.password_hash = hash_password(body["password"].strip())   # admin-set: no stray spaces
            # Same reasoning as creation: an admin-reset password is a new
            # known/shared value, so force a change again unless told not to.
            user.must_change_password = bool(body.get("must_change_password", True))
        elif "must_change_password" in body:
            user.must_change_password = bool(body["must_change_password"])
        session.commit()
        if str(user.id) == _admin["id"]:   # renaming yourself: this session shows the new name at once
            request.session["user"] = {**_admin, "username": user.username}
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
