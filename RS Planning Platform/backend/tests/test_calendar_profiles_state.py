import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "Tentative AOP Forecaster"))

import pytest
from sqlalchemy import delete

from db.base import SessionLocal
from db.models.calendar import ClusterProfile, ClusterProfileFestival, AppStateMeta


@pytest.fixture(autouse=True)
def _clean_cluster_profiles_and_app_state():
    # calendar.cluster_profiles and calendar.app_state_meta are brand-new
    # tables (Task 1) with no pre-existing real data — no snapshot/restore
    # dance needed here (unlike test_calendar_store_cluster.py). Just wipe
    # whatever these tests create so runs stay isolated.
    yield
    session = SessionLocal()
    try:
        session.execute(delete(ClusterProfileFestival))
        session.execute(delete(ClusterProfile))
        session.execute(delete(AppStateMeta))
        session.commit()
    finally:
        session.close()


def test_planner_replaces_cluster_profiles(planner_client):
    payload = {"profiles": [{
        "name": "TestProfile", "region": "south", "nextId": 5,
        "festivals": [{"id": 1, "name": "Test Fest", "refDate": "2030-01-01", "futDate": "2031-01-01",
                       "pre": 1, "core": 1, "post": 1}],
    }]}
    r = planner_client.put("/api/calendar/cluster-profiles", json=payload)
    assert r.status_code == 200, r.text

    r = planner_client.get("/api/calendar/cluster-profiles")
    assert r.status_code == 200
    profiles = r.json()["profiles"]
    names = [p["name"] for p in profiles]
    assert "TestProfile" in names
    tp = next(p for p in profiles if p["name"] == "TestProfile")
    assert tp["nextId"] == 5
    assert tp["festivals"][0]["name"] == "Test Fest"


def test_planner_updates_app_state(planner_client):
    payload = {"activeClusterIdx": 2, "refYear": "2031", "futYear": "2032", "themeId": "dark"}
    r = planner_client.put("/api/calendar/app-state", json=payload)
    assert r.status_code == 200, r.text

    r = planner_client.get("/api/calendar/app-state")
    assert r.status_code == 200
    state = r.json()
    assert state["activeClusterIdx"] == 2
    assert state["themeId"] == "dark"


def test_buyer_cannot_update_app_state(buyer_client):
    r = buyer_client.put("/api/calendar/app-state", json={"themeId": "dark"})
    assert r.status_code == 403
