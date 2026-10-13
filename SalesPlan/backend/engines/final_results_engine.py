"""
Final Results Engine
====================
Read-only. Which engines have run and the most-advanced plan file (base_corrected > attr_corrected > final_dept);
the page itself is the Hierarchy view (grain_view /hierarchy, 2026-10-13). Also the department -> attribute map.
"""
from fastapi import APIRouter
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engines.department_plan import _MASTER_RAW

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


@router.get("/pipeline")
def get_pipeline():
    """Which engines have run and which plan file is active - all the Final Results page needs besides the Hierarchy
    view (user, 2026-10-13: "remove multiple views just keep the hierarchial view"; the Store / Department / Cluster /
    Dashboard views and their /data + /dashboard routes - a 1.3 MB read of the whole plan file - are gone)."""
    ps = _pipeline_status()
    return {"pipeline": {k: ps[k] for k in ("master_setup", "buyer_synced", "new_depts", "attr_correction", "base_correction")},
            "active_source": ps["active_source"], "remark": ps["remark"]}




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
