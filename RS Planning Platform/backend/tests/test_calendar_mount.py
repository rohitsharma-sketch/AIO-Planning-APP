"""Requires the unified app running on :8010 (same live-server pattern as
test_router_mount.py from the AOP+SalesPlan merge)."""
import httpx

BASE = "http://127.0.0.1:8010"


def test_calendar_route_requires_login():
    r = httpx.get(f"{BASE}/api/calendar/calendar-library")
    assert r.status_code == 401


def test_login_then_calendar_route_succeeds():
    client = httpx.Client(base_url=BASE)
    r = client.post("/api/auth/login", json={"username": "planner1", "password": "PlannerPass123!"})
    assert r.status_code == 200
    r2 = client.get("/api/calendar/calendar-library")
    assert r2.status_code == 200


def test_buyer_cannot_write_calendar_data():
    client = httpx.Client(base_url=BASE)
    client.post("/api/auth/login", json={"username": "buyer1", "password": "BuyerPass123!"})
    r = client.put("/api/calendar/app-state", json={"themeId": "dark"})
    assert r.status_code == 403
