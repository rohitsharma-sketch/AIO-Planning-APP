"""
Store x Department x Day sales (SL_V) from the data lake's DAY-WISE export
-> RS_planning/data/listing/cache/daily.parquet (gitignored, business data).

Why: seasonal windows and festival periods are calendar DATES, not months - a Diwali on
20 Oct one year and 8 Nov the next moves sales between months. build_suggestions.py works
off this day grain so every window can be cut on exact dates.

Source: the same folder the core day-weights sync reads (Postgres sync.sources
'data_lake_day_weights'), newest `<uuid>_<YYYYMMDDTHHMMSS>.parquet` (a periodic full
re-export, ~1.5 GB / 87M rows). Rebuilt only when a newer export appears; the file name,
rows read and date range are stored in the cache's metadata so every number traces back.
Scope: apparel departments only (same token list as build_sales.py), from DAILY_FROM on.

Usage: python build_daily.py [--force]
"""
import datetime
import json
import os
import re
import sys
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import AOP_DIR, DATA_DIR, daywise_dir, sales_dir  # noqa: E402
from build_knowledge_base import DEPT_SPLITS  # noqa: E402  - the Listing app's one old -> new department list
from build_sales import ALLOWED_TOKENS  # noqa: E402  - one apparel scope for every build script

if AOP_DIR not in sys.path:
    sys.path.insert(0, AOP_DIR)
from sync.common import call_with_timeout  # noqa: E402  - stall-safe reads of the network share

CACHE = os.path.join(DATA_DIR, "cache", "daily.parquet")
COLS = ["BILLDATE", "STORE_NAME", "DEPARTMENT", "SL_V"]
DAILY_FROM = datetime.datetime(2022, 1, 1)  # benchmark years start here (festival dates exist from 2021; 2021 H1 = lockdowns)


def latest(folder):
    files = [f for f in call_with_timeout(os.listdir, folder) if re.search(r"_\d{8}T\d{6}\.parquet$", f)]
    if not files:
        raise ValueError(f"No day-wise parquet files in {folder}")
    return os.path.join(folder, max(files, key=lambda f: re.search(r"_(\d{8}T\d{6})\.parquet$", f).group(1)))


def cached_source():
    try:
        meta = pq.read_schema(CACHE).metadata or {}
        return json.loads(meta.get(b"trace", b"{}")).get("source_file")
    except (OSError, ValueError):
        return None


def split_old_departments(df, monthly):
    """The day-wise export (28 Aug 2026) predates the data lake's department split; the month-wise one has it.
    Each old department's day rows are shared between its parts by that store's month split (month-wise SL_V);
    a store-month with no split uses the chain's split that month, then the chain's overall split. So every
    store x month total is exact and the days inside a month follow the old department's pattern. No-op once a
    day-wise export carries the new names. df: STORE_NAME, DEPARTMENT, BILLDATE, SL_V; monthly: + MONTH (Period)."""
    old = [d for d in DEPT_SPLITS if d in set(df["DEPARTMENT"])]
    if not old:
        return df, []
    keep, pieces = df[~df["DEPARTMENT"].isin(old)], []
    for o in old:
        parts = DEPT_SPLITS[o]
        rows = df[df["DEPARTMENT"] == o].assign(MONTH=lambda x: x["BILLDATE"].dt.to_period("M"))
        m = monthly[monthly["DEPARTMENT"].isin(parts)].assign(SL_V=lambda x: x["SL_V"].clip(lower=0))
        store = m.pivot_table(index=["STORE_NAME", "MONTH"], columns="DEPARTMENT", values="SL_V", aggfunc="sum").reindex(columns=parts)
        chain = m.pivot_table(index="MONTH", columns="DEPARTMENT", values="SL_V", aggfunc="sum").reindex(columns=parts)
        overall = m.groupby("DEPARTMENT")["SL_V"].sum().reindex(parts).fillna(0)
        norm = lambda t: t.div(t.sum(axis=1), axis=0).where(t.sum(axis=1) > 0)
        sh = norm(store.fillna(0)).reindex(pd.MultiIndex.from_frame(rows[["STORE_NAME", "MONTH"]]))
        sh = sh.fillna(norm(chain.fillna(0)).reindex(rows["MONTH"]).set_axis(sh.index))
        sh = sh.fillna(overall / overall.sum() if overall.sum() > 0 else 1 / len(parts))
        for p in parts:
            pieces.append(rows.drop(columns="MONTH").assign(DEPARTMENT=p, SL_V=rows["SL_V"].to_numpy() * sh[p].to_numpy()))
    return pd.concat([keep, *pieces], ignore_index=True), old


def _monthly_parts():
    """Month-wise SL_V of every split part (newest month-wise export), for split_old_departments."""
    folder = sales_dir()
    files = [f for f in call_with_timeout(os.listdir, folder) if re.search(r"_\d{8}T\d{6}\.parquet$", f)]
    src = os.path.join(folder, max(files, key=lambda f: re.search(r"_(\d{8}T\d{6})\.parquet$", f).group(1)))
    parts = sorted({p for v in DEPT_SPLITS.values() for p in v})
    t = call_with_timeout(pq.read_table, src, columns=["BILLMONTH", "STORE_NAME", "DEPARTMENT", "SL_V"],
                          filters=[("DEPARTMENT", "in", parts)]).to_pandas()
    t["MONTH"] = pd.to_datetime(t["BILLMONTH"]).dt.to_period("M")
    return t.groupby(["STORE_NAME", "DEPARTMENT", "MONTH"], as_index=False)["SL_V"].sum(), os.path.basename(src)


def build(force=False):
    src = latest(daywise_dir())
    if not force and cached_source() == os.path.basename(src):
        print(f"daily cache already built from {os.path.basename(src)}")
        return
    t0 = time.time()
    pf = call_with_timeout(pq.ParquetFile, src)
    j = pf.schema_arrow.names.index("BILLDATE")
    frames, rows = [], 0
    for i in range(pf.metadata.num_row_groups):
        st = pf.metadata.row_group(i).column(j).statistics
        if st is not None and st.has_min_max and st.max < DAILY_FROM:
            continue
        t = call_with_timeout(pf.read_row_group, i, columns=COLS).to_pandas()
        rows += len(t)
        t = t[t["BILLDATE"] >= DAILY_FROM].dropna(subset=["STORE_NAME", "DEPARTMENT"])
        t = t[t["DEPARTMENT"].str.split("_", n=1).str[0].isin(ALLOWED_TOKENS)]
        if len(t):
            t["BILLDATE"] = t["BILLDATE"].dt.normalize()
            frames.append(t.groupby(["STORE_NAME", "DEPARTMENT", "BILLDATE"], as_index=False)["SL_V"].sum())
        if i % 50 == 0:
            print(f"  row group {i + 1}/{pf.metadata.num_row_groups} · {rows:,} rows read · {time.time() - t0:.0f}s", flush=True)
    df = pd.concat(frames, ignore_index=True)
    df = df.groupby(["STORE_NAME", "DEPARTMENT", "BILLDATE"], as_index=False)["SL_V"].sum()  # a key can span row groups
    split = {}
    if set(DEPT_SPLITS) & set(df["DEPARTMENT"]):
        monthly, msrc = _monthly_parts()
        df, done = split_old_departments(df, monthly)
        split = {"dept_split": {"departments": done, "month_shares_from": msrc}}
    trace = {**split, "source_file": os.path.basename(src), "source_folder": daywise_dir(), "rows_read": rows,
             "rows_out": len(df), "date_min": str(df["BILLDATE"].min().date()), "date_max": str(df["BILLDATE"].max().date()),
             "from": str(DAILY_FROM.date()), "metric": "SL_V", "built_at": datetime.datetime.now().isoformat(timespec="seconds")}
    tbl = pa.Table.from_pandas(df, preserve_index=False)
    tbl = tbl.replace_schema_metadata({**(tbl.schema.metadata or {}), b"trace": json.dumps(trace).encode()})
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pq.write_table(tbl, CACHE + ".tmp")
    os.replace(CACHE + ".tmp", CACHE)
    print(f"daily cache: {len(df):,} store-dept-days from {rows:,} rows in {time.time() - t0:.0f}s -> {CACHE}")
    print(json.dumps(trace, indent=1))


def demo():
    """Store-month split is exact; a store-month with no split of its own falls back to the chain's month."""
    d = pd.DataFrame({"STORE_NAME": ["A", "A", "B"], "DEPARTMENT": ["MSE_PYJAMA"] * 3, "SL_V": [30.0, 10.0, 8.0],
                      "BILLDATE": pd.to_datetime(["2026-01-05", "2026-01-20", "2026-01-07"])})
    m = pd.DataFrame({"STORE_NAME": ["A", "A", "C", "C"], "DEPARTMENT": ["MSE_HSR PYJAMA", "MSE_TXTL PYJAMA"] * 2,
                      "SL_V": [30.0, 10.0, 10.0, 30.0], "MONTH": pd.Period("2026-01", "M")})
    out, done = split_old_departments(d, m)
    assert done == ["MSE_PYJAMA"] and "MSE_PYJAMA" not in set(out["DEPARTMENT"])
    g = out.groupby(["STORE_NAME", "DEPARTMENT"])["SL_V"].sum()
    assert abs(g["A", "MSE_HSR PYJAMA"] - 30) < 1e-9 and abs(g["A", "MSE_TXTL PYJAMA"] - 10) < 1e-9, g
    assert abs(g["B", "MSE_HSR PYJAMA"] - 4) < 1e-9 and abs(g["B", "MSE_TXTL PYJAMA"] - 4) < 1e-9, g  # chain Jan = 40/40
    assert abs(out["SL_V"].sum() - d["SL_V"].sum()) < 1e-9
    print("demo OK")


if __name__ == "__main__":
    demo() if "--test" in sys.argv else build(force="--force" in sys.argv)
