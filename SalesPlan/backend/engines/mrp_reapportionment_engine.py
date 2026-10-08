"""
MRP Re-apportionment Engine — FastAPI Router v2
================================================
Redistributes historical sales from discontinued MRP slabs to valid (listed) MRP slabs.

Logic (the planners' MRP master, user 2026-10-08 - "MRP MASTER - 27-04-2026 - New(Shubham).xlsx", sheet "MRP Adj"):
  - The master lists, per Department x Display, every old MRP (MRP_CURRENT) and its new MRP (MRP_LISTED; 0 =
    discontinued).
  - Sales at a listed MRP move to its MRP_LISTED.
  - Sales at a discontinued MRP split between the nearest listed MRP below and the nearest above (old MRPs in value
    order, same Department x Display): Summer 60% down / 40% up, every other attribute 40% down / 60% up (Regular and
    Occasional per the master's assumptions; PreWinter / Winter the same, user 2026-10-08). Only one side listed ->
    100% there. Nothing listed in the Department x Display -> Unmapped.
  - Totals are preserved exactly per Store x Dept x Display x Attribute x Month (Unmapped rows reported apart).

Sources:
  Sales:       the suite's sales engine (user, 2026-09-29: "LY actual sales will be taken from the sales engine
               which is embedded in all the other apps, only the new MRP structure will be given") - the Calendar
               engine's month-wise data-lake file, read with its own reader, LY Mar-Jun 2026, and checked cell by
               cell against the Calendar department snapshot (store x department x month) Sales Plan reads.
  MRP Mapping: MRP Merging Engine/Sales Reapportionment/MRP Mapping/MRP Mapping Master.xlsx (the only upload)

Endpoints:
  GET  /status           → file presence, last-run metadata
  GET  /sales-status     → sales engine file, LY months, tie to Calendar dept sales
  GET  /mrp-groups       → groups (Dept, Display): listed MRPs and where each discontinued one goes
  POST /run              → redistribution by the nearest-listed-MRP rule
  GET  /download         → latest output Excel
"""

import os
import io
import glob
import json
import warnings
import datetime
import threading
from typing import Optional, Dict, List

import sys
import pandas as pd
import openpyxl
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import SHOWN  # noqa: E402
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from plan_cache import save_json  # noqa: E402 - atomic JSON writes (audit 2026-10-06)

warnings.filterwarnings("ignore")

router = APIRouter()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE         = r"C:\Users\A9820\Documents\CLaude - New Projects"
MAPPING_DIR  = os.path.join(BASE, r"MRP Merging Engine\Sales Reapportionment\MRP Mapping")
OUTPUT_DIR   = os.path.join(BASE, r"MRP Merging Engine\Sales Reapportionment\Output")
LAST_RUN_JSON = os.path.join(OUTPUT_DIR, "_last_run.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MAPPING_DIR, exist_ok=True)


# ── Pydantic models ────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    pass   # the split is fixed by the master's rule (typed %s per group until 2026-10-08)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().upper().replace(" ", "_").replace("-", "_") for c in df.columns]
    return df


# LY months = the plan's LY (Mar-Jun 2026, as BIS / AOP); labels as the old sales template ("Mar 2026").
LY_MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06"]
_SALES_CACHE: dict = {}   # {"key": (path, mtime), "df", "month_cols", "check"}
_SALES_LOCK = threading.Lock()   # one read at a time: a page opened during the startup warm-up waits for it


def _calendar_scans():
    """The Calendar engine's own data-lake reader (RS Planning Platform/backend/calendar_engine/scans.py)."""
    import sys
    plat = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "RS Planning Platform", "backend")
    if plat not in sys.path:
        sys.path.insert(0, plat)
    from calendar_engine import scans
    return scans


def _find_sales_file() -> Optional[str]:
    files = _calendar_scans()._latest_monthwise_files()
    return files[0] if files else None


def _engine_check(raw: pd.DataFrame) -> dict:
    """Store x department x month of the MRP-level sales vs the Calendar 'actual_dept' snapshot (Rs in, lakh diff)."""
    import collections
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))
    from db.base import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as db:
        snap = db.execute(text("SELECT rows FROM calendar.sales_snapshots "
                               "WHERE source_type='mw' AND kind='actual_dept'")).scalar() or []
    want = set(LY_MONTHS)
    cal = collections.defaultdict(float)
    for r in snap:
        if r["col"] in want:
            cal[(str(r["store"]).strip().upper(), str(r["DEPARTMENT"]).strip().upper(), r["col"])] += float(r["value"])
    ours = raw.groupby(["STORE", "DEPARTMENT", "ym"])["SL_V"].sum().to_dict()
    keys = set(cal) | set(ours)
    worst = max((abs(ours.get(k, 0.0) - cal.get(k, 0.0)) / 1e5 for k in keys), default=0.0)
    return {"cells": len(keys), "max_diff_lakh": round(worst, 6), "pass": bool(keys) and worst <= 0.01,
            "total_lakh": round(sum(ours.values()) / 1e5, 2), "calendar_total_lakh": round(sum(cal.values()) / 1e5, 2)}


def _engine_sales() -> tuple:
    """LY sales at Store x Division x Dept x MRP x Display x Attribute, one column per LY month, from the sales
    engine's file. ponytail: one cached copy, re-read only when the data-lake file changes."""
    scans = _calendar_scans()
    path = _find_sales_file()
    if not path:
        raise ValueError(f"Sales engine file not reachable: {scans.PARQUET_DIR}")
    key = (path, os.path.getmtime(path))
    with _SALES_LOCK:
        if _SALES_CACHE.get("key") != key:
            _read_engine_sales(scans, path, key)
    return _SALES_CACHE["df"].copy(), list(_SALES_CACHE["month_cols"]), _SALES_CACHE["check"]


def _read_engine_sales(scans, path, key):
    lo, hi = scans._month_bounds(LY_MONTHS)
    raw = scans._read_file_filtered(path, ["BILLMONTH", "DIVISION", "STORE_NAME", "SL_V", "DEPARTMENT", "MRP",
                                           "DISPLAY_TYPE", "ATTRIBUTE1"], "BILLMONTH", lo, hi)
    raw["ym"] = raw["BILLMONTH"].dt.strftime("%Y-%m")
    raw = raw[raw["ym"].isin(LY_MONTHS)].rename(
        columns={"STORE_NAME": "STORE", "DISPLAY_TYPE": "DISPLAY", "ATTRIBUTE1": "ATTRIBUTE"})
    for c in ("STORE", "DIVISION", "DEPARTMENT", "DISPLAY", "ATTRIBUTE"):
        raw[c] = raw[c].astype(str).str.strip().str.upper()
    raw["MRP"] = pd.to_numeric(raw["MRP"], errors="coerce").fillna(0).round().astype(int)
    raw["SL_V"] = pd.to_numeric(raw["SL_V"], errors="coerce").fillna(0.0)
    check = _engine_check(raw)
    label = {m: datetime.date(int(m[:4]), int(m[5:]), 1).strftime("%b %Y") for m in LY_MONTHS}
    wide = raw.pivot_table(index=["STORE", "DIVISION", "DEPARTMENT", "MRP", "DISPLAY", "ATTRIBUTE"],
                           columns="ym", values="SL_V", aggfunc="sum", fill_value=0.0).reset_index()
    wide.columns.name = None
    wide = wide.rename(columns=label)
    month_cols = [label[m] for m in LY_MONTHS if label[m] in wide.columns]
    _SALES_CACHE.update(key=key, df=wide, month_cols=month_cols, check=check)


def warm_sales():
    """Read the sales engine file once at server start (user, 2026-10-07: the first MRP Re-apportionment open after a
    restart took ~85 s). Never raises - the page shows the reason itself if the file isn't reachable."""
    try:
        _engine_sales()
    except Exception as e:  # noqa: BLE001
        print(f"MRP re-apportionment warm-up skipped: {e}", flush=True)


def _mapped_sales(mapping_df: pd.DataFrame) -> tuple:
    """Engine sales of the departments the MRP structure covers (the rest of the business is not re-apportioned)."""
    df, month_cols, check = _engine_sales()
    return df[df["DEPARTMENT"].isin(set(mapping_df["DEPARTMENT"]))].reset_index(drop=True), month_cols, check


def _find_mapping_file() -> Optional[str]:
    files = []
    for pat in ("*.xlsx", "*.xls"):
        files.extend(glob.glob(os.path.join(MAPPING_DIR, pat)))
    return max(files, key=os.path.getmtime) if files else None


def _wide_master(path: str) -> Optional[pd.DataFrame]:
    """The master as the planners keep it: one column per Department x Display x old MRP, rows labelled DEPARTMENT /
    DISPLAY / MRP_CURRENT / MRP_LISTED in column A (sheet "MRP Adj"). None if no sheet is laid out that way."""
    need = ("DEPARTMENT", "DISPLAY", "MRP_CURRENT", "MRP_LISTED")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            rows = {str(r[0]).strip().upper(): r for r in ws.iter_rows(max_row=30, values_only=True)
                    if r and r[0] is not None}
            if all(k in rows for k in need):
                n = min(len(rows[k]) for k in need)
                df = pd.DataFrame({k: list(rows[k][1:n]) for k in need})
                return df[df["DEPARTMENT"].notna() & pd.to_numeric(df["MRP_CURRENT"], errors="coerce").notna()]
    finally:
        wb.close()
    return None


def _load_mapping() -> pd.DataFrame:
    """Load the MRP master -> DEPARTMENT, DISPLAY, MRP_CURRENT, MRP_LISTED (one row per Department x Display x old
    MRP). Reads the planners' wide "MRP Adj" layout, or a plain list with those columns."""
    path = _find_mapping_file()
    if not path:
        raise ValueError(f"No mapping file found in: {MAPPING_DIR}")

    df = _wide_master(path)
    if df is None:
        df = _norm_cols(pd.read_excel(path))
        rename = {}
        for c in df.columns:
            cu = c.upper()
            if cu in ("DEPARTMENT", "DEPT"):               rename[c] = "DEPARTMENT"
            elif cu in ("DISPLAY", "DISPLAY_TYPE"):        rename[c] = "DISPLAY"
            elif cu in ("MRP_CURRENT", "CURRENT_MRP",
                        "MRP", "RAW_MRP", "OLD_MRP"):      rename[c] = "MRP_CURRENT"
            elif cu in ("MRP_LISTED", "LISTED_MRP",
                        "NEW_MRP", "FINAL_MRP"):            rename[c] = "MRP_LISTED"
        df.rename(columns=rename, inplace=True)
        missing = [c for c in ("DEPARTMENT", "DISPLAY", "MRP_CURRENT", "MRP_LISTED") if c not in df.columns]
        if missing:
            raise ValueError(f"MRP Mapping Master missing columns: {missing}")

    df = df.dropna(subset=["DEPARTMENT"])[["DEPARTMENT", "DISPLAY", "MRP_CURRENT", "MRP_LISTED"]].copy()
    for c in ["DEPARTMENT", "DISPLAY"]:
        df[c] = df[c].astype(str).str.strip().str.upper()
    df["MRP_CURRENT"] = pd.to_numeric(df["MRP_CURRENT"], errors="coerce").fillna(0).round().astype(int)
    df["MRP_LISTED"]  = pd.to_numeric(df["MRP_LISTED"],  errors="coerce").fillna(0).round().astype(int)
    df = df.drop_duplicates()
    clash = df[df.duplicated(["DEPARTMENT", "DISPLAY", "MRP_CURRENT"], keep=False)]
    if not clash.empty:
        raise ValueError(f"MRP master gives {len(clash)} old MRPs two different new MRPs, "
                         f"e.g. {clash.head(3).to_dict('records')}")
    return df.reset_index(drop=True)


# Share of a discontinued MRP's sales that goes to the nearest listed MRP BELOW it; the rest goes to the nearest above.
LOWER_PCT = {"SUMMER": 60.0}
LOWER_PCT_DEFAULT = 40.0   # Regular / Occasional (master's assumptions); PreWinter / Winter too (user, 2026-10-08)
KEYS = ["DEPARTMENT", "DISPLAY", "MRP_CURRENT"]


def _targets(mapping_df: pd.DataFrame) -> pd.DataFrame:
    """Each master row plus BELOW / ABOVE: the new MRP of the nearest listed old MRP below / above it in the same
    Department x Display (0 = none on that side) - what the master's Initial1 / Initial2 rows work out."""
    out = []
    for _, g in mapping_df.sort_values("MRP_CURRENT").groupby(["DEPARTMENT", "DISPLAY"], sort=False):
        lst = g["MRP_LISTED"].tolist()
        below, run = [], 0
        for v in lst:
            below.append(run)
            run = v or run
        above, run = [], 0
        for v in reversed(lst):
            above.append(run)
            run = v or run
        out.append(g.assign(BELOW=below, ABOVE=above[::-1]))
    cols = ["DEPARTMENT", "DISPLAY", "MRP_CURRENT", "MRP_LISTED", "BELOW", "ABOVE"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def _redistribute(sales_df: pd.DataFrame, mapping_df: pd.DataFrame, month_cols: list) -> tuple:
    """Listed MRPs move to their new MRP; a discontinued MRP splits between the nearest listed MRPs below / above
    (LOWER_PCT by attribute, 100% to the only side). Returns (output_df, unmapped_df, log_lines)."""
    s = sales_df[(sales_df[month_cols] != 0).any(axis=1)].rename(columns={"MRP": "MRP_CURRENT"})
    s = s.assign(MRP_CURRENT=s["MRP_CURRENT"].astype(int)).merge(_targets(mapping_df), on=KEYS, how="left")
    not_in = s["MRP_LISTED"].isna()
    listed = ~not_in & (s["MRP_LISTED"] > 0)
    nowhere = ~not_in & ~listed & (s["BELOW"] == 0) & (s["ABOVE"] == 0)
    d = s[~not_in & ~listed & ~nowhere]

    lo_pct = d["ATTRIBUTE"].map(LOWER_PCT).fillna(LOWER_PCT_DEFAULT)
    lo_pct = lo_pct.where(d["ABOVE"] > 0, 100.0).where(d["BELOW"] > 0, 0.0)
    lo = d.assign(LISTED_MRP=d["BELOW"], SHARE_PCT=lo_pct)
    lo[month_cols] = d[month_cols].mul(lo_pct / 100.0, axis=0)
    hi = d.assign(LISTED_MRP=d["ABOVE"], SHARE_PCT=100.0 - lo_pct)
    hi[month_cols] = d[month_cols] - lo[month_cols]   # the rest, so the two parts add back to the month exactly

    key_cols = ["STORE", "DIVISION", "DEPARTMENT", "DISPLAY", "ATTRIBUTE", "MRP_CURRENT", "LISTED_MRP"]
    parts = [s[listed].assign(LISTED_MRP=s["MRP_LISTED"], SHARE_PCT=100.0), lo[lo_pct > 0], hi[lo_pct < 100]]
    output_df = pd.concat(parts, ignore_index=True)[key_cols + ["SHARE_PCT"] + month_cols]
    output_df["LISTED_MRP"] = output_df["LISTED_MRP"].astype(int)
    # one row per store x ... x old MRP x new MRP (both neighbours can carry the same new MRP: their shares add)
    output_df = output_df.groupby(key_cols, dropna=False)[["SHARE_PCT"] + month_cols].sum().reset_index()

    unmapped_df = pd.concat([s[not_in].assign(REASON="MRP combination not in mapping master"),
                             s[nowhere].assign(REASON="No listed MRP in this Department x Display")],
                            ignore_index=True)
    unmapped_df = unmapped_df.assign(LISTED_MRP=0)[key_cols[:-1] + ["LISTED_MRP"] + month_cols + ["REASON"]]

    log = [f"Rule: discontinued MRP -> nearest listed MRP below / above; Summer {LOWER_PCT['SUMMER']:g}/"
           f"{100 - LOWER_PCT['SUMMER']:g}, others {LOWER_PCT_DEFAULT:g}/{100 - LOWER_PCT_DEFAULT:g}; one side -> 100%",
           f"Listed rows: {int(listed.sum()):,} | split rows: {len(d):,} | unmapped rows: {len(unmapped_df):,}"]
    for (dept, disp), n in unmapped_df.groupby(["DEPARTMENT", "DISPLAY"]).size().items():
        log.append(f"WARN: {n} rows unmapped in [{dept} | {disp}]")
    log.append(f"Output rows: {len(output_df)}")
    return output_df, unmapped_df, log


def _validate(sales_df: pd.DataFrame, output_df: pd.DataFrame,
              month_cols: list, unmapped_df: Optional[pd.DataFrame] = None) -> tuple[list[dict], bool]:
    """Store x Department totals before vs after. Unmapped rows count on the 'after' side - they are reported on their
    own sheet, not lost (user, 2026-10-08: departments with no listed MRP go to Unmapped)."""
    if unmapped_df is not None and not unmapped_df.empty:
        output_df = pd.concat([output_df, unmapped_df[["STORE", "DEPARTMENT"] + month_cols]], ignore_index=True)
    tol = SHOWN   # any difference that shows at 8 decimals (was 0.01)
    val_rows = []
    val_pass = True

    # Sum all month sales per row for Store×Dept totals
    sales_df = sales_df.copy()
    output_df = output_df.copy() if not output_df.empty else pd.DataFrame()

    sales_df["TOTAL"] = sales_df[month_cols].sum(axis=1)
    orig = sales_df.groupby(["STORE", "DEPARTMENT"])["TOTAL"].sum().reset_index()
    orig.rename(columns={"TOTAL": "BEFORE"}, inplace=True)

    if output_df.empty:
        for _, r in orig.iterrows():
            val_rows.append({"STORE": r["STORE"], "DEPARTMENT": r["DEPARTMENT"],
                             "BEFORE": r["BEFORE"], "AFTER": 0.0,
                             "DIFF": r["BEFORE"], "STATUS": "FAIL"})
        return val_rows, False

    mc_in_output = [c for c in month_cols if c in output_df.columns]
    output_df["TOTAL"] = output_df[mc_in_output].sum(axis=1)
    after = output_df.groupby(["STORE", "DEPARTMENT"])["TOTAL"].sum().reset_index()
    after.rename(columns={"TOTAL": "AFTER"}, inplace=True)

    merged = orig.merge(after, on=["STORE", "DEPARTMENT"], how="outer").fillna(0)
    merged["DIFF"]   = (merged["AFTER"] - merged["BEFORE"]).abs()
    merged["STATUS"] = merged["DIFF"].apply(lambda d: "PASS" if d <= tol else "FAIL")
    val_pass = bool((merged["STATUS"] == "PASS").all())
    return merged.to_dict("records"), val_pass


# ── Excel output builder ───────────────────────────────────────────────────────

def _build_excel(output_df, unmapped_df, val_rows, val_pass, log_lines, sales_df, month_cols) -> bytes:
    def fill(h): return PatternFill("solid", fgColor=h)
    def fnt(bold=False, color="E2EAED", size=9): return Font(name="Arial", bold=bold, color=color, size=size)
    def bdr():
        t = Side(style="thin", color="2D3B40")
        return Border(left=t, right=t, top=t, bottom=t)
    def aln(h="left"): return Alignment(horizontal=h, vertical="center")

    NAVY = "1F3864"; GREEN = "C6EFCE"; RED = "FF9999"; GREY = "2C3538"; DKGREY = "1C2022"

    def write_header(ws, cols, row=1):
        for ci, c in enumerate(cols, 1):
            cell = ws.cell(row=row, column=ci, value=c)
            cell.fill = fill(NAVY); cell.font = fnt(True, "FFFFFF", 10)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = bdr()
        ws.row_dimensions[row].height = 26

    def write_df(ws, df, title=""):
        if df.empty:
            ws.cell(1, 1, f"No data — {title}").font = fnt(False, "7FA0AD")
            return
        cols = list(df.columns)
        write_header(ws, cols)
        num_cols = {c for c in cols if pd.api.types.is_numeric_dtype(df[c])}
        for ri, (_, row) in enumerate(df.iterrows(), 2):
            bg = GREY if ri % 2 == 0 else DKGREY
            for ci, c in enumerate(cols, 1):
                v = row[c]
                cell = ws.cell(ri, ci, v)
                cell.fill = fill(bg); cell.font = fnt(); cell.border = bdr()
                cell.alignment = aln("right" if c in num_cols else "left")
                if c in num_cols and isinstance(v, (int, float)):
                    # full precision to 8 dp (was round(v, 2) - it undid the exact split in the file)
                    cell.value = round(float(v), 8) + 0.0
                    if c in ("MRP_CURRENT", "LISTED_MRP", "SHARE_PCT"):
                        cell.number_format = "#,##0"
                    else:
                        cell.number_format = "#,##0.00000000"
        ws.freeze_panes = "A2"
        if len(df) > 0:
            ws.auto_filter.ref = ws.dimensions
        for ci, c in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(ci)].width = min(28, max(10, len(c) + 4))

    wb = openpyxl.Workbook()

    ws1 = wb.active; ws1.title = "Reapportioned Sales"
    write_df(ws1, output_df if not output_df.empty else pd.DataFrame(), "Reapportioned Sales")

    ws2 = wb.create_sheet("Validation")
    ws2.cell(1, 1, "Validation — Store × Department Totals").font = fnt(True, "E2EAED", 12)
    ws2.cell(2, 1, f"Overall: {'PASSED' if val_pass else 'FAILED'}").font = \
        fnt(True, "006100" if val_pass else "9C0006", 11)
    write_header(ws2, ["STORE", "DEPARTMENT", "BEFORE", "AFTER", "DIFF", "STATUS"], row=4)
    for ri, r in enumerate(val_rows, 5):
        bg = GREEN if r["STATUS"] == "PASS" else RED
        for ci, (k, v) in enumerate(zip(
            ["STORE","DEPARTMENT","BEFORE","AFTER","DIFF","STATUS"],
            [r["STORE"],r["DEPARTMENT"],r["BEFORE"],r["AFTER"],r["DIFF"],r["STATUS"]]), 1):
            cell = ws2.cell(ri, ci, v)
            cell.fill = fill(bg); cell.font = fnt(r["STATUS"]!="PASS", "000000"); cell.border = bdr()
            cell.alignment = aln("right" if ci >= 3 else "left")
            if ci in (3,4,5) and isinstance(v, float): cell.number_format = "#,##0.00000000"

    ws3 = wb.create_sheet("Unmapped (Listed MRP 0)")
    write_df(ws3, unmapped_df if not unmapped_df.empty else pd.DataFrame(), "Unmapped Sales")

    ws4 = wb.create_sheet("Engine Log")
    ws4.column_dimensions["A"].width = 90
    ws4.cell(1, 1, f"Run: {datetime.datetime.now().strftime('%d-%b-%Y %H:%M:%S')}").font = fnt(False, "7FA0AD")
    for ri, line in enumerate(log_lines, 3):
        c = ws4.cell(ri, 1, line)
        if "FAIL" in line or "ERROR" in line: c.font = fnt(False, "9C0006")
        elif "PASS" in line: c.font = fnt(False, "006100")
        elif "WARN" in line: c.font = fnt(False, "9C6500")
        else: c.font = fnt(False, "E2EAED")

    ws5 = wb.create_sheet("Original Sales")
    write_df(ws5, sales_df, "Original Sales")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    sales_file   = _find_sales_file()
    mapping_file = _find_mapping_file()
    output_files = sorted(
        glob.glob(os.path.join(OUTPUT_DIR, "MRP Reapportioned*.xlsx")),
        key=os.path.getmtime, reverse=True
    )
    last_run = None
    if os.path.exists(LAST_RUN_JSON):
        try:
            with open(LAST_RUN_JSON) as f:
                last_run = json.load(f)
        except Exception:
            pass

    return {
        "sales_file_found":   sales_file is not None,
        "sales_file":         os.path.basename(sales_file) if sales_file else None,
        "mapping_file_found": mapping_file is not None,
        "mapping_file":       os.path.basename(mapping_file) if mapping_file else None,
        "output_found":       len(output_files) > 0,
        "last_output":        os.path.basename(output_files[0]) if output_files else None,
        "last_run":           last_run,
        "mapping_folder":     MAPPING_DIR,
    }


@router.get("/sales-status")
def get_sales_status():
    """The sales engine's file, the LY months read and the tie to the Calendar department snapshot."""
    try:
        f = _find_sales_file()
        _, month_cols, check = _engine_sales()
    except Exception as e:
        return {"file_found": False, "source": "Sales engine (data lake)", "error": str(e)}
    return {
        "file_found": True,
        "source":     "Sales engine (data lake)",
        "filename":   os.path.basename(f),
        "modified":   datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d %b %Y %H:%M"),
        "months":     month_cols,
        "check":      check,
    }


@router.get("/mrp-groups")
def get_mrp_groups():
    """Per Department x Display: the listed MRPs (old -> new) and, for each discontinued old MRP, the nearest listed
    new MRP below / above it (0 = none) plus how many sales rows sit on discontinued MRPs."""
    try:
        t = _targets(_load_mapping())
    except Exception as e:
        raise HTTPException(400, detail=str(e))

    disc_rows: dict = {}
    if _find_sales_file():
        try:
            sales_df, _, _ = _mapped_sales(t)
            hit = sales_df.rename(columns={"MRP": "MRP_CURRENT"}).merge(t[t["MRP_LISTED"] == 0][KEYS], on=KEYS)
            disc_rows = hit.groupby(["DEPARTMENT", "DISPLAY"]).size().to_dict()
        except Exception:
            pass

    result = []
    for (dept, display), g in t.groupby(["DEPARTMENT", "DISPLAY"]):
        on = g[g["MRP_LISTED"] > 0]
        off = g[g["MRP_LISTED"] == 0]
        result.append({
            "dept": dept, "display": display, "group_key": f"{dept}|{display}",
            "listed": [{"mrp": int(r.MRP_CURRENT), "listed": int(r.MRP_LISTED)} for r in on.itertuples()],
            "disc": [{"mrp": int(r.MRP_CURRENT), "below": int(r.BELOW), "above": int(r.ABOVE)} for r in off.itertuples()],
            "disc_rows_in_sales": int(disc_rows.get((dept, display), 0)),
        })
    return {"groups": result, "total_groups": len(result),
            "rule": {"lower_pct": LOWER_PCT, "lower_pct_default": LOWER_PCT_DEFAULT}}


@router.post("/run")
def run_engine(body: RunRequest):
    """Run re-apportionment by the master's nearest-listed-MRP rule (see module docstring)."""
    sales_path = _find_sales_file()
    if not sales_path:
        raise HTTPException(400, detail="Sales engine file not reachable")

    mapping_file = _find_mapping_file()
    if not mapping_file:
        raise HTTPException(400, detail=f"No mapping master found in: {MAPPING_DIR}")

    try:
        mapping_df = _load_mapping()
        sales_df, month_cols, check = _mapped_sales(mapping_df)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    if not check["pass"]:   # never re-apportion sales that don't tie to the sales engine's structure
        raise HTTPException(409, detail=f"Sales do not tie to the Calendar department sales (max diff {check['max_diff_lakh']} L)")

    try:
        output_df, unmapped_df, eng_log = _redistribute(sales_df, mapping_df, month_cols)
    except Exception as e:
        raise HTTPException(500, detail=f"Redistribution error: {e}")

    val_rows, val_pass = _validate(sales_df, output_df, month_cols, unmapped_df)

    total_before = round(float(sales_df[month_cols].sum().sum()), 8)
    total_after  = round(float(output_df[month_cols].sum().sum()), 8) if not output_df.empty else 0.0
    total_unmapped = round(float(unmapped_df[month_cols].sum().sum()), 8) if not unmapped_df.empty else 0.0

    full_log = [
        f"Sales       : sales engine {os.path.basename(sales_path)} (tie to Calendar dept sales: max {check['max_diff_lakh']} L)",
        f"Mapping file: {os.path.basename(mapping_file)}",
        f"Month cols  : {', '.join(month_cols)}",
        f"Input rows  : {len(sales_df):,}",
        f"Output rows : {len(output_df):,}",
        f"Unmapped    : {len(unmapped_df)} rows, {total_unmapped:,.2f}",
        f"Total before: {total_before:,.2f}",
        f"Total after : {total_after:,.2f}",
        f"Diff        : {abs(total_after + total_unmapped - total_before):.6f} (after + unmapped vs before)",
        f"Validation  : {'PASSED' if val_pass else 'FAILED'}",
        "---",
        *eng_log,
    ]

    ts_str = datetime.datetime.now().strftime("%d%b%Y_%H%M")
    out_filename = f"MRP Reapportioned {ts_str}.xlsx"
    out_path = os.path.join(OUTPUT_DIR, out_filename)
    xlsx_bytes = _build_excel(output_df, unmapped_df, val_rows, val_pass, full_log, sales_df, month_cols)
    with open(out_path, "wb") as f:
        f.write(xlsx_bytes)

    preview = []
    if not output_df.empty:
        sort_cols = ["STORE", "DEPARTMENT", "DISPLAY", "ATTRIBUTE", "LISTED_MRP"]
        sc = [c for c in sort_cols if c in output_df.columns]
        preview_df = output_df.sort_values(sc).head(50)
        preview = preview_df.round(2).to_dict("records")

    run_meta = {
        "run_at":      datetime.datetime.now().isoformat(),
        "sales_file":  os.path.basename(sales_path),
        "sales_check": check,
        "input_rows":  len(sales_df),
        "output_rows": len(output_df),
        "unmapped":    len(unmapped_df),
        "total_before": total_before,
        "total_after":  total_after,
        "val_pass":     val_pass,
        "output_file":  out_filename,
        "stores":       int(sales_df["STORE"].nunique()),
        "departments":  int(sales_df["DEPARTMENT"].nunique()),
        "month_cols":   month_cols,
    }
    save_json(LAST_RUN_JSON, run_meta, indent=2)

    return {
        "ok":           True,
        "input_rows":   len(sales_df),
        "output_rows":  len(output_df),
        "unmapped":     len(unmapped_df),
        "total_before": total_before,
        "total_after":  total_after,
        "total_unmapped": total_unmapped,
        "diff":         round(abs(total_after + total_unmapped - total_before), 8),
        "val_pass":     val_pass,
        "val_rows":     val_rows,
        "output_file":  out_filename,
        "log":          full_log,
        "preview":      preview,
        "month_cols":   month_cols,
    }


@router.get("/download")
def download_latest():
    files = sorted(
        glob.glob(os.path.join(OUTPUT_DIR, "MRP Reapportioned*.xlsx")),
        key=os.path.getmtime, reverse=True
    )
    if not files:
        raise HTTPException(404, detail="No output file found. Run the engine first.")
    path = files[0]
    with open(path, "rb") as f:
        data = f.read()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={os.path.basename(path)}"},
    )
