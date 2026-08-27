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
    ("store_actuals", "data_lake_sales"),
    ("calendar_reindex", "calendar_reindex"),
]


def main():
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
