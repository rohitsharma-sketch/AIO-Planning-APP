"""
Calendar Engine local server — port 7822
Serves static files + JSON state stores persisted under Local DB/:
  GET/POST /api/changelog              -> festival_changelog.json
  GET/POST /api/state/<key>            -> <key>.json  (whitelisted keys below)
  POST     /api/import/store_cluster   -> parses an uploaded Store/Cluster template
                                          (.xlsx via openpyxl, or .csv) and returns rows
  GET      /api/salesdata/link          -> month-wise source: scans rs_sales_19-_till_date
                                           (BILLMONTH + STORE_NAME only) for available months +
                                           store coverage vs the locked store-cluster map.
  GET      /api/salesdata/link_daywise  -> day-wise source: scans the 4 billwise_fy* files
                                           (BILLDATE + STORE_NAME only) for available months,
                                           store coverage, and real date gaps between files.
  Both cached in memory; ?refresh=1 forces a rescan. No sales figures are read here.
  POST     /api/salesdata/reindex       -> the actual reindex: for the given source
                                          ('mw'|'dw') and months, reads the real sales
                                          column (SL_V or NETAMT) for those months, maps
                                          each row's store -> cluster -> LY/TY date via the
                                          caller-supplied locked calendar dayMap, and returns
                                          the reindexed totals (long-form; client pivots wide).
On startup, Local DB/Default Template.xlsx is imported ONCE into
store_cluster_map.json if that file does not exist yet.
"""
import csv, io, json, os, glob, time, datetime, calendar as _calendar
from collections import Counter
from urllib.parse import urlsplit, parse_qs
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

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

    mapped_stores = set()
    try:
        with open(STORE_MAP_PATH, "r", encoding="utf-8") as f:
            mapped_stores = {s["store"] for s in json.load(f).get("stores", [])}
    except Exception:
        pass

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
        result = dict(data)
        result["cached"] = False
        return result
    except Exception as e:
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

    mapped_stores = set()
    try:
        with open(STORE_MAP_PATH, "r", encoding="utf-8") as f:
            mapped_stores = {s["store"] for s in json.load(f).get("stores", [])}
    except Exception:
        pass

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
        result = dict(data)
        result["cached"] = False
        return result
    except Exception as e:
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


def _fetch_raw_daywise(months):
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor

    months_set = set(months)
    lo, hi = _month_bounds(months)
    files = []
    for d in DAYWISE_DIRS:
        files.extend(sorted(glob.glob(os.path.join(d, "*.parquet"))))

    def _read(fp):
        return _read_file_filtered(fp, ["BILLDATE", "STORE_NAME", "NETAMT"], "BILLDATE", lo, hi)

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
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["BILLDATE", "STORE_NAME", "NETAMT"])
    return df, total_read


def _fetch_raw_monthwise(months):
    months_set = set(months)
    lo, hi = _month_bounds(months)
    files = sorted(glob.glob(os.path.join(PARQUET_DIR, "*.parquet")))

    frames = []
    total_read = 0
    for fp in files:
        df = _read_file_filtered(fp, ["BILLMONTH", "DIVISION", "STORE_NAME", "SL_V"], "BILLMONTH", lo, hi)
        if df is None or df.empty:
            continue
        total_read += len(df)
        df["ym"] = df["BILLMONTH"].dt.strftime("%Y-%m")
        df = df[df["ym"].isin(months_set)]
        if not df.empty:
            frames.append(df)
    import pandas as pd
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["BILLMONTH", "DIVISION", "STORE_NAME", "SL_V"])
    return df, total_read


def _get_raw(source, months, sync_id, fetch_fn):
    """Returns (df_copy, rows_read, used_cache). df_copy is always a fresh .copy()
    of the frozen/cached data - callers mutate it freely (adding cluster/date
    lookup columns) without ever corrupting the cache for the next run."""
    import time as _time
    slot = _RAW_CACHE.get(source)
    if sync_id and slot and slot.get("syncId") == sync_id:
        return slot["df"].copy(), slot["rowsRead"], True
    df, rows_read = fetch_fn(months)
    if sync_id:  # only freeze when the client sent a real sync marker to key on
        _RAW_CACHE[source] = {"syncId": sync_id, "df": df, "rowsRead": rows_read, "fetchedAt": _time.time()}
    return df.copy(), rows_read, False


def reindex_daywise(months, store_cluster, day_map, sync_id=None):
    cluster_ref_fut = {c: {p[0]: p[1] for p in pairs} for c, pairs in day_map.items()}

    df, total_read, used_cache = _get_raw("dw", months, sync_id, _fetch_raw_daywise)
    df["cluster"] = df["STORE_NAME"].map(store_cluster)
    unmapped_stores = sorted(df.loc[df["cluster"].isna(), "STORE_NAME"].unique().tolist())
    df = df.dropna(subset=["cluster"])

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
        "usedFrozenSync": used_cache,
    }


def reindex_monthwise(months, store_cluster, day_map, sync_id=None):
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

    df, total_read, used_cache = _get_raw("mw", months, sync_id, _fetch_raw_monthwise)
    df["cluster"] = df["STORE_NAME"].map(store_cluster)
    unmapped_stores = sorted(df.loc[df["cluster"].isna(), "STORE_NAME"].unique().tolist())
    df = df.dropna(subset=["cluster"])

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
        "usedFrozenSync": used_cache,
    }


def run_reindex(payload):
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
            return reindex_daywise(months, store_cluster, day_map, sync_id)
        return reindex_monthwise(months, store_cluster, day_map, sync_id)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ─── Store / Cluster template parsing ────────────────────────────────────────
def _pick_columns(header):
    """Return (store_idx, cluster_idx) from a header row; falls back to first two columns."""
    norm = [str(h or "").strip().lower() for h in header]
    s_idx = next((i for i, h in enumerate(norm) if "store" in h), 0)
    c_idx = next((i for i, h in enumerate(norm) if "cluster" in h and i != s_idx), 1 if s_idx != 1 else 0)
    return s_idx, c_idx


def _rows_from_table(table):
    """table: list of row lists (first row = header). Returns list of {store, cluster}."""
    if not table:
        raise ValueError("Template is empty")
    header = table[0]
    s_idx, c_idx = _pick_columns(header)
    out, seen = [], set()
    for r in table[1:]:
        if r is None or s_idx >= len(r):
            continue
        store = str(r[s_idx] if r[s_idx] is not None else "").strip()
        cluster = str(r[c_idx] if c_idx < len(r) and r[c_idx] is not None else "").strip()
        if not store:
            continue
        key = store.upper()
        if key in seen:
            continue  # keep first occurrence of a duplicated store code
        seen.add(key)
        out.append({"store": store, "cluster": cluster})
    if not out:
        raise ValueError("No store rows found (expected columns: Store Name, Calendar Cluster)")
    return out


def parse_template(data, filename):
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        import openpyxl  # available on this machine; error surfaces to the client if not
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        return _rows_from_table(table)
    # CSV / TSV / TXT
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except Exception:
        dialect = csv.excel
    table = [row for row in csv.reader(io.StringIO(text), dialect)]
    return _rows_from_table(table)


def seed_store_cluster():
    """One-time import of Default Template.xlsx -> store_cluster_map.json (+ initial log)."""
    if os.path.exists(STORE_MAP_PATH) or not os.path.exists(DEFAULT_TEMPLATE):
        return
    try:
        with open(DEFAULT_TEMPLATE, "rb") as f:
            rows = parse_template(f.read(), DEFAULT_TEMPLATE)
    except Exception as e:
        print("Default template seed failed:", e)
        return
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state = {
        "locked": True,
        "lockedAt": now,
        "source": os.path.basename(DEFAULT_TEMPLATE),
        "aliases": {},
        "stores": rows,
    }
    log = [{
        "at": now,
        "source": os.path.basename(DEFAULT_TEMPLATE),
        "summary": "Initial import of default template",
        "added": len(rows), "removed": 0, "reassigned": 0,
        "details": [{"type": "added", "store": r["store"], "to": r["cluster"]} for r in rows],
    }]
    _write_json_file(STORE_MAP_PATH, state)
    _write_json_file(STORE_LOG_PATH, log)
    print(f"Seeded store-cluster map from Default Template.xlsx ({len(rows)} stores)")


def _write_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress request logging

    def _state_key(self):
        if self.path.startswith("/api/state/"):
            key = self.path[len("/api/state/"):]
            if key in STATE_KEYS:
                return key
        return None

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/api/changelog":
            self._send_json(self._read_json(DB_PATH))
        elif parsed.path == "/api/salesdata/link":
            qs = parse_qs(parsed.query)
            force = qs.get("refresh", ["0"])[0] == "1"
            self._send_json(get_salesdata_link(force_refresh=force))
        elif parsed.path == "/api/salesdata/link_daywise":
            qs = parse_qs(parsed.query)
            force = qs.get("refresh", ["0"])[0] == "1"
            self._send_json(get_salesdata_link_daywise(force_refresh=force))
        elif self._state_key():
            self._send_json(self._read_json(os.path.join(DB_DIR, self._state_key() + ".json")))
        else:
            super().do_GET()

    def do_POST(self):
        key = self._state_key()
        if self.path == "/api/changelog":
            self._handle_write(DB_PATH)
        elif key:
            self._handle_write(os.path.join(DB_DIR, key + ".json"))
        elif self.path == "/api/import/store_cluster":
            self._handle_import()
        elif self.path == "/api/salesdata/reindex":
            self._handle_reindex()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_import(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        filename = self.headers.get("X-Filename", "upload.csv")
        try:
            rows = parse_template(data, filename)
            self._send_json({"ok": True, "filename": filename, "rows": rows})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, status=400)

    def _handle_reindex(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
            self._send_json(run_reindex(payload))
        except Exception as e:
            self._send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=400)

    def _handle_write(self, path):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            _write_json_file(path, data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(str(e).encode())

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}


if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__))
    seed_store_cluster()
    server = ThreadingHTTPServer(("", 7822), Handler)
    print(f"Calendar Engine server running at http://localhost:7822")
    server.serve_forever()
