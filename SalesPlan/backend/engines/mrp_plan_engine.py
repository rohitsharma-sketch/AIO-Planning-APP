"""
MRP Plan Engine
---------------
Stores per-dept MRP price points with buyer-supplied contribution % per P1/P2 period.
Splits the final dept plan TY (ty_p1/ty_p2) by those period contributions.

Data file: mrp_plan.json
  {division: {dept: {mrp_str: {period: contrib_pct}}}}
  e.g. {"KIDS": {"KB_BERMUDA": {"299": {"Mar'27 P1": 40.0, "Mar'27 P2": 42.0}}}}

Expected upload columns:
  Division | Department | MRP | Mar'27 P1 | Mar'27 P2 | Apr'27 P1 | Apr'27 P2 | ...
  Contribution % per dept per period must sum to 100 across its MRP bands.
"""

import os, json, io, sys
from fastapi import APIRouter, UploadFile, File, HTTPException
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import split  # noqa: E402
from fastapi.responses import StreamingResponse

router = APIRouter()

DATA_PATH = os.path.join(os.path.dirname(__file__), "mrp_plan.json")

TY_MONTHS = [
    "Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
    "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"
]
# Periods: each month has P1 and P2
TY_PERIODS = [f"{m} P{p}" for m in TY_MONTHS for p in (1, 2)]
TY_PERIOD_SET = set(TY_PERIODS)

_COL_ALIASES = {
    "division":   ["division", "div", "divison", "division name"],
    "department": ["department", "dept", "department name"],
    "mrp":        ["mrp", "price", "price point", "mrp value", "final mrp", "mrp value"],
}

# Normalize month name variants in period headers
_MONTH_NORM = {
    "jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr",
    "may": "May", "jun": "Jun", "june": "Jun", "jul": "Jul",
    "aug": "Aug", "sep": "Sep", "sept": "Sep", "oct": "Oct",
    "nov": "Nov", "dec": "Dec",
}

def _normalize_period_header(h: str) -> str:
    """Normalize 'June\\'27 P1 %' → 'Jun\\'27 P1', strip trailing % etc."""
    import re
    h = h.strip().rstrip("%").strip()
    # Match pattern like "Jun'27 P1" or "June'27 P1 %"
    m = re.match(r"([A-Za-z]+)'(\d+)\s+(P[12])$", h, re.IGNORECASE)
    if m:
        mon, yr, period = m.group(1), m.group(2), m.group(3).upper()
        mon_norm = _MONTH_NORM.get(mon.lower(), mon.capitalize())
        return f"{mon_norm}'{yr} {period}"
    return h


def _load() -> dict:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH) as f:
            return json.load(f)
    return {}


def _save(data: dict):
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _resolve_col(headers: list, key: str) -> str | None:
    aliases = _COL_ALIASES[key]
    for h in headers:
        if h.strip().lower() in aliases:
            return h
    return None


def _load_dept_plan() -> dict:
    for fname in ["base_corrected_plan.json", "attr_corrected_plan.json", "final_dept_plan.json"]:
        # the plan files live in backend/, one level up, like every other engine reads them (2026-09-30: this looked in
        # engines/, found nothing, and every MRP band showed 0)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", fname)
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def _parse_upload(contents: bytes, filename: str):
    """
    Parse upload → (data_dict, month_cols, errors, warnings)
    data_dict: {div: {dept: {mrp_str: {month: contrib_pct}}}}
    """
    errors = []

    if filename.lower().endswith(".csv"):
        import csv
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig")))
        raw_rows = list(reader)
        headers = list(reader.fieldnames or [])
    else:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
            ws = wb.active
            data = list(ws.values)
            if not data:
                return {}, [], ["File is empty"], []
            # Find first non-blank row as the header row (handles leading blank rows)
            header_idx = 0
            for i, row in enumerate(data):
                if any(c is not None and str(c).strip() for c in row):
                    header_idx = i
                    break
            headers = [str(h).strip() if h is not None else "" for h in data[header_idx]]
            raw_rows = [
                dict(zip(headers, [str(c).strip() if c is not None else "" for c in row]))
                for row in data[header_idx + 1:]
            ]
        except Exception as e:
            return {}, [], [f"Could not read Excel file: {e}"], []

    # Normalize period headers in-place (strip trailing %, fix June→Jun, etc.)
    normalized_headers = [_normalize_period_header(h) if h else h for h in headers]
    if normalized_headers != headers:
        # Rebuild raw_rows with normalized keys
        key_map = {old: new for old, new in zip(headers, normalized_headers) if old != new}
        raw_rows = [{key_map.get(k, k): v for k, v in row.items()} for row in raw_rows]
        headers = normalized_headers

    c_div  = _resolve_col(headers, "division")
    c_dept = _resolve_col(headers, "department")
    c_mrp  = _resolve_col(headers, "mrp")

    missing = [k for k, v in {"Division": c_div, "Department": c_dept, "MRP": c_mrp}.items() if v is None]
    if missing:
        return {}, [], [f"Missing required columns: {', '.join(missing)}. Found: {', '.join(headers)}"], []

    # Detect period columns — anything that matches TY_PERIOD_SET (e.g. "Mar'27 P1")
    period_cols = [h for h in headers if h.strip() in TY_PERIOD_SET]
    if not period_cols:
        return {}, [], [
            f"No period columns found. Expected headers like: {', '.join(TY_PERIODS[:4])}, … "
            f"(Each month needs P1 and P2, e.g. \"Mar'27 P1\", \"Mar'27 P2\") "
            f"Found non-key headers: {[h for h in headers if h not in (c_div, c_dept, c_mrp)]}"
        ], []

    data_out: dict = {}
    row_errors = []

    for i, row in enumerate(raw_rows, start=2):
        div  = str(row.get(c_div,  "") or "").strip().upper()
        dept = str(row.get(c_dept, "") or "").strip()
        mrp_raw = str(row.get(c_mrp, "") or "").strip()

        if not div or not dept or not mrp_raw:
            continue

        try:
            mrp_val = float(mrp_raw.replace(",", ""))
        except ValueError:
            row_errors.append(f"Row {i}: non-numeric MRP ({mrp_raw!r})")
            continue

        mrp_key = str(int(mrp_val)) if mrp_val == int(mrp_val) else str(mrp_val)
        period_data = {}

        for p in period_cols:
            raw = str(row.get(p, "") or "").strip().replace("%", "").replace(",", "")
            if raw == "" or raw == "-":
                continue
            try:
                period_data[p] = float(raw)
            except ValueError:
                row_errors.append(f"Row {i} ({dept} MRP {mrp_key}, {p}): non-numeric value ({raw!r})")

        if not period_data:
            continue

        data_out.setdefault(div, {}).setdefault(dept, {})[mrp_key] = period_data

    # Contrib warnings: per (div, dept, period) sum should be 100
    from collections import defaultdict
    period_sums: dict = defaultdict(lambda: defaultdict(float))
    for div, depts in data_out.items():
        for dept, bands in depts.items():
            for mrp_key, period_vals in bands.items():
                for p, pct in period_vals.items():
                    period_sums[(div, dept)][p] += pct

    warnings = []
    for (div, dept), psums in period_sums.items():
        for p, total in psums.items():
            if abs(total - 100) > 0.5:
                warnings.append(f"{div} / {dept} / {p}: contribution sums to {total:.1f}% (expected 100%)")

    return data_out, period_cols, row_errors, warnings


# Folder that the buyer drops the MRP contribution file into
MRP_SOURCE_DIR  = r"C:\Users\A9820\Documents\CLaude - New Projects\SalesPlan\MRP Cont %"
MRP_SOURCE_NAME = "MRP Cont %.xlsx"
MRP_SOURCE_PATH = os.path.join(MRP_SOURCE_DIR, MRP_SOURCE_NAME)


def _import_from_disk():
    """Read the MRP file directly from the well-known source folder."""
    if not os.path.exists(MRP_SOURCE_PATH):
        raise HTTPException(
            status_code=404,
            detail=f"Source file not found: {MRP_SOURCE_PATH}. Drop the file into the MRP Cont % folder and try again.",
        )
    with open(MRP_SOURCE_PATH, "rb") as f:
        contents = f.read()
    return _parse_upload(contents, MRP_SOURCE_NAME)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/sync")
def sync_mrp():
    """Import MRP data directly from the well-known source folder on disk."""
    data, period_cols, errors, warnings = _import_from_disk()

    if errors and not data:
        raise HTTPException(status_code=400, detail=errors[0])

    _save(data)

    dept_count = sum(len(depts) for depts in data.values())
    band_count = sum(len(bands) for depts in data.values() for bands in depts.values())

    import os as _os
    mtime = _os.path.getmtime(MRP_SOURCE_PATH)
    import datetime
    file_date = datetime.datetime.fromtimestamp(mtime).strftime("%d %b %Y %H:%M")

    return {
        "ok": True,
        "divisions": list(data.keys()),
        "dept_count": dept_count,
        "mrp_count": band_count,
        "periods": period_cols,
        "parse_errors": errors,
        "contrib_warnings": warnings,
        "source_file": MRP_SOURCE_NAME,
        "source_path": MRP_SOURCE_DIR,
        "file_date": file_date,
    }


@router.get("/sync-status")
def get_sync_status():
    """Return whether the source file exists and when it was last modified."""
    exists = os.path.exists(MRP_SOURCE_PATH)
    if not exists:
        return {"file_found": False, "source_path": MRP_SOURCE_DIR, "source_name": MRP_SOURCE_NAME}
    import datetime
    mtime = os.path.getmtime(MRP_SOURCE_PATH)
    file_date = datetime.datetime.fromtimestamp(mtime).strftime("%d %b %Y %H:%M")
    size_kb = round(os.path.getsize(MRP_SOURCE_PATH) / 1024, 1)
    return {
        "file_found": True,
        "source_path": MRP_SOURCE_DIR,
        "source_name": MRP_SOURCE_NAME,
        "file_date": file_date,
        "size_kb": size_kb,
    }


@router.get("/data")
def get_mrp_data():
    mrp = _load()
    if not mrp:
        raise HTTPException(status_code=404, detail="No MRP plan imported yet. Upload a file to get started.")

    plan = _load_dept_plan()

    # Aggregate per-period P1/P2 TY across all stores
    # dept_ty_period[div][dept][period] = total TY  (period = "Mar'27 P1" etc)
    dept_ty_period: dict = {}
    for store_data in plan.get("stores", {}).values():
        for div, div_data in store_data.get("divisions", {}).items():
            for m, m_data in (div_data.get("months") or {}).items():
                if not isinstance(m_data, dict):
                    continue
                for dept, d_data in (m_data.get("departments") or {}).items():
                    if not isinstance(d_data, dict) or not d_data.get("active", True):
                        continue
                    ty_total = d_data.get("ty", 0.0) or 0.0
                    p1 = d_data.get("ty_p1", ty_total / 2.0) or 0.0
                    p2 = d_data.get("ty_p2", ty_total / 2.0) or 0.0
                    dept_ty_period.setdefault(div, {}).setdefault(dept, {})
                    k1, k2 = f"{m} P1", f"{m} P2"
                    dept_ty_period[div][dept][k1] = dept_ty_period[div][dept].get(k1, 0.0) + p1
                    dept_ty_period[div][dept][k2] = dept_ty_period[div][dept].get(k2, 0.0) + p2

    # Collect all periods present in the mrp data
    all_periods_set: set = set()
    for depts in mrp.values():
        for bands in depts.values():
            for period_vals in bands.values():
                all_periods_set.update(period_vals.keys())
    all_periods = [p for p in TY_PERIODS if p in all_periods_set]

    result = {}
    for div, depts in mrp.items():
        result[div] = {}
        for dept, bands in depts.items():
            period_ty = dept_ty_period.get(div, {}).get(dept, {})
            dept_total_ty = sum(period_ty.values())

            # each period's department TY split over its MRP bands by their share - the bands add back to the
            # department exactly, even when the shares total 99.6 or 100.4 (2026-09-30: each band was rounded to 2 dp)
            keys = sorted(bands.keys(), key=lambda x: float(x))
            per = {p: split(period_ty.get(p, 0.0), {k: bands[k].get(p, 0.0) for k in keys}) for p in all_periods}
            band_list = []
            for mrp_key in keys:
                period_split = {p: per[p][mrp_key] for p in all_periods}
                band_list.append({
                    "mrp": float(mrp_key),
                    "period_contrib": {p: bands[mrp_key].get(p, 0.0) for p in all_periods},
                    "period_ty": period_split,
                    "band_total_ty": sum(period_split.values()),
                })

            # contrib validation per period
            contrib_ok = {}
            for p in all_periods:
                total = sum(b["period_contrib"].get(p, 0.0) for b in band_list)
                contrib_ok[p] = abs(total - 100) <= 0.5

            allocated = sum(b["band_total_ty"] for b in band_list)
            result[div][dept] = {
                "dept_total_ty": dept_total_ty,
                "allocated_ty": allocated,
                # the reconciliation: department TY vs its MRP bands (0 to 8 dp unless no band has a share in a period)
                "difference": allocated - sum(period_ty.get(p, 0.0) for p in all_periods),
                "bands": band_list,
                "contrib_ok": contrib_ok,
                "all_ok": all(contrib_ok.values()),
            }

    return {
        "divisions": list(result.keys()),
        "periods": all_periods,
        "total_depts": sum(len(d) for d in result.values()),
        "total_bands": sum(len(d[dept]["bands"]) for d in result.values() for dept in d),
        "has_plan": bool(plan),
        "data": result,
    }


@router.get("/status")
def get_mrp_status():
    mrp = _load()
    if not mrp:
        return {"imported": False}
    dept_count = sum(len(depts) for depts in mrp.values())
    band_count = sum(len(bands) for depts in mrp.values() for bands in depts.values())
    periods_set: set = set()
    for depts in mrp.values():
        for bands in depts.values():
            for period_vals in bands.values():
                periods_set.update(period_vals.keys())
    ordered = [p for p in TY_PERIODS if p in periods_set]
    months_set = {p.replace(" P1", "").replace(" P2", "") for p in ordered}
    months_ordered = [m for m in TY_MONTHS if m in months_set]
    return {
        "imported": True,
        "divisions": list(mrp.keys()),
        "dept_count": dept_count,
        "band_count": band_count,
        "periods": ordered,
        "months": months_ordered,
    }


@router.delete("/clear")
def clear_mrp():
    if os.path.exists(DATA_PATH):
        os.remove(DATA_PATH)
    return {"ok": True}


@router.get("/export")
def export_mrp():
    mrp = _load()
    if not mrp:
        raise HTTPException(status_code=404, detail="No MRP data to export.")

    plan = _load_dept_plan()
    dept_ty_period: dict = {}
    for store_data in plan.get("stores", {}).values():
        for div, div_data in store_data.get("divisions", {}).items():
            for m, m_data in (div_data.get("months") or {}).items():
                if not isinstance(m_data, dict):
                    continue
                for dept, d_data in (m_data.get("departments") or {}).items():
                    if not isinstance(d_data, dict) or not d_data.get("active", True):
                        continue
                    ty_total = d_data.get("ty", 0.0) or 0.0
                    p1 = d_data.get("ty_p1", ty_total / 2.0) or 0.0
                    p2 = d_data.get("ty_p2", ty_total / 2.0) or 0.0
                    dept_ty_period.setdefault(div, {}).setdefault(dept, {})
                    k1, k2 = f"{m} P1", f"{m} P2"
                    dept_ty_period[div][dept][k1] = dept_ty_period[div][dept].get(k1, 0.0) + p1
                    dept_ty_period[div][dept][k2] = dept_ty_period[div][dept].get(k2, 0.0) + p2

    periods_set: set = set()
    for depts in mrp.values():
        for bands in depts.values():
            for pv in bands.values():
                periods_set.update(pv.keys())
    periods = [p for p in TY_PERIODS if p in periods_set]

    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Division", "Department", "MRP"] + [f"{p} Contrib%" for p in periods] + [f"{p} TY(₹L)" for p in periods] + ["Band TY Total(₹L)"])

    for div in sorted(mrp.keys()):
        for dept in sorted(mrp[div].keys()):
            period_ty = dept_ty_period.get(div, {}).get(dept, {})
            keys = sorted(mrp[div][dept].keys(), key=lambda x: float(x))
            per = {p: split(period_ty.get(p, 0.0), {k: mrp[div][dept][k].get(p, 0.0) for k in keys}) for p in periods}
            for mrp_key in keys:
                period_vals = mrp[div][dept][mrp_key]
                contrib_row = [period_vals.get(p, "") for p in periods]
                ty_row = [round(per[p][mrp_key], 8) if period_ty.get(p) else "" for p in periods]
                band_total = sum(per[p][mrp_key] for p in periods)
                writer.writerow([div, dept, mrp_key] + contrib_row + ty_row + [round(band_total, 8)])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mrp_plan_output.csv"},
    )
