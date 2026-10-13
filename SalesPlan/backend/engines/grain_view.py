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


PLAN_DIVS = {"KIDS", "LADIES", "MENS"}   # = dept_sales_engine.DIVISIONS


def build_cube(plan: dict, source: dict) -> dict:
    """The plan reduced to what the views need: per store its cluster; per division x store x month (LY, TY); per
    division x department x store x month (LY, TY, TY P1, TY P2). Active departments only (as MRP Output)."""
    stores, div, dept, months = {}, {}, {}, set()
    for s, sd in (plan.get("stores") or {}).items():
        stores[s] = {"cluster": sd.get("cluster") or NO_CLUSTER, "ssg": bool(sd.get("is_ssg")), "tag": sd.get("tag")}
        for dv, dd in (sd.get("divisions") or {}).items():
            if dv not in PLAN_DIVS:   # a plan saved before GM / RETAIL left the engine (2026-10-13)
                continue
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


LIVE_SOURCE = {"kind": "live", "name": "live base plan",
               "note": "the live base plan - not generated yet (Generate Base Plan saves it; corrections apply after)"}


def _register_live_cube():
    from engines import dept_sales_engine as _dse
    _dse.VIEW_BUILDERS["cube"] = lambda plan: build_cube(plan, LIVE_SOURCE)


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
        # the live plan's cube comes with the shared plan views (one plan run for every view, 2026-10-13)
        from engines.dept_sales_engine import plan_views
        return plan_views()["cube"]


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


# ── Step 2 (user, 2026-10-12: chose "Both, in two steps", "By each store's LY share", "AOP store forecast x BIS mix") ──
# Two more ways to build the plan, previewed beside today's plan - nothing here is saved or adopted:
#   store-built   each store x division x month = its AOP Forecaster store forecast, split over departments by the store's
#                 own LY department mix x BIS growth (a store with no LY of its own takes its cluster's mix)
#   cluster-built each cluster x division x month = the sum of its stores' AOP forecasts, split over departments by the
#                 cluster's LY mix x BIS growth, then down to its stores by each store's LY share (no LY -> no plan)
# AOP = the publish BIS plans on (division_plan._bis_aop), per store from that AOP session's detail.json; LY = the plan's
# re-indexed LY (Calendar); BIS growth = the live growth matrix (P1 / P2 averaged; 100 where BIS has no value).
_mcache = {"key": None, "v": None}


def build_methods(cube: dict, aop: dict, growth: dict, aop_clusters: dict | None = None) -> dict:
    """{div: {dept: {store: {month: {store_built, cluster_built}}}}} plus unallocated AOP per method
    {"unalloc": {div: {store: {month: {store_built, cluster_built}}}}}. aop = {store: {div: {month: lakh}}};
    growth = {div: {dept: {month: factor}}} (1.0 = flat); aop_clusters = {store: cluster} for stores the plan does not
    list yet (new stores in the AOP Forecaster only)."""
    st, months, ac = cube["stores"], cube["months"], aop_clusters or {}
    clus = lambda s: st[s]["cluster"] if s in st else (ac.get(s) or NO_CLUSTER)   # noqa: E731
    out, un = {}, {}
    for dv in sorted(set(cube["dept"]) | {d for a in aop.values() for d in a}):
        deps = cube["dept"].get(dv, {})
        g = lambda dp, m: growth.get(dv, {}).get(dp, {}).get(m, 1.0)   # noqa: E731
        # weights = LY x growth, per store and per cluster
        w_s, w_c, ly_c = {}, {}, {}
        for dp, ss in deps.items():
            for s, ms in ss.items():
                for m, (ly, _, _, _) in ms.items():
                    if ly > 0:
                        w = ly * g(dp, m)
                        w_s.setdefault((s, m), {})[dp] = w
                        w_c.setdefault((clus(s), m), {})
                        w_c[(clus(s), m)][dp] = w_c[(clus(s), m)].get(dp, 0.0) + w
                        ly_c.setdefault((clus(s), dp, m), {})[s] = ly
        put = lambda dp, s, m, k, v: out.setdefault(dv, {}).setdefault(dp, {}).setdefault(s, {}).setdefault(m, {}).__setitem__(k, v)   # noqa: E731
        miss = lambda s, m, k, v: un.setdefault(dv, {}).setdefault(s, {}).setdefault(m, {}).__setitem__(k, v)   # noqa: E731
        ct = {}
        for s, a in aop.items():
            for m, T in (a.get(dv) or {}).items():
                if m not in months or not T:
                    continue
                ct[(clus(s), m)] = ct.get((clus(s), m), 0.0) + T
                ws = w_s.get((s, m)) or w_c.get((clus(s), m))      # own mix, else its cluster's
                if ws and sum(ws.values()) > 0:
                    for dp, v in split(T, ws).items():
                        put(dp, s, m, "store_built", v)
                else:
                    miss(s, m, "store_built", T)
        for (cl, m), T in ct.items():
            wc = w_c.get((cl, m))
            if not wc or sum(wc.values()) <= 0:
                for s in [x for x, a in aop.items() if clus(x) == cl and (a.get(dv) or {}).get(m)]:
                    miss(s, m, "cluster_built", aop[s][dv][m])
                continue
            for dp, v in split(T, wc).items():
                for s, part in split(v, ly_c[(cl, dp, m)]).items():
                    put(dp, s, m, "cluster_built", part)
    return {"plan": out, "unalloc": un}


_aop_cache = {}


def _aop_by_store():
    """The AOP Forecaster's store x division x month forecast (Rs lakh) of the publish BIS plans on."""
    from engines.division_plan import _bis_aop
    pid, label, _, _, _ = _bis_aop()
    if not pid:
        return None, None, {}, {}, []
    from db.base import SessionLocal
    from sqlalchemy import text
    with SessionLocal() as db:
        sid = db.execute(text("SELECT session_id FROM planning_inputs.aop_publish_history WHERE id = :i"), {"i": pid}).scalar()
    p = os.path.join(_HERE, "..", "..", "..", "Tentative AOP Forecaster", "sessions", str(sid), "detail.json")
    if not sid or not os.path.exists(p):
        return pid, label, {}, {}, []
    # read once per publish / file version, not on every preview (latency, 2026-10-13)
    ck = (pid, p, os.path.getmtime(p))
    if _aop_cache.get("key") == ck:
        return _aop_cache["v"]
    aop, cl, base = {}, {}, {}
    with open(p, encoding="utf-8") as fh:
        recs = json.load(fh)
    # only the months that AOP version had LY for (it ran before later months closed - e.g. V2 on 25 Sep has no Sep base,
    # its Sep figure is new stores only), so the comparison with today's plan is like for like
    for r in recs:
        for m in TY_MONTHS:
            base[m] = base.get(m, 0.0) + float(r.get(f"{m} | Base") or 0.0)
    covered = {m for m, v in base.items() if v > 0}
    for r in recs:
        s, dv = str(r.get("Store") or "").strip().upper(), str(r.get("Division") or "").strip().upper()
        if s and r.get("Cluster"):
            cl[s] = str(r["Cluster"]).strip()
        for m in TY_MONTHS:
            v = r.get(f"{m} | Forecast")
            if s and dv and v and m in covered:
                d = aop.setdefault(s, {}).setdefault(dv, {})
                d[m] = d.get(m, 0.0) + float(v)
    # months the version has ANY forecast for (Sep'27 = new stores only in V2) - what the plan months follow
    fc = {m for m in TY_MONTHS if any(float(r.get(f"{m} | Forecast") or 0.0) > 0 for r in recs)}
    _aop_cache.update(key=ck, v=(pid, label, aop, cl, sorted(covered, key=TY_MONTHS.index)), fc=fc)
    return _aop_cache["v"]


def aop_forecast_months() -> set:
    """TY months the live AOP version forecasts (any store has a forecast) - Sales Plan plans these only (2026-10-13)."""
    _aop_by_store()
    return set(_aop_cache.get("fc") or ())


def _methods():
    c = _cube()
    from engines.department_plan import live_growth_matrix
    gm = live_growth_matrix()
    pid, label, aop, aop_cl, amonths = _aop_by_store()
    from engines import sellthru_factor as stf
    try:
        st = stf.sell_thru()
    except Exception as e:   # noqa: BLE001 - lake unreachable: the other methods still show; every factor is 0 (flat)
        st = {**stf.EMPTY, "error": str(e)}
    key = (id(c), pid, json.dumps(gm, sort_keys=True), st.get("file"))
    if _mcache["key"] != key:
        growth = {dv: {dp: {m: (ps.get(f"{m} P1", 100.0) + ps.get(f"{m} P2", 100.0)) / 200.0 for m in c["months"]}
                       for dp, ps in deps.items()} for dv, deps in gm.items()}
        v = build_methods(c, aop, growth, aop_cl)
        # user, 2026-10-13 (the MAMJ'27 cluster workbook's working): the same cluster-built split, weighted by LY x
        # (1 + sell-thru factor) instead of LY x BIS growth - engines/sellthru_factor.py
        sg, sinfo = stf.growth({dv: list(d) for dv, d in c["dept"].items()}, c["months"], st)
        alt = build_methods(c, aop, sg, aop_cl)
        for dv, deps in alt["plan"].items():
            for dp, ss in deps.items():
                for s, ms in ss.items():
                    for m, x in ms.items():
                        if "cluster_built" in x:
                            v["plan"].setdefault(dv, {}).setdefault(dp, {}).setdefault(s, {}).setdefault(m, {})["cluster_st"] = x["cluster_built"]
        for dv, ss in alt["unalloc"].items():
            for s, ms in ss.items():
                for m, x in ms.items():
                    if "cluster_built" in x:
                        v["unalloc"].setdefault(dv, {}).setdefault(s, {}).setdefault(m, {})["cluster_st"] = x["cluster_built"]
        _mcache.update(key=key, v={**v, "aop": aop, "aop_clusters": aop_cl, "pid": pid, "label": label,
                                   "months": [m for m in c["months"] if m in amonths], "st_info": sinfo,
                                   "st_file": st.get("file"), "st_error": st.get("error")})
    return c, _mcache["v"]


@router.get("/methods")
def get_methods(grain: str = "cluster", division: str = "ALL", dept: str = ""):
    """Today's plan beside the store-built and cluster-built AOP x BIS plans, by cluster or store (preview only).
    dept = one department (its division), else the division totals with each store's AOP forecast."""
    g = _grain(grain)
    c, M = _methods()
    divs = _divs(c, division) if not dept else [division.upper()]
    months = M["months"]
    per = {}
    for dv in divs:
        deps = c["dept"].get(dv, {})
        mp = M["plan"].get(dv, {})
        names = [dept] if dept else sorted(set(deps) | set(mp))
        for dp in names:
            for s, ms in deps.get(dp, {}).items():
                for m, (ly, ty, _, _) in ms.items():
                    if m in months:
                        _add(per.setdefault(s, {}).setdefault(m, {}), {"ly": ly, "ty": ty})
            for s, ms in mp.get(dp, {}).items():
                for m, v in ms.items():
                    _add(per.setdefault(s, {}).setdefault(m, {}), v)
        if not dept:
            for s, a in M["aop"].items():
                for m, v in (a.get(dv) or {}).items():
                    if m in months:
                        _add(per.setdefault(s, {}).setdefault(m, {}), {"aop": v})
            for s, ms in M["unalloc"].get(dv, {}).items():
                for m, v in ms.items():
                    _add(per.setdefault(s, {}).setdefault(m, {}), {f"unalloc_{k}": x for k, x in v.items()})
    for s in per:
        for m in per[s]:
            for k in ("ly", "ty", "store_built", "cluster_built", "cluster_st"):
                per[s][m].setdefault(k, 0.0)
    out = rows(per, {**{s: {"cluster": k} for s, k in M["aop_clusters"].items()}, **c["stores"]}, g, months)
    si = M["st_info"].get(divs[0], {}).get(dept) if dept else None
    return {**out, "fields": ["ly", "ty", "store_built", "cluster_built", "cluster_st"] + ([] if dept else ["aop"]),
            "source": c["source"], "aop": {"publish": M["pid"], "label": M["label"], "stores": len(M["aop"])},
            "division": division.upper(), "dept": dept or None,
            "sellthru": {"file": M["st_file"], "error": M["st_error"],
                         **({"tag": si["tag"], "tag_st": si["tag_st"],
                             "months": {m: si["months"][m] for m in months if m in si["months"]}} if si else {})}}


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


# user, 2026-10-13: "i need a editable hierarchial system for editing a hierarchy for view" - the plan as a tree whose
# levels (and their order) the user picks; view only. One call = the children of one node: every plan cell under
# `path` grouped by the next level, so a branch loads only when it is opened. Same cube (and live fallback) as above.
HIER_LEVELS = ("cluster", "store", "stype", "division", "attribute", "department", "month")


def hierarchy_rows(cube: dict, attr_map: dict, levels: list, path: list) -> dict:
    """Pure. levels: the order picked (from HIER_LEVELS); path: the values of levels[:len(path)] down to the node.
    Returns {level, rows: [{key, ly, ty}] (TY high to low; months in calendar order), total: {ly, ty}}."""
    want = dict(zip(levels, path))
    nxt = levels[len(path)] if len(path) < len(levels) else None
    sinfo = {s: {"cluster": x["cluster"], "store": s, "stype": "SSG" if x.get("ssg") else "NSO"}
             for s, x in cube["stores"].items()}
    ok = {s for s, x in sinfo.items() if all(want.get(k, v) == v for k, v in x.items())}
    acc, tl, tt = {}, 0.0, 0.0
    for dv, dmap in cube["dept"].items():
        if want.get("division", dv) != dv:
            continue
        amap = attr_map.get(dv, {})
        for dp, smap in dmap.items():
            at = amap.get(dp) or "-"
            if want.get("department", dp) != dp or want.get("attribute", at) != at:
                continue
            fixed = {"division": dv, "department": dp, "attribute": at}
            for s, mm in smap.items():
                if s not in ok:
                    continue
                for m, v in mm.items():
                    if want.get("month", m) != m:
                        continue
                    ly, ty = v[0], v[1]
                    tl, tt = tl + ly, tt + ty
                    if nxt:
                        k = m if nxt == "month" else fixed.get(nxt) or sinfo[s][nxt]
                        a = acc.setdefault(k, [0.0, 0.0])
                        a[0] += ly
                        a[1] += ty
    # a branch with no data at all (e.g. stores with no cluster and no sales) is not listed (user, 2026-10-13)
    rows = [{"key": k, "ly": round(v[0], 4), "ty": round(v[1], 4)} for k, v in acc.items() if abs(v[0]) > 1e-9 or abs(v[1]) > 1e-9]
    if nxt == "month":
        rows.sort(key=lambda r: TY_MONTHS.index(r["key"]) if r["key"] in TY_MONTHS else 99)
    else:
        rows.sort(key=lambda r: -r["ty"])
    return {"level": nxt, "rows": rows, "total": {"ly": round(tl, 4), "ty": round(tt, 4)}}


@router.get("/hierarchy")
def get_hierarchy(levels: str, path: str = "[]"):
    """?levels=cluster,store,division&path=["BH - (NP)"] -> the children of that node (view only)."""
    lv = [x for x in levels.split(",") if x]
    if not lv or len(set(lv)) != len(lv) or any(x not in HIER_LEVELS for x in lv):
        raise HTTPException(status_code=422, detail=f"levels: pick from {', '.join(HIER_LEVELS)}, each once")
    try:
        pth = json.loads(path)
    except ValueError:
        raise HTTPException(status_code=422, detail="path must be a JSON list")
    if not isinstance(pth, list) or len(pth) >= len(lv):
        raise HTTPException(status_code=422, detail="path must be shorter than levels")
    from engines.final_results_engine import _load_dept_attr_map
    c = _cube()
    return {**hierarchy_rows(c, _load_dept_attr_map(), lv, [str(p) for p in pth]), "source": c["source"]}


_register_live_cube()
