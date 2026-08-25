import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select

from auth.deps import require_login
from db.base import SessionLocal
from db.models.workflow import PlanCycle, PlanCycleTransition
from workflow.service import create_cycle, set_buyer_totals, set_current_run, transition

router = APIRouter()


@router.post("")
def create(body: dict = Body(...), user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        try:
            cycle = create_cycle(session, uuid.UUID(body["run_id"]), user)
        except PermissionError as e:
            raise HTTPException(403, str(e))
        return {"id": str(cycle.id), "status": cycle.status, "current_run_id": str(cycle.current_run_id)}
    finally:
        session.close()


@router.put("/{cycle_id}/current-run")
def update_run(cycle_id: str, body: dict = Body(...), user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        try:
            cycle = set_current_run(session, uuid.UUID(cycle_id), uuid.UUID(body["run_id"]), user)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except PermissionError as e:
            raise HTTPException(403, str(e))
        return {"id": str(cycle.id), "status": cycle.status, "current_run_id": str(cycle.current_run_id)}
    finally:
        session.close()


@router.put("/{cycle_id}/buyer-totals")
def update_buyer_totals(cycle_id: str, body: dict = Body(...), user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        try:
            cycle = set_buyer_totals(session, uuid.UUID(cycle_id), body.get("totals") or {}, user)
        except LookupError as e:
            raise HTTPException(404, str(e))
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {"id": str(cycle.id), "status": cycle.status, "buyer_adjusted_totals": cycle.buyer_adjusted_totals}
    finally:
        session.close()


@router.post("/{cycle_id}/{action}")
def do_transition(cycle_id: str, action: str, body: dict = Body(default={}), user: dict = Depends(require_login)):
    if action not in ("submit", "approve", "reject"):
        raise HTTPException(404, "Unknown action")
    session = SessionLocal()
    try:
        try:
            cycle = transition(session, uuid.UUID(cycle_id), action, user, comment=body.get("comment"))
        except LookupError as e:
            raise HTTPException(404, str(e))
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"id": str(cycle.id), "status": cycle.status, "current_run_id": str(cycle.current_run_id) if cycle.current_run_id else None}
    finally:
        session.close()


@router.get("/{cycle_id}")
def get_cycle(cycle_id: str, user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        cycle = session.get(PlanCycle, uuid.UUID(cycle_id))
        if cycle is None:
            raise HTTPException(404, "Plan cycle not found")
        transitions = session.execute(
            select(PlanCycleTransition).where(PlanCycleTransition.plan_cycle_id == cycle.id).order_by(PlanCycleTransition.created_at)
        ).scalars().all()
        return {
            "id": str(cycle.id), "status": cycle.status,
            "current_run_id": str(cycle.current_run_id) if cycle.current_run_id else None,
            "created_at": cycle.created_at.isoformat(),
            "transitions": [
                {"from": t.from_status, "to": t.to_status, "actor_role": t.actor_role,
                 "comment": t.comment, "at": t.created_at.isoformat()}
                for t in transitions
            ],
        }
    finally:
        session.close()


@router.get("")
def list_cycles(user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        cycles = session.execute(select(PlanCycle).order_by(PlanCycle.created_at.desc())).scalars().all()
        return [{"id": str(c.id), "status": c.status, "created_at": c.created_at.isoformat()} for c in cycles]
    finally:
        session.close()
