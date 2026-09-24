import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "Tentative AOP Forecaster"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "SalesPlan", "backend"))

# Tests write real rows (store-cluster full replace, users, audit rows), so
# they must never hit the app's DATABASE_URL. Point db.base at
# TEST_DATABASE_URL *before* it is imported (load_dotenv won't override an
# already-set env var); without a distinct TEST_DATABASE_URL, any test that
# opens a DB connection is skipped instead.
from dotenv import dotenv_values

_APP_DB_URL = os.environ.get("DATABASE_URL") or dotenv_values(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "Tentative AOP Forecaster", ".env")
).get("DATABASE_URL")
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
_DB_SAFE = bool(_TEST_DB_URL) and _TEST_DB_URL != _APP_DB_URL
if _DB_SAFE:
    os.environ["DATABASE_URL"] = _TEST_DB_URL

import pytest
from sqlalchemy import event
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from auth.routes import router as auth_router
from auth.security import hash_password
from calendar_engine.router import router as calendar_router
from db.base import SessionLocal, engine
from db.models.audit import DataChange
from db.models.auth import User

if not _DB_SAFE:
    @event.listens_for(engine, "do_connect")
    def _refuse_app_db(*args, **kwargs):
        pytest.skip("DB test skipped: set TEST_DATABASE_URL to a separate database (not the app's DATABASE_URL)")


@pytest.fixture
def app():
    a = FastAPI()
    a.add_middleware(SessionMiddleware, secret_key="test-secret-key")
    a.include_router(auth_router, prefix="/api/auth")
    from workflow.routes import router as workflow_router
    from audit.routes import router as audit_router
    a.include_router(workflow_router, prefix="/api/aop/plan-cycles")
    a.include_router(audit_router, prefix="/api/audit")
    a.include_router(calendar_router, prefix="/api/calendar")
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
    # Tests using this fixture may write audit.data_changes rows referencing
    # this user (e.g. calling db/editor.py's put_* functions) — delete those
    # first, or the FK constraint (correctly) blocks deleting the user.
    session.execute(DataChange.__table__.delete().where(DataChange.actor_id == user_id))
    session.delete(session.get(User, user_id))
    session.commit()
    session.close()


@pytest.fixture
def planner_client(client):
    session = SessionLocal()
    u = User(username="test_cal_planner", password_hash=hash_password("testpass123"), role="planner")
    session.add(u)
    session.commit()
    session.refresh(u)
    user_id = u.id
    client.post("/api/auth/login", json={"username": "test_cal_planner", "password": "testpass123"})
    yield client
    session.delete(session.get(User, user_id))
    session.commit()
    session.close()


@pytest.fixture
def buyer_client(client):
    session = SessionLocal()
    u = User(username="test_cal_buyer", password_hash=hash_password("testpass123"), role="buyer")
    session.add(u)
    session.commit()
    session.refresh(u)
    user_id = u.id
    client.post("/api/auth/login", json={"username": "test_cal_buyer", "password": "testpass123"})
    yield client
    session.delete(session.get(User, user_id))
    session.commit()
    session.close()
