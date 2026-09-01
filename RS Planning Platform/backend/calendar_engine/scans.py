import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

import csv, io, json, os, glob, time, datetime, calendar as _calendar, traceback, hashlib
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


def _months_between(lo, hi):
    """Every 'YYYY-MM' label from lo's month through hi's month, inclusive -
    used to expand one row group's (min, max) BILLDATE bound into the set of
    months it touches, without reading which specific days actually have rows.
    A row group spanning Jan 5 - Mar 10 with zero real rows in February would
    report February as covered anyway - the same approximation trade-off the
    footer-only date-range PRUNING elsewhere in this file already accepts
    (_read_file_filtered's docstring: "coarse... only cuts what gets fetched,
    not what counts as a match"). Acceptable here because nothing downstream
    reads exact per-month counts (confirmed against LinkStatusPanel.jsx -
    only `.month` labels and the file-level `rowCount` are ever displayed)."""
    out = []
    y, m = lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _scan_daywise_link(progress=None):
    """Detects which months + stores the latest compiled day-wise file covers.

    Month/date-range detection is footer-only (row-group min/max BILLDATE
    statistics, the same _row_group_stats() every reindex read already prunes
    with) - no BILLDATE column data is read at all. Store detection genuinely
    needs real data (a distinct-value set isn't in the footer), so that part
    reads STORE_NAME alone - still half the I/O/memory the previous version
    used (BILLDATE + STORE_NAME, in full, across all 87M+ rows), which was
    the actual cause of this scan taking minutes and looking hung: its own
    docstring claimed "no data read... detection only" while doing exactly
    the opposite of that for BILLDATE.
    """
    import pyarrow.parquet as pq

    files = _latest_daywise_files()
    if not files:
        raise FileNotFoundError(f"No .parquet files found under {DAYWISE_DIRS}")
    if progress is not None:
        progress["total"] = len(files)

    months_seen = set()
    store_set = set()
    row_count = 0
    file_info = []
    all_dates = []  # per-file (min, max) to detect real gaps between files
    for fp in files:
        pf = pq.ParquetFile(fp)
        row_count += pf.metadata.num_rows

        stats = _row_group_stats(pf, "BILLDATE")
        if stats:
            fmin = min(mn for mn, _ in stats)
            fmax = max(mx for _, mx in stats)
            for mn, mx in stats:
                months_seen.update(_months_between(mn.date() if hasattr(mn, "date") else mn,
                                                    mx.date() if hasattr(mx, "date") else mx))
            fmin_s, fmax_s = fmin.date().isoformat() if hasattr(fmin, "date") else str(fmin), \
                             fmax.date().isoformat() if hasattr(fmax, "date") else str(fmax)
        else:
            # No footer stats on this file (rare/older writer) - fall back to
            # actually reading the column rather than reporting nothing.
            bd = pf.read(columns=["BILLDATE"]).column("BILLDATE").to_pandas().dropna()
            if len(bd):
                months_seen.update(bd.dt.to_period("M").astype(str).unique().tolist())
                fmin_s, fmax_s = bd.min().date().isoformat(), bd.max().date().isoformat()
            else:
                fmin_s, fmax_s = None, None
        all_dates.append((fmin_s, fmax_s))

        store_set.update(pf.read(columns=["STORE_NAME"]).column("STORE_NAME").to_pandas().dropna().unique().tolist())

        file_info.append({"name": os.path.basename(fp), "folder": os.path.basename(os.path.dirname(fp)),
                           "rows": pf.metadata.num_rows, "sizeBytes": os.path.getsize(fp),
                           "dateMin": fmin_s, "dateMax": fmax_s,
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

    months = sorted(months_seen)
    return {
        "ok": True,
        "sourceType": "daywise",
        "dirs": DAYWISE_DIRS,
        "files": file_info,
        "rowCount": row_count,
        # `rows` is no longer computed per month (it required the full
        # BILLDATE read this rewrite removes) - nothing in the frontend reads
        # it, only `.month` labels and the file-level rowCount above.
        "months": [{"month": m, "rows": None} for m in months],
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

    # A link scan is just "is anything new in the source" - not the sync
    # action itself, and LinkStatusPanel fires this on every single mount
    # (every page visit / login). Re-running even the fast footer-only dw
    # scan (~9s) or the mw scan on every visit is pure overhead the user
    # never asked for - the durable last-known scan (_save_scan_cache,
    # written by get_salesdata_link[_daywise] on every real scan, survives
    # restarts) is served here INSTANTLY with no subprocess at all unless
    # the caller explicitly forces a refresh (the Refresh/Sync button) or no
    # scan has ever completed yet. This is what "keep it in cache until the
    # user force syncs it" means in practice for both mw and dw.
    if not force_refresh:
        cache_name = "salesdata_link_daywise" if source_type == "dw" else "salesdata_link"
        cached = _load_scan_cache(cache_name)
        if cached is not None:
            result = dict(cached)
            result["cached"] = True
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f)
            with open(progress_path, "w", encoding="utf-8") as f:
                json.dump({"done": 1, "total": 1}, f)
            _LINK_SCAN_JOBS[job_id] = {"progress_path": progress_path, "result_path": result_path, "started_at": time.time()}
            return job_id

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
    lookup columns) without ever corrupting the cache for the next run.

    The cached slot can cover MORE months than a given call asks for - see
    run_reindex's pre-warm, which fetches every uncached (closed-but-not-yet-
    cached) month for a run in ONE pass (one file open + row-group scan)
    instead of the N separate reads the old one-call-per-reference-month
    loop did (each of those calls is still what makes a single reference
    month's result safe to cache on its own - see ReindexMonthCache). A
    request whose months are a SUBSET of what's already cached is served by
    filtering the cached frame in memory (cheap) instead of re-reading the
    source; an exact or wider request still requires a fresh fetch, since
    filtering can only ever narrow, not widen, what's already in memory."""
    import time as _time
    months_set = set(months)
    fields_key = (tuple(sorted(extra_dims or [])), metric_col)
    slot = _RAW_CACHE.get(source)
    if sync_id and slot and slot.get("syncId") == sync_id and slot.get("fieldsKey") == fields_key \
            and months_set <= slot.get("months", set()):
        if progress is not None:  # nothing to read - the frozen copy already covers this request
            progress["total"] = progress["done"] = 1
        df = slot["df"]
        if months_set != slot["months"]:
            df = df[df["ym"].isin(months_set)]
        return df.copy(), int(len(df)), True
    df, rows_read = fetch_fn(months, progress=progress, extra_dims=extra_dims, metric_col=metric_col)
    if sync_id:  # only freeze when the client sent a real sync marker to key on
        _RAW_CACHE[source] = {"syncId": sync_id, "fieldsKey": fields_key, "months": months_set, "df": df, "rowsRead": rows_read, "fetchedAt": _time.time()}
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
        v = float(getattr(r, val_col))
        # A NaN/Infinity here (a genuine data-quality gap - null/malformed
        # source values propagating through a SUM - is plausible at tens of
        # millions of rows even though every smaller run to date has been
        # clean) serializes as the bare token NaN/Infinity, which is valid
        # for Python's json module but NOT valid JSON - Postgres' JSONB
        # parser rejects it outright, failing the whole snapshot save over
        # one bad row. 0.0 matches this codebase's existing NVL-style
        # "swallow bad data, don't corrupt the whole result" convention.
        d["value"] = round(v, 2) if v == v and v not in (float("inf"), float("-inf")) else 0.0
        rows.append(d)
    return rows


def reindex_daywise(months, store_cluster, day_map, sync_id=None, progress=None, extra_dims=None, metric_col=None):
    import pandas as pd

    extra_dims = [d for d in (extra_dims or []) if d in SOURCE_SCHEMA["dw"]["dimensions"]]
    metric_col = metric_col if metric_col in SOURCE_SCHEMA["dw"]["metrics"] else SOURCE_SCHEMA["dw"]["default_metric"]

    # Long (cluster, ref_iso, fut_date) mapping table - one row per pair in
    # day_map - instead of a {ref_iso: fut_date} dict. A locked calendar can
    # legitimately reuse the same reference day for two different future
    # days (engine.js's "Same-Month Reuse"/leap-year fallback, sharedRef:
    # when a month's own reference days run out, the algorithm reuses the
    # nearest already-used one from that SAME month rather than crossing
    # into another month). A dict keyed by ref_iso can only hold one fut_date
    # per key, so a reused reference day silently dropped its earlier
    # mapping here - found live 2026-09-01 as future dates going completely
    # missing from reindexed output. The merge below fans a reused
    # reference day's sales out to every future day it maps to, instead of
    # picking just one.
    ref_fut_rows = [(c, p[0], p[1]) for c, pairs in day_map.items() for p in pairs]
    ref_fut_map = pd.DataFrame(ref_fut_rows, columns=["cluster", "ref_iso", "fut_date"])
    known_clusters = set(day_map)

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

    df, unknown_clusters, unknown_cluster_stores = _split_unknown_clusters(df, known_clusters)

    df["ref_iso"] = df["BILLDATE"].dt.strftime("%Y-%m-%d")
    # merge (not _vectorized_lookup's dict .map()) so a reference day mapped
    # to more than one future day fans this row out to each of them, instead
    # of collapsing to a single fut_date - see ref_fut_map's comment above.
    df = df.merge(ref_fut_map, on=["cluster", "ref_iso"], how="left")
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


# Dims worth persisting to Postgres, independent of whatever extra fields a
# planner ticked under "Customise Output Fields" for their OWN on-screen
# view/download. db/reindexed_base_sales.py (AOP's consumer, the only known
# reader of these snapshots) only ever looks at DIVISION (always) and
# ATTRIBUTE1 (conditionally, for its Q1-quarter filter) - everything else
# (DEPARTMENT, SECTION, ARTICLE_NAME, SEASON_TYPE, DISPLAY_TYPE, STORE_STATUS,
# CLUSTER_TYPE, REGION_TYPE) inflates row count for zero downstream benefit.
# "store" is always kept - it's the base grain, added separately below.
_PERSIST_DIMS = {"DIVISION", "ATTRIBUTE1"}


def _collapse_for_persistence(key_fields, rows):
    """Re-aggregate `rows` down to only the dims _PERSIST_DIMS actually uses,
    summing `value` across whatever's dropped. Confirmed necessary, not just
    an optimisation: a real day-wise reindex at full history (store x DIVISION
    x DEPARTMENT x ATTRIBUTE1 x date) produced 7.2M rows, and Postgres saving
    that as a single JSONB value failed with WinError 10055 (socket send
    buffer exhausted) - the save was silently swallowed by the best-effort
    try/except around it, so the reindex reported success while the database
    never actually got the data. Collapsing to only the dims anything reads
    keeps this bounded (store x division x date, optionally x attribute) -
    the same order of magnitude as month-wise's own row count, not two orders
    larger."""
    keep = [kf for kf in key_fields if kf in _PERSIST_DIMS or kf == "store"]
    if keep == key_fields:
        return key_fields, rows  # nothing to drop - already at (or under) the kept set
    totals = {}
    order = []  # preserve first-seen order for stable, deterministic output
    for r in rows:
        key = tuple(r[k] for k in keep) + (r["col"],)
        if key not in totals:
            totals[key] = 0.0
            order.append(key)
        totals[key] += r["value"]
    collapsed = [
        {**dict(zip(keep, key[:-1])), "col": key[-1], "value": round(totals[key], 2)}
        for key in order
    ]
    return keep, collapsed


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
            ts_keep, ts_rows = _collapse_for_persistence(result["keyFields"], result["rows"])
            actual_keep, actual_rows = _collapse_for_persistence(result["keyFields"], result["actualRows"])
            _save_sales_snapshot(session, result["source"], "trend_shifted", result["grain"], result["metric"], ts_keep,
                                  result["columns"], ts_rows, result["rowsRead"], len(ts_rows), now)
            _save_sales_snapshot(session, result["source"], "actual", result["grain"], result["metric"], actual_keep,
                                  result["actualColumns"], actual_rows, result["rowsRead"], len(actual_rows), now)
            session.commit()
        finally:
            session.close()
    except Exception:
        traceback.print_exc()


def _is_month_closed(ym, today=None):
    """A reference month is 'closed' once it has fully elapsed as of the
    server's system date - e.g. on 2026-09-01, 2026-08 is closed (August is
    entirely in the past) but 2026-09 is not (today IS September, still
    accumulating sales). Only closed months are safe to cache: an open
    month's sales can still change between now and month-end, so caching it
    would silently freeze it at a partial, stale total. `today` is only for
    tests - real callers always use the actual system date."""
    today = today or datetime.date.today()
    y, m = (int(p) for p in ym.split("-"))
    first_of_next = datetime.date(y + (m == 12), (m % 12) + 1, 1)
    return today >= first_of_next


def _calendar_fingerprint(day_map):
    """Hashes the day-map actually used for a reindex - not a calendar id -
    so editing an existing locked calendar's mappings self-invalidates every
    cache entry that calendar produced, instead of a stale cache silently
    surviving an in-place edit. sort_keys makes this stable regardless of
    dict/list ordering."""
    blob = json.dumps(day_map, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _reindex_fields_key(extra_dims, metric_col):
    """Folds the extra output fields + metric selection into the cache key,
    alongside _calendar_fingerprint - a cached month is reused only when
    calendar, fields, AND metric all match the current request exactly."""
    return "|".join(sorted(extra_dims or [])) + "::" + (metric_col or "")


def _load_month_cache(source, ref_month, calendar_fp, fields_key):
    from db.base import SessionLocal
    from db.models.calendar import ReindexMonthCache

    session = SessionLocal()
    try:
        row = session.get(ReindexMonthCache, (source, ref_month, calendar_fp, fields_key))
        return json.loads(row.result_blob) if row is not None else None
    finally:
        session.close()


def _save_month_cache(source, ref_month, calendar_fp, fields_key, result):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from db.base import SessionLocal
    from db.models.calendar import ReindexMonthCache

    # BYTEA, not JSONB - a day-wise month broken out by several extra fields
    # can serialize past Postgres's hard ~256MB per-JSONB-value limit (hit
    # live on a real 2026-04 run); BYTEA has no such ceiling. See the
    # result_blob docstring on ReindexMonthCache.
    blob = json.dumps(result).encode("utf-8")
    session = SessionLocal()
    try:
        stmt = pg_insert(ReindexMonthCache).values(
            source_type=source, ref_month=ref_month, calendar_fingerprint=calendar_fp, fields_key=fields_key,
            result_blob=blob, computed_at=datetime.datetime.now(datetime.timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_type", "ref_month", "calendar_fingerprint", "fields_key"],
            set_={"result_blob": stmt.excluded.result_blob, "computed_at": stmt.excluded.computed_at},
        )
        session.execute(stmt)
        session.commit()
    finally:
        session.close()


def _cached_months_status(source, months, calendar_fp, fields_key):
    """{ref_month: computed_at_iso} for whichever of `months` are already
    cached under this exact (source, calendar, fields) combination - used by
    both run_reindex (to decide what it can skip) and the cache-status
    endpoint (so the UI can show it before a run even starts)."""
    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.calendar import ReindexMonthCache

    session = SessionLocal()
    try:
        rows = session.execute(
            select(ReindexMonthCache.ref_month, ReindexMonthCache.computed_at).where(
                ReindexMonthCache.source_type == source,
                ReindexMonthCache.calendar_fingerprint == calendar_fp,
                ReindexMonthCache.fields_key == fields_key,
                ReindexMonthCache.ref_month.in_(months),
            )
        ).all()
        return {m: ts.isoformat() for m, ts in rows}
    finally:
        session.close()


def reindex_month_cache_status(source, months, day_map, extra_dims, metric_col):
    """Per-requested-month status for the Run Reindex UI, computed BEFORE any
    actual run: 'open' (current/future month - always recomputed, never
    cached), 'cached' (closed and already reindexed under these exact
    calendar/fields/metric settings - the next run reuses it for free), or
    'pending' (closed but never cached under this combination - the next run
    will do real work for it, same as before this feature existed)."""
    calendar_fp = _calendar_fingerprint(day_map)
    fields_key = _reindex_fields_key(extra_dims, metric_col)
    closed = [m for m in months if _is_month_closed(m)]
    cached = _cached_months_status(source, closed, calendar_fp, fields_key) if closed else {}
    out = []
    for m in months:
        if m not in closed:
            out.append({"month": m, "status": "open"})
        elif m in cached:
            out.append({"month": m, "status": "cached", "computedAt": cached[m]})
        else:
            out.append({"month": m, "status": "pending"})
    return {"ok": True, "months": out}


def _merge_reindex_results(results):
    """Concatenates N per-reference-month reindex results (each computed with
    months=[that one month], so its rows/actualRows belong entirely to that
    month - see run_reindex) back into one combined result matching the same
    shape a single multi-month reindex_daywise/reindex_monthwise call would
    have returned. Safe to just concatenate rather than re-aggregate: a
    locked calendar's day-map is a per-cluster bijection ref-date -> fut-date,
    so distinct reference months can never produce overlapping output
    columns to sum together."""
    if len(results) == 1:
        return results[0]
    first = results[0]
    merged = {
        "ok": True, "source": first["source"], "keyFields": first["keyFields"],
        "grain": first["grain"], "metric": first["metric"],
        "rows": [], "actualRows": [], "columns": [], "actualColumns": [],
        "refDateByColumn": {}, "rowsRead": 0, "rowsMapped": 0,
        "unmappedStores": set(), "unmappedDateCount": 0, "unmappedDateSample": [],
        "unmappedClusters": set(), "unmappedClusterStores": set(),
        "usedFrozenSync": True,
    }
    for r in results:
        merged["rows"].extend(r.get("rows", []))
        merged["actualRows"].extend(r.get("actualRows", []))
        merged["columns"].extend(r.get("columns", []))
        merged["actualColumns"].extend(r.get("actualColumns", []))
        merged["refDateByColumn"].update(r.get("refDateByColumn", {}))
        merged["rowsRead"] += r.get("rowsRead", 0)
        merged["rowsMapped"] += r.get("rowsMapped", 0)
        merged["unmappedStores"].update(r.get("unmappedStores", []))
        merged["unmappedDateCount"] += r.get("unmappedDateCount", 0)
        merged["unmappedDateSample"].extend(r.get("unmappedDateSample", []))
        merged["unmappedClusters"].update(r.get("unmappedClusters", []))
        merged["unmappedClusterStores"].update(r.get("unmappedClusterStores", []))
        merged["usedFrozenSync"] = merged["usedFrozenSync"] and r.get("usedFrozenSync", False)
    merged["columns"] = sorted(set(merged["columns"]))
    merged["actualColumns"] = sorted(set(merged["actualColumns"]))
    merged["unmappedStores"] = sorted(merged["unmappedStores"])
    merged["unmappedDateSample"] = merged["unmappedDateSample"][:20]
    merged["unmappedClusters"] = sorted(merged["unmappedClusters"])
    merged["unmappedClusterStores"] = sorted(merged["unmappedClusterStores"])
    return merged


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
        fn = reindex_daywise if source == "dw" else reindex_monthwise
        # Closed-month caching: a month that's fully in the past can never
        # produce different sales again, so once it's been reindexed under
        # this exact (calendar, extra fields, metric) combination there is no
        # reason to ever re-read and re-aggregate its raw sales on a later
        # run - only the open/current month (which can still change) needs
        # fresh work every time. This is the main lever for "every login
        # doesn't have to re-run the same months" - see ReindexMonthCache.
        calendar_fp = _calendar_fingerprint(day_map)
        fields_key = _reindex_fields_key(extra_dims, metric_col)
        cached_status = _cached_months_status(
            source, [m for m in months if _is_month_closed(m)], calendar_fp, fields_key)

        results = []
        computed_months = []
        for m in months:
            if m in cached_status:
                results.append(_load_month_cache(source, m, calendar_fp, fields_key))
                continue
            computed_months.append(m)

        # Pre-warm the raw-data cache with EVERY uncached month in one pass,
        # instead of letting the per-month loop below each trigger its own
        # separate file read - opening a 1.5GB+ parquet file and evaluating
        # its row-group stats has real fixed overhead per call, so 5 separate
        # single-month reads cost noticeably more than 1 read covering all 5
        # months plus 5 cheap in-memory filters (see _get_raw's subset-reuse
        # above). The per-month loop is still what makes each month's own
        # result self-contained and safe to cache individually - this only
        # removes the redundant I/O behind it, not the per-month structure.
        if len(computed_months) > 1:
            raw_fetch_fn = _fetch_raw_daywise if source == "dw" else _fetch_raw_monthwise
            _get_raw(source, computed_months, sync_id, raw_fetch_fn, progress=progress,
                     extra_dims=extra_dims, metric_col=metric_col)

        for m in computed_months:
            # One month at a time - each call's whole result belongs to
            # exactly this one reference month, which is what makes it safe
            # to cache directly and merge back later without re-splitting.
            # Thanks to the pre-warm above, this no longer re-reads the
            # source per month - _get_raw serves each one from the already-
            # fetched combined frame.
            r = fn(months=[m], store_cluster=store_cluster, day_map=day_map, sync_id=sync_id,
                   progress=progress, extra_dims=extra_dims, metric_col=metric_col)
            if not r.get("ok"):
                return r
            results.append(r)
            # rowsRead == 0 means nothing was actually read for this month -
            # almost always the sales data source being temporarily
            # unreachable (parquet directory unmounted/offline), not a real
            # "this month genuinely has zero sales" fact. ok=True either way
            # (an unreachable source degrades gracefully to an empty
            # dataframe rather than raising - see _fetch_raw_daywise), so
            # caching on ok alone was caching that outage as if it were
            # permanent: every later run replayed the same empty result
            # forever, even once the source came back. Only a month that
            # actually read real rows is safe to treat as "done for good".
            if _is_month_closed(m) and r.get("rowsRead", 0) > 0:
                _save_month_cache(source, m, calendar_fp, fields_key, r)

        result = _merge_reindex_results(results)
        result["cachedMonths"] = sorted(cached_status.keys())
        result["computedMonths"] = sorted(computed_months)
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

# A reindex job is almost always "1 of 1 files" the whole way through (see the
# comment in poll_reindex_job) - there is no in-run completion signal to
# extrapolate an ETA from the way poll_link_scan_job does. The only other
# signal available is how long PAST runs of this source took relative to how
# many months they covered, so a small rolling history of completed runs
# (successful ones only - a run that errored out partway isn't a real duration
# sample) is kept here and used to project "about how long this one will take"
# from its own month count.
_REINDEX_TIMING_PATH = os.path.join(DB_DIR, "reindex_timing_stats.json")
_REINDEX_TIMING_MAX_RECORDS = 20  # per source


def _load_reindex_timing():
    if not os.path.exists(_REINDEX_TIMING_PATH):
        return {}
    try:
        with open(_REINDEX_TIMING_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


_REINDEX_TIMING_MAX_SECONDS_PER_MONTH = 3600  # 1hr/month - real runs are minutes/month; a sample above this is corrupt, not slow


def _record_reindex_timing(source, months_count, elapsed_seconds):
    if not source or months_count <= 0:
        return
    # Belt-and-braces against a bad elapsed_seconds slipping in from some
    # future code path the same way a recovered job's approximated started_at
    # once did (see _recover_reindex_job's "recovered" comment) - one such
    # sample is enough to poison the average for every later ETA on this
    # source, so a single implausible outlier is worth discarding outright
    # rather than letting it dilute in with real samples.
    if elapsed_seconds / months_count > _REINDEX_TIMING_MAX_SECONDS_PER_MONTH:
        return
    stats = _load_reindex_timing()
    records = stats.setdefault(source, [])
    records.append({"months": months_count, "seconds": elapsed_seconds})
    del records[:-_REINDEX_TIMING_MAX_RECORDS]
    tmp_path = _REINDEX_TIMING_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(stats, f)
    os.replace(tmp_path, _REINDEX_TIMING_PATH)


def _estimate_reindex_eta(source, months_count, elapsed_seconds):
    """Seconds-per-month rate averaged across every recorded past run of this
    source, scaled to this run's own month count, minus time already spent.
    None (shown as "estimating…") until at least one past run of this source
    has completed - there's nothing to average yet on a cold start."""
    if not source or months_count <= 0:
        return None
    records = _load_reindex_timing().get(source) or []
    total_months = sum(r["months"] for r in records)
    if total_months <= 0:
        return None
    seconds_per_month = sum(r["seconds"] for r in records) / total_months
    return max(0, round(seconds_per_month * months_count - elapsed_seconds))


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

    _REINDEX_JOBS[job_id] = {
        "progress_path": progress_path, "result_path": result_path, "log_path": log_path,
        "started_at": time.time(), "source": payload.get("source"),
        "monthsCount": len(payload.get("months") or []), "timingRecorded": False,
    }
    return job_id


def _recover_reindex_job(job_id):
    """Reconstruct a job record from its on-disk directory when it's missing
    from the in-memory _REINDEX_JOBS map - which happens on every backend
    restart, since that dict (unlike progress/result files) isn't persisted.
    Before this, a restart while a job was running or freshly done permanently
    orphaned it: poll_reindex_job returned "Unknown or expired job" even
    though the result was sitting right there in result.json, so a planner
    waiting on a 15-20 minute day-wise run would see the progress bar vanish
    with no download and no way to recover it short of re-running the whole
    thing. started_at falls back to the payload file's mtime (its write is the
    very first thing start_reindex_job does) - an approximation, but only used
    for the elapsed/ETA display on a job that's still running; a job that's
    already done doesn't need it at all."""
    job_dir = os.path.join(_REINDEX_JOB_DIR, job_id)
    if not os.path.isdir(job_dir):
        return None
    payload_path = os.path.join(job_dir, "payload.json")
    source, months_count, started_at = None, 0, None
    if os.path.exists(payload_path):
        try:
            with open(payload_path, encoding="utf-8") as f:
                payload = json.load(f)
            source = payload.get("source")
            months_count = len(payload.get("months") or [])
            started_at = os.path.getmtime(payload_path)
        except (json.JSONDecodeError, OSError):
            pass
    job = {
        "progress_path": os.path.join(job_dir, "progress.json"),
        "result_path": os.path.join(job_dir, "result.json"),
        "log_path": os.path.join(job_dir, "worker.log"),
        "started_at": started_at if started_at is not None else time.time(),
        "source": source, "monthsCount": months_count, "timingRecorded": False,
        # A recovered job's started_at is an approximation (payload.json's
        # mtime), not the real start time the in-memory job would have had -
        # for a job that sat unpolled for a long time (e.g. across a restart,
        # or a stale localStorage pointer picked up much later), "elapsed"
        # computed from it can be wildly larger than the job's real runtime.
        # Reproduced live: one such recovery recorded 55960 "seconds" for an
        # 8-month run, dragging the seconds-per-month average enough to turn
        # a real ~2-minute single-month ETA into a false 17-minute one. Never
        # trust a recovered job's timing as a sample - see
        # get_reindex_result_stream_path.
        "recovered": True,
    }
    _REINDEX_JOBS[job_id] = job
    return job


def get_reindex_result_stream_path(job_id):
    """Path to a completed job's result.json, for the router to stream
    straight to the client (FileResponse) without this process ever calling
    json.load() on it - see the comment in reindex_worker.py on why that
    matters: a day-wise result over a full year can be a huge file, and
    parsing (or re-serializing) it in pure Python holds the GIL for the
    whole operation, freezing every other request on the server for however
    long that takes - reproduced live: polling one finished 8-month result
    made even GET /docs time out for the whole server. Returns None while
    still running or if the job is unknown, in which case the caller should
    fall back to poll_reindex_job for the running/error-status response.

    Also records this run's timing as a side effect (once per job, via
    result_meta.json - a tiny companion file, safe to actually parse) so
    _estimate_reindex_eta has data for the next run of this source. Skips the
    sample - rather than recording a misleading one - when: the result is
    older than result_meta.json (nothing to check ok/rowsRead against); the
    run read 0 rows (source was unreachable, not a real timing of real work);
    or the job's started_at came from _recover_reindex_job's approximation
    (see its "recovered" comment - not trustworthy as elapsed time)."""
    job = _REINDEX_JOBS.get(job_id) or _recover_reindex_job(job_id)
    if job is None or not os.path.exists(job["result_path"]):
        return None
    if not job.get("timingRecorded") and not job.get("recovered"):
        meta_path = os.path.join(os.path.dirname(job["result_path"]), "result_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("ok") and meta.get("rowsRead", 0) > 0:
                    job["timingRecorded"] = True
                    _record_reindex_timing(job.get("source"), job.get("monthsCount", 0), round(time.time() - job["started_at"]))
            except (json.JSONDecodeError, OSError):
                pass
    return job["result_path"]


def get_reindex_csv_path(job_id, view):
    """CSV (not JSON) download for a job whose result is too large for the
    browser tab to safely parse and hold - see the "too large to preview"
    fallback in CalendarisedSalesTab. Every other download in this app is a
    CSV; this exists so a huge result is never the one exception.

    Converts result.json to CSV via reindex_csv_worker.py, in its own
    process for the same reason get_reindex_result_stream_path never parses
    result.json in this process (json.load() on a huge file holds the GIL
    long enough to freeze the whole server for every user). The conversion
    itself is comparatively fast (no raw sales re-read, just a reshape of
    already-computed data) so this runs synchronously and waits for it -
    Starlette runs a sync route in its own threadpool thread, so waiting on
    the subprocess here blocks only that one request, not the event loop or
    any other user's request.

    Returns (csv_path, error) - exactly one is None. csv_path is cached
    per (job, view) so a repeat click of the same download button reuses it
    instead of re-converting."""
    import subprocess

    job = _REINDEX_JOBS.get(job_id) or _recover_reindex_job(job_id)
    if job is None:
        return None, "Unknown or expired job"
    if not os.path.exists(job["result_path"]):
        return None, "Job is not finished yet"

    job_dir = os.path.dirname(job["result_path"])
    payload_path = os.path.join(job_dir, "payload.json")
    csv_path = os.path.join(job_dir, f"{view}.csv")
    done_path = os.path.join(job_dir, f"{view}_csv_done.json")

    if not os.path.exists(done_path):
        worker_dir = os.path.dirname(os.path.abspath(__file__))
        worker_script = os.path.join(worker_dir, "reindex_csv_worker.py")
        subprocess.run(
            [sys.executable, worker_script, job["result_path"], payload_path, view, csv_path, done_path],
            cwd=worker_dir,
        )

    if not os.path.exists(done_path):
        return None, "CSV conversion did not complete"
    with open(done_path, encoding="utf-8") as f:
        done = json.load(f)
    if not done.get("ok"):
        return None, done.get("error") or "CSV conversion failed"
    return csv_path, None


def poll_reindex_job(job_id):
    """Handles the 'unknown job' and 'still running' responses only - a
    completed job is served by get_reindex_result_stream_path instead (see
    its docstring for why). The router checks that first and only falls back
    here when it returns None."""
    job = _REINDEX_JOBS.get(job_id) or _recover_reindex_job(job_id)
    if job is None:
        return {"ok": False, "status": "error", "error": "Unknown or expired job"}

    if os.path.exists(job["result_path"]):
        return {"ok": True, "status": "running", "progressPct": 100}  # result file just appeared between the two checks; next poll streams it

    progress = {"done": 0, "total": 0}
    if os.path.exists(job["progress_path"]):
        try:
            with open(job["progress_path"], encoding="utf-8") as f:
                progress = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass  # progress file mid-write; next poll retries, not fatal
    pct = round(100 * progress["done"] / progress["total"]) if progress["total"] else 0
    # No per-file ETA here (unlike poll_link_scan_job): a reindex job is
    # typically "1 of 1 files" the whole way through - the real work is the
    # post-read pandas aggregation, which has no sub-file progress signal to
    # extrapolate from. The ETA below instead comes from _estimate_reindex_eta
    # (seconds-per-month rate averaged from past completed runs of this
    # source) - None until at least one past run exists to average from.
    elapsed = round(time.time() - job["started_at"])
    eta = _estimate_reindex_eta(job.get("source"), job.get("monthsCount", 0), elapsed)
    return {
        "ok": True, "status": "running", "progressPct": pct,
        "filesDone": progress["done"], "filesTotal": progress["total"],
        "elapsedSeconds": elapsed, "etaSeconds": eta,
    }
