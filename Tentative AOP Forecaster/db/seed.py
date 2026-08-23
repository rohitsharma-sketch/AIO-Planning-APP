"""
Idempotent seed of static reference data: divisions, lever definitions, and the
three file-based sync sources (data lake, not the old Calendar Engine HTTP call).

Run manually: python db/seed.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.base import SessionLocal
from db.models.masterdata import Division
from db.models.planning_inputs import LeverDefinition, Period
from db.models.sync import SyncSource

MONTH_ABBR = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
              7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}

# Wide enough to cover the sales history (2019-) through a few forecast years
# ahead — the app's own month labels ("Apr'26") are always "Mon'YY".
PERIODS = [
    {"period_id": y * 100 + m, "label": f"{MONTH_ABBR[m]}'{y % 100:02d}"}
    for y in range(2019, 2031) for m in range(1, 13)
]

DATA_LAKE_RAW = r"C:\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION\data_lake\raw"

DIVISIONS = [
    ("GM", "General Merchandise (rolled up from 8 GM departments)"),
    ("KIDS", "Kids"),
    ("LADIES", "Ladies"),
    ("MENS", "Mens"),
    ("RETAIL", "Retail"),
]

LEVERS = [
    ("store_master", "Store Master", True, "named_row"),
    ("store_actuals", "Store Actuals", True, "store_division_period"),
    ("growth_pct", "Growth %", True, "named_row"),
    ("nso_opening_months", "NSO Opening Months", True, "named_row"),
    ("aop_optional", "AOP (Optional)", False, "store_division_period"),
    ("named_nso_optional", "Named NSO (Optional)", False, "named_row"),
    ("settings", "Settings", False, "scalar"),
]

PROJECTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../CLAUDE Projects
STORE_MASTER_XLSX = os.path.join(PROJECTS_DIR, "..", "Store Master", "Store Master.xlsx")
CALENDAR_ENGINE_DB = os.path.join(PROJECTS_DIR, "..", "Calendar Engine", "Local DB")

SOURCES = [
    ("data_lake_sales", {"path": os.path.join(DATA_LAKE_RAW, "rs_sales_19-_till_date")}, 24 * 60),
    ("data_lake_day_shift", {"path": os.path.join(DATA_LAKE_RAW, "day_shifting_calender")}, 24 * 60),
    ("data_lake_site_master", {"path": os.path.join(DATA_LAKE_RAW, "site_master")}, 24 * 60),
    # Manually curated by the planning team — not on the data lake's automated
    # pipeline, so re-run this one on demand when the file changes, not nightly.
    ("store_master_xlsx", {"path": os.path.normpath(STORE_MASTER_XLSX)}, 0),
    # The Calendar Engine's own state files — locked calendars (per-cluster
    # dayMap) and the store->Calendar Cluster mapping. Updated whenever the
    # planning team locks a new calendar or edits the cluster map, not nightly.
    ("calendar_library", {"path": os.path.normpath(os.path.join(CALENDAR_ENGINE_DB, "calendar_library.json"))}, 0),
    ("store_calendar_cluster_map", {"path": os.path.normpath(os.path.join(CALENDAR_ENGINE_DB, "store_cluster_map.json"))}, 0),
]


def _upsert(session, model, values, pk_col):
    stmt = pg_insert(model).values(values)
    update_cols = {c.name: getattr(stmt.excluded, c.name) for c in model.__table__.columns if c.name != pk_col}
    stmt = stmt.on_conflict_do_update(index_elements=[pk_col], set_=update_cols)
    session.execute(stmt)


def main():
    with SessionLocal() as session:
        _upsert(session, Division, [{"division_code": c, "description": d} for c, d in DIVISIONS], "division_code")
        _upsert(session, Period, PERIODS, "period_id")
        _upsert(
            session, LeverDefinition,
            [{"lever_key": k, "label": lbl, "required": req, "shape": shape} for k, lbl, req, shape in LEVERS],
            "lever_key",
        )
        _upsert(
            session, SyncSource,
            [{"source_key": k, "config": cfg, "enabled": True, "ttl_minutes": ttl} for k, cfg, ttl in SOURCES],
            "source_key",
        )
        session.commit()
    print("Seeded divisions, periods, lever_definitions, sync.sources.")


if __name__ == "__main__":
    main()
