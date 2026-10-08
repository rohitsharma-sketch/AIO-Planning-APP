"""Runs every data-lake sync job into Postgres, in the same order and with
the same jobs app.py's `POST /api/config/db-sync` uses (the "Sync into
database" button) - just invoked directly, with no HTTP call and no login
session, so a Windows Scheduled Task can run it unattended.

This is what makes newly-closed months show up automatically: each sync
module (store_actuals_sync.py in particular) only ever pulls in a month once
the real calendar has moved past it - engine_v3.py's pivot_actuals() also
refuses to use an not-yet-closed month's actuals even if one is already in
the DB, so the two agree independently. Running this daily means the day a
month closes, the next run within 24h picks it up with no manual click.

Run manually: python sync/run_all.py
Installed as a daily scheduled task by ../install_auto_sync.ps1 (see that
script for the exact time and how to uninstall).
"""
import importlib
import os
import sys

# Run directly (`python sync/run_all.py`) rather than imported, Python sets
# sys.path[0] to this file's OWN directory (.../sync), not its parent - so
# `import sync.xxx` below fails with "No module named 'sync'" without this,
# even though the identical import works fine from app.py (which lives in
# the parent dir already). Same fixup every individual *_sync.py module
# already does for itself, needed here too since this import happens before
# any of them get a chance to run their own.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Same list as app.py's DB_SYNC_JOBS - kept as a literal copy, not an import,
# so this script has no dependency on app.py (which pulls in the full FastAPI
# app just to read one constant) and can run standalone.
DB_SYNC_JOBS = [
    ("site_master", "data_lake_site_master"),
    ("store_master_xlsx", "store_master_xlsx"),
    ("day_shift", "data_lake_day_shift"),
    # Cluster x day sales from the day-wise export - weights the festival
    # shift by real day sales (db/calendar_shift.py, option b 2026-09-25).
    ("day_weights", "data_lake_day_weights"),
    # Multi-year calendar sales (2026-10-08, Phase 0): every closed month 2019+ actual + every saved calendar's
    # reindexed months into calendar.sales_fact (needs the day weights); verified by calendar_check (check 8).
    ("calendar_sales_fact", "calendar_sales_fact"),
    # AOP base from calendar.sales_fact (Phase 1, 2026-10-08) - so after it; writes closed_through for the rest.
    ("store_actuals", "data_lake_sales"),
    ("calendar_reindex", "calendar_reindex"),
    # Read-only accuracy check of what calendar_reindex just saved (user, 2026-09-28): raw vs saved, independent
    # recompute, conservation, department tables, day maps, trading stores without a cluster. Fails loudly.
    ("calendar_check", "calendar_check"),
    # Day-wise calendarised sales (user, 2026-09-30) - after the month-wise rebuild and its check, own source row.
    ("calendar_reindex_dw", "calendar_reindex_dw"),
    # Not in app.py's list: Google "Holidays in India" -> festival_reference_dates,
    # then re-dates Festival Master + locked calendars' festival lists.
    ("festival_dates", "festival_dates"),
    # Additional app (2026-09-26): Listing/Delisting rebuilds its app/*.json from the same
    # data lake + planning store master. Last, so the core sources are never delayed by it (~3 min).
    ("listing_delisting", "listing_delisting"),
]


def _single_instance():
    """Exclusive lock for the whole run, so a second trigger (two "Sync now"
    calls a second apart, Landing's after-launch sync + the daily task, ...)
    exits instead of running every job twice in parallel (seen 2026-09-26:
    two runs 1 s apart, each a multi-hour data_lake_sales pass). The OS drops
    the lock when this process ends, even on a crash, so it never goes stale."""
    import tempfile
    fh = open(os.path.join(tempfile.gettempdir(), "rs_planning_run_all.lock"), "a+")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Another sync run is already in progress - not starting a second one.")
        sys.exit(0)
    return fh   # keep the handle (and the lock) for the life of the process


def main():
    _lock = _single_instance()  # noqa: F841 - held until exit
    ok = True
    for module_name, source_key in DB_SYNC_JOBS:
        try:
            mod = importlib.import_module(f"sync.{module_name}_sync")
            mod.run()
            print(f"[{source_key}] ok")
        except Exception as e:
            ok = False
            print(f"[{source_key}] FAILED: {type(e).__name__}: {e}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
