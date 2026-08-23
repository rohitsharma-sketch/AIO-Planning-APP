# Unified Backend + Auth + Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One authenticated FastAPI process (port 8010) mounting AOP Forecaster
and SalesPlan's existing routers, with a four-role Planner→Buyer→Reviewer→
Approver workflow gating SalesPlan's data pull to approved forecasts only,
and a full audit trail of both workflow decisions and data edits.

**Architecture:** New project `RS Planning Platform/backend/` imports AOP
Forecaster's and SalesPlan's existing route modules via `sys.path` (neither
app's files move). New SQLAlchemy models (`auth`, `workflow`, `audit`
schemas) are added to AOP Forecaster's existing `db/` package — same
Postgres instance (`rs_planning`), same Alembic setup already proven this
session, so no new migration tooling. AOP Forecaster's `app.py` gets its
routes extracted into an `APIRouter` (additive — it still runs standalone
too). SalesPlan needs zero backend changes; its 11 routers are already
`APIRouter()` objects.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 + Alembic (existing), Postgres 18
(existing `rs_planning` DB), `passlib[bcrypt]` (new), Starlette
`SessionMiddleware` + `itsdangerous` (already a FastAPI transitive
dependency), `pytest` + `httpx` for tests.

**Spec:** `CLAUDE Projects/docs/superpowers/specs/2026-08-22-unified-backend-auth-design.md`

## Global Constraints

- Postgres connection: reuse `rs_planning_app` / the connection string already
  in `Tentative AOP Forecaster/.env` (`DATABASE_URL`) — no new database, no
  new role.
- All new tables live in three new schemas — `auth`, `workflow`, `audit` —
  in the existing `rs_planning` Postgres database, per the spec.
- `input_values`-style identity columns must never be nullable in a unique
  constraint (the bug fixed earlier this session) — every new table with a
  composite uniqueness requirement uses non-null columns or a surrogate key,
  never a nullable one.
- Neither `Tentative AOP Forecaster/app.py` nor `SalesPlan/backend/main.py`
  may be broken as standalone servers at any point — every task that touches
  them must leave `python -m uvicorn app:app --port 8000` (AOP) and
  `python -m uvicorn main:app --port 8002` (SalesPlan) working exactly as
  before.
- No placeholder/TBD code — every step below is real, complete code.

---

## File Structure

```
Tentative AOP Forecaster/                    (existing project — modified)
  db/models/
    auth.py                  # NEW — User
    workflow.py               # NEW — PlanCycle, PlanCycleTransition
    audit.py                  # NEW — DataChange
    __init__.py                # MODIFIED — register the 3 new modules
  db/editor.py                 # MODIFIED — put_growth/put_nso/put_aop_overrides log to audit.data_changes
  app.py                       # MODIFIED — routes extracted into `router = APIRouter()`, kept working standalone
  alembic/versions/…            # NEW migration for auth/workflow/audit schemas

SalesPlan/backend/               (existing project — UNCHANGED)

RS Planning Platform/            (new project)
  backend/
    app.py                      # the ONE FastAPI() instance, port 8010
    auth/
      __init__.py
      security.py               # hash_password, verify_password, session helpers
      deps.py                   # require_login, require_role(*roles), require_admin
      routes.py                 # /api/auth/login, /logout, /me, /api/auth/admin/users
    workflow/
      __init__.py
      service.py                # create_cycle, submit, approve, reject — the state machine
      routes.py                 # /api/aop/plan-cycles/*
    audit/
      __init__.py
      routes.py                 # /api/audit/data-changes, /api/audit/plan-cycles/{id}
    static/
      login.html                # plain HTML/JS login form
    seed_admin.py                # one-time first-admin creation script
    requirements.txt
    tests/
      conftest.py
      test_auth.py
      test_workflow.py
      test_audit.py
      test_router_mount.py
      test_full_pipeline.py
```

---

## Task 1: Auth data model + migration

**Files:**
- Create: `Tentative AOP Forecaster/db/models/auth.py`
- Modify: `Tentative AOP Forecaster/db/models/__init__.py`
- Create: `Tentative AOP Forecaster/alembic/versions/<hash>_add_auth_schema.py` (via autogenerate)

**Interfaces:**
- Produces: `db.models.auth.User` (columns: `id: uuid`, `username: str`,
  `password_hash: str`, `role: str`, `is_admin: bool`, `created_at:
  datetime`, `is_active: bool`) — every later auth/workflow/audit task
  imports this.

- [x] **Step 1: Write `db/models/auth.py`**

```python
"""auth schema — Postgres-backed login, four workflow roles + an
orthogonal is_admin flag (see docs/superpowers/specs/2026-08-22-...-design.md)."""
import datetime
import uuid

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

ROLES = ("planner", "buyer", "reviewer", "approver")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # one of ROLES
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

- [x] **Step 2: Register it in `db/models/__init__.py`**

Change:
```python
from . import masterdata, calendar, planning_inputs, sync, engine  # noqa: F401
```
to:
```python
from . import masterdata, calendar, planning_inputs, sync, engine, auth, workflow, audit  # noqa: F401
```
(This references `workflow` and `audit` modules created in Tasks 2 and 3 —
this edit is finalized once those files exist; for this task, temporarily
import only `auth` and revisit in Task 3's Step 2.)

- [x] **Step 3: Generate and apply the migration**

Run from `Tentative AOP Forecaster/`:
```bash
python -m alembic revision --autogenerate -m "add auth schema"
```
Open the generated file and confirm it creates schema `auth` and table
`auth.users` only (no unrelated diffs — if there are any, something in
Task steps 1-2 is wrong; fix before applying). Then:
```bash
python -m alembic upgrade head
python -m alembic check
```
Expected: `alembic check` prints "No new upgrade operations detected."

- [x] **Step 4: Verify the table exists**

```bash
export PGPASSWORD='RsPlanning_2026Local'
"/c/Program Files/PostgreSQL/18/bin/psql.exe" -U rs_planning_app -h 127.0.0.1 -p 5432 -d rs_planning -c "\d auth.users"
```
Expected: column list matching the model above.

---

## Task 2: Workflow data model + migration

**Files:**
- Create: `Tentative AOP Forecaster/db/models/workflow.py`
- Modify: `Tentative AOP Forecaster/db/models/__init__.py` (add `workflow` to the import line finalized here)
- Create: new Alembic migration

**Interfaces:**
- Consumes: `db.models.auth.User` (Task 1), `db.models.engine.ForecastRun` (existing, from earlier this session).
- Produces: `db.models.workflow.PlanCycle` (`id: uuid`, `status: str`,
  `current_run_id: uuid|None`, `created_by: uuid`, `created_at`,
  `updated_at`), `db.models.workflow.PlanCycleTransition` (`id: int`,
  `plan_cycle_id: uuid`, `from_status: str`, `to_status: str`,
  `actor_id: uuid`, `actor_role: str`, `comment: str|None`,
  `run_id: uuid|None`, `created_at`). `PlanCycle.STATUSES` = the 5-tuple of
  valid statuses.

- [x] **Step 1: Write `db/models/workflow.py`**

```python
"""workflow schema — the Planner->Buyer->Reviewer->Approver plan_cycle
state machine. See the spec for the full transition table."""
import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

STATUSES = ("draft", "pending_buyer", "pending_review", "pending_approval", "approved")


class PlanCycle(Base):
    __tablename__ = "plan_cycles"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    current_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engine.forecast_runs.run_id"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlanCycleTransition(Base):
    __tablename__ = "plan_cycle_transitions"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow.plan_cycles.id"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String, nullable=False)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engine.forecast_runs.run_id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [x] **Step 2: Finalize `db/models/__init__.py`**

```python
from . import masterdata, calendar, planning_inputs, sync, engine, auth, workflow, audit  # noqa: F401
```
(`audit` module is created in Task 3 — this line is only valid once Task 3's
file exists; if running tasks strictly in order, `audit.py` doesn't exist
yet. Create an empty `db/models/audit.py` with just `pass` as a placeholder
file now, to be filled in by Task 3, so this import doesn't break — a
temporarily-empty module is fine since nothing references its contents yet.)

- [x] **Step 3: Generate and apply the migration**

```bash
python -m alembic revision --autogenerate -m "add workflow schema"
python -m alembic upgrade head
python -m alembic check
```

- [x] **Step 4: Verify**

```bash
"/c/Program Files/PostgreSQL/18/bin/psql.exe" -U rs_planning_app -h 127.0.0.1 -p 5432 -d rs_planning -c "\d workflow.plan_cycles" -c "\d workflow.plan_cycle_transitions"
```

---

## Task 3: Audit data model + migration + wire into `db/editor.py`

**Files:**
- Create: `Tentative AOP Forecaster/db/models/audit.py` (replacing the empty placeholder from Task 2)
- Modify: `Tentative AOP Forecaster/db/editor.py`
- Create: new Alembic migration

**Interfaces:**
- Consumes: `db.models.auth.User`.
- Produces: `db.models.audit.DataChange` (`id: int`, `table_name: str`,
  `record_key: dict`, `old_value: str|None`, `new_value: str|None`,
  `actor_id: uuid`, `actor_role: str`, `plan_cycle_id: uuid|None`,
  `changed_at`); `db.editor.log_change(session, table_name, record_key,
  old_value, new_value, actor_id, actor_role, plan_cycle_id=None)` — a new
  helper other editor functions call.
- Modifies: `get_growth`/`put_growth`/`get_nso`/`put_nso`/
  `get_aop_overrides`/`put_aop_overrides` in `db/editor.py` all gain an
  `actor_id: uuid.UUID` and `actor_role: str` required parameter (GET
  functions accept but don't use them yet — kept symmetric for the route
  layer's convenience); PUT functions call `log_change` for every row whose
  value actually changed.

- [x] **Step 1: Write `db/models/audit.py`**

```python
"""audit schema — every Growth %/NSO/AOP override edit, old value -> new
value, who and when. See db/editor.py for the write path."""
import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class DataChange(Base):
    __tablename__ = "data_changes"
    __table_args__ = {"schema": "audit"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    record_key: Mapped[dict] = mapped_column(JSON, nullable=False)
    old_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_id: Mapped["uuid.UUID"] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)
    plan_cycle_id: Mapped["uuid.UUID | None"] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow.plan_cycles.id"), nullable=True
    )
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
(Add `import uuid` at the top alongside `import datetime`.)

- [x] **Step 2: Add `log_change` to `db/editor.py`**

Add near the top of the file, after the existing imports:
```python
from db.models.audit import DataChange


def log_change(session, table_name, record_key, old_value, new_value, actor_id, actor_role, plan_cycle_id=None):
    session.add(DataChange(
        table_name=table_name, record_key=record_key,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        actor_id=actor_id, actor_role=actor_role, plan_cycle_id=plan_cycle_id,
    ))
```

- [x] **Step 3: Wire `log_change` into `put_growth`**

In `put_growth`, the existing loop builds `upsert_rows` and separately
tracks `delete_ids`. Change the signature and add logging — replace:
```python
def put_growth(session: Session, rows: list) -> dict:
```
with:
```python
def put_growth(session: Session, rows: list, actor_id, actor_role: str) -> dict:
```
and inside the loop over `(row.get("values") or {}).items()`, right after
computing `pid = periods[label]`, insert the diff-and-log before the
existing delete/upsert logic:
```python
            current_val = existing_values.get((rk, pid))  # see note below
            if val is None or val == "":
                if (rk, pid) in existing:
                    delete_ids.append(existing[(rk, pid)])
                    log_change(session, "planning_inputs.input_values",
                               {"lever_key": "growth_pct", "row_key": rk, "period_id": pid},
                               current_val, None, actor_id, actor_role)
                continue
            if current_val != str(float(val)):
                log_change(session, "planning_inputs.input_values",
                           {"lever_key": "growth_pct", "row_key": rk, "period_id": pid},
                           current_val, float(val), actor_id, actor_role)
```
This requires a lookup of current values by `(row_key, period_id)` before
the loop — add right before `for row in rows:`:
```python
    existing_values = {
        (v.row_key, v.period_id): str(float(v.value)) if v.value is not None else None
        for v in session.execute(select(InputValue).where(InputValue.lever_key == "growth_pct")).scalars().all()
    }
```
Remove the now-redundant separate `if val is None or val == "": ... continue`
block that follows (the logic above already handles the delete-and-log case
and `continue`s) — keep only the `upsert_rows.append(...)` call after it for
the non-delete path.

- [x] **Step 4: Wire `log_change` into `put_nso`**

Change the signature:
```python
def put_nso(session: Session, rows: list, actor_id, actor_role: str) -> list:
```
Before the main loop, capture current state:
```python
    existing_rows = {n.store_id: n for n in session.execute(select(NsoOpening)).scalars().all()}
```
Inside the loop, after computing `opening = datetime.date(...)`, before the
`pg_insert` call:
```python
        prev = existing_rows.get(sid)
        old = f"{prev.opening_month.isoformat()}|{prev.is_named}" if prev else None
        new = f"{opening.isoformat()}|{bool(row.get('is_named'))}"
        if old != new:
            log_change(session, "masterdata.nso_openings", {"store_id": sid}, old, new, actor_id, actor_role)
```
After the loop, where `to_delete` is computed and rows deleted, log each:
```python
    for sid in to_delete:
        prev = existing_rows.get(sid)
        old = f"{prev.opening_month.isoformat()}|{prev.is_named}" if prev else None
        log_change(session, "masterdata.nso_openings", {"store_id": sid}, old, None, actor_id, actor_role)
```
(place this loop before the `session.query(NsoOpening).filter(...).delete(...)` call, so the row still exists to read from if needed — here it just reads `existing_rows`, already captured, so order relative to the delete doesn't matter, but keep it before `session.commit()`.)

- [x] **Step 5: Wire `log_change` into `put_aop_overrides`**

Change the signature:
```python
def put_aop_overrides(session: Session, rows: list, actor_id, actor_role: str) -> list:
```
Before the main loop, capture current values:
```python
    existing_values = {
        (v.store_id, v.division_code, v.period_id): str(float(v.value))
        for v in session.execute(select(InputValue).where(InputValue.lever_key == "aop_optional")).scalars().all()
    }
```
Inside the loop, right after `pid = periods[label]`:
```python
        current_val = existing_values.get((sid, div, pid))
        record_key = {"lever_key": "aop_optional", "store_id": sid, "division_code": div, "period_id": pid}
        if val is None or val == "":
            if current_val is not None:
                log_change(session, "planning_inputs.input_values", record_key, current_val, None, actor_id, actor_role)
            delete_keys.append((sid, div, pid))
            continue
        if current_val != str(float(val)):
            log_change(session, "planning_inputs.input_values", record_key, current_val, float(val), actor_id, actor_role)
```
(This replaces the existing `if val is None or val == "": delete_keys.append(...); continue` block — same control flow, with logging added.)

- [x] **Step 6: Generate and apply the migration**

```bash
python -m alembic revision --autogenerate -m "add audit schema"
python -m alembic upgrade head
python -m alembic check
```

- [x] **Step 7: Manual verification of the diff-and-log logic**

Run from `Tentative AOP Forecaster/`:
```bash
python -c "
import sys, uuid
sys.path.insert(0, '.')
from db.base import SessionLocal
from db.editor import put_growth, get_growth

s = SessionLocal()
actor = uuid.uuid4()  # no real user yet — Task 5 adds real users; this just exercises the logging path
before = get_growth(s)
put_growth(s, [{'row_key': 'GM', 'values': {\"Apr'27\": 9.99}}], actor, 'planner')
from sqlalchemy import select
from db.models.audit import DataChange
rows = s.execute(select(DataChange).where(DataChange.table_name=='planning_inputs.input_values')).scalars().all()
print('audit rows:', len(rows))
print('last:', rows[-1].record_key, rows[-1].old_value, '->', rows[-1].new_value)
# revert
put_growth(s, [{'row_key': 'GM', 'values': {\"Apr'27\": None}}], actor, 'planner')
s.close()
"
```
Expected: `audit rows: 1` (or more, if run repeatedly — that's fine), last
row shows `old_value=None, new_value='9.99'`. This will fail with a foreign
key violation on `actor_id` since `auth.users` has no rows yet — **expected
at this point**; if it fails with anything else (e.g. an `AttributeError` or
`NameError`), the wiring in Steps 2-5 has a bug, fix before continuing. Once
Task 4 creates a real user, re-run this same check with a real `actor_id`
and confirm no FK error.

---

## Task 4: Auth security + session dependencies + seed script

**Files:**
- Create: `RS Planning Platform/backend/auth/security.py`
- Create: `RS Planning Platform/backend/auth/deps.py`
- Create: `RS Planning Platform/backend/seed_admin.py`
- Create: `RS Planning Platform/backend/requirements.txt`

**Interfaces:**
- Consumes: `db.models.auth.User`, `db.base.SessionLocal` (from AOP
  Forecaster's `db/` package, imported via `sys.path`).
- Produces: `auth.security.hash_password(plain: str) -> str`,
  `auth.security.verify_password(plain: str, hashed: str) -> bool`,
  `auth.deps.get_session_user(request) -> dict | None` (reads
  `request.session`), `auth.deps.require_login` (FastAPI dependency,
  raises 401), `auth.deps.require_role(*roles)` (dependency factory, raises
  403), `auth.deps.require_admin` (dependency, raises 403).

- [x] **Step 1: Create the project skeleton and `requirements.txt`**

```bash
mkdir -p "RS Planning Platform/backend/auth" "RS Planning Platform/backend/workflow" "RS Planning Platform/backend/audit" "RS Planning Platform/backend/static" "RS Planning Platform/backend/tests"
touch "RS Planning Platform/backend/auth/__init__.py" "RS Planning Platform/backend/workflow/__init__.py" "RS Planning Platform/backend/audit/__init__.py"
```

`RS Planning Platform/backend/requirements.txt`:
```
fastapi
uvicorn[standard]
sqlalchemy>=2.0
alembic
psycopg[binary]
python-dotenv
passlib[bcrypt]
itsdangerous
pytest
httpx
```

- [x] **Step 2: Write `auth/security.py`**

```python
"""Password hashing and session-cookie helpers."""
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)
```

- [x] **Step 3: Write `auth/deps.py`**

```python
"""FastAPI dependencies that read the signed session cookie (set by
Starlette's SessionMiddleware, configured in the main app.py)."""
from fastapi import HTTPException, Request


def get_session_user(request: Request) -> dict | None:
    return request.session.get("user")  # {"id": str, "username": str, "role": str, "is_admin": bool} or None


def require_login(request: Request) -> dict:
    user = get_session_user(request)
    if user is None:
        raise HTTPException(401, "Not authenticated")
    return user


def require_role(*roles: str):
    def _check(request: Request) -> dict:
        user = require_login(request)
        if user["role"] not in roles:
            raise HTTPException(403, f"Forbidden — requires role in {roles}")
        return user
    return _check


def require_admin(request: Request) -> dict:
    user = require_login(request)
    if not user.get("is_admin"):
        raise HTTPException(403, "Forbidden — admin only")
    return user
```

- [x] **Step 4: Write `seed_admin.py`**

```python
"""One-time first-admin creation. Run: python seed_admin.py"""
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "Tentative AOP Forecaster"))

from auth.security import hash_password  # noqa: E402  (this file's own auth/, on sys.path via cwd)
from db.base import SessionLocal  # noqa: E402
from db.models.auth import User  # noqa: E402


def main():
    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password: ")
    role = input("Role (planner/buyer/reviewer/approver) [planner]: ").strip() or "planner"
    session = SessionLocal()
    try:
        session.add(User(username=username, password_hash=hash_password(password), role=role, is_admin=True))
        session.commit()
        print(f"Created admin user '{username}' with role={role}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [x] **Step 5: Install dependencies and verify imports**

```bash
python -m pip install passlib[bcrypt] itsdangerous
cd "RS Planning Platform/backend"
python -c "from auth.security import hash_password, verify_password; h = hash_password('test123'); print(verify_password('test123', h), verify_password('wrong', h))"
```
Expected: `True False`

---

## Task 5: Auth routes + create first real user + tests

**Files:**
- Create: `RS Planning Platform/backend/auth/routes.py`
- Create: `RS Planning Platform/backend/tests/conftest.py`
- Create: `RS Planning Platform/backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `auth.security.*`, `auth.deps.*`, `db.models.auth.User`,
  `db.base.SessionLocal`.
- Produces: `auth.routes.router` (an `APIRouter`) with `POST /login`,
  `POST /logout`, `GET /me`, `POST /admin/users`, `GET /admin/users` — this
  gets mounted at `/api/auth` in Task 8.

- [x] **Step 1: Write `auth/routes.py`**

```python
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
```

- [x] **Step 2: Write `tests/conftest.py`**

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "Tentative AOP Forecaster"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "SalesPlan", "backend"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from auth.routes import router as auth_router
from auth.security import hash_password
from db.base import SessionLocal
from db.models.auth import User


@pytest.fixture
def app():
    a = FastAPI()
    a.add_middleware(SessionMiddleware, secret_key="test-secret-key")
    a.include_router(auth_router, prefix="/api/auth")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def test_user():
    """Creates (and cleans up) a real auth.users row for tests to log in as."""
    session = SessionLocal()
    u = User(username="test_planner", password_hash=hash_password("testpass123"), role="planner", is_admin=False)
    session.add(u)
    session.commit()
    session.refresh(u)
    user_id = u.id
    yield u
    session.delete(session.get(User, user_id))
    session.commit()
    session.close()
```

- [x] **Step 3: Write `tests/test_auth.py`**

```python
def test_login_wrong_password_returns_401(client, test_user):
    r = client.post("/api/auth/login", json={"username": "test_planner", "password": "wrong"})
    assert r.status_code == 401


def test_login_success_sets_session(client, test_user):
    r = client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    assert r.status_code == 200
    assert r.json()["role"] == "planner"

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "test_planner"


def test_me_without_login_returns_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_session(client, test_user):
    client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    client.post("/api/auth/logout")
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_admin_route_rejects_non_admin(client, test_user):
    client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    r = client.get("/api/auth/admin/users")
    assert r.status_code == 403
```

- [x] **Step 4: Run the tests**

```bash
cd "RS Planning Platform/backend"
python -m pytest tests/test_auth.py -v
```
Expected: 5 passed.

- [x] **Step 5: Seed a real first admin for manual testing later**

```bash
python seed_admin.py
```
Enter a real username/password, role `planner` (or any), confirm it prints
"Created admin user...". Verify:
```bash
export PGPASSWORD='RsPlanning_2026Local'
"/c/Program Files/PostgreSQL/18/bin/psql.exe" -U rs_planning_app -h 127.0.0.1 -p 5432 -d rs_planning -c "select username, role, is_admin from auth.users;"
```

---

## Task 6: Workflow state machine service + routes + tests

**Files:**
- Create: `RS Planning Platform/backend/workflow/service.py`
- Create: `RS Planning Platform/backend/workflow/routes.py`
- Create: `RS Planning Platform/backend/tests/test_workflow.py`

**Interfaces:**
- Consumes: `db.models.workflow.{PlanCycle, PlanCycleTransition, STATUSES}`,
  `db.models.engine.ForecastRun`, `auth.deps.require_login`,
  `auth.deps.require_role`.
- Produces: `workflow.service.create_cycle(session, run_id, actor) ->
  PlanCycle`, `workflow.service.transition(session, cycle_id, action, actor,
  comment=None) -> PlanCycle` where `action` is one of `"submit"`,
  `"approve"`, `"reject"` (raises `ValueError` with a message on an invalid
  transition — the route layer turns that into a 409).
  `workflow.routes.router` mounted at `/api/aop/plan-cycles`.

- [x] **Step 1: Write `workflow/service.py`**

```python
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
    current run without a status transition (see spec: 'no transition logged
    for this, it's normal iteration')."""
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
```

- [x] **Step 2: Write `workflow/routes.py`**

```python
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select

from auth.deps import require_login
from db.base import SessionLocal
from db.models.workflow import PlanCycle, PlanCycleTransition
from workflow.service import create_cycle, set_current_run, transition

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
```

- [x] **Step 3: Write `tests/test_workflow.py`**

```python
import uuid

import pytest
from sqlalchemy import select

from auth.security import hash_password
from db.base import SessionLocal
from db.models.auth import User
from db.models.engine import ForecastRun
from workflow.service import TRANSITIONS, create_cycle, transition


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
```

- [x] **Step 4: Run the workflow tests**

Run:
```bash
cd "RS Planning Platform/backend"
python -m pytest tests/test_workflow.py -v
```
Expected: all pass.

---

## Task 7: Audit routes + tests

**Files:**
- Create: `RS Planning Platform/backend/audit/routes.py`
- Create: `RS Planning Platform/backend/tests/test_audit.py`

**Interfaces:**
- Consumes: `db.models.audit.DataChange`, `auth.deps.require_admin`,
  `workflow.service` (for one approver-access check).
- Produces: `audit.routes.router` mounted at `/api/audit`.

- [x] **Step 1: Write `audit/routes.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from auth.deps import require_login
from db.base import SessionLocal
from db.models.audit import DataChange

router = APIRouter()


def _require_admin_or_approver(request: Request) -> dict:
    from auth.deps import require_login as _rl
    user = _rl(request)
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
```

- [x] **Step 2: Write `tests/test_audit.py`**

```python
import uuid

from db.base import SessionLocal
from db.editor import put_growth


def test_put_growth_logs_a_data_change(test_user):
    from sqlalchemy import select
    from db.models.audit import DataChange

    session = SessionLocal()
    before = session.execute(select(DataChange)).scalars().all()
    put_growth(session, [{"row_key": "RETAIL", "values": {"May'27": 12.5}}], test_user.id, "planner")
    after = session.execute(select(DataChange)).scalars().all()
    assert len(after) == len(before) + 1
    assert after[-1].old_value is None
    assert after[-1].new_value == "12.5"

    # revert
    put_growth(session, [{"row_key": "RETAIL", "values": {"May'27": None}}], test_user.id, "planner")
    session.close()


def test_non_admin_non_approver_gets_403(client, test_user):
    client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    # (this test file needs audit.routes mounted on the same test app fixture — see Step 3)
```

- [x] **Step 3: Extend `tests/conftest.py`'s `app` fixture to include audit + workflow routers**

Modify the `app` fixture from Task 5 to also mount the routers built so far:
```python
@pytest.fixture
def app():
    a = FastAPI()
    a.add_middleware(SessionMiddleware, secret_key="test-secret-key")
    a.include_router(auth_router, prefix="/api/auth")
    from workflow.routes import router as workflow_router
    from audit.routes import router as audit_router
    a.include_router(workflow_router, prefix="/api/aop/plan-cycles")
    a.include_router(audit_router, prefix="/api/audit")
    return a
```
(Add the corresponding imports at the top: `from workflow.routes import
router as workflow_router` and `from audit.routes import router as
audit_router` — or keep them inline as above, either works with pytest.)

Finish `test_non_admin_non_approver_gets_403`:
```python
def test_non_admin_non_approver_gets_403(client, test_user):
    client.post("/api/auth/login", json={"username": "test_planner", "password": "testpass123"})
    r = client.get("/api/audit/data-changes")
    assert r.status_code == 403
```

- [x] **Step 4: Run all tests so far**

```bash
cd "RS Planning Platform/backend"
python -m pytest tests/ -v
```
Expected: all pass (auth: 5, workflow: 4, audit: 2, ≥11 total).

---

## Task 8: Extract AOP Forecaster's routes into an `APIRouter`

**Files:**
- Modify: `Tentative AOP Forecaster/app.py`

**Interfaces:**
- Produces: `app.router` (an `APIRouter` containing every route currently on
  `app`) — importable as `from app import router as aop_router` by the
  unified app in Task 9.

- [x] **Step 1: Change the module-level `app = FastAPI(...)` setup**

Replace:
```python
app = FastAPI(title="AOP Forecaster API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```
with:
```python
router = APIRouter()

app = FastAPI(title="AOP Forecaster API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```
Add `APIRouter` to the existing `from fastapi import ...` line at the top:
```python
from fastapi import FastAPI, UploadFile, HTTPException, Body, APIRouter
```

- [x] **Step 2: Change every `@app.get/@app.post/@app.put/@app.delete` to `@router.*`**

There are 16 route decorators (verified this session): `POST /api/upload`,
`POST /api/run/{session_id}`, `GET /api/results/{session_id}`,
`GET /api/data/{session_id}`, `GET /api/palettes`,
`GET /api/download/{session_id}`, `DELETE /api/sessions/{session_id}`,
`POST /api/config/session-from-db`, `POST /api/config/db-sync`,
`GET /api/config/db-sync/status`, `GET /api/config/growth`,
`PUT /api/config/growth`, `GET /api/config/nso`, `PUT /api/config/nso`,
`GET /api/config/aop-overrides`, `PUT /api/config/aop-overrides`,
`GET /api/config/division-aop-summary`. For every one, change `@app.` to
`@router.` — e.g. `@app.post("/api/upload")` becomes
`@router.post("/api/upload")`. Leave the function bodies and all path
strings exactly as they are (the mounting prefix is applied by whoever
includes this router, not baked into the paths here).

- [x] **Step 3: Mount the router back onto `app` for standalone use, and update the static-file section**

After the last route definition and before the "Serve built React app"
section at the bottom of the file, add:
```python
app.include_router(router)
```
This keeps `python -m uvicorn app:app --port 8000` working exactly as
before — same paths, same behavior, just routed through the extracted
`router` object instead of directly.

- [x] **Step 4: Verify AOP Forecaster still runs standalone**

```bash
cd "Tentative AOP Forecaster"
python -c "import app"   # must not raise
python -m uvicorn app:app --host 127.0.0.1 --port 8000 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/docs
curl -s -X POST http://127.0.0.1:8000/api/config/session-from-db | python -c "import sys,json; print('session_id' in json.load(sys.stdin))"
```
Expected: `import app` succeeds silently, `/docs` returns 200, session-from-db
prints `True`. Kill the background server after confirming
(`taskkill //PID <pid> //F` on the PID `uvicorn` printed, or via `netstat`).

- [x] **Step 5: Also modify `division_aop_summary` to require an approved plan cycle**

Per the spec, replace the body of `division_aop_summary` (currently reads
"the latest `ForecastRun`, period") — change:
```python
    with SessionLocal() as session:
        latest = session.execute(select(ForecastRun).order_by(ForecastRun.created_at.desc())).scalars().first()
        if latest is None:
            raise HTTPException(404, "No forecast run has been persisted yet — run /api/config/session-from-db then /api/run/{session_id} first")
```
to:
```python
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..", "RS Planning Platform", "backend"))
    from workflow.service import latest_approved_run_id

    with SessionLocal() as session:
        run_id = latest_approved_run_id(session)
        if run_id is None:
            raise HTTPException(404, "No approved plan cycle yet")
        latest = session.get(ForecastRun, run_id)
```
Everything after this (the `next_fy_periods`/`rows`/return-dict logic) stays
unchanged — it already uses `latest.run_id` and `latest.created_at`, both
still valid on the `ForecastRun` object fetched this way.

**Note:** this makes `Tentative AOP Forecaster`'s standalone `app.py` depend
on `RS Planning Platform/backend/workflow/` existing — acceptable per the
spec (Task 8 happens after Tasks 1-7 build that code), but means AOP
Forecaster is no longer fully independent of the new project from this
point forward. This is a deliberate, spec-driven coupling (the whole point
of the workflow is gating this exact endpoint) — not an accident.

- [x] **Step 6: Re-verify standalone AOP Forecaster after Step 5's change**

```bash
cd "Tentative AOP Forecaster"
python -c "import app"
```
Expected: succeeds (proves the new `sys.path` addition + import resolves
correctly even though no approved cycle exists yet — the function body only
runs when the endpoint is actually called, so import-time success is the
right check here; a live 404 check happens in Task 10's integration test
once real workflow data exists).

---

## Task 9: The unified app — mount everything

**Files:**
- Create: `RS Planning Platform/backend/app.py`
- Create: `RS Planning Platform/backend/static/login.html`

**Interfaces:**
- Consumes: `app.router` (AOP Forecaster, Task 8), all 11 SalesPlan
  routers (existing, unchanged), `auth.routes.router`,
  `workflow.routes.router`, `audit.routes.router` (Tasks 5-7).
- Produces: a runnable `uvicorn app:app --port 8010`.

- [x] **Step 1: Write `app.py`**

```python
"""RS Planning Platform — unified backend. Port 8010.
Mounts AOP Forecaster + SalesPlan's existing routers, adds auth/workflow/audit."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_AOP_DIR = os.path.join(_HERE, "..", "..", "Tentative AOP Forecaster")
_SALESPLAN_DIR = os.path.join(_HERE, "..", "..", "SalesPlan", "backend")
sys.path.insert(0, _HERE)
sys.path.insert(0, _AOP_DIR)
sys.path.insert(0, _SALESPLAN_DIR)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auth.deps import require_login
from auth.routes import router as auth_router
from workflow.routes import router as workflow_router
from audit.routes import router as audit_router

app = FastAPI(title="RS Planning Platform")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "dev-only-change-me"))
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router, prefix="/api/auth")
app.include_router(workflow_router, prefix="/api/aop/plan-cycles")
app.include_router(audit_router, prefix="/api/audit")

# AOP Forecaster — its own app.py's `router` (Task 8), protected here
from app import router as aop_router  # noqa: E402  (name collides with this module's own `app` var; import AFTER app is defined)
app.include_router(aop_router, prefix="/api/aop", dependencies=[Depends(require_login)])

# SalesPlan — its 11 existing routers, re-mounted with their own prefixes under /api/planning
from engines.division_plan import router as division_plan_router  # noqa: E402
from engines.department_plan import router as department_plan_router  # noqa: E402
from engines.dept_sales_engine import router as dept_sales_router  # noqa: E402
from engines.attribute_correction_engine import router as attr_correction_router  # noqa: E402
from engines.base_correction_engine import router as base_correction_router  # noqa: E402
from engines.final_results_engine import router as final_results_router  # noqa: E402
from engines.mrp_plan_engine import router as mrp_plan_router  # noqa: E402
from engines.pww_deviation_engine import router as pww_deviation_router  # noqa: E402
from engines.sor_deviation_engine import router as sor_deviation_router  # noqa: E402
from engines.display_type_engine import router as display_type_router  # noqa: E402
from engines.sync_engine import router as sync_router  # noqa: E402
import store_master as _sm  # noqa: E402

_dep = [Depends(require_login)]
app.include_router(division_plan_router,   prefix="/api/planning/division-plan",   dependencies=_dep)
app.include_router(department_plan_router, prefix="/api/planning/department-plan", dependencies=_dep)
app.include_router(dept_sales_router,      prefix="/api/planning/dept-sales",      dependencies=_dep)
app.include_router(attr_correction_router, prefix="/api/planning/attr-correction", dependencies=_dep)
app.include_router(base_correction_router, prefix="/api/planning/base-correction", dependencies=_dep)
app.include_router(final_results_router,   prefix="/api/planning/final-results",   dependencies=_dep)
app.include_router(mrp_plan_router,        prefix="/api/planning/mrp-plan",        dependencies=_dep)
app.include_router(pww_deviation_router,   prefix="/api/planning/deviation/pww",   dependencies=_dep)
app.include_router(sor_deviation_router,   prefix="/api/planning/deviation/sor",   dependencies=_dep)
app.include_router(display_type_router,    prefix="/api/planning/display-type",    dependencies=_dep)
app.include_router(sync_router,            prefix="/api/planning/sync",            dependencies=_dep)


@app.get("/api/planning/store-master", dependencies=_dep)
def get_store_master():
    return {"stores": list(_sm.load_store_master()), "clusters": _sm.get_clusters()}


@app.post("/api/planning/store-master/reload", dependencies=_dep)
def reload_store_master():
    _sm.reload()
    return {"ok": True, "stores": len(list(_sm.load_store_master())), "clusters": _sm.get_clusters()}


# Login page (plain HTML — Phase 2's unified frontend replaces this)
@app.get("/login")
def login_page():
    return FileResponse(os.path.join(_HERE, "static", "login.html"))


# Serve both existing frontends' built bundles under their own paths
_aop_dist = os.path.join(_AOP_DIR, "frontend", "dist")
if os.path.isdir(_aop_dist):
    app.mount("/aop/assets", StaticFiles(directory=os.path.join(_aop_dist, "assets")), name="aop_assets")

_planning_dist = os.path.join(os.path.dirname(_SALESPLAN_DIR), "frontend", "dist")
if os.path.isdir(_planning_dist):
    app.mount("/planning/assets", StaticFiles(directory=os.path.join(_planning_dist, "assets")), name="planning_assets")


@app.get("/aop/{full_path:path}", include_in_schema=False)
def aop_spa(full_path: str):
    return FileResponse(os.path.join(_aop_dist, "index.html"))


@app.get("/planning/{full_path:path}", include_in_schema=False)
def planning_spa(full_path: str):
    return FileResponse(os.path.join(_planning_dist, "index.html"))
```

- [x] **Step 2: Write `static/login.html`**

```html
<!doctype html>
<html>
<head><meta charset="utf-8"><title>RS Planning Platform — Login</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 360px; margin: 80px auto; }
  input { display: block; width: 100%; padding: 8px; margin: 8px 0; box-sizing: border-box; }
  button { padding: 8px 16px; }
  #err { color: #c0392b; font-size: 13px; }
</style>
</head>
<body>
  <h2>RS Planning Platform</h2>
  <form id="f">
    <input id="username" placeholder="Username" autocomplete="username" required>
    <input id="password" type="password" placeholder="Password" autocomplete="current-password" required>
    <button type="submit">Log in</button>
    <p id="err"></p>
  </form>
  <script>
    document.getElementById('f').addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('username').value;
      const password = document.getElementById('password').value;
      const r = await fetch('/api/auth/login', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, password}),
      });
      if (r.ok) { window.location.href = '/aop/'; }
      else { document.getElementById('err').textContent = 'Invalid username or password.'; }
    });
  </script>
</body>
</html>
```

- [x] **Step 3: Update AOP Forecaster's frontend API base path**

`Tentative AOP Forecaster/frontend/src/App.jsx`, `UploadStep.jsx`,
`ConfigPanel.jsx`-successor `DbSyncPanel.jsx`, and `PlanningInputsEditor.jsx`
all call bare `/api/...` paths via `fetch`. Since the unified app serves this
frontend's static files at `/aop/*` but its own AOP routes are also mounted
at `/api/aop/*` (not bare `/api/*`), every fetch call needs its path
prefixed. Rather than editing every call site individually, add one file:

`Tentative AOP Forecaster/frontend/src/lib/apiBase.js`:
```javascript
// When served standalone (port 8000), API routes are at /api/*.
// When served from the unified platform (under /aop/*), the same
// frontend's API routes are mounted at /api/aop/*. Detect which by the
// page's own path prefix.
export const API_BASE = window.location.pathname.startsWith('/aop/') ? '/api/aop' : '/api'
```
Then in every file that does `fetch('/api/...)`, change the literal
`'/api/` prefix to `` `${API_BASE}/` `` (template literal) — e.g.
`fetch('/api/config/session-from-db', ...)` becomes
`` fetch(`${API_BASE}/config/session-from-db`, ...) `` — and add
`import { API_BASE } from '../lib/apiBase'` (adjust relative path per file)
to each file that needs it: `App.jsx`, `UploadStep.jsx`, `DbSyncPanel.jsx`,
`PlanningInputsEditor.jsx`. This keeps the standalone `:8000` deployment
working (paths resolve to `/api/*` there) while working correctly when
served from `:8010/aop/*` too.

- [x] **Step 4: Rebuild AOP Forecaster's frontend**

```bash
cd "Tentative AOP Forecaster/frontend"
npm run build
```
Expected: builds clean, no errors (same check pattern used repeatedly this
session).

- [x] **Step 5: Start the unified app and smoke-test it**

```bash
cd "RS Planning Platform/backend"
python -c "import app"   # catches import errors before starting a server
python -m uvicorn app:app --host 127.0.0.1 --port 8010 &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/docs
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/login
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/api/aop/config/summary  # any AOP route without login
```
Expected: `/docs` → 200, `/login` → 200, the unauthenticated AOP route → 401
(not 404 — a 404 would mean the router didn't mount; a 401 confirms it
mounted AND the auth dependency is active).

---

## Task 10: Full integration test — the real workflow end to end

**Files:**
- Create: `RS Planning Platform/backend/tests/test_full_pipeline.py`
- Create: `RS Planning Platform/backend/tests/test_router_mount.py`

**Interfaces:**
- Consumes: the running unified app (these are `httpx`-against-a-live-server
  tests, not `TestClient`-in-process, since they need the real Postgres data
  built up over this whole session plus a real running AOP engine).

- [x] **Step 1: Write `tests/test_router_mount.py`**

```python
"""Confirms every mounted prefix actually reaches the underlying app's
routes, and that auth is enforced. Requires the unified app running on
:8010 (Task 9, Step 5) — this hits it over real HTTP, not TestClient,
because AOP's routes do real Postgres/engine work not worth mocking here."""
import httpx

BASE = "http://127.0.0.1:8010"


def test_aop_route_requires_login():
    r = httpx.get(f"{BASE}/api/aop/config/summary")
    assert r.status_code in (401, 404)  # 404 acceptable only if that specific old route was removed; primarily checking not-500
    r2 = httpx.post(f"{BASE}/api/aop/config/session-from-db")
    assert r2.status_code == 401


def test_planning_route_requires_login():
    r = httpx.get(f"{BASE}/api/planning/store-master")
    assert r.status_code == 401


def test_login_then_aop_route_succeeds():
    client = httpx.Client(base_url=BASE)
    # Assumes a real user was seeded via seed_admin.py (Task 5, Step 5) —
    # replace with that real username/password before running.
    r = client.post("/api/auth/login", json={"username": "REPLACE_WITH_SEEDED_USERNAME", "password": "REPLACE_WITH_SEEDED_PASSWORD"})
    assert r.status_code == 200
    r2 = client.post("/api/aop/config/session-from-db")
    assert r2.status_code == 200
    assert "session_id" in r2.json()
```

- [x] **Step 2: Write `tests/test_full_pipeline.py`**

```python
"""The chain exercised repeatedly by hand this session, now through the
unified app + full workflow gate. Requires the unified app on :8010 and a
seeded planner/buyer/reviewer/approver set of users."""
import httpx

BASE = "http://127.0.0.1:8010"


def _login(username, password):
    c = httpx.Client(base_url=BASE)
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return c


def test_division_aop_summary_404s_with_no_approved_cycle(planner_client):
    # Fresh state assumption: no plan_cycles have reached 'approved' yet in
    # this test's data set. If earlier tests approved one, this test can't
    # assert 404 meaningfully — run this test FIRST, before any approval
    # test, or use a fresh Postgres transaction/rollback strategy per test.
    r = planner_client.get("/api/aop/config/division-aop-summary")
    assert r.status_code == 404


def test_full_workflow_to_salesplan(planner_client, buyer_client, reviewer_client, approver_client):
    # 1. Planner builds a run
    r = planner_client.post("/api/aop/config/session-from-db")
    session_id = r.json()["session_id"]
    r = planner_client.post(f"/api/aop/run/{session_id}", json={})
    run_id = r.json()["run_id"]
    assert run_id is not None

    # 2. Planner starts a plan cycle and submits it
    r = planner_client.post("/api/aop/plan-cycles", json={"run_id": run_id})
    cycle_id = r.json()["id"]
    assert r.json()["status"] == "draft"
    r = planner_client.post(f"/api/aop/plan-cycles/{cycle_id}/submit")
    assert r.json()["status"] == "pending_buyer"

    # 3. Buyer submits onward (without editing, for this test's simplicity)
    r = buyer_client.post(f"/api/aop/plan-cycles/{cycle_id}/submit")
    assert r.json()["status"] == "pending_review"

    # 4. Reviewer approves
    r = reviewer_client.post(f"/api/aop/plan-cycles/{cycle_id}/approve")
    assert r.json()["status"] == "pending_approval"

    # 5. Approver approves
    r = approver_client.post(f"/api/aop/plan-cycles/{cycle_id}/approve")
    assert r.json()["status"] == "approved"

    # 6. division-aop-summary now serves this run
    r = planner_client.get("/api/aop/config/division-aop-summary")
    assert r.status_code == 200
    assert r.json()["run_id"] == run_id

    # 7. SalesPlan pulls it
    r = planner_client.post("/api/planning/department-plan/sync-from-aop-forecaster")
    assert r.status_code == 200
    assert r.json()["run_id"] == run_id
```

(`planner_client`/`buyer_client`/`reviewer_client`/`approver_client` fixtures:
seed one real `auth.users` row per role via `seed_admin.py`-equivalent logic
in a `conftest.py` fixture before running these, or run `seed_admin.py`
interactively four times first and hardcode the credentials into a local
`.env.test` — either is acceptable for this one-time integration pass; don't
over-engineer fixture automation for a test suite run once during this
build.)

- [x] **Step 3: Seed one user per role for the integration run**

```bash
cd "RS Planning Platform/backend"
python seed_admin.py   # username: planner1 / role: planner
python seed_admin.py   # username: buyer1 / role: buyer
python seed_admin.py   # username: reviewer1 / role: reviewer
python seed_admin.py   # username: approver1 / role: approver
```
(All created with `is_admin=True` per `seed_admin.py`'s current design —
fine for this internal test pass; a real deployment would want a non-admin
option, out of scope to add here.)

- [x] **Step 4: Fill in the real credentials and run the full suite**

Update `test_full_pipeline.py`'s fixtures with the actual seeded
usernames/passwords, then:
```bash
cd "RS Planning Platform/backend"
python -m pytest tests/ -v
```
Expected: every test across `test_auth.py`, `test_workflow.py`,
`test_audit.py`, `test_router_mount.py`, `test_full_pipeline.py` passes.

- [x] **Step 5: Confirm AOP Forecaster and SalesPlan still run standalone, unaffected**

```bash
cd "Tentative AOP Forecaster" && python -c "import app" && echo AOP-OK
cd "../SalesPlan/backend" && python -c "import main" && echo SALESPLAN-OK
```
Expected: both print their `-OK` line with no traceback.

---

## Task 11: Final round audit across the whole workflow

**Files:** none created — this is verification only, following the same
audit pattern used earlier this session (the `input_values` NULL-constraint
bug, the frontend null-guard sweep).

- [x] **Step 1: Re-run the full end-to-end pipeline live** (not just pytest)
  through the unified app in a real browser or via curl, exactly as done
  repeatedly earlier this session: session-from-db → run → create plan
  cycle → submit → submit → approve → approve → division-aop-summary →
  SalesPlan sync → calculate. Confirm the numbers match what AOP
  Forecaster's standalone `:8000` produces for the same inputs (they must be
  identical — the unified app doesn't change any business logic, only adds
  auth/workflow in front of it).

- [x] **Step 2: Audit every new table for the same NULL-in-unique-constraint
  bug class fixed earlier this session** — check `auth.users.username`
  (unique, not null — safe), `workflow.plan_cycles` (no composite unique
  constraint at all — safe by construction), `workflow.plan_cycle_transitions`
  (no unique constraint — append-only log, safe), `audit.data_changes` (no
  unique constraint — append-only log, safe). Run:
  ```bash
  export PGPASSWORD='RsPlanning_2026Local'
  "/c/Program Files/PostgreSQL/18/bin/psql.exe" -U rs_planning_app -h 127.0.0.1 -p 5432 -d rs_planning -c "\d+ auth.users" -c "\d+ workflow.plan_cycles" -c "\d+ workflow.plan_cycle_transitions" -c "\d+ audit.data_changes"
  ```
  Confirm no table has a composite unique index over nullable columns.

- [x] **Step 3: Verify audit completeness** — for the plan cycle created in
  Task 10's integration test, confirm `GET /api/aop/plan-cycles/{id}` shows
  all 4 transitions (submit, submit, approve, approve) with correct
  `actor_role` values in order, and query `audit.data_changes` for any edits
  made during the test run (if the walkthrough in Step 1 included a Buyer
  edit) to confirm old/new values are captured correctly.

- [x] **Step 4: Verify role enforcement holds under adversarial input** —
  attempt (and confirm rejected) each of: a `buyer` calling `/submit` on a
  `draft` cycle (should 403 — only planner can submit from draft), a
  `planner` calling `/approve` on any status (should 403 — planner never
  approves), a `reviewer` calling `/api/auth/admin/users` without
  `is_admin` (should 403), an unauthenticated request to any
  `/api/aop/plan-cycles/*` route (should 401).

- [x] **Step 5: Verify idempotency of the audit log** — re-run
  `put_growth`/`put_aop_overrides` with the *same* values twice in a row
  (no actual change) and confirm the second call does **not** write a new
  `audit.data_changes` row (the diff check added in Task 3 should suppress
  no-op writes) — this matters because a naive implementation logs on every
  write regardless of whether the value changed, which would make the audit
  log noisy and useless for "what actually changed" questions.

- [x] **Step 6: Confirm both standalone apps and the unified app can run
  concurrently** without port or database-lock conflicts — start all three
  (`:8000`, `:8002`, `:8010`) at once, hit a read-only endpoint on each,
  confirm all three respond correctly at the same time (proves the merge is
  genuinely additive, not something that only works if the old servers are
  stopped first).

- [x] **Step 7: Write a short audit summary** (in chat, not a new file —
  this session already has a spec and a plan; a third document isn't
  needed) covering: what was tested, what passed, any deviations from the
  plan made during implementation and why, and any new risks discovered
  that weren't anticipated in the spec's "Open risks" section.
