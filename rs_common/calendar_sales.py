"""The one reader for calendar sales (Phase 0 of the multi-year switch, user 2026-10-08): actual or reindexed sales
from calendar.sales_fact (filled nightly by AOP's sync/calendar_sales_fact_sync.py, verified by calendar_check_sync
check 8) instead of each app re-reading the data-lake parquet.

    from rs_common.calendar_sales import get_sales
    df = get_sales(conn, "actual", ["2026-03", "2026-04"], by=("store", "plan_division", "department"))
    df = get_sales(conn, "reindexed", ["2027-03"], calendar_id=1790655109215)   # TY months of that calendar

`conn` = any SQLAlchemy Connection / Session on the planning DB. Returns a DataFrame with the `by` columns, `month`
('YYYY-MM'), `sl_v` (rupees) and `sl_q` (units). plan_division None = not a planning division (NON-TRADING ...);
pass planned_only=True to leave those out. reindexed without calendar_id = the latest saved calendar whose plan
(TY) year holds the first month asked.
"""
import pandas as pd
from sqlalchemy import text

_BY = {"store", "division", "plan_division", "department", "attribute1", "ref_month"}


def latest_calendar_for(conn, ty_month):
    return conn.execute(text("SELECT calendar_id FROM calendar.calendars WHERE fut_year = :y ORDER BY saved_at DESC LIMIT 1"),
                        {"y": str(ty_month)[:4]}).scalar()


def get_sales(conn, kind, months, by=("store", "plan_division"), calendar_id=None, stores=None, planned_only=False):
    if kind not in ("actual", "reindexed"):
        raise ValueError("kind must be 'actual' or 'reindexed'")
    bad = set(by) - _BY
    if bad:
        raise ValueError(f"unknown grouping {sorted(bad)}")
    months = sorted(months)
    if kind == "actual":
        calendar_id = 0
    elif calendar_id is None:
        calendar_id = latest_calendar_for(conn, months[0])
        if calendar_id is None:
            raise LookupError(f"no saved calendar for plan year {months[0][:4]}")
    cols = ", ".join(("to_char(ref_month, 'YYYY-MM') AS ref_month" if c == "ref_month" else c) for c in by)
    grp = ", ".join(str(i + 1) for i in range(len(by) + 1))
    sql = (f"SELECT {cols}{', ' if cols else ''}to_char(month, 'YYYY-MM') AS month, sum(sl_v) AS sl_v, sum(sl_q) AS sl_q "
           "FROM calendar.sales_fact WHERE kind = :k AND calendar_id = :c AND month = ANY(CAST(:m AS date[]))"
           + (" AND store = ANY(:s)" if stores else "") + (" AND plan_division IS NOT NULL" if planned_only else "")
           + f" GROUP BY {grp}")
    p = {"k": kind, "c": int(calendar_id), "m": [f"{m}-01" for m in months]}
    if stores:
        p["s"] = list(stores)
    return pd.DataFrame(conn.execute(text(sql), p).mappings().all(), columns=list(by) + ["month", "sl_v", "sl_q"])
