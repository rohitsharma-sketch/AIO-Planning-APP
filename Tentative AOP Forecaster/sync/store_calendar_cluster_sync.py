"""
sync.sources['store_calendar_cluster_map'] -> calendar.store_calendar_clusters

Reads the Calendar Engine's Local DB/store_cluster_map.json — store -> Calendar
Cluster (the festival-timing cluster used for the day-shift reindex; distinct
from masterdata.stores.cluster_key and .erp_cluster_type, see db/models/calendar.py).
Full replace each run — the source is a single locked snapshot, not a history.

Run manually: python sync/store_calendar_cluster_sync.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json

from sqlalchemy import delete

from db.models.calendar import StoreCalendarCluster
from db.models.sync import SyncSource
from sync.common import sync_run

SOURCE_KEY = "store_calendar_cluster_map"


def run():
    with sync_run(SOURCE_KEY) as (session, result):
        source = session.get(SyncSource, SOURCE_KEY)
        path = source.config["path"]

        with open(path, encoding="utf-8") as f:
            scm = json.load(f)
        stores = scm.get("stores", [])
        locked_at = scm.get("lockedAt")
        result["rows_read"] = len(stores)

        session.execute(delete(StoreCalendarCluster))
        rows = [
            {"store_id": s["store"].strip(), "cluster_name": s["cluster"].strip(), "locked_at": locked_at}
            for s in stores if s.get("store") and s.get("cluster")
        ]
        if rows:
            session.execute(StoreCalendarCluster.__table__.insert(), rows)

        result["rows_updated"] = len(rows)
        result["rows_added"] = 0
        result["detail"] = {"source_file": os.path.basename(path), "locked": scm.get("locked")}


if __name__ == "__main__":
    run()
    print("store_calendar_cluster_sync: done")
