"""
sync.sources['calendar_reindex'] -> calendar.sales_snapshots (source_type='mw'),
by running Calendar Engine's OWN run_reindex() - the same function its "Run
Reindex" button calls - in a separate OS process.

Why a subprocess, not an in-process call: reindex_worker.py (calendar_engine's
own subprocess entry point) exists specifically because a single large parquet
decode can hold the GIL for minutes, confirmed to freeze the WHOLE unified
platform for every user, not just the request that triggered it - Calendar
Engine's own UI already had to move off in-process/threaded execution for
this exact reason (see reindex_worker.py's docstring). Calling scans.run_reindex()
directly from inside this web server's request handler would reintroduce
that same incident, just from a different button. Shelling out to the same
worker script this app's own UI already uses avoids it.

Why this exists at all: until 2026-08-27, keeping calendar.sales_snapshots
fresh (with ATTRIBUTE1 broken out, and covering AOP's current forecast
period) required a manual trip to the Calendar Engine tab - pick Month-wise,
pick the right calendar, check ATTRIBUTE1, click Run Reindex - with nothing
tying it to AOP's own sync cadence. AOP's Q1 attribute filter (engine_v3.py)
and its "Calendar Engine Reindex" actuals-source toggle (db/reindexed_base_sales.py)
both depend on that snapshot actually existing and having ATTRIBUTE1. This
runs it as a 5th job on every "Sync into database" click, same as the other
4 - a deliberate choice (simpler/more consistent than staleness-checking,
at the cost of a slower sync) confirmed with the user rather than assumed.

Run manually: python sync/calendar_reindex_sync.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select

from db.models.calendar import Calendar, CalendarDayPair, StoreCalendarCluster
from sync.common import sync_run

SOURCE_KEY = "calendar_reindex"
REF_YEAR = 2026  # matches store_actuals_sync.py's own REF_YEAR - same forecast cycle
EXTRA_DIMS = ["ATTRIBUTE1"]
DEPT_EXTRA_DIMS = ["DEPARTMENT"]   # the department-level snapshot for Sales Plan (2026-09-28)
REINDEX_TIMEOUT_SECONDS = 1800  # 30 min - a full-year month-wise reindex with one extra dim; generous, not tuned

_HERE = os.path.dirname(os.path.abspath(__file__))
_CALENDAR_ENGINE_DIR = os.path.abspath(os.path.join(
    _HERE, "..", "..", "RS Planning Platform", "backend", "calendar_engine"))
_WORKER = os.path.join(_CALENDAR_ENGINE_DIR, "reindex_worker.py")


def run():
    with sync_run(SOURCE_KEY) as (session, result):
        # Same "latest locked calendar for this refYear" rule store_actuals_sync.py
        # already uses - the two are meant to stay in sync with each other, both
        # ultimately feeding AOP's same base_sales.LFL concept from two different
        # angles (AOP's own replica vs Calendar Engine's authoritative reindex).
        cal = session.execute(
            select(Calendar).where(Calendar.ref_year == REF_YEAR).order_by(Calendar.saved_at.desc())
        ).scalars().first()
        if cal is None:
            raise LookupError(f"No locked calendar with refYear {REF_YEAR} found — save one via the Calendarisation Suite (/calendar/)")

        pairs = session.execute(
            select(CalendarDayPair).where(CalendarDayPair.calendar_id == cal.calendar_id)
        ).scalars().all()
        day_map = {}
        for p in pairs:
            day_map.setdefault(p.cluster_name, []).append([p.ref_date.isoformat(), p.fut_date.isoformat()])
        if not day_map:
            raise RuntimeError(f'Calendar "{cal.name}" has no day-pairs saved — cannot reindex against it')

        store_cluster = dict(session.execute(
            select(StoreCalendarCluster.store_id, StoreCalendarCluster.cluster_name)
        ).all())

        # Whole reference year - reindex_monthwise silently contributes zero for
        # any month the source data doesn't have yet, same as store_actuals_sync's
        # own month-wise reader; no need to pre-check exactly what's available.
        months = [f"{REF_YEAR}-{m:02d}" for m in range(1, 13)]

        # Two month-wise runs: the main snapshot (store x division x ATTRIBUTE1) and the department-level one
        # (kinds actual_dept / trend_shifted_dept) Sales Plan reads its store x department actual and reindexed
        # sales from (user, 2026-09-28: no more manual sales import in Sales Plan).
        details = []
        for suffix, extra_dims in (("", EXTRA_DIMS), ("_dept", DEPT_EXTRA_DIMS)):
            rx_result = _run_worker({
                "source": "mw", "months": months, "storeCluster": store_cluster,
                "dayMap": day_map, "extraDims": extra_dims, "metric": None, "snapshotSuffix": suffix,
            })
            details.append({"snapshot": "mw" + suffix, "extra_dims": extra_dims,
                            "columns": rx_result.get("columns"), "key_fields": rx_result.get("keyFields"),
                            "rows_read": rx_result.get("rowsRead"), "rows_mapped": rx_result.get("rowsMapped")})

        result["rows_read"] = details[0]["rows_read"]
        result["rows_updated"] = details[0]["rows_mapped"]
        result["rows_added"] = 0
        result["detail"] = {
            "calendar_id": cal.calendar_id, "calendar_name": cal.name,
            "months": months, "extra_dims": EXTRA_DIMS,
            "columns": details[0]["columns"], "key_fields": details[0]["key_fields"],
            "snapshots": details,
        }


def _run_worker(payload):
    """One reindex in Calendar Engine's own worker process; raises on any failure (see run())."""
    with tempfile.TemporaryDirectory() as tmp:
        payload_path = os.path.join(tmp, "payload.json")
        progress_path = os.path.join(tmp, "progress.json")
        result_path = os.path.join(tmp, "result.json")
        with open(payload_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        proc = subprocess.run(
            [sys.executable, _WORKER, payload_path, progress_path, result_path],
            cwd=_CALENDAR_ENGINE_DIR, capture_output=True, text=True,
            timeout=REINDEX_TIMEOUT_SECONDS,
        )
        if not os.path.exists(result_path):
            raise RuntimeError(
                f"reindex_worker produced no result (exit code {proc.returncode}): "
                f"{(proc.stderr or proc.stdout)[-2000:]}"
            )
        with open(result_path, encoding="utf-8") as f:
            rx_result = json.load(f)

    if not rx_result.get("ok"):
        raise RuntimeError(rx_result.get("error") or "reindex_worker returned ok=false with no error message")
    if rx_result.get("sourceUnreachable"):
        # Message matches sync/common.py's _is_network_offline -> status 'offline'.
        raise ConnectionError(
            f"0 rows read for every freshly computed month {rx_result.get('computedMonths')} - "
            "data-lake network path was not found; existing MW snapshot left untouched")
    if rx_result.get("snapshotSaveError"):
        raise RuntimeError(f"Reindex ran but saving the MW snapshot failed: {rx_result['snapshotSaveError']}")
    return rx_result


if __name__ == "__main__":
    run()
    print("calendar_reindex_sync: done")
