"""
Multi-year calendar sales (Phase 0 of "flow all sales for actual and reindexed in all other apps from calendarised app",
user 2026-10-08: "go ahead with phase 0"). Fills calendar.sales_fact (migration b5d1e8f2a9c4) from the newest
month-wise export (rs_common.lake_files - the same file the Calendar reindex reads):

  actual     every CLOSED month from Jan 2019 (store_actuals_sync._closed_through on the same file), on its own month
  reindexed  per saved calendar, each closed reference month spread over its TY months by the Calendar's own split
             (db.calendar_shift.month_plan with the clusters' day sales - what scans.reindex_monthwise and the nightly
             snapshots use), stores mapped by calendar.store_calendar_clusters

Grain: store x raw DIVISION x DEPARTMENT x ATTRIBUTE1 x month, SL_V and SL_Q (rupees / units), plus the planning
division (rs_common.divisions). Blank division / department / attribute -> "(none)", as the Calendar does.

Past months are written once and then frozen (calendar.sales_fact_load.frozen) - later runs skip them, so a restated
old month never changes silently: calendar_check_sync check 8 compares every stored month with the export and fails
loudly instead. A reindexed reference month that still borders a not-yet-closed month (the whole-month rule) is
stored unfrozen and recomputed every run. Rows of a calendar that no longer exists are removed.

Run: python sync/calendar_sales_fact_sync.py [--refresh] [--only actual|reindexed]   (--test: no-DB check)
     (--refresh rewrites frozen months too - after a deliberate restatement)
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))   # repo root: rs_common

import pandas as pd
from sqlalchemy import text

from rs_common.divisions import plan_division
from sync.common import call_with_timeout, latest_file, sync_run

SOURCE_KEY = "calendar_sales_fact"
FIRST_MONTH = "2019-01"
COLS = ["STORE_NAME", "DIVISION", "DEPARTMENT", "ATTRIBUTE1"]
KEYS = ["store", "division", "department", "attribute1"]
FACT_COLS = ["kind", "calendar_id", "ref_month", "month", "store", "division", "plan_division", "department",
             "attribute1", "sl_v", "sl_q"]


def ensure_source():
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text("INSERT INTO sync.sources (source_key, config, enabled, ttl_minutes) "
                        "VALUES (:k, CAST(:cfg AS JSON), true, 1440) ON CONFLICT (source_key) DO NOTHING"),
                   {"k": SOURCE_KEY, "cfg": json.dumps({"note": "Multi-year calendar sales (calendar.sales_fact)"})})
        db.commit()


def _clean(s):
    s = s.astype("object")
    return s.where(s.notna() & (s.astype(str).str.strip() != ""), "(none)")


def read_monthwise(src, lo, hi):
    """store x division x department x attribute x 'YYYY-MM' -> sl_v, sl_q for lo <= month <= hi, read in batches."""
    import pyarrow.parquet as pq
    parts = []
    with open(src, "rb") as fh:   # an open handle: pyarrow mangles UNC paths given as strings
        pf = pq.ParquetFile(fh)
        for b in pf.iter_batches(columns=["BILLMONTH"] + COLS + ["SL_V", "SL_Q"], batch_size=2_000_000):
            df = b.to_pandas()
            df["ym"] = pd.to_datetime(df["BILLMONTH"]).dt.strftime("%Y-%m")
            df = df[(df["ym"] >= lo) & (df["ym"] <= hi) & df["STORE_NAME"].notna()]
            if df.empty:
                continue
            for c in COLS[1:]:
                df[c] = _clean(df[c])
            parts.append(df.groupby(COLS + ["ym"], observed=True, sort=False)[["SL_V", "SL_Q"]].sum().reset_index())
    if not parts:
        return pd.DataFrame(columns=KEYS + ["ym", "sl_v", "sl_q"])
    out = pd.concat(parts).groupby(COLS + ["ym"], observed=True, sort=False)[["SL_V", "SL_Q"]].sum().reset_index()
    out.columns = KEYS + ["ym", "sl_v", "sl_q"]
    out["sl_q"] = out["sl_q"].fillna(0.0)
    return out


def _copy(session, df):
    """COPY a frame (FACT_COLS order) into calendar.sales_fact, on the session's own connection / transaction."""
    buf = io.StringIO()
    df[FACT_COLS].to_csv(buf, index=False, header=False, na_rep="")
    raw = session.connection().connection.dbapi_connection   # psycopg 3
    with raw.cursor() as cur:
        with cur.copy("COPY calendar.sales_fact (" + ",".join(FACT_COLS) + ") FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
            cp.write(buf.getvalue())


def _write_month(session, kind, cal_id, rm, frame, src_name, frozen):
    """Replace one (kind, calendar, reference month) and log it."""
    session.execute(text("DELETE FROM calendar.sales_fact WHERE kind = :k AND calendar_id = :c AND ref_month = :r"),
                    {"k": kind, "c": cal_id, "r": rm})
    if len(frame):
        _copy(session, frame)
    session.execute(text("""
        INSERT INTO calendar.sales_fact_load (kind, calendar_id, ref_month, rows, sl_v, sl_q, source_file, frozen, loaded_at)
        VALUES (:k, :c, :r, :n, :v, :q, :f, :fr, now())
        ON CONFLICT (kind, calendar_id, ref_month) DO UPDATE SET rows = EXCLUDED.rows, sl_v = EXCLUDED.sl_v,
            sl_q = EXCLUDED.sl_q, source_file = EXCLUDED.source_file, frozen = EXCLUDED.frozen, loaded_at = now()"""),
        {"k": kind, "c": cal_id, "r": rm, "n": int(len(frame)), "v": float(frame["sl_v"].sum()) if len(frame) else 0.0,
         "q": float(frame["sl_q"].sum()) if len(frame) else 0.0, "f": src_name, "fr": frozen})
    session.commit()


def _frozen_done(session):
    return {(k, int(c), r.strftime("%Y-%m")) for k, c, r in session.execute(text(
        "SELECT kind, calendar_id, ref_month FROM calendar.sales_fact_load WHERE frozen"))}


def load_actual(session, raw, src_name, refresh):
    done = set() if refresh else _frozen_done(session)
    written = []
    for ym, g in raw.groupby("ym", sort=True):
        if ("actual", 0, ym) in done:
            continue
        rm = f"{ym}-01"
        f = g.assign(kind="actual", calendar_id=0, ref_month=rm, month=rm, plan_division=g["division"].map(plan_division))
        _write_month(session, "actual", 0, rm, f, src_name, True)
        written.append(ym)
    return written


def load_reindexed(session, raw, src_name, closed, refresh):
    from db.calendar_shift import load_day_weights, month_plan
    store_cluster = dict(session.execute(text("SELECT store_id, cluster_name FROM calendar.store_calendar_clusters")).all())
    weights = load_day_weights(session)
    cals = session.execute(text("SELECT calendar_id, name, ref_year FROM calendar.calendars ORDER BY ref_year")).all()
    ids = [int(c.calendar_id) for c in cals]
    # rows of calendars that were deleted / replaced
    gone = session.execute(text("DELETE FROM calendar.sales_fact WHERE kind = 'reindexed' AND calendar_id <> ALL(:ids)"),
                           {"ids": ids}).rowcount
    session.execute(text("DELETE FROM calendar.sales_fact_load WHERE kind = 'reindexed' AND calendar_id <> ALL(:ids)"), {"ids": ids})
    session.commit()
    done = set() if refresh else _frozen_done(session)
    raw = raw.assign(cluster=raw["store"].map(store_cluster))
    out = {"removed_rows_of_old_calendars": int(gone or 0), "calendars": []}
    for cal in cals:
        by_cluster = {}
        for cl, r, f in session.execute(text("SELECT cluster_name, ref_date, fut_date FROM calendar.calendar_day_pairs "
                                             "WHERE calendar_id = :c"), {"c": cal.calendar_id}):
            by_cluster.setdefault(cl, []).append((r, f))
        ref_months = sorted({r.strftime("%Y-%m") for ps in by_cluster.values() for r, _ in ps})
        have = {m for m in ref_months if m in closed}
        plan, frozen = month_plan(by_cluster, weights, have)
        shares = pd.DataFrame([(cl, rm, fm, s) for cl, p in plan.items() for rm, fs in p.items() for fm, s in fs.items() if s > 0],
                              columns=["cluster", "ym", "fut", "share"])
        info = {"calendar_id": int(cal.calendar_id), "name": cal.name, "written": [], "skipped_frozen": 0, "unmapped_L": 0.0}
        for rm in sorted(have):
            unfrozen = any(m == rm for _, m in frozen)
            if ("reindexed", int(cal.calendar_id), rm) in done and not unfrozen:
                info["skipped_frozen"] += 1
                continue
            g = raw[raw["ym"] == rm]
            m = g.merge(shares[shares["ym"] == rm], on=["cluster", "ym"], how="left")
            info["unmapped_L"] = round(info["unmapped_L"] + float(m.loc[m["fut"].isna(), "sl_v"].sum()) / 1e5, 2)
            m = m.dropna(subset=["fut"])
            m = m.assign(sl_v=m["sl_v"] * m["share"], sl_q=m["sl_q"] * m["share"])
            f = m.groupby(KEYS + ["fut"], observed=True, sort=False)[["sl_v", "sl_q"]].sum().reset_index()
            f = f.assign(kind="reindexed", calendar_id=int(cal.calendar_id), ref_month=f"{rm}-01", month=f["fut"] + "-01",
                         plan_division=f["division"].map(plan_division))
            _write_month(session, "reindexed", int(cal.calendar_id), f"{rm}-01", f, src_name, not unfrozen)
            info["written"].append(rm + (" (unfrozen)" if unfrozen else ""))
        out["calendars"].append(info)
    return out


def run(refresh=False, only=None):
    ensure_source()
    with sync_run(SOURCE_KEY) as (session, result):
        t0 = time.time()
        folder = session.execute(text("SELECT config->>'path' FROM sync.sources WHERE source_key = 'data_lake_sales'")).scalar()
        src = latest_file(folder)
        raw = call_with_timeout(read_monthwise, src, FIRST_MONTH, "9999-12", timeout=1800, retries=0)   # whole file, 2019+
        # "closed" by the same rule and file as the AOP base sync (store_actuals_sync._closed_through) - worked out here,
        # since the AOP base now reads this table and runs after it (Phase 1, 2026-10-08)
        from sync.store_actuals_sync import _closed_through
        ct = _closed_through(os.path.basename(src), raw["ym"].max() if len(raw) else None)
        raw = raw[raw["ym"] <= ct]
        closed = set(raw["ym"].unique())
        detail = {"source_file": os.path.basename(src), "closed_through": ct, "months": [min(closed), max(closed)] if closed else [],
                  "raw_cells": int(len(raw)), "raw_total_L": round(float(raw["sl_v"].sum()) / 1e5, 2)}
        if only in (None, "actual"):
            detail["actual_written"] = load_actual(session, raw, os.path.basename(src), refresh)
        if only in (None, "reindexed"):
            detail["reindexed"] = load_reindexed(session, raw, os.path.basename(src), closed, refresh)
        detail["seconds"] = round(time.time() - t0, 1)
        result["rows_read"] = int(len(raw))
        result["rows_added"] = int(session.execute(text("SELECT count(*) FROM calendar.sales_fact")).scalar())
        result["detail"] = detail
        print(json.dumps(detail, default=str)[:3000])


def demo():
    """No-DB check of the batch reader's cleaning."""
    df = pd.DataFrame({"DEPARTMENT": ["A", None, "  "], "x": [1, 2, 3]})
    assert _clean(df["DEPARTMENT"]).tolist() == ["A", "(none)", "(none)"]
    print("calendar_sales_fact demo: OK")


if __name__ == "__main__":
    if "--test" in sys.argv:
        demo()
    else:
        only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
        run(refresh="--refresh" in sys.argv, only=only)
