# Display Type Plan Engine
# Store × Dept × MRP × Display Type → ₹L plan and Qty
#
# Sources:
#   final_dept_plan.json  — store × div × dept × month → ty_p1, ty_p2 (₹L)
#   mrp_plan.json         — div × dept × mrp × period  → contrib%
#   dt_contributions.json — store × div × dept × mrp   → {table%, nontable%}  (user upload)
#   dt_asp.json           — div × dept × mrp × dt × month → ASP ₹              (user upload)

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
import os, json, datetime, io, sys
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import SHOWN, split  # noqa: E402

from plan_cache import load_json as _load_plan_json  # noqa: E402

router = APIRouter()

_BASE          = os.path.dirname(__file__)
_PARENT        = os.path.join(_BASE, "..")
FINAL_PLAN_PATH = os.path.join(_PARENT, "final_dept_plan.json")
MRP_PLAN_PATH   = os.path.join(_BASE,  "mrp_plan.json")
DT_CONTRIB_PATH = os.path.join(_PARENT, "dt_contributions.json")
DT_ASP_PATH     = os.path.join(_PARENT, "dt_asp.json")
DT_RESULT_PATH  = os.path.join(_PARENT, "dt_plan_result.json")
DT_QTY_PATH     = os.path.join(_PARENT, "dt_qty_result.json")

DT_TABLE    = "Table"
DT_NONTABLE = "Non-Table"


def _ts(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ── helpers ────────────────────────────────────────────────────────────────────

def _month_from_period(period: str) -> str:
    """'Mar'27 P1' → 'Mar'27'"""
    return period.rsplit(" P", 1)[0]

def _derive_months(mrp_plan: dict) -> list[str]:
    """Extract unique months from mrp_plan periods."""
    seen, months = set(), []
    for div in mrp_plan.values():
        for dept in div.values():
            for mrp in dept.values():
                for period in mrp:
                    m = _month_from_period(period)
                    if m not in seen:
                        seen.add(m)
                        months.append(m)
    return months


# ── status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
def status():
    contrib = _load(DT_CONTRIB_PATH)
    asp     = _load(DT_ASP_PATH)
    result  = _load(DT_RESULT_PATH)
    qty     = _load(DT_QTY_PATH)
    fp      = _load(FINAL_PLAN_PATH)
    mrp     = _load(MRP_PLAN_PATH)
    return {
        "dept_plan_ok":    fp is not None,
        "mrp_plan_ok":     mrp is not None,
        "contrib_imported": contrib is not None,
        "contrib_rows":     contrib.get("count", 0) if contrib else 0,
        "contrib_date":     contrib.get("imported_at", "") if contrib else "",
        "asp_imported":    asp is not None,
        "asp_rows":        asp.get("count", 0) if asp else 0,
        "asp_date":        asp.get("imported_at", "") if asp else "",
        "plan_run":        result is not None,
        "plan_date":       result.get("run_at", "") if result else "",
        "qty_run":         qty is not None,
        "qty_date":        qty.get("run_at", "") if qty else "",
    }


# ── contribution import ─────────────────────────────────────────────────────────
# Expected columns: Store | Division | Department | MRP | Table% | Non-Table%

@router.post("/import/contributions")
async def import_contributions(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(raw)) if not file.filename.endswith(".csv") else pd.read_csv(io.BytesIO(raw))
        df.columns = [str(c).strip() for c in df.columns]
    except Exception as e:
        raise HTTPException(400, f"Parse error: {e}")

    col_map = {}
    for c in df.columns:
        cu = c.strip().upper()
        if cu == "STORE":               col_map[c] = "store"
        elif cu in ("DIVISION","DIV"):  col_map[c] = "division"
        elif cu in ("DEPARTMENT","DEPT"): col_map[c] = "dept"
        elif cu in ("MRP","FINAL MRP","PRICE"): col_map[c] = "mrp"
        elif "TABLE" in cu and "NON" not in cu and "%" in cu: col_map[c] = "table_pct"
        elif "NON" in cu and "TABLE" in cu:                   col_map[c] = "nontable_pct"
        elif cu == "TABLE%":   col_map[c] = "table_pct"
        elif cu == "NON-TABLE%" or cu == "NONTABLE%": col_map[c] = "nontable_pct"
    df = df.rename(columns=col_map)

    required = {"store", "division", "dept", "mrp", "table_pct", "nontable_pct"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(400, f"Missing columns: {missing}. Got: {list(df.columns)}")

    records = {}  # (store, div, dept, mrp) → {table_pct, nontable_pct}
    for _, r in df.iterrows():
        store = str(r["store"]).strip()
        div   = str(r["division"]).strip()
        dept  = str(r["dept"]).strip()
        mrp   = str(r["mrp"]).strip()
        if not store or store == "nan": continue
        try: tbl = float(r["table_pct"])
        except: tbl = 0.0
        try: ntbl = float(r["nontable_pct"])
        except: ntbl = 0.0
        records[f"{store}|{div}|{dept}|{mrp}"] = {
            "store": store, "division": div, "dept": dept, "mrp": mrp,
            "table_pct": round(tbl, 4), "nontable_pct": round(ntbl, 4),
        }

    out = {"imported_at": _ts(), "source": file.filename, "count": len(records), "data": records}
    _save(DT_CONTRIB_PATH, out)
    return {"ok": True, "rows": len(records)}


# ── ASP import ─────────────────────────────────────────────────────────────────
# Expected: Division | Department | MRP | Display Type | Mar'27 | Apr'27 | ...

@router.post("/import/asp")
async def import_asp(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(raw)) if not file.filename.endswith(".csv") else pd.read_csv(io.BytesIO(raw))
        df.columns = [str(c).strip() for c in df.columns]
    except Exception as e:
        raise HTTPException(400, f"Parse error: {e}")

    FIXED = {"division", "dept", "department", "mrp", "final mrp", "display type", "display_type", "type"}
    col_map = {}
    for c in df.columns:
        cu = c.strip().upper()
        if cu in ("DIVISION", "DIV"):          col_map[c] = "division"
        elif cu in ("DEPARTMENT", "DEPT"):     col_map[c] = "dept"
        elif cu in ("MRP", "FINAL MRP"):       col_map[c] = "mrp"
        elif cu in ("DISPLAY TYPE", "DISPLAY_TYPE", "TYPE", "DT"): col_map[c] = "display_type"
    df = df.rename(columns=col_map)

    month_cols = [c for c in df.columns if c not in {"division","dept","mrp","display_type"}]

    records = {}
    for _, r in df.iterrows():
        div  = str(r.get("division","")).strip()
        dept = str(r.get("dept","")).strip()
        mrp  = str(r.get("mrp","")).strip()
        dt   = str(r.get("display_type","")).strip()
        if not dept or dept == "nan": continue
        month_vals = {}
        for m in month_cols:
            try: month_vals[m] = float(r[m])
            except: month_vals[m] = 0.0
        records[f"{div}|{dept}|{mrp}|{dt}"] = {
            "division": div, "dept": dept, "mrp": mrp, "display_type": dt,
            "months": month_vals,
        }

    out = {"imported_at": _ts(), "source": file.filename, "count": len(records),
           "months": month_cols, "data": records}
    _save(DT_ASP_PATH, out)
    return {"ok": True, "rows": len(records), "months": month_cols}


# ── run plan ───────────────────────────────────────────────────────────────────

def _dept_plan():
    """The latest department plan - corrected first, like every other engine (was the uncorrected plan only)."""
    for f in ("base_corrected_plan.json", "attr_corrected_plan.json", "final_dept_plan.json"):
        d = _load_plan_json(os.path.join(_PARENT, f))
        if d:
            return d
    return None


@router.get("/run-plan")
def run_plan():
    fp      = _dept_plan()
    mrp_raw = _load(MRP_PLAN_PATH)
    contrib = _load(DT_CONTRIB_PATH)

    if not fp:      raise HTTPException(400, "final_dept_plan not found")
    if not mrp_raw: raise HTTPException(400, "mrp_plan not found")
    if not contrib: raise HTTPException(400, "Contributions not imported")

    contrib_data = contrib["data"]
    months = _derive_months(mrp_raw)

    rows = []
    for store, sr in fp["stores"].items():
        if not sr.get("is_ssg"): continue
        divs = sr.get("divisions", {})
        for div, div_data in divs.items():
            if div not in mrp_raw: continue
            # 2026-09-30: this looped over the division's keys ("months") instead of its months - no rows were made
            for month, month_data in div_data.get("months", {}).items():
                if month not in months: continue   # a month with no MRP shares has nothing to split by
                depts_data = month_data.get("departments", {})
                for dept, dept_rec in depts_data.items():
                    if dept not in mrp_raw.get(div, {}): continue
                    mrp_dept = mrp_raw[div][dept]
                    ty_p1 = dept_rec.get("ty_p1", 0.0)
                    ty_p2 = dept_rec.get("ty_p2", 0.0)
                    # each half split over the MRPs by its share - the MRPs add back to the department exactly
                    s1 = split(ty_p1, {m: pm.get(f"{month} P1", 0.0) for m, pm in mrp_dept.items()})
                    s2 = split(ty_p2, {m: pm.get(f"{month} P2", 0.0) for m, pm in mrp_dept.items()})

                    for mrp_str in mrp_dept:
                        mrp_plan_rs = s1[mrp_str] + s2[mrp_str]

                        ck = f"{store}|{div}|{dept}|{mrp_str}"
                        c  = contrib_data.get(ck, {})
                        tbl_pct  = c.get("table_pct",    0.0)
                        ntbl_pct = c.get("nontable_pct", 0.0)
                        has_contrib = bool(c) and (tbl_pct + ntbl_pct) > 0
                        # Table / Non-Table add back to the MRP plan exactly
                        dt = split(mrp_plan_rs, {"t": tbl_pct, "n": ntbl_pct})

                        rows.append({
                            "store": store, "division": div, "dept": dept, "mrp": mrp_str,
                            "month": month,
                            "ty_p1": ty_p1, "ty_p2": ty_p2,
                            "mrp_plan": mrp_plan_rs,
                            "table_contrib":    tbl_pct,
                            "nontable_contrib": ntbl_pct,
                            "table_plan":    dt["t"],
                            "nontable_plan": dt["n"],
                            "has_contrib": has_contrib,
                        })

    out = {"run_at": _ts(), "months": months, "rows": rows}
    _save(DT_RESULT_PATH, out)
    return {"ok": True, "rows": len(rows), "months": months}


@router.get("/result")
def get_result():
    d = _load(DT_RESULT_PATH)
    if not d: raise HTTPException(404, "Plan not run yet")
    return d


# ── validate ───────────────────────────────────────────────────────────────────

@router.get("/validate")
def validate():
    result = _load(DT_RESULT_PATH)
    if not result: raise HTTPException(400, "Run plan first")

    rows = result["rows"]
    anomalies = []
    TOLS = SHOWN  # any gap that shows at 8 decimals (was 0.001 L)

    # Index by (store, div, dept, mrp, month)
    by_key: dict = {}
    for r in rows:
        k = (r["store"], r["division"], r["dept"], r["mrp"], r["month"])
        by_key[k] = r

    # 1. Display Type → MRP: table+nontable should equal mrp_plan (within tolerance)
    #    Also: missing contribution
    for r in rows:
        dt_sum = r["table_plan"] + r["nontable_plan"]
        gap    = abs(dt_sum - r["mrp_plan"])
        if not r["has_contrib"]:
            anomalies.append({
                "level": "Display Type → MRP",
                "severity": "error",
                "store": r["store"], "division": r["division"],
                "dept": r["dept"], "mrp": r["mrp"], "month": r["month"],
                "expected": round(r["mrp_plan"], 4), "actual": 0.0,
                "gap": round(r["mrp_plan"], 4),
                "message": (
                    f"No Display Type contribution defined for "
                    f"{r['store']} / {r['dept']} / MRP ₹{r['mrp']} in {r['month']}. "
                    f"Full MRP plan of ₹{r['mrp_plan']:.2f}L is unallocated."
                ),
            })
        elif gap > TOLS:
            contrib_sum = r["table_contrib"] + r["nontable_contrib"]
            anomalies.append({
                "level": "Display Type → MRP",
                "severity": "error",
                "store": r["store"], "division": r["division"],
                "dept": r["dept"], "mrp": r["mrp"], "month": r["month"],
                "expected": round(r["mrp_plan"], 4), "actual": round(dt_sum, 4),
                "gap": round(dt_sum - r["mrp_plan"], 4),
                "message": (
                    f"{r['store']} / {r['dept']} / MRP ₹{r['mrp']} / {r['month']}: "
                    f"Display Type plans sum to ₹{dt_sum:.4f}L but MRP plan is ₹{r['mrp_plan']:.4f}L. "
                    f"Contribution totals {contrib_sum:.1f}% — "
                    f"{'remaining ' + str(round(100 - contrib_sum, 1)) + '% unallocated' if contrib_sum < 100 else 'over-allocated by ' + str(round(contrib_sum - 100, 1)) + '%'}."
                ),
            })

    # 2. Contribution sum check
    seen_contrib = set()
    contrib_data = (_load(DT_CONTRIB_PATH) or {}).get("data", {})
    for ck, c in contrib_data.items():
        total = c.get("table_pct", 0) + c.get("nontable_pct", 0)
        if abs(total - 100) > 0.05:
            key = f"{c['store']}|{c['dept']}|{c['mrp']}"
            if key not in seen_contrib:
                seen_contrib.add(key)
                anomalies.append({
                    "level": "Contribution Sum",
                    "severity": "warning",
                    "store": c["store"], "division": c.get("division",""),
                    "dept": c["dept"], "mrp": c["mrp"], "month": "—",
                    "expected": 100.0, "actual": round(total, 2),
                    "gap": round(total - 100, 2),
                    "message": (
                        f"Contribution for {c['store']} / {c['dept']} / MRP ₹{c['mrp']} "
                        f"sums to {total:.1f}% — "
                        f"{'remaining ' + str(round(100 - total, 1)) + '% unallocated' if total < 100 else 'over-allocated by ' + str(round(total - 100, 1)) + '%'}. "
                        f"Assign the balance to Table or Non-Table."
                    ),
                })

    # 3. MRP → Dept check per store × month
    from collections import defaultdict
    mrp_by_dept: dict = defaultdict(float)
    dept_ty: dict     = defaultdict(float)
    for r in rows:
        dk = (r["store"], r["division"], r["dept"], r["month"])
        mrp_by_dept[dk] += r["mrp_plan"]
        dept_ty[dk]      = r["ty_p1"] + r["ty_p2"]

    for dk, mrp_sum in mrp_by_dept.items():
        store, div, dept, month = dk
        ty = dept_ty[dk]
        gap = abs(mrp_sum - ty)
        if gap > TOLS and ty > 0:
            anomalies.append({
                "level": "MRP → Department",
                "severity": "error",
                "store": store, "division": div, "dept": dept, "mrp": "ALL", "month": month,
                "expected": ty, "actual": mrp_sum,
                "gap": mrp_sum - ty,
                "message": (
                    f"{dept} in {store} / {month}: no MRP shares for this month in the MRP plan - "
                    f"₹{ty:.8f}L is not split to MRPs. Add its MRP shares." if mrp_sum == 0 else
                    f"{dept} in {store} / {month}: MRP plans total ₹{mrp_sum:.8f}L "
                    f"vs department plan ₹{ty:.8f}L (gap ₹{mrp_sum - ty:+.8f}L)."
                ),
            })

    # 4. Dept → Division check per store × month
    dept_sum_by_div: dict = defaultdict(float)
    div_ty: dict          = defaultdict(float)
    fp = _dept_plan()
    if fp:
        for store, sr in fp["stores"].items():
            if not sr.get("is_ssg"): continue
            for div, div_data in sr.get("divisions", {}).items():
                for month, mdata in div_data.get("months", {}).items():
                    div_ty[(store, div, month)] = mdata.get("div_total_ty", 0.0)
    for r in rows:
        dept_sum_by_div[(r["store"], r["division"], r["month"])] += r["mrp_plan"]
    for dk, dept_sum in dept_sum_by_div.items():
        store, div, month = dk
        div_total = div_ty.get(dk, 0.0)
        gap = abs(dept_sum - div_total)
        if gap > TOLS and div_total > 0:
            anomalies.append({
                "level": "Department → Division",
                "severity": "warning",
                "store": store, "division": div, "dept": "ALL", "mrp": "ALL", "month": month,
                "expected": div_total, "actual": dept_sum,
                "gap": dept_sum - div_total,
                "message": (
                    f"{div} in {store} / {month}: departments split to MRPs total ₹{dept_sum:.8f}L "
                    f"vs division plan ₹{div_total:.8f}L ({(dept_sum/div_total - 1)*100:+.2f}%) - "
                    f"departments with no MRP shares in the MRP plan are not split."
                ),
            })

    errors   = [a for a in anomalies if a["severity"] == "error"]
    warnings = [a for a in anomalies if a["severity"] == "warning"]

    summary = {
        "validated_at": _ts(),
        "total": len(anomalies),
        "errors": len(errors),
        "warnings": len(warnings),
        "gate_open": len(errors) == 0,
        "anomalies": anomalies,
    }
    return summary


# ── run qty ────────────────────────────────────────────────────────────────────

@router.get("/run-qty")
def run_qty():
    result = _load(DT_RESULT_PATH)
    asp    = _load(DT_ASP_PATH)
    if not result: raise HTTPException(400, "Run plan first")
    if not asp:    raise HTTPException(400, "ASP not imported")

    asp_data = asp["data"]

    def get_asp(div, dept, mrp, dt, month):
        k = f"{div}|{dept}|{mrp}|{dt}"
        rec = asp_data.get(k, {})
        val = rec.get("months", {}).get(month, 0.0)
        return val

    qty_rows = []
    missing_asp = []
    for r in result["rows"]:
        div   = r["division"]
        dept  = r["dept"]
        mrp   = r["mrp"]
        month = r["month"]

        t_asp  = get_asp(div, dept, mrp, DT_TABLE,    month)
        nt_asp = get_asp(div, dept, mrp, DT_NONTABLE, month)

        def to_qty(plan_l, asp_val):
            if asp_val and asp_val > 0:
                return round(plan_l * 1e5 / asp_val, 0)
            return None

        t_qty  = to_qty(r["table_plan"],    t_asp)
        nt_qty = to_qty(r["nontable_plan"], nt_asp)

        if t_qty is None:
            missing_asp.append({"store": r["store"], "dept": dept, "mrp": mrp, "dt": DT_TABLE, "month": month})
        if nt_qty is None:
            missing_asp.append({"store": r["store"], "dept": dept, "mrp": mrp, "dt": DT_NONTABLE, "month": month})

        qty_rows.append({**r,
            "table_asp":  t_asp,  "table_qty":  t_qty,
            "nontable_asp": nt_asp, "nontable_qty": nt_qty,
        })

    out = {"run_at": _ts(), "months": result["months"], "rows": qty_rows, "missing_asp": missing_asp}
    _save(DT_QTY_PATH, out)
    return {"ok": True, "rows": len(qty_rows), "missing_asp": len(missing_asp)}


@router.get("/qty-result")
def get_qty():
    d = _load(DT_QTY_PATH)
    if not d: raise HTTPException(404, "Qty not run yet")
    return d


# ── export ─────────────────────────────────────────────────────────────────────

@router.get("/export")
def export():
    qty = _load(DT_QTY_PATH) or _load(DT_RESULT_PATH)
    if not qty: raise HTTPException(404, "No result to export")

    records = []
    for r in qty.get("rows", []):
        month = r["month"]
        records.append({
            "Store":      r["store"], "Division": r["division"],
            "Department": r["dept"],  "MRP":      r["mrp"],
            "Month":      month,
            "Table Contrib%":    r.get("table_contrib", 0),
            "NonTable Contrib%": r.get("nontable_contrib", 0),
            "MRP Plan (₹L)":    r.get("mrp_plan", 0),
            "Table Plan (₹L)":  r.get("table_plan", 0),
            "NonTable Plan (₹L)": r.get("nontable_plan", 0),
            "Table ASP (₹)":    r.get("table_asp", ""),
            "Table Qty":        r.get("table_qty", ""),
            "NonTable ASP (₹)": r.get("nontable_asp", ""),
            "NonTable Qty":     r.get("nontable_qty", ""),
        })

    df = pd.DataFrame(records)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for div, grp in df.groupby("Division"):
            grp.to_excel(writer, index=False, sheet_name=str(div)[:31])
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=display_type_plan.xlsx"},
    )
