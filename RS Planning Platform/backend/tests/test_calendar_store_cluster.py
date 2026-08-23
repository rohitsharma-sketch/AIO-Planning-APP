import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "Tentative AOP Forecaster"))

import io
import pytest
from sqlalchemy import delete, select

from db.base import SessionLocal
from db.models.calendar import StoreCalendarCluster, StoreClusterMapMeta, StoreClusterLogEntry


@pytest.fixture(autouse=True)
def _clean_test_stores():
    # PUT /store-cluster-map does a full-table replace of StoreCalendarCluster
    # (see router.py: `session.execute(delete(StoreCalendarCluster))` before
    # re-inserting). This is a real, shared Postgres database that already
    # holds real store-cluster rows, so a naive "just delete ZZ1/ZZ2/ZZ3
    # afterwards" cleanup is not enough — the PUT call in
    # test_planner_replaces_store_cluster_map_and_logs_diff wipes every real
    # row too. Snapshot the real state before the test and restore it after,
    # in addition to removing whatever the test itself created.
    session = SessionLocal()
    backup_rows = [
        {"store_id": r.store_id, "cluster_name": r.cluster_name, "locked_at": r.locked_at, "synced_at": r.synced_at}
        for r in session.execute(select(StoreCalendarCluster)).scalars().all()
    ]
    backup_meta_row = session.get(StoreClusterMapMeta, 1)
    backup_meta = (
        {"source": backup_meta_row.source, "aliases": backup_meta_row.aliases, "edited_at": backup_meta_row.edited_at}
        if backup_meta_row is not None else None
    )
    pre_existing_log_ids = {row[0] for row in session.execute(select(StoreClusterLogEntry.id)).all()}
    session.close()

    yield

    session = SessionLocal()
    # Remove anything this test created directly.
    session.execute(delete(StoreCalendarCluster).where(StoreCalendarCluster.store_id.in_(["ZZ1", "ZZ2", "ZZ3"])))
    session.execute(delete(StoreClusterLogEntry).where(StoreClusterLogEntry.summary == "Test import"))
    # Remove any store-cluster-log rows created during the test run (e.g. the
    # diff log row from the PUT test), then restore the real table state.
    session.execute(delete(StoreClusterLogEntry).where(StoreClusterLogEntry.id.not_in(pre_existing_log_ids)))
    session.execute(delete(StoreCalendarCluster))
    if backup_rows:
        session.execute(StoreCalendarCluster.__table__.insert(), backup_rows)
    if backup_meta is None:
        session.execute(delete(StoreClusterMapMeta).where(StoreClusterMapMeta.id == 1))
    else:
        meta_row = session.get(StoreClusterMapMeta, 1)
        if meta_row is not None:
            meta_row.source = backup_meta["source"]
            meta_row.aliases = backup_meta["aliases"]
            meta_row.edited_at = backup_meta["edited_at"]
    session.commit()
    session.close()


def test_planner_replaces_store_cluster_map_and_logs_diff(planner_client):
    r = planner_client.get("/api/calendar/store-cluster-map")
    assert r.status_code == 200
    before_count = len(r.json()["stores"])

    payload = {"stores": [{"store": "ZZ1", "cluster": "TestClusterA"}, {"store": "ZZ2", "cluster": "TestClusterA"}],
               "source": "test-upload.csv"}
    r = planner_client.put("/api/calendar/store-cluster-map", json=payload)
    assert r.status_code == 200, r.text

    r = planner_client.get("/api/calendar/store-cluster-map")
    stores = {s["store"]: s["cluster"] for s in r.json()["stores"]}
    assert stores["ZZ1"] == "TestClusterA"
    assert stores["ZZ2"] == "TestClusterA"
    assert r.json()["source"] == "test-upload.csv"

    r = planner_client.get("/api/calendar/store-cluster-log")
    assert r.status_code == 200
    latest = r.json()[0]  # newest first
    assert latest["added"] >= 2


def test_import_store_cluster_parses_csv(planner_client):
    csv_bytes = b"Store,Cluster\nZZ3,TestClusterB\n"
    r = planner_client.post(
        "/api/calendar/import/store-cluster",
        files={"file": ("test.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert {"store": "ZZ3", "cluster": "TestClusterB"} in rows


def test_buyer_cannot_replace_store_cluster_map(buyer_client):
    r = buyer_client.put("/api/calendar/store-cluster-map", json={"stores": [], "source": "x"})
    assert r.status_code == 403
