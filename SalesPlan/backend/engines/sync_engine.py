"""Sales Sync - read-only view of the Calendar app's saved sales (user, 2026-09-28: no manual sync; the backend's
nightly data-lake sync, sync/run_all.py -> calendar_reindex_sync, pushes them). Also shows the department-level
month-wise snapshots Sales Plan's actuals come from (actuals_manager).

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
KINDS = ("actual", "trend_shifted", "actual_dept", "trend_shifted_dept")


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


def _snapshot_meta(source_type: str, kind: str):
    """A snapshot without its rows - all the status needs (user, 2026-10-07: loading six full snapshots' rows took
    ~4.5 s on every Sales Sync page view)."""
    from sqlalchemy import select
    S = SalesSnapshot
    session = SessionLocal()
    try:
        r = session.execute(select(S.grain, S.metric, S.columns, S.rows_mapped, S.computed_at)
                            .where(S.source_type == source_type, S.kind == kind)).first()
    finally:
        session.close()
    if r is None:
        return None
    return {"grain": r[0], "metric": r[1], "columns": r[2], "rowsMapped": r[3], "computedAt": r[4].isoformat()}


def _all_summaries():
    out = {
        source: {
            "actual": _summary(_snapshot_meta(source, "actual")),
            "trendShifted": _summary(_snapshot_meta(source, "trend_shifted")),
        }
        for source in SOURCE_TYPES
    }
    out["mw_dept"] = {"actual": _summary(_snapshot_meta("mw", "actual_dept")),
                      "trendShifted": _summary(_snapshot_meta("mw", "trend_shifted_dept"))}
    return out


def _last_sync():
    """The latest nightly calendar_reindex run (sync.sync_runs) - what refreshed these snapshots."""
    from sqlalchemy import text
    session = SessionLocal()
    try:
        r = session.execute(text(
            "SELECT status, started_at, completed_at, error_message FROM sync.sync_runs "
            "WHERE source_key = 'calendar_reindex' ORDER BY sync_run_id DESC LIMIT 1")).first()
        return None if r is None else {"status": r[0], "startedAt": r[1].isoformat() if r[1] else None,
                                       "completedAt": r[2].isoformat() if r[2] else None, "error": r[3]}
    finally:
        session.close()


def _last_check():
    """The latest nightly calendar_check run (sync/calendar_check_sync.py): is the calendarised sales exact?"""
    from sqlalchemy import text
    session = SessionLocal()
    try:
        r = session.execute(text(
            "SELECT status, completed_at, error_message, detail FROM sync.sync_runs "
            "WHERE source_key = 'calendar_check' ORDER BY sync_run_id DESC LIMIT 1")).first()
        if r is None:
            return None
        checks = (r[3] or {}).get("checks", [])
        return {"status": r[0], "completedAt": r[1].isoformat() if r[1] else None, "error": r[2],
                "passed": sum(1 for c in checks if c.get("ok")), "total": len(checks),
                "checks": [{"name": c.get("name"), "ok": c.get("ok"), "maxDiffL": c.get("max_diff_L"), "cells": c.get("cells")} for c in checks]}
    finally:
        session.close()


@router.get("/status")
def sync_status():
    return {**_all_summaries(), "lastSync": _last_sync(), "lastCheck": _last_check()}


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
