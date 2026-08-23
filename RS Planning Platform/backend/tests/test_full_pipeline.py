"""The chain exercised repeatedly by hand this session, now through the
unified app + full workflow gate. Requires the unified app on :8010, the
standalone AOP Forecaster on :8000 (SalesPlan's sync-from-aop-forecaster
calls out to it directly — see department_plan.py's AOP_FORECASTER_URL),
and the planner1/buyer1/reviewer1/approver1 users seeded this session.

Route note: AOP's own routes carry an internal `/api/...` prefix, so
mounted under `/api/aop` they land at `/api/aop/api/...` — verified live,
not copied blind from the plan draft (which omitted the inner `/api`)."""
import httpx
import pytest

BASE = "http://127.0.0.1:8010"

CREDS = {
    "planner": ("planner1", "PlannerPass123!"),
    "buyer": ("buyer1", "BuyerPass123!"),
    "reviewer": ("reviewer1", "ReviewerPass123!"),
    "approver": ("approver1", "ApproverPass123!"),
}


def _login(role):
    username, password = CREDS[role]
    # httpx's default 5s read timeout is too tight for /api/run, which
    # executes the real forecast engine — bump it (discovered by a
    # ReadTimeout on this test's second live run, not a functional bug).
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def planner_client():
    return _login("planner")


@pytest.fixture
def buyer_client():
    return _login("buyer")


@pytest.fixture
def reviewer_client():
    return _login("reviewer")


@pytest.fixture
def approver_client():
    return _login("approver")


def test_division_aop_summary_404s_with_no_approved_cycle(planner_client):
    # Fresh state assumption: confirmed via psql before this test file was
    # written that workflow.plan_cycles has 0 rows. Must run before
    # test_full_workflow_to_salesplan, which approves one.
    r = planner_client.get("/api/aop/api/config/division-aop-summary")
    assert r.status_code == 404


def test_full_workflow_to_salesplan(planner_client, buyer_client, reviewer_client, approver_client):
    # 1. Planner builds a run
    r = planner_client.post("/api/aop/api/config/session-from-db")
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]

    r = planner_client.post(f"/api/aop/api/run/{session_id}", json={})
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    assert run_id is not None

    # 2. Planner starts a plan cycle and submits it
    r = planner_client.post("/api/aop/plan-cycles", json={"run_id": run_id})
    assert r.status_code == 200, r.text
    cycle_id = r.json()["id"]
    assert r.json()["status"] == "draft"

    r = planner_client.post(f"/api/aop/plan-cycles/{cycle_id}/submit")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_buyer"

    # 3. Buyer submits onward (without editing, for this test's simplicity)
    r = buyer_client.post(f"/api/aop/plan-cycles/{cycle_id}/submit")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_review"

    # 4. Reviewer approves
    r = reviewer_client.post(f"/api/aop/plan-cycles/{cycle_id}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_approval"

    # 5. Approver approves
    r = approver_client.post(f"/api/aop/plan-cycles/{cycle_id}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    # 6. division-aop-summary now serves this run
    r = planner_client.get("/api/aop/api/config/division-aop-summary")
    assert r.status_code == 200, r.text
    assert r.json()["run_id"] == run_id

    # 7. SalesPlan pulls it (via its own out-of-process call to :8000 —
    # requires the standalone AOP Forecaster server running there too)
    r = planner_client.post("/api/planning/department-plan/sync-from-aop-forecaster")
    assert r.status_code == 200, r.text
    assert r.json()["run_id"] == run_id
