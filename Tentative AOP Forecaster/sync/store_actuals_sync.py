"""
calendar.sales_fact (the Calendar's multi-year sales, sync/calendar_sales_fact_sync.py) -> planning_inputs.input_values
lever_key='store_actuals' (the AOP LfL base) and 'store_actuals_fy26' (the FY26 placeholder base).

Phase 1 of "flow all sales for actual and reindexed in all other apps from calendarised app" (user, 2026-10-08): this
sync used to re-read the month-wise parquet and repeat the Calendar's reindex itself; it now takes both straight from
the Calendar's own table, so the AOP base is the calendarised sales by construction:

  1. The active calendar = the latest saved one for REF_YEAR (the one the nightly Calendar reindex uses).
  2. Closed months + source file = the table's last successful load (it runs right before this job in run_all and
     works out "closed" by _closed_through below on the same export).
  3. store_actuals: the calendar's reindexed sales landing in an FY27 base month (Mar'26..Mar'27 labels = TY
     Mar'27..Mar'28), every closed reference month's share included (e.g. Feb'26 days landing in Mar'27), at
     store x planning division x ATTRIBUTE1 (row_key) - Lakhs. Divisions roll up by rs_common.divisions (DND ->
     RETAIL, NON FOOD -> GM; NON-TRADING / FIXED ASSETS / CONSIGNMENT / CDIT left out).
  4. store_actuals_fy26: raw (not reindexed) Mar'25..Feb'26 actuals, store x division - the placeholder base the
     engine uses for an FY28 month whose FY27 base month hasn't closed yet (option b, 2026-09-24).
  5. sync_runs.detail["closed_through"] ('YYYY-MM') - the single value the engine / reindex / UI read
     (sync.common.get_closed_through).

Tie-out before the switch (2026-10-08): FY26 placeholder identical on all 8,839 cells; base Apr'26..Aug'26 identical;
Mar'26 label (TY Mar'27) 15,482.1 -> 14,750.4 L = the Calendar's own Mar'27 (the old sync kept all of Mar'26 there
because it did not count Jan / Feb'26 as closed - the 731.7 L Holi move).

Run manually: python sync/store_actuals_sync.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))   # repo root: rs_common

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.calendar import Calendar
from db.models.planning_inputs import InputValue, LeverDefinition, Period
from rs_common.divisions import plan_division
from sync.common import closed_through_from_last_day, snapshot_last_day, sync_run

SOURCE_KEY = "data_lake_sales"
LEVER_KEY = "store_actuals"
FY26_LEVER_KEY = "store_actuals_fy26"
REF_YEAR = 2026  # matches calendar_sync.py's default _load_calendar(ref_year=2026)

FY27_M = ["Mar'26", "Apr'26", "May'26", "Jun'26", "Jul'26", "Aug'26", "Sep'26",
          "Oct'26", "Nov'26", "Dec'26", "Jan'27", "Feb'27", "Mar'27"]
MON = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
       "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
MON_NAMES = {v: k for k, v in MON.items()}
LAKH = 1e5
_norm_div = plan_division   # the one roll-up (rs_common.divisions)


def _label_to_ym(label):
    mon, yy = label.split("'")
    return f"20{yy}-{MON[mon]:02d}"


# Same month one year earlier for every FY27 base month except Mar'27 (Mar'28
# waits for a real closed Mar'27 - pivot_actuals docstring, 2026-08-27):
# "2025-03".."2026-02".
FY26_YM = [f"{int(_label_to_ym(m)[:4]) - 1}{_label_to_ym(m)[4:]}" for m in FY27_M[:-1]]


def _fut_to_label(fut):
    y, m = (int(x) for x in fut.split("-"))
    return f"{MON_NAMES[m]}'{(y - 1) % 100:02d}"


def _closed_through(snapshot_name, latest_month_in_data, today=None):
    """'YYYY-MM' of the last month the export fully accounts for. Unstamped
    export -> the old date rule (neither today's month nor the data's latest
    month counts as closed). Never later than the data's own latest month.
    Used by calendar_sales_fact_sync on the export it reads."""
    last_day = snapshot_last_day(snapshot_name)
    if last_day is None:
        cut = (today or datetime.date.today()).replace(day=1)
        if latest_month_in_data:
            cut = min(cut, datetime.date(int(latest_month_in_data[:4]), int(latest_month_in_data[5:]), 1))
        last_day = cut - datetime.timedelta(days=1)
    ct = closed_through_from_last_day(last_day)
    return min(ct, latest_month_in_data) if latest_month_in_data else ct


def _complete_months(ref_months, closed_through, include_partial=False):
    keep, skipped = [], []
    for m in ref_months:
        (keep if m <= closed_through or include_partial else skipped).append(m)
    return keep, skipped


def from_fact(session, calendar_id, ref_months):
    """The AOP base from calendar.sales_fact.
    -> (agg {(store, div, attribute, FY27 label): Lakhs} - every closed reference month's share that lands in an FY27
        month (e.g. Feb'26 days landing in Mar'27 count too, as on the Calendar; ref_months only reports what is
        missing), fy26 {(store, div, FY26 label): Lakhs} raw Mar'25..Feb'26, info)."""
    agg, fy26, excluded = {}, {}, {}
    for st, raw_div, attr, fut, v in session.execute(text(
            "SELECT store, division, attribute1, to_char(month, 'YYYY-MM'), sum(sl_v) FROM calendar.sales_fact "
            "WHERE kind = 'reindexed' AND calendar_id = :c GROUP BY 1, 2, 3, 4"), {"c": int(calendar_id)}):
        div = _norm_div(raw_div)
        if div is None:
            excluded[raw_div] = excluded.get(raw_div, 0.0) + float(v) / LAKH
            continue
        label = _fut_to_label(fut)
        if label in FY27_M:
            key = (st.strip(), div, str(attr).strip(), label)
            agg[key] = agg.get(key, 0.0) + float(v) / LAKH
    for st, raw_div, ym, v in session.execute(text(
            "SELECT store, division, to_char(month, 'YYYY-MM'), sum(sl_v) FROM calendar.sales_fact "
            "WHERE kind = 'actual' AND to_char(month, 'YYYY-MM') = ANY(:m) GROUP BY 1, 2, 3"), {"m": FY26_YM}):
        div = _norm_div(raw_div)
        if div is not None:
            key = (st.strip(), div, f"{MON_NAMES[int(ym[5:])]}'{ym[2:4]}")
            fy26[key] = fy26.get(key, 0.0) + float(v) / LAKH
    loaded = {m for (m,) in session.execute(text(
        "SELECT to_char(ref_month, 'YYYY-MM') FROM calendar.sales_fact_load WHERE kind = 'reindexed' AND calendar_id = :c"),
        {"c": int(calendar_id)})}
    return agg, fy26, {"missing_ref_months": sorted(set(ref_months) - loaded),
                       "excluded_lakhs": {k: round(v, 1) for k, v in excluded.items()}}


def run(include_partial=False):
    """include_partial is kept for old callers - the table holds closed months only, so it has no effect any more."""
    with sync_run(SOURCE_KEY) as (session, result):
        # 1. the active calendar (latest saved, matching REF_YEAR)
        cal = session.execute(
            select(Calendar).where(Calendar.ref_year == REF_YEAR).order_by(Calendar.saved_at.desc())
        ).scalars().first()
        if cal is None:
            raise LookupError(f"No locked calendar with refYear {REF_YEAR} found — save one via the Calendarisation Suite (/calendar/)")

        # 2. closed months + export = the multi-year table's last load (runs right before this job)
        fact = session.execute(text("SELECT detail FROM sync.sync_runs WHERE source_key = 'calendar_sales_fact' "
                                    "AND status = 'success' ORDER BY sync_run_id DESC LIMIT 1")).scalar()
        if not fact:
            raise RuntimeError("calendar.sales_fact has not been loaded yet - run sync/calendar_sales_fact_sync.py first")
        closed_through, snapshot_name = fact["closed_through"], fact["source_file"]
        ref_months, partial_months = _complete_months([_label_to_ym(m) for m in FY27_M], closed_through)
        if not ref_months:
            raise RuntimeError("No complete reference months available yet")

        # 3. reindexed base + FY26 placeholder, straight from the Calendar's table
        agg, fy26, info = from_fact(session, cal.calendar_id, ref_months)
        if info["missing_ref_months"]:
            raise RuntimeError(f"calendar.sales_fact holds no reindexed {info['missing_ref_months']} for calendar "
                               f"{cal.calendar_id} - run sync/calendar_sales_fact_sync.py")

        # 4. write store_actuals: delete every row of each period being (re)written, then insert fresh - an attribute /
        #    store / division with sales last time but none now must not linger (upsert alone never removes a key).
        #    Batched: Postgres' ~65535 bound-parameter limit (7 params per row).
        period_ids = {p.label: p.period_id for p in session.execute(select(Period)).scalars().all()}
        rows = [
            {"lever_key": LEVER_KEY, "store_id": store, "division_code": div, "period_id": period_ids[label],
             "row_key": attribute, "value": round(v, 10), "source": "calendar_sales_fact"}
            for (store, div, attribute, label), v in agg.items()
        ]
        if rows:
            session.execute(InputValue.__table__.delete().where(InputValue.lever_key == LEVER_KEY)
                            .where(InputValue.period_id.in_(sorted({r["period_id"] for r in rows}))))
            for i in range(0, len(rows), 5000):
                stmt = pg_insert(InputValue).values(rows[i:i + 5000])
                stmt = stmt.on_conflict_do_update(
                    index_elements=["lever_key", "store_id", "division_code", "period_id", "row_key"],
                    set_={"value": stmt.excluded.value, "source": stmt.excluded.source, "updated_at": datetime.datetime.now(datetime.timezone.utc)},
                )
                session.execute(stmt)

        # 5. FY26 raw month actuals (placeholder base) - full replace every run
        session.execute(pg_insert(LeverDefinition).values(
            lever_key=FY26_LEVER_KEY, label="Store Actuals FY26 (proxy base)", required=False,
            shape="store_division_period").on_conflict_do_nothing())
        session.execute(InputValue.__table__.delete().where(InputValue.lever_key == FY26_LEVER_KEY))
        fy26_rows = [
            {"lever_key": FY26_LEVER_KEY, "store_id": store, "division_code": div, "period_id": period_ids[label],
             "row_key": "", "value": round(v, 10), "source": "calendar_sales_fact"}
            for (store, div, label), v in fy26.items()
        ]
        for i in range(0, len(fy26_rows), 5000):
            session.execute(pg_insert(InputValue).values(fy26_rows[i:i + 5000]))

        result["rows_read"] = len(agg) + len(fy26)
        result["rows_updated"] = len(rows)
        result["rows_added"] = 0
        result["detail"] = {
            "closed_through": closed_through, "snapshot_file": snapshot_name, "source": "calendar.sales_fact",
            "fy26_proxy_rows": len(fy26_rows),
            "calendar_id": cal.calendar_id, "calendar_name": cal.name,
            "months_synced": ref_months, "months_partial_skipped": partial_months,
            "excluded_departments_lakhs": info["excluded_lakhs"],
        }


if __name__ == "__main__":
    run()
    print("store_actuals_sync: done")
