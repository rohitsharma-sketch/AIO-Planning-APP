import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "Tentative AOP Forecaster"))

import pytest
from sqlalchemy import delete, select

from db.base import SessionLocal
from db.models.calendar import ClusterProfile, ClusterProfileFestival, AppStateMeta


@pytest.fixture(autouse=True)
def _clean_cluster_profiles_and_app_state():
    # calendar.cluster_profiles / cluster_profile_festivals / app_state_meta
    # were brand-new, empty tables when this fixture was first written (Task
    # 1) — but Task 7's migrate_from_json.py has since populated them with
    # real data from Calendar Engine/Local DB/app_state.json (10 cluster
    # profiles, ~214 festivals, 1 app_state_meta row). A naive full wipe here
    # destroys that real data with nothing to restore it. Snapshot the real
    # state before the test and restore it after, same pattern as
    # test_calendar_store_cluster.py's _clean_test_stores.
    session = SessionLocal()
    backup_profiles = [
        {"id": r.id, "name": r.name, "region": r.region, "next_id": r.next_id}
        for r in session.execute(select(ClusterProfile)).scalars().all()
    ]
    backup_festivals = [
        {"id": r.id, "cluster_profile_id": r.cluster_profile_id, "source_festival_id": r.source_festival_id,
         "name": r.name, "ref_date": r.ref_date, "fut_date": r.fut_date,
         "pre": r.pre, "core": r.core, "post": r.post}
        for r in session.execute(select(ClusterProfileFestival)).scalars().all()
    ]
    backup_meta_row = session.get(AppStateMeta, 1)
    backup_meta = (
        {"active_cluster_idx": backup_meta_row.active_cluster_idx, "ref_year": backup_meta_row.ref_year,
         "fut_year": backup_meta_row.fut_year, "max_shift": backup_meta_row.max_shift,
         "mo_pri": backup_meta_row.mo_pri, "theme_id": backup_meta_row.theme_id,
         "saved_at": backup_meta_row.saved_at, "migrations": backup_meta_row.migrations}
        if backup_meta_row is not None else None
    )
    session.close()

    yield

    session = SessionLocal()
    try:
        # Full delete + reinsert restores real state regardless of what the
        # test itself created or replaced (PUT /cluster-profiles does a
        # full-table replace, same as store-cluster-map).
        session.execute(delete(ClusterProfileFestival))
        session.execute(delete(ClusterProfile))
        if backup_profiles:
            session.execute(ClusterProfile.__table__.insert(), backup_profiles)
        if backup_festivals:
            session.execute(ClusterProfileFestival.__table__.insert(), backup_festivals)

        if backup_meta is None:
            session.execute(delete(AppStateMeta).where(AppStateMeta.id == 1))
        else:
            meta_row = session.get(AppStateMeta, 1)
            if meta_row is None:
                meta_row = AppStateMeta(id=1)
                session.add(meta_row)
            meta_row.active_cluster_idx = backup_meta["active_cluster_idx"]
            meta_row.ref_year = backup_meta["ref_year"]
            meta_row.fut_year = backup_meta["fut_year"]
            meta_row.max_shift = backup_meta["max_shift"]
            meta_row.mo_pri = backup_meta["mo_pri"]
            meta_row.theme_id = backup_meta["theme_id"]
            meta_row.saved_at = backup_meta["saved_at"]
            meta_row.migrations = backup_meta["migrations"]
        session.commit()
    finally:
        # This is a real shared database holding real cluster-profile data —
        # guarantee the session (and its connection) is released even if a
        # restore statement above raises partway through.
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
