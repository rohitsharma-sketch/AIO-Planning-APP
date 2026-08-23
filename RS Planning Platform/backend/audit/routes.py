from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from auth.deps import require_login
from db.base import SessionLocal
from db.models.audit import DataChange

router = APIRouter()


def _require_admin_or_approver(request: Request) -> dict:
    user = require_login(request)
    if not (user.get("is_admin") or user["role"] == "approver"):
        raise HTTPException(403, "Forbidden — admin or approver only")
    return user


@router.get("/data-changes")
def list_data_changes(table: str | None = None, limit: int = 200, user: dict = Depends(_require_admin_or_approver)):
    session = SessionLocal()
    try:
        stmt = select(DataChange).order_by(DataChange.changed_at.desc()).limit(min(limit, 1000))
        if table:
            stmt = stmt.where(DataChange.table_name == table)
        rows = session.execute(stmt).scalars().all()
        return [
            {"id": r.id, "table": r.table_name, "record_key": r.record_key, "old": r.old_value, "new": r.new_value,
             "actor_role": r.actor_role, "plan_cycle_id": str(r.plan_cycle_id) if r.plan_cycle_id else None,
             "changed_at": r.changed_at.isoformat()}
            for r in rows
        ]
    finally:
        session.close()
