from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io
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

DIVISION_SEASONALITY = {
    "KIDS":   1.10,
    "LADIES": 1.08,
    "MENS":   1.06,
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


def _build_default_divisions(aop_growth: dict | None = None):
    growth_rates = _load_growth_rates()
    # If AOP-derived growth is available, prefer it over inputs.xlsx
    if aop_growth:
        growth_rates.update(aop_growth)
    return [
        {
            "division_name": div,
            "base_sales": FY27_BASE[div],
            "growth_pct": growth_rates[div],
            "seasonality_index": DIVISION_SEASONALITY[div],
            "fy_start_month": 4,
        }
        for div in DIVISIONS
    ]


class DivisionConfig(BaseModel):
    division_name: str
    base_sales: float
    growth_pct: float
    seasonality_index: float
    fy_start_month: int


class DivisionPlanInput(BaseModel):
    divisions: list[DivisionConfig]
    plan_year: int
    plan_name: str


class MonthlyBreakdown(BaseModel):
    month: str
    planned_sales: float
    index: float


class DivisionResult(BaseModel):
    division_name: str
    annual_target: float
    monthly_breakdown: list[MonthlyBreakdown]


class DivisionPlanOutput(BaseModel):
    plan_name: str
    plan_year: int
    total_planned_sales: float
    divisions: list[DivisionResult]


@router.get("/aop-targets")
def get_aop_targets():
    """Return MAMJ AOP targets per division from the shared DB, with AOP growth from inputs.xlsx."""
    aop_by_div, _lever = _load_aop_targets()
    mamj = _aop_mamj_total(aop_by_div)
    # Growth rates from the AOP Forecaster's Growth % sheet — the actual forecast rates
    growth_rates = _load_growth_rates()
    out = []
    for div in DIVISIONS:
        mamj_val = mamj.get(div, 0.0)
        out.append({
            "division": div,
            "mamj_lakhs": round(mamj_val, 2),
            "fy27_base_lakhs": FY27_BASE.get(div, 0.0),
            "aop_growth_pct": round(growth_rates.get(div, 6.0), 2),
        })
    return {
        "source": "planning_inputs.input_values (aop_division_target)",
        "growth_source": "AOP Forecaster — inputs.xlsx",
        "divisions": out,
        "total_mamj_lakhs": round(sum(r["mamj_lakhs"] for r in out), 2),
    }


@router.get("/config")
def get_config():
    store_master = _load_store_master()
    aop_by_div, aop_lever = _load_aop_targets()
    mamj = _aop_mamj_total(aop_by_div)
    divisions_data = _build_default_divisions()
    for d in divisions_data:
        d["mamj_lakhs"] = round(mamj.get(d["division_name"], 0.0), 2)
    has_mamj = any(d["mamj_lakhs"] for d in divisions_data)
    lever_label = "locked" if aop_lever == "aop_locked_target" else ("staging" if aop_lever else None)
    return {
        "divisions": divisions_data,
        "store_master": store_master,
        "total_stores": len(store_master),
        "n_divisions": len(DIVISIONS),
        "source": "AOP Forecaster — inputs.xlsx (KLM)",
        "aop_source": "planning_inputs.input_values (MAMJ ref)" if has_mamj else "inputs.xlsx",
        "aop_lever": lever_label,
        "total_mamj_lakhs": round(sum(d["mamj_lakhs"] for d in divisions_data), 2),
    }


@router.post("/calculate", response_model=DivisionPlanOutput)
def calculate_plan(payload: DivisionPlanInput):
    results = []
    total = 0.0

    for div in payload.divisions:
        annual_target = div.base_sales * (1 + div.growth_pct / 100)
        start = div.fy_start_month - 1

        raw = []
        for i in range(12):
            month_idx = (start + i) % 12
            raw.append(SEASONALITY_CURVE[month_idx] * div.seasonality_index)

        raw_sum = sum(raw)
        monthly = []
        running = 0.0
        for i in range(12):
            month_idx = (start + i) % 12
            month_name = MONTH_NAMES[month_idx]
            idx = raw[i]
            if i < 11:
                planned = round((idx / raw_sum) * annual_target, 2)
                running += planned
            else:
                planned = round(annual_target - running, 2)
            monthly.append(MonthlyBreakdown(month=month_name, planned_sales=planned, index=round(idx, 4)))

        results.append(DivisionResult(
            division_name=div.division_name,
            annual_target=round(annual_target, 2),
            monthly_breakdown=monthly,
        ))
        total += annual_target

    return DivisionPlanOutput(
        plan_name=payload.plan_name,
        plan_year=payload.plan_year,
        total_planned_sales=round(total, 2),
        divisions=results,
    )


@router.get("/export")
def export_csv(plan_name: str = "FY27 Division Plan", plan_year: int = 2027):
    divisions = _build_default_divisions()
    lines = ["Plan Name,Plan Year,Division,Month,Planned Sales (Lakhs)"]
    for div in divisions:
        annual = div["base_sales"] * (1 + div["growth_pct"] / 100)
        start = div["fy_start_month"] - 1
        raw = []
        for i in range(12):
            month_idx = (start + i) % 12
            raw.append(SEASONALITY_CURVE[month_idx] * div["seasonality_index"])
        raw_sum = sum(raw)
        running = 0.0
        for i in range(12):
            month_idx = (start + i) % 12
            mn = MONTH_NAMES[month_idx]
            if i < 11:
                val = round((raw[i] / raw_sum) * annual, 2)
                running += val
            else:
                val = round(annual - running, 2)
            lines.append(f"{plan_name},{plan_year},{div['division_name']},{mn},{val}")

    content = "\n".join(lines)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=division_plan.csv"},
    )


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
