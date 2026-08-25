import uuid

import pytest

from sqlalchemy import select

from auth.security import hash_password
from db.base import SessionLocal
from db.models.auth import User
from db.models.engine import ForecastRun
from db.models.workflow import PlanCycle, PlanCycleTransition
from workflow.service import TRANSITIONS, create_cycle, transition
from workflow.service import latest_approved_cycle


@pytest.fixture
def fake_run():
    """A minimal ForecastRun row to attach cycles to — doesn't need real
    forecast_results, just a valid run_id to reference."""
    import datetime
    session = SessionLocal()
    run = ForecastRun(input_snapshot_at=datetime.datetime.now(datetime.timezone.utc), status="success")
    session.add(run)
    session.commit()
    session.refresh(run)
    run_id = run.run_id
    yield run_id
    session.delete(session.get(ForecastRun, run_id))
    session.commit()
    session.close()


@pytest.fixture
def role_users():
    """One throwaway auth.users row per role — plan_cycles.created_by and
    plan_cycle_transitions.actor_id are real foreign keys, so tests need
    real rows to reference, not just role-shaped dicts."""
    session = SessionLocal()
    users = {}
    for role in ("planner", "buyer", "reviewer", "approver"):
        u = User(username=f"{role}_{uuid.uuid4().hex[:8]}", password_hash=hash_password("x"), role=role)
        session.add(u)
        session.commit()
        session.refresh(u)
        users[role] = {"id": str(u.id), "role": role}
    yield users
    # Tests using this fixture create plan_cycles (created_by) and
    # plan_cycle_transitions (actor_id) referencing these users — delete
    # those first, or the FK constraint (deliberately, correctly) blocks
    # deleting a user with workflow history.
    user_ids = [uuid.UUID(u["id"]) for u in users.values()]
    cycle_ids = [
        c.id for c in session.execute(select(PlanCycle).where(PlanCycle.created_by.in_(user_ids))).scalars().all()
    ]
    if cycle_ids:
        session.execute(
            PlanCycleTransition.__table__.delete().where(PlanCycleTransition.plan_cycle_id.in_(cycle_ids))
        )
        session.execute(PlanCycle.__table__.delete().where(PlanCycle.id.in_(cycle_ids)))
    for u in users.values():
        session.delete(session.get(User, uuid.UUID(u["id"])))
    session.commit()
    session.close()


def test_happy_path_reaches_approved(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])
    assert cycle.status == "draft"

    cycle = transition(session, cycle.id, "submit", role_users["planner"])
    assert cycle.status == "pending_buyer"

    cycle = transition(session, cycle.id, "submit", role_users["buyer"])
    assert cycle.status == "pending_review"

    cycle = transition(session, cycle.id, "approve", role_users["reviewer"])
    assert cycle.status == "pending_approval"

    cycle = transition(session, cycle.id, "approve", role_users["approver"])
    assert cycle.status == "approved"
    session.close()


def test_transition_table_is_reflexive_only_forward():
    # No status transitions to itself, and 'approved' has no outgoing transitions
    for (frm, action), (to, role) in TRANSITIONS.items():
        assert frm != to
    assert not any(frm == "approved" for frm, _ in TRANSITIONS)


def test_wrong_role_raises_permission_error(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])
    with pytest.raises(PermissionError):
        transition(session, cycle.id, "submit", role_users["buyer"])  # only planner may submit from draft
    session.close()


def test_invalid_action_for_status_raises_value_error(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])
    with pytest.raises(ValueError):
        transition(session, cycle.id, "approve", role_users["reviewer"])  # can't approve straight from draft
    session.close()


def test_latest_approved_cycle_returns_none_when_nothing_approved(fake_run, role_users):
    session = SessionLocal()
    create_cycle(session, fake_run, role_users["planner"])  # stays in draft
    assert latest_approved_cycle(session) is None
    session.close()


def test_latest_approved_cycle_carries_buyer_adjusted_totals(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])
    cycle = transition(session, cycle.id, "submit", role_users["planner"])
    cycle.buyer_adjusted_totals = {"mens": 100.0, "ladies": 200.0, "kids": 50.0}
    session.commit()
    cycle = transition(session, cycle.id, "submit", role_users["buyer"])
    cycle = transition(session, cycle.id, "approve", role_users["reviewer"])
    cycle = transition(session, cycle.id, "approve", role_users["approver"])

    found = latest_approved_cycle(session)
    assert found is not None
    assert found.id == cycle.id
    assert found.buyer_adjusted_totals == {"mens": 100.0, "ladies": 200.0, "kids": 50.0}
    session.close()
