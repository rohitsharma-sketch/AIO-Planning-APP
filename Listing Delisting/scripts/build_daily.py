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
from _paths import AOP_DIR, DATA_DIR, daywise_dir  # noqa: E402
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
    trace = {"source_file": os.path.basename(src), "source_folder": daywise_dir(), "rows_read": rows,
             "rows_out": len(df), "date_min": str(df["BILLDATE"].min().date()), "date_max": str(df["BILLDATE"].max().date()),
             "from": str(DAILY_FROM.date()), "metric": "SL_V", "built_at": datetime.datetime.now().isoformat(timespec="seconds")}
    tbl = pa.Table.from_pandas(df, preserve_index=False)
    tbl = tbl.replace_schema_metadata({**(tbl.schema.metadata or {}), b"trace": json.dumps(trace).encode()})
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pq.write_table(tbl, CACHE + ".tmp")
    os.replace(CACHE + ".tmp", CACHE)
    print(f"daily cache: {len(df):,} store-dept-days from {rows:,} rows in {time.time() - t0:.0f}s -> {CACHE}")
    print(json.dumps(trace, indent=1))


if __name__ == "__main__":
    build(force="--force" in sys.argv)
