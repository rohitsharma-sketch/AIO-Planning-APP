from fastapi import APIRouter
from pydantic import BaseModel
import os
import sys
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))
from store_master import load_store_master as _universal_store_master, is_ssg as _universal_is_ssg

router = APIRouter()

SEASONALITY_CURVE = [0.75, 0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.10, 0.90, 1.10]
MONTH_NAMES = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]

AOP_INPUTS = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "Tentative AOP Forecaster", "inputs.xlsx"
)

# KLM only — GM and RETAIL excluded until expanded
DIVISIONS = ["KIDS", "LADIES", "MENS"]

# FY27 LFL actuals by division (Lakhs) — base for growth rate calculation
FY27_BASE = {
    "KIDS":   54237.27,
    "LADIES": 51264.55,
    "MENS":   68427.08,
}

FY28_MONTHS = [
    "Apr'27","May'27","Jun'27","Jul'27","Aug'27","Sep'27",
    "Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"
]


def _load_growth_rates():
    """
    Read Growth % sheet from inputs.xlsx.
    Returns {div: float} using the average across months per division.
    Falls back to 6.0 if the file is unreadable.
    """
    try:
        path = os.path.abspath(AOP_INPUTS)
        df = pd.read_excel(path, sheet_name="Growth %", header=3)
        df.columns = [str(c).strip().replace("’", "’").replace("‘", "’") for c in df.columns]
        df = df[df.iloc[:, 0].notna()]
        df = df[~df.iloc[:, 0].astype(str).str.upper().str.startswith("HOW")]
        df.rename(columns={df.columns[0]: "Division"}, inplace=True)
        df["Division"] = df["Division"].astype(str).str.strip().str.upper()
        df = df.set_index("Division")

        month_cols = [c for c in FY28_MONTHS if c in df.columns]
        overall_fallback = 6.0

        overall_row = df.loc["OVERALL", month_cols] if "OVERALL" in df.index else None
        if overall_row is not None:
            overall_vals = pd.to_numeric(overall_row, errors="coerce").dropna()
            overall_fallback = float(overall_vals.mean()) if len(overall_vals) else 6.0

        result = {}
        for div in DIVISIONS:
            if div in df.index:
                row = pd.to_numeric(df.loc[div, month_cols], errors="coerce").dropna()
                result[div] = float(row.mean()) if len(row) else overall_fallback
            else:
                result[div] = overall_fallback
        return result
    except Exception:
        return {div: 6.0 for div in DIVISIONS}


def _load_store_master():
    return list(_universal_store_master())


def _load_aop_targets():
    """Read MAMJ AOP targets. Prefers locked (aop_locked_target) over staging
    (aop_division_target) — locked is set by the explicit Promote action in
    the AOP Forecaster after a run is approved.
    Returns ({div: {period_id: lakhs}}, lever_key_used | None).
    """
    try:
        from db.base import SessionLocal
        from sqlalchemy import text
        with SessionLocal() as db:
            for lever in ("aop_locked_target", "aop_division_target"):
                rows = db.execute(text(
                    "SELECT row_key, period_id, value FROM planning_inputs.input_values "
                    "WHERE lever_key=:lk AND row_key = ANY(:divs) "
                    "ORDER BY row_key, period_id"
                ), {"lk": lever, "divs": list(DIVISIONS)}).fetchall()
                if rows:
                    result = {}
                    for row_key, period_id, value in rows:
                        result.setdefault(row_key, {})[period_id] = float(value)
                    return result, lever
        return {}, None
    except Exception:
        return {}, None


def _aop_mamj_total(aop_by_div: dict) -> dict:
    """Sum MAMJ (period_ids 202703..202706) per division → Lakhs."""
    MAMJ = {202703, 202704, 202705, 202706}
    return {
        div: sum(v for pid, v in periods.items() if pid in MAMJ)
        for div, periods in aop_by_div.items()
    }


PLAN_MONTHS = {202703: "Mar'27", 202704: "Apr'27", 202705: "May'27", 202706: "Jun'27"}


def _bis_aop():
    """The AOP publish BIS plans on (user, 29 Sep 2026: "show the plan shown in BIS and not any day further"):
    the one stamped on BIS's last growth push (buyer_department_growth source "buyer_input|aop:<id>"), else the
    live saved version. Returns (publish id, version label, division_totals, division_base_totals) or Nones."""
    from db.base import SessionLocal
    from db.publish_aop_targets import list_aop_history
    from sqlalchemy import text
    with SessionLocal() as db:
        src = db.execute(text(
            "SELECT source FROM planning_inputs.input_values WHERE lever_key = 'buyer_department_growth' "
            "AND source LIKE '%aop:%' ORDER BY updated_at DESC LIMIT 1")).scalar()
        hist = list_aop_history(db, limit=50)
        pid = int(src.split("aop:", 1)[1]) if src else (hist[0]["id"] if hist else None)
        h = next((x for x in hist if x["id"] == pid), None)
        if h is None:
            return None, None, {}, {}
        bases = db.execute(text("SELECT division_base_totals FROM planning_inputs.aop_publish_history WHERE id = :id"),
                           {"id": pid}).scalar()
    return pid, h["version_label"], h["division_totals"] or {}, bases or {}


def _plan_rows(totals: dict, bases: dict) -> list:
    """Per division, the months BIS plans: LY base = the publish's base (Mar-Jun 2026 LY, fixed once published),
    plan = its division target - BIS spreads every division exactly onto it (verified 0.0000 L)."""
    val = lambda d, p: float((d or {}).get(str(p), (d or {}).get(p)) or 0)
    out = []
    for div in DIVISIONS:
        months = [{"period_id": p, "month": m, "ly": round(val(bases.get(div), p), 2), "plan": round(val(totals.get(div), p), 2)}
                  for p, m in PLAN_MONTHS.items()]
        for m in months:
            m["growth_pct"] = round((m["plan"] / m["ly"] - 1) * 100, 2) if m["ly"] else None
        ly, plan = sum(m["ly"] for m in months), sum(m["plan"] for m in months)
        out.append({"division_name": div, "ly_mamj": round(ly, 2), "plan_mamj": round(plan, 2),
                    "growth_pct": round((plan / ly - 1) * 100, 2) if ly else None, "months": months})
    return out


def _versions():
    """Every saved AOP version (its latest publish) - the choices for "Compare with" (user, 30 Sep 2026)."""
    from db.base import SessionLocal
    from db.publish_aop_targets import list_aop_history
    with SessionLocal() as db:
        hist = list_aop_history(db, limit=50)
    return [{"id": h["id"], "label": h["version_label"], "published_at": h["published_at"],
             "total_mamj": round(h["total_mamj_lakhs"] or 0, 2)} for h in hist]


@router.get("/compare/{publish_id}")
def get_compare(publish_id: int):
    """Another saved version's Mar-Jun division numbers, to set beside the BIS plan - view only, changes nothing."""
    from fastapi import HTTPException
    from db.base import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as db:
        row = db.execute(text("SELECT division_totals, division_base_totals FROM planning_inputs.aop_publish_history "
                              "WHERE id = :id"), {"id": publish_id}).first()
    v = next((x for x in _versions() if x["id"] == publish_id), None)
    if row is None or v is None:
        raise HTTPException(404, "That AOP version isn't among the saved versions.")
    divisions = _plan_rows(row[0] or {}, row[1] or {})
    return {"publish_id": publish_id, "version_label": v["label"], "published_at": v["published_at"],
            "divisions": divisions,
            "total_ly": round(sum(d["ly_mamj"] for d in divisions), 2),
            "total_plan": round(sum(d["plan_mamj"] for d in divisions), 2)}


@router.get("/config")
def get_config():
    store_master = _load_store_master()
    pid, label, totals, bases = _bis_aop()
    divisions = _plan_rows(totals, bases)
    return {
        "divisions": divisions,
        "total_stores": len(store_master),
        "n_divisions": len(DIVISIONS),
        "aop_publish_id": pid,
        "version_label": label,
        "source": f"BIS plan on AOP {label or '-'} (publish {pid})" if pid else "No AOP published yet",
        "total_ly": round(sum(d["ly_mamj"] for d in divisions), 2),
        "total_plan": round(sum(d["plan_mamj"] for d in divisions), 2),
        "versions": _versions(),
    }


@router.get("/stores")
def get_stores():
    return {"stores": _load_store_master()}


# ──────────────────────────────────────────────
# Growth Structure endpoints
# ──────────────────────────────────────────────

SEASON_SUM = sum(SEASONALITY_CURVE)


class GrowthMatrixInput(BaseModel):
    growth_matrix: dict  # {"OVERALL": [6,6,...], "GM": [None,...], ...}


def _read_growth_matrix_from_file() -> dict:
    """
    Read Growth % sheet from inputs.xlsx.
    Returns {div: [v0..v11]} where null means "inherits OVERALL".
    OVERALL row always has 12 floats.
    """
    try:
        path = os.path.abspath(AOP_INPUTS)
        df = pd.read_excel(path, sheet_name="Growth %", header=3)
        df.columns = [str(c).strip().replace("’", "’").replace("‘", "’") for c in df.columns]
        df = df[df.iloc[:, 0].notna()]
        df = df[~df.iloc[:, 0].astype(str).str.upper().str.startswith("HOW")]
        df.rename(columns={df.columns[0]: "Division"}, inplace=True)
        df["Division"] = df["Division"].astype(str).str.strip().str.upper()
        df = df.set_index("Division")

        month_cols = [c for c in FY28_MONTHS if c in df.columns]

        # OVERALL row — all 12 floats
        if "OVERALL" in df.index:
            overall_raw = pd.to_numeric(df.loc["OVERALL", month_cols], errors="coerce")
            overall_vals = [float(v) if pd.notna(v) else 6.0 for v in overall_raw]
        else:
            overall_vals = [6.0] * 12

        result = {"OVERALL": overall_vals}

        for div in DIVISIONS:
            if div in df.index:
                row_raw = pd.to_numeric(df.loc[div, month_cols], errors="coerce")
                row_vals = []
                for i, v in enumerate(row_raw):
                    if pd.isna(v):
                        row_vals.append(None)
                    elif abs(float(v) - overall_vals[i]) < 0.001:
                        row_vals.append(None)  # inherits
                    else:
                        row_vals.append(float(v))
                result[div] = row_vals
            else:
                result[div] = [None] * 12

        return result
    except Exception:
        overall = [6.0] * 12
        result = {"OVERALL": overall}
        for div in DIVISIONS:
            result[div] = [None] * 12
        return result


def _build_growth_structure(growth_matrix: dict) -> dict:
    """
    Given a growth_matrix {"OVERALL": [...], "GM": [...], ...},
    compute monthly base, effective growth, and forecast for each division.
    """
    raw_overall = growth_matrix.get("OVERALL", [])
    overall = (list(raw_overall) + [6.0] * 12)[:12]

    divisions_out = []
    total_base = 0.0
    total_forecast = 0.0

    for div in DIVISIONS:
        base = FY27_BASE.get(div, 0.0)
        raw_growth = growth_matrix.get(div, [])
        # Ensure exactly 12 entries — pad with None if shorter
        div_growth = list(raw_growth) + [None] * (12 - len(raw_growth))
        div_growth = div_growth[:12]

        monthly_base = []
        monthly_forecast = []

        for i in range(12):
            mb = base / SEASON_SUM * SEASONALITY_CURVE[i]
            monthly_base.append(round(mb, 2))

            eff = div_growth[i] if (div_growth[i] is not None) else overall[i]
            mf = mb * (1 + eff / 100)
            monthly_forecast.append(round(mf, 2))

        annual_base = round(sum(monthly_base), 2)
        annual_forecast = round(sum(monthly_forecast), 2)
        eff_annual = (annual_forecast / annual_base - 1) * 100 if annual_base else 0.0

        divisions_out.append({
            "division_name": div,
            "annual_base": annual_base,
            "annual_forecast": annual_forecast,
            "growth_pct": round(eff_annual, 2),
            "monthly_base": monthly_base,
            "monthly_forecast": monthly_forecast,
        })

        total_base += annual_base
        total_forecast += annual_forecast

    overall_growth_pct = round((total_forecast / total_base - 1) * 100, 2) if total_base else 0.0

    return {
        "months": FY28_MONTHS,
        "growth_matrix": growth_matrix,
        "divisions": divisions_out,
        "total_base": round(total_base, 2),
        "total_forecast": round(total_forecast, 2),
        "overall_growth_pct": overall_growth_pct,
        "source": "AOP Forecaster — inputs.xlsx",
    }


@router.get("/growth-structure")
def get_growth_structure():
    matrix = _read_growth_matrix_from_file()
    return _build_growth_structure(matrix)


@router.post("/growth-structure")
def post_growth_structure(payload: GrowthMatrixInput):
    return _build_growth_structure(payload.growth_matrix)
