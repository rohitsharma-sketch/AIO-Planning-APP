# Buyer Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing (built but UI-less) Planner→Buyer→Reviewer→Approver plan-cycle workflow actually operable end to end, wire Buyer's Input Sheet in as the buyer-adjustment step, and give the Landing page a live view of where each cycle is in that pipeline — matching the confirmed flow: **Calendar → AOP Forecaster → Buyer's Input → Sales Plan**.

**Architecture:** No new services. `PlanCycle`'s existing state machine (`workflow/service.py`) is unchanged. Adds one column (`buyer_adjusted_totals`) so a buyer's edited division totals become the numbers Sales Plan eventually syncs; two new tiny read endpoints on AOP Forecaster so a planner can pick a run and a buyer can see one; one new plain-HTML page (`plan-cycles.html`) covering the planner/reviewer/approver steps; one new tab in Buyer's Input Sheet's existing app for the buyer step; and a live-status rewrite of Landing's "Data Sync & Flow" card plus drag-and-drop reordering of its module cards.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend, Postgres-backed), pytest against the real `rs_planning` Postgres database (matching `tests/test_workflow.py`'s existing pattern — no mocking), plain HTML/vanilla JS for `plan-cycles.html` and the Landing page (no build step, matching `static/login.html` and `Landing/index.html`), Buyer's Input Sheet's existing vanilla-JS/Flask stack.

**Spec:** `docs/superpowers/specs/2026-08-24-buyer-review-workflow-design.md`

## Global Constraints

- `buyer_adjusted_totals` shape: `{"mens": <float>, "ladies": <float>, "kids": <float>}`, Rs Lakhs — same unit and division codes `division-aop-summary` already returns.
- The `PlanCycle` transition table (`workflow/service.py`'s `TRANSITIONS`) is not modified — it's already correct and tested.
- No new backend framework/build step for `plan-cycles.html` — plain HTML + vanilla JS served via `FileResponse`, exactly like `static/login.html`.
- Buyer's Input Sheet's new tab talks to the platform (port 8010) cross-origin with `credentials: 'include'` — it does not get mounted as a platform module.
- Drag-and-drop card order persists via `localStorage` only (a personal browser preference, not synced across devices/users).

---

## File Structure

```
RS Planning Platform/backend/
  db/models/workflow.py                    # MODIFY: + buyer_adjusted_totals column
  alembic/... (lives under Tentative AOP Forecaster/alembic/ — see Task 1)
  workflow/service.py                      # MODIFY: + set_buyer_totals(), latest_approved_cycle()
  workflow/routes.py                       # MODIFY: + PUT /plan-cycles/{id}/buyer-totals
  tests/test_workflow.py                   # MODIFY: + buyer-totals tests
  static/plan-cycles.html                  # CREATE: planner/reviewer/approver page
  app.py                                   # MODIFY: + GET /plan-cycles route

Tentative AOP Forecaster/
  app.py                                   # MODIFY: division_aop_summary() prefers buyer
                                            #   totals; + GET /api/config/recent-runs;
                                            #   + GET /api/config/runs/{run_id}/division-totals
  alembic/versions/<rev>_add_buyer_adjusted_totals.py  # CREATE

Buyer's Input Sheet/
  otb-plan-app.html                        # MODIFY: + "AOP Review" tab

Landing/
  index.html                               # MODIFY: live plan-cycle status in the
                                            #   "Data Sync & Flow" card; drag-and-drop
                                            #   card reordering
```

---

### Task 1: `buyer_adjusted_totals` column + migration + `latest_approved_cycle()`

**Files:**
- Modify: `RS Planning Platform/backend/db/models/workflow.py`
- Create: `Tentative AOP Forecaster/alembic/versions/<new>_add_buyer_adjusted_totals.py`
- Modify: `RS Planning Platform/backend/workflow/service.py`
- Test: `RS Planning Platform/backend/tests/test_workflow.py`

**Interfaces:**
- Produces: `PlanCycle.buyer_adjusted_totals: dict | None` (JSON column). `workflow.service.latest_approved_cycle(session: Session) -> PlanCycle | None`.

- [ ] **Step 1: Write the failing test**

Add to `RS Planning Platform/backend/tests/test_workflow.py`:

```python
from workflow.service import latest_approved_cycle


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "RS Planning Platform/backend" && python -m pytest tests/test_workflow.py -k latest_approved_cycle -v`
Expected: FAIL with `ImportError: cannot import name 'latest_approved_cycle'`

- [ ] **Step 3: Add the column to the model**

In `RS Planning Platform/backend/db/models/workflow.py`, the model actually lives in `Tentative AOP Forecaster/db/models/workflow.py` (imports resolve there — confirm by checking which file `from db.models.workflow import PlanCycle` in `workflow/service.py` actually resolves to via `sys.path`; it is `Tentative AOP Forecaster/db/models/workflow.py`, add the column there):

```python
from sqlalchemy import JSON  # add to the existing sqlalchemy import line

class PlanCycle(Base):
    __tablename__ = "plan_cycles"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    current_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engine.forecast_runs.run_id"), nullable=True
    )
    buyer_adjusted_totals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Write and apply the migration**

```bash
cd "Tentative AOP Forecaster" && python -m alembic revision -m "add buyer_adjusted_totals to plan_cycles"
```

Edit the generated file (`down_revision = '1968caf074da'` — confirm this is still the current head with `python -m alembic heads` first; if a newer migration has landed since, use that instead):

```python
"""add buyer_adjusted_totals to plan_cycles

Revision ID: <generated>
Revises: 1968caf074da
Create Date: <generated>

"""
from alembic import op
import sqlalchemy as sa

revision = '<generated>'
down_revision = '1968caf074da'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('plan_cycles', sa.Column('buyer_adjusted_totals', sa.JSON(), nullable=True), schema='workflow')


def downgrade():
    op.drop_column('plan_cycles', 'buyer_adjusted_totals', schema='workflow')
```

Run: `python -m alembic upgrade head`

- [ ] **Step 5: Add `latest_approved_cycle()` to `workflow/service.py`**

In `RS Planning Platform/backend/workflow/service.py`, add right after the existing `latest_approved_run_id`:

```python
def latest_approved_cycle(session: Session) -> PlanCycle | None:
    """Same lookup as latest_approved_run_id, but returns the cycle itself —
    division_aop_summary() needs buyer_adjusted_totals off it, not just the run id."""
    return session.execute(
        select(PlanCycle).where(PlanCycle.status == "approved").order_by(PlanCycle.updated_at.desc())
    ).scalars().first()
```

(`latest_approved_run_id` can stay as-is — nothing else calls it, no need to refactor it to call this.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd "RS Planning Platform/backend" && python -m pytest tests/test_workflow.py -v`
Expected: PASS (all tests, including the two new ones and the existing suite unaffected)

- [ ] **Step 7: Commit**

```bash
git add "RS Planning Platform/backend/workflow/service.py" "RS Planning Platform/backend/tests/test_workflow.py" "Tentative AOP Forecaster/db/models/workflow.py" "Tentative AOP Forecaster/alembic/versions/"*add_buyer_adjusted_totals*.py
git commit -m "Add buyer_adjusted_totals to PlanCycle + latest_approved_cycle()"
```

---

### Task 2: `PUT /plan-cycles/{id}/buyer-totals`

**Files:**
- Modify: `RS Planning Platform/backend/workflow/service.py`
- Modify: `RS Planning Platform/backend/workflow/routes.py`
- Test: `RS Planning Platform/backend/tests/test_workflow.py`

**Interfaces:**
- Consumes: `PlanCycle` (Task 1), `SessionLocal` from `db.base`.
- Produces: `workflow.service.set_buyer_totals(session, cycle_id: uuid.UUID, totals: dict, actor: dict) -> PlanCycle`, raising `LookupError`/`PermissionError`/`ValueError` exactly like `set_current_run`. Route: `PUT /api/aop/plan-cycles/{cycle_id}/buyer-totals`, body `{"totals": {"mens": ..., "ladies": ..., "kids": ...}}`.

- [ ] **Step 1: Write the failing tests**

Add to `RS Planning Platform/backend/tests/test_workflow.py`:

```python
from workflow.service import set_buyer_totals


def test_set_buyer_totals_requires_buyer_role(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])
    cycle = transition(session, cycle.id, "submit", role_users["planner"])  # now pending_buyer
    with pytest.raises(PermissionError):
        set_buyer_totals(session, cycle.id, {"mens": 1, "ladies": 2, "kids": 3}, role_users["planner"])
    session.close()


def test_set_buyer_totals_requires_pending_buyer_status(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])  # still draft
    with pytest.raises(PermissionError):
        set_buyer_totals(session, cycle.id, {"mens": 1, "ladies": 2, "kids": 3}, role_users["buyer"])
    session.close()


def test_set_buyer_totals_rejects_incomplete_totals(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])
    cycle = transition(session, cycle.id, "submit", role_users["planner"])
    with pytest.raises(ValueError):
        set_buyer_totals(session, cycle.id, {"mens": 1, "ladies": 2}, role_users["buyer"])  # missing kids
    session.close()


def test_set_buyer_totals_saves_without_transitioning_status(fake_run, role_users):
    session = SessionLocal()
    cycle = create_cycle(session, fake_run, role_users["planner"])
    cycle = transition(session, cycle.id, "submit", role_users["planner"])
    cycle = set_buyer_totals(session, cycle.id, {"mens": 10.5, "ladies": 20.5, "kids": 5.5}, role_users["buyer"])
    assert cycle.status == "pending_buyer"  # unchanged - saving is not submitting
    assert cycle.buyer_adjusted_totals == {"mens": 10.5, "ladies": 20.5, "kids": 5.5}
    session.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "RS Planning Platform/backend" && python -m pytest tests/test_workflow.py -k set_buyer_totals -v`
Expected: FAIL with `ImportError: cannot import name 'set_buyer_totals'`

- [ ] **Step 3: Implement `set_buyer_totals` in `workflow/service.py`**

```python
REQUIRED_DIVISIONS = ("mens", "ladies", "kids")


def set_buyer_totals(session: Session, cycle_id: uuid.UUID, totals: dict, actor: dict) -> PlanCycle:
    cycle = session.get(PlanCycle, cycle_id)
    if cycle is None:
        raise LookupError("Plan cycle not found")
    if cycle.status != "pending_buyer" or actor["role"] != "buyer":
        raise PermissionError("Only buyer may set totals while pending_buyer")
    if not all(d in totals and isinstance(totals[d], (int, float)) for d in REQUIRED_DIVISIONS):
        raise ValueError(f"totals must include numeric values for {REQUIRED_DIVISIONS}")
    cycle.buyer_adjusted_totals = {d: float(totals[d]) for d in REQUIRED_DIVISIONS}
    session.commit()
    session.refresh(cycle)
    return cycle
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "RS Planning Platform/backend" && python -m pytest tests/test_workflow.py -v`
Expected: PASS (full suite)

- [ ] **Step 5: Add the route**

In `RS Planning Platform/backend/workflow/routes.py`, add `set_buyer_totals` to the import from `workflow.service`, then:

```python
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
```

- [ ] **Step 6: Manually verify the route through the running platform**

Start the platform (`python -m uvicorn app:app --port 8010 --app-dir "RS Planning Platform/backend"`), log in as `admin`/`Citykart@123`, and exercise the endpoint:

```bash
python -c "
import requests
s = requests.Session()
s.post('http://127.0.0.1:8010/api/auth/login', json={'username':'admin','password':'Citykart@123'}).raise_for_status()
r = s.put('http://127.0.0.1:8010/api/aop/plan-cycles/00000000-0000-0000-0000-000000000000/buyer-totals', json={'totals': {'mens':1,'ladies':2,'kids':3}})
print(r.status_code, r.json())
"
```
Expected: `404 {'detail': 'Plan cycle not found'}` (proves the route is wired and the error path works; a full happy-path check comes in Task 5/6's manual walkthrough once there's a real cycle to point at).

- [ ] **Step 7: Commit**

```bash
git add "RS Planning Platform/backend/workflow/service.py" "RS Planning Platform/backend/workflow/routes.py" "RS Planning Platform/backend/tests/test_workflow.py"
git commit -m "Add PUT /plan-cycles/{id}/buyer-totals"
```

---

### Task 3: `division-aop-summary` prefers the buyer's totals

**Files:**
- Modify: `Tentative AOP Forecaster/app.py:344-383` (the existing `division_aop_summary` function)
- Test: `RS Planning Platform/backend/tests/test_full_pipeline.py` (existing file — check its imports/fixtures before adding; it already exercises AOP Forecaster's endpoints against the real DB per the codebase's established pattern)

**Interfaces:**
- Consumes: `workflow.service.latest_approved_cycle` (Task 1).
- Produces: no change to `division-aop-summary`'s response shape — still `{"run_id", "computed_at", "division_aops": [{"division", "annual_target"}, ...]}`, so `SalesPlan`'s `sync-from-aop-forecaster` needs zero changes.

- [ ] **Step 1: Read the existing test file's pattern**

Run: `cat "RS Planning Platform/backend/tests/test_full_pipeline.py"`. It tests via real HTTP (`httpx.Client`) against the LIVE platform on `:8010`, using pre-seeded users `planner1/buyer1/reviewer1/approver1` — **do not use those users or that fixture as-is**: confirmed via `psql` that `auth.users` currently has only one row (`admin`, role `planner`); those seeded users don't exist in this environment. Do NOT import AOP Forecaster's `app.py` directly either — `RS Planning Platform/backend/app.py` is *also* named `app.py` and already carries a comment explaining why a plain `from app import ...` collides with itself when both are on `sys.path` in the same process (see its `importlib.util.spec_from_file_location` workaround). Testing through real HTTP against the mounted route sidesteps that collision entirely, which is why this task tests that way instead of calling `division_aop_summary()` directly.

Requires the platform running on `:8010` before running these tests (`python -m uvicorn app:app --port 8010 --app-dir "RS Planning Platform/backend"`).

- [ ] **Step 2: Write the failing test**

Add to `RS Planning Platform/backend/tests/test_full_pipeline.py`:

```python
import uuid as _uuid

from auth.security import hash_password
from db.base import SessionLocal
from db.models.auth import User
from db.models.engine import ForecastRun
from workflow.service import create_cycle, set_buyer_totals, transition


def _make_role_user(role):
    """Throwaway user for this test only — test_full_pipeline.py's own
    planner1/buyer1/... fixtures assume users seeded in an earlier session
    that don't exist in this environment (confirmed via psql before writing
    this)."""
    session = SessionLocal()
    u = User(username=f"{role}_{_uuid.uuid4().hex[:8]}", password_hash=hash_password("testpass123"), role=role)
    session.add(u)
    session.commit()
    session.refresh(u)
    session.close()
    return {"id": str(u.id), "role": role, "username": u.username}


def _login_as(username):
    c = httpx.Client(base_url=BASE, timeout=30.0)
    r = c.post("/api/auth/login", json={"username": username, "password": "testpass123"})
    assert r.status_code == 200, r.text
    return c


def test_division_aop_summary_prefers_buyer_adjusted_totals():
    session = SessionLocal()
    import datetime
    run = ForecastRun(input_snapshot_at=datetime.datetime.now(datetime.timezone.utc), status="success")
    session.add(run)
    session.commit()
    session.refresh(run)
    run_id = run.run_id

    users = {r: _make_role_user(r) for r in ("planner", "buyer", "reviewer", "approver")}
    cycle = create_cycle(session, run_id, users["planner"])
    cycle = transition(session, cycle.id, "submit", users["planner"])
    cycle = set_buyer_totals(session, cycle.id, {"mens": 111.0, "ladies": 222.0, "kids": 333.0}, users["buyer"])
    transition(session, cycle.id, "submit", users["buyer"])
    transition(session, cycle.id, "approve", users["reviewer"])
    transition(session, cycle.id, "approve", users["approver"])
    session.close()

    client = _login_as(users["planner"]["username"])
    r = client.get("/api/aop/api/config/division-aop-summary")
    assert r.status_code == 200, r.text
    by_div = {row["division"]: row["annual_target"] for row in r.json()["division_aops"]}
    assert by_div == {"mens": 111.0, "ladies": 222.0, "kids": 333.0}
```

- [ ] **Step 3: Run the test to verify it fails**

Run (with the platform running on `:8010`): `cd "RS Planning Platform/backend" && python -m pytest tests/test_full_pipeline.py -k buyer_adjusted_totals -v`
Expected: FAIL — the endpoint still returns the raw computed sum (empty, since this run has no real `ForecastResult` rows), not the buyer's totals.

- [ ] **Step 4: Modify `division_aop_summary()`**

In `Tentative AOP Forecaster/app.py`, replace the body from `with SessionLocal() as session:` onward:

```python
    from workflow.service import latest_approved_cycle

    with SessionLocal() as session:
        cycle = latest_approved_cycle(session)
        if cycle is None or cycle.current_run_id is None:
            raise HTTPException(404, "No approved plan cycle yet")
        run_id = cycle.current_run_id
        latest = session.get(ForecastRun, run_id)

        if cycle.buyer_adjusted_totals:
            return {
                "run_id": str(latest.run_id), "computed_at": latest.created_at.isoformat(),
                "division_aops": [{"division": d, "annual_target": v} for d, v in cycle.buyer_adjusted_totals.items()],
            }

        # FY28 = Apr'27..Mar'28 (engine_v3.FY28_M minus its leading Mar'27, which
        # is this year's last actual month, not part of the plan being AOP'd)
        next_fy_labels = {"Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                          "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"}
        next_fy_periods = {
            p.period_id for p in session.execute(select(Period)).scalars().all()
            if p.label in next_fy_labels
        }
        rows = session.execute(
            select(ForecastResult.division_code, func.sum(ForecastResult.value))
            .where(ForecastResult.run_id == latest.run_id, ForecastResult.metric_key == "forecast",
                   ForecastResult.period_id.in_(next_fy_periods))
            .group_by(ForecastResult.division_code)
        ).all()
        return {
            "run_id": str(latest.run_id), "computed_at": latest.created_at.isoformat(),
            "division_aops": [{"division": div, "annual_target": round(float(total), 2)} for div, total in rows],
        }
```

(The import of `latest_approved_run_id` at the top of the function is no longer used — remove that line; keep the `sys.path.insert` above it, since `latest_approved_cycle` needs the same path to resolve `workflow.service`.)

- [ ] **Step 5: Restart the platform and run the test to verify it passes**

The route this test hits is mounted in-process when the platform starts — a code change to `Tentative AOP Forecaster/app.py` needs the platform process restarted before the running server reflects it. Find and kill the current listener, then restart:

```bash
# Windows: find the PID on :8010 and stop it, matching the pattern used all session
netstat -ano | grep :8010
# then: taskkill //F //PID <pid>   (or the platform-appropriate equivalent)
python -m uvicorn app:app --port 8010 --app-dir "RS Planning Platform/backend" &
```

Wait for `http://127.0.0.1:8010/calendar/` to respond before testing. Then:

Run: `cd "RS Planning Platform/backend" && python -m pytest tests/test_full_pipeline.py -k buyer_adjusted_totals -v`
Expected: PASS

- [ ] **Step 6: Run the rest of `test_full_pipeline.py` and `test_workflow.py`, noting pre-existing failures separately**

Run: `cd "RS Planning Platform/backend" && python -m pytest tests/test_workflow.py tests/test_full_pipeline.py -v`
Expected: `test_workflow.py` fully PASS (no change to its fixtures). In `test_full_pipeline.py`, the *other* pre-existing tests (`test_division_aop_summary_404s_with_no_approved_cycle`, `test_full_workflow_to_salesplan`) were already failing before this task, since they depend on `planner1/buyer1/reviewer1/approver1` users that don't exist in this environment (confirmed via `psql` in Step 1) — that is a pre-existing gap, not a regression this task introduces. Confirm only that: (a) the new `test_division_aop_summary_prefers_buyer_adjusted_totals` passes, and (b) any pre-existing failures are the same missing-user failures as before this task's changes, not something new. If a pre-existing test now fails with a *different* error than a login/401 failure, that is a real regression — stop and investigate before continuing.

- [ ] **Step 7: Commit**

```bash
git add "Tentative AOP Forecaster/app.py" "RS Planning Platform/backend/tests/test_full_pipeline.py"
git commit -m "division-aop-summary: prefer the buyer's adjusted totals once approved"
```

---

### Task 4: `GET /api/config/recent-runs` and `GET /api/config/runs/{run_id}/division-totals`

**Files:**
- Modify: `Tentative AOP Forecaster/app.py` (add near `division_aop_summary`, after it)
- Test: `RS Planning Platform/backend/tests/test_full_pipeline.py`

**Interfaces:**
- Produces: `_division_totals_for_run(session, run_id) -> dict[str, float]` (shared helper, e.g. `{"mens": 123.4, ...}`), `GET /api/config/recent-runs` → `[{"run_id", "created_at", "status", "division_totals"}, ...]` (newest 20 by `created_at`), `GET /api/config/runs/{run_id}/division-totals` → `{"run_id", "division_totals"}` or `404`.

- [ ] **Step 1: Write the failing tests**

Same reasoning as Task 3's Step 1: test via real HTTP against the live `:8010` platform, not a direct `from app import ...` (the module-name collision), and don't depend on `test_workflow.py`'s `fake_run`/`role_users` fixtures — those are local to that file, not shared via `conftest.py` (checked: `conftest.py` defines `app`/`client`/`test_user`/`planner_client`/`buyer_client`, none of which mount AOP Forecaster's router or provide a `ForecastRun`). Use the same `_make_role_user`/`_login_as` helpers Task 3 added to this file.

Add to `RS Planning Platform/backend/tests/test_full_pipeline.py`:

```python
def test_recent_runs_lists_newest_first():
    import datetime
    session = SessionLocal()
    run = ForecastRun(input_snapshot_at=datetime.datetime.now(datetime.timezone.utc), status="success")
    session.add(run)
    session.commit()
    session.refresh(run)
    run_id = str(run.run_id)
    session.close()

    user = _make_role_user("planner")
    client = _login_as(user["username"])
    r = client.get("/api/aop/api/config/recent-runs")
    assert r.status_code == 200, r.text
    run_ids = [row["run_id"] for row in r.json()]
    assert run_id in run_ids


def test_run_division_totals_404s_for_unknown_run():
    user = _make_role_user("planner")
    client = _login_as(user["username"])
    r = client.get(f"/api/aop/api/config/runs/{_uuid.uuid4()}/division-totals")
    assert r.status_code == 404, r.text
```

(`_make_role_user` and `_login_as` are the helpers Task 3 already added to this file — this task depends on Task 3 landing first, which the plan's task order already guarantees.)

- [ ] **Step 2: Run tests to verify they fail**

Run (with the platform running on `:8010`): `cd "RS Planning Platform/backend" && python -m pytest tests/test_full_pipeline.py -k "recent_runs or run_division_totals" -v`
Expected: FAIL with a 404 on both routes (neither endpoint exists yet)

- [ ] **Step 3: Implement, right after `division_aop_summary` in `Tentative AOP Forecaster/app.py`**

```python
def _division_totals_for_run(session, run_id) -> dict:
    next_fy_labels = {"Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                      "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"}
    next_fy_periods = {
        p.period_id for p in session.execute(select(Period)).scalars().all()
        if p.label in next_fy_labels
    }
    rows = session.execute(
        select(ForecastResult.division_code, func.sum(ForecastResult.value))
        .where(ForecastResult.run_id == run_id, ForecastResult.metric_key == "forecast",
               ForecastResult.period_id.in_(next_fy_periods))
        .group_by(ForecastResult.division_code)
    ).all()
    return {div: round(float(total), 2) for div, total in rows}


@router.get("/api/config/recent-runs")
def recent_runs():
    """Lists recent ForecastRuns for the planner's "submit for buyer review"
    picker in plan-cycles.html — nothing else in this app lists runs by id."""
    from sqlalchemy import select, func, desc
    from db.base import SessionLocal
    from db.models.engine import ForecastRun

    with SessionLocal() as session:
        runs = session.execute(select(ForecastRun).order_by(desc(ForecastRun.created_at)).limit(20)).scalars().all()
        return [
            {"run_id": str(r.run_id), "created_at": r.created_at.isoformat(), "status": r.status,
             "division_totals": _division_totals_for_run(session, r.run_id)}
            for r in runs
        ]


@router.get("/api/config/runs/{run_id}/division-totals")
def run_division_totals(run_id: str):
    """The buyer tab's totals source (Buyer's Input Sheet's AOP Review tab) -
    a cycle's current_run_id isn't guaranteed to still be within recent-runs'
    20-row window, so it looks a specific run up directly instead."""
    import uuid as _uuid
    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.engine import ForecastRun

    with SessionLocal() as session:
        run = session.get(ForecastRun, _uuid.UUID(run_id))
        if run is None:
            raise HTTPException(404, "Run not found")
        return {"run_id": run_id, "division_totals": _division_totals_for_run(session, run.run_id)}
```

- [ ] **Step 4: Restart the platform and run tests to verify they pass**

Same reasoning as Task 3's Step 5 — this route is mounted in-process, restart the `:8010` server before testing:

Run: `cd "RS Planning Platform/backend" && python -m pytest tests/test_full_pipeline.py -k "buyer_adjusted_totals or recent_runs or run_division_totals" -v`
Expected: PASS (the new tests from this task and Task 3; the pre-existing `planner1`-dependent tests are still expected to fail the same way they did before this task, per Task 3 Step 6's note — don't treat that as this task's regression)

- [ ] **Step 5: Manually verify against the running platform**

```bash
python -c "
import requests
s = requests.Session()
s.post('http://127.0.0.1:8010/api/auth/login', json={'username':'admin','password':'Citykart@123'}).raise_for_status()
print(s.get('http://127.0.0.1:8010/api/aop/api/config/recent-runs').json())
"
```
Expected: a JSON list (empty or with real runs, either is fine — this just proves the route resolves and returns valid JSON, not a 500).

- [ ] **Step 6: Commit**

```bash
git add "Tentative AOP Forecaster/app.py" "RS Planning Platform/backend/tests/test_full_pipeline.py"
git commit -m "Add recent-runs and per-run division-totals endpoints"
```

---

### Task 5: `plan-cycles.html` — planner / reviewer / approver page

**Files:**
- Create: `RS Planning Platform/backend/static/plan-cycles.html`
- Modify: `RS Planning Platform/backend/app.py` (add the `GET /plan-cycles` route)

**Interfaces:**
- Consumes: `GET /api/aop/plan-cycles` (list), `GET /api/aop/plan-cycles/{id}` (detail+transitions), `POST /api/aop/plan-cycles` (create, body `{"run_id"}`), `POST /api/aop/plan-cycles/{id}/{submit|approve|reject}`, `GET /api/aop/api/config/recent-runs` (Task 4) — all already exist or were just added; no new backend work in this task.
- Produces: a page at `GET /plan-cycles`, login-gated like every other protected page.

- [ ] **Step 1: Add the route in `app.py`**

Right after the existing `/login` route:

```python
@app.get("/plan-cycles")
def plan_cycles_page(request: Request):
    if get_session_user(request) is None:
        return RedirectResponse(f"/login?next=/plan-cycles")
    return FileResponse(os.path.join(_HERE, "static", "plan-cycles.html"))
```

- [ ] **Step 2: Write `static/plan-cycles.html`**

Follow `static/login.html`'s exact styling conventions (same `:root` variables, same card/button classes) so it looks like part of the same app, not a separate tool:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RS Planning Platform — Plan Cycles</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; padding: 32px;
    font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    background: #f4f5f7;
  }
  .wrap { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  p.sub { margin: 0 0 24px; color: #6b7280; font-size: 13px; }
  .card {
    background: #fff; border-radius: 10px; padding: 20px; margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 8px 24px rgba(0,0,0,0.06);
  }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .status {
    display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  }
  .status-draft { background: #e5e7eb; color: #374151; }
  .status-pending_buyer, .status-pending_review, .status-pending_approval { background: #fef3c7; color: #92400e; }
  .status-approved { background: #d1fae5; color: #065f46; }
  select, button, input {
    padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px;
  }
  button { background: #2563eb; color: #fff; border: none; cursor: pointer; font-weight: 600; }
  button:disabled { background: #93b4f0; cursor: default; }
  .muted { color: #6b7280; font-size: 12px; }
  .transitions { margin-top: 10px; font-size: 12px; color: #6b7280; }
  .transitions div { padding: 2px 0; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Plan Cycles</h1>
  <p class="sub" id="role-line">Loading…</p>

  <div class="card" id="planner-card" style="display:none">
    <div class="row">
      <strong>Submit an AOP run for buyer review</strong>
    </div>
    <div class="row" style="margin-top:10px">
      <select id="run-picker"></select>
      <button id="submit-run-btn">Submit for buyer review</button>
    </div>
  </div>

  <div id="cycle-list"></div>
</div>

<script>
async function api(path, opts) {
  const res = await fetch('/api/aop' + path, { credentials: 'same-origin', ...opts });
  if (res.status === 401) { window.location.href = '/login?next=/plan-cycles'; throw new Error('not authenticated'); }
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

let me = null;

async function loadMe() {
  me = await fetch('/api/auth/me', { credentials: 'same-origin' }).then(r => r.ok ? r.json() : null);
  document.getElementById('role-line').textContent = me
    ? `Signed in as ${me.username} (${me.role})`
    : 'Not signed in';
  if (me && me.role === 'planner') {
    document.getElementById('planner-card').style.display = '';
    loadRecentRuns();
  }
}

async function loadRecentRuns() {
  const runs = await fetch('/api/aop/api/config/recent-runs', { credentials: 'same-origin' }).then(r => r.json());
  const sel = document.getElementById('run-picker');
  sel.innerHTML = runs.map(r => {
    const totals = Object.entries(r.division_totals).map(([d, v]) => `${d}: ${v}`).join(', ') || 'no totals yet';
    return `<option value="${r.run_id}">${r.created_at.slice(0, 16)} — ${totals}</option>`;
  }).join('') || '<option value="">No runs yet</option>';
}

document.getElementById('submit-run-btn').addEventListener('click', async () => {
  const runId = document.getElementById('run-picker').value;
  if (!runId) return;
  const cycle = await api('/plan-cycles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId }) });
  await api(`/plan-cycles/${cycle.id}/submit`, { method: 'POST' });
  loadCycles();
});

function statusClass(s) { return 'status status-' + s; }

async function loadCycles() {
  const cycles = await api('/plan-cycles');
  const list = document.getElementById('cycle-list');
  list.innerHTML = '';
  for (const c of cycles) {
    const detail = await api(`/plan-cycles/${c.id}`);
    const div = document.createElement('div');
    div.className = 'card';
    const canReview = me.role === 'reviewer' && c.status === 'pending_review';
    const canApprove = me.role === 'approver' && c.status === 'pending_approval';
    div.innerHTML = `
      <div class="row">
        <div><strong>${c.id.slice(0, 8)}</strong> <span class="muted">created ${c.created_at.slice(0, 16)}</span></div>
        <span class="${statusClass(c.status)}">${c.status}</span>
      </div>
      ${(canReview || canApprove) ? `
        <div class="row" style="margin-top:10px">
          <button class="approve-btn" data-id="${c.id}">Approve</button>
          <button class="reject-btn" data-id="${c.id}" style="background:#dc2626">Reject</button>
        </div>` : ''}
      <div class="transitions">
        ${detail.transitions.map(t => `<div>${t.at.slice(0, 16)} — ${t.actor_role} ${t.from} → ${t.to}${t.comment ? ' ("' + t.comment + '")' : ''}</div>`).join('')}
      </div>
    `;
    list.appendChild(div);
  }
  list.querySelectorAll('.approve-btn').forEach(b => b.addEventListener('click', () => actOn(b.dataset.id, 'approve')));
  list.querySelectorAll('.reject-btn').forEach(b => b.addEventListener('click', () => actOn(b.dataset.id, 'reject')));
}

async function actOn(id, action) {
  await api(`/plan-cycles/${id}/${action}`, { method: 'POST' });
  loadCycles();
}

(async () => { await loadMe(); await loadCycles(); })();
</script>
</body>
</html>
```

- [ ] **Step 3: Manually verify in the browser**

Start the platform, log in as `admin` (role `planner`), navigate to `http://localhost:8010/plan-cycles`. Confirm: the page loads without a login redirect loop, the planner card shows (since `admin`'s role is `planner`), and the run picker populates from `/api/config/recent-runs` (empty list is fine if no AOP runs exist yet — confirm it shows "No runs yet" rather than erroring).

- [ ] **Step 4: Commit**

```bash
git add "RS Planning Platform/backend/static/plan-cycles.html" "RS Planning Platform/backend/app.py"
git commit -m "Add plan-cycles.html: planner submit + reviewer/approver actions"
```

---

### Task 6: "AOP Review" tab in Buyer's Input Sheet

**Files:**
- Modify: `Buyer's Input Sheet/otb-plan-app.html`

**Interfaces:**
- Consumes (cross-origin, `credentials: 'include'`, against `http://localhost:8010`): `GET /api/aop/plan-cycles`, `GET /api/aop/api/config/runs/{run_id}/division-totals` (Task 4), `PUT /api/aop/plan-cycles/{id}/buyer-totals` (Task 2), `POST /api/aop/plan-cycles/{id}/submit`, `POST /api/calendar/salesdata/reindex` (existing, for the LY reference — read-only display, no new job needed for a quick reference number).

- [ ] **Step 1: Locate the existing tab strip**

Run: `grep -n "tab-strip\|class=\"tabs\"\|Buyer.s Plan" "Buyer's Input Sheet/otb-plan-app.html" | head -20` to find the existing tab-switching markup/JS and match its exact pattern (tab button + content-panel show/hide convention already used for the app's other tabs).

- [ ] **Step 2: Add the tab button and panel**

Following whatever pattern Step 1 finds, add a new tab button labeled "AOP Review" and a corresponding content panel `<div id="aop-review-panel" style="display:none">` containing:
- A `<select id="aop-review-cycle-picker">` populated from cycles with `status === 'pending_buyer'`.
- Three number inputs (Mens / Ladies / Kids), prefilled from `run_division_totals`.
- A read-only "LY reference" line per division, sourced from a month-wise reindex call against the current locked calendar (reuse the existing `runReindex`-style call already in this file if one exists for month-wise summaries; if not, skip populating this specific line and show "LY reference unavailable" — this is explicitly informational-only per the spec, never blocking).
- "Save" and "Submit for Review" buttons.

```html
<script>
const PLATFORM_BASE = 'http://localhost:8010';

async function platformApi(path, opts) {
  const res = await fetch(PLATFORM_BASE + path, { credentials: 'include', ...opts });
  if (res.status === 401) {
    document.getElementById('aop-review-panel').innerHTML =
      '<p>Sign in to the platform first — <a href="' + PLATFORM_BASE + '/login" target="_blank">open login</a>, then reload this tab.</p>';
    throw new Error('not authenticated to platform');
  }
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

let aopReviewCycle = null;

async function loadAopReviewCycles() {
  const cycles = await platformApi('/api/aop/plan-cycles');
  const pending = cycles.filter(c => c.status === 'pending_buyer');
  const sel = document.getElementById('aop-review-cycle-picker');
  sel.innerHTML = pending.map(c => `<option value="${c.id}">${c.id.slice(0, 8)} — created ${c.created_at.slice(0, 16)}</option>`).join('')
    || '<option value="">No cycles awaiting review</option>';
  if (pending.length) await loadCycleTotals(pending[0].id);
}

async function loadCycleTotals(cycleId) {
  aopReviewCycle = await platformApi(`/api/aop/plan-cycles/${cycleId}`);
  if (!aopReviewCycle.current_run_id) return;
  const { division_totals } = await platformApi(`/api/aop/api/config/runs/${aopReviewCycle.current_run_id}/division-totals`);
  document.getElementById('aop-review-mens').value = division_totals.mens ?? '';
  document.getElementById('aop-review-ladies').value = division_totals.ladies ?? '';
  document.getElementById('aop-review-kids').value = division_totals.kids ?? '';
}

function readAopReviewTotals() {
  return {
    mens: parseFloat(document.getElementById('aop-review-mens').value),
    ladies: parseFloat(document.getElementById('aop-review-ladies').value),
    kids: parseFloat(document.getElementById('aop-review-kids').value),
  };
}

document.getElementById('aop-review-save-btn').addEventListener('click', async () => {
  if (!aopReviewCycle) return;
  await platformApi(`/api/aop/plan-cycles/${aopReviewCycle.id}/buyer-totals`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ totals: readAopReviewTotals() }),
  });
  document.getElementById('aop-review-msg').textContent = 'Saved.';
});

document.getElementById('aop-review-submit-btn').addEventListener('click', async () => {
  if (!aopReviewCycle) return;
  await platformApi(`/api/aop/plan-cycles/${aopReviewCycle.id}/buyer-totals`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ totals: readAopReviewTotals() }),
  });
  await platformApi(`/api/aop/plan-cycles/${aopReviewCycle.id}/submit`, { method: 'POST' });
  document.getElementById('aop-review-msg').textContent = 'Submitted for review.';
  loadAopReviewCycles();
});

document.getElementById('aop-review-cycle-picker').addEventListener('change', e => {
  if (e.target.value) loadCycleTotals(e.target.value);
});
</script>
```

Wire the new tab button's click handler to call `loadAopReviewCycles()` the first time it's shown (matching whatever lazy-load convention Step 1 found for other tabs).

- [ ] **Step 3: Manually verify in the browser**

1. Log into the platform (`http://localhost:8010/login`) in the same browser.
2. As `admin` (planner), go to `http://localhost:8010/plan-cycles`, submit a run for buyer review (needs at least one `ForecastRun` to exist — run AOP Forecaster once first if `recent-runs` is empty).
3. Open Buyer's Input Sheet (`http://localhost:5050`), click the new "AOP Review" tab. Confirm: the cycle appears in the picker, the three division totals prefill from the run, editing and clicking "Save" then reloading the tab shows the edited values persisted, and "Submit for Review" moves the cycle to `pending_review` (confirm by reloading `http://localhost:8010/plan-cycles` and seeing its status change).

- [ ] **Step 4: Commit**

```bash
git add "Buyer's Input Sheet/otb-plan-app.html"
git commit -m "Add AOP Review tab to Buyer's Input Sheet"
```

---

### Task 7: Landing — live plan-cycle status + drag-and-drop card reordering

**Files:**
- Modify: `Landing/index.html`

**Interfaces:**
- Consumes (cross-origin, `credentials: 'include'`, against `http://localhost:8010`): `GET /api/aop/plan-cycles` (existing).
- Produces: replaces the static "Flow — AOP Forecaster → Planning Engine" text block with a live, polling view of the most recent cycle's actual stage; adds drag-and-drop reordering to the `.grid` of module cards, order persisted to `localStorage`.

- [ ] **Step 1: Replace the static "Flow" section's content with a live one**

In `Landing/index.html`, find the `<div class="sync-section">` containing `Flow — AOP Forecaster → Planning Engine` (there are two `sync-section` blocks — this is the second one, `id="flow-rows"` holds its content). Leave the surrounding markup; add a new function and call it alongside the existing status-check calls:

```javascript
const STAGE_ORDER = ['draft', 'pending_buyer', 'pending_review', 'pending_approval', 'approved'];
const STAGE_LABELS = {
  draft: 'Draft', pending_buyer: 'Awaiting Buyer', pending_review: 'Awaiting Review',
  pending_approval: 'Awaiting Approval', approved: 'Approved — synced to Sales Plan',
};

async function checkPlanCycleFlow() {
  const el = document.getElementById('flow-rows');
  try {
    const res = await fetch('http://localhost:8010/api/aop/plan-cycles', { credentials: 'include', cache: 'no-store' });
    if (res.status === 401) { el.innerHTML = '<div class="sync-empty">Sign in to the platform to see live cycle status.</div>'; return; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cycles = await res.json();
    if (!cycles.length) { el.innerHTML = '<div class="sync-empty">No plan cycles started yet.</div>'; return; }
    const latest = cycles[0]; // already newest-first per the backend's own ordering
    const stageIdx = STAGE_ORDER.indexOf(latest.status);
    el.innerHTML = `
      <div class="sync-row">
        <div style="display:flex; gap:4px; margin-bottom:6px">
          ${STAGE_ORDER.map((s, i) => `<div style="flex:1; height:4px; border-radius:2px; background:${i <= stageIdx ? '#2ecc71' : 'rgba(255,255,255,0.15)'}"></div>`).join('')}
        </div>
        <div>Cycle ${latest.id.slice(0, 8)}: <strong>${STAGE_LABELS[latest.status] || latest.status}</strong></div>
      </div>`;
  } catch (e) {
    el.innerHTML = `<div class="sync-error">Platform (localhost:8010) unreachable.</div>`;
  }
}
checkPlanCycleFlow();
setInterval(checkPlanCycleFlow, 10000); // live - reflects new transitions without a manual reload
```

Remove the now-superseded old fetch to `http://localhost:8002/api/department-plan/aop-forecaster-status` for the `flow-rows` element if it exists (check for it — it populated the same DOM element with the old static-style content; keep the `extraction-rows` fetch to `:8000/api/config/db-sync/status` untouched, that's a separate, still-accurate section for data-lake extraction).

- [ ] **Step 2: Add drag-and-drop card reordering**

Add near the other `<script>` logic in `Landing/index.html`:

```javascript
(function () {
  const grid = document.querySelector('.grid');
  if (!grid) return;
  const STORAGE_KEY = 'landing-card-order';

  function applyStoredOrder() {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    if (!stored.length) return;
    const cards = [...grid.children];
    const byHref = new Map(cards.map(c => [c.getAttribute('href') || c.id, c]));
    stored.forEach(key => { const c = byHref.get(key); if (c) grid.appendChild(c); });
  }

  function saveOrder() {
    const order = [...grid.children].map(c => c.getAttribute('href') || c.id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(order));
  }

  [...grid.children].forEach(card => {
    card.setAttribute('draggable', 'true');
    card.addEventListener('dragstart', e => {
      e.dataTransfer.setData('text/plain', card.getAttribute('href') || card.id);
      card.style.opacity = '0.4';
    });
    card.addEventListener('dragend', () => { card.style.opacity = ''; saveOrder(); });
    card.addEventListener('dragover', e => e.preventDefault());
    card.addEventListener('drop', e => {
      e.preventDefault();
      const draggedKey = e.dataTransfer.getData('text/plain');
      const dragged = [...grid.children].find(c => (c.getAttribute('href') || c.id) === draggedKey);
      if (dragged && dragged !== card) {
        const cards = [...grid.children];
        const draggedIdx = cards.indexOf(dragged), targetIdx = cards.indexOf(card);
        if (draggedIdx < targetIdx) card.after(dragged); else card.before(dragged);
      }
    });
  });

  applyStoredOrder();
})();
```

Add a small CSS affordance so cards look draggable — in the existing `.card` rule block, add `cursor: grab;` and on `:active` `cursor: grabbing;`:

```css
.card { cursor: grab; }
.card:active { cursor: grabbing; }
```

- [ ] **Step 3: Manually verify in the browser**

1. Reload `http://localhost:7800`. Confirm the "Flow" section now shows a 5-segment progress bar and a stage label instead of the old static text (with no plan cycles yet, it should say "No plan cycles started yet" rather than erroring).
2. After completing Task 5/6's manual walkthrough (a real cycle exists and has been submitted), reload Landing and confirm the bar/label reflects that cycle's actual current stage, and that it updates within ~10s of a stage change (e.g. approve it via `plan-cycles.html` in another tab, watch Landing pick it up without a manual reload).
3. Drag a module card to a different position, reload the page, confirm the new order persists.

- [ ] **Step 4: Commit**

```bash
git add "Landing/index.html"
git commit -m "Landing: live plan-cycle stage indicator + drag-and-drop card order"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1–2 cover the spec's data-model + buyer-totals endpoint; Task 3 covers the `division-aop-summary` change (the spec's core "sync always from buyer's input" guarantee); Task 4 covers the two new AOP Forecaster read endpoints the spec calls out; Task 5 covers the spec's shared planner/reviewer/approver page; Task 6 covers the spec's AOP Review tab, including the calendarised-LY-reference requirement (best-effort, non-blocking per the spec's error-handling section); Task 7 covers the two new requirements from the user's follow-up message (live flow tracking, drag-and-drop) that extend the spec.
- **Type consistency:** `buyer_adjusted_totals` shape (`{mens, ladies, kids}` floats) is identical across Task 1's column, Task 2's endpoint, Task 3's summary endpoint, and Task 6's UI fields — checked.
- **Scope:** this is one coherent feature (the approved spec plus its two follow-up UI asks) — not split further.
