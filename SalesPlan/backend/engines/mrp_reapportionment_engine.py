"""
MRP Re-apportionment Engine — FastAPI Router v2
================================================
Redistributes historical sales from discontinued MRP slabs to valid (listed) MRP slabs.

Logic:
  - MRP master defines per (Dept, Display, Attribute): which MRP slabs are valid (MRP_LISTED != 0)
    and which are discontinued (MRP_LISTED = 0).
  - Sales at a discontinued MRP slab are split across the valid MRP slabs for that group,
    using contribution %s defined by the user.
  - Sales at a valid MRP slab pass through unchanged.
  - Totals are preserved exactly per Store × Dept × Display × Attribute × Month.

Sources:
  Sales:       the suite's sales engine (user, 2026-09-29: "LY actual sales will be taken from the sales engine
               which is embedded in all the other apps, only the new MRP structure will be given") - the Calendar
               engine's month-wise data-lake file, read with its own reader, LY Mar-Jun 2026, and checked cell by
               cell against the Calendar department snapshot (store x department x month) Sales Plan reads.
  MRP Mapping: MRP Merging Engine/Sales Reapportionment/MRP Mapping/MRP Mapping Master.xlsx (the only upload)

Endpoints:
  GET  /status           → file presence, last-run metadata
  GET  /sales-status     → sales engine file, LY months, tie to Calendar dept sales
  GET  /mrp-groups       → groups (Dept, Display, Attr) with valid + discontinued MRPs
  POST /run              → redistribution with user-provided cont_pcts
  GET  /download         → latest output Excel
"""

import os
import io
import glob
import json
import warnings
import datetime
from typing import Optional, Dict, List

import sys
import pandas as pd
import openpyxl
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import SHOWN, shares_pct, split  # noqa: E402
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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

class MrpSplit(BaseModel):
    mrp: int
    pct: float

class RunRequest(BaseModel):
    # cont_pcts: group_key → list of {mrp, pct}
    # group_key = "DEPARTMENT|DISPLAY|ATTRIBUTE"
    cont_pcts: Optional[Dict[str, List[MrpSplit]]] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip().upper().replace(" ", "_").replace("-", "_") for c in df.columns]
    return df


# LY months = the plan's LY (Mar-Jun 2026, as BIS / AOP); labels as the old sales template ("Mar 2026").
LY_MONTHS = ["2026-03", "2026-04", "2026-05", "2026-06"]
_SALES_CACHE: dict = {}   # {"key": (path, mtime), "df", "month_cols", "check"}


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
    if _SALES_CACHE.get("key") != key:
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
    return _SALES_CACHE["df"].copy(), list(_SALES_CACHE["month_cols"]), _SALES_CACHE["check"]


def _mapped_sales(mapping_df: pd.DataFrame) -> tuple:
    """Engine sales of the departments the MRP structure covers (the rest of the business is not re-apportioned)."""
    df, month_cols, check = _engine_sales()
    return df[df["DEPARTMENT"].isin(set(mapping_df["DEPARTMENT"]))].reset_index(drop=True), month_cols, check


def _find_mapping_file() -> Optional[str]:
    files = []
    for pat in ("*.xlsx", "*.xls"):
        files.extend(glob.glob(os.path.join(MAPPING_DIR, pat)))
    return max(files, key=os.path.getmtime) if files else None


def _load_mapping() -> pd.DataFrame:
    """Load MRP Mapping Master. Returns DataFrame with cols:
    DEPARTMENT, DISPLAY, MRP_CURRENT, MRP_LISTED, ATTRIBUTE_1
    """
    path = _find_mapping_file()
    if not path:
        raise ValueError(f"No mapping file found in: {MAPPING_DIR}")

    df = pd.read_excel(path)
    df = _norm_cols(df)

    # Flexible column detection
    rename = {}
    for c in df.columns:
        cu = c.upper()
        if cu in ("DEPARTMENT", "DEPT"):               rename[c] = "DEPARTMENT"
        elif cu in ("DISPLAY", "DISPLAY_TYPE"):        rename[c] = "DISPLAY"
        elif cu in ("MRP_CURRENT", "CURRENT_MRP",
                    "MRP", "RAW_MRP", "OLD_MRP"):      rename[c] = "MRP_CURRENT"
        elif cu in ("MRP_LISTED", "LISTED_MRP",
                    "NEW_MRP", "FINAL_MRP"):            rename[c] = "MRP_LISTED"
        elif cu in ("ATTRIBUTE_1", "ATTRIBUTE1",
                    "ATTRIBUTE", "ATTR"):               rename[c] = "ATTRIBUTE"
    df.rename(columns=rename, inplace=True)

    required = ["DEPARTMENT", "DISPLAY", "MRP_CURRENT", "MRP_LISTED"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"MRP Mapping Master missing columns: {missing}")

    for c in ["DEPARTMENT", "DISPLAY"]:
        df[c] = df[c].astype(str).str.strip().str.upper()
    if "ATTRIBUTE" in df.columns:
        df["ATTRIBUTE"] = df["ATTRIBUTE"].astype(str).str.strip().str.upper()
    else:
        df["ATTRIBUTE"] = "ALL"

    df["MRP_CURRENT"] = pd.to_numeric(df["MRP_CURRENT"], errors="coerce").fillna(0).astype(int)
    df["MRP_LISTED"]  = pd.to_numeric(df["MRP_LISTED"],  errors="coerce").fillna(0).astype(int)
    return df.dropna(subset=["DEPARTMENT"])


def _build_groups(mapping_df: pd.DataFrame) -> dict:
    """Build group structure: {(dept, display, attr): {valid: [...], disc: [...]}}"""
    groups = {}
    for _, row in mapping_df.iterrows():
        key = (row["DEPARTMENT"], row["DISPLAY"], row["ATTRIBUTE"])
        if key not in groups:
            groups[key] = {"valid": [], "discontinued": []}
        if row["MRP_LISTED"] != 0:
            groups[key]["valid"].append(int(row["MRP_LISTED"]))
        else:
            groups[key]["discontinued"].append(int(row["MRP_CURRENT"]))
    return groups


def _default_cont_pcts(valid_mrps: list) -> list:
    """Equal split across valid MRPs."""
    eq = shares_pct({i: 1.0 for i in range(len(valid_mrps))})   # adds to exactly 100
    return [eq[i] for i in range(len(valid_mrps))]


def _redistribute(sales_df: pd.DataFrame, mapping_df: pd.DataFrame,
                  month_cols: list, cont_pcts_input: Optional[dict]) -> tuple:
    """
    Main redistribution.
    cont_pcts_input: dict of "DEPT|DISPLAY|ATTR" → [{mrp, pct}, ...]
                     if None, use equal split for all groups.
    Returns (output_df, unmapped_df, log_lines)
    """
    log = []
    groups = _build_groups(mapping_df)

    # Build fast lookup: (dept, display, attr, mrp) → mrp_listed (0 if discontinued)
    master_map: dict = {}
    for _, row in mapping_df.iterrows():
        master_map[(row["DEPARTMENT"], row["DISPLAY"], row["ATTRIBUTE"], int(row["MRP_CURRENT"]))] = int(row["MRP_LISTED"])

    # Parse user cont_pcts into dict: (dept, display, attr) → [(mrp, pct), ...]
    user_splits: dict = {}
    if cont_pcts_input:
        for group_key, splits in cont_pcts_input.items():
            parts = group_key.split("|")
            if len(parts) == 3:
                k = (parts[0].upper(), parts[1].upper(), parts[2].upper())
                user_splits[k] = [(int(s.mrp), float(s.pct)) for s in splits]

    out_rows = []
    unmapped_rows = []
    warn_counts: dict = {}

    for _, row in sales_df.iterrows():
        store = row["STORE"]
        dept  = row["DEPARTMENT"]
        disp  = row["DISPLAY"]
        attr  = row["ATTRIBUTE"]
        mrp   = int(row["MRP"])
        div   = row.get("DIVISION", "")
        month_vals = {mc: row[mc] for mc in month_cols}

        # Skip fully zero rows
        if all(v == 0 for v in month_vals.values()):
            continue

        # Check master
        lookup_key = (dept, disp, attr, mrp)
        mrp_listed = master_map.get(lookup_key)

        if mrp_listed is None:
            # Not in master at all
            reason = "MRP combination not in mapping master"
            unmapped_rows.append({
                "STORE": store, "DEPARTMENT": dept, "DISPLAY": disp,
                "ATTRIBUTE": attr, "MRP_CURRENT": mrp, "LISTED_MRP": 0,
                **month_vals, "REASON": reason
            })
            wk = (dept, disp, attr)
            warn_counts[wk] = warn_counts.get(wk, 0) + 1
            continue

        if mrp_listed != 0:
            # Valid MRP → pass through
            out_rows.append({
                "STORE": store, "DIVISION": div, "DEPARTMENT": dept,
                "DISPLAY": disp, "ATTRIBUTE": attr,
                "MRP_CURRENT": mrp, "LISTED_MRP": mrp_listed,
                **month_vals
            })
            continue

        # Discontinued MRP → redistribute across valid MRPs in this group
        group_key = (dept, disp, attr)
        group = groups.get(group_key, {"valid": [], "discontinued": []})
        valid_mrps = sorted(set(group["valid"]))

        if not valid_mrps:
            # No valid MRPs in this group
            unmapped_rows.append({
                "STORE": store, "DEPARTMENT": dept, "DISPLAY": disp,
                "ATTRIBUTE": attr, "MRP_CURRENT": mrp, "LISTED_MRP": 0,
                **month_vals, "REASON": "No valid MRPs in group"
            })
            continue

        # Get contribution %s
        if group_key in user_splits:
            splits = [(m, p) for m, p in user_splits[group_key] if m in valid_mrps]
            if not splits:
                splits = list(zip(valid_mrps, _default_cont_pcts(valid_mrps)))
        else:
            splits = list(zip(valid_mrps, _default_cont_pcts(valid_mrps)))

        total_pct = sum(p for _, p in splits)
        if total_pct == 0:
            total_pct = 100
            splits = list(zip(valid_mrps, _default_cont_pcts(valid_mrps)))

        # Redistribute each month independently, last row absorbs rounding residual
        for mc in month_cols:
            total = month_vals[mc]
            if total == 0:
                for mrp_valid, _ in splits:
                    out_rows.append({
                        "STORE": store, "DIVISION": div, "DEPARTMENT": dept,
                        "DISPLAY": disp, "ATTRIBUTE": attr,
                        "MRP_CURRENT": mrp, "LISTED_MRP": mrp_valid,
                        **{m: (0 if m != mc else 0) for m in month_cols}
                    })
                # Actually don't emit zero-sales rows — skip
                continue

            # the month's total split by the shares at full precision; the remainder lands on the largest part, so
            # the valid MRPs add back to it exactly (was rounded to 6 dp, last row plugged)
            parts = split(total, {i: pct for i, (_, pct) in enumerate(splits)})
            for i, (mrp_valid, pct) in enumerate(splits):
                alloc = parts[i]
                # Build month dict for this row (all months 0 except the current one)
                mc_vals = {m: 0.0 for m in month_cols}
                mc_vals[mc] = alloc
                out_rows.append({
                    "STORE": store, "DIVISION": div, "DEPARTMENT": dept,
                    "DISPLAY": disp, "ATTRIBUTE": attr,
                    "MRP_CURRENT": mrp, "LISTED_MRP": mrp_valid,
                    **mc_vals
                })

    for (dept, disp, attr), cnt in warn_counts.items():
        log.append(f"WARN: {cnt} rows unmapped in [{dept} | {disp} | {attr}]")

    output_df   = pd.DataFrame(out_rows) if out_rows else pd.DataFrame()
    unmapped_df = pd.DataFrame(unmapped_rows) if unmapped_rows else pd.DataFrame()

    # Consolidate: group by key columns and sum month cols
    if not output_df.empty:
        key_cols = ["STORE", "DIVISION", "DEPARTMENT", "DISPLAY", "ATTRIBUTE", "MRP_CURRENT", "LISTED_MRP"]
        output_df = output_df.groupby(key_cols, dropna=False)[month_cols].sum().reset_index()

    log.append(f"Output rows: {len(output_df)}")
    log.append(f"Unmapped rows: {len(unmapped_df)}")

    return output_df, unmapped_df, log


def _validate(sales_df: pd.DataFrame, output_df: pd.DataFrame,
              month_cols: list) -> tuple[list[dict], bool]:
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
                    if c in ("MRP_CURRENT", "LISTED_MRP"):
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
    """
    Load the MRP Mapping Master and optionally overlay sales impact from the sales file.
    Returns groups: [{dept, display, attr, valid_mrps, discontinued_mrps, disc_sales_count}]
    """
    try:
        mapping_df = _load_mapping()
    except Exception as e:
        raise HTTPException(400, detail=str(e))

    groups = _build_groups(mapping_df)

    # Try to overlay sales counts
    sales_counts: dict = {}
    if _find_sales_file():
        try:
            sales_df, month_cols, _ = _mapped_sales(mapping_df)
            disc_lookup = set()
            for _, row in mapping_df[mapping_df["MRP_LISTED"] == 0].iterrows():
                disc_lookup.add((row["DEPARTMENT"], row["DISPLAY"], row["ATTRIBUTE"], int(row["MRP_CURRENT"])))

            for _, row in sales_df.iterrows():
                key = (row["DEPARTMENT"], row["DISPLAY"], row["ATTRIBUTE"], int(row["MRP"]))
                if key in disc_lookup:
                    gk = (row["DEPARTMENT"], row["DISPLAY"], row["ATTRIBUTE"])
                    sales_counts[gk] = sales_counts.get(gk, 0) + 1
        except Exception:
            pass

    result = []
    for (dept, display, attr), grp in sorted(groups.items()):
        valid_mrps = sorted(set(grp["valid"]))
        disc_mrps  = sorted(set(grp["discontinued"]))
        if not disc_mrps and not valid_mrps:
            continue
        default_pcts = _default_cont_pcts(valid_mrps)
        result.append({
            "dept":           dept,
            "display":        display,
            "attr":           attr,
            "group_key":      f"{dept}|{display}|{attr}",
            "valid_mrps":     valid_mrps,
            "disc_mrps":      disc_mrps,
            "disc_rows_in_sales": sales_counts.get((dept, display, attr), 0),
            "default_pcts":   default_pcts,
        })

    return {"groups": result, "total_groups": len(result)}


@router.post("/run")
def run_engine(body: RunRequest):
    """
    Run re-apportionment. body.cont_pcts = {group_key: [{mrp, pct}, ...]}
    If cont_pcts is None or empty, equal split is used for all groups.
    """
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
        output_df, unmapped_df, eng_log = _redistribute(
            sales_df, mapping_df, month_cols, body.cont_pcts
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Redistribution error: {e}")

    val_rows, val_pass = _validate(sales_df, output_df, month_cols)

    total_before = round(float(sales_df[month_cols].sum().sum()), 8)
    total_after  = round(float(output_df[month_cols].sum().sum()), 8) if not output_df.empty else 0.0

    full_log = [
        f"Sales       : sales engine {os.path.basename(sales_path)} (tie to Calendar dept sales: max {check['max_diff_lakh']} L)",
        f"Mapping file: {os.path.basename(mapping_file)}",
        f"Month cols  : {', '.join(month_cols)}",
        f"Input rows  : {len(sales_df):,}",
        f"Output rows : {len(output_df):,}",
        f"Unmapped    : {len(unmapped_df)}",
        f"Total before: {total_before:,.2f}",
        f"Total after : {total_after:,.2f}",
        f"Diff        : {abs(total_after - total_before):.6f}",
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
    with open(LAST_RUN_JSON, "w") as f:
        json.dump(run_meta, f, indent=2)

    return {
        "ok":           True,
        "input_rows":   len(sales_df),
        "output_rows":  len(output_df),
        "unmapped":     len(unmapped_df),
        "total_before": total_before,
        "total_after":  total_after,
        "diff":         round(abs(total_after - total_before), 8),
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
