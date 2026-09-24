"""Sales Sync
No longer parses its own parquet files from a manually-configured server
folder - that duplicated work the Calendar Engine app already does against
the same network source, and the two could silently drift apart (e.g. one
pointed at a stale/wrong path). Instead this just reads what the
Calendarisation app itself already computed and saved to Postgres on its
last Run Reindex: 'actual' sales (real sales on their own reference date,
straight off the same sales link Calendar Engine reads) and 'trend_shifted'
sales (the same sales moved onto the calendar-aligned future date), for
both the month-wise ('mw') and day-wise ('dw') sources. All four live in
the shared `calendar.sales_snapshots` table - see calendar_engine/scans.py's
run_reindex()/_save_calendarised_sales_snapshot() - so "syncing" here means
reading the latest rows, not recomputing anything.
"""
import os
import sys

# This router is mounted both by the unified RS Planning Platform backend
# (which already puts "Tentative AOP Forecaster" on sys.path) and by
# SalesPlan's own standalone main.py (port 8002 in landing_server.py's APPS
# list), which does not. Insert it here too, same relative path scans.py
# uses from its own directory, so `db.*` imports below resolve either way.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

from fastapi import APIRouter, HTTPException

from db.base import SessionLocal
from db.models.calendar import SalesSnapshot

router = APIRouter()

SOURCE_TYPES = ("mw", "dw")
KINDS = ("actual", "trend_shifted")


def _load_snapshot(source_type: str, kind: str):
    session = SessionLocal()
    try:
        row = session.get(SalesSnapshot, (source_type, kind))
        if row is None:
            return None
        return {
            "grain": row.grain, "metric": row.metric, "keyFields": row.key_fields, "columns": row.columns, "rows": row.rows,
            "rowsRead": row.rows_read, "rowsMapped": row.rows_mapped, "computedAt": row.computed_at.isoformat(),
        }
    finally:
        session.close()


def _summary(snap):
    if snap is None:
        return {"synced": False}
    return {
        "synced": True, "computedAt": snap["computedAt"], "grain": snap["grain"], "metric": snap["metric"],
        "rowCount": snap["rowsMapped"], "columnCount": len(snap["columns"]),
        "dateRange": {"min": snap["columns"][0], "max": snap["columns"][-1]} if snap["columns"] else None,
    }


def _all_summaries():
    return {
        source: {
            "actual": _summary(_load_snapshot(source, "actual")),
            "trendShifted": _summary(_load_snapshot(source, "trend_shifted")),
        }
        for source in SOURCE_TYPES
    }


@router.get("/status")
def sync_status():
    return _all_summaries()


@router.post("/sync")
def sync_sales():
    """Re-reads every snapshot from the DB - nothing to compute here. The
    actual computation happens in the Calendarisation app's Run Reindex."""
    summaries = _all_summaries()
    if not any(s["actual"]["synced"] or s["trendShifted"]["synced"] for s in summaries.values()):
        raise HTTPException(
            409,
            "No calendarised sales yet - run Reindex in the Calendarisation app's "
            "Calendarised Sales tab first, then sync here.",
        )
    return {"ok": True, **summaries}


@router.get("/data")
def get_sales_data(source: str = "mw", kind: str = "trend_shifted", limit: int = 500):
    if source not in SOURCE_TYPES:
        raise HTTPException(422, "source must be 'mw' or 'dw'")
    if kind not in KINDS:
        raise HTTPException(422, "kind must be 'actual' or 'trend_shifted'")
    snap = _load_snapshot(source, kind)
    if snap is None:
        raise HTTPException(404, "Not synced yet")

    key_fields = snap["keyFields"] or (["store", "division"] if snap["grain"] == "store_division" else ["store"])
    by_key = {}
    for r in snap["rows"]:
        k = tuple(r.get(f) for f in key_fields)
        e = by_key.setdefault(k, {f: r.get(f) for f in key_fields})
        e[r["col"]] = e.get(r["col"], 0) + r["value"]  # sum, not assign: duplicate (key, col) rows must not overwrite
    preview = list(by_key.values())[:limit]

    return {
        "columns": key_fields + snap["columns"], "preview": preview, "rows": len(by_key),
        "computedAt": snap["computedAt"],
    }
