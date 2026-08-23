"""
Department Sales Plan Engine
=============================
Breaks store-division TY targets down to department level.

SSG stores  (Tag ends with '- Stores', or listed in SSG_OVERRIDE_STORES):
    dept_TY = dept_LY × avg(P1_growth, P2_growth) / 100
    TY cont% re-derived from active dept values (sums to 100%)
    Inactive departments → TY = 0, excluded from total

Non-SSG stores (NSO, MAMJ-NSO, FY-tagged):
    TY cont% copied from their Ref Store (must be an SSG store)
    TY value = cont% × store_div_TY_total
    where store_div_TY_total = LY_div_total × avg_division_growth / 100
    LY_div_total: from "Store Actuals" sheet; falls back to summing dept actuals
    when absent/zero (fixes stores like AJL absent from the sheet).

Data required in inputs.xlsx:
    Sheet "Dept Actuals" — header row 1
    Columns: Store | Division | Department | Apr'26 | May'26 | … | Mar'27
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import io, json, os
import pandas as pd
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from actuals_manager import (
    load_actuals, locked_ly_months, available_ty_months,
    import_actuals_file, admin_unlock_month, load_lock,
    ACTUALS_DIR,
)
from store_master import load_store_master as _universal_store_master, is_ssg as _universal_is_ssg

router = APIRouter()

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE     = os.path.dirname(__file__)
AOP_INPUTS = os.path.abspath(os.path.join(_BASE, "..", "..", "..", "Tentative AOP Forecaster", "inputs.xlsx"))
DEPT_STATE_PATH    = os.path.join(_BASE, "..", "department_state.json")
DEPT_CUSTOM_PATH   = os.path.join(_BASE, "..", "department_custom.json")
DEPT_GROWTH_PATH   = os.path.join(_BASE, "..", "department_growth.json")
NEW_DEPT_MAP_PATH  = os.path.join(_BASE, "..", "new_dept_mapping.json")
FINAL_PLAN_PATH    = os.path.join(_BASE, "..", "final_dept_plan.json")

# Auto-sync source for New Departments file
NEW_DEPT_SOURCE_DIR  = r"C:\Users\A9820\Documents\CLaude - New Projects\SalesPlan\New Departments"
NEW_DEPT_SOURCE_NAME = "NEW Departments.xlsx"
NEW_DEPT_SOURCE_PATH = os.path.join(NEW_DEPT_SOURCE_DIR, NEW_DEPT_SOURCE_NAME)

# ── Constants ─────────────────────────────────────────────────────────────────
DIVISIONS = ["GM", "KIDS", "LADIES", "MENS", "RETAIL"]

# Full plan range: Mar'27 → Mar'28 (13 months) with corresponding LY
TY_MONTHS  = ["Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
              "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"]
LY_MONTHS  = ["Mar'26","Apr'26","May'26","Jun'26","Jul'26","Aug'26",
              "Sep'26","Oct'26","Nov'26","Dec'26","Jan'27","Feb'27","Mar'27"]
MONTH_PAIR = list(zip(TY_MONTHS, LY_MONTHS))

# Keep FY28_MONTHS alias for export compatibility
FY28_MONTHS = TY_MONTHS

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_ssg(tag: str, store: str = "") -> bool:
    return _universal_is_ssg(tag, store)


def _norm(s) -> str:
    return str(s).strip().upper()


# ── Data Loaders ──────────────────────────────────────────────────────────────

def _load_store_master():
    """Returns [{Store, Ref Store, Cluster, Tag}] from the universal Store Master."""
    return list(_universal_store_master())


def _load_dept_actuals():
    """
    Reads from actuals_store.json (populated by actuals_manager.import_actuals_file).
    Returns (actuals_dict, ly_months_available).
    Only months that are locked are returned.
    """
    actuals = load_actuals()
    ly_locked = locked_ly_months()
    return actuals, ly_locked


def _load_store_div_actuals():
    """
    Store × Division × Month LY actuals from 'Store Actuals' sheet.
    Returns {store: {division: {ly_month: value}}}
    """
    try:
        df = pd.read_excel(AOP_INPUTS, sheet_name="Store Actuals", header=2)
        df.columns = [str(c).strip() for c in df.columns]
        col0, col1 = df.columns[0], df.columns[1]
        df = df[df[col0].notna() & (df[col0].astype(str).str.strip() != "Store")]
        df = df[~df[col0].astype(str).str.contains("Values pulled", na=True)]
        df.rename(columns={col0: "Store", col1: "Division"}, inplace=True)

        ly_cols = [c for c in LY_MONTHS if c in df.columns]
        result = {}
        for _, row in df.iterrows():
            store = _norm(row["Store"])
            div   = _norm(row["Division"])
            result.setdefault(store, {}).setdefault(div, {})
            for m in ly_cols:
                val = row.get(m, 0)
                try:
                    result[store][div][m] = float(val) if pd.notna(val) else 0.0
                except (ValueError, TypeError):
                    result[store][div][m] = 0.0
        return result
    except Exception:
        return {}


def _load_new_dept_map() -> dict:
    """Returns {division: {new_dept: {ref_dept, alloc_pct}}}"""
    if os.path.exists(NEW_DEPT_MAP_PATH):
        with open(NEW_DEPT_MAP_PATH) as f:
            return json.load(f)
    return {}


def _save_new_dept_map(data: dict):
    with open(NEW_DEPT_MAP_PATH, "w") as f:
        json.dump(data, f, indent=2)


def apply_new_dept_adjustments(plan_result: dict, new_dept_map: dict) -> dict:
    """
    Post-calculation pass: two independent % controls per new dept entry.
      new_dept_ty  = ref_dept_ty × new_dept_pct / 100
      ref_dept_ty  = ref_dept_ty × (1 - ref_reduction_pct / 100)
    These are intentionally independent — division totals may shift.
    Backward-compat: old entries with only alloc_pct use it for both.
    Applied store-by-store, month-by-month.
    """
    if not new_dept_map:
        return plan_result

    import copy
    result = copy.deepcopy(plan_result)

    for store, sdata in result["stores"].items():
        for div, entries in new_dept_map.items():
            div_data = sdata["divisions"].get(div, {})
            for ty_month, month_data in div_data.get("months", {}).items():
                depts = month_data["departments"]
                for new_dept, cfg in entries.items():
                    ref_dept = cfg["ref_dept"]
                    # Support both old alloc_pct and new split fields
                    legacy = float(cfg.get("alloc_pct", 0))
                    new_dept_pct      = float(cfg.get("new_dept_pct",      legacy)) / 100.0
                    ref_reduction_pct = float(cfg.get("ref_reduction_pct", legacy)) / 100.0
                    if new_dept_pct == 0 and ref_reduction_pct == 0:
                        continue
                    ref_d = depts.get(ref_dept)
                    if ref_d is None or not ref_d.get("active", True):
                        continue
                    ref_ty   = ref_d.get("ty", 0.0)
                    ref_cont = ref_d.get("cont_pct", 0.0)
                    # New dept gains new_dept_pct of ref
                    carve_ty   = round(ref_ty   * new_dept_pct, 4)
                    carve_cont = round(ref_cont * new_dept_pct, 4)
                    # Ref dept loses ref_reduction_pct (independent)
                    reduce_ty   = round(ref_ty   * ref_reduction_pct, 4)
                    reduce_cont = round(ref_cont * ref_reduction_pct, 4)
                    depts[ref_dept]["ty"]       = round(ref_ty   - reduce_ty,   4)
                    depts[ref_dept]["cont_pct"] = round(ref_cont - reduce_cont, 4)
                    if new_dept in depts:
                        depts[new_dept]["ty"]       = round(depts[new_dept]["ty"]       + carve_ty,   4)
                        depts[new_dept]["cont_pct"] = round(depts[new_dept]["cont_pct"] + carve_cont, 4)
                    else:
                        depts[new_dept] = {
                            "ly": 0.0, "ty": carve_ty, "growth_pct": None,
                            "cont_pct": carve_cont, "active": True, "is_new": True,
                            "ref_dept": ref_dept,
                            "new_dept_pct": cfg.get("new_dept_pct", legacy),
                            "ref_reduction_pct": cfg.get("ref_reduction_pct", legacy),
                        }

    return result


def _load_growth_matrix():
    """
    Returns {division: {dept: {period: float}}} from saved JSON.
    """
    if os.path.exists(DEPT_GROWTH_PATH):
        with open(DEPT_GROWTH_PATH) as f:
            return json.load(f)
    return {}


def _load_dept_config():
    """
    Returns {division: [{name, active}]} merging master + custom + state.
    Imports _build_master from department_plan to avoid duplication.
    """
    from engines.department_plan import _build_master
    return _build_master()


def _growth_p1_p2(growth_matrix, div, dept, ty_month):
    dept_data = growth_matrix.get(div, {}).get(dept, {})
    g_p1 = float(dept_data.get(f"{ty_month} P1", 100.0))
    g_p2 = float(dept_data.get(f"{ty_month} P2", 100.0))
    return g_p1, g_p2

def _avg_monthly_growth(growth_matrix, div, dept, ty_month):
    """
    Returns average of P1 and P2 growth % for a dept in a given TY month.
    Falls back to 100.0 (no growth) if not found.
    """
    g_p1, g_p2 = _growth_p1_p2(growth_matrix, div, dept, ty_month)
    return (g_p1 + g_p2) / 2.0


def _avg_division_growth(growth_matrix, div, ty_month):
    """
    Division-level average growth for a month — used for non-SSG stores.
    Averages growth across all departments in the division for that month.
    Falls back to 100.0.
    """
    dept_growths = growth_matrix.get(div, {})
    if not dept_growths:
        return 100.0
    vals = []
    p1_key = f"{ty_month} P1"
    p2_key = f"{ty_month} P2"
    for dept_periods in dept_growths.values():
        p1 = float(dept_periods.get(p1_key, 100.0))
        p2 = float(dept_periods.get(p2_key, 100.0))
        vals.append((p1 + p2) / 2.0)
    return sum(vals) / len(vals) if vals else 100.0


# ── Core Calculation ──────────────────────────────────────────────────────────

def run_dept_plan():
    """
    Returns:
      {
        "stores": {
          store_code: {
            "tag": str,
            "is_ssg": bool,
            "ref_store": str,
            "divisions": {
              div: {
                "months": {
                  ty_month: {
                    "div_total_ty": float,
                    "departments": {
                      dept: {
                        "ly": float,
                        "ty": float,
                        "growth_pct": float,   # effective monthly growth applied
                        "cont_pct": float,     # TY contribution % within div
                        "active": bool
                      }
                    }
                  }
                }
              }
            }
          }
        },
        "meta": {
          "ssg_count": int,
          "non_ssg_count": int,
          "dept_actuals_loaded": bool,
          "missing_ref_stores": [str]
        }
      }
    """
    store_master   = _load_store_master()
    dept_actuals, ly_locked = _load_dept_actuals()
    store_div_acts = _load_store_div_actuals()
    growth_matrix  = _load_growth_matrix()
    dept_config    = _load_dept_config()

    dept_actuals_loaded = bool(dept_actuals)

    # Only compute months where LY actuals are locked
    # ly_locked e.g. ["Mar'26","Apr'26","May'26","Jun'26"]
    # active_pairs = [(TY_month, LY_month)] filtered to locked LY months only
    active_pairs = [(ty, ly) for ty, ly in MONTH_PAIR if ly in ly_locked]
    active_ty_months = [ty for ty, _ in active_pairs]

    # Build active dept sets per division
    active_depts = {}
    for div, rows in dept_config.items():
        active_depts[div] = {r["name"] for r in rows if r.get("active", True)}

    # Build store lookup
    store_info = {}
    for s in store_master:
        store_info[s["Store"]] = s

    ssg_stores = {s for s, info in store_info.items() if _is_ssg(info.get("Tag", ""), s)}
    missing_ref = []

    results_ssg = {}

    # ── Step 1: SSG stores ────────────────────────────────────────────────────
    for store in ssg_stores:
        results_ssg[store] = {}
        for div in DIVISIONS:
            active = active_depts.get(div, set())
            months_out = {}

            for ty_month, ly_month in active_pairs:   # only locked months
                store_dept_data = dept_actuals.get(store, {}).get(div, {})
                dept_vals = {}

                for dept in active:
                    ly_val = store_dept_data.get(dept, {}).get(ly_month, 0.0)
                    g_p1, g_p2 = _growth_p1_p2(growth_matrix, div, dept, ty_month)
                    g = (g_p1 + g_p2) / 2.0
                    ly_half = ly_val / 2.0
                    ty_p1 = round(ly_half * g_p1 / 100.0, 4)
                    ty_p2 = round(ly_half * g_p2 / 100.0, 4)
                    ty_val = round(ty_p1 + ty_p2, 4)
                    dept_vals[dept] = {
                        "ly": ly_val, "ly_p1": round(ly_half, 4), "ly_p2": round(ly_half, 4),
                        "ty": ty_val, "ty_p1": ty_p1, "ty_p2": ty_p2,
                        "growth_pct": g, "g_p1": g_p1, "g_p2": g_p2,
                        "active": True,
                    }

                # Add inactive depts (zero, not in total)
                all_depts = {r["name"] for r in dept_config.get(div, [])}
                for dept in all_depts - active:
                    ly_val = store_dept_data.get(dept, {}).get(ly_month, 0.0)
                    dept_vals[dept] = {
                        "ly": ly_val, "ly_p1": round(ly_val/2.0, 4), "ly_p2": round(ly_val/2.0, 4),
                        "ty": 0.0, "ty_p1": 0.0, "ty_p2": 0.0,
                        "growth_pct": 0.0, "g_p1": 0.0, "g_p2": 0.0, "active": False,
                    }

                # TY divisional total from active depts only
                div_total_ty = sum(v["ty"] for v in dept_vals.values() if v["active"])
                div_total_p1 = sum(v.get("ty_p1", v["ty"] / 2.0) for v in dept_vals.values() if v["active"])
                div_total_p2 = sum(v.get("ty_p2", v["ty"] / 2.0) for v in dept_vals.values() if v["active"])

                # Derive contribution %
                for dept, v in dept_vals.items():
                    if v["active"] and div_total_ty > 0:
                        v["cont_pct"] = round(v["ty"] / div_total_ty * 100, 4)
                    else:
                        v["cont_pct"] = 0.0

                months_out[ty_month] = {
                    "div_total_ty": round(div_total_ty, 4),
                    "div_total_p1": round(div_total_p1, 4),
                    "div_total_p2": round(div_total_p2, 4),
                    "departments": dept_vals,
                }

            results_ssg[store][div] = {"months": months_out}

    # ── Step 2: Non-SSG stores ────────────────────────────────────────────────
    results_non_ssg = {}

    for s_info in store_master:
        store = s_info["Store"]
        if _is_ssg(s_info.get("Tag", ""), store):
            continue

        ref = s_info.get("Ref Store", "")
        if ref not in results_ssg:
            missing_ref.append(store)
            ref_data = None
        else:
            ref_data = results_ssg[ref]

        results_non_ssg[store] = {}
        for div in DIVISIONS:
            active = active_depts.get(div, set())
            all_depts = {r["name"] for r in dept_config.get(div, [])}
            months_out = {}

            for ty_month, ly_month in active_pairs:   # only locked months
                # LY divisional total — prefer "Store Actuals" sheet; fall back to
                # summing dept-level actuals (fixes stores absent from that sheet).
                ly_div_total = store_div_acts.get(store, {}).get(div, {}).get(ly_month, 0.0)
                if ly_div_total == 0.0:
                    store_dept_acts = dept_actuals.get(store, {}).get(div, {})
                    ly_div_total = sum(
                        info.get(ly_month, 0.0)
                        for info in store_dept_acts.values()
                        if isinstance(info, dict)
                    )
                div_growth = _avg_division_growth(growth_matrix, div, ty_month)
                div_total_ty = ly_div_total * (div_growth / 100.0)

                dept_vals = {}

                if ref_data:
                    ref_month = ref_data.get(div, {}).get("months", {}).get(ty_month, {})
                    ref_depts  = ref_month.get("departments", {})
                    for dept in active:
                        ref_dept = ref_depts.get(dept, {})
                        cont_pct = ref_dept.get("cont_pct", 0.0)
                        ty_val   = div_total_ty * (cont_pct / 100.0)
                        g        = ref_dept.get("growth_pct", 100.0)
                        ly_implied = ly_div_total * (cont_pct / 100.0)
                        ref_p1 = ref_dept.get("ty_p1", ty_val / 2.0)
                        ref_p2 = ref_dept.get("ty_p2", ty_val / 2.0)
                        ref_ty = ref_dept.get("ty", ty_val) or ty_val
                        ty_p1 = round(ty_val * ref_p1 / ref_ty, 4) if ref_ty > 0 else round(ty_val / 2.0, 4)
                        ty_p2 = round(ty_val * ref_p2 / ref_ty, 4) if ref_ty > 0 else round(ty_val / 2.0, 4)
                        dept_vals[dept] = {
                            "ly": ly_implied, "ly_p1": round(ly_implied / 2.0, 4), "ly_p2": round(ly_implied / 2.0, 4),
                            "ty": round(ty_val, 4), "ty_p1": ty_p1, "ty_p2": ty_p2,
                            "growth_pct": g, "g_p1": ref_dept.get("g_p1", g), "g_p2": ref_dept.get("g_p2", g),
                            "cont_pct": round(cont_pct, 4),
                            "active": True,
                        }
                    for dept in all_depts - active:
                        dept_vals[dept] = {"ly": 0.0, "ly_p1": 0.0, "ly_p2": 0.0,
                                           "ty": 0.0, "ty_p1": 0.0, "ty_p2": 0.0,
                                           "growth_pct": 0.0, "g_p1": 0.0, "g_p2": 0.0,
                                           "cont_pct": 0.0, "active": False}
                else:
                    # No ref store — mark zero
                    for dept in all_depts:
                        dept_vals[dept] = {
                            "ly": 0.0, "ly_p1": 0.0, "ly_p2": 0.0,
                            "ty": 0.0, "ty_p1": 0.0, "ty_p2": 0.0,
                            "growth_pct": 100.0, "g_p1": 100.0, "g_p2": 100.0,
                            "cont_pct": 0.0, "active": dept in active,
                        }

                nsg_p1 = sum(v.get("ty_p1", v["ty"]/2.0) for v in dept_vals.values() if v.get("active"))
                nsg_p2 = sum(v.get("ty_p2", v["ty"]/2.0) for v in dept_vals.values() if v.get("active"))
                months_out[ty_month] = {
                    "div_total_ty": round(div_total_ty, 4),
                    "div_total_p1": round(nsg_p1, 4),
                    "div_total_p2": round(nsg_p2, 4),
                    "departments": dept_vals,
                }

            results_non_ssg[store][div] = {"months": months_out}

    # Merge both
    all_results = {}
    for s, data in {**results_ssg, **results_non_ssg}.items():
        info = store_info.get(s, {})
        all_results[s] = {
            "tag": info.get("Tag", ""),
            "is_ssg": _is_ssg(info.get("Tag", ""), s),
            "ref_store": info.get("Ref Store", ""),
            "cluster": info.get("Cluster", ""),
            "divisions": data,
        }

    return {
        "stores": all_results,
        "meta": {
            "ssg_count": len(results_ssg),
            "non_ssg_count": len(results_non_ssg),
            "dept_actuals_loaded": dept_actuals_loaded,
            "missing_ref_stores": list(set(missing_ref)),
            "ly_months_locked": ly_locked,
            "ty_months_active": active_ty_months,
        },
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

# ── Actuals & Lock Endpoints ──────────────────────────────────────────────────

@router.get("/actuals/status")
def actuals_status():
    """Returns lock registry + which TY months are available in the UI."""
    lock = load_lock()
    return {
        "locked_ly_months": lock["locked_ly_months"],
        "available_ty_months": available_ty_months(),
        "unlock_log_count": len(lock.get("unlock_log", [])),
    }


@router.post("/actuals/import-from-dir")
def import_from_dir():
    """
    Scans the Actual Sales folder and imports any Excel files not yet locked.
    Safe to call repeatedly — already-locked months are skipped.
    """
    if not os.path.isdir(ACTUALS_DIR):
        return {"ok": False, "error": f"Actuals directory not found: {ACTUALS_DIR}"}

    files = [
        os.path.join(ACTUALS_DIR, f)
        for f in os.listdir(ACTUALS_DIR)
        if f.endswith((".xlsx", ".xls", ".csv")) and not f.startswith("~")
    ]

    if not files:
        return {"ok": False, "error": "No Excel/CSV files found in Actual Sales folder"}

    results = []
    for fp in sorted(files):
        r = import_actuals_file(fp)
        r["file"] = os.path.basename(fp)
        results.append(r)

    return {"ok": True, "files_processed": len(files), "results": results}


@router.post("/actuals/admin-unlock/{ly_month}")
async def admin_unlock(ly_month: str, request: Request, reason: str = ""):
    """
    ADMIN ONLY — removes lock for a LY month and deletes its actuals data.
    Requires header: X-Admin-Override: force
    Not exposed in any UI. Only callable by Claude explicitly.
    Every call is journaled in actuals_lock.json → unlock_log.
    """
    override = request.headers.get("X-Admin-Override", "")
    if override.strip().lower() != "force":
        raise HTTPException(
            status_code=403,
            detail="This endpoint is admin-only. Requires header: X-Admin-Override: force"
        )
    return admin_unlock_month(ly_month, reason=reason)


# ── Plan Endpoints ────────────────────────────────────────────────────────────

@router.get("/new-depts")
def get_new_depts():
    """Returns the new-dept mapping: {division: {new_dept: {ref_dept, alloc_pct}}}"""
    return _load_new_dept_map()


@router.post("/new-depts")
async def save_new_depts(request: Request):
    """
    Saves the new-dept mapping.
    Body: {division: {new_dept: {ref_dept, new_dept_pct, ref_reduction_pct}}}
    Both % fields are unlimited (>100 allowed). No upper cap.
    Backward-compat: accepts old alloc_pct field.
    """
    body = await request.json()
    for div, entries in body.items():
        if div not in DIVISIONS:
            raise HTTPException(status_code=422, detail=f"Unknown division: {div}")
        for new_dept, cfg in entries.items():
            if "ref_dept" not in cfg:
                raise HTTPException(status_code=422, detail=f"Entry {new_dept} missing ref_dept")
            has_pct = "new_dept_pct" in cfg or "ref_reduction_pct" in cfg or "alloc_pct" in cfg
            if not has_pct:
                raise HTTPException(status_code=422, detail=f"Entry {new_dept} missing % fields")
            # Negative % allowed — carve or boost logic handled in apply_new_dept_adjustments
            pass
    _save_new_dept_map(body)
    # Compute and persist the final plan immediately so it's ready for downstream use
    try:
        base = run_dept_plan()
        final = apply_new_dept_adjustments(base, body)
        with open(FINAL_PLAN_PATH, "w") as f:
            json.dump(final, f)
        finalized = True
    except Exception:
        finalized = False
    return {"ok": True, "saved": sum(len(v) for v in body.values()), "plan_finalized": finalized}


@router.delete("/new-depts")
def clear_new_depts():
    """
    Clears the new-dept mapping and deletes all downstream plan files
    (final_dept_plan, attr_corrected_plan, base_corrected_plan).
    """
    _BASE_DIR = os.path.join(_BASE, "..")
    removed = []
    # Clear mapping
    if os.path.exists(NEW_DEPT_MAP_PATH):
        with open(NEW_DEPT_MAP_PATH, "w") as f:
            json.dump({}, f)
        removed.append("new_dept_mapping.json")
    # Remove downstream plan files so Final Results reflects the cleared state
    for fname in ("final_dept_plan.json", "attr_corrected_plan.json", "base_corrected_plan.json"):
        p = os.path.join(_BASE_DIR, fname)
        if os.path.exists(p):
            os.remove(p)
            removed.append(fname)
    return {"ok": True, "cleared": removed}


@router.get("/new-depts/sync-status")
def get_new_depts_sync_status():
    """Check if the New Departments source file is available on disk."""
    if not os.path.exists(NEW_DEPT_SOURCE_PATH):
        return {"file_found": False, "file_date": None, "size_kb": None, "path": NEW_DEPT_SOURCE_PATH}
    st = os.stat(NEW_DEPT_SOURCE_PATH)
    import datetime
    return {
        "file_found": True,
        "file_date": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "size_kb": round(st.st_size / 1024, 1),
        "path": NEW_DEPT_SOURCE_PATH,
    }


@router.post("/new-depts/sync")
def sync_new_depts():
    """
    Read NEW Departments.xlsx from the source folder, parse it, infer divisions
    from the ref dept lookup, build new_dept_mapping.json, and regenerate the plan.

    File columns: NEW MC | REF. MC | Mar P1 | Mar P2 | Apr P1 | Apr P2 | ...
    Values are decimal fractions (0.5 = 50%). Division is looked up from the
    existing dept actuals / state config; falls back to prefix heuristics.
    """
    if not os.path.exists(NEW_DEPT_SOURCE_PATH):
        raise HTTPException(status_code=404, detail=f"Source file not found: {NEW_DEPT_SOURCE_PATH}")

    # --- Parse the Excel file ---
    try:
        df = pd.read_excel(NEW_DEPT_SOURCE_PATH, header=0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read file: {e}")

    df.columns = [str(c).strip() for c in df.columns]

    # Find NEW MC and REF MC columns (flexible matching)
    new_col = next((c for c in df.columns if "new" in c.lower() and "mc" in c.lower()), None)
    ref_col = next((c for c in df.columns if "ref" in c.lower() and "mc" in c.lower()), None)
    if not new_col or not ref_col:
        raise HTTPException(status_code=422, detail=f"Could not find NEW MC / REF. MC columns. Got: {list(df.columns)}")

    # Month abbreviation → TY month (Mar'27 etc.)
    _MONTH_MAP = {
        "mar": "Mar'27", "apr": "Apr'27", "may": "May'27", "jun": "Jun'27",
        "june": "Jun'27", "jul": "Jul'27", "aug": "Aug'27", "sep": "Sep'27",
        "sept": "Sep'27", "oct": "Oct'27", "nov": "Nov'27", "dec": "Dec'27",
        "jan": "Jan'28", "feb": "Feb'28",
    }

    # Identify period columns: "Mar P1", "Mar P2", "June P1" etc.
    import re as _re
    period_cols = {}  # col_name → TY period string "Mar'27 P1"
    for c in df.columns:
        m = _re.match(r"([A-Za-z]+)\s+(P[12])$", c.strip(), _re.IGNORECASE)
        if m:
            mon_raw, p = m.group(1).lower(), m.group(2).upper()
            ty_mon = _MONTH_MAP.get(mon_raw)
            if ty_mon:
                period_cols[c] = f"{ty_mon} {p}"

    if not period_cols:
        raise HTTPException(status_code=422, detail=f"No period columns found. Got: {list(df.columns)}")

    # --- Build division lookup from existing dept state/actuals ---
    # dept_state.json: {division: {dept_code: {...}}}
    dept_to_div: dict[str, str] = {}
    if os.path.exists(DEPT_STATE_PATH):
        try:
            with open(DEPT_STATE_PATH) as f:
                state = json.load(f)
            for div, depts in state.items():
                if isinstance(depts, dict):
                    for d in depts:
                        dept_to_div[str(d).strip().upper()] = div
        except Exception:
            pass

    # Prefix heuristics as fallback
    _PREFIX_DIV = [
        ("KB_", "KIDS"), ("KG_", "KIDS"), ("KI_", "KIDS"), ("KBW_", "KIDS"), ("KGW_", "KIDS"),
        ("LWW_", "LADIES"), ("LW_", "LADIES"), ("L_", "LADIES"), ("LY_", "LADIES"),
        ("M_", "MENS"), ("MW_", "MENS"),
        ("GM_", "GM"), ("RT_", "RETAIL"),
    ]

    def _infer_div(dept_code: str) -> str:
        upper = dept_code.strip().upper()
        if upper in dept_to_div:
            return dept_to_div[upper]
        for prefix, div in _PREFIX_DIV:
            if upper.startswith(prefix):
                return div
        return "UNKNOWN"

    # --- Build the mapping dict ---
    mapping: dict[str, dict] = {}
    errors = []
    for _, row in df.iterrows():
        new_dept = str(row[new_col]).strip() if pd.notna(row[new_col]) else ""
        ref_dept = str(row[ref_col]).strip() if pd.notna(row[ref_col]) else ""
        if not new_dept or not ref_dept or new_dept.lower() in ("nan", "") or ref_dept.lower() in ("nan", ""):
            continue

        # Average allocation across all period columns (convert decimal → %)
        pct_vals = []
        for col in period_cols:
            v = row.get(col)
            if pd.notna(v):
                try:
                    pct_vals.append(float(v) * 100.0)
                except (ValueError, TypeError):
                    pass

        if not pct_vals:
            errors.append(f"No allocation values for {new_dept}")
            continue

        avg_pct = round(sum(pct_vals) / len(pct_vals), 2)
        div = _infer_div(ref_dept)

        if div not in mapping:
            mapping[div] = {}
        mapping[div][new_dept] = {
            "ref_dept": ref_dept,
            "new_dept_pct": avg_pct,
            "ref_reduction_pct": avg_pct,
        }

    if not mapping:
        raise HTTPException(status_code=422, detail=f"No valid rows parsed. Errors: {errors}")

    # --- Save and regenerate plan ---
    _save_new_dept_map(mapping)

    try:
        base = run_dept_plan()
        final = apply_new_dept_adjustments(base, mapping)
        with open(FINAL_PLAN_PATH, "w") as f:
            json.dump(final, f)
        # Invalidate downstream stale files
        _BASE_DIR = os.path.join(_BASE, "..")
        for fname in ("attr_corrected_plan.json", "base_corrected_plan.json"):
            p = os.path.join(_BASE_DIR, fname)
            if os.path.exists(p):
                os.remove(p)
        plan_ok = True
        store_count = len(final.get("stores", {}))
    except Exception as e:
        plan_ok = False
        store_count = 0

    total_entries = sum(len(v) for v in mapping.values())
    import datetime
    return {
        "ok": True,
        "file_date": datetime.datetime.fromtimestamp(os.stat(NEW_DEPT_SOURCE_PATH).st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "divisions": list(mapping.keys()),
        "total_entries": total_entries,
        "period_columns": list(period_cols.values()),
        "errors": errors,
        "plan_regenerated": plan_ok,
        "stores": store_count,
    }


@router.post("/generate-base")
def generate_base_plan():
    """
    Runs the base department plan (growth-matrix only, no new-dept adjustments)
    and writes final_dept_plan.json. Also clears any stale downstream files so
    Attr Correction and Base Correction know they need to re-run.
    """
    _BASE_DIR = os.path.join(_BASE, "..")
    plan = run_dept_plan()
    # Apply new-dept mapping if one exists (empty mapping = no change)
    new_dept_map = _load_new_dept_map()
    final = apply_new_dept_adjustments(plan, new_dept_map)
    with open(FINAL_PLAN_PATH, "w") as f:
        json.dump(final, f)
    # Invalidate downstream optional engines
    stale_cleared = []
    for fname in ("attr_corrected_plan.json", "base_corrected_plan.json"):
        p = os.path.join(_BASE_DIR, fname)
        if os.path.exists(p):
            os.remove(p)
            stale_cleared.append(fname)
    store_count = len(final.get("stores", {}))
    return {"ok": True, "stores": store_count, "stale_cleared": stale_cleared}


@router.get("/run")
def run_plan():
    base = run_dept_plan()
    new_dept_map = _load_new_dept_map()
    return apply_new_dept_adjustments(base, new_dept_map)


@router.get("/final-plan")
def get_final_plan():
    """
    Returns the last finalized plan (written by POST /new-depts → Save & Apply).
    Falls back to live run if not yet finalized.
    """
    if os.path.exists(FINAL_PLAN_PATH):
        with open(FINAL_PLAN_PATH) as f:
            return json.load(f)
    # Not yet finalized — compute on the fly
    base = run_dept_plan()
    new_dept_map = _load_new_dept_map()
    return apply_new_dept_adjustments(base, new_dept_map)


@router.get("/store/{store_code}/{division}")
def get_store_division(store_code: str, division: str):
    """Preview one store × division breakdown."""
    result = run_dept_plan()
    store_data = result["stores"].get(store_code.upper())
    if not store_data:
        return {"error": f"Store {store_code} not found"}
    div_data = store_data["divisions"].get(division.upper())
    if not div_data:
        return {"error": f"Division {division} not found"}
    return {
        "store": store_code.upper(),
        "division": division.upper(),
        "is_ssg": store_data["is_ssg"],
        "ref_store": store_data["ref_store"],
        "tag": store_data["tag"],
        **div_data,
    }


@router.get("/meta")
def get_meta():
    """Quick health check — returns meta without full calc."""
    result = run_dept_plan()
    return result["meta"]


@router.get("/export")
def export_plan():
    """
    Exports full plan as Excel:
    Sheet 1 — Summary: Store | Division | Department | Month1 TY | … | Month12 TY
    Sheet 2 — Contribution: Store | Division | Department | Month1 Cont% | …
    """
    result = run_dept_plan()

    rows_val  = []
    rows_cont = []

    for store, sdata in result["stores"].items():
        for div in DIVISIONS:
            div_data = sdata["divisions"].get(div, {})
            months_data = div_data.get("months", {})

            # Collect all depts that appear
            all_depts = set()
            for m_data in months_data.values():
                all_depts.update(m_data.get("departments", {}).keys())

            for dept in sorted(all_depts):
                row_val  = {"Store": store, "Division": div, "Department": dept,
                            "Type": "SSG" if sdata["is_ssg"] else "Non-SSG",
                            "Ref Store": sdata["ref_store"]}
                row_cont = {"Store": store, "Division": div, "Department": dept,
                            "Type": "SSG" if sdata["is_ssg"] else "Non-SSG",
                            "Ref Store": sdata["ref_store"]}

                for ty_month in available_ty_months():
                    m_data = months_data.get(ty_month, {})
                    dept_d = m_data.get("departments", {}).get(dept, {})
                    row_val[ty_month]  = round(dept_d.get("ty", 0.0), 2)
                    row_cont[ty_month] = round(dept_d.get("cont_pct", 0.0), 4)

                rows_val.append(row_val)
                rows_cont.append(row_cont)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(rows_val).to_excel(writer, sheet_name="TY Values (Rs Lakhs)", index=False)
        pd.DataFrame(rows_cont).to_excel(writer, sheet_name="Contribution %", index=False)
        # Meta sheet
        meta_df = pd.DataFrame([result["meta"]])
        meta_df.to_excel(writer, sheet_name="Run Meta", index=False)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=dept_sales_plan.xlsx"},
    )


@router.get("/plan-summary")
def get_plan_summary():
    """
    Lightweight sidebar snapshot: Division → Month → {ty, ly, growth%}
    Also returns overall total and month list.
    """
    result = run_dept_plan()
    months = result["meta"]["ty_months_active"]
    divs: dict = {}

    for store, sdata in result["stores"].items():
        if not sdata.get("is_ssg"):
            continue
        for div, div_data in sdata.get("divisions", {}).items():
            if div not in divs:
                divs[div] = {m: {"ty": 0.0, "ly": 0.0} for m in months}
            for month, mdata in div_data.get("months", {}).items():
                if month not in divs[div]:
                    continue
                depts = mdata.get("departments", {})
                for dept_data in depts.values():
                    divs[div][month]["ty"] += dept_data.get("ty", 0.0)
                    divs[div][month]["ly"] += dept_data.get("ly", 0.0)

    # round and add growth
    summary = {}
    grand_ty = 0.0
    grand_ly = 0.0
    for div, month_data in divs.items():
        summary[div] = {}
        for m, vals in month_data.items():
            ty = round(vals["ty"], 2)
            ly = round(vals["ly"], 2)
            growth = round((ty - ly) / ly * 100, 1) if ly > 0 else None
            summary[div][m] = {"ty": ty, "ly": ly, "growth": growth}
            grand_ty += ty
            grand_ly += ly

    grand_growth = round((grand_ty - grand_ly) / grand_ly * 100, 1) if grand_ly > 0 else None
    return {
        "months": months,
        "divisions": summary,
        "grand_ty": round(grand_ty, 2),
        "grand_ly": round(grand_ly, 2),
        "grand_growth": grand_growth,
    }


@router.get("/cluster-plan")
def get_cluster_plan():
    """
    Aggregate the final department plan by Cluster instead of Store.

    For each Cluster × Division × Month × Department:
      ty_total   = sum of store TY values within the cluster
      ly_total   = sum of store LY values within the cluster
      cont_pct   = dept_ty_total / div_ty_total × 100  (re-derived, sums to 100% within div/month)

    Returns:
      {clusters: [...], divisions: [...], months: [...],
       result: {cluster → {division → {month → {dept → {ty, ly, cont_pct}}}}}}
    """
    from store_master import get_store_cluster_map, get_clusters

    plan = run_dept_plan()
    cluster_map = get_store_cluster_map()

    # Accumulate: cluster → div → month → dept → {ty, ly}
    acc: dict = {}
    for store, sdata in plan["stores"].items():
        cluster = cluster_map.get(store)
        if not cluster:
            continue
        cl_acc = acc.setdefault(cluster, {})
        for div, div_data in sdata["divisions"].items():
            div_acc = cl_acc.setdefault(div, {})
            for month, m_data in div_data["months"].items():
                mo_acc = div_acc.setdefault(month, {})
                for dept, dd in m_data.get("departments", {}).items():
                    dp = mo_acc.setdefault(dept, {"ty": 0.0, "ly": 0.0})
                    dp["ty"] += dd.get("ty",  0.0) or 0.0
                    dp["ly"] += dd.get("ly",  0.0) or 0.0

    # Re-derive cont_pct within each cluster/div/month
    result: dict = {}
    for cluster, divs in acc.items():
        result[cluster] = {}
        for div, months in divs.items():
            result[cluster][div] = {}
            for month, depts in months.items():
                div_ty_total = sum(d["ty"] for d in depts.values())
                result[cluster][div][month] = {}
                for dept, vals in depts.items():
                    result[cluster][div][month][dept] = {
                        "ty":       round(vals["ty"], 2),
                        "ly":       round(vals["ly"], 2),
                        "cont_pct": round(vals["ty"] / div_ty_total * 100, 4) if div_ty_total else 0.0,
                    }

    all_clusters = sorted(result.keys())
    all_divs     = sorted({d for cl in result.values() for d in cl.keys()})
    all_months   = available_ty_months()

    return {
        "clusters":  all_clusters,
        "divisions": all_divs,
        "months":    all_months,
        "result":    result,
    }


@router.get("/cluster-plan/export")
def export_cluster_plan():
    """Export cluster-aggregated plan as Excel."""
    data = get_cluster_plan()

    rows = []
    for cluster, divs in data["result"].items():
        for div, months in divs.items():
            all_depts = sorted({d for mo in months.values() for d in mo.keys()})
            for dept in all_depts:
                row = {"Cluster": cluster, "Division": div, "Department": dept}
                for month in data["months"]:
                    dd = months.get(month, {}).get(dept, {})
                    row[f"{month} TY"]      = round(dd.get("ty", 0.0), 2)
                    row[f"{month} Cont%"]   = round(dd.get("cont_pct", 0.0), 4)
                rows.append(row)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Cluster Plan", index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=cluster_dept_plan.xlsx"},
    )
