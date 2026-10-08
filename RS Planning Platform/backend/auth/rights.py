"""Rights an admin can switch off per person (Users & access page, 2026-09-30).

Everyone has every right unless an admin revoked it; admins always have all of them (they could grant them back
anyway). Revokes live in data/user_rights.json ({user id: [revoked right, ...]}, local state, gitignored) and are
read on every check, so a revoke applies at once - not at the person's next sign-in. Landing enforces them
(landing_server.py GUARDED) because every browser request to every app passes through it."""
import json
import os
import uuid

from sqlalchemy import select

from db.base import SessionLocal
from db.models.auth import User

RIGHTS = {   # key -> what the admin sees
    "servers": "Start / stop all servers (Master Switch)",
    "data_sync": "Sync the data lake (Sync now, Sync into database)",
    "aop_publish": "Promote AOP to Planning / unlock it",
    "calendar_reindex": "Run Reindex (Calendar)",
    "realigner_run": "Run the Re-Aligner (Run, Re-phase & run)",
    "suite_theme": "Change the colour theme for everyone",
    "buyer_push": "Send the Buyer's plan to Sales Plan (Save in BIS)",   # audit 2026-10-07: one POST replaces everyone's
    "mrp_master": "Import a new MRP master (Sales Plan, MRP Re-apportionment)",   # user 2026-10-08: replaces it for everyone
}
_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "user_rights.json")


def load_revoked(path=None) -> dict:
    try:
        with open(path or _FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_revoked(user_id: str, revoked, path=None) -> list:
    path = path or _FILE
    unknown = set(revoked) - set(RIGHTS)
    if unknown:
        raise ValueError(f"Unknown right(s): {', '.join(sorted(unknown))}")
    allr = load_revoked(path)
    allr[user_id] = sorted(set(revoked))
    if not allr[user_id]:
        del allr[user_id]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(allr, fh, indent=1)
    os.replace(path + ".tmp", path)
    return allr.get(user_id, [])


def effective(is_admin: bool, is_active: bool, revoked) -> list:
    if not is_active:
        return []
    return list(RIGHTS) if is_admin else [r for r in RIGHTS if r not in set(revoked)]


def rights_for(user_id: str) -> list:
    """This person's rights now - admin / switched-off read from the database, not the (possibly old) session."""
    session = SessionLocal()
    try:
        u = session.execute(select(User).where(User.id == uuid.UUID(user_id))).scalar_one_or_none()
    finally:
        session.close()
    return [] if u is None else effective(u.is_admin, u.is_active, load_revoked().get(user_id, []))
