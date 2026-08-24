import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

import csv, io, json, os, glob, time, datetime, calendar as _calendar
from collections import Counter
from urllib.parse import urlsplit, parse_qs

DB_DIR = os.path.join(os.path.dirname(__file__), "Local DB")
DB_PATH = os.path.join(DB_DIR, "festival_changelog.json")
DEFAULT_TEMPLATE = os.path.join(DB_DIR, "Default Template.xlsx")
STORE_MAP_PATH = os.path.join(DB_DIR, "store_cluster_map.json")
STORE_LOG_PATH = os.path.join(DB_DIR, "store_cluster_log.json")

# Named state stores persisted as Local DB/<key>.json via /api/state/<key>
STATE_KEYS = {"period_log", "app_state", "calendar_library", "store_cluster_map", "store_cluster_log",
              "salesdata_link_selection", "salesdata_link_selection_daywise"}

# ─── Sales data lake link (read-only; no data is imported/processed in this step) ─
PARQUET_DIR = (r"\\10.0.1.85\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION"
               r"\data_lake\raw\rs_sales_19-_till_date")
_LINK_CACHE = {"data": None, "at": 0}
LINK_CACHE_TTL = 600  # seconds

# ─── Durable last-known-good scan cache (survives restarts and outages) ─────
# _LINK_CACHE above is only an in-memory 10-min TTL to avoid re-hitting the
# network on every request while it's reachable - it's empty again after any
# restart and gives no fallback once it expires mid-outage. This one persists
# a successful scan to disk and is served (clearly marked, see get_salesdata_
# link's `offline` flag) whenever a live scan fails, e.g. this machine is off
# the office LAN/VPN where \\10.0.1.85 lives - instead of the raw
# FileNotFoundError the UI showed before.
_SCAN_CACHE_DIR = os.path.join(DB_DIR, "scan_cache")


def _save_scan_cache(name, data):
    os.makedirs(_SCAN_CACHE_DIR, exist_ok=True)
    with open(os.path.join(_SCAN_CACHE_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)


def _load_scan_cache(name):
    path = os.path.join(_SCAN_CACHE_DIR, f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _mapped_stores():
    try:
        from sqlalchemy import select
        from db.base import SessionLocal
        from db.models.calendar import StoreCalendarCluster

        session = SessionLocal()
        try:
            return {r[0] for r in session.execute(select(StoreCalendarCluster.store_id)).all()}
        finally:
            session.close()
    except Exception:
        pass
    return set()


def _scan_parquet_link():
    """Read only BILLMONTH + STORE_NAME across every .parquet file in PARQUET_DIR.
    No sales figures are read or processed here - this is detection only."""
    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "*.parquet")))
    if not files:
        raise FileNotFoundError(f"No .parquet files found under {PARQUET_DIR}")

    import pyarrow.parquet as pq
    import pandas as pd

    month_counts = {}
    store_set = set()
    row_count = 0
    file_info = []
    for fp in files:
        pf = pq.ParquetFile(fp)
        row_count += pf.metadata.num_rows
        tbl = pf.read(columns=["BILLMONTH", "STORE_NAME"])
        bm = tbl.column("BILLMONTH").to_pandas()
        periods = bm.dropna().dt.to_period("M").astype(str)
        for k, v in periods.value_counts().items():
            month_counts[k] = month_counts.get(k, 0) + int(v)
        store_set.update(tbl.column("STORE_NAME").to_pandas().dropna().unique().tolist())
        file_info.append({"name": os.path.basename(fp), "rows": pf.metadata.num_rows,
                           "sizeBytes": os.path.getsize(fp),
                           "modifiedAt": datetime.datetime.fromtimestamp(
                               os.path.getmtime(fp), datetime.timezone.utc).isoformat()})

    mapped_stores = _mapped_stores()

    months = sorted(month_counts.keys())
    return {
        "ok": True,
        "path": PARQUET_DIR,
        "files": file_info,
        "rowCount": row_count,
        "months": [{"month": m, "rows": month_counts[m]} for m in months],
        "dateRange": {"min": months[0] if months else None, "max": months[-1] if months else None},
        "stores": {
            "inSource": len(store_set),
            "inMapping": len(mapped_stores),
            "matched": sorted(store_set & mapped_stores),
            "unmatchedInSource": sorted(store_set - mapped_stores),
            "unmatchedInMapping": sorted(mapped_stores - store_set),
        },
        "scannedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def get_salesdata_link(force_refresh=False):
    now = time.time()
    if not force_refresh and _LINK_CACHE["data"] and (now - _LINK_CACHE["at"]) < LINK_CACHE_TTL:
        cached = dict(_LINK_CACHE["data"])
        cached["cached"] = True
        return cached
    try:
        data = _scan_parquet_link()
        _LINK_CACHE["data"] = data
        _LINK_CACHE["at"] = now
        _save_scan_cache("salesdata_link", data)
        result = dict(data)
        result["cached"] = False
        return result
    except Exception as e:
        stale = _load_scan_cache("salesdata_link")
        if stale is not None:
            result = dict(stale)
            result["cached"] = True
            result["offline"] = True  # source unreachable right now - this is last-known-good, not live
            return result
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "path": PARQUET_DIR}


# ─── Day-wise (billwise) sources ─────────────────────────────────────────────
# Confirmed with the user: billwise_fy16-20 and billwise_fy-24-26 replace the
# smaller/incomplete billwise_fy16-22 and billwise_fy-24-25 folders, which are
# a near-empty stub and a strict subset respectively - using both would either
# leave a multi-year gap or double-count the overlapping period.
DAYWISE_DIRS = [
    (r"\\10.0.1.85\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION"
     r"\data_lake\raw\billwise_fy16-20"),
    (r"\\10.0.1.85\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION"
     r"\data_lake\raw\bill_wise_fy20--23"),
    (r"\\10.0.1.85\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION"
     r"\data_lake\raw\billwise_fy-24-26"),
    (r"\\10.0.1.85\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION"
     r"\data_lake\raw\billwise_fy26-27"),
]
_LINK_CACHE_DW = {"data": None, "at": 0}


def _scan_daywise_link():
    """Read only BILLDATE + STORE_NAME across each billwise_fy* file. No sales
    figures are read or processed here - this is detection only."""
    import pyarrow.parquet as pq
    import pandas as pd

    files = []
    for d in DAYWISE_DIRS:
        found = sorted(glob.glob(os.path.join(d, "*.parquet")))
        if not found:
            raise FileNotFoundError(f"No .parquet files found under {d}")
        files.extend(found)

    month_counts = {}
    store_set = set()
    row_count = 0
    file_info = []
    all_dates = []  # per-file (min, max) to detect real gaps between files
    for fp in files:
        pf = pq.ParquetFile(fp)
        row_count += pf.metadata.num_rows
        tbl = pf.read(columns=["BILLDATE", "STORE_NAME"])
        bd = tbl.column("BILLDATE").to_pandas().dropna()
        periods = bd.dt.to_period("M").astype(str)
        for k, v in periods.value_counts().items():
            month_counts[k] = month_counts.get(k, 0) + int(v)
        store_set.update(tbl.column("STORE_NAME").to_pandas().dropna().unique().tolist())
        fmin, fmax = (bd.min().date().isoformat(), bd.max().date().isoformat()) if len(bd) else (None, None)
        all_dates.append((fmin, fmax))
        file_info.append({"name": os.path.basename(fp), "folder": os.path.basename(os.path.dirname(fp)),
                           "rows": pf.metadata.num_rows, "sizeBytes": os.path.getsize(fp),
                           "dateMin": fmin, "dateMax": fmax,
                           "modifiedAt": datetime.datetime.fromtimestamp(
                               os.path.getmtime(fp), datetime.timezone.utc).isoformat()})

    # Real gaps: consecutive files (sorted by start date) whose ranges don't touch
    gaps = []
    ordered = sorted([f for f in all_dates if f[0]], key=lambda x: x[0])
    for a, b in zip(ordered, ordered[1:]):
        prev_end = datetime.date.fromisoformat(a[1])
        next_start = datetime.date.fromisoformat(b[0])
        if (next_start - prev_end).days > 1:
            gaps.append({"from": a[1], "to": b[0],
                         "days": (next_start - prev_end).days - 1})

    mapped_stores = _mapped_stores()

    months = sorted(month_counts.keys())
    return {
        "ok": True,
        "sourceType": "daywise",
        "dirs": DAYWISE_DIRS,
        "files": file_info,
        "rowCount": row_count,
        "months": [{"month": m, "rows": month_counts[m]} for m in months],
        "dateRange": {"min": ordered[0][0] if ordered else None, "max": ordered[-1][1] if ordered else None},
        "gaps": gaps,
        "stores": {
            "inSource": len(store_set),
            "inMapping": len(mapped_stores),
            "matched": sorted(store_set & mapped_stores),
            "unmatchedInSource": sorted(store_set - mapped_stores),
            "unmatchedInMapping": sorted(mapped_stores - store_set),
        },
        "scannedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def get_salesdata_link_daywise(force_refresh=False):
    now = time.time()
    if not force_refresh and _LINK_CACHE_DW["data"] and (now - _LINK_CACHE_DW["at"]) < LINK_CACHE_TTL:
        cached = dict(_LINK_CACHE_DW["data"])
        cached["cached"] = True
        return cached
    try:
        data = _scan_daywise_link()
        _LINK_CACHE_DW["data"] = data
        _LINK_CACHE_DW["at"] = now
        _save_scan_cache("salesdata_link_daywise", data)
        result = dict(data)
        result["cached"] = False
        return result
    except Exception as e:
        stale = _load_scan_cache("salesdata_link_daywise")
        if stale is not None:
            result = dict(stale)
            result["cached"] = True
            result["offline"] = True  # source unreachable right now - this is last-known-good, not live
            return result
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "dirs": DAYWISE_DIRS}


# ─── Reindexing engine ────────────────────────────────────────────────────────
# Metric: Sales Value only (SL_V for month-wise, NETAMT for day-wise) - confirmed.
# Row grain: Store x Division for month-wise, Store-only for day-wise - confirmed
# (day-wise/billwise has no product hierarchy to break out by).
# Calendar: caller supplies the locked template's dayMap (LY date -> TY date, per
# cluster) and the resolved store->cluster map; this endpoint does no calendar or
# store-cluster resolution of its own, so there is one source of truth (the app's
# existing client-side resolution logic) for both.

def _month_bounds(months):
    """Contiguous [lo, hi) pandas Timestamp bounds spanning the given YYYY-MM list,
    for parquet predicate pushdown. hi is exclusive (first day of month after max)."""
    import pandas as pd
    lo = pd.Timestamp(min(months) + "-01")
    y, m = (int(x) for x in max(months).split("-"))
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    hi = pd.Timestamp(f"{y:04d}-{m:02d}-01")
    return lo, hi


def _vectorized_lookup(df, cluster_col, key_col, out_col, cluster_maps):
    """out_col[i] = cluster_maps[cluster_col[i]].get(key_col[i]), done per-cluster
    with a vectorized .map() instead of a slow row-wise apply."""
    df[out_col] = None
    for cluster, sub in df.groupby(cluster_col, observed=True):
        m = cluster_maps.get(cluster)
        if not m:
            continue
        df.loc[sub.index, out_col] = sub[key_col].map(m)
    return df


def _row_group_range(pf, date_col):
    """Cheap (footer-only, no data pages read) overall (min, max) of date_col across
    every row group's stored statistics. Returns None if any row group lacks stats,
    so the caller falls back to reading it normally rather than risk skipping data."""
    try:
        col_idx = pf.schema_arrow.names.index(date_col)
    except ValueError:
        return None
    lo = hi = None
    for i in range(pf.num_row_groups):
        stats = pf.metadata.row_group(i).column(col_idx).statistics
        if stats is None or not stats.has_min_max:
            return None
        mn, mx = stats.min, stats.max
        if lo is None or mn < lo:
            lo = mn
        if hi is None or mx > hi:
            hi = mx
    return (lo, hi) if lo is not None else None


def _read_file_filtered(fp, columns, date_col, lo, hi):
    """Open once, skip entirely (no read call) if the file's own min/max for date_col
    - read from parquet footer statistics, not data - has zero overlap with [lo, hi).
    Otherwise read with row-group-level predicate pushdown on date_col."""
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(fp)  # footer-only open; used for the cheap stats check below
    rng = _row_group_range(pf, date_col)
    if rng is not None:
        fmin, fmax = rng
        lo_cmp = lo.to_pydatetime() if hasattr(lo, "to_pydatetime") else lo
        hi_cmp = hi.to_pydatetime() if hasattr(hi, "to_pydatetime") else hi
        if fmax < lo_cmp or fmin >= hi_cmp:
            return None  # provably no matching rows - skip the read entirely
    # ParquetFile.read() has no `filters` kwarg - the predicate-pushdown filtered
    # read has to go through the module-level read_table (dataset-backed) API.
    tbl = pq.read_table(fp, columns=columns, filters=[(date_col, ">=", lo), (date_col, "<", hi)])
    return tbl.to_pandas() if tbl.num_rows else None


# ─── Frozen raw-data cache: one slot per source, keyed to the sync action ────────
# "Sync" (clicking Sync Selected Months) stamps a syncedAt timestamp on the client.
# The raw sales rows for that sync's months are fetched from the network once and
# held here; every reindex run against the SAME sync (e.g. switching calendars)
# reuses this frozen copy instead of re-reading the network. A new sync (even with
# unchanged months - the user asked to refresh) stamps a new syncedAt, which misses
# the cache and triggers a fresh fetch, replacing the old frozen copy.
_RAW_CACHE = {}  # {'dw': {'syncId':..., 'df':..., 'rowsRead':..., 'fetchedAt':...}, 'mw': {...}}


def _fetch_raw_daywise(months, progress=None):
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor

    months_set = set(months)
    lo, hi = _month_bounds(months)
    files = []
    for d in DAYWISE_DIRS:
        files.extend(sorted(glob.glob(os.path.join(d, "*.parquet"))))
    if progress is not None:
        progress["total"] = len(files)

    def _read(fp):
        result = _read_file_filtered(fp, ["BILLDATE", "STORE_NAME", "NETAMT"], "BILLDATE", lo, hi)
        # Files run concurrently (ThreadPoolExecutor below) - a plain += here is
        # not perfectly atomic, but this only feeds a rough progress percentage,
        # not a row count anything downstream depends on, so the GIL's per-op
        # serialization is more than good enough without an explicit lock.
        if progress is not None:
            progress["done"] += 1
        return result

    frames = []
    total_read = 0
    with ThreadPoolExecutor(max_workers=min(8, len(files) or 1)) as ex:
        for df in ex.map(_read, files):
            if df is None or df.empty:
                continue
            total_read += len(df)
            df["ym"] = df["BILLDATE"].dt.strftime("%Y-%m")
            df = df[df["ym"].isin(months_set)]
            if not df.empty:
                frames.append(df)
    # Empty fallback needs the SAME columns (name + dtype) every real per-file
    # frame ends up with above ("ym" included, "BILLDATE" kept datetime64) —
    # a bare pd.DataFrame(columns=[...]) defaults every column to object
    # dtype and omits "ym" entirely, which crashed reindex_daywise/monthwise's
    # downstream `.dt` and `df["ym"]` access with an AttributeError/KeyError
    # whenever the source directory is unreachable (e.g. off the office LAN)
    # instead of reporting "0 rows found" like every other empty-result path.
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame({
        "BILLDATE": pd.Series(dtype="datetime64[ns]"), "STORE_NAME": pd.Series(dtype="object"),
        "NETAMT": pd.Series(dtype="float64"), "ym": pd.Series(dtype="object"),
    })
    return df, total_read


def _fetch_raw_monthwise(months, progress=None):
    months_set = set(months)
    lo, hi = _month_bounds(months)
    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "*.parquet")))
    if progress is not None:
        progress["total"] = len(files)

    frames = []
    total_read = 0
    for fp in files:
        df = _read_file_filtered(fp, ["BILLMONTH", "DIVISION", "STORE_NAME", "SL_V"], "BILLMONTH", lo, hi)
        if progress is not None:
            progress["done"] += 1
        if df is None or df.empty:
            continue
        total_read += len(df)
        df["ym"] = df["BILLMONTH"].dt.strftime("%Y-%m")
        df = df[df["ym"].isin(months_set)]
        if not df.empty:
            frames.append(df)
    import pandas as pd
    # See the matching comment in _fetch_raw_daywise — the fallback must carry
    # the same columns/dtypes real frames get ("ym" included, "BILLMONTH" kept
    # datetime64), or reindex_monthwise's `df["ym"]`/`fut_month` lookups crash
    # instead of reporting zero rows when the source directory is unreachable.
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame({
        "BILLMONTH": pd.Series(dtype="datetime64[ns]"), "DIVISION": pd.Series(dtype="object"),
        "STORE_NAME": pd.Series(dtype="object"), "SL_V": pd.Series(dtype="float64"), "ym": pd.Series(dtype="object"),
    })
    return df, total_read


def _get_raw(source, months, sync_id, fetch_fn, progress=None):
    """Returns (df_copy, rows_read, used_cache). df_copy is always a fresh .copy()
    of the frozen/cached data - callers mutate it freely (adding cluster/date
    lookup columns) without ever corrupting the cache for the next run."""
    import time as _time
    slot = _RAW_CACHE.get(source)
    if sync_id and slot and slot.get("syncId") == sync_id:
        if progress is not None:  # nothing to read - the frozen copy IS the whole job
            progress["total"] = progress["done"] = 1
        return slot["df"].copy(), slot["rowsRead"], True
    df, rows_read = fetch_fn(months, progress=progress)
    if sync_id:  # only freeze when the client sent a real sync marker to key on
        _RAW_CACHE[source] = {"syncId": sync_id, "df": df, "rowsRead": rows_read, "fetchedAt": _time.time()}
    return df.copy(), rows_read, False


def _split_unknown_clusters(df, known_clusters):
    """Separate rows whose cluster has NO entry at all in the calendar's map from
    rows that merely lack a mapping for one specific date/month.

    Both used to fail the same `dropna` and get counted as "unmapped dates", which
    misattributes a cluster-name mismatch (a data-quality problem affecting every
    row of those stores) to a handful of missing calendar days. Returns
    (df_with_known_clusters, unknown_cluster_names, unknown_cluster_stores).
    """
    unknown_mask = ~df["cluster"].isin(known_clusters)
    if not bool(unknown_mask.any()):
        return df, [], []
    unknown = df.loc[unknown_mask]
    names = sorted(unknown["cluster"].unique().tolist())
    stores = sorted(unknown["STORE_NAME"].unique().tolist())
    return df.loc[~unknown_mask], names, stores


def reindex_daywise(months, store_cluster, day_map, sync_id=None, progress=None):
    cluster_ref_fut = {c: {p[0]: p[1] for p in pairs} for c, pairs in day_map.items()}

    df, total_read, used_cache = _get_raw("dw", months, sync_id, _fetch_raw_daywise, progress=progress)
    df["cluster"] = df["STORE_NAME"].map(store_cluster)
    unmapped_stores = sorted(df.loc[df["cluster"].isna(), "STORE_NAME"].unique().tolist())
    df = df.dropna(subset=["cluster"])

    df, unknown_clusters, unknown_cluster_stores = _split_unknown_clusters(df, set(cluster_ref_fut))

    df["ref_iso"] = df["BILLDATE"].dt.strftime("%Y-%m-%d")
    df = _vectorized_lookup(df, "cluster", "ref_iso", "fut_date", cluster_ref_fut)
    unmapped_dates = int(df["fut_date"].isna().sum())
    unmapped_sample = sorted(df.loc[df["fut_date"].isna(), "ref_iso"].unique().tolist())[:20]
    df = df.dropna(subset=["fut_date"])

    grp = df.groupby(["STORE_NAME", "fut_date"], observed=True)["NETAMT"].sum().reset_index()
    rows = [{"store": r.STORE_NAME, "col": r.fut_date, "value": round(float(r.NETAMT), 2)} for r in grp.itertuples()]
    columns = sorted(grp["fut_date"].unique().tolist())

    return {
        "ok": True, "source": "dw", "grain": "store", "metric": "NETAMT",
        "rowsRead": total_read, "rowsMapped": len(df), "rows": rows, "columns": columns,
        "unmappedStores": unmapped_stores, "unmappedDateCount": unmapped_dates, "unmappedDateSample": unmapped_sample,
        "unmappedClusters": unknown_clusters, "unmappedClusterStores": unknown_cluster_stores,
        "usedFrozenSync": used_cache,
    }


def reindex_monthwise(months, store_cluster, day_map, sync_id=None, progress=None):
    # Per-cluster ref-month -> fut-month, by plurality of that month's mapped days
    # (a locked calendar maps individual days; month-wise source only has monthly
    # totals, so each LY month is assigned the TY month most of its days fall in).
    cluster_month_map = {}
    for cluster, pairs in day_map.items():
        buckets = {}
        for p in pairs:
            ref_m, fut_m = p[0][:7], p[1][:7]
            buckets.setdefault(ref_m, Counter())[fut_m] += 1
        cluster_month_map[cluster] = {rm: c.most_common(1)[0][0] for rm, c in buckets.items()}

    df, total_read, used_cache = _get_raw("mw", months, sync_id, _fetch_raw_monthwise, progress=progress)
    df["cluster"] = df["STORE_NAME"].map(store_cluster)
    unmapped_stores = sorted(df.loc[df["cluster"].isna(), "STORE_NAME"].unique().tolist())
    df = df.dropna(subset=["cluster"])

    df, unknown_clusters, unknown_cluster_stores = _split_unknown_clusters(df, set(cluster_month_map))

    df = _vectorized_lookup(df, "cluster", "ym", "fut_month", cluster_month_map)
    unmapped_months = int(df["fut_month"].isna().sum())
    unmapped_sample = sorted(df.loc[df["fut_month"].isna(), "ym"].unique().tolist())[:20]
    df = df.dropna(subset=["fut_month"])

    df["DIVISION"] = df["DIVISION"].fillna("(none)")
    grp = df.groupby(["STORE_NAME", "DIVISION", "fut_month"], observed=True)["SL_V"].sum().reset_index()
    rows = [{"store": r.STORE_NAME, "division": r.DIVISION, "col": r.fut_month, "value": round(float(r.SL_V), 2)} for r in grp.itertuples()]
    columns = sorted(grp["fut_month"].unique().tolist())

    return {
        "ok": True, "source": "mw", "grain": "store_division", "metric": "SL_V",
        "rowsRead": total_read, "rowsMapped": len(df), "rows": rows, "columns": columns,
        "unmappedStores": unmapped_stores, "unmappedDateCount": unmapped_months, "unmappedDateSample": unmapped_sample,
        "unmappedClusters": unknown_clusters, "unmappedClusterStores": unknown_cluster_stores,
        "usedFrozenSync": used_cache,
    }


def run_reindex(payload, progress=None):
    source = payload.get("source")
    months = payload.get("months") or []
    store_cluster = payload.get("storeCluster") or {}
    day_map = payload.get("dayMap") or {}
    sync_id = payload.get("syncedAt")  # freezes the raw read to this specific sync action
    if source not in ("mw", "dw"):
        return {"ok": False, "error": "source must be 'mw' or 'dw'"}
    if not months:
        return {"ok": False, "error": "months is required"}
    if not day_map:
        return {"ok": False, "error": "dayMap is required (pick a locked calendar)"}
    try:
        if source == "dw":
            return reindex_daywise(months, store_cluster, day_map, sync_id, progress=progress)
        return reindex_monthwise(months, store_cluster, day_map, sync_id, progress=progress)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ─── Background job + poll (mirrors Buyer's Input Sheet's sync-job pattern) ──
# The plain POST /salesdata/reindex above blocked the request for the whole
# read with zero feedback - a day-wise run reads tens of millions of rows.
# This runs the same run_reindex() on a background thread and tracks
# "files processed / total files" (see the `progress` dict threaded through
# _fetch_raw_* above) so the frontend can show a real percentage instead.
_REINDEX_JOBS = {}  # {job_id: {"status", "progress": {"done","total"}, "data", "error"}}


def start_reindex_job(payload):
    import threading
    import uuid as _uuid

    job_id = str(_uuid.uuid4())
    progress = {"done": 0, "total": 0}
    _REINDEX_JOBS[job_id] = {"status": "running", "progress": progress, "data": None, "error": None}

    def _run():
        try:
            result = run_reindex(payload, progress=progress)
            if result.get("ok"):
                _REINDEX_JOBS[job_id] = {"status": "done", "progress": progress, "data": result, "error": None}
            else:
                _REINDEX_JOBS[job_id] = {"status": "error", "progress": progress, "data": None, "error": result.get("error")}
        except Exception as e:
            _REINDEX_JOBS[job_id] = {"status": "error", "progress": progress, "data": None, "error": f"{type(e).__name__}: {e}"}

    threading.Thread(target=_run, daemon=True).start()
    return job_id


def poll_reindex_job(job_id):
    job = _REINDEX_JOBS.get(job_id)
    if job is None:
        return {"ok": False, "status": "error", "error": "Unknown or expired job"}
    p = job["progress"]
    pct = round(100 * p["done"] / p["total"]) if p["total"] else 0
    if job["status"] == "done":
        return {**job["data"], "status": "done", "progressPct": 100}
    if job["status"] == "error":
        return {"ok": False, "status": "error", "error": job["error"]}
    return {"ok": True, "status": "running", "progressPct": pct, "filesDone": p["done"], "filesTotal": p["total"]}
