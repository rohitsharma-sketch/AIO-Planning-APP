"""Confirms every mounted prefix actually reaches the underlying app's
routes, and that auth is enforced. Requires the unified app running on
:8010 (Task 9, Step 5) — this hits it over real HTTP, not TestClient,
because AOP's routes do real Postgres/engine work not worth mocking here.

Note: AOP Forecaster's router carries its own internal `/api/...` paths
(e.g. `/api/config/growth`), and is mounted here under `/api/aop`, so the
final path is `/api/aop/api/config/growth` — NOT `/api/aop/config/growth`.
Verified live against the running unified app before writing these paths."""
import httpx

BASE = "http://127.0.0.1:8010"


def test_aop_route_requires_login():
    r = httpx.get(f"{BASE}/api/aop/api/config/growth")
    assert r.status_code == 401
    r2 = httpx.post(f"{BASE}/api/aop/api/config/session-from-db")
    assert r2.status_code == 401


def test_planning_route_requires_login():
    r = httpx.get(f"{BASE}/api/planning/store-master")
    assert r.status_code == 401


def test_login_then_aop_route_succeeds():
    client = httpx.Client(base_url=BASE)
    r = client.post("/api/auth/login", json={"username": "planner1", "password": "PlannerPass123!"})
    assert r.status_code == 200
    r2 = client.post("/api/aop/api/config/session-from-db")
    assert r2.status_code == 200
    assert "session_id" in r2.json()
