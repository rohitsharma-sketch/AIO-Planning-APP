"""
CityKart OTB Sync Server
Reads the latest sales parquet + sell-through file from the data lake
and serves them to the browser app on http://localhost:5050

Start: python sync_server.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import os
import glob
import shutil
import tempfile
from datetime import datetime

app = Flask(__name__)
CORS(app)

@app.after_request
def strip_cache_headers(resp):
    """Remove ETag/Last-Modified AFTER Werkzeug finalize_request() adds them, so the
    browser can never serve a 304 and always fetches the latest HTML."""
    resp.headers.remove("ETag")
    resp.headers.remove("Last-Modified")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# ── CONFIGURE PATHS HERE ─────────────────────────────────────────────────────
SALES_DIR = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw\rs_sales_19-_till_date"
SELLTHRU_DIR = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw\rs_weekly_sell_ths_apps"
LOCAL_CACHE = os.path.join(tempfile.gettempdir(), "citykart_otb_cache")

# ── SALES PIN ────────────────────────────────────────────────────────────────
# Set to an absolute path to freeze the parquet used by ALL jobs.
# Server will ignore any newer files on the network until this is set to None.
# Set to None to resume auto-pick (latest file in SALES_DIR).
PINNED_SALES_FILE = os.path.join(LOCAL_CACHE, "rs_sales_latest.parquet")  # pinned: Aug-17 2026

# ── LFL STORE TAG FILTER (26V27) ─────────────────────────────────────────────
# TAG_TYPE values that identify LFL stores for the FY27 plan base (FY26 LY).
# 032=legacy network, 080/095/125=other store clusters, FY26=stores opened in FY26.
# Combined these give 148 stores. SET-1/SET-2/6-NSO are excluded from LFL.
LFL_TAGS_26V27 = {"032 - Stores", "080 - Stores", "095 - Stores", "125 - Stores", "FY26"}

# ── WEEKLY ST% → MONTH MAP (MAMJ block, retail week numbering) ───────────────
# WK9-13=Mar(mi=11)  WK14-17=Apr(mi=0)  WK18-22=May(mi=1)  WK23-26=Jun(mi=2)
WEEK_TO_MI: dict = {
    **{w: 11 for w in range(9,  14)},
    **{w:  0 for w in range(14, 18)},
    **{w:  1 for w in range(18, 23)},
    **{w:  2 for w in range(23, 27)},
}
# String keys as stored in the parquet WEEK column: 'WK-09', 'WK-10', …
WEEK_STR_TO_MI: dict = {f"WK-{w:02d}": mi for w, mi in WEEK_TO_MI.items()}
VALID_WK_STRS:  set  = set(WEEK_STR_TO_MI)

# ── PINNED LY ACTUALS ─────────────────────────────────────────────────────────
# Division-level AOP month actuals (Mar/Apr/May/Jun FY26, Rs Cr) sourced from
# the Aug-10 parquet (32 LFL stores). Server returns these instead of reading
# the current parquet, so the KPI LY total stays at 388.75 Cr.
# Keys: division string → {mi_string → Cr value}. Set to None to use live parquet.
PINNED_LY_ACTUALS = {
    "kids":   {"11": 38.0918, "0": 30.2102, "1": 29.815,  "2": 28.136},
    "ladies": {"11": 34.02,   "0": 31.0028, "1": 29.578,  "2": 28.369},
    "mens":   {"11": 42.3026, "0": 34.8313, "1": 32.2924, "2": 30.0966},
}
# ─────────────────────────────────────────────────────────────────────────────

# Division aliases for auto-mapping parquet DIV column → app div ID
DIV_MAP = {
    "mens":   ["mens", "men", "gents", "male"],
    "ladies": ["ladies", "lady", "womens", "women", "female"],
    "kids":   ["kids", "kid", "children", "boys", "girls", "junior"],
}

# Indian FY: mi=0=Apr … mi=11=Mar
# LY for FY27 plan = FY26 = Apr 2025–Mar 2026
# AOP months and their calendar dates in FY26:
AOP_MONTHS = [11, 0, 1, 2]  # Mar, Apr, May, Jun
# mi → calendar month number (0=Apr→4 … 11=Mar→3)
MI_TO_CAL_MONTH = {0:4,1:5,2:6,3:7,4:8,5:9,6:10,7:11,8:12,9:1,10:2,11:3}
# Calendar months in the AOP block (MAMJ → {3,4,5,6})
AOP_CAL_MONTHS = frozenset(MI_TO_CAL_MONTH[mi] for mi in AOP_MONTHS)
# Final (latest) calendar month — closing stock denominator (June for MAMJ)
AOP_FINAL_CAL_MONTH = max(AOP_CAL_MONTHS)
AOP_FY26_DATES = {
    11: (2026, 3),   # Mar 2026
    0:  (2025, 4),   # Apr 2025
    1:  (2025, 5),   # May 2025
    2:  (2025, 6),   # Jun 2025
}
DATE_TO_MI = {v: k for k, v in AOP_FY26_DATES.items()}

# Full-year FY calendars: mi=0=Apr … mi=11=Mar
_CAL_MONTHS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]

def _fy_date_to_mi(fy_start_year: int) -> dict:
    """Return {(year, month): mi} for a full Indian FY starting April of fy_start_year."""
    result = {}
    for mi, cal_mo in enumerate(_CAL_MONTHS):
        yr = fy_start_year if cal_mo >= 4 else fy_start_year + 1
        result[(yr, cal_mo)] = mi
    return result

FY19_DATE_TO_MI = _fy_date_to_mi(2019)   # Apr 2019 – Mar 2020
FY25_DATE_TO_MI = _fy_date_to_mi(2024)   # Apr 2024 – Mar 2025
FY26_DATE_TO_MI = _fy_date_to_mi(2025)   # Apr 2025 – Mar 2026

# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(LOCAL_CACHE, exist_ok=True)
_last_sync: dict = {}
_hist_job:  dict = {"status": "idle", "data": None, "error": None}
_sales_job: dict = {"status": "idle", "progress": 0, "data": None, "error": None}
_st_job:    dict = {"status": "idle", "data": None, "error": None}


def _data_version() -> str:
    """Cheap fingerprint: mtime of the sales + ST parquet files in milliseconds."""
    parts = []
    # Sales: use pinned file's mtime when pin is active (keeps version stable)
    try:
        sales_f = (PINNED_SALES_FILE if (PINNED_SALES_FILE and os.path.exists(PINNED_SALES_FILE))
                   else get_latest_file(SALES_DIR, ("*.parquet",)))
        if sales_f:
            parts.append(str(int(os.path.getmtime(sales_f) * 1000)))
    except Exception:
        pass
    # ST: always latest on network
    try:
        import glob as _glob
        files = _glob.glob(os.path.join(SELLTHRU_DIR, "*.parquet"))
        if files:
            latest = max(files, key=os.path.getmtime)
            parts.append(str(int(os.path.getmtime(latest) * 1000)))
    except Exception:
        pass
    return "-".join(parts) if parts else "unknown"


def get_latest_file(directory: str, patterns=("*.parquet",)) -> str | None:
    files = []
    for pat in patterns:
        files.extend(glob.glob(os.path.join(directory, pat)))
    return max(files, key=os.path.getmtime) if files else None


def _get_sales_src() -> str | None:
    """Return the sales parquet to use: pinned file if active, else latest from network."""
    if PINNED_SALES_FILE and os.path.exists(PINNED_SALES_FILE):
        return PINNED_SALES_FILE
    return get_latest_file(SALES_DIR, ("*.parquet",))


def normalize_div(name: str) -> str | None:
    nl = str(name).lower().strip()
    for did, aliases in DIV_MAP.items():
        if any(a in nl for a in aliases):
            return did
    return None


def detect_col(cols_lower: dict, keywords: list[str]) -> str | None:
    return next((cols_lower[k] for k in cols_lower if any(x in k for x in keywords)), None)


def normalize_dept_id(name: str) -> str:
    """Convert parquet DEPARTMENT name to DVDATA section id format.
    e.g. 'MU_FORMAL SHIRT F/S' → 'mu_formal_shirt_f_s'
         'KB_T-SHIRT H/S'      → 'kb_t_shirt_h_s'
    """
    import re
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower().strip()).strip('_')


def parse_date_col(series: "pd.Series") -> "pd.Series":
    """Parse dates that may be YYYYMM integers, date strings, or datetimes."""
    import numpy as np
    if pd.api.types.is_integer_dtype(series):
        # Treat integer values as YYYYMM (e.g. 202504 → 2025-04-01)
        return pd.to_datetime(series.astype(str), format="%Y%m", errors="coerce")
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    # Try YYYYMM string format first, then generic parse
    parsed = pd.to_datetime(series.astype(str).str.strip(), format="%Y%m", errors="coerce")
    fallback = pd.to_datetime(series, errors="coerce")
    return parsed.fillna(fallback)


@app.route("/")
def serve_app():
    """Serve the OTB app HTML — always reads fresh from disk, no caching."""
    import time
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "otb-plan-app.html")
    from flask import Response
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Append a unique nonce so the ETag (computed from body) is always different,
    # preventing any browser or proxy from serving a cached copy.
    content += f"\n<!-- served:{int(time.time() * 1000)} -->"
    return Response(content, mimetype="text/html; charset=utf-8")


@app.route("/demo")
def serve_demo():
    """Standalone demo — no server calls, all data baked in. Share this URL on the local network."""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "otb-plan-standalone.html")
    from flask import send_file
    return send_file(html_path, mimetype="text/html")


@app.route("/api/status")
def api_status():
    return jsonify({"ok": True, "last_sync": _last_sync, "server": "CityKart OTB Sync v1.0", "data_version": _data_version()})


@app.route("/api/config/aop-division-targets")
def aop_division_targets():
    """Proxy to AOP Forecaster (port 8000) for live MAMJ division targets.
    Returns the same JSON shape so BIS works whether accessed at 5050 or via
    the 7800 proxy."""
    import urllib.request as _ur
    from flask import Response
    try:
        with _ur.urlopen("http://127.0.0.1:8000/api/config/aop-division-targets", timeout=5) as r:
            return Response(r.read(), status=r.status, content_type="application/json")
    except Exception as e:
        return jsonify({"targets": None, "published_at": None,
                        "note": f"AOP Forecaster unreachable: {e}"})


def _run_sales_job(src: str):
    """Background worker: aggregate FY26 AOP-month actuals and store in _sales_job."""
    global _sales_job, _last_sync
    try:
        # When PINNED_LY_ACTUALS is set, skip parquet read entirely and return pinned values.
        if PINNED_LY_ACTUALS:
            ts = datetime.now().isoformat()
            _last_sync["sales"] = ts
            _sales_job = {
                "status": "done",
                "data": {"ok": True, "dept_actual_ly": PINNED_LY_ACTUALS,
                         "source_file": "PINNED (Aug-10 LFL actuals)",
                         "rows_processed": 0, "synced_at": ts,
                         "data_version": _data_version()},
                "error": None,
            }
            return

        # Use the local cached copy if it exists — same snapshot as history job.
        # If it doesn't exist yet, copy from network now so future jobs share it.
        local_src = os.path.join(LOCAL_CACHE, "rs_sales_latest.parquet")
        if os.path.exists(local_src):
            src = local_src
        else:
            try:
                shutil.copy2(src, local_src)
                src = local_src
            except Exception:
                pass  # fall back to network path
        _sales_job["progress"] = 10

        import pyarrow.parquet as pq
        schema = pq.read_schema(src)
        cols_lower = {c.lower(): c for c in schema.names}
        _sales_job["progress"] = 20

        date_col  = detect_col(cols_lower, ["bill_date", "tran_date", "billdate", "billmonth", "bill_month",
                                             "invoice_date", "sale_date", "trans_date", "date", "dt",
                                             "month", "yr_mo", "yearmonth"])
        div_col   = detect_col(cols_lower, ["division", "div_nm", "div", "divis"])
        amt_col   = detect_col(cols_lower, ["sl_v", "slv", "sl_val", "sale_val",
                                             "net_amount", "net_amt", "net_sale", "netsale", "netsales",
                                             "net_value", "bill_value", "bill_amt", "billing_amt",
                                             "sale_value", "sale_amt", "sales_value", "sales_amt",
                                             "amount", "revenue", "gross", "net_bill", "extaxamt", "ex_tax"])
        store_col = detect_col(cols_lower, ["store_name", "store", "store_nm", "outlet", "outlet_name"])
        tag_col   = detect_col(cols_lower, ["tag_type", "tag", "store_tag", "store_type"])

        if not all([date_col, div_col, amt_col]):
            _sales_job = {"status": "error", "data": None,
                          "error": f"Column detection failed: date={date_col} div={div_col} amt={amt_col}. "
                                   f"Columns: {schema.names[:40]}"}
            return

        read_cols = [date_col, div_col, amt_col] \
                    + ([store_col] if store_col else []) \
                    + ([tag_col]   if tag_col   else [])
        df = pd.read_parquet(src, columns=read_cols)
        _sales_job["progress"] = 70
        df[date_col] = parse_date_col(df[date_col])
        df = df.dropna(subset=[date_col])

        # Filter to 148 LFL stores (TAG_TYPE in LFL_TAGS_26V27)
        if tag_col and store_col and tag_col in df.columns:
            lfl_mask = df[tag_col].astype(str).str.strip().isin(LFL_TAGS_26V27)
            df = df[lfl_mask]

        target = set(AOP_FY26_DATES.values())
        mask = df[date_col].apply(lambda d: (d.year, d.month) in target)
        df_f = df[mask].copy()

        if df_f.empty:
            _sales_job = {"status": "error", "data": None,
                          "error": "No data for FY26 AOP months (Apr/May/Jun 2025 + Mar 2026)."}
            return

        df_f["_div"] = df_f[div_col].apply(normalize_div)
        df_f["_mi"]  = df_f[date_col].apply(lambda d: DATE_TO_MI.get((d.year, d.month)))
        df_f[amt_col] = pd.to_numeric(df_f[amt_col], errors="coerce").fillna(0)
        df_f = df_f.dropna(subset=["_div", "_mi"])

        _sales_job["progress"] = 90
        grouped = df_f.groupby(["_div", "_mi"])[amt_col].sum()
        result: dict = {}
        for (dv, mi), total in grouped.items():
            result.setdefault(str(dv), {})[str(int(mi))] = round(float(total) / 1e7, 4)

        ts = datetime.now().isoformat()
        _last_sync["sales"] = ts
        _sales_job = {
            "status": "done",
            "data": {"ok": True, "dept_actual_ly": result, "source_file": os.path.basename(src),
                     "rows_processed": int(mask.sum()), "synced_at": ts,
                     "data_version": _data_version()},
            "error": None,
        }
    except Exception as exc:
        _sales_job = {"status": "error", "data": None, "error": str(exc)}


@app.route("/api/sync/sales")
def api_sync_sales():
    """Start background sales sync; returns immediately. Poll /api/sync/sales/poll for result."""
    global _sales_job
    src = _get_sales_src()
    if not src:
        return jsonify({"ok": False, "error": "No parquet file found in SALES_DIR"}), 404
    if _sales_job["status"] == "running":
        return jsonify({"ok": True, "status": "running"})
    if _sales_job["status"] == "done":
        return jsonify({"ok": True, "status": "done"})
    _sales_job = {"status": "running", "progress": 0, "data": None, "error": None}
    import threading
    threading.Thread(target=_run_sales_job, args=(src,), daemon=True).start()
    return jsonify({"ok": True, "status": "running"})


@app.route("/api/sync/sales/poll")
def api_sync_sales_poll():
    job = _sales_job
    if job["status"] == "done":
        return jsonify({**job["data"], "status": "done", "progress": 100})
    if job["status"] == "error":
        return jsonify({"ok": False, "status": "error", "error": job["error"]})
    return jsonify({"ok": True, "status": job["status"], "progress": job.get("progress", 0)})


def _run_st_job(src: str):
    """Background worker: copy + compute ST% by section from weekly sell-through parquet."""
    global _st_job, _last_sync
    try:
        ext = os.path.splitext(src)[1].lower()
        local = os.path.join(LOCAL_CACHE, f"st_latest{ext}")
        shutil.copy2(src, local)

        try:
            # Read columns we need; DEPARTMENT is optional — include if present
            needed = ["SECTION", "DIVISION", "DEPARTMENT", "WEEK", "WK_START_DT",
                      "SL_Q", "CLS_STK_Q", "LOCATION", "SEASON", "STORE_STATUS"]
            if ext == ".csv":
                df = pd.read_csv(local, usecols=lambda c: c in needed)
            elif ext == ".parquet":
                import pyarrow.parquet as pq
                avail = pq.read_schema(local).names
                cols  = [c for c in needed if c in avail]
                df    = pd.read_parquet(local, columns=cols)
            else:
                df = pd.read_excel(local)
                df = df[[c for c in needed if c in df.columns]]
        except Exception as e:
            os.remove(local)
            _st_job = {"status": "error", "data": None, "error": f"File read failed: {e}"}
            return

        if "SECTION" not in df.columns or "SL_Q" not in df.columns or "CLS_STK_Q" not in df.columns:
            _st_job = {"status": "error", "data": None,
                       "error": f"Missing required columns. Available: {list(df.columns)}"}
            return

        has_dept_col = "DEPARTMENT" in df.columns

        # Filter to store-level data only (exclude DC/transit rows)
        if "LOCATION" in df.columns:
            df = df[df["LOCATION"].astype(str).str.upper() == "STORE"]

        if "WK_START_DT" in df.columns:
            df["WK_START_DT"] = pd.to_datetime(df["WK_START_DT"], errors="coerce")

        for col in ["SL_Q", "CLS_STK_Q"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df = df.dropna(subset=["SECTION"])

        # ST% = AOP-block sales ÷ (AOP-block sales + end-of-block closing stock)
        # Numerator  : SL_Q summed over all weeks in the AOP block's calendar months
        # Denominator: SL_Q + CLS_STK_Q from the last week of the final AOP month (June for MAMJ)
        has_wk = "WK_START_DT" in df.columns

        aop_mask = pd.Series(True, index=df.index)  # rows that count toward sales
        ref_wk   = None                              # week used for closing-stock snapshot
        last_wk  = None                              # used for response label

        if has_wk:
            df["_cal_month"] = df["WK_START_DT"].dt.month
            df["_cal_year"]  = df["WK_START_DT"].dt.year

            final_mo_rows = df[df["_cal_month"] == AOP_FINAL_CAL_MONTH]
            if not final_mo_rows.empty:
                ref_year = int(final_mo_rows["_cal_year"].max())
                # Sales: AOP block months only, in the reference year
                aop_mask = (df["_cal_month"].isin(AOP_CAL_MONTHS)) & (df["_cal_year"] == ref_year)
                # Stock: last week of the final AOP month (June) with positive closing stock
                stk_rows = df[(df["_cal_month"] == AOP_FINAL_CAL_MONTH) &
                              (df["_cal_year"] == ref_year) & (df["CLS_STK_Q"] > 0)]
                if stk_rows.empty:
                    stk_rows = df[(df["_cal_month"] == AOP_FINAL_CAL_MONTH) &
                                  (df["_cal_year"] == ref_year)]
                ref_wk = stk_rows["WK_START_DT"].max() if not stk_rows.empty else None
            else:
                # No data for final AOP month — fall back to global most-recent week
                stocked = df[df["CLS_STK_Q"] > 0]
                ref_wk  = stocked["WK_START_DT"].max() if not stocked.empty else df["WK_START_DT"].max()

            last_wk = ref_wk

        df["_in_aop"] = aop_mask

        def _compute_st(grp):
            total_sl = grp[grp["_in_aop"]]["SL_Q"].sum()
            if has_wk and ref_wk is not None:
                cls_stk = grp[grp["WK_START_DT"] == ref_wk]["CLS_STK_Q"].sum()
            else:
                cls_stk = grp["CLS_STK_Q"].sum()
            avail = total_sl + cls_stk
            return round(total_sl / avail * 100, 1) if avail > 0 else 0.0

        # Section-level ST% (broad categories)
        result = {str(sec).strip(): _compute_st(grp) for sec, grp in df.groupby("SECTION")}

        # Department-level ST% (granular, normalized to DVDATA section ids)
        result_dept = {}
        if has_dept_col:
            df["_dept"] = df["DEPARTMENT"].astype(str).str.strip().apply(normalize_dept_id)
            for dept, grp in df.groupby("_dept"):
                if dept and dept != "nan":
                    result_dept[dept] = _compute_st(grp)

        week_label = str(last_wk.date()) if has_wk and last_wk is not None and pd.notna(last_wk) else "all"

        # ── Monthly average weekly ST% (WK9-26, SEASON contains '26', ACTIVE stores) ──
        # Reads the weekly ST data already present in the parquet; groups by week, then
        # averages per month (WK9-13=Mar, WK14-17=Apr, WK18-22=May, WK23-26=Jun).
        monthly_st:      dict = {}  # {DIVISION: {mi: avg_pct}}  → updates DEPT_MONTHLY_ST in UI
        monthly_st_dept: dict = {}  # {dept_id:  {mi: avg_pct}}  → shown per department row

        has_week_col = "WEEK" in df.columns
        if has_week_col:
            mdf = df.copy()
            if "SEASON" in mdf.columns:
                mdf = mdf[mdf["SEASON"].astype(str).str.contains("26", na=False)]
            if "STORE_STATUS" in mdf.columns:
                mdf = mdf[mdf["STORE_STATUS"].astype(str).str.upper() == "ACTIVE"]
            mdf = mdf[mdf["WEEK"].isin(VALID_WK_STRS)]
            if not mdf.empty:
                mdf["_mi"] = mdf["WEEK"].map(WEEK_STR_TO_MI)
                if has_dept_col and "_dept" not in mdf.columns:
                    mdf["_dept"] = mdf["DEPARTMENT"].astype(str).str.strip().apply(normalize_dept_id)

                def _avg_wk_st(wdf, grp_col):
                    """Per (grp_col, WEEK) → sum qty → weekly ST% → average per (grp_col, MI) excluding 0%."""
                    out: dict = {}
                    wg = wdf.groupby([grp_col, "WEEK", "_mi"])[["SL_Q","CLS_STK_Q"]].sum().reset_index()
                    wg["_pct"] = wg.apply(
                        lambda r: r["SL_Q"]/(r["SL_Q"]+r["CLS_STK_Q"])*100
                                  if (r["SL_Q"]+r["CLS_STK_Q"])>0 else 0.0, axis=1)
                    for (key, mi), g in wg.groupby([grp_col, "_mi"]):
                        k = str(key).strip()
                        if not k or k == "nan": continue
                        nz = g[g["_pct"] > 0]["_pct"]
                        if k not in out: out[k] = {}
                        out[k][int(mi)] = round(float(nz.mean()), 1) if len(nz) else 0.0
                    return out

                if "DIVISION" in mdf.columns:
                    monthly_st = _avg_wk_st(mdf, "DIVISION")
                if has_dept_col and "_dept" in mdf.columns:
                    monthly_st_dept = _avg_wk_st(mdf, "_dept")

        ts = datetime.now().isoformat()
        _last_sync["sellthru"] = ts
        _st_job = {
            "status": "done",
            "data": {"ok": True, "sell_thru": result, "sell_thru_dept": result_dept,
                     "monthly_st": monthly_st, "monthly_st_dept": monthly_st_dept,
                     "source_file": os.path.basename(src), "section_count": len(result),
                     "dept_count": len(result_dept), "has_dept_col": has_dept_col,
                     "week": week_label, "synced_at": ts, "data_version": _data_version()},
            "error": None,
        }
    except Exception as exc:
        _st_job = {"status": "error", "data": None, "error": str(exc)}


@app.route("/api/sync/sellthru")
def api_sync_sellthru():
    global _st_job
    src = get_latest_file(SELLTHRU_DIR, ("*.parquet",)) or \
          get_latest_file(SELLTHRU_DIR, ("*.xlsx", "*.xls", "*.csv"))
    if not src:
        return jsonify({"ok": False, "error": "No sell-through file found."}), 404
    if _st_job["status"] == "running":
        return jsonify({"ok": True, "status": "running"})
    if _st_job["status"] == "done":
        return jsonify({"ok": True, "status": "done"})
    _st_job = {"status": "running", "data": None, "error": None}
    import threading
    threading.Thread(target=_run_st_job, args=(src,), daemon=True).start()
    return jsonify({"ok": True, "status": "running"})


@app.route("/api/sync/sellthru/poll")
def api_sync_sellthru_poll():
    job = _st_job
    if job["status"] == "done":
        return jsonify({**job["data"], "status": "done"})
    if job["status"] == "error":
        return jsonify({"ok": False, "status": "error", "error": job["error"]})
    return jsonify({"ok": True, "status": job["status"]})


def _run_history_job(src: str):
    """Background worker: aggregate FY19 + FY26 from the parquet and store in _hist_job."""
    global _hist_job, _last_sync
    try:
        import pyarrow.parquet as pq
        import pyarrow as pa
        schema = pq.read_schema(src)
        cols_lower_schema = {c.lower(): c for c in schema.names}

        date_col = detect_col(cols_lower_schema, ["bill_date", "tran_date", "billdate", "billmonth", "bill_month",
                                                   "invoice_date", "sale_date", "trans_date", "date", "dt",
                                                   "month", "yr_mo", "yearmonth"])
        div_col  = detect_col(cols_lower_schema, ["division", "div_nm", "div", "divis"])
        amt_col  = detect_col(cols_lower_schema, ["sl_v", "slv", "sl_val", "sale_val",
                                                   "net_amount", "net_amt", "net_sale", "netsale", "netsales",
                                                   "net_value", "bill_value", "bill_amt", "billing_amt",
                                                   "sale_value", "sale_amt", "sales_value", "sales_amt",
                                                   "amount", "revenue", "gross", "net_bill", "extaxamt", "ex_tax"])

        if not all([date_col, div_col, amt_col]):
            _hist_job = {"status": "error", "data": None,
                         "error": f"Column detection failed: date={date_col} div={div_col} amt={amt_col}"}
            return

        # Integer YYYYMM filter — pushes down to row groups if parquet has stats
        date_field = schema.field(date_col)
        target_ym_ints = []
        for mi, cal_mo in enumerate(_CAL_MONTHS):
            yr19 = 2019 if cal_mo >= 4 else 2020
            yr26 = 2025 if cal_mo >= 4 else 2026
            target_ym_ints.extend([yr19 * 100 + cal_mo, yr26 * 100 + cal_mo])

        row_filter = [(date_col, "in", target_ym_ints)] if pa.types.is_integer(date_field.type) else None

        # Copy network parquet to local once; sales job will read the same snapshot for consistency
        local_src = os.path.join(LOCAL_CACHE, "rs_sales_latest.parquet")
        if src != local_src:
            try:
                shutil.copy2(src, local_src)
                src = local_src
            except Exception:
                pass  # fall back to network path if copy fails

        # Read STORE_NAME and TAG_TYPE to filter to LFL stores (032 - Stores tag)
        store_col = detect_col(cols_lower_schema, ["store_name", "store", "store_nm", "outlet", "outlet_name"])
        tag_col   = detect_col(cols_lower_schema, ["tag_type", "tag", "store_tag", "store_type"])
        sec_col   = detect_col(cols_lower_schema, ["section_nm", "section", "sec_nm", "sec_name"])
        dept_col  = detect_col(cols_lower_schema, ["department", "dept_nm", "dept_name", "dept"])
        read_cols = [date_col, div_col, amt_col] \
                    + ([dept_col]  if dept_col  else []) \
                    + ([sec_col]   if sec_col   else []) \
                    + ([store_col] if store_col else []) \
                    + ([tag_col]   if tag_col   else [])

        df = pd.read_parquet(src, columns=read_cols, filters=row_filter)
        df[date_col] = parse_date_col(df[date_col])
        df = df.dropna(subset=[date_col])
        df["_ym"]  = list(zip(df[date_col].dt.year, df[date_col].dt.month))
        df["_div"] = df[div_col].apply(normalize_div)
        df[amt_col] = pd.to_numeric(df[amt_col], errors="coerce").fillna(0)
        df = df.dropna(subset=["_div"])

        # Two distinct LFL sets:
        #   lfl_19v26 — stores present in BOTH FY19 and FY26 (long-standing ~32 stores)
        #               used only for FY19 base data to compute 19V26 growth %
        #   lfl_26v27 — ALL stores present in FY26 data (~148 stores, full current network)
        #               used for FY25 and FY26 LY actuals (the 26V27 plan base)
        lfl_19v26 = None
        lfl_26v27 = None
        if tag_col and store_col:
            lfl_mask  = df[tag_col].astype(str).str.strip() == "032 - Stores"
            lfl_19v26 = set(df[lfl_mask][store_col].dropna().unique())
            untagged_mask = df[tag_col].isna() | df[tag_col].astype(str).str.strip().isin(["", "nan", "None"])
            if untagged_mask.any():
                ut_df  = df[untagged_mask & df[store_col].notna()]
                fy19_s = set(FY19_DATE_TO_MI.keys()); fy26_s = set(FY26_DATE_TO_MI.keys())
                ut_fy19 = set(ut_df[ut_df["_ym"].isin(fy19_s)][store_col].unique())
                ut_fy26 = set(ut_df[ut_df["_ym"].isin(fy26_s)][store_col].unique())
                lfl_19v26 |= (ut_fy19 & ut_fy26)
            fy26_tag_mask = df[tag_col].astype(str).str.strip().isin(LFL_TAGS_26V27)
            lfl_26v27 = set(df[fy26_tag_mask & df["_ym"].isin(set(FY26_DATE_TO_MI.keys()))][store_col].dropna().unique())
        elif store_col:
            fy19_all = set(df[df["_ym"].isin(set(FY19_DATE_TO_MI.keys()))][store_col].dropna().unique())
            fy26_all = set(df[df["_ym"].isin(set(FY26_DATE_TO_MI.keys()))][store_col].dropna().unique())
            lfl_19v26 = fy19_all & fy26_all
            lfl_26v27 = fy26_all

        def _agg_fy(date_to_mi: dict, store_set=None):
            target = set(date_to_mi.keys())
            sub = df[df["_ym"].isin(target)].copy()
            if store_set is not None and store_col and store_col in sub.columns:
                sub = sub[sub[store_col].isin(store_set)]
            sub["_mi"] = sub["_ym"].map(date_to_mi)
            # Division-level aggregation
            div_grouped = sub.groupby(["_div", "_mi"])[amt_col].sum()
            div_res: dict = {}
            for (dv, mi), total in div_grouped.items():
                div_res.setdefault(str(dv), {})[str(int(mi))] = round(float(total) / 1e7, 4)
            # Department-level aggregation (granular, normalized to DVDATA section ids)
            dept_res: dict = {}
            if dept_col and dept_col in sub.columns:
                sub["_dept"] = sub[dept_col].astype(str).str.strip().apply(normalize_dept_id)
                dept_grouped = sub.groupby(["_dept", "_mi"])[amt_col].sum()
                for (dept, mi), total in dept_grouped.items():
                    if dept and dept != "nan":
                        dept_res.setdefault(dept, {})[str(int(mi))] = round(float(total) / 1e7, 4)
            return div_res, dept_res

        # FY19 base: 19V26 LFL stores only (long-standing stores, for growth % accuracy)
        fy19_div, fy19_dept = _agg_fy(FY19_DATE_TO_MI, store_set=lfl_19v26)
        # FY25 + FY26 LY: all FY26 stores (148 stores, full 26V27 base)
        fy25_div, fy25_dept = _agg_fy(FY25_DATE_TO_MI, store_set=lfl_26v27)
        fy26_div, fy26_dept = _agg_fy(FY26_DATE_TO_MI, store_set=lfl_26v27)
        ts = datetime.now().isoformat()
        _last_sync["history"] = ts
        _hist_job = {
            "status": "done",
            "data": {"ok": True,
                     "fy19": fy19_div, "fy25": fy25_div, "fy26": fy26_div,
                     "fy19_dept": fy19_dept, "fy25_dept": fy25_dept, "fy26_dept": fy26_dept,
                     "source_file": os.path.basename(src), "synced_at": ts,
                     "lfl_store_count": len(lfl_19v26) if lfl_19v26 is not None else None,
                     "lfl_26v27_count": len(lfl_26v27) if lfl_26v27 is not None else None,
                     "detected_dept_col": dept_col,
                     "dept_count": len(fy26_dept),
                     "data_version": _data_version()},
            "error": None,
        }
    except Exception as exc:
        _hist_job = {"status": "error", "data": None, "error": str(exc)}


@app.route("/api/sync/history")
def api_sync_history():
    """Start a background history sync and return immediately. Poll /api/sync/history/poll for result."""
    global _hist_job
    src = _get_sales_src()
    if not src:
        return jsonify({"ok": False, "error": "No parquet file found in SALES_DIR"}), 404

    if _hist_job["status"] == "running":
        return jsonify({"ok": True, "status": "running"})
    if _hist_job["status"] == "done":
        # Already computed — client should poll to receive the data
        return jsonify({"ok": True, "status": "done"})

    # idle or error: start a new background job
    _hist_job = {"status": "running", "data": None, "error": None}
    import threading
    threading.Thread(target=_run_history_job, args=(src,), daemon=True).start()
    return jsonify({"ok": True, "status": "running"})


@app.route("/api/sync/history/poll")
def api_sync_history_poll():
    """Return current history job status. status: running | done | error | idle."""
    job = _hist_job
    if job["status"] == "done":
        return jsonify({**job["data"], "status": "done"})
    if job["status"] == "error":
        return jsonify({"ok": False, "status": "error", "error": job["error"]}), 500
    return jsonify({"ok": True, "status": job["status"]})


@app.route("/api/sync")
def api_sync_all():
    """Kick off sales + sell-through background jobs and return immediately."""
    from flask import current_app
    with current_app.test_request_context("/api/sync/sales"):
        sales_resp = api_sync_sales()
    with current_app.test_request_context("/api/sync/sellthru"):
        st_resp = api_sync_sellthru()
    sales = sales_resp.get_json() if hasattr(sales_resp, "get_json") else sales_resp[0].get_json()
    st    = st_resp.get_json()    if hasattr(st_resp,    "get_json") else st_resp[0].get_json()
    return jsonify({"ok": True, "sales": sales, "sellthru": st})


if __name__ == "__main__":
    print("=" * 58)
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=" * 58)
    print("  CityKart OTB Sync Server  -  http://localhost:5050")
    print("=" * 58)
    print(f"  Sales dir  : {SALES_DIR}")
    print(f"  ST dir     : {SELLTHRU_DIR}")
    print(f"  Local cache: {LOCAL_CACHE}")
    if PINNED_SALES_FILE:
        exists = os.path.exists(PINNED_SALES_FILE)
        print(f"  PINNED FILE: {PINNED_SALES_FILE} {'[OK]' if exists else '[MISSING!]'}")
    else:
        print("  Sales pin  : OFF (auto-pick latest)")
    print()
    print("  Endpoints:")
    print("    GET /              - serve the OTB app (open this in browser)")
    print("    GET /api/status    - server health")
    print("    GET /api/sync/sales     - pull latest parquet -> JSON")
    print("    GET /api/sync/history   - FY19 + FY26 full year -> JSON")
    print("    GET /api/sync/sellthru  - pull latest ST file  -> JSON")
    print()
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
