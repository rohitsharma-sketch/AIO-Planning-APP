"""Store / Cluster view of the plan (user, 2026-10-12: "a switch in the planning engine for working as Cluster or Store
... give a vice versa preview on all stages - Division, Department, MRP or Display Type"). Step 1 = view only: the same
plan numbers, rolled up to clusters or listed by store; every cluster row carries its stores (the plan flowing down to
them) and every store row its cluster (what it rolls up to).

Source = the plan Final Results shows (base-corrected > attribute-corrected > generated base plan). When that file has no
months (not generated since the LY months closed) the live base-plan run is used instead, cached on its inputs like the
sidebar summary - every response says which (`source`). Values are Rs lakh, as in the plan files.
"""
import json
import os
import threading

from fastapi import APIRouter, HTTPException

from apportion import split

router = APIRouter()
NO_CLUSTER = "(no cluster)"
TY_MONTHS = ["Mar'27", "Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27", "Oct'27", "Nov'27", "Dec'27",
             "Jan'28", "Feb'28", "Mar'28"]
_HERE = os.path.dirname(os.path.abspath(__file__))
DT_RESULT = os.path.join(_HERE, "..", "dt_plan_result.json")
MRP_PLAN = os.path.join(_HERE, "mrp_plan.json")
_lock = threading.Lock()
_cache = {"key": None, "cube": None}


def build_cube(plan: dict, source: dict) -> dict:
    """The plan reduced to what the views need: per store its cluster; per division x store x month (LY, TY); per
    division x department x store x month (LY, TY, TY P1, TY P2). Active departments only (as MRP Output)."""
    stores, div, dept, months = {}, {}, {}, set()
    for s, sd in (plan.get("stores") or {}).items():
        stores[s] = {"cluster": sd.get("cluster") or NO_CLUSTER, "ssg": bool(sd.get("is_ssg")), "tag": sd.get("tag")}
        for dv, dd in (sd.get("divisions") or {}).items():
            for m, md in ((dd or {}).get("months") or {}).items():
                if not isinstance(md, dict):
                    continue
                months.add(m)
                tl = tt = 0.0
                for dp, x in (md.get("departments") or {}).items():
                    if not isinstance(x, dict) or not x.get("active", True):
                        continue
                    ly, ty = float(x.get("ly") or 0.0), float(x.get("ty") or 0.0)
                    p1 = float(x.get("ty_p1", ty / 2) or 0.0)
                    p2 = float(x.get("ty_p2", ty / 2) or 0.0)
                    tl, tt = tl + ly, tt + ty
                    dept.setdefault(dv, {}).setdefault(dp, {}).setdefault(s, {})[m] = (ly, ty, p1, p2)
                div.setdefault(dv, {}).setdefault(s, {})[m] = (tl, tt)
    return {"stores": stores, "div": div, "dept": dept, "months": [m for m in TY_MONTHS if m in months],
            "source": source}


def _cube() -> dict:
    """The active plan as a cube, cached on the file's mtime, or on the live run's inputs."""
    from engines.final_results_engine import _pipeline_status
    ps = _pipeline_status()
    with _lock:
        f = ps["active_file"]
        if f and os.path.exists(f):
            key = ("file", f, os.path.getmtime(f))
            if _cache["key"] == key:
                return _cache["cube"]
            with open(f, encoding="utf-8") as fh:
                c = build_cube(json.load(fh), {"kind": "saved", "name": ps["active_source"],
                                              "note": f"the saved plan ({ps['active_source']})"})
            if c["months"]:
                _cache.update(key=key, cube=c)
                return c
        from engines.dept_sales_engine import _plan_inputs_key, run_dept_plan
        key = ("live", _plan_inputs_key())
        if _cache["key"] != key:
            _cache.update(key=key, cube=build_cube(run_dept_plan(), {
                "kind": "live", "name": "live base plan",
                "note": "the live base plan - not generated yet (Generate Base Plan saves it; corrections apply after)"}))
        return _cache["cube"]


def _add(a: dict, b: dict) -> dict:
    """a += b for nested {field: number | {field: number}}"""
    for k, v in b.items():
        if isinstance(v, dict):
            _add(a.setdefault(k, {}), v)
        else:
            a[k] = a.get(k, 0.0) + v
    return a


def rows(per_store: dict, stores: dict, grain: str, months: list) -> dict:
    """per_store = {store: {month: {field: value}}} -> cluster rows (each with its stores) or store rows (each with its
    cluster's total). Every level adds up exactly: clusters = stores = total."""
    def store_row(s):
        ms = per_store[s]
        tot = {}
        for m in months:
            _add(tot, ms.get(m, {}))
        return {"key": s, "label": s, "cluster": stores.get(s, {}).get("cluster", NO_CLUSTER),
                "ssg": stores.get(s, {}).get("ssg", False), "tag": stores.get(s, {}).get("tag"),
                "months": {m: ms.get(m, {}) for m in months}, "total": tot}

    every = [store_row(s) for s in per_store]
    # stores with nothing in them (warehouses, dummy / e-com codes) are counted, not listed
    nz = lambda t: any((abs(v) > 1e-9) if not isinstance(v, dict) else nz(v) for v in t.values())   # noqa: E731
    srows = [r for r in every if nz(r["total"])]
    clusters = {}
    for r in srows:
        c = clusters.setdefault(r["cluster"], {"key": r["cluster"], "label": r["cluster"], "months": {}, "total": {},
                                               "stores": []})
        for m, v in r["months"].items():
            _add(c["months"].setdefault(m, {}), v)
        _add(c["total"], r["total"])
        c["stores"].append(r)
    size = lambda r: r["total"].get("ty", r["total"].get("plan", 0.0))   # noqa: E731
    for c in clusters.values():
        c["n_stores"] = len(c["stores"])
        c["stores"].sort(key=size, reverse=True)
    total = {}
    for c in clusters.values():
        _add(total, c["total"])
    if grain == "store":
        for r in srows:
            r["cluster_total"] = clusters[r["cluster"]]["total"]
        out = sorted(srows, key=size, reverse=True)
    else:
        out = sorted(clusters.values(), key=lambda c: (c["key"] == NO_CLUSTER, -size(c)))
    return {"grain": grain, "months": months, "rows": out, "total": total, "n_clusters": len(clusters),
            "n_stores": len(srows), "n_empty": len(every) - len(srows)}


def _grain(g: str) -> str:
    if g not in ("store", "cluster"):
        raise HTTPException(400, "grain must be 'store' or 'cluster'")
    return g


def _divs(c: dict, division: str) -> list:
    if division.upper() == "ALL":
        return sorted(c["div"])
    if division.upper() not in c["div"]:
        raise HTTPException(404, f"No {division} in the plan")
    return [division.upper()]


@router.get("/meta")
def get_meta():
    c = _cube()
    cl = {}
    for s, v in c["stores"].items():
        cl.setdefault(v["cluster"], []).append(s)
    return {"source": c["source"], "months": c["months"], "divisions": sorted(c["div"]),
            "clusters": [{"cluster": k, "n_stores": len(v)} for k, v in sorted(cl.items())], "n_stores": len(c["stores"])}


@router.get("/division")
def get_division(grain: str = "cluster", division: str = "ALL"):
    """LY and plan by cluster or store, one division or all."""
    c, g = _cube(), _grain(grain)
    per = {}
    for dv in _divs(c, division):
        for s, ms in c["div"][dv].items():
            for m, (ly, ty) in ms.items():
                _add(per.setdefault(s, {}).setdefault(m, {}), {"ly": ly, "ty": ty})
    return {**rows(per, c["stores"], g, c["months"]), "fields": ["ly", "ty"], "source": c["source"],
            "divisions": sorted(c["div"]), "division": division.upper()}


@router.get("/department")
def get_department(grain: str = "cluster", division: str = "MENS", dept: str = ""):
    """One department's LY and plan by cluster or store; `departments` = the division's departments for the picker."""
    c, g = _cube(), _grain(grain)
    dv = _divs(c, division)[0]
    deps = c["dept"].get(dv, {})
    tot = {d: sum(t for ms in st.values() for _, t, _, _ in ms.values()) for d, st in deps.items()}
    order = sorted(deps, key=lambda d: -tot[d])
    if not order:
        raise HTTPException(404, f"No departments for {dv} in the plan")
    d = dept if dept in deps else order[0]
    per = {s: {m: {"ly": ly, "ty": ty} for m, (ly, ty, _, _) in ms.items()} for s, ms in deps[d].items()}
    return {**rows(per, c["stores"], g, c["months"]), "fields": ["ly", "ty"], "source": c["source"], "division": dv,
            "dept": d, "departments": [{"dept": x, "ty": round(tot[x], 4)} for x in order]}


@router.get("/mrp")
def get_mrp(grain: str = "cluster", division: str = "MENS", dept: str = ""):
    """One department's plan split over its MRP bands by cluster or store: each store's fortnight TY x the department's
    MRP shares (the same chain-level shares as MRP Output, so the stores add back to its totals)."""
    c, g = _cube(), _grain(grain)
    dv = _divs(c, division)[0]
    try:
        with open(MRP_PLAN, encoding="utf-8") as fh:
            mrp = json.load(fh).get(dv, {})
    except (OSError, ValueError):
        mrp = {}
    deps = {d: st for d, st in c["dept"].get(dv, {}).items() if d in mrp}
    if not deps:
        return {"rows": [], "months": c["months"], "bands": [], "departments": [], "source": c["source"], "division": dv,
                "note": f"No MRP split imported for {dv} yet (MRP Plan · Buyer's Input)."}
    tot = {d: sum(t for ms in st.values() for _, t, _, _ in ms.values()) for d, st in deps.items()}
    order = sorted(deps, key=lambda d: -tot[d])
    d = dept if dept in deps else order[0]
    bands = sorted(mrp[d], key=float)
    # only the months the MRP split covers (Mar-Jun today) - the department's other months have no MRP shares yet
    months = [m for m in c["months"] if any(mrp[d][k].get(f"{m} P1") or mrp[d][k].get(f"{m} P2") for k in bands)]
    per = {}
    for s, ms in deps[d].items():
        for m, (_, ty, p1, p2) in ms.items():
            if m not in months:
                continue
            b = {}
            for half, v in (("P1", p1), ("P2", p2)):
                sh = {k: mrp[d][k].get(f"{m} {half}", 0.0) for k in bands}
                if sum(sh.values()) > 0:
                    _add(b, split(v, sh))
            per.setdefault(s, {})[m] = {"ty": sum(b.values()), "bands": b}
    return {**rows(per, c["stores"], g, months), "fields": ["ty"], "bands": bands, "source": c["source"],
            "division": dv, "dept": d, "departments": [{"dept": x, "ty": round(tot[x], 4)} for x in order]}


@router.get("/display")
def get_display(grain: str = "cluster", division: str = "ALL"):
    """The Display Type plan (Table / Non-Table, SSG stores) by cluster or store, from its last run."""
    g = _grain(grain)
    c = _cube()
    try:
        with open(DT_RESULT, encoding="utf-8") as fh:
            dt = json.load(fh)
    except (OSError, ValueError):
        return {"rows": [], "months": [], "source": {"kind": "display", "note": "no Display Type run yet"},
                "note": "Run the Display Type plan first (Display Type · Run plan)."}
    per = {}
    for r in dt.get("rows", []):
        if division.upper() != "ALL" and r.get("division") != division.upper():
            continue
        _add(per.setdefault(r["store"], {}).setdefault(r["month"], {}),
             {"plan": r.get("mrp_plan") or 0.0, "table": r.get("table_plan") or 0.0,
              "nontable": r.get("nontable_plan") or 0.0})
    months = [m for m in TY_MONTHS if m in set(dt.get("months") or [])]
    return {**rows(per, c["stores"], g, months), "fields": ["plan", "table", "nontable"],
            "source": {"kind": "display", "note": f"the Display Type run of {dt.get('run_at', '-')}"},
            "division": division.upper()}
