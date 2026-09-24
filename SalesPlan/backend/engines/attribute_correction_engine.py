"""
Attribute Correction Engine
===========================
Optional post-processing engine — runs after New Department adjustments.
Allows adjusting ATTRIBUTE1 contribution % per division per month (SSG stores only).
Proportionally reapportions dept TYs within each attribute group.
Generates pre vs post comparison for audit.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import io, json, os, copy
import pandas as pd
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

router = APIRouter()

_BASE              = os.path.dirname(__file__)
ATTR_MASTER_PATH   = os.path.abspath(os.path.join(_BASE, "..", "..", "Attribute Master", "att master.xlsx"))
FINAL_PLAN_PATH    = os.path.join(_BASE, "..", "final_dept_plan.json")
CORRECTIONS_PATH   = os.path.join(_BASE, "..", "attr_corrections.json")
ATTR_PLAN_PATH     = os.path.join(_BASE, "..", "attr_corrected_plan.json")

# Map plan division → which master DIVISION values belong to it
PLAN_DIV_MASTERS = {
    "KIDS":   {"KIDS"},
    "LADIES": {"LADIES"},
    "MENS":   {"MENS"},
    "RETAIL": {"RETAIL"},
    "GM":     {
        "FOOTWEAR", "LIFESTYLE", "HOME FURNISHING", "HOUSEHOLD",
        "NON FOOD", "STATIONERY", "CDIT", "TRAVEL ACCESSORIES",
        "SPORTS  & TOYS", "SPORTS & TOYS", "CONSIGNMENT",
    },
}


# ── Module-level cache ────────────────────────────────────────────────────────

_cache: dict = {}   # keys: "plan", "attr_map", "aggregates", "preview_result"

def _mtime(path: str):
    # Attribute master's cache fingerprint: the shared DB table's (count,
    # max(updated_at)) while it is live, else the xlsx file's mtime.
    if path == ATTR_MASTER_PATH:
        sig = _attr_db("SELECT count(*), max(updated_at) FROM masterdata.attribute_master")
        if sig and sig[0][0]:
            return ("db", sig[0][0], str(sig[0][1]))
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return 0.0

def _cache_valid(key: str, *paths: str) -> bool:
    entry = _cache.get(key)
    if not entry:
        return False
    return all(entry["mtimes"].get(p, -1) == _mtime(p) for p in paths)

def _cache_set(key: str, value, *paths: str):
    _cache[key] = {"value": value, "mtimes": {p: _mtime(p) for p in paths}}

def _cache_get(key: str):
    return _cache[key]["value"]

def _cache_invalidate(*keys: str):
    for k in keys:
        _cache.pop(k, None)


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_final_plan():
    key = "plan"
    if _cache_valid(key, FINAL_PLAN_PATH):
        return _cache_get(key)
    if os.path.exists(FINAL_PLAN_PATH):
        with open(FINAL_PLAN_PATH) as f:
            plan = json.load(f)
        _cache_set(key, plan, FINAL_PLAN_PATH)
        return plan
    return None


def _load_corrections() -> dict:
    if os.path.exists(CORRECTIONS_PATH):
        with open(CORRECTIONS_PATH) as f:
            return json.load(f)
    return {}


def _save_corrections(data: dict):
    with open(CORRECTIONS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    _cache_invalidate("preview_result", "aggregates")


# ── Attribute master ──────────────────────────────────────────────────────────
# Source: shared Postgres masterdata.attribute_master (loaded from att master.xlsx
# by `Tentative AOP Forecaster/db/attribute_master.py`), same lazy db.base import
# as store_master.py. Falls back to the xlsx when the db layer is missing, the DB
# is unreachable, or the table is empty/absent.

def _attr_db(sql: str):
    """Rows of a read on the shared DB, or None if it can't be reached."""
    # ponytail: no failure memo - an unreachable-but-configured DB costs one connect
    # timeout per call; add a short negative cache if that ever bites (on 8010 auth
    # already needs this DB, so it would be down anyway).
    try:
        from sqlalchemy import text
        from db.base import engine
        with engine.connect() as c:
            return c.execute(text(sql)).fetchall()
    except Exception:
        return None


def _read_attr_master() -> pd.DataFrame:
    rows = _attr_db("SELECT division, section, department, attribute1 FROM masterdata.attribute_master")
    if rows:
        return pd.DataFrame([tuple(r) for r in rows], columns=["DIVISION", "SECTION", "DEPARTMENT", "ATTRIBUTE1"])
    return pd.read_excel(ATTR_MASTER_PATH)


def _get_attr_map_cached(active_dept_set: dict) -> dict:
    """Cache attr map keyed on attribute-master fingerprint (DB or xlsx) + active_dept_set hash."""
    import hashlib
    dept_sig = hashlib.md5(
        json.dumps(sorted((k, sorted(v)) for k, v in active_dept_set.items())).encode()
    ).hexdigest()
    key = f"attr_map_{dept_sig}"
    if _cache_valid(key, ATTR_MASTER_PATH):
        return _cache_get(key)
    result = _build_attr_dept_map(active_dept_set)
    _cache_set(key, result, ATTR_MASTER_PATH)
    return result


def _build_attr_dept_map(active_dept_set: dict) -> dict:
    """
    Returns {plan_div: {dept_code: attribute_name}}.
    Filtered to departments present and active in the plan.
    """
    try:
        df = _read_attr_master()
        df.columns = [str(c).strip() for c in df.columns]
        df = df[df["DEPARTMENT"].notna() & df["ATTRIBUTE1"].notna()]
        df["DEPARTMENT"] = df["DEPARTMENT"].astype(str).str.strip()
        df["ATTRIBUTE1"] = df["ATTRIBUTE1"].astype(str).str.strip()
        df["DIVISION"]   = df["DIVISION"].astype(str).str.strip().str.upper()
    except Exception:
        return {}

    # Build reverse map: master_div_upper → plan_div
    master_to_plan = {}
    for plan_div, master_divs in PLAN_DIV_MASTERS.items():
        for md in master_divs:
            master_to_plan[md.upper()] = plan_div

    result = {}
    for _, row in df.iterrows():
        plan_div = master_to_plan.get(row["DIVISION"])
        if not plan_div:
            continue
        dept = row["DEPARTMENT"]
        attr = row["ATTRIBUTE1"]
        if dept in active_dept_set.get(plan_div, set()):
            result.setdefault(plan_div, {})[dept] = attr

    return result


def _get_active_depts_from_plan(plan: dict) -> dict:
    """Return {plan_div: set(dept_codes)} for all depts that appear active in SSG stores."""
    active = {}
    for store, sdata in plan.get("stores", {}).items():
        if not sdata.get("is_ssg"):
            continue
        for div, div_data in sdata.get("divisions", {}).items():
            for month_data in div_data.get("months", {}).values():
                for dept, dinfo in month_data.get("departments", {}).items():
                    if dinfo.get("active"):
                        active.setdefault(div, set()).add(dept)
    return active


# ── Aggregation ───────────────────────────────────────────────────────────────

def compute_attr_aggregates(plan: dict, attr_map: dict) -> dict:
    """
    SSG stores only. Aggregates TY by attribute per division per month.
    Returns {div: {attr: {month: {ty, cont_pct}}}}
    """
    raw: dict[str, dict[str, dict[str, float]]] = {}
    div_month_totals: dict[str, dict[str, float]] = {}

    for store, sdata in plan.get("stores", {}).items():
        if not sdata.get("is_ssg"):
            continue
        for div, div_data in sdata.get("divisions", {}).items():
            dept_attr = attr_map.get(div, {})
            for month, month_data in div_data.get("months", {}).items():
                for dept, dinfo in month_data.get("departments", {}).items():
                    if not dinfo.get("active"):
                        continue
                    attr = dept_attr.get(dept)
                    if not attr:
                        continue
                    ty = dinfo.get("ty", 0.0)
                    raw.setdefault(div, {}).setdefault(attr, {})
                    raw[div][attr][month] = round(raw[div][attr].get(month, 0.0) + ty, 4)
                    div_month_totals.setdefault(div, {})
                    div_month_totals[div][month] = round(div_month_totals[div].get(month, 0.0) + ty, 4)

    result = {}
    for div, attrs in raw.items():
        result[div] = {}
        for attr, months in attrs.items():
            result[div][attr] = {}
            for month, ty in months.items():
                total = div_month_totals.get(div, {}).get(month, 0.0)
                cont_pct = round(ty / total * 100, 4) if total > 0 else 0.0
                result[div][attr][month] = {"ty": round(ty, 2), "cont_pct": cont_pct}

    return result


# ── Correction apply ──────────────────────────────────────────────────────────

def apply_attr_corrections(plan: dict, corrections: dict, attr_map: dict) -> dict:
    """
    corrections: {div: {month: {attr: cont_pct}}} — already balanced, sums to ~100.
    Proportionally scales dept TYs within each attribute group.
    Only touches SSG stores.
    """
    if not corrections:
        return plan

    result = copy.deepcopy(plan)

    for store, sdata in result.get("stores", {}).items():
        if not sdata.get("is_ssg"):
            continue
        for div, div_corrections in corrections.items():
            div_data = sdata.get("divisions", {}).get(div, {})
            dept_attr = attr_map.get(div, {})

            for month, attr_pcts in div_corrections.items():
                month_data = div_data.get("months", {}).get(month)
                if not month_data:
                    continue
                depts = month_data.get("departments", {})

                total_ty = sum(d.get("ty", 0.0) for d in depts.values() if d.get("active"))
                if total_ty <= 0:
                    continue

                # Group active dept TYs by attribute
                attr_dept_ty: dict[str, dict[str, float]] = {}
                for dept, dinfo in depts.items():
                    if not dinfo.get("active"):
                        continue
                    attr = dept_attr.get(dept)
                    if attr:
                        attr_dept_ty.setdefault(attr, {})[dept] = dinfo.get("ty", 0.0)

                # Apply each attribute's target cont%
                for attr, new_pct in attr_pcts.items():
                    if attr not in attr_dept_ty:
                        continue
                    target_ty = total_ty * new_pct / 100.0
                    old_ty = sum(attr_dept_ty[attr].values())
                    if old_ty <= 0:
                        continue
                    scale = target_ty / old_ty
                    for dept in attr_dept_ty[attr]:
                        depts[dept]["ty"] = round(depts[dept]["ty"] * scale, 4)
                        if "ty_p1" in depts[dept]:
                            depts[dept]["ty_p1"] = round(depts[dept]["ty_p1"] * scale, 4)
                        if "ty_p2" in depts[dept]:
                            depts[dept]["ty_p2"] = round(depts[dept]["ty_p2"] * scale, 4)

            # Recalculate cont_pcts for this store × div after all months corrected
            for month, month_data in div_data.get("months", {}).items():
                depts = month_data.get("departments", {})
                total_ty = sum(d.get("ty", 0.0) for d in depts.values() if d.get("active"))
                month_data["div_total_ty"] = round(total_ty, 4)
                month_data["div_total_p1"] = round(sum(d.get("ty_p1", 0.0) for d in depts.values() if d.get("active")), 4)
                month_data["div_total_p2"] = round(sum(d.get("ty_p2", 0.0) for d in depts.values() if d.get("active")), 4)
                for dept, dinfo in depts.items():
                    if dinfo.get("active"):
                        dinfo["cont_pct"] = round(dinfo.get("ty", 0.0) / total_ty * 100, 4) if total_ty > 0 else 0.0

    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/preview")
def get_preview():
    """
    Returns attribute grid data from final_dept_plan.json (pre-correction).
    {data: {div: {attr: {month: {ty, cont_pct}}}}, corrections, attr_dept_map, months}
    """
    plan = _load_final_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="Final plan not yet generated. Complete New Depts → Save & Apply first.")

    # Cache the expensive stable parts (plan + Excel) separately from corrections
    preview_key = "preview_static"
    if not _cache_valid(preview_key, FINAL_PLAN_PATH, ATTR_MASTER_PATH):
        active_depts = _get_active_depts_from_plan(plan)
        attr_map = _get_attr_map_cached(active_depts)
        data = compute_attr_aggregates(plan, attr_map)
        months = plan.get("meta", {}).get("ty_months_active", [])
        attr_dept_list: dict[str, dict[str, list]] = {}
        for div, dept_attr in attr_map.items():
            for dept, attr in dept_attr.items():
                attr_dept_list.setdefault(div, {}).setdefault(attr, []).append(dept)
        _cache_set(preview_key, {"data": data, "months": months, "attr_dept_map": attr_dept_list},
                   FINAL_PLAN_PATH, ATTR_MASTER_PATH)

    static = _cache_get(preview_key)
    corrections = _load_corrections()

    return {
        "data": static["data"],
        "corrections": corrections,
        "attr_dept_map": static["attr_dept_map"],
        "months": static["months"],
    }


@router.post("/save")
async def save_and_apply(request: Request):
    """
    Body: {div: {month: {attr: cont_pct}}} — balanced corrections.
    Saves, applies, writes attr_corrected_plan.json, returns pre+post comparison.
    """
    body = await request.json()
    plan = _load_final_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="Final plan not found.")
    active_depts = _get_active_depts_from_plan(plan)
    attr_map = _get_attr_map_cached(active_depts)

    _save_corrections(body)
    _cache_invalidate("preview_static")
    try:
        corrected = apply_attr_corrections(plan, body, attr_map)
        with open(ATTR_PLAN_PATH, "w") as f:
            json.dump(corrected, f)
        pre  = compute_attr_aggregates(plan, attr_map)
        post = compute_attr_aggregates(corrected, attr_map)
        months = plan.get("meta", {}).get("ty_months_active", [])
        return {"ok": True, "pre": pre, "post": post, "months": months}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comparison")
def get_comparison():
    """Returns pre vs post comparison using saved corrections."""
    plan = _load_final_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="Final plan not found.")
    active_depts = _get_active_depts_from_plan(plan)
    attr_map = _get_attr_map_cached(active_depts)
    corrections = _load_corrections()
    pre = compute_attr_aggregates(plan, attr_map)
    if corrections:
        corrected = apply_attr_corrections(plan, corrections, attr_map)
        post = compute_attr_aggregates(corrected, attr_map)
    else:
        post = pre
    months = plan.get("meta", {}).get("ty_months_active", [])
    return {"pre": pre, "post": post, "months": months, "has_corrections": bool(corrections)}
