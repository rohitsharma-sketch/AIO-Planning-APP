"""
extract_dept_kpis.py  ·  CityKart OTB Planning
================================================
Produces two JSON constants for otb-plan-app.html:
  · DEPT_MONTHLY_ST   — monthly avg weekly sell-through % by division
  · DEPT_LFL_GROWTH   — LFL (same-store) YoY growth% by (division, FY month)
                         yoy  = FY25-26 vs FY24-25  (same calendar month)
                         base = FY25-26 vs FY18-19  (NOT AVAILABLE in current
                                data; placeholder zeros output — update path
                                below once older data is sourced)

Output: dept_monthly_kpis.json  →  paste into the HTML constants block.

Run:  python extract_dept_kpis.py
"""

import os, json, warnings
import pandas as pd
import numpy as np
from datetime import date

warnings.filterwarnings("ignore")

# ── PATHS ───────────────────────────────────────────────────────────────────
ST_PATH    = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw\rs_weekly_sell_ths_apps"
SALES_PATH = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw\rs_sales_19-_till_date"
OUT_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dept_monthly_kpis.json")

# ── CONSTANTS ────────────────────────────────────────────────────────────────
# Indian FY: Apr=0, May=1, …, Mar=11
FY_MONTHS = ["Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar"]

def fy_mi(cal_month: int) -> int:
    return (cal_month - 4) % 12

# Divisions to include  (parquet DIVISION value → app id)
DIV_MAP = {
    "MENS"            : "mens",
    "LADIES"          : "ladies",
    "KIDS"            : "kids",
    "HOUSEHOLD"       : "household",
    "FOOTWEAR"        : "footwear",
    "LIFESTYLE"       : "lifestyle",
    "HOME FURNISHING" : "homefurn",
    "STATIONERY"      : "stationery",
    "SPORTS  & TOYS"  : "sports",      # future: add to DVDATA if needed
}
VALID_DIVS = set(DIV_MAP.keys())

# ── STEP 1 : MONTHLY AVG WEEKLY ST% FROM rs_weekly_sell_ths_apps ─────────────
def compute_monthly_st():
    """
    Schema: DIVISION, WEEK (WK-01…), WK_START_DT (datetime), SL_Q, OPN_Q, IN_TRAN_Q
    ST% = SL_Q / (OPN_Q + IN_TRAN_Q) * 100, summed to (div, week) then averaged per month.
    Uses FY26 data only (WK_START_DT >= 2025-04-01) to give current-year sell-through.
    """
    print("\n" + "─"*60)
    print("STEP 1 · Weekly ST% → monthly avg by division (FY26)")
    print("─"*60)

    COLS = ["DIVISION","WEEK","WK_START_DT","SL_Q","OPN_Q","IN_TRAN_Q"]
    frames = []
    for fname in sorted(os.listdir(ST_PATH)):
        if not fname.endswith(".parquet"):
            continue
        df = pd.read_parquet(os.path.join(ST_PATH, fname), columns=COLS)
        frames.append(df)

    if not frames:
        print("  ✗ No parquet files found in ST_PATH — skipping")
        return {}

    raw = pd.concat(frames, ignore_index=True)
    raw["WK_START_DT"] = pd.to_datetime(raw["WK_START_DT"])
    print(f"  Loaded {len(frames)} file(s)  |  {len(raw):,} rows")
    print(f"  WK_START_DT range: {raw['WK_START_DT'].min().date()} → {raw['WK_START_DT'].max().date()}")
    print(f"  Divisions: {sorted(raw['DIVISION'].dropna().unique())}")

    # Filter to known apparel/GM divisions
    raw = raw[raw["DIVISION"].isin(VALID_DIVS)].copy()
    raw["_DIV"]   = raw["DIVISION"].map(DIV_MAP)
    raw["_MONTH"] = raw["WK_START_DT"].dt.month
    raw["_FY_MI"] = raw["_MONTH"].apply(fy_mi)
    raw["_FY_YR"] = raw["WK_START_DT"].apply(
        lambda d: d.year if d.month >= 4 else d.year - 1
    )

    # FY26-27 = year starting April 2026 (current planning year; today = Aug 2026)
    fy26_st = raw[raw["_FY_YR"] == 2026].copy()
    print(f"  FY26-27 rows (Apr 2026 onward): {len(fy26_st):,}")

    # Sum quantities to (division, week, fy_month) level — article rows → one row per week/div
    agg = (
        fy26_st.groupby(["_DIV","WEEK","_FY_MI"])
        .agg(SL=("SL_Q","sum"), OPN=("OPN_Q","sum"), TRN=("IN_TRAN_Q","sum"))
        .reset_index()
    )
    denom = (agg["OPN"] + agg["TRN"]).replace(0, np.nan)
    agg["ST_PCT"] = agg["SL"] / denom * 100

    # Average weekly ST% per (division, fy_month)
    monthly = (
        agg.groupby(["_DIV","_FY_MI"])["ST_PCT"]
        .mean()
        .reset_index()
    )

    print(f"\n  Division × month avg ST% (FY26):")
    pivot = monthly.pivot(index="_DIV", columns="_FY_MI", values="ST_PCT").round(1)
    pivot.columns = [FY_MONTHS[m] for m in pivot.columns]
    print(pivot.to_string())

    # Build result: {app_div_id: {fy_mi: avg_st}}
    result = {}
    for _, row in monthly.iterrows():
        div = row["_DIV"]
        mi  = int(row["_FY_MI"])
        st  = row["ST_PCT"]
        if pd.notna(st):
            result.setdefault(div, {})[mi] = round(float(st), 2)
    return result


# ── STEP 2 : FY25 vs FY26 LFL GROWTH FROM rs_sales_19-_till_date ─────────────
def compute_lfl_growth():
    print("\n" + "─"*60)
    print("STEP 2 · LFL growth — FY25 vs FY26 (same-store, same month)")
    print("─"*60)

    COLS_NEEDED = ["BILLMONTH","DIVISION","STORE_NAME","SL_V","STORE_CURRENT_STATUS"]
    print(f"  Reading columns: {COLS_NEEDED}")

    # Find the single parquet file (or read all if folder with multiple)
    sales_files = [f for f in os.listdir(SALES_PATH) if f.endswith(".parquet")]
    if not sales_files:
        print("  ✗ No sales parquet files found")
        return {}, {}

    frames = []
    for fname in sales_files:
        df = pd.read_parquet(os.path.join(SALES_PATH, fname), columns=COLS_NEEDED)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    print(f"  Loaded {len(raw):,} rows")

    # Normalise
    raw["BILLMONTH"] = pd.to_datetime(raw["BILLMONTH"])
    raw["_DIV"]    = raw["DIVISION"].str.strip()
    raw["_SLV"]    = pd.to_numeric(raw["SL_V"], errors="coerce").fillna(0)
    raw["_STORE"]  = raw["STORE_NAME"].astype(str).str.strip()
    raw["_STATUS"] = raw["STORE_CURRENT_STATUS"].astype(str).str.strip()

    # Restrict to known apparel/GM divisions
    raw = raw[raw["_DIV"].isin(VALID_DIVS)].copy()
    raw["_APPID"]  = raw["_DIV"].map(DIV_MAP)
    raw["_FY_MI"]  = raw["BILLMONTH"].dt.month.apply(fy_mi)
    raw["_FY_YR"]  = raw["BILLMONTH"].apply(
        lambda d: d.year if d.month >= 4 else d.year - 1   # FY start year (Apr-based)
    )

    print(f"\n  After division filter: {len(raw):,} rows")
    print(f"  STORE_CURRENT_STATUS breakdown: {raw['_STATUS'].value_counts().to_dict()}")

    # ── FY26 = FY starting April 2025  (year 2025 in Apr-based numbering)
    # ── FY25 = FY starting April 2024  (year 2024)
    FY26_YR, FY25_YR = 2025, 2024

    fy26 = raw[raw["_FY_YR"] == FY26_YR].copy()
    fy25 = raw[raw["_FY_YR"] == FY25_YR].copy()

    print(f"\n  FY26 rows: {len(fy26):,}   FY25 rows: {len(fy25):,}")

    # LFL filter: keep only stores classified as SAME STORE
    fy26_lfl = fy26[fy26["_STATUS"] == "SAME STORE"]
    fy25_lfl = fy25[fy25["_STATUS"] == "SAME STORE"]

    # Additional LFL: store must appear in BOTH FY25 and FY26 for the same month
    # Aggregate sales by (div, fy_month, store)
    g26 = fy26_lfl.groupby(["_APPID","_FY_MI","_STORE"])["_SLV"].sum().reset_index()
    g25 = fy25_lfl.groupby(["_APPID","_FY_MI","_STORE"])["_SLV"].sum().reset_index()

    # Inner join on (div, fy_month, store) = only truly matched stores
    merged = g26.merge(
        g25, on=["_APPID","_FY_MI","_STORE"], suffixes=("_26","_25")
    )
    print(f"  LFL matched (div, month, store) combos: {len(merged):,}")

    # Sum to (div, fy_month) level and compute growth%
    agg = merged.groupby(["_APPID","_FY_MI"]).agg(
        SLV_26=("_SLV_26","sum"),
        SLV_25=("_SLV_25","sum")
    ).reset_index()
    agg["GROWTH"] = (agg["SLV_26"] - agg["SLV_25"]) / agg["SLV_25"].replace(0, np.nan) * 100

    print(f"\n  YoY growth by division × month:")
    pivot = agg.pivot(index="_APPID", columns="_FY_MI", values="GROWTH").round(1)
    pivot.columns = [FY_MONTHS[m] for m in pivot.columns]
    print(pivot.to_string())

    # Build result dict
    yoy = {}
    for _, row in agg.iterrows():
        div = row["_APPID"]
        mi  = int(row["_FY_MI"])
        g   = row["GROWTH"]
        if pd.notna(g):
            yoy.setdefault(div, {})[mi] = round(float(g), 1)

    # Base (FY19) not available — return empty dict with note
    base = {}
    print("\n  ⚠  FY18-19 data not in this file (starts Jan 2024).")
    print("     base growth will remain as placeholder in the app.")

    return yoy, base


# ── STEP 3 : ASSEMBLE & WRITE OUTPUT ─────────────────────────────────────────
def build_html_constants(st_by_code, lfl_yoy, lfl_base):
    """
    st_by_code: {dept_code: {fy_mi: avg_st_pct}}
    The ST data department codes may differ from the sales DIVISION codes.
    We try to match them; if a code maps to an app div via DIV_MAP we use it,
    otherwise we use the code directly as the key.
    """
    # Normalise ST keys through DIV_MAP
    dept_monthly_st = {}
    for code, months in st_by_code.items():
        app_id = DIV_MAP.get(code.strip().upper(), code.strip().lower().replace(" ","_"))
        existing = dept_monthly_st.get(app_id, {})
        for mi, val in months.items():
            existing[mi] = val
        dept_monthly_st[app_id] = existing

    dept_lfl_growth = {}
    all_divs = set(lfl_yoy) | set(lfl_base)
    for div in all_divs:
        dept_lfl_growth[div] = {}
        if div in lfl_yoy:
            dept_lfl_growth[div]["yoy"]  = lfl_yoy[div]
        if div in lfl_base:
            dept_lfl_growth[div]["base"] = lfl_base[div]

    return dept_monthly_st, dept_lfl_growth


def to_js_obj(d):
    """Render a nested dict as compact JS object literal with integer keys unquoted."""
    def render(v, indent=0):
        pad = "  " * indent
        if isinstance(v, dict):
            if not v:
                return "{}"
            items = []
            for k, vv in sorted(v.items(), key=lambda x: int(x[0]) if isinstance(x[0], str) and x[0].isdigit() else x[0]):
                items.append(f"{pad}  {k}:{render(vv,indent+1)}")
            return "{\n" + ",\n".join(items) + f"\n{pad}}}"
        elif isinstance(v, float):
            return f"{v:.1f}"
        else:
            return repr(v)
    return render(d)


if __name__ == "__main__":
    print("=" * 60)
    print("CityKart OTB  ·  Dept KPI Extractor")
    print("=" * 60)

    st_by_code        = compute_monthly_st()
    lfl_yoy, lfl_base = compute_lfl_growth()

    dept_monthly_st, dept_lfl_growth = build_html_constants(st_by_code, lfl_yoy, lfl_base)

    # Save JSON
    result = {
        "dept_monthly_st":  {div: {str(k): v for k, v in months.items()} for div, months in dept_monthly_st.items()},
        "dept_lfl_growth":  dept_lfl_growth,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n✓ JSON saved → {OUT_PATH}")

    # Print ready-to-paste JS constants
    print("\n" + "="*60)
    print("PASTE INTO otb-plan-app.html  (replace existing constants)")
    print("="*60)
    print(f"\nconst DEPT_MONTHLY_ST = {to_js_obj({div: {int(k):v for k,v in m.items()} for div,m in result['dept_monthly_st'].items()})};\n")
    print(f"const DEPT_LFL_GROWTH = {to_js_obj(result['dept_lfl_growth'])};")
