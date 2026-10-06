"""
sync.sources['calendar_reindex_dw'] -> calendar.sales_snapshots (source_type='dw', kinds actual / trend_shifted).

The day-wise twin of calendar_reindex_sync (user, 2026-09-30: "add day-wise to the nightly sync"). Until now the
day-wise calendarised sales were only rebuilt by hand (Calendar -> Run Reindex -> Day-wise), so they sat on
26 Sep's data (up to 27 Aug) while the month-wise ones were rebuilt every night. Same calendar, stores and months
as the month-wise job, same worker process; output fields as the Calendar's own day-wise run (store level,
default metric). Its own sync source, so a day-wise failure never marks the month-wise rebuild failed.

Day-wise closed months are cached only once the day-wise data reaches their last day (scans._covers_month_end),
so a month cached while the export lagged is recomputed here.

Run manually: python sync/calendar_reindex_dw_sync.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text

from sync.calendar_reindex_sync import _run_worker, calendar_inputs
from sync.common import sync_run

SOURCE_KEY = "calendar_reindex_dw"


def ensure_source():
    """Idempotent sync.sources row (SyncRun has an FK to it)."""
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text("INSERT INTO sync.sources (source_key, config, enabled, ttl_minutes) "
                        "VALUES (:k, CAST(:cfg AS JSON), true, 1440) ON CONFLICT (source_key) DO NOTHING"),
                   {"k": SOURCE_KEY, "cfg": json.dumps({"note": "Day-wise calendarised sales (Calendar Run Reindex, day-wise)"})})
        db.commit()


def run():
    ensure_source()
    with sync_run(SOURCE_KEY) as (session, result):
        cal, day_map, store_cluster, months = calendar_inputs(session)
        rx = _run_worker({"source": "dw", "months": months, "storeCluster": store_cluster, "dayMap": day_map,
                          "extraDims": [], "metric": None, "snapshotSuffix": "", "persistSnapshot": True})
        cols = rx.get("actualColumns") or []
        result["rows_read"] = rx.get("rowsRead")
        result["rows_updated"] = rx.get("rowsMapped")
        result["rows_added"] = 0
        result["detail"] = {"calendar_id": cal.calendar_id, "calendar_name": cal.name, "months": months,
                            "first_day": cols[0] if cols else None, "last_day": cols[-1] if cols else None,
                            "days": len(cols), "cached_months": rx.get("cachedMonths"),
                            "computed_months": rx.get("computedMonths")}


if __name__ == "__main__":
    run()
    print("calendar_reindex_dw_sync: done")
