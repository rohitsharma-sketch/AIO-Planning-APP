"""
sync.sources['data_lake_day_weights'] -> calendar.cluster_day_sales

Daily sales per Calendar Engine cluster, from the day-wise data-lake export
(rs_19_to_26_day_wise_sales_data_compiled, one compiled file). Used by
db.calendar_shift to weight the festival shift by real day sales instead of
by day count (user decision 2026-09-25, option b): the month-wise source has
no day field, so the old split valued every moved day at its month's AVERAGE
- e.g. Holi build-up days Feb 25-28 2026 moving into Mar'27 counted as average
Feb days, and 4 ordinary March days moving out counted as average (Holi+Eid
inflated) March days, pulling the LfL KLM Mar'27 base 114.4 -> 109.8 Cr.

Rules:
  * From Jan of last year on (2025-01-01 today) - enough for the 2025->2026
    and 2026->2027 shifts; older days are never shifted.
  * Only stores that already sold in the first month of the window AND in the
    file's last month ("stable" stores), so a store opening or closing
    mid-month can't tilt a cluster's day profile.
  * All divisions summed per cluster x day (SL_V). Full replace each run.

Run manually: python sync/day_weights_sync.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SOURCE_KEY = "data_lake_day_weights"
DAYWISE_DIR = ("//10.0.1.85/Users/Citykart/Desktop/AI_WORK/INVENTORY AUTOMATION"
               "/data_lake/raw/rs_19_to_26_day_wise_sales_data_compiled")
COLUMNS = ["BILLDATE", "STORE_NAME", "SL_V"]

_DDL = """
CREATE TABLE IF NOT EXISTS calendar.cluster_day_sales (
    cluster_name TEXT NOT NULL,
    sale_date DATE NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    stores INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cluster_name, sale_date)
)
"""


def ensure_schema(session):
    """Idempotent: the table + this job's sync.sources row (SyncRun has an FK
    to it) - same CREATE TABLE IF NOT EXISTS pattern as festival_dates_sync."""
    from sqlalchemy import text
    session.execute(text(_DDL))
    session.execute(text(
        "INSERT INTO sync.sources (source_key, config, enabled, ttl_minutes) "
        "VALUES (:k, CAST(:cfg AS JSON), true, 1440) ON CONFLICT (source_key) DO NOTHING"
    ), {"k": SOURCE_KEY, "cfg": '{"path": "%s"}' % DAYWISE_DIR})
    session.commit()


def cluster_day_totals(frames, store_cluster, window_start):
    """Pure: {(cluster, date): (value, n_stores)} from per-row-group frames of
    (BILLDATE, STORE_NAME, SL_V) already aggregated to store x day. Keeps
    stable stores only (sold in the window's first month AND the last month
    present)."""
    import pandas as pd
    df = pd.concat(frames, ignore_index=True).groupby(["STORE_NAME", "BILLDATE"], as_index=False)["SL_V"].sum()
    ym = df["BILLDATE"].dt.to_period("M")
    first, last = pd.Period(window_start, "M"), ym.max()
    stable = set(df.loc[ym == first, "STORE_NAME"]) & set(df.loc[ym == last, "STORE_NAME"])
    df = df[df["STORE_NAME"].isin(stable)].copy()
    df["cluster"] = df["STORE_NAME"].map(store_cluster)
    df = df.dropna(subset=["cluster"])
    g = df.groupby(["cluster", "BILLDATE"]).agg(value=("SL_V", "sum"), stores=("STORE_NAME", "nunique"))
    return {(cl, d.date()): (float(v), int(n)) for (cl, d), v, n in zip(g.index, g["value"], g["stores"])}


def _read_store_days(path, window_start):
    """Store x day SL_V from every row group that can hold dates >= window_start
    (footer stats; each group read under the stall-safe timeout)."""
    import pandas as pd
    import pyarrow.parquet as pq
    from sync.common import call_with_timeout

    pf = call_with_timeout(pq.ParquetFile, path)
    md, j = pf.metadata, pf.schema_arrow.names.index("BILLDATE")
    lo = datetime.datetime.combine(window_start, datetime.time())
    frames, rows_read = [], 0
    for i in range(md.num_row_groups):
        st = md.row_group(i).column(j).statistics
        if st is not None and st.has_min_max and st.max < lo:
            continue
        df = call_with_timeout(pf.read_row_group, i, columns=COLUMNS).to_pandas()
        rows_read += len(df)
        df = df[df["BILLDATE"] >= pd.Timestamp(lo)]
        if len(df):
            df["BILLDATE"] = df["BILLDATE"].dt.normalize()
            frames.append(df.groupby(["STORE_NAME", "BILLDATE"], as_index=False)["SL_V"].sum())
    return frames, rows_read


def run(today=None):
    from sqlalchemy import text
    from db.base import SessionLocal
    from sync.common import latest_file, sync_run

    with SessionLocal() as s:
        ensure_schema(s)
    window_start = datetime.date((today or datetime.date.today()).year - 1, 1, 1)
    with sync_run(SOURCE_KEY) as (session, result):
        path = latest_file(DAYWISE_DIR)
        frames, rows_read = _read_store_days(path, window_start)
        store_cluster = dict(session.execute(text(
            "SELECT store_id, cluster_name FROM calendar.store_calendar_clusters")).all())
        totals = cluster_day_totals(frames, store_cluster, window_start) if frames else {}
        if not totals:
            raise RuntimeError(f"No day-wise sales on/after {window_start} in {os.path.basename(path)} - table left unchanged")
        session.execute(text("DELETE FROM calendar.cluster_day_sales"))
        session.execute(text(
            "INSERT INTO calendar.cluster_day_sales (cluster_name, sale_date, value, stores) VALUES (:c, :d, :v, :n)"),
            [{"c": c, "d": d, "v": v, "n": n} for (c, d), (v, n) in totals.items()])
        days = sorted({d for _, d in totals})
        result["rows_read"] = rows_read
        result["rows_updated"] = len(totals)
        result["rows_added"] = 0
        result["detail"] = {"file": os.path.basename(path), "from": days[0].isoformat(), "to": days[-1].isoformat(),
                            "clusters": len({c for c, _ in totals})}
        print(f"[{SOURCE_KEY}] {len(totals)} cluster-days, {days[0]} .. {days[-1]}, from {rows_read:,} rows")


if __name__ == "__main__":
    run()
