import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "Tentative AOP Forecaster"))

import datetime
import pytest
from sqlalchemy import delete

from db.base import SessionLocal
from db.models.calendar import FestivalChangelogEntry, SalesdataLinkSelection


@pytest.fixture(autouse=True)
def _restore_salesdata_link_mw():
    # test_salesdata_link_selection_round_trip PUTs fake test data (months
    # 2030-01/2030-02, path \\test\path) to the real 'mw' row -- the row
    # Task 7's migrate_from_json.py populated with the real months/UNC path
    # from Calendar Engine/Local DB/salesdata_link_selection.json -- and
    # never restores it. Snapshot the real row before the test and restore
    # it after, same pattern as test_calendar_store_cluster.py's
    # _clean_test_stores.
    session = SessionLocal()
    backup_row = session.get(SalesdataLinkSelection, "mw")
    backup = (
        {"months": backup_row.months, "path": backup_row.path, "synced_at": backup_row.synced_at}
        if backup_row is not None else None
    )
    session.close()

    yield

    session = SessionLocal()
    try:
        if backup is None:
            session.execute(delete(SalesdataLinkSelection).where(SalesdataLinkSelection.source_type == "mw"))
        else:
            row = session.get(SalesdataLinkSelection, "mw")
            if row is None:
                row = SalesdataLinkSelection(source_type="mw")
                session.add(row)
            row.months = backup["months"]
            row.path = backup["path"]
            row.synced_at = backup["synced_at"]
        session.commit()
    finally:
        # This is a real shared database holding a real salesdata-link row --
        # guarantee the session (and its connection) is released even if a
        # restore statement above raises partway through.
        session.close()


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


def test_reindex_route_returns_ok_false_for_invalid_payload(planner_client):
    # Cheap route-wiring smoke test: POST /api/calendar/salesdata/reindex has
    # no coverage anywhere else (Task 2 only tested get_salesdata_link /
    # get_salesdata_link_daywise as direct function calls; Task 6 added the
    # route but only tested changelog/link-selection). An invalid payload
    # (missing months/dayMap, bogus source) exercises run_reindex's own
    # error-handling path (calendar_engine/scans.py) without touching the
    # network parquet source -- it returns {"ok": False, "error": ...} with a
    # 200 status rather than raising, so this only confirms the route is
    # wired to run_reindex, not the reindex logic itself.
    r = planner_client.post("/api/calendar/salesdata/reindex", json={"source": "bogus"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert "error" in body


def test_buyer_cannot_run_reindex(buyer_client):
    # Run Reindex overwrites calendar.sales_snapshots (read by SalesPlan's Sales Sync) - planner-only.
    for path in ("/api/calendar/salesdata/reindex", "/api/calendar/salesdata/reindex/start"):
        assert buyer_client.post(path, json={"source": "bogus"}).status_code == 403
