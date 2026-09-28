from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import datetime
import io, json, os
import pandas as pd

router = APIRouter()

# ── Department master ─────────────────────────────────────────────────────────
# Source: permanent hierarchy provided by CityKart.
# GM and RETAIL have no pre-defined departments — they start empty.
# custom_departments.json (auto-created alongside this file) persists user additions.

_MASTER_RAW = [
    # KIDS
    ("KIDS","BOYS DESIGNER","REGULAR"),("KIDS","GIRLS DESIGNER","REGULAR"),
    ("KIDS","KB_BABA SUIT DNM F/S","PREWINTER"),("KIDS","KB_BABA SUIT DNM H/S","SUMMER"),
    ("KIDS","KB_BABA SUIT HSR F/S","PREWINTER"),("KIDS","KB_BABA SUIT HSR H/S","SUMMER"),
    ("KIDS","KB_BABA SUIT TXTL H/S","SUMMER"),("KIDS","KB_HSR BERMUDA","SUMMER"),("KIDS","KB_TXTL BERMUDA","SUMMER"),
    ("KIDS","KB_BLAZER SUIT","OCCASIONAL"),("KIDS","KB_BLAZER","OCCASIONAL"),
    ("KIDS","KB_CASUAL SHIRT F/S","REGULAR"),("KIDS","KB_CASUAL SHIRT H/S","SUMMER"),
    ("KIDS","KB_HALF PANT","SUMMER"),("KIDS","KB_IN_BRIEF","REGULAR"),
    ("KIDS","KB_IN_VEST","REGULAR"),("KIDS","KB_INDO WESTERN","OCCASIONAL"),
    ("KIDS","KB_J_CTN TROUSER","REGULAR"),("KIDS","KB_J_JEANS","REGULAR"),
    ("KIDS","KB_JAMAICAN","SUMMER"),("KIDS","KB_KURTA","REGULAR"),
    ("KIDS","KB_MIX","REGULAR"),("KIDS","KB_NIGHT SUIT","REGULAR"),
    ("KIDS","KB_PYJAMA","REGULAR"),("KIDS","KB_SANDO SET","SUMMER"),
    ("KIDS","KB_SANDO","SUMMER"),("KIDS","KB_T-SHIRT F/S","PREWINTER"),
    ("KIDS","KB_R/N T-SHIRT H/S","SUMMER"),("KIDS","KB_POLO T-SHIRT H/S","SUMMER"),("KIDS","KB_Y_CTN TROUSER","REGULAR"),
    ("KIDS","KB_Y_JEANS","REGULAR"),("KIDS","KBW_BABA SUIT","LT WINTER"),
    ("KIDS","KBW_JACKET","HVY WINTER"),("KIDS","KBW_PULLOVER","LT WINTER"),
    ("KIDS","KBW_PYJAMA","LT WINTER"),("KIDS","KBW_THERMAL LOWER","LT WINTER"),
    ("KIDS","KBW_THERMAL UPPER","LT WINTER"),("KIDS","KBW_TRACK SUIT","LT WINTER"),
    ("KIDS","KBW_WINTER T-SHIRT","LT WINTER"),("KIDS","KG_CAPRI SET","SUMMER"),
    ("KIDS","KG_CAPRI","SUMMER"),("KIDS","KG_DANGRI F/S","PREWINTER"),
    ("KIDS","KG_DRESS","REGULAR"),("KIDS","KG_FANCY_FROCK","OCCASIONAL"),
    ("KIDS","KG_FROCK F/S","PREWINTER"),("KIDS","KG_FROCK","SUMMER"),
    ("KIDS","KG_HIPSTER SET F/S","PREWINTER"),("KIDS","KG_HOT PANT SET","SUMMER"),
    ("KIDS","KG_HOT PANT","SUMMER"),("KIDS","KG_IN_PANTY","REGULAR"),
    ("KIDS","KG_IN_VEST","REGULAR"),("KIDS","KG_J_JEANS","REGULAR"),
    ("KIDS","KG_KURTI","REGULAR"),("KIDS","KG_LEGGING SET","REGULAR"),
    ("KIDS","KG_LEGGING","REGULAR"),("KIDS","KG_NIGHT SUIT","REGULAR"),
    ("KIDS","KG_PALAZZO","REGULAR"),("KIDS","KG_PARALLEL","REGULAR"),
    ("KIDS","KG_SALWAR SUIT","REGULAR"),("KIDS","KG_SKIRT TOP SET","SUMMER"),
    ("KIDS","KG_SKIRT","SUMMER"),("KIDS","KG_TEES F/S","PREWINTER"),
    ("KIDS","KG_TEES","SUMMER"),("KIDS","KG_T-TOP F/S","PREWINTER"),
    ("KIDS","KG_T-TOP","SUMMER"),("KIDS","KG_Y_JEANS","REGULAR"),
    ("KIDS","KGW_HIPSTER SET","LT WINTER"),("KIDS","KGW_JACKET","HVY WINTER"),
    ("KIDS","KGW_PYJAMA","LT WINTER"),("KIDS","KGW_WINTER TOP","LT WINTER"),
    ("KIDS","KI_AP_BABA SUIT DANGRI H/S","SUMMER"),("KIDS","KI_AP_BABA SUIT DNM F/S","PREWINTER"),
    ("KIDS","KI_AP_BABA SUIT DNM H/S","SUMMER"),("KIDS","KI_AP_BABA SUIT HSR F/S","PREWINTER"),
    ("KIDS","KI_AP_BABA SUIT HSR H/S","SUMMER"),("KIDS","KI_AP_BABA SUIT NEW BORN  F/S","PREWINTER"),
    ("KIDS","KI_AP_BABA SUIT NEW BORN H/S","SUMMER"),("KIDS","KI_AP_BABA SUIT TXTL H/S","SUMMER"),
    ("KIDS","KI_AP_CAPRI SET","SUMMER"),("KIDS","KI_AP_CAPRI","SUMMER"),
    ("KIDS","KI_AP_CASUAL SHIRT F/S","PREWINTER"),("KIDS","KI_AP_CASUAL SHIRT H/S","SUMMER"),
    ("KIDS","KI_AP_DANGRI_F/S","PREWINTER"),("KIDS","KI_AP_FANCY_FROCK","OCCASIONAL"),
    ("KIDS","KI_AP_FROCK F/S","PREWINTER"),("KIDS","KI_AP_FROCK","SUMMER"),
    ("KIDS","KI_AP_HALF PANT","SUMMER"),("KIDS","KI_AP_HIPSTER SET F/S","PREWINTER"),
    ("KIDS","KI_AP_HOT PANT SET","SUMMER"),("KIDS","KI_AP_HOT PANT","SUMMER"),
    ("KIDS","KI_AP_INDO WESTERN","OCCASIONAL"),("KIDS","KI_AP_JEANS","REGULAR"),
    ("KIDS","KI_AP_NEW BORN FROCK","SUMMER"),("KIDS","KI_AP_NEW BORN GIRLS SET","SUMMER"),
    ("KIDS","KI_AP_NIGHT SUIT","REGULAR"),("KIDS","KI_AP_PYJAMA","PREWINTER"),
    ("KIDS","KI_AP_SANDO","SUMMER"),("KIDS","KI_AP_SKIRT TOP SET","SUMMER"),
    ("KIDS","KI_AP_SKIRT","SUMMER"),("KIDS","KI_AP_TOP F/S","PREWINTER"),
    ("KIDS","KI_AP_TOP H/S","SUMMER"),("KIDS","KI_AP_TROUSER","REGULAR"),
    ("KIDS","KI_AP_T-SHIRT F/S","PREWINTER"),("KIDS","KI_AP_T-SHIRT H/S","SUMMER"),
    ("KIDS","KI_IN_BLOOMER","REGULAR"),("KIDS","KI_IN_GIFT SET","REGULAR"),
    ("KIDS","KI_IN_VEST","REGULAR"),("KIDS","KIW_BLANKET","HVY WINTER"),
    ("KIDS","KIW_BOYS JACKET","HVY WINTER"),("KIDS","KIW_GIFT SET","LT WINTER"),
    ("KIDS","KIW_GIRLS JACKET","HVY WINTER"),("KIDS","KIW_HIPSTER SET","LT WINTER"),
    ("KIDS","KIW_PULLOVER","LT WINTER"),("KIDS","KIW_PYJAMA","LT WINTER"),
    ("KIDS","KIW_VEST","LT WINTER"),("KIDS","KIW_WINTER BABA_SUIT","LT WINTER"),
    ("KIDS","KIW_WINTER TOP","LT WINTER"),("KIDS","KIW_WINTER T-SHIRT","LT WINTER"),
    ("KIDS","KW_MIX","HVY WINTER"),("KIDS","RAINCOAT","OCCASIONAL"),
    # LADIES
    ("LADIES","L_EW_BLOUSE","OCCASIONAL"),("LADIES","L_EW_DRESS FABRIC","REGULAR"),
    ("LADIES","L_EW_DUPATTA","REGULAR"),("LADIES","L_EW_KURTI S/L","REGULAR"),
    ("LADIES","L_EW_KURTI SET","REGULAR"),("LADIES","L_EW_KURTI","REGULAR"),
    ("LADIES","L_EW_LEGGING","REGULAR"),("LADIES","L_EW_LEHANGA","OCCASIONAL"),
    ("LADIES","L_EW_MIX","REGULAR"),("LADIES","L_EW_NIGHT SUIT","REGULAR"),
    ("LADIES","L_EW_NIGHTY","REGULAR"),("LADIES","L_EW_PETTICOAT","REGULAR"),
    ("LADIES","L_EW_SALWAR SUIT","OCCASIONAL"),("LADIES","L_EW_SALWAR","REGULAR"),
    ("LADIES","L_EW_SAREE_COTTON","OCCASIONAL"),("LADIES","L_EW_SAREE_FNCY","OCCASIONAL"),
    ("LADIES","L_EW_SAREE_JAIPURI","OCCASIONAL"),("LADIES","L_EW_SAREE_PRINTED","OCCASIONAL"),
    ("LADIES","L_EW_SAREE_SILK","OCCASIONAL"),("LADIES","L_EW_SAREE_TANT","OCCASIONAL"),
    ("LADIES","L_EW_SHORT KURTA","REGULAR"),("LADIES","L_IN_BRA","REGULAR"),("LADIES","L_IN_SPRT BRA","REGULAR"),
    ("LADIES","L_IN_PANTY","REGULAR"),("LADIES","L_IN_SLIPS","REGULAR"),
    ("LADIES","LW_L_CAPRI","SUMMER"),("LADIES","LW_L_CULOTTES","REGULAR"),
    ("LADIES","LW_L_HAREM_DHOTI","REGULAR"),("LADIES","LW_L_JEANS","REGULAR"),
    ("LADIES","LW_L_DNM JOGGER","REGULAR"),("LADIES","LW_L_WVN JOGGER","REGULAR"),
    ("LADIES","LW_L_WES PALAZZO","REGULAR"),("LADIES","LW_L_ETH PALAZZO","REGULAR"),
    ("LADIES","LW_L_PARALLEL","REGULAR"),("LADIES","LW_L_PYJAMA","REGULAR"),
    ("LADIES","LW_L_SETS","REGULAR"),("LADIES","LW_L_SHORTS","SUMMER"),
    ("LADIES","LW_L_SKIRT","SUMMER"),("LADIES","LW_L_TROUSER","REGULAR"),
    ("LADIES","LW_U_ACCESSORIES","SUMMER"),("LADIES","LW_U_CROP TEES","SUMMER"),
    ("LADIES","LW_U_DRESS","REGULAR"),("LADIES","LW_U_ETHNIC DRESS","REGULAR"),
    ("LADIES","LW_U_F.O TOP","REGULAR"),("LADIES","LW_U_RAINCOAT","OCCASIONAL"),
    ("LADIES","LW_U_SETS","REGULAR"),("LADIES","LW_U_TEES F/S","PREWINTER"),
    ("LADIES","LW_U_TEES","SUMMER"),("LADIES","LW_U_T-TOP F/S","PREWINTER"),
    ("LADIES","LW_U_T-TOP","REGULAR"),("LADIES","LWW_BLAZER","HVY WINTER"),
    ("LADIES","LWW_CARDIGAN","HVY WINTER"),("LADIES","LWW_JACKET","HVY WINTER"),
    ("LADIES","LWW_KURTI SET","HVY WINTER"),("LADIES","LWW_KURTI","HVY WINTER"),
    ("LADIES","LWW_LEGGING","LT WINTER"),("LADIES","LWW_MIX","HVY WINTER"),
    ("LADIES","LWW_NIGHT SUIT","HVY WINTER"),("LADIES","LWW_NIGHTY","HVY WINTER"),
    ("LADIES","LWW_PYJAMA","HVY WINTER"),("LADIES","LWW_SHAWL","HVY WINTER"),
    ("LADIES","LWW_THERMAL LOWER","HVY WINTER"),("LADIES","LWW_THERMAL UPPER","HVY WINTER"),
    ("LADIES","LWW_TRACK SUIT","HVY WINTER"),("LADIES","LWW_WINDCHEATER","LT WINTER"),
    ("LADIES","LWW_WINTER TOP","LT WINTER"),("LADIES","LWW_WINTER T-SHIRT","LT WINTER"),
    # MENS
    ("MENS","FABRIC-SUITING","REGULAR"),("MENS","M_IN_BRIEF","REGULAR"),
    ("MENS","M_IN_VEST","REGULAR"),("MENS","ME_BLAZER S/L","OCCASIONAL"),
    ("MENS","ME_BLAZER SUIT","OCCASIONAL"),("MENS","ME_BLAZER","HVY WINTER"),
    ("MENS","ME_INDO WESTERN","REGULAR"),("MENS","ME_KURTA PYJAMA","OCCASIONAL"),
    ("MENS","ME_KURTA","REGULAR"),("MENS","ME_PYJAMA","REGULAR"),
    ("MENS","ML_CASUAL TROUSER","REGULAR"),("MENS","ML_CORDROY TROUSER","REGULAR"),
    ("MENS","ML_FORMAL TROUSER","REGULAR"),("MENS","ML_JEANS","REGULAR"),
    ("MENS","ML_JOGGERS","REGULAR"),("MENS","MSE_BERMUDA","SUMMER"),
    ("MENS","MSE_BOXER","SUMMER"),("MENS","MSE_JAMAICAN","SUMMER"),
    ("MENS","MSE_MIX","REGULAR"),("MENS","MSE_POLO T-SHIRT H/S","SUMMER"),
    ("MENS","MSE_HSR PYJAMA","REGULAR"),("MENS","MSE_TXTL PYJAMA","REGULAR"),("MENS","MSE_R/N T-SHIRT H/S","SUMMER"),
    ("MENS","MSE_RAINCOAT","OCCASIONAL"),("MENS","MSE_SANDO","SUMMER"),
    ("MENS","MSE_T-SHIRT F/S","PREWINTER"),("MENS","MU_CASUAL SHIRT F/S","REGULAR"),
    ("MENS","MU_CASUAL SHIRT H/S","SUMMER"),("MENS","MU_CORD SETS","SUMMER"),
    ("MENS","MU_FORMAL SHIRT F/S","REGULAR"),("MENS","MU_FORMAL SHIRT H/S","SUMMER"),
    ("MENS","MU_KNITTED SHIRT H/S","SUMMER"),("MENS","MU_PARTY WEAR SHIRT F/S","REGULAR"),
    ("MENS","MU_SEMI CASUAL SHIRT F/S","REGULAR"),("MENS","MU_SHACKET","REGULAR"),
    ("MENS","MW_BLAZER S/L","LT WINTER"),("MENS","MW_JACKET S/L","LT WINTER"),
    ("MENS","MW_JACKET","HVY WINTER"),("MENS","MW_MIX","HVY WINTER"),
    ("MENS","MW_PULLOVER S/L","LT WINTER"),("MENS","MW_PULLOVER","LT WINTER"),
    ("MENS","MW_PYJAMA","LT WINTER"),("MENS","MW_SHACKET","LT WINTER"),
    ("MENS","MW_THERMAL LOWER","HVY WINTER"),("MENS","MW_THERMAL UPPER","HVY WINTER"),
    ("MENS","MW_TRACK-SUIT","HVY WINTER"),("MENS","MW_WINDCHEATER","LT WINTER"),
    ("MENS","MW_WINTER T-SHIRT S/L","LT WINTER"),("MENS","MW_WINTER T-SHIRT","LT WINTER"),
]

CUSTOM_PATH = os.path.join(os.path.dirname(__file__), "department_custom.json")
STATE_PATH  = os.path.join(os.path.dirname(__file__), "department_state.json")


def _load_custom() -> list:
    if os.path.exists(CUSTOM_PATH):
        with open(CUSTOM_PATH) as f:
            return json.load(f)
    return []


def _save_custom(entries: list):
    with open(CUSTOM_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def _load_state() -> dict:
    """Returns {division: {dept: {active, contrib_pct}}}"""
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _build_master() -> dict:
    """Returns {division: [{name, attribute, source}]}"""
    master: dict = {}
    for div, dept, attr in _MASTER_RAW:
        master.setdefault(div, [])
        master[div].append({"name": dept, "attribute": attr, "source": "master"})
    for entry in _load_custom():
        div = entry["division"]
        master.setdefault(div, [])
        master[div].append({"name": entry["name"], "attribute": entry["attribute"], "source": "custom"})
    return master


def _merge_state(master: dict, state: dict) -> dict:
    """Merge saved active/contrib state into master; compute default equal contrib for active depts."""
    result = {}
    for div, depts in master.items():
        div_state = state.get(div, {})
        active_depts = []
        rows = []
        for d in depts:
            ds = div_state.get(d["name"], {})
            active = ds.get("active", True)
            rows.append({
                "name": d["name"],
                "attribute": d["attribute"],
                "source": d["source"],
                "active": active,
                "contrib_pct": ds.get("contrib_pct", None),
            })
            if active:
                active_depts.append(d["name"])

        # Fill missing contrib_pct with equal distribution
        n = len(active_depts)
        default_pct = round(100.0 / n, 4) if n else 0.0

        for row in rows:
            if row["contrib_pct"] is None:
                row["contrib_pct"] = default_pct if row["active"] else 0.0

        result[div] = rows
    return result


def _get_full_config():
    master = _build_master()
    state  = _load_state()
    return _merge_state(master, state)


# ── Pydantic models ───────────────────────────────────────────────────────────

class DeptToggle(BaseModel):
    division: str
    name: str
    active: bool


class DeptContrib(BaseModel):
    division: str
    name: str
    contrib_pct: float


class DeptContribBatch(BaseModel):
    updates: list[DeptContrib]


class NewDepartment(BaseModel):
    division: str
    name: str
    attribute: str


class DivisionAOP(BaseModel):
    division: str
    annual_target: float  # total division AOP in Lakhs


class CalculateInput(BaseModel):
    division_aops: list[DivisionAOP]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _contrib_sum(rows: list) -> float:
    return round(sum(r["contrib_pct"] for r in rows if r["active"]), 4)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/config")
def get_config():
    config = _get_full_config()
    summary = {}
    for div, rows in config.items():
        active = [r for r in rows if r["active"]]
        summary[div] = {
            "total_depts": len(rows),
            "active_depts": len(active),
            "contrib_sum": _contrib_sum(rows),
        }
    return {"divisions": config, "summary": summary}


@router.post("/toggle")
def toggle_department(payload: DeptToggle):
    state = _load_state()
    state.setdefault(payload.division, {})
    state[payload.division].setdefault(payload.name, {})
    state[payload.division][payload.name]["active"] = payload.active

    # Rebalance contrib_pct for active depts in this division
    master = _build_master()
    all_rows = master.get(payload.division, [])
    dept_states = state[payload.division]
    active_names = [d["name"] for d in all_rows if dept_states.get(d["name"], {}).get("active", True)]
    n = len(active_names)
    if n:
        default = round(100.0 / n, 4)
        for name in active_names:
            if "contrib_pct" not in dept_states.get(name, {}):
                state[payload.division].setdefault(name, {})["contrib_pct"] = default

    _save_state(state)
    return {"ok": True}


@router.post("/contrib")
def update_contrib(payload: DeptContribBatch):
    state = _load_state()
    for u in payload.updates:
        state.setdefault(u.division, {})
        state[u.division].setdefault(u.name, {})
        state[u.division][u.name]["contrib_pct"] = u.contrib_pct
    _save_state(state)
    config = _get_full_config()
    summary = {}
    for div, rows in config.items():
        active = [r for r in rows if r["active"]]
        summary[div] = {"contrib_sum": _contrib_sum(rows), "active_depts": len(active)}
    return {"ok": True, "summary": summary}


@router.post("/auto-balance")
def auto_balance(payload: dict):
    division = payload.get("division")
    state = _load_state()
    master = _build_master()

    divs = [division] if division else list(master.keys())
    for div in divs:
        all_rows = master.get(div, [])
        div_state = state.get(div, {})
        active_names = [d["name"] for d in all_rows if div_state.get(d["name"], {}).get("active", True)]
        n = len(active_names)
        if n:
            eq = round(100.0 / n, 4)
            state.setdefault(div, {})
            for name in active_names:
                state[div].setdefault(name, {})["contrib_pct"] = eq

    _save_state(state)
    return {"ok": True}


@router.post("/add-department")
def add_department(payload: NewDepartment):
    custom = _load_custom()
    # Guard duplicate
    existing = [(e["division"], e["name"]) for e in custom]
    master_names = [(d, n) for d, n, _ in _MASTER_RAW]
    key = (payload.division.upper(), payload.name.upper())
    if key in [(e[0].upper(), e[1].upper()) for e in existing + master_names]:
        return {"ok": False, "error": "Department already exists"}
    custom.append({"division": payload.division, "name": payload.name, "attribute": payload.attribute})
    _save_custom(custom)
    return {"ok": True}


@router.post("/calculate")
def calculate(payload: CalculateInput):
    config = _get_full_config()
    results = []
    for daop in payload.division_aops:
        div = daop.division
        rows = config.get(div, [])
        active = [r for r in rows if r["active"]]
        total_pct = sum(r["contrib_pct"] for r in active)
        dept_breakdown = []
        for r in active:
            effective_pct = (r["contrib_pct"] / total_pct * 100) if total_pct else 0.0
            sales = round(daop.annual_target * r["contrib_pct"] / 100, 2)
            dept_breakdown.append({
                "name": r["name"],
                "attribute": r["attribute"],
                "contrib_pct": r["contrib_pct"],
                "effective_pct": round(effective_pct, 4),
                "sales_lakhs": sales,
            })
        results.append({
            "division": div,
            "annual_target": daop.annual_target,
            "contrib_sum": round(total_pct, 4),
            "dept_breakdown": dept_breakdown,
        })
    return {"results": results}


# ── Growth Matrix ─────────────────────────────────────────────────────────────
# 13 months × P1/P2 = 26 periods. Starts Mar'27, ends Mar'28.
# Default baseline = 100.0 (index, not %). Stored in department_growth.json.

GROWTH_PERIODS = []
_period_months = [
    "Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
    "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"
]
for _m in _period_months:
    GROWTH_PERIODS.append(f"{_m} P1")
    GROWTH_PERIODS.append(f"{_m} P2")

GROWTH_PATH = os.path.join(os.path.dirname(__file__), "department_growth.json")


def _load_growth() -> dict:
    if os.path.exists(GROWTH_PATH):
        with open(GROWTH_PATH) as f:
            return json.load(f)
    return {}


def _save_growth(data: dict):
    with open(GROWTH_PATH, "w") as f:
        json.dump(data, f, indent=2)


# 127.0.0.1, not localhost: on Windows 'localhost' tries IPv6 first and each call waited ~10 s (deep check 2026-09-26).
AOP_FORECASTER_BASE = os.environ.get("AOP_FORECASTER_URL", "http://127.0.0.1:8000")
BIS_DIVISIONS = ("KIDS", "LADIES", "MENS")   # BIS covers these only; GM / RETAIL growth is entered in Sales Plan


def _fetch_buyer_growth_live(division: str, strict: bool = False) -> list[dict]:
    """Live pull from Buyer's Input Sheet (via AOP Forecaster's shared-DB
    endpoint — see Tentative AOP Forecaster/db/buyer_department_growth.py).
    Called on every GET, not cached: this is the "automatic, live" half of
    the integration, matching the equally-live AOP-Forecaster-to-BIS sync.
    Never raises — AOP Forecaster being down just means no buyer overlay
    this request, same graceful-degradation as sync_from_aop_forecaster."""
    import urllib.error
    import urllib.request
    url = f"{AOP_FORECASTER_BASE}/api/config/buyer-department-growth?division={division}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read()).get("rows", [])
    except Exception as e:
        if strict:   # a plan run must not quietly fall back to 0% growth (deep check 2026-09-26)
            raise RuntimeError(f"Buyer's Input growth for {division} is unavailable (AOP Forecaster at "
                               f"{AOP_FORECASTER_BASE} unreachable: {e}) - the plan was not run, so it isn't made at 0% growth.")
        return []


def _get_growth_matrix(division: str, strict: bool = False) -> tuple[list, list]:
    """Returns ([{name, attribute, periods: {period: float}, buyer_periods:
    [period]}], buyer_months) for a division. Any period the buyer has
    actually entered in BIS overrides the saved/manual value for BOTH P1 and
    P2 of that month (same growth % floated across the fortnight split BIS
    itself doesn't have) and is flagged in buyer_periods so the frontend can
    mark it read-only. buyer_months is every month label (e.g. "Apr'27")
    with at least one buyer value anywhere in the division — the set the
    frontend hides all other months against, per the standing instruction
    that a month stays hidden until real work has landed in Buyer's Input."""
    master = _build_master()
    depts  = master.get(division, [])
    saved  = _load_growth().get(division, {})
    state  = _load_state().get(division, {})

    buyer_rows = _fetch_buyer_growth_live(division, strict)
    # {dept_name: {month_label: growth_pct}}
    buyer_by_dept: dict[str, dict[str, float]] = {}
    buyer_months: set[str] = set()
    for r in buyer_rows:
        buyer_by_dept.setdefault(r["department"], {})[r["month"]] = r["growth_pct"]
        buyer_months.add(r["month"])

    result = []
    for d in depts:
        dept_vals  = saved.get(d["name"], {})
        buyer_vals = buyer_by_dept.get(d["name"], {})
        periods = {p: dept_vals.get(p, 100.0) for p in GROWTH_PERIODS}
        buyer_periods = []
        for month, growth_pct in buyer_vals.items():
            index_val = 100.0 + growth_pct
            for suffix in (" P1", " P2"):
                p = month + suffix
                if p in periods:
                    periods[p] = index_val
                    buyer_periods.append(p)
        result.append({
            "name": d["name"], "attribute": d["attribute"],
            "periods": periods, "buyer_periods": buyer_periods,
            # Department Master status (user, 2026-09-26: an inactive department is greyed out in the matrix)
            "active": state.get(d["name"], {}).get("active", True),
        })
    return result, sorted(buyer_months)


def live_growth_matrix() -> dict:
    """{division: {dept: {period: index}}} - exactly what the Growth Matrix screen shows (saved values with BIS's
    live growth on P1 and P2 of each BIS month). The plan engines read this, so BIS growth reaches the plan itself,
    not just the screen (user, 2026-09-26; before, they read only department_growth.json, which was {}).
    Only departments with a BIS or saved value are listed; the engines give the rest 100 per department as before,
    and a division average (non-SSG / NSO stores) is no longer pulled down by the KLM departments BIS doesn't have.
    Raises if BIS growth can't be fetched for a BIS division, so a plan is never run at 0% by accident."""
    saved = _load_growth()
    out = {}
    for div in _build_master():
        rows, _ = _get_growth_matrix(div, strict=div in BIS_DIVISIONS)
        out[div] = {d["name"]: d["periods"] for d in rows if d["buyer_periods"] or d["name"] in saved.get(div, {})}
    return out


class GrowthUpdate(BaseModel):
    division: str
    updates: dict  # {dept_name: {period: value}}


@router.get("/growth-matrix/{division}")
def get_growth_matrix(division: str):
    departments, buyer_months = _get_growth_matrix(division.upper())
    return {
        "division": division,
        "periods": GROWTH_PERIODS,
        "departments": departments,
        "buyer_available_months": buyer_months,
    }


@router.post("/growth-matrix")
def save_growth_matrix(payload: GrowthUpdate):
    growth = _load_growth()
    growth.setdefault(payload.division, {})
    for dept_name, period_vals in payload.updates.items():
        growth[payload.division].setdefault(dept_name, {})
        growth[payload.division][dept_name].update(period_vals)
    _save_growth(growth)
    return {"ok": True, "saved": len(payload.updates)}


@router.post("/growth-matrix/reset")
def reset_growth_matrix(payload: dict):
    division = payload.get("division")
    growth   = _load_growth()
    if division:
        growth.pop(division, None)
    else:
        growth = {}
    _save_growth(growth)
    return {"ok": True}


BUYER_UPLOAD_META_PATH = os.path.join(os.path.dirname(__file__), "..", "buyer_upload_meta.json")

def _load_buyer_meta() -> dict:
    if os.path.exists(BUYER_UPLOAD_META_PATH):
        with open(BUYER_UPLOAD_META_PATH) as f:
            return json.load(f)
    return {}

def _save_buyer_meta(meta: dict):
    with open(BUYER_UPLOAD_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


@router.get("/buyer-upload-meta")
def get_buyer_upload_meta():
    return _load_buyer_meta()


@router.post("/growth-matrix/import")
async def import_buyer_growth(
    file: UploadFile = File(...),
    division: str = Form(...),
):
    """
    Accepts an Excel or CSV file from the buyer.
    Expected format — one row per department, columns:
      Department | <period1> | <period2> | ...
    Period column headers must match GROWTH_PERIODS exactly, e.g. "Apr'27 P1".
    Any unrecognised columns are silently ignored.
    """
    content = await file.read()
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
    except Exception as e:
        return {"ok": False, "error": f"Could not parse file: {e}"}

    # Normalise column names
    df.columns = [str(c).strip() for c in df.columns]

    # Find department column (first column, or one named "Department")
    dept_col = df.columns[0]
    for candidate in df.columns:
        if candidate.lower() in ("department", "dept", "department name"):
            dept_col = candidate
            break

    valid_periods = set(GROWTH_PERIODS)
    period_cols = [c for c in df.columns if c in valid_periods]

    if not period_cols:
        return {"ok": False, "error": "No matching period columns found. Columns must match period names like \"Apr'27 P1\"."}

    growth = _load_growth()
    div_upper = division.upper()
    growth.setdefault(div_upper, {})

    updated = 0
    skipped = 0
    for _, row in df.iterrows():
        dept_name = str(row[dept_col]).strip().upper()
        if not dept_name or dept_name == "NAN":
            continue
        growth[div_upper].setdefault(dept_name, {})
        for p in period_cols:
            val = row[p]
            try:
                growth[div_upper][dept_name][p] = float(val)
                updated += 1
            except (ValueError, TypeError):
                skipped += 1

    _save_growth(growth)

    import datetime
    meta = _load_buyer_meta()
    meta[div_upper] = {
        "filename": file.filename,
        "uploaded_at": datetime.datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "periods_updated": len(period_cols),
        "depts_updated": len(df),
    }
    _save_buyer_meta(meta)

    return {
        "ok": True,
        "division": div_upper,
        "depts_processed": len(df),
        "values_updated": updated,
        "values_skipped": skipped,
        "periods_matched": period_cols,
    }


@router.post("/sync-from-buyer")
def sync_from_buyer():
    """
    Mark KIDS / LADIES / MENS departments active or inactive from the LIVE Buyer's Input Sheet: a department BIS
    plans (has growth in the live buyer_department_growth lever) → active; one it doesn't → inactive. GM / RETAIL
    are untouched (BIS doesn't cover them). Contribution % is preserved. Returns counts of activated / deactivated.
    2026-09-26: this read mrp_plan.json, a 24-Aug file (86/48/35 active vs 96/57/39 in live BIS).
    """
    from fastapi import HTTPException
    try:
        buyer_depts = {div: {r["department"] for r in _fetch_buyer_growth_live(div, strict=True)} for div in BIS_DIVISIONS}
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    if not any(buyer_depts.values()):
        raise HTTPException(400, "Buyer's Input has no departments yet - open BIS once so it syncs its plan.")

    state = _load_state()
    master = _build_master()

    activated = deactivated = 0

    for div, dept_rows in master.items():
        if div not in buyer_depts:
            continue
        div_buyer = buyer_depts[div]
        div_state = state.setdefault(div, {})
        for row in dept_rows:
            dept = row["name"]
            was_active = div_state.get(dept, {}).get("active", True)
            now_active = dept in div_buyer
            entry = div_state.setdefault(dept, {})
            entry["active"] = now_active
            if "contrib_pct" not in entry:
                entry["contrib_pct"] = None
            if now_active and not was_active:
                activated += 1
            elif not now_active and was_active:
                deactivated += 1

    _save_state(state)
    return {
        "ok": True,
        "activated": activated,
        "deactivated": deactivated,
        "active": {div: len(buyer_depts[div]) for div in BIS_DIVISIONS},
        "message": f"Synced from Buyer's Input — active KIDS {len(buyer_depts['KIDS'])}, LADIES {len(buyer_depts['LADIES'])}, "
                   f"MENS {len(buyer_depts['MENS'])} ({activated} activated, {deactivated} deactivated; GM / RETAIL unchanged).",
    }


# ── AOP Forecaster integration ─────────────────────────────────────────────────
# Real pipeline link (not just a navigation shortcut): pulls the latest
# persisted forecast run's division-level annual AOP target (Rs Lakhs) from
# the AOP Forecaster app (Tentative AOP Forecaster, port 8000 by default,
# rs_planning Postgres underneath) and hands it back in exactly the shape
# POST /api/department-plan/calculate expects ({division, annual_target}) —
# nothing here auto-runs calculate(); the caller reviews then triggers it.
AOP_FORECASTER_URL = os.environ.get("AOP_FORECASTER_URL", "http://localhost:8000")
_AOP_SYNC_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "aop_forecaster_sync.json")


@router.get("/aop-forecaster-status")
def aop_forecaster_status():
    """Last cached sync-from-aop-forecaster result, if any — for the UI to show
    without re-fetching."""
    if not os.path.exists(_AOP_SYNC_CACHE_PATH):
        return {"synced": False}
    with open(_AOP_SYNC_CACHE_PATH) as f:
        return {"synced": True, **json.load(f)}


@router.post("/sync-from-aop-forecaster")
def sync_from_aop_forecaster():
    """Fetch GET {AOP_FORECASTER_URL}/api/config/division-aop-summary and cache
    it locally. Returns division_aops ready to pass straight into
    POST /api/department-plan/calculate as {"division_aops": [...]}."""
    import urllib.error
    import urllib.request
    from fastapi import HTTPException

    url = f"{AOP_FORECASTER_URL}/api/config/division-aop-summary"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(400, "AOP Forecaster has no persisted run yet — run it (session-from-db + run) first.")
        raise HTTPException(502, f"AOP Forecaster returned HTTP {e.code}")
    except Exception as e:
        raise HTTPException(502, f"Could not reach AOP Forecaster at {url}: {type(e).__name__}: {e}")

    cached = {
        "source_url": url, "run_id": payload["run_id"], "computed_at": payload["computed_at"],
        "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "division_aops": payload["division_aops"],
    }
    with open(_AOP_SYNC_CACHE_PATH, "w") as f:
        json.dump(cached, f, indent=2)
    return {"ok": True, **cached}


@router.get("/export")
def export_csv():
    config = _get_full_config()
    lines = ["Division,Department,Attribute,Status,Contribution %"]
    for div, rows in config.items():
        for r in rows:
            status = "Active" if r["active"] else "Inactive"
            lines.append(f"{div},{r['name']},{r['attribute']},{status},{r['contrib_pct']}")
    content = "\n".join(lines)
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=department_master.csv"},
    )
