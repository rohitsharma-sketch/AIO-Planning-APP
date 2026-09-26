"""Where the Listing/Delisting build scripts read from - one place, shared with the
RS Planning core apps (moved into RS_planning 2026-09-26):

- DATA_DIR    : the yearly listing workbooks (RS_planning/data/listing/Directories, RAW) - gitignored.
- sales_dir() : the data-lake sales folder, read from the SAME setting the core syncs use
                (Postgres sync.sources 'data_lake_sales'), so a moved data lake is changed once
                for every app. Falls back to the known path if the database can't be reached.
"""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # .../Listing Delisting
REPO = os.path.dirname(BASE)                                                 # .../RS_planning
DATA_DIR = os.path.join(REPO, "data", "listing")
AOP_DIR = os.path.join(REPO, "Tentative AOP Forecaster")
FALLBACK_SALES_DIR = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw\rs_sales_19-_till_date"


def planning_session():
    """A session on the RS Planning Postgres (AOP Forecaster's db package + .env)."""
    if AOP_DIR not in sys.path:
        sys.path.insert(0, AOP_DIR)
    from db.base import SessionLocal
    return SessionLocal()


def sales_dir():
    try:
        from sqlalchemy import text
        with planning_session() as s:
            path = s.execute(text(
                "SELECT config->>'path' FROM sync.sources WHERE source_key = 'data_lake_sales'")).scalar()
        if path:
            return path
    except Exception as e:  # DB down / not configured: keep working on the known location
        print(f"[paths] planning DB unavailable ({type(e).__name__}); using the default data-lake path")
    return FALLBACK_SALES_DIR
