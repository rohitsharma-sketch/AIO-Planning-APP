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
from db.models.audit import DataChange
from db.models.auth import User


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
