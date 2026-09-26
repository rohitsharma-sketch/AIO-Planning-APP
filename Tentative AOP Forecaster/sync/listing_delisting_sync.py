"""sync.sources['listing_delisting'] -> the Listing/Delisting app's data files
(`Listing Delisting/app/*.json`) - an ADDITIONAL app, joined to the daily data-lake sync
on 2026-09-26 (user: "unified network for data and analysis").

Rebuilds, in the order the app's PRD_LOGIC requires (each step feeds the next):
listing KB (yearly workbooks in data/listing) -> sales (data-lake parquet, same
sync.sources path as data_lake_sales) -> seasonality -> season category -> risk
scores -> store master (planning DB, AOP's LfL rule). Each script runs as its own
process (the sales pass reads the full parquet; separate processes free that memory).
A data-lake outage is recorded as 'offline' like every other source - the app keeps
its last files.

Run manually: python sync/listing_delisting_sync.py
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sync.common import sync_run

SOURCE_KEY = "listing_delisting"
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Listing Delisting"))
# build_daily.py (store x dept x DAY cache, rebuilt only when a newer day-wise export lands) and
# build_suggestions.py (festival / season windows + like-for-like delist & relist, 2026-09-26) replace
# the old month-level build_risk_scores.py.
STEPS = ["build_knowledge_base.py", "build_sales.py", "build_seasonality.py",
         "build_season_category.py", "build_stores.py", "build_daily.py", "build_suggestions.py"]  # suggestions read stores.json
_ready = False


def ensure_source():
    """Idempotent sync.sources row (SyncRun has an FK to it)."""
    global _ready
    if _ready:
        return
    import json
    from sqlalchemy import text
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text(
            "INSERT INTO sync.sources (source_key, config, enabled, ttl_minutes) "
            "VALUES (:k, CAST(:cfg AS JSON), true, 1440) ON CONFLICT (source_key) DO NOTHING"
        ), {"k": SOURCE_KEY, "cfg": json.dumps({"app": APP_DIR, "note": "Additional app - rebuilds its app/*.json"})})
        db.commit()
    _ready = True


def run():
    ensure_source()
    with sync_run(SOURCE_KEY) as (session, result):
        timings = {}
        for step in STEPS:
            t0 = time.time()
            p = subprocess.run([sys.executable, os.path.join("scripts", step)], cwd=APP_DIR,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            timings[step] = round(time.time() - t0, 1)
            if p.returncode:
                tail = (p.stderr or p.stdout).strip()[-600:]
                # sync_run records "network path was not found" & co. as offline, anything else as failed
                raise RuntimeError(f"{step} failed: {tail}")
        result["rows_read"] = None
        result["rows_updated"] = len(STEPS)
        result["rows_added"] = 0
        result["detail"] = {"steps_secs": timings}


if __name__ == "__main__":
    run()
    print("listing_delisting_sync: done")
