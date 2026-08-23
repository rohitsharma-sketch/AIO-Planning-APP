import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "Tentative AOP Forecaster"))

import datetime
from sqlalchemy import delete

from db.base import SessionLocal
from db.models.calendar import FestivalChangelogEntry


def test_planner_upserts_festival_changelog(planner_client):
    payload = {"rangeKey": "2030-2031", "clusterName": "TestCluster", "festivalName": "Test Festival",
               "refDate": "2030-03-01", "futDate": "2031-03-05"}
    r = planner_client.put("/api/calendar/festival-changelog", json=payload)
    assert r.status_code == 200, r.text

    r = planner_client.get("/api/calendar/festival-changelog?range_key=2030-2031")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    assert entries[0]["festivalName"] == "Test Festival"
    assert entries[0]["refDate"] == "2030-03-01"

    # Upsert same key again with a different date — must update, not duplicate
    payload["refDate"] = "2030-03-02"
    r = planner_client.put("/api/calendar/festival-changelog", json=payload)
    assert r.status_code == 200
    r = planner_client.get("/api/calendar/festival-changelog?range_key=2030-2031")
    entries = r.json()
    assert len(entries) == 1
    assert entries[0]["refDate"] == "2030-03-02"

    session = SessionLocal()
    session.execute(delete(FestivalChangelogEntry).where(FestivalChangelogEntry.range_key == "2030-2031"))
    session.commit()
    session.close()


def test_salesdata_link_selection_round_trip(planner_client):
    payload = {"months": ["2030-01", "2030-02"], "path": "\\\\test\\path", "syncedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    r = planner_client.put("/api/calendar/salesdata-link-selection/mw", json=payload)
    assert r.status_code == 200, r.text
    r = planner_client.get("/api/calendar/salesdata-link-selection/mw")
    assert r.status_code == 200
    assert r.json()["months"] == ["2030-01", "2030-02"]
