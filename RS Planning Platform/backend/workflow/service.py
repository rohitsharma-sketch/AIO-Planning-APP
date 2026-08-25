"""The Planner -> Buyer -> Reviewer -> Approver state machine.
See docs/superpowers/specs/2026-08-22-...-design.md for the full table."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.workflow import PlanCycle, PlanCycleTransition

# (current_status, action) -> (next_status, role_required)
TRANSITIONS = {
    ("draft", "submit"):            ("pending_buyer", "planner"),
    ("pending_buyer", "submit"):    ("pending_review", "buyer"),
    ("pending_review", "approve"):  ("pending_approval", "reviewer"),
    ("pending_review", "reject"):   ("draft", "reviewer"),
    ("pending_approval", "approve"): ("approved", "approver"),
    ("pending_approval", "reject"): ("draft", "approver"),
}


def create_cycle(session: Session, run_id: uuid.UUID, actor: dict) -> PlanCycle:
    if actor["role"] != "planner":
        raise PermissionError("Only planner may start a plan cycle")
    cycle = PlanCycle(current_run_id=run_id, created_by=uuid.UUID(actor["id"]))
    session.add(cycle)
    session.commit()
    session.refresh(cycle)
    return cycle


def set_current_run(session: Session, cycle_id: uuid.UUID, run_id: uuid.UUID, actor: dict) -> PlanCycle:
    """Buyer editing + re-running while pending_buyer — updates the cycle's
    current run without a status transition (normal iteration, not a
    workflow event)."""
    cycle = session.get(PlanCycle, cycle_id)
    if cycle is None:
        raise LookupError("Plan cycle not found")
    if cycle.status != "pending_buyer" or actor["role"] != "buyer":
        raise PermissionError("Only buyer may update the run while pending_buyer")
    cycle.current_run_id = run_id
    session.commit()
    session.refresh(cycle)
    return cycle


def transition(session: Session, cycle_id: uuid.UUID, action: str, actor: dict, comment: str | None = None) -> PlanCycle:
    cycle = session.get(PlanCycle, cycle_id)
    if cycle is None:
        raise LookupError("Plan cycle not found")
    key = (cycle.status, action)
    if key not in TRANSITIONS:
        raise ValueError(f"Cannot '{action}' a cycle in status '{cycle.status}'")
    next_status, required_role = TRANSITIONS[key]
    if actor["role"] != required_role:
        raise PermissionError(f"'{action}' from '{cycle.status}' requires role '{required_role}', not '{actor['role']}'")

    session.add(PlanCycleTransition(
        plan_cycle_id=cycle.id, from_status=cycle.status, to_status=next_status,
        actor_id=uuid.UUID(actor["id"]), actor_role=actor["role"], comment=comment, run_id=cycle.current_run_id,
    ))
    cycle.status = next_status
    session.commit()
    session.refresh(cycle)
    return cycle


def latest_approved_run_id(session: Session) -> uuid.UUID | None:
    cycle = session.execute(
        select(PlanCycle).where(PlanCycle.status == "approved").order_by(PlanCycle.updated_at.desc())
    ).scalars().first()
    return cycle.current_run_id if cycle else None


def latest_approved_cycle(session: Session) -> PlanCycle | None:
    """Same lookup as latest_approved_run_id, but returns the cycle itself —
    division_aop_summary() needs buyer_adjusted_totals off it, not just the run id."""
    return session.execute(
        select(PlanCycle).where(PlanCycle.status == "approved").order_by(PlanCycle.updated_at.desc())
    ).scalars().first()
