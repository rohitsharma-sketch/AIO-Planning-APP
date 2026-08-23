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

Source files (server-side):
  Sales:       MRP Merging Engine/Sales Reapportionment/Historical Sales/  (.xlsb/.xlsx/.csv)
  MRP Mapping: MRP Merging Engine/Sales Reapportionment/MRP Mapping/MRP Mapping Master.xlsx

Endpoints:
  GET  /status           → file presence, last-run metadata
  GET  /sales-status     → sales file info (name, size, modified)
  GET  /mrp-groups       → groups (Dept, Display, Attr) with valid + discontinued MRPs
  POST /run              → redistribution with user-provided cont_pcts
  GET  /download         → latest output Excel
  GET  /template         → blank sales template
"""

import os
import io
import glob
import json
import warnings
import datetime
from typing import Optional, Dict, List

import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

warnings.filterwarnings("ignore")

router = APIRouter()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE         = r"C:\Users\A9820\Documents\CLaude - New Projects"
SALES_DIR    = os.path.join(BASE, r"MRP Merging Engine\Sales Reapportionment\Historical Sales")
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


def _find_sales_file() -> Optional[str]:
    files = []
    for pat in ("*.xlsb", "*.xlsx", "*.xls", "*.csv"):
        files.extend(glob.glob(os.path.join(SALES_DIR, pat)))
    files = [f for f in files if "template" not in os.path.basename(f).lower()]
    return max(files, key=os.path.getmtime) if files else None


def _find_mapping_file() -> Optional[str]:
    files = []
    for pat in ("*.xlsx", "*.xls"):
        files.extend(glob.glob(os.path.join(MAPPING_DIR, pat)))
    return max(files, key=os.path.getmtime) if files else None


def _excel_serial_to_month(serial) -> Optional[str]:
    """Convert Excel date serial to month name like 'Mar 2026'."""
    try:
        s = int(float(serial))
        # Excel serial: days since 1900-01-00 (with 1900 leap year bug)
        import datetime as _dt
        d = _dt.date(1899, 12, 30) + _dt.timedelta(days=s)
        return d.strftime("%b %Y")
    except Exception:
        return None


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


def _load_sales(path: str) -> tuple[pd.DataFrame, list[str]]:
    """Load sales file (.xlsb / .xlsx / .csv).
    Returns (df, month_cols) where month_cols is the list of month column names.
    df always has: STORE, DIVISION, DEPARTMENT, MRP, DISPLAY, ATTRIBUTE
    then month_cols columns each containing numeric sales.
    """
    if path.endswith(".xlsb"):
        try:
            import pyxlsb
        except ImportError:
            raise ValueError("pyxlsb not installed. Run: pip install pyxlsb")
        rows = []
        with pyxlsb.open_workbook(path) as wb:
            with wb.get_sheet(1) as ws:
                all_rows = list(ws.rows())
        headers = [str(c.v).strip() if c.v is not None else "" for c in all_rows[0]]
        for row in all_rows[1:]:
            rows.append([c.v for c in row])
        df = pd.DataFrame(rows, columns=headers)
    elif path.endswith(".csv"):
        df = pd.read_csv(path)
    else:
        df = pd.read_excel(path)

    df = _norm_cols(df)

    # Map column names
    rename = {}
    for c in df.columns:
        cu = c.upper()
        if cu in ("STORE_NAME", "STORE", "STORE_CODE", "STORE_ID"): rename[c] = "STORE"
        elif cu in ("DIVISION", "DIV"):                              rename[c] = "DIVISION"
        elif cu in ("DEPARTMENT", "DEPT"):                           rename[c] = "DEPARTMENT"
        elif cu in ("MRP", "EXISTING_MRP", "CURRENT_MRP",
                    "OLD_MRP", "RAW_MRP"):                           rename[c] = "MRP"
        elif cu in ("DISPLAY_TYPE", "DISPLAY", "SECTION",
                    "DISPLAY_TYPE"):                                  rename[c] = "DISPLAY"
        elif cu in ("ATTRIBUTE", "ATTRIBUTE1", "ATTRIBUTE_1",
                    "ATTR"):                                          rename[c] = "ATTRIBUTE"
        elif cu in ("SALES", "SALES_VALUE", "AMOUNT",
                    "NET_SALES", "REVENUE"):                          rename[c] = "SALES"
    df.rename(columns=rename, inplace=True)

    # Detect month / sales columns — numeric columns that aren't key columns
    key_cols = {"STORE", "DIVISION", "DEPARTMENT", "MRP", "DISPLAY", "ATTRIBUTE"}
    # Excel date serials or string month names in non-key columns
    month_cols = []
    for c in df.columns:
        if c in key_cols:
            continue
        if c == "SALES":
            continue
        # Try parsing as numeric (date serial or sales)
        vals = pd.to_numeric(df[c], errors="coerce")
        if vals.notna().sum() > len(df) * 0.5:
            # Rename if it's an Excel serial
            try:
                serial = float(c)
                month_label = _excel_serial_to_month(serial)
                if month_label:
                    df.rename(columns={c: month_label}, inplace=True)
                    month_cols.append(month_label)
                else:
                    month_cols.append(c)
            except (ValueError, TypeError):
                month_cols.append(c)

    # If no month cols found, check for single SALES column
    if not month_cols and "SALES" in df.columns:
        month_cols = ["SALES"]

    if not month_cols:
        raise ValueError("Could not detect sales columns. Expected month columns or a SALES column.")

    # Ensure required key columns exist
    for req in ["STORE", "DEPARTMENT", "MRP"]:
        if req not in df.columns:
            raise ValueError(f"Missing required column: {req}")

    for c in ["STORE", "DEPARTMENT", "DIVISION"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip().str.upper()
    if "DISPLAY" in df.columns:
        df["DISPLAY"] = df["DISPLAY"].astype(str).str.strip().str.upper()
    if "ATTRIBUTE" in df.columns:
        df["ATTRIBUTE"] = df["ATTRIBUTE"].astype(str).str.strip().str.upper()

    df["MRP"] = pd.to_numeric(df["MRP"], errors="coerce").fillna(0).astype(int)

    for mc in month_cols:
        df[mc] = pd.to_numeric(df[mc], errors="coerce").fillna(0)

    # Ensure DISPLAY and ATTRIBUTE exist
    if "DISPLAY" not in df.columns:
        df["DISPLAY"] = "ALL"
    if "ATTRIBUTE" not in df.columns:
        df["ATTRIBUTE"] = "ALL"
    if "DIVISION" not in df.columns:
        df["DIVISION"] = ""

    return df, month_cols


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
    n = len(valid_mrps)
    if n == 0:
        return []
    base = round(100.0 / n, 4)
    pcts = [base] * (n - 1)
    pcts.append(round(100.0 - sum(pcts), 4))
    return pcts


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

            allocated = 0.0
            for i, (mrp_valid, pct) in enumerate(splits):
                frac = pct / total_pct
                alloc = round(total - allocated, 6) if i == len(splits) - 1 else round(total * frac, 6)
                if i < len(splits) - 1:
                    allocated += alloc
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
    tol = 0.01
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
                    cell.value = round(float(v), 2)
                    if c in ("MRP_CURRENT", "LISTED_MRP"):
                        cell.number_format = "#,##0"
                    else:
                        cell.number_format = "#,##0.00"
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
            if ci in (3,4,5) and isinstance(v, float): cell.number_format = "#,##0.00"

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


def _build_template() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Historical Sales"

    def fill(h): return PatternFill("solid", fgColor=h)
    def fnt(bold=False, color="E2EAED", size=9): return Font(name="Arial", bold=bold, color=color, size=size)
    def bdr():
        t = Side(style="thin", color="2D3B40")
        return Border(left=t, right=t, top=t, bottom=t)

    headers = ["STORE_NAME", "DIVISION", "DEPARTMENT", "MRP", "DISPLAY_TYPE", "ATTRIBUTE",
               "Mar 2026", "Apr 2026", "May 2026", "Jun 2026"]
    widths  = [16, 12, 24, 10, 14, 14, 12, 12, 12, 12]
    for ci, h in enumerate(headers, 1):
        c = ws.cell(1, ci, h)
        c.fill = fill("1F3864"); c.font = fnt(True, "FFFFFF", 10)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = bdr()

    examples = [
        ["STORE_A", "KIDS", "KB_BERMUDA", 299, "NON_TABLE", "SUMMER", 43320, 32275, 16409, 26714],
        ["STORE_A", "KIDS", "KB_BERMUDA", 399, "NON_TABLE", "SUMMER", 37483, 31398, 17436, 19811],
    ]
    for ri, row in enumerate(examples, 2):
        for ci, v in enumerate(row, 1):
            c = ws.cell(ri, ci, v)
            c.fill = fill("FFEB9C"); c.font = fnt(False, "7D4E00"); c.border = bdr()
            c.alignment = Alignment(horizontal="right" if ci >= 4 else "left", vertical="center")

    ws.cell(5, 1, "Yellow rows = example data. Delete before use. Month columns can be named anything — engine auto-detects numeric columns.").font = fnt(False, "7FA0AD")

    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"

    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


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
        "sales_folder":       SALES_DIR,
        "mapping_folder":     MAPPING_DIR,
    }


@router.get("/sales-status")
def get_sales_status():
    f = _find_sales_file()
    if not f:
        return {"file_found": False, "folder": SALES_DIR}
    mtime = os.path.getmtime(f)
    return {
        "file_found": True,
        "filename":   os.path.basename(f),
        "folder":     SALES_DIR,
        "modified":   datetime.datetime.fromtimestamp(mtime).strftime("%d %b %Y %H:%M"),
        "size_kb":    round(os.path.getsize(f) / 1024, 1),
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
    sales_path = _find_sales_file()
    if sales_path:
        try:
            sales_df, month_cols = _load_sales(sales_path)
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
        raise HTTPException(400, detail=f"No sales file found in: {SALES_DIR}")

    mapping_file = _find_mapping_file()
    if not mapping_file:
        raise HTTPException(400, detail=f"No mapping master found in: {MAPPING_DIR}")

    try:
        mapping_df          = _load_mapping()
        sales_df, month_cols = _load_sales(sales_path)
    except Exception as e:
        raise HTTPException(400, detail=str(e))

    try:
        output_df, unmapped_df, eng_log = _redistribute(
            sales_df, mapping_df, month_cols, body.cont_pcts
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Redistribution error: {e}")

    val_rows, val_pass = _validate(sales_df, output_df, month_cols)

    total_before = round(float(sales_df[month_cols].sum().sum()), 2)
    total_after  = round(float(output_df[month_cols].sum().sum()), 2) if not output_df.empty else 0.0

    full_log = [
        f"Sales file  : {os.path.basename(sales_path)}",
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
        "diff":         round(abs(total_after - total_before), 6),
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


@router.get("/template")
def download_template():
    data = _build_template()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Historical_Sales_Template.xlsx"},
    )
