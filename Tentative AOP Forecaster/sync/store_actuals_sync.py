"""
sync.sources['data_lake_sales'] (+ calendar.calendars / calendar_day_pairs /
store_calendar_clusters) -> planning_inputs.input_values (lever_key='store_actuals')

Faithful port of the Calendar Engine's reindex_monthwise() (Calendar Engine/
local_server.py) plus the AOP Forecaster's calendar_sync.py roll-up — computed
locally now, no dependency on the :7822 server:

  1. Per Calendar Cluster, collapse the locked calendar's daily dayMap into a
     ref-month -> fut-month mapping by plurality of that month's mapped days
     (a past month's total sales moves wholesale to whichever future month
     most of its days fall into — rs_sales is month-grain, not daily, so this
     is the same trick reindex_monthwise() uses to avoid needing daily sales).
  2. Map each sales row's STORE_NAME -> Calendar Cluster -> fut_month, sum SL_V
     grouped by (store, DIVISION, fut_month).
  3. Roll DIVISION up to GM/KIDS/LADIES/MENS/RETAIL (GM = 8 GM departments;
     DND/NON-TRADING/FIXED ASSETS/CDIT/CONSIGNMENT excluded) — calendar_sync.py's
     _norm_div.
  4. fut_month (e.g. "2027-04") -> the FY27 period label, same month previous
     year ("Apr'26") — calendar_sync.py's _fut_to_label — convert Rupees to
     Lakhs, and skip months not yet closed in the data lake: a month is closed
     only when the export accounts for its LAST day (snapshot stamp - 1 day,
     see sync.common.snapshot_last_day). The result is persisted as
     sync_runs.detail["closed_through"] ('YYYY-MM') - the single value the
     engine / reindex / UI read (sync.common.get_closed_through) instead of
     recomputing a cutoff from today's date.
  5. Also writes the raw (not reindexed) FY26 months Mar'25..Feb'26 to
     lever_key='store_actuals_fy26' - the placeholder base the engine uses for
     an FY28 month whose FY27 base month hasn't closed yet (option b, 2026-09-24).

Run manually: python sync/store_actuals_sync.py [--include-partial]
"""
import datetime
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.calendar import Calendar, CalendarDayPair, StoreCalendarCluster
from db.models.planning_inputs import InputValue, LeverDefinition, Period
from db.models.sync import SyncSource
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

DIVS = ["GM", "KIDS", "LADIES", "MENS", "RETAIL"]
GM_DEPTS = {"HOUSEHOLD", "LIFESTYLE", "NON FOOD", "HOME FURNISHING", "SPORTS & TOYS",
            "FOOTWEAR", "TRAVEL ACCESSORIES", "STATIONERY"}
LAKH = 1e5


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


def _norm_div(d):
    d = " ".join(str(d or "").upper().split())
    if d in DIVS:
        return d
    if d in GM_DEPTS:
        return "GM"
    return None


def _month_bounds(months):
    lo = pd.Timestamp(min(months) + "-01")
    y, m = (int(x) for x in max(months).split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    hi = pd.Timestamp(f"{y:04d}-{m:02d}-01")
    return lo, hi


def _fetch_raw_monthwise(folder, months):
    # Full re-exports: the newest file always contains all historical data.
    # Read only it instead of every file to avoid OOM on accumulated snapshots.
    from sync.common import call_with_timeout, latest_file
    months_set = set(months)
    lo, hi = _month_bounds(months)
    tbl = call_with_timeout(
        pq.read_table,
        latest_file(folder),
        columns=["BILLMONTH", "DIVISION", "STORE_NAME", "SL_V", "ATTRIBUTE1"],
        filters=[("BILLMONTH", ">=", lo), ("BILLMONTH", "<", hi)],
    )
    df = tbl.to_pandas()
    total_read = len(df)
    df["ym"] = df["BILLMONTH"].dt.strftime("%Y-%m")
    df = df[df["ym"].isin(months_set)]
    return df, total_read


def _closed_through(snapshot_name, latest_month_in_data, today=None):
    """'YYYY-MM' of the last month the export fully accounts for. Unstamped
    export -> the old date rule (neither today's month nor the data's latest
    month counts as closed). Never later than the data's own latest month."""
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


def run(include_partial=False):
    with sync_run(SOURCE_KEY) as (session, result):
        # 1. resolve the active calendar (latest saved, matching REF_YEAR) and its
        #    per-cluster day pairs -> ref-month -> fut-month plurality map
        cal = session.execute(
            select(Calendar).where(Calendar.ref_year == REF_YEAR).order_by(Calendar.saved_at.desc())
        ).scalars().first()
        if cal is None:
            raise LookupError(f"No locked calendar with refYear {REF_YEAR} found — save one via the Calendarisation Suite (/calendar/)")

        pairs = session.execute(
            select(CalendarDayPair).where(CalendarDayPair.calendar_id == cal.calendar_id)
        ).scalars().all()
        cluster_month_map = {}
        buckets_by_cluster = {}
        for p in pairs:
            ref_m, fut_m = p.ref_date.isoformat()[:7], p.fut_date.isoformat()[:7]
            buckets_by_cluster.setdefault(p.cluster_name, {}).setdefault(ref_m, Counter())[fut_m] += 1
        for cluster, buckets in buckets_by_cluster.items():
            cluster_month_map[cluster] = {rm: c.most_common(1)[0][0] for rm, c in buckets.items()}

        # 2. store -> Calendar Cluster
        store_cluster = dict(session.execute(
            select(StoreCalendarCluster.store_id, StoreCalendarCluster.cluster_name)
        ).all())

        # 3. reference months = FY27_M, minus any that may still be incomplete in the lake
        source = session.get(SyncSource, SOURCE_KEY)
        path = source.config["path"]
        ref_months_all = [_label_to_ym(m) for m in FY27_M]
        # max-month probe — only the latest file (full re-export contains all history)
        from sync.common import call_with_timeout, latest_file
        snapshot = latest_file(path)
        bm = call_with_timeout(pq.read_table, snapshot, columns=["BILLMONTH"]).column("BILLMONTH").to_pandas()
        all_months = set(bm.dropna().dt.strftime("%Y-%m").unique().tolist())
        latest_month_in_data = max(all_months) if all_months else None
        closed_through = _closed_through(os.path.basename(snapshot), latest_month_in_data)

        ref_months, partial_months = _complete_months(ref_months_all, closed_through, include_partial)
        if not ref_months:
            raise RuntimeError("No complete reference months available yet")

        # 4. read + reindex (reindex_monthwise, ported) - one read covers the
        #    FY26 proxy months too (disjoint from ref_months, split right after)
        df, rows_read = _fetch_raw_monthwise(path, ref_months + FY26_YM)
        fy26_df = df[df["ym"].isin(FY26_YM)]
        df = df[df["ym"].isin(ref_months)].copy()
        df["cluster"] = df["STORE_NAME"].map(store_cluster)
        unmapped_stores = sorted(df.loc[df["cluster"].isna(), "STORE_NAME"].unique().tolist())
        df = df.dropna(subset=["cluster"])

        def _fut_month(row):
            return cluster_month_map.get(row["cluster"], {}).get(row["ym"])

        df["fut_month"] = df.apply(_fut_month, axis=1)
        df = df.dropna(subset=["fut_month"])

        df["DIVISION"] = df["DIVISION"].fillna("(none)")
        # ATTRIBUTE1 carried through as its own group so a store/division/month's
        # sales split by attribute instead of collapsing into one row - see
        # row_key below. A missing/blank ATTRIBUTE1 still needs a real string
        # (not NaN) to group and to satisfy input_values' NOT NULL row_key.
        # (Was SEASON_TYPE - its real values turned out to be collection codes
        # like AW26/SS26, not the Regular/Occasional/etc business attribute
        # this filter actually needs; ATTRIBUTE1 is the confirmed real column.)
        df["ATTRIBUTE1"] = df["ATTRIBUTE1"].fillna("(none)").astype(str).str.strip()
        grp = df.groupby(["STORE_NAME", "DIVISION", "ATTRIBUTE1", "fut_month"], observed=True)["SL_V"].sum().reset_index()

        # 5. roll up division, relabel to FY27 period, convert to Lakhs
        excluded_lakhs = {}
        agg = {}
        for r in grp.itertuples():
            div = _norm_div(r.DIVISION)
            if div is None:
                excluded_lakhs[r.DIVISION] = excluded_lakhs.get(r.DIVISION, 0.0) + r.SL_V / LAKH
                continue
            label = _fut_to_label(r.fut_month)
            if label not in FY27_M:
                continue
            key = (r.STORE_NAME.strip(), div, r.ATTRIBUTE1, label)
            agg[key] = agg.get(key, 0.0) + r.SL_V / LAKH

        # 6. write into planning_inputs.input_values (upsert on the identity constraint)
        # row_key carries ATTRIBUTE1 - previously always "" (store_actuals had no
        # sub-row dimension), now one row per store x division x period x
        # attribute so engine_v3.py's get_file_info() can filter Q1's base sales
        # down to specific attribute values without losing the rest of the
        # year's totals.
        period_ids = {p.label: p.period_id for p in session.execute(select(Period)).scalars().all()}
        rows = [
            {"lever_key": LEVER_KEY, "store_id": store, "division_code": div, "period_id": period_ids[label],
             "row_key": attribute, "value": round(v, 10), "source": "calendar_sync"}
            for (store, div, attribute, label), v in agg.items()
        ]
        if rows:
            # Delete every existing store_actuals row for each PERIOD about to be
            # (re)written, THEN insert fresh - not just an upsert keyed on the
            # full identity including row_key. Two reasons:
            # (a) migrating off the old scheme, where every row had row_key=""
            #     - those rows share no key with the new attribute-split rows below,
            #       so upsert alone would leave them behind as stale duplicates
            #       that double-count every total downstream.
            # (b) an attribute value (or store/division) that had sales in a PRIOR
            #     sync but genuinely has none this time would otherwise never
            #     get cleared - upsert only touches keys present in this run's
            #     `rows`, it can't remove one that dropped out.
            # Scoped by period_id (small - one per synced month) rather than a
            # precise (store, division, period) tuple list: a full per-combo
            # tuple_().in_() blew past Postgres' ~65535-bound-parameter limit
            # once SEASON_TYPE multiplied row count several times over. This
            # is simpler AND strictly more correct - it also clears a
            # store/division that had actuals last sync but none now, which
            # the old per-combo delete never would have touched either.
            period_ids_to_clear = sorted({period_ids[label] for (_s, _d, _a, label) in agg})
            del_stmt = (
                InputValue.__table__.delete()
                .where(InputValue.lever_key == LEVER_KEY)
                .where(InputValue.period_id.in_(period_ids_to_clear))
            )
            session.execute(del_stmt)

            # Batched, not one bulk INSERT for every row - the same param-count
            # limit above applies here too (7 params/row), and SEASON_TYPE
            # splitting can multiply row count well past a single statement's
            # budget on a large sync.
            BATCH = 5000
            for i in range(0, len(rows), BATCH):
                stmt = pg_insert(InputValue).values(rows[i:i + BATCH])
                stmt = stmt.on_conflict_do_update(
                    index_elements=["lever_key", "store_id", "division_code", "period_id", "row_key"],
                    set_={"value": stmt.excluded.value, "source": stmt.excluded.source, "updated_at": datetime.datetime.now(datetime.timezone.utc)},
                )
                session.execute(stmt)

        # 7. FY26 raw month actuals (placeholder base, see docstring step 5) -
        #    full replace every run, one row per store x division x FY26 month.
        fy26 = {}
        for r in fy26_df.groupby(["STORE_NAME", "DIVISION", "ym"], observed=True)["SL_V"].sum().reset_index().itertuples():
            div = _norm_div(r.DIVISION)
            if div is not None:
                key = (r.STORE_NAME.strip(), div, f"{MON_NAMES[int(r.ym[5:])]}'{r.ym[2:4]}")
                fy26[key] = fy26.get(key, 0.0) + r.SL_V / LAKH
        session.execute(pg_insert(LeverDefinition).values(
            lever_key=FY26_LEVER_KEY, label="Store Actuals FY26 (proxy base)", required=False,
            shape="store_division_period").on_conflict_do_nothing())
        session.execute(InputValue.__table__.delete().where(InputValue.lever_key == FY26_LEVER_KEY))
        fy26_rows = [
            {"lever_key": FY26_LEVER_KEY, "store_id": store, "division_code": div, "period_id": period_ids[label],
             "row_key": "", "value": round(v, 10), "source": "data_lake_raw"}
            for (store, div, label), v in fy26.items()
        ]
        for i in range(0, len(fy26_rows), 5000):
            session.execute(pg_insert(InputValue).values(fy26_rows[i:i + 5000]))

        result["rows_read"] = rows_read
        result["rows_updated"] = len(rows)
        result["rows_added"] = 0
        result["detail"] = {
            "closed_through": closed_through, "snapshot_file": os.path.basename(snapshot),
            "fy26_proxy_rows": len(fy26_rows),
            "calendar_id": cal.calendar_id, "calendar_name": cal.name,
            "months_synced": ref_months, "months_partial_skipped": partial_months,
            "unmapped_stores": unmapped_stores, "excluded_departments_lakhs": {k: round(v, 1) for k, v in excluded_lakhs.items()},
        }


if __name__ == "__main__":
    run(include_partial="--include-partial" in sys.argv)
    print("store_actuals_sync: done")
