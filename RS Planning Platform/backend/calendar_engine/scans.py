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


def _scan_parquet_link(progress=None):
    """Read only BILLMONTH + STORE_NAME across every .parquet file in PARQUET_DIR.
    No sales figures are read or processed here - this is detection only."""
    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "*.parquet")))
    if not files:
        raise FileNotFoundError(f"No .parquet files found under {PARQUET_DIR}")
    if progress is not None:
        progress["total"] = len(files)

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
        if progress is not None:
            progress["done"] += 1

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


def get_salesdata_link(force_refresh=False, progress=None):
    now = time.time()
    if not force_refresh and _LINK_CACHE["data"] and (now - _LINK_CACHE["at"]) < LINK_CACHE_TTL:
        if progress is not None:  # nothing to read - the in-memory cache IS the whole job
            progress["total"] = progress["done"] = 1
        cached = dict(_LINK_CACHE["data"])
        cached["cached"] = True
        return cached
    try:
        data = _scan_parquet_link(progress=progress)
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
# Single compiled source (replaces the old 4-folder billwise_fy16-20 /
# bill_wise_fy20--23 / billwise_fy-24-26 / billwise_fy26-27 split) - fixes the
# extra-header and attribute mismatches those separately-exported folders had.
DAYWISE_DIRS = [
    (r"\\10.0.1.85\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION"
     r"\data_lake\raw\rs_19_to_26_day_wise_sales_data_compiled"),
]
_LINK_CACHE_DW = {"data": None, "at": 0}


def _latest_daywise_files():
    """Only the single most-recently-modified *.parquet across DAYWISE_DIRS.
    This source drops full compiled re-exports (each one covers the whole
    2019-2026 span on its own), not incremental partitions - reading more
    than one file here would double-count every sale in the overlap, so once
    a newer export lands, every older one is a stale, superseded snapshot to
    ignore, not more data to add. Every day-wise read (link scan, schema
    introspection, and the actual reindex fetch) goes through this so all
    three always agree on which single file is "the" source."""
    candidates = []
    for d in DAYWISE_DIRS:
        candidates.extend(glob.glob(os.path.join(d, "*.parquet")))
    if not candidates:
        return []
    return [max(candidates, key=os.path.getmtime)]


def _scan_daywise_link(progress=None):
    """Read only BILLDATE + STORE_NAME from the latest compiled day-wise file.
    No sales figures are read or processed here - this is detection only."""
    import pyarrow.parquet as pq
    import pandas as pd

    files = _latest_daywise_files()
    if not files:
        raise FileNotFoundError(f"No .parquet files found under {DAYWISE_DIRS}")
    if progress is not None:
        progress["total"] = len(files)

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
        if progress is not None:
            progress["done"] += 1

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


def get_salesdata_link_daywise(force_refresh=False, progress=None):
    now = time.time()
    if not force_refresh and _LINK_CACHE_DW["data"] and (now - _LINK_CACHE_DW["at"]) < LINK_CACHE_TTL:
        if progress is not None:
            progress["total"] = progress["done"] = 1
        cached = dict(_LINK_CACHE_DW["data"])
        cached["cached"] = True
        return cached
    try:
        data = _scan_daywise_link(progress=progress)
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


# ─── Link-scan background job + poll, running in a SEPARATE PROCESS ─────────
# Same reasoning and mechanism as the reindex job below (kept above it since
# this is the one the frontend hits first, on page load) - the scan reads
# real columns out of every source file (day-wise: 86M+ rows across 6 files),
# which carries the exact same GIL-starvation risk proven to freeze the whole
# platform during Run Reindex before that was isolated into its own process.
_LINK_SCAN_JOB_DIR = os.path.join(DB_DIR, "link_scan_jobs")
_LINK_SCAN_JOBS = {}  # {job_id: {"progress_path", "result_path", "started_at"}}


def start_link_scan_job(source_type, force_refresh=False):
    import subprocess
    import uuid as _uuid

    job_id = str(_uuid.uuid4())
    job_dir = os.path.join(_LINK_SCAN_JOB_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    progress_path = os.path.join(job_dir, "progress.json")
    result_path = os.path.join(job_dir, "result.json")

    worker_dir = os.path.dirname(os.path.abspath(__file__))
    worker_script = os.path.join(worker_dir, "link_scan_worker.py")
    log_path = os.path.join(job_dir, "worker.log")
    with open(log_path, "w", encoding="utf-8") as logf:
        subprocess.Popen(
            [sys.executable, worker_script, source_type, "1" if force_refresh else "0", progress_path, result_path],
            stdout=logf, stderr=subprocess.STDOUT, cwd=worker_dir,
        )

    _LINK_SCAN_JOBS[job_id] = {"progress_path": progress_path, "result_path": result_path, "started_at": time.time()}
    return job_id


def poll_link_scan_job(job_id):
    job = _LINK_SCAN_JOBS.get(job_id)
    if job is None:
        return {"ok": False, "status": "error", "error": "Unknown or expired job"}

    if os.path.exists(job["result_path"]):
        try:
            with open(job["result_path"], encoding="utf-8") as f:
                result = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"ok": True, "status": "running", "progressPct": 100}
        if result.get("ok"):
            return {**result, "status": "done", "progressPct": 100}
        return {"ok": False, "status": "error", "error": result.get("error", "Scan failed")}

    progress = {"done": 0, "total": 0}
    if os.path.exists(job["progress_path"]):
        try:
            with open(job["progress_path"], encoding="utf-8") as f:
                progress = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    done, total = progress["done"], progress["total"]
    pct = round(100 * done / total) if total else 0

    # ETA: simple linear extrapolation from the rate observed so far - good
    # enough for "roughly how much longer" on a handful of files, not meant
    # to be exact. None (shown as "estimating…") until at least one file has
    # finished, since a rate computed from zero completed files is meaningless.
    eta_seconds = None
    elapsed = time.time() - job["started_at"]
    if done > 0 and total > done:
        eta_seconds = round(elapsed / done * (total - done))

    return {
        "ok": True, "status": "running", "progressPct": pct,
        "filesDone": done, "filesTotal": total,
        "elapsedSeconds": round(elapsed), "etaSeconds": eta_seconds,
    }


# ─── Reindexing engine ────────────────────────────────────────────────────────
# Metric: Sales Value by default for both sources - SL_V for month-wise,
# SL_V for day-wise too as of the 2026-08-28 compiled export (was NETAMT
# under the old billwise source, which no longer exists in this file at all).
# Row grain: Store x Division for month-wise; day-wise now carries the SAME
# merchandise hierarchy (DIVISION/SECTION/DEPARTMENT/ATTRIBUTE1/ARTICLE_NAME)
# since the compiled source replaced billwise - it is no longer Store-only.
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


def _row_group_stats(pf, date_col):
    """Cheap (footer-only, no data pages read) per-row-group (min, max) of date_col,
    read from parquet footer statistics. Returns None if ANY row group lacks stats
    (caller falls back to reading everything rather than risk skipping data), else
    a list of (min, max) tuples, one per row group, in row-group order."""
    try:
        col_idx = pf.schema_arrow.names.index(date_col)
    except ValueError:
        return None
    out = []
    for i in range(pf.num_row_groups):
        stats = pf.metadata.row_group(i).column(col_idx).statistics
        if stats is None or not stats.has_min_max:
            return None
        out.append((stats.min, stats.max))
    return out


def _read_file_filtered(fp, columns, date_col, lo, hi):
    """Skip entirely (no data read) if the file's own row groups - from footer
    statistics, not a data read - provably have zero overlap with [lo, hi).
    Otherwise read only the OVERLAPPING row groups, off the SAME already-open
    handle used for the stats check.

    Previously this opened the file twice over the network: once via
    ParquetFile() for the stats check, then again inside a separate
    pq.read_table(fp, filters=...) call for the actual data - read_table has
    no way to reuse an already-open handle, so on a slow network share (this
    reads from a \\\\10.0.1.85\\... SMB mount, not local disk) that redundant
    open cost real, measurable wall time per file. read_row_groups() on the
    SAME ParquetFile object gets the same row-group-level pruning benefit
    (only overlapping groups are fetched) from one network round-trip instead
    of two. Row-group pruning is coarse - a group can straddle [lo, hi) with
    only some of its rows actually matching - so the caller's existing exact
    ym-based filter still runs afterward; this only cuts what gets fetched
    over the network, not what counts as a match.
    """
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(fp)  # one footer-only network round-trip
    stats = _row_group_stats(pf, date_col)
    lo_cmp = lo.to_pydatetime() if hasattr(lo, "to_pydatetime") else lo
    hi_cmp = hi.to_pydatetime() if hasattr(hi, "to_pydatetime") else hi

    if stats is None:
        matching = list(range(pf.num_row_groups))  # no stats to prune on - read everything
    else:
        matching = [i for i, (mn, mx) in enumerate(stats) if not (mx < lo_cmp or mn >= hi_cmp)]
        if not matching:
            return None  # provably no matching rows - skip the read entirely

    tbl = pf.read_row_groups(matching, columns=columns)
    if tbl.num_rows == 0:
        return None
    df = tbl.to_pandas()
    mask = (df[date_col] >= lo_cmp) & (df[date_col] < hi_cmp)
    df = df.loc[mask]
    return df if not df.empty else None


# ─── Customisable output fields ──────────────────────────────────────────────
# The reindex used to hardcode exactly which columns it read (STORE_NAME/
# DIVISION/SL_V for month-wise, STORE_NAME/NETAMT for day-wise) even though the
# source parquet carries far more - confirmed by inspecting the actual schema.
# These maps say, per source, which of the source's OTHER real columns are
# offered as optional extra group-by dimensions or alternate sum metrics -
# every name here is a real column in that source, nothing invented. Identifier
# / already-fixed columns (the date column, STORE_NAME, BILLNO, OPENING_DATE)
# are left out because grouping by them either does nothing (already the grain)
# or defeats aggregation entirely (a bill number is unique per row).
SOURCE_SCHEMA = {
    "mw": {
        "path_kind": "single_dir",
        "dimensions": ["SECTION", "DEPARTMENT", "ARTICLE_NAME", "ATTRIBUTE1", "SEASON_TYPE",
                       "DISPLAY_TYPE", "REGION_TYPE", "CLUSTER_TYPE", "STORE_STATUS", "DISTRICT",
                       "STORE_GRADE", "GM_GRADE", "FESTIVAL_GROUPING", "STORE_CURRENT_STATUS",
                       "STORE_DONOR_FILTER", "LOCATION", "TAG_TYPE"],
        "metrics": ["SL_V", "SL_Q", "TAXAMT", "MRPAMT", "EXTAXAMT", "DIS_V", "COST_AMT", "MRP"],
        "default_metric": "SL_V",
        "always_dims": ["STORE_NAME", "DIVISION"],  # DIVISION is default-on, not just always-available
    },
    "dw": {
        # Confirmed against the current compiled export (2026-08-28,
        # c56319b8-...parquet, 17 cols / 7.07M rows) - this source now writes
        # the SQL export's OWN output column names (SL_Q/SL_V/TAXAMT/
        # TTL_DIS_V/COSTAMOUNT, DIVISION/SECTION/DEPARTMENT/ATTRIBUTE1/
        # ARTICLE_NAME/SEASON_TYPE/DISPLAY_TYPE/STORE_STATUS/CLUSTER_TYPE/
        # REGION_TYPE), not the old billwise source's raw ledger columns
        # (ADMSITE_CODE, NETAMT) - those no longer exist in this file at all.
        "path_kind": "multi_dir",
        "dimensions": ["STORE_STATUS", "CLUSTER_TYPE", "REGION_TYPE", "DIVISION", "SECTION",
                       "DEPARTMENT", "ATTRIBUTE1", "ARTICLE_NAME", "SEASON_TYPE", "DISPLAY_TYPE"],
        "metrics": ["SL_V", "SL_Q", "TAXAMT", "TTL_DIS_V", "COSTAMOUNT"],
        "default_metric": "SL_V",
        "always_dims": ["STORE_NAME"],
    },
}


def get_source_schema(source_type):
    """Real columns available for this source, split into optional dimensions
    (group-by candidates) and metrics (summable), read from one representative
    file's footer only - no data read, so this is cheap even for day-wise."""
    if source_type not in SOURCE_SCHEMA:
        return {"ok": False, "error": "source_type must be 'mw' or 'dw'"}
    if source_type == "mw":
        files = sorted(glob.glob(os.path.join(PARQUET_DIR, "*.parquet")))
    else:
        files = _latest_daywise_files()
    if not files:
        return {"ok": False, "error": f"No files found for source '{source_type}'"}
    try:
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(files[0]).schema_arrow.names)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    cfg = SOURCE_SCHEMA[source_type]
    # Filter against the real file in case the schema drifts from this list -
    # never offer a field the actual file doesn't have.
    return {
        "ok": True, "source": source_type,
        "dimensions": [d for d in cfg["dimensions"] if d in available],
        "metrics": [m for m in cfg["metrics"] if m in available],
        "defaultMetric": cfg["default_metric"],
    }


# ─── Frozen raw-data cache: one slot per source, keyed to the sync action ────────
# "Sync" (clicking Sync Selected Months) stamps a syncedAt timestamp on the client.
# The raw sales rows for that sync's months are fetched from the network once and
# held here; every reindex run against the SAME sync (e.g. switching calendars)
# reuses this frozen copy instead of re-reading the network. A new sync (even with
# unchanged months - the user asked to refresh) stamps a new syncedAt, which misses
# the cache and triggers a fresh fetch, replacing the old frozen copy. The cache key
# also carries the extra-dims/metric selection - a run with different customised
# output fields needs different columns read, so it can't reuse a frozen frame
# that was fetched without them.
_RAW_CACHE = {}  # {'dw': {'syncId':..., 'fieldsKey':..., 'df':..., 'rowsRead':..., 'fetchedAt':...}, 'mw': {...}}


def _fetch_raw_daywise(months, progress=None, extra_dims=None, metric_col="SL_V"):
    import pandas as pd

    extra_dims = extra_dims or []
    months_set = set(months)
    lo, hi = _month_bounds(months)
    files = _latest_daywise_files()
    if progress is not None:
        progress["total"] = len(files)

    columns = ["BILLDATE", "STORE_NAME", metric_col] + [c for c in extra_dims if c not in ("BILLDATE", "STORE_NAME", metric_col)]

    # Sequential, not a ThreadPoolExecutor - this used to read up to 8 files
    # concurrently, which sounded like a speedup but actually made the whole
    # platform unresponsive for everyone for several minutes on a multi-month
    # run: several threads all doing sustained CPU-bound pandas/pyarrow work
    # at once inside the SAME process compete hard for the GIL, starving
    # every other request the server needs to handle (confirmed by isolated
    # reproduction - the same fetch, single-threaded and outside the server
    # process, completed in under 2 minutes with no slowdown at all). A
    # somewhat longer fetch phase that leaves the server responsive is a much
    # better trade than a faster one that freezes the app for every user.
    frames = []
    total_read = 0
    for fp in files:
        df = _read_file_filtered(fp, columns, "BILLDATE", lo, hi)
        if progress is not None:
            progress["done"] += 1
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
    empty_cols = {"BILLDATE": pd.Series(dtype="datetime64[ns]"), "STORE_NAME": pd.Series(dtype="object"),
                  metric_col: pd.Series(dtype="float64"), "ym": pd.Series(dtype="object")}
    for c in extra_dims:
        empty_cols.setdefault(c, pd.Series(dtype="object"))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(empty_cols)
    return df, total_read


def _fetch_raw_monthwise(months, progress=None, extra_dims=None, metric_col="SL_V"):
    extra_dims = extra_dims or []
    months_set = set(months)
    lo, hi = _month_bounds(months)
    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "*.parquet")))
    if progress is not None:
        progress["total"] = len(files)

    columns = ["BILLMONTH", "DIVISION", "STORE_NAME", metric_col] + \
        [c for c in extra_dims if c not in ("BILLMONTH", "DIVISION", "STORE_NAME", metric_col)]

    frames = []
    total_read = 0
    for fp in files:
        df = _read_file_filtered(fp, columns, "BILLMONTH", lo, hi)
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
    empty_cols = {"BILLMONTH": pd.Series(dtype="datetime64[ns]"), "DIVISION": pd.Series(dtype="object"),
                  "STORE_NAME": pd.Series(dtype="object"), metric_col: pd.Series(dtype="float64"),
                  "ym": pd.Series(dtype="object")}
    for c in extra_dims:
        empty_cols.setdefault(c, pd.Series(dtype="object"))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(empty_cols)
    return df, total_read


def _get_raw(source, months, sync_id, fetch_fn, progress=None, extra_dims=None, metric_col=None):
    """Returns (df_copy, rows_read, used_cache). df_copy is always a fresh .copy()
    of the frozen/cached data - callers mutate it freely (adding cluster/date
    lookup columns) without ever corrupting the cache for the next run."""
    import time as _time
    fields_key = (tuple(sorted(extra_dims or [])), metric_col)
    slot = _RAW_CACHE.get(source)
    if sync_id and slot and slot.get("syncId") == sync_id and slot.get("fieldsKey") == fields_key:
        if progress is not None:  # nothing to read - the frozen copy IS the whole job
            progress["total"] = progress["done"] = 1
        return slot["df"].copy(), slot["rowsRead"], True
    df, rows_read = fetch_fn(months, progress=progress, extra_dims=extra_dims, metric_col=metric_col)
    if sync_id:  # only freeze when the client sent a real sync marker to key on
        _RAW_CACHE[source] = {"syncId": sync_id, "fieldsKey": fields_key, "df": df, "rowsRead": rows_read, "fetchedAt": _time.time()}
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


def _rows_from_group(grp_df, group_cols, col_col, val_col, key_fields):
    """grp_df is a reset_index() groupby result whose first len(group_cols) columns
    are group_cols in order, followed by col_col and val_col. key_fields[i] is the
    OUTPUT name for group_cols[i] (e.g. 'store' for 'STORE_NAME'; extra dims pass
    their real column name through unchanged, e.g. 'SECTION' -> 'SECTION')."""
    rows = []
    for r in grp_df.itertuples(index=False):
        d = {kf: getattr(r, gc) for kf, gc in zip(key_fields, group_cols)}
        d["col"] = getattr(r, col_col)
        d["value"] = round(float(getattr(r, val_col)), 2)
        rows.append(d)
    return rows


def reindex_daywise(months, store_cluster, day_map, sync_id=None, progress=None, extra_dims=None, metric_col=None):
    extra_dims = [d for d in (extra_dims or []) if d in SOURCE_SCHEMA["dw"]["dimensions"]]
    metric_col = metric_col if metric_col in SOURCE_SCHEMA["dw"]["metrics"] else SOURCE_SCHEMA["dw"]["default_metric"]
    cluster_ref_fut = {c: {p[0]: p[1] for p in pairs} for c, pairs in day_map.items()}

    df, total_read, used_cache = _get_raw("dw", months, sync_id, _fetch_raw_daywise, progress=progress,
                                           extra_dims=extra_dims, metric_col=metric_col)
    for c in extra_dims:
        df[c] = df[c].fillna("(none)")

    group_cols = ["STORE_NAME"] + extra_dims
    key_fields = ["store"] + extra_dims

    # "Actual" grouping: real sales on their own reference date, independent of
    # whether the calendar-shift mapping below succeeds for that row - a store
    # or date missing from the calendar shouldn't make its real sales vanish
    # from the "actual" side too. Computed on the full raw read, before the
    # cluster/date-mapping drops that follow.
    actual_grp = df.groupby(group_cols + [df["BILLDATE"].dt.strftime("%Y-%m-%d")], observed=True)[metric_col].sum().reset_index()
    actual_grp.columns = group_cols + ["ref_iso", metric_col]
    actual_rows = _rows_from_group(actual_grp, group_cols, "ref_iso", metric_col, key_fields)
    actual_columns = sorted(actual_grp["ref_iso"].unique().tolist())

    df["cluster"] = df["STORE_NAME"].map(store_cluster)
    unmapped_stores = sorted(df.loc[df["cluster"].isna(), "STORE_NAME"].unique().tolist())
    df = df.dropna(subset=["cluster"])

    df, unknown_clusters, unknown_cluster_stores = _split_unknown_clusters(df, set(cluster_ref_fut))

    df["ref_iso"] = df["BILLDATE"].dt.strftime("%Y-%m-%d")
    df = _vectorized_lookup(df, "cluster", "ref_iso", "fut_date", cluster_ref_fut)
    unmapped_dates = int(df["fut_date"].isna().sum())
    unmapped_sample = sorted(df.loc[df["fut_date"].isna(), "ref_iso"].unique().tolist())[:20]
    df = df.dropna(subset=["fut_date"])

    # Reference (LY) date most commonly mapped to each future (TY) date column -
    # lets the frontend show a "Reference Date" header row directly above the
    # future-date row in the wide export, so a reader sees at a glance which
    # source date each output column's sales were shifted from. Different
    # clusters can map the same future date to slightly different reference
    # dates (their calendars don't have to shift identically) - this is the
    # PLURALITY across every mapped row for that future date, the same
    # "most common wins" rule reindex_monthwise's own cluster_month_map
    # already uses one level up, not a per-row guarantee.
    ref_date_by_column = df.groupby("fut_date")["ref_iso"].agg(lambda s: s.value_counts().idxmax()).to_dict()

    grp = df.groupby(group_cols + ["fut_date"], observed=True)[metric_col].sum().reset_index()
    rows = _rows_from_group(grp, group_cols, "fut_date", metric_col, key_fields)
    columns = sorted(grp["fut_date"].unique().tolist())

    return {
        "ok": True, "source": "dw", "keyFields": key_fields, "grain": "_".join(f.lower() for f in key_fields), "metric": metric_col,
        "rowsRead": total_read, "rowsMapped": len(df), "rows": rows, "columns": columns,
        "refDateByColumn": ref_date_by_column,
        "actualRows": actual_rows, "actualColumns": actual_columns, "actualRowCount": len(actual_grp),
        "unmappedStores": unmapped_stores, "unmappedDateCount": unmapped_dates, "unmappedDateSample": unmapped_sample,
        "unmappedClusters": unknown_clusters, "unmappedClusterStores": unknown_cluster_stores,
        "usedFrozenSync": used_cache,
    }


def reindex_monthwise(months, store_cluster, day_map, sync_id=None, progress=None, extra_dims=None, metric_col=None):
    extra_dims = [d for d in (extra_dims or []) if d in SOURCE_SCHEMA["mw"]["dimensions"]]
    metric_col = metric_col if metric_col in SOURCE_SCHEMA["mw"]["metrics"] else SOURCE_SCHEMA["mw"]["default_metric"]

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

    df, total_read, used_cache = _get_raw("mw", months, sync_id, _fetch_raw_monthwise, progress=progress,
                                           extra_dims=extra_dims, metric_col=metric_col)
    df["DIVISION"] = df["DIVISION"].fillna("(none)")
    for c in extra_dims:
        df[c] = df[c].fillna("(none)")

    group_cols = ["STORE_NAME", "DIVISION"] + extra_dims
    key_fields = ["store", "division"] + extra_dims

    # "Actual" grouping: real sales on their own reference month, independent of
    # whether the calendar-shift mapping below succeeds for that row - see the
    # matching comment in reindex_daywise. Computed on the full raw read.
    actual_grp = df.groupby(group_cols + ["ym"], observed=True)[metric_col].sum().reset_index()
    actual_rows = _rows_from_group(actual_grp, group_cols, "ym", metric_col, key_fields)
    actual_columns = sorted(actual_grp["ym"].unique().tolist())

    df["cluster"] = df["STORE_NAME"].map(store_cluster)
    unmapped_stores = sorted(df.loc[df["cluster"].isna(), "STORE_NAME"].unique().tolist())
    df = df.dropna(subset=["cluster"])

    df, unknown_clusters, unknown_cluster_stores = _split_unknown_clusters(df, set(cluster_month_map))

    df = _vectorized_lookup(df, "cluster", "ym", "fut_month", cluster_month_map)
    unmapped_months = int(df["fut_month"].isna().sum())
    unmapped_sample = sorted(df.loc[df["fut_month"].isna(), "ym"].unique().tolist())[:20]
    df = df.dropna(subset=["fut_month"])

    # See the matching comment in reindex_daywise - same plurality rule, one
    # grain up (reference MONTH most commonly mapped to each future month).
    ref_date_by_column = df.groupby("fut_month")["ym"].agg(lambda s: s.value_counts().idxmax()).to_dict()

    grp = df.groupby(group_cols + ["fut_month"], observed=True)[metric_col].sum().reset_index()
    rows = _rows_from_group(grp, group_cols, "fut_month", metric_col, key_fields)
    columns = sorted(grp["fut_month"].unique().tolist())

    return {
        "ok": True, "source": "mw", "keyFields": key_fields, "grain": "_".join(f.lower() for f in key_fields), "metric": metric_col,
        "rowsRead": total_read, "rowsMapped": len(df), "rows": rows, "columns": columns,
        "refDateByColumn": ref_date_by_column,
        "actualRows": actual_rows, "actualColumns": actual_columns, "actualRowCount": len(actual_grp),
        "unmappedStores": unmapped_stores, "unmappedDateCount": unmapped_months, "unmappedDateSample": unmapped_sample,
        "unmappedClusters": unknown_clusters, "unmappedClusterStores": unknown_cluster_stores,
        "usedFrozenSync": used_cache,
    }


def _save_sales_snapshot(session, source_type, kind, grain, metric, key_fields, columns, rows, rows_read, rows_mapped, computed_at):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from db.models.calendar import SalesSnapshot

    stmt = pg_insert(SalesSnapshot).values(
        source_type=source_type, kind=kind, grain=grain, metric=metric, key_fields=key_fields,
        columns=columns, rows=rows, rows_read=rows_read, rows_mapped=rows_mapped, computed_at=computed_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_type", "kind"],
        set_={"grain": stmt.excluded.grain, "metric": stmt.excluded.metric, "key_fields": stmt.excluded.key_fields,
              "columns": stmt.excluded.columns, "rows": stmt.excluded.rows,
              "rows_read": stmt.excluded.rows_read, "rows_mapped": stmt.excluded.rows_mapped,
              "computed_at": stmt.excluded.computed_at},
    )
    session.execute(stmt)


def _save_calendarised_sales_snapshot(result):
    """Persist a successful reindex result - both the 'actual' (real sales on
    their own reference date) and 'trend_shifted' (calendar-shifted) sides -
    to Postgres, one row each per source_type, full replace on every run. So
    other apps (e.g. SalesPlan's Sales Sync) can read both straight from the
    DB instead of re-running their own reindex or parquet parse. Best-effort:
    a save failure must never turn a successful reindex into an error for the
    Calendar Engine caller, so it's logged and swallowed."""
    try:
        from db.base import SessionLocal

        session = SessionLocal()
        try:
            now = datetime.datetime.now(datetime.timezone.utc)
            _save_sales_snapshot(session, result["source"], "trend_shifted", result["grain"], result["metric"], result["keyFields"],
                                  result["columns"], result["rows"], result["rowsRead"], result["rowsMapped"], now)
            _save_sales_snapshot(session, result["source"], "actual", result["grain"], result["metric"], result["keyFields"],
                                  result["actualColumns"], result["actualRows"], result["rowsRead"], result["actualRowCount"], now)
            session.commit()
        finally:
            session.close()
    except Exception:
        traceback.print_exc()


def run_reindex(payload, progress=None):
    source = payload.get("source")
    months = payload.get("months") or []
    store_cluster = payload.get("storeCluster") or {}
    day_map = payload.get("dayMap") or {}
    sync_id = payload.get("syncedAt")  # freezes the raw read to this specific sync action
    # Optional customised output fields - real columns from SOURCE_SCHEMA only;
    # reindex_daywise/reindex_monthwise silently drop anything not in that list,
    # so a stale or hand-crafted request can't make the reindex read an arbitrary
    # column off the parquet file.
    extra_dims = payload.get("extraDims") or []
    metric_col = payload.get("metric")
    if source not in ("mw", "dw"):
        return {"ok": False, "error": "source must be 'mw' or 'dw'"}
    if not months:
        return {"ok": False, "error": "months is required"}
    if not day_map:
        return {"ok": False, "error": "dayMap is required (pick a locked calendar)"}
    try:
        result = reindex_daywise(months, store_cluster, day_map, sync_id, progress=progress,
                                  extra_dims=extra_dims, metric_col=metric_col) if source == "dw" \
            else reindex_monthwise(months, store_cluster, day_map, sync_id, progress=progress,
                                    extra_dims=extra_dims, metric_col=metric_col)
        if result.get("ok"):
            _save_calendarised_sales_snapshot(result)
        return result
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ─── Background job + poll, running in a SEPARATE PROCESS ───────────────────
# The plain POST /salesdata/reindex above blocked the request for the whole
# read with zero feedback - a day-wise run reads tens of millions of rows.
#
# This was first tried as a background THREAD (mirroring Buyer's Input
# Sheet's sync-job pattern) - that made progress reporting work, but live
# reproduction proved it doesn't fix the actual problem: a single large
# parquet file's pandas/pyarrow decode can hold the GIL for minutes on its
# own, freezing the ENTIRE server for every user, not just the request that
# started the reindex (confirmed: 18 of 53 concurrent unrelated requests
# failed during one multi-month day-wise run, even after cutting
# _fetch_raw_daywise from 6 concurrent threads down to 1). No amount of
# thread-count tuning fixes that - a thread in the same process shares the
# same GIL no matter what.
#
# So this runs reindex_worker.py in a genuinely separate OS process via
# subprocess.Popen, which has its own independent GIL - however long it
# holds it, the server process answering everyone else's requests is
# unaffected. The reindex functions touch no database (confirmed by
# inspection), so there's no SQLAlchemy session/connection-pool concern
# running them in a fresh process. Progress/result cross the process
# boundary via small JSON files (atomic write-then-rename - see
# reindex_worker.py) rather than a shared in-memory dict, since the two
# processes don't share memory.
_REINDEX_JOB_DIR = os.path.join(DB_DIR, "reindex_jobs")
_REINDEX_JOBS = {}  # {job_id: {"progress_path", "result_path"}} - just the paths; state lives on disk


def start_reindex_job(payload):
    import subprocess
    import uuid as _uuid

    job_id = str(_uuid.uuid4())
    job_dir = os.path.join(_REINDEX_JOB_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    payload_path = os.path.join(job_dir, "payload.json")
    progress_path = os.path.join(job_dir, "progress.json")
    result_path = os.path.join(job_dir, "result.json")
    with open(payload_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    worker_dir = os.path.dirname(os.path.abspath(__file__))
    worker_script = os.path.join(worker_dir, "reindex_worker.py")
    log_path = os.path.join(job_dir, "worker.log")  # captures a real traceback if the worker itself fails to start
    with open(log_path, "w", encoding="utf-8") as logf:
        subprocess.Popen(
            [sys.executable, worker_script, payload_path, progress_path, result_path],
            stdout=logf, stderr=subprocess.STDOUT, cwd=worker_dir,
        )

    _REINDEX_JOBS[job_id] = {"progress_path": progress_path, "result_path": result_path, "log_path": log_path}
    return job_id


def poll_reindex_job(job_id):
    job = _REINDEX_JOBS.get(job_id)
    if job is None:
        return {"ok": False, "status": "error", "error": "Unknown or expired job"}

    if os.path.exists(job["result_path"]):
        try:
            with open(job["result_path"], encoding="utf-8") as f:
                result = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"ok": True, "status": "running", "progressPct": 100}  # result file mid-rename; poll again shortly
        if result.get("ok"):
            return {**result, "status": "done", "progressPct": 100}
        return {"ok": False, "status": "error", "error": result.get("error", "Reindex failed")}

    progress = {"done": 0, "total": 0}
    if os.path.exists(job["progress_path"]):
        try:
            with open(job["progress_path"], encoding="utf-8") as f:
                progress = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass  # progress file mid-write; next poll retries, not fatal
    pct = round(100 * progress["done"] / progress["total"]) if progress["total"] else 0
    return {"ok": True, "status": "running", "progressPct": pct, "filesDone": progress["done"], "filesTotal": progress["total"]}
