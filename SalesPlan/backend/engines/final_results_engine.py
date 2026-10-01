"""
Final Results Engine
====================
Read-only endpoint. Loads the most-advanced plan available (base_corrected >
attr_corrected > final_dept) and returns:
  - pipeline status (which engines have run)
  - a human-readable remark string
  - store-level aggregated TY per division per month
"""
from fastapi import APIRouter, HTTPException
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engines.department_plan import _MASTER_RAW

# Divisions that have full dept-attribute breakdown vs item-master-only
ATTR_DIVISIONS   = {"KIDS", "LADIES", "MENS"}
NODEPT_DIVISIONS = {"GM", "RETAIL"}   # item master only — no dept corrections

# Build dept→attribute lookup once at import time
_DEPT_ATTR: dict = {}   # {div: {dept: attribute}}
for _div, _dept, _attr in _MASTER_RAW:
    _DEPT_ATTR.setdefault(_div, {})[_dept] = _attr

router = APIRouter()

_BASE             = os.path.dirname(__file__)
_FINAL_DEPT       = os.path.join(_BASE, "..", "final_dept_plan.json")
_ATTR_CORRECTED   = os.path.join(_BASE, "..", "attr_corrected_plan.json")
_BASE_CORRECTED   = os.path.join(_BASE, "..", "base_corrected_plan.json")
_DEPT_STATE       = os.path.join(_BASE, "department_state.json")
_MRP_PLAN         = os.path.join(_BASE, "mrp_plan.json")

TY_MONTHS = [
    "Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
    "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"
]


def _pipeline_status():
    has_master_setup = os.path.exists(_DEPT_STATE)
    has_mrp_synced   = os.path.exists(_MRP_PLAN)
    has_new_depts    = os.path.exists(_FINAL_DEPT)
    has_attr         = os.path.exists(_ATTR_CORRECTED)
    has_base         = os.path.exists(_BASE_CORRECTED)

    if has_base:
        active_file = _BASE_CORRECTED
        active_name = "base_corrected_plan.json"
    elif has_attr:
        active_file = _ATTR_CORRECTED
        active_name = "attr_corrected_plan.json"
    elif has_new_depts:
        active_file = _FINAL_DEPT
        active_name = "final_dept_plan.json"
    else:
        active_file = None
        active_name = None

    # Remark
    stages = []
    if has_new_depts:
        stages.append("New Depts")
    if has_attr:
        stages.append("Attr Correction")
    if has_base:
        stages.append("Base Correction")
    remark = " → ".join(stages) if stages else "No plan generated yet"

    return {
        "master_setup":   has_master_setup,
        "buyer_synced":   has_mrp_synced,
        "new_depts":      has_new_depts,
        "attr_correction": has_attr,
        "base_correction": has_base,
        "active_source":  active_name,
        "remark":         remark,
        "active_file":    active_file,
    }


def _aggregate_plan(plan: dict) -> dict:
    stores_out = []
    total_ty = 0.0
    ssg_count = 0
    nso_count = 0

    for store, info in plan.get("stores", {}).items():
        is_ssg   = info.get("is_ssg", False)
        tag      = info.get("tag", "")
        cluster  = info.get("cluster", "")
        ref      = info.get("ref_store", "")

        if is_ssg:
            ssg_count += 1
        else:
            nso_count += 1

        divs_out = {}
        store_total = 0.0

        for div, div_data in info.get("divisions", {}).items():
            months_map = div_data.get("months", {})
            monthly = {}
            div_total = 0.0
            for m in TY_MONTHS:
                m_data = months_map.get(m, {})
                ty   = m_data.get("div_total_ty", 0.0) or 0.0
                p1   = m_data.get("div_total_p1", ty / 2.0) or 0.0
                p2   = m_data.get("div_total_p2", ty / 2.0) or 0.0
                monthly[m] = {"total": ty, "p1": p1, "p2": p2}
                div_total += ty

            # Aggregate dept-level TY + LY across all months
            dept_agg = {}
            for m, m_data in months_map.items():
                for dept, d_data in m_data.get("departments", {}).items():
                    if not isinstance(d_data, dict):
                        continue
                    if not d_data.get("active", True):
                        continue
                    if dept not in dept_agg:
                        dept_agg[dept] = {"ty": 0.0, "ly": 0.0, "ty_p1": 0.0, "ty_p2": 0.0, "monthly": {}}
                    dept_agg[dept]["ty"]    += d_data.get("ty", 0.0) or 0.0
                    dept_agg[dept]["ly"]    += d_data.get("ly", 0.0) or 0.0
                    ty_val = d_data.get("ty", 0.0) or 0.0
                    dept_agg[dept]["ty_p1"] += d_data.get("ty_p1", ty_val / 2.0) or 0.0
                    dept_agg[dept]["ty_p2"] += d_data.get("ty_p2", ty_val / 2.0) or 0.0
                    dept_agg[dept]["monthly"][m] = {
                        "ty":   ty_val,
                        "ty_p1": d_data.get("ty_p1", ty_val / 2.0) or 0.0,
                        "ty_p2": d_data.get("ty_p2", ty_val / 2.0) or 0.0,
                        "ly":   d_data.get("ly", 0.0) or 0.0,
                    }

            depts_out = {}
            for dept, vals in dept_agg.items():
                ty_d, ly_d = vals["ty"], vals["ly"]
                if ly_d > 0:
                    growth = round((ty_d / ly_d - 1) * 100, 1)
                elif ty_d > 0:
                    growth = None   # new dept, no LY
                else:
                    growth = None
                depts_out[dept] = {
                    "ty":     ty_d,
                    "ty_p1":  vals["ty_p1"],
                    "ty_p2":  vals["ty_p2"],
                    "ly":     ly_d,
                    "growth": growth,
                    "monthly": vals["monthly"],
                }

            divs_out[div] = {
                "monthly":    monthly,
                "div_total":  div_total,
                "departments": depts_out,
            }
            store_total += div_total

        stores_out.append({
            "store":     store,
            "is_ssg":    is_ssg,
            "tag":       tag,
            "cluster":   cluster,
            "ref_store": ref,
            "divisions": divs_out,
            "store_total": store_total,
        })
        total_ty += store_total

    stores_out.sort(key=lambda x: (not x["is_ssg"], x["store"]))

    return {
        "total_stores": len(stores_out),
        "ssg_stores":   ssg_count,
        "nso_stores":   nso_count,
        "total_ty":     total_ty,
        "stores":       stores_out,
    }


@router.get("/status")
def get_pipeline_status():
    ps = _pipeline_status()
    return {
        "pipeline":      {k: ps[k] for k in ("master_setup","buyer_synced","new_depts","attr_correction","base_correction")},
        "active_source": ps["active_source"],
        "remark":        ps["remark"],
        "ready":         ps["active_file"] is not None,
    }


@router.get("/data")
def get_final_results():
    ps = _pipeline_status()
    if not ps["active_file"]:
        raise HTTPException(status_code=404, detail="No department plan has been generated yet.")

    with open(ps["active_file"]) as f:
        plan = json.load(f)

    agg = _aggregate_plan(plan)

    return {
        "pipeline":      {k: ps[k] for k in ("master_setup","buyer_synced","new_depts","attr_correction","base_correction")},
        "active_source": ps["active_source"],
        "remark":        ps["remark"],
        **agg,
    }


def _load_dept_attr_map() -> dict:
    """
    Returns {div: {dept_name: attribute}}.
    Starts from the hardcoded master, overlays any user-added custom depts.
    """
    import copy
    result = copy.deepcopy(_DEPT_ATTR)
    custom_path = os.path.join(os.path.dirname(__file__), "department_custom.json")
    if os.path.exists(custom_path):
        for entry in json.load(open(custom_path)):
            div  = entry.get("division", "")
            name = entry.get("name", "")
            attr = entry.get("attribute", "REGULAR")
            if div and name:
                result.setdefault(div, {})[name] = attr
    return result


@router.get("/dashboard")
def get_dashboard():
    ps = _pipeline_status()
    if not ps["active_file"]:
        raise HTTPException(status_code=404, detail="No department plan has been generated yet.")

    with open(ps["active_file"]) as f:
        plan = json.load(f)

    dept_attr = _load_dept_attr_map()

    divisions_out = {}

    for store, s_info in plan.get("stores", {}).items():
        is_ssg = s_info.get("is_ssg", False)
        for div, div_data in s_info.get("divisions", {}).items():
            if div not in divisions_out:
                divisions_out[div] = {
                    "ty": 0.0, "ly": 0.0,
                    "ssg_ty": 0.0, "nso_ty": 0.0,
                    "degrowth_stores": set(),
                    "attributes": {},
                    "has_attr": div in ATTR_DIVISIONS,
                }
            d = divisions_out[div]

            div_ty = 0.0
            div_ly = 0.0

            for m_data in div_data.get("months", {}).values():
                d["ty"] += m_data.get("div_total_ty", 0.0) or 0.0
                div_ty  += m_data.get("div_total_ty", 0.0) or 0.0

                for dept, dept_data in m_data.get("departments", {}).items():
                    if not isinstance(dept_data, dict) or not dept_data.get("active", True):
                        continue
                    dept_ty = dept_data.get("ty", 0.0) or 0.0
                    dept_ly = dept_data.get("ly", 0.0) or 0.0
                    div_ly += dept_ly

                    if div in ATTR_DIVISIONS:
                        attr = dept_attr.get(div, {}).get(dept, "REGULAR")
                        a = d["attributes"].setdefault(attr, {"ty": 0.0, "ly": 0.0})
                        a["ty"] += dept_ty
                        a["ly"] += dept_ly

            d["ly"] += div_ly
            if is_ssg:
                d["ssg_ty"] += div_ty
            else:
                d["nso_ty"] += div_ty

            # Track degrowth stores (store × div)
            if div_ty > 0 and div_ly > 0 and div_ty < div_ly:
                d["degrowth_stores"].add(store)

    # Serialise
    result = {}
    for div, d in divisions_out.items():
        ly, ty = d["ly"], d["ty"]
        growth = round((ty / ly - 1) * 100, 1) if ly > 0 else None

        attrs_out = {}
        for attr, av in d["attributes"].items():
            aly, aty = av["ly"], av["ty"]
            attrs_out[attr] = {
                "ty":     aty,
                "ly":     aly,
                "growth": round((aty / aly - 1) * 100, 1) if aly > 0 else None,
            }

        result[div] = {
            "ty":             ty,
            "ly":             ly,
            "ssg_ty":         d["ssg_ty"],
            "nso_ty":         d["nso_ty"],
            "growth":         growth,
            "degrowth_stores": len(d["degrowth_stores"]),
            "has_attr":       d["has_attr"],
            "attributes":     attrs_out,
        }

    return {
        "pipeline":      {k: ps[k] for k in ("master_setup","buyer_synced","new_depts","attr_correction","base_correction")},
        "active_source": ps["active_source"],
        "remark":        ps["remark"],
        "divisions":     result,
        "nodept_divisions": list(NODEPT_DIVISIONS),
    }
