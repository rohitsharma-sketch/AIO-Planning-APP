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
import sys
import threading

from fastapi import APIRouter, HTTPException

from apportion import split

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))   # repo root: rs_common
from rs_common.stores import canon_store  # noqa: E402 - renamed store codes (15 Oct 2026)

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
    stores, div, dept, months, grow, off = {}, {}, {}, set(), {}, {}
    for s, sd in (plan.get("stores") or {}).items():
        stores[s] = {"cluster": sd.get("cluster") or NO_CLUSTER, "ssg": bool(sd.get("is_ssg")), "tag": sd.get("tag"),
                     "ref": sd.get("ref_store") or "",
                     # SSG / NSO / Others and the like-for-like store a non-SSG store's split follows (2026-10-14)
                     "group": sd.get("group") or ("SSG" if sd.get("is_ssg") else "NSO"), "ref_used": sd.get("ref_used") or ""}
        for dv, dd in (sd.get("divisions") or {}).items():
            if dv not in PLAN_DIVS:   # a plan saved before GM / RETAIL left the engine (2026-10-13)
                continue
            for m, md in ((dd or {}).get("months") or {}).items():
                if not isinstance(md, dict):
                    continue
                months.add(m)
                tl = tt = 0.0
                for dp, x in (md.get("departments") or {}).items():
                    if not isinstance(x, dict):
                        continue
                    if not x.get("active", True):
                        # its LY counts in Final Results with a plan of 0, as in AOP's base (2026-10-13); the other views
                        # (MRP, methods) keep planning active departments only
                        if float(x.get("ly") or 0.0):
                            off.setdefault(dv, {}).setdefault(dp, {}).setdefault(s, {})[m] = float(x.get("ly") or 0.0)
                        continue
                    ly, ty = float(x.get("ly") or 0.0), float(x.get("ty") or 0.0)
                    p1 = float(x.get("ty_p1", ty / 2) or 0.0)
                    p2 = float(x.get("ty_p2", ty / 2) or 0.0)
                    l1 = float(x["ly_p1"]) if x.get("ly_p1") is not None else ly / 2   # its LY in P1 (half-month LY, 2026-10-15)
                    tl, tt = tl + ly, tt + ty
                    dept.setdefault(dv, {}).setdefault(dp, {}).setdefault(s, {})[m] = (ly, ty, p1, p2, l1)
                    # the growth index a like-for-like store's department was planned on (100 = flat) - the same in
                    # every LFL store; kept for the "how is this number made" pop-up (2026-10-13)
                    if sd.get("is_ssg") and "g_p1" in x and m not in grow.get(dv, {}).get(dp, {}):
                        grow.setdefault(dv, {}).setdefault(dp, {})[m] = (float(x["g_p1"]) + float(x.get("g_p2", x["g_p1"]))) / 2
                div.setdefault(dv, {}).setdefault(s, {})[m] = (tl, tt)
    return {"stores": stores, "div": div, "dept": dept, "months": [m for m in TY_MONTHS if m in months],
            "source": source, "g": grow, "off": off}


LIVE_SOURCE = {"kind": "live", "name": "live base plan",
               "note": "the live base plan - not generated yet (Generate Base Plan saves it; corrections apply after)"}


def _register_live_cube():
    from engines import dept_sales_engine as _dse
    _dse.VIEW_BUILDERS["cube"] = lambda plan: build_cube(plan, LIVE_SOURCE)


_only_cache = {"key": None, "cube": None}


def only_months(c: dict, keep) -> dict:
    """The cube with just the months in `keep` (None = all). A plan saved before the plan months changed (e.g. Mar-Sep
    while BIS plans Mar-Jun) shows only the months planned now - every view reads the cube (2026-10-13)."""
    if not keep or set(c["months"]) <= set(keep):
        return c
    k = set(keep)
    sub = lambda mm: {m: v for m, v in mm.items() if m in k}   # noqa: E731
    return {**c, "months": [m for m in c["months"] if m in k],
            "div": {dv: {s: sub(mm) for s, mm in ss.items()} for dv, ss in c["div"].items()},
            "dept": {dv: {dp: {s: sub(mm) for s, mm in ss.items()} for dp, ss in dd.items()} for dv, dd in c["dept"].items()},
            "g": {dv: {dp: sub(mm) for dp, mm in dd.items()} for dv, dd in (c.get("g") or {}).items()},
            "off": {dv: {dp: {s: sub(mm) for s, mm in ss.items()} for dp, ss in dd.items()} for dv, dd in (c.get("off") or {}).items()}}


def _cube() -> dict:
    """The active plan as a cube - only the months Sales Plan plans now (BIS's input months)."""
    from actuals_manager import plan_ty_months
    c, keep = _cube_all(), plan_ty_months()
    key = (id(c), tuple(sorted(keep or ())))
    if _only_cache["key"] != key:
        _only_cache.update(key=key, cube=only_months(c, keep))
    return _only_cache["cube"]


def warm_views():
    """Background, from 8010's warmer every minute (user, 2026-10-15: "speed the population of view faster"): build what
    the Final Results / MRP / Display / Qty pages and the check-up read, so the first page after a change doesn't wait for
    it (cold: cube ~2 s, MRP tree ~5 s, Display tree ~3 s, check-up ~10 s). Each is cached on its inputs, so a minute
    with no change costs ~0.2 s."""
    c, am = _cube(), _load_attr()
    for h in (False, True):
        _index(c, am, h)
        _mrp_index(c, am, h)
        _display_index(c, am, h)
    publish_display(c, am)
    publish_versions()
    from engines.display_type_engine import _qty_frame
    _qty_frame()
    from engines.plan_checkup import checkup
    checkup(False)


# Growth vs LY reads the Sales Plan's output from this file (user, 2026-10-15: "link the growth V LY to the output of the
# Sales Plan and make the template till Display on Merged MRP Sales comparison"): the Display tree's cells - every store x
# department x merged MRP (the MRP Re-apportionment's new MRPs) x display type x fortnight, TY plan and the plan's own LY
# on the same split. Rewritten only when the Display tree is rebuilt (the warmer calls it every minute).
PUBLISH_PATH = os.path.join(_HERE, "..", "sales_plan_display.pkl")
_pub: dict = {"ix": None}


def publish_display(c: dict | None = None, am: dict | None = None) -> bool:
    c = c if c is not None else _cube()
    ix = _display_index(c, am if am is not None else _load_attr(), True)
    if _pub["ix"] is ix and os.path.exists(PUBLISH_PATH):
        return False
    _write_published(c, ix, PUBLISH_PATH)
    _pub["ix"] = ix
    return True


def _write_published(c: dict, ix: dict, path: str, extra: dict | None = None):
    import time
    import pandas as pd
    N, C = ix["names"], ix["c"]
    lv = ("store", "division", "attribute", "department", "mrp", "display", "month")
    df = pd.DataFrame({k: pd.Categorical.from_codes(C[k], [str(x) for x in N[k]]) for k in lv})
    df["ly"], df["ty"] = ix["ly"], ix["ty"]
    df = df[(df["ly"].abs() > 1e-12) | (df["ty"].abs() > 1e-12)].reset_index(drop=True)
    # pieces for the apps that need them (Re-Aligner, NSO - 2026-10-15): value / the ASP master's ASP of the department x
    # MRP x display x period (its own, else the other display type's), to 2 decimals as the Qty run (M3); 0 without an ASP
    import numpy as np
    from engines.display_type_engine import load_asp, asp_lookup
    a = (load_asp() or {}).get("data") or {}
    df["qty"] = 0.0
    if a and len(df):
        k = ["department", "mrp", "display", "month"]
        u = df[k].drop_duplicates()
        u["asp"] = [asp_lookup(a, d, m, t, mo)[0] for d, m, t, mo in u.itertuples(index=False)]
        df = df.merge(u, on=k, how="left")
        df["qty"] = np.where(df["asp"].fillna(0) > 0, (df["ty"] * 1e5 / df["asp"]).round(2), 0.0)
        df = df.drop(columns="asp")
    stores = {s: {"cluster": x["cluster"], "stype": x["stype"], "tag": (c["stores"].get(s) or {}).get("tag") or "",
                  "ref": (c["stores"].get(s) or {}).get("ref") or (c["stores"].get(s) or {}).get("ref_used") or ""}
              for s, x in _sinfo(c).items()}
    src = c.get("source") or {}
    out = {"built": time.strftime("%d %b %Y %H:%M"), "plan": src.get("note") or src.get("name") or "the Sales Plan",
           "months": sorted({str(m) for m in N["month"]}, key=month_key), "stores": stores, "cells": df,
           "about": {"mrp": ix.get("source"), "split": ix.get("about")}, **(extra or {})}
    tmp = f"{path}.{os.getpid()}.tmp"
    pd.to_pickle(out, tmp)
    os.replace(tmp, path)


# Saved versions too (user, 2026-10-15: "can i have a version selector from this"): each saved Sales Plan version
# (plan_versions) published the same way, so Growth vs LY can pick it. A version freezes the department plan; its MRP /
# display split is today's rules (the same split the live plan takes). Built once, again only when the version is saved
# over or the split's inputs change; built off to the side, so the live views' caches stay as they are.
VERSIONS_PATH = os.path.join(_HERE, "..", "sales_plan_display_versions.json")


def version_path(vid: str) -> str:
    return os.path.join(_HERE, "..", f"sales_plan_display.{vid}.pkl")


def publish_versions() -> int:
    from engines import plan_versions as pv
    from engines.mrp_plan_engine import effective_shares_key
    from engines.display_type_engine import mix_key
    from engines import plan_file_mix as pfm
    from engines.display_type_engine import DT_ASP_PATH
    asp_mt = os.path.getmtime(DT_ASP_PATH) if os.path.exists(DT_ASP_PATH) else None
    rules = repr((effective_shares_key(), mix_key(), (pfm.load() or {}).get("imported_at"), asp_mt, "fmt2-qty"))
    try:
        with open(VERSIONS_PATH, encoding="utf-8") as f:
            done = {r["id"]: r for r in json.load(f)}
    except (OSError, ValueError):
        done = {}
    out, built = [], 0
    for r in pv._index():
        if r.get("removed"):
            continue
        vid, key = r["id"], repr((r["updated_at"], rules))
        row = {"id": vid, "name": r["name"], "saved": r["updated_at"], "key": key}
        if done.get(vid, {}).get("key") != key or not os.path.exists(version_path(vid)):
            snap = pv.snapshot(vid)
            with _mx_lock:
                keep_mx = dict(_mx)
            keep_dx = dict(_dx)
            try:
                ix = _display_index(snap["cube"], snap.get("attr_map") or {}, True)
                _write_published(snap["cube"], ix, version_path(vid), {"version": {"id": vid, "name": r["name"], "saved": r["updated_at"]}})
            finally:   # the live plan's MRP / Display caches back as they were
                with _mx_lock:
                    _mx.clear()
                    _mx.update(keep_mx)
                _dx.clear()
                _dx.update(keep_dx)
            built += 1
        out.append(row)
    if built or len(out) != len(done):
        from plan_cache import save_json
        save_json(VERSIONS_PATH, out, indent=1)
    return built


def _cube_all() -> dict:
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
                for m, (ly, *_) in ms.items():
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
    aop, cl, base, sbase = {}, {}, {}, {}
    with open(p, encoding="utf-8") as fh:
        recs = json.load(fh)
    # only the months that AOP version had LY for (it ran before later months closed - e.g. V2 on 25 Sep has no Sep base,
    # its Sep figure is new stores only), so the comparison with today's plan is like for like
    for r in recs:
        for m in TY_MONTHS:
            base[m] = base.get(m, 0.0) + float(r.get(f"{m} | Base") or 0.0)
    covered = {m for m, v in base.items() if v > 0}
    for r in recs:
        s, dv = canon_store(str(r.get("Store") or "")), str(r.get("Division") or "").strip().upper()   # a publish from before a rename
        if s and r.get("Cluster"):
            cl[s] = str(r["Cluster"]).strip()
        for m in TY_MONTHS:
            b = r.get(f"{m} | Base")
            if s and dv and b:   # the LY base AOP's growth is on, per store (Sales Plan's LFL LY anchor, 2026-10-13)
                x = sbase.setdefault(s, {}).setdefault(dv, {})
                x[m] = x.get(m, 0.0) + float(b)
            v = r.get(f"{m} | Forecast")
            if s and dv and v and m in covered:
                d = aop.setdefault(s, {}).setdefault(dv, {})
                d[m] = d.get(m, 0.0) + float(v)
    # months the version has ANY forecast for (Sep'27 = new stores only in V2) - what the plan months follow
    fc = {m for m in TY_MONTHS if any(float(r.get(f"{m} | Forecast") or 0.0) > 0 for r in recs)}
    _aop_cache.update(key=ck, v=(pid, label, aop, cl, sorted(covered, key=TY_MONTHS.index)), fc=fc, base=sbase)
    return _aop_cache["v"]


def aop_base_by_store() -> tuple:
    """(publish id, {STORE: {DIVISION: {TY month: Rs lakh}}}) - the LY base of the AOP publish BIS plans on."""
    pid = _aop_by_store()[0]
    return pid, (_aop_cache.get("base") or {}) if pid else {}


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
                for m, (ly, ty, *_) in ms.items():
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
    per = {s: {m: {"ly": ly, "ty": ty} for m, (ly, ty, *_) in ms.items()} for s, ms in deps[d].items()}
    return {**rows(per, c["stores"], g, c["months"]), "fields": ["ly", "ty"], "source": c["source"], "division": dv,
            "dept": d, "departments": [{"dept": x, "ty": round(tot[x], 4)} for x in order]}


@router.get("/mrp")
def get_mrp(grain: str = "cluster", division: str = "MENS", dept: str = ""):
    """One department's plan split over its MRP bands by cluster or store: each store's fortnight TY x the department's
    MRP shares (the same chain-level shares as MRP Output, so the stores add back to its totals)."""
    c, g = _cube(), _grain(grain)
    dv = _divs(c, division)[0]
    from engines.mrp_plan_engine import effective_shares   # new departments on their reference's split (2026-10-13)
    try:
        mrp = effective_shares()[0].get(dv, {})
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
        for m, (_, ty, p1, p2, *_) in ms.items():
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


def _sinfo(cube: dict) -> dict:
    return {s: {"cluster": x["cluster"], "store": s, "stype": x.get("group") or ("SSG" if x.get("ssg") else "NSO")}
            for s, x in cube["stores"].items()}


def _cells(cube: dict, attr_map: dict, want: dict, sinfo: dict, filt: dict | None = None, p12: bool = False):
    """Every (division, department, attribute, store, month, LY, TY) cell of the node want = {level: value}, inside the
    filters filt = {level: set of values} (user, 2026-10-13: "filters required"). p12: each cell also carries its TY P1 /
    TY P2 (an inactive department's 0, 0) and its LY in P1 - what the P1 / P2 index is made of (_halve)."""
    f = filt or {}
    fit = lambda lv, v: want.get(lv, v) == v and (lv not in f or v in f[lv])   # noqa: E731
    ok = {s for s, x in sinfo.items() if all(fit(k, v) for k, v in x.items())}
    for dv, dmap in cube["dept"].items():
        if not fit("division", dv):
            continue
        amap = attr_map.get(dv, {})
        for dp, smap in dmap.items():
            at = amap.get(dp) or "-"
            if not fit("department", dp) or not fit("attribute", at):
                continue
            for s, mm in smap.items():
                if s not in ok:
                    continue
                for m, v in mm.items():
                    if fit("month", m):
                        yield ((dv, dp, at, s, m, v[0], v[1], v[2], v[3], v[4] if len(v) > 4 else v[0] / 2) if p12
                               else (dv, dp, at, s, m, v[0], v[1]))
    for dv, dmap in (cube.get("off") or {}).items():   # inactive departments: LY, plan 0
        if not fit("division", dv):
            continue
        amap = attr_map.get(dv, {})
        for dp, smap in dmap.items():
            at = amap.get(dp) or "-"
            if not fit("department", dp) or not fit("attribute", at):
                continue
            for s, mm in smap.items():
                if s in ok:
                    for m, ly in mm.items():
                        if fit("month", m):
                            yield (dv, dp, at, s, m, ly, 0.0, 0.0, 0.0, ly / 2) if p12 else (dv, dp, at, s, m, ly, 0.0)


def parse_filters(raw: str, allowed=HIER_LEVELS) -> dict:
    """'{"division": ["MENS"], "month": ["Mar'27"]}' -> {level: set}; unknown levels / empty lists dropped."""
    try:
        f = json.loads(raw or "{}")
    except ValueError:
        raise HTTPException(status_code=422, detail="filters must be JSON: {level: [values]}")
    if not isinstance(f, dict):
        raise HTTPException(status_code=422, detail="filters must be JSON: {level: [values]}")
    return {k: {str(x) for x in v} for k, v in f.items() if k in allowed and isinstance(v, list) and v}


def make_index(cells, levels) -> dict:
    """The column index the Hierarchy reads, from any cells: iterable of ({level: value}, ly, ty). Shared by the
    department plan (below) and the Article Name plan (art_nm_engine), so both trees behave the same."""
    import numpy as np
    names = {lv: [] for lv in levels}
    pos = {lv: {} for lv in levels}
    cols = {lv: [] for lv in levels}
    ly, ty = [], []
    for key, a, t in cells:
        for lv in levels:
            v = key[lv]
            c = pos[lv].get(v)
            if c is None:
                c = pos[lv][v] = len(names[lv])
                names[lv].append(v)
            cols[lv].append(c)
        ly.append(a)
        ty.append(t)
    return {"names": names, "pos": pos, "c": {lv: np.asarray(c, dtype=np.int32) for lv, c in cols.items()},
            "ly": np.asarray(ly, dtype=float), "ty": np.asarray(ty, dtype=float)}


def index_from_frame(df, levels, ly_col: str, ty_col: str) -> dict:
    """make_index straight from a DataFrame (one column per level) - pandas factorize, for a million cells in a second."""
    import numpy as np
    import pandas as pd
    names, pos, c = {}, {}, {}
    for lv in levels:
        codes, uniq = pd.factorize(df[lv].astype(str), sort=False)
        names[lv] = list(uniq)
        pos[lv] = {v: i for i, v in enumerate(uniq)}
        c[lv] = codes.astype(np.int32)
    return {"names": names, "pos": pos, "c": c, "ly": df[ly_col].to_numpy(dtype=float), "ty": df[ty_col].to_numpy(dtype=float)}


def month_key(m: str):
    """Calendar order of "Mar'27" and of its fortnights "Mar'27 P1" / "Mar'27 P2"."""
    base, _, half = str(m).partition(" ")
    return (TY_MONTHS.index(base) if base in TY_MONTHS else 99, half)


def _mrp_key(v):
    """MRPs in price order (as numbers), anything else (Unmapped) last."""
    try:
        return (0, float(v))
    except (TypeError, ValueError):
        return (1, 0.0)


# One column index per cube (user, 2026-10-13: "make sure that the population speed is fast"): every cell once, each
# level as an integer code, so a branch / a filter list is a mask + a bincount (ms) instead of a walk over every cell
# (~0.2 s on the 305k cells of the MAMJ plan). Built once per cube and attribute map; 8010 builds it at start.
_ix: dict = {"key": None, "v": None}   # v = {False: by month, True: by P1 / P2}
_ix_lock = threading.Lock()


def _halve(ix: dict, p12, l1=None) -> dict:
    """The month index as fortnights: every cell twice - "Mar'27 P1" with its LY in P1 (l1; half its LY without one) and
    its TY P1, "Mar'27 P2" with the rest of its LY and its TY P2 (the plan engine's LY half x BIS P1 / P2 growth). numpy
    only, so the P1 / P2 view costs milliseconds once the month index is there (user, 2026-10-14: "decrease the latency
    for such views")."""
    import numpy as np
    n = len(ix["ly"])
    months = [f"{m} {h}" for m in ix["names"]["month"] for h in ("P1", "P2")]
    c = {lv: np.repeat(a, 2) for lv, a in ix["c"].items()}
    c["month"] = (np.repeat(ix["c"]["month"], 2) * 2 + np.tile(np.array([0, 1], dtype=np.int32), n)).astype(np.int32)
    return {"names": {**ix["names"], "month": months}, "pos": {**ix["pos"], "month": {v: i for i, v in enumerate(months)}},
            "c": c, "ly": (np.repeat(ix["ly"] / 2, 2) if l1 is None else
                           np.column_stack([np.asarray(l1, dtype=float), ix["ly"] - np.asarray(l1, dtype=float)]).reshape(-1)),
            "ty": np.asarray(p12, dtype=float).reshape(-1)}


def _index(cube: dict, attr_map: dict, halves: bool = False) -> dict:
    key = (id(cube), json.dumps(attr_map, sort_keys=True, default=str))
    with _ix_lock:
        if _ix["key"] == key:
            return _ix["v"][halves]
        sinfo = _sinfo(cube)
        p12, l1 = [], []

        def cells():
            for dv, dp, at, st, m, a, t, p1, p2, a1 in _cells(cube, attr_map, {}, sinfo, p12=True):
                p12.append((p1, p2))
                l1.append(a1)
                yield ({"division": dv, "department": dp, "attribute": at, "month": m, "store": st,
                        "cluster": sinfo[st]["cluster"], "stype": sinfo[st]["stype"]}, a, t)
        mon = make_index(cells(), HIER_LEVELS)
        _ix.update(key=key, v={False: mon, True: _halve(mon, p12, l1)})
        return _ix["v"][halves]


def _halves(period: str) -> bool:
    """?period=month (default) | half - the month level by month or by fortnight (P1 / P2)."""
    if period not in ("month", "half"):
        raise HTTPException(422, "period must be 'month' or 'half'")
    return period == "half"


def _mask(ix: dict, want: dict, filt: dict | None, skip: str | None = None):
    """Cells of the node `want` inside the filters (the filter on `skip` left out - Excel's list for that column)."""
    import numpy as np
    m = np.ones(len(ix["ly"]), dtype=bool)
    for lv, v in want.items():
        c = ix["pos"][lv].get(v)
        if c is None:
            return np.zeros(len(ix["ly"]), dtype=bool)
        m &= ix["c"][lv] == c
    for lv, vals in (filt or {}).items():
        if lv != skip:
            m &= np.isin(ix["c"][lv], [ix["pos"][lv][x] for x in vals if x in ix["pos"][lv]])
    return m


def hierarchy_values(cube: dict, attr_map: dict, filt: dict | None = None, levels=None, halves: bool = False) -> dict:
    """{level: [values]} a level can be filtered on, as an Excel filter list: the values with any LY / TY inside the
    OTHER levels' filters (the level's own filter does not hide its own choices). Months in calendar order."""
    return values_of(_index(cube, attr_map, halves), filt, levels or HIER_LEVELS)


def values_of(ix: dict, filt: dict | None, levels) -> dict:
    """hierarchy_values on any index (make_index)."""
    import numpy as np
    nz = (np.abs(ix["ly"]) > 1e-12) | (np.abs(ix["ty"]) > 1e-12)
    out = {}
    for lv in levels:
        vals = [ix["names"][lv][i] for i in np.unique(ix["c"][lv][_mask(ix, {}, filt, skip=lv) & nz])]
        out[lv] = (sorted(vals, key=month_key) if lv == "month" else
                   sorted(vals, key=_mrp_key) if lv in ("mrp", "old_mrp", "new_mrp") else sorted(vals))
    return out


def hierarchy_rows(cube: dict, attr_map: dict, levels: list, path: list, filt: dict | None = None, halves: bool = False) -> dict:
    """Pure. levels: the order picked (from HIER_LEVELS); path: the values of levels[:len(path)] down to the node.
    Returns {level, rows: [{key, ly, ty}] (TY high to low; months in calendar order), total: {ly, ty}}."""
    return rows_of(_index(cube, attr_map, halves), levels, path, filt)


def rows_of(ix: dict, levels: list, path: list, filt: dict | None = None) -> dict:
    """hierarchy_rows on any index (make_index)."""
    import numpy as np
    want = dict(zip(levels, path))
    nxt = levels[len(path)] if len(path) < len(levels) else None
    m = _mask(ix, want, filt)
    lys, tys = ix["ly"][m], ix["ty"][m]
    tl, tt = float(lys.sum()), float(tys.sum())
    acc = {}
    if nxt:
        g, n = ix["c"][nxt][m], len(ix["names"][nxt])
        L, T = np.bincount(g, weights=lys, minlength=n), np.bincount(g, weights=tys, minlength=n)
        acc = {ix["names"][nxt][i]: (float(L[i]), float(T[i])) for i in np.unique(g)}
    # a branch with no data at all (e.g. stores with no cluster and no sales) is not listed (user, 2026-10-13)
    rows = [{"key": k, "ly": round(v[0], 4), "ty": round(v[1], 4)} for k, v in acc.items() if abs(v[0]) > 1e-9 or abs(v[1]) > 1e-9]
    if nxt == "month":
        rows.sort(key=lambda r: month_key(r["key"]))
    elif nxt == "mrp":   # price order (Re-apportionment's before / after, 2026-10-14)
        rows.sort(key=lambda r: _mrp_key(r["key"]))
    else:
        rows.sort(key=lambda r: -r["ty"])
    return {"level": nxt, "rows": rows, "total": {"ly": round(tl, 4), "ty": round(tt, 4)}}


def _view(version: str) -> tuple:
    """(cube, attribute map, New-departments map) of the live plan, or of a saved version (plan_versions) as saved."""
    if version:
        from engines.plan_versions import snapshot
        s = snapshot(version)
        return s["cube"], s.get("attr_map") or {}, s.get("nd_map") or {}
    from engines.final_results_engine import _load_dept_attr_map
    from engines.dept_sales_engine import _load_new_dept_map
    return _cube(), _load_dept_attr_map(), _load_new_dept_map()


@router.get("/hierarchy")
def get_hierarchy(levels: str, path: str = "[]", filters: str = "{}", version: str = "", period: str = "month"):
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
    c, am, _ = _view(version)
    return {**hierarchy_rows(c, am, lv, [str(p) for p in pth], parse_filters(filters), _halves(period)), "source": c["source"]}


@router.get("/hierarchy-options")
def get_hierarchy_options(filters: str = "{}", level: str = "", version: str = "", period: str = "month"):
    """The values each Hierarchy level (or just `level`) can be filtered on - Excel style: inside the other levels'
    filters, so a pick in one column narrows the lists of the others."""
    if level and level not in HIER_LEVELS:
        raise HTTPException(status_code=422, detail=f"level: one of {', '.join(HIER_LEVELS)}")
    c, am, _ = _view(version)
    return hierarchy_values(c, am, parse_filters(filters), [level] if level else None, _halves(period))


def warm_hierarchy():
    """8010 start: load the active plan and build its index, so the first Final Results open doesn't wait for it - then
    the MRP tree's (it reads the MRP Re-apportionment, ~40 s cold)."""
    try:
        from engines.final_results_engine import _load_dept_attr_map
        _index(_cube(), _load_dept_attr_map())   # month and P1 / P2
        from engines.plan_versions import totals
        totals(_cube())                           # the version bar's live totals
        _mrp_index(_cube(), _load_dept_attr_map(), False)   # month and P1 / P2
        _display_index(_cube(), _load_dept_attr_map(), False)   # the Display Type tree on top of it
        from engines.plan_checkup import checkup
        checkup()   # the Reconciliation check-up, so its page opens at once (2026-10-14)
    except Exception:   # noqa: BLE001 - the page builds it on first use and shows any error itself
        pass


LEVEL_NAME = {"cluster": "Cluster", "store": "Store", "stype": "Store group (SSG / NSO / Others)", "division": "Division",
              "attribute": "Attribute", "department": "Department", "month": "Month"}


def _inr(v: float) -> str:
    """12345678.9 -> '1,23,45,678.9' (Indian grouping, as the pages show)."""
    neg, v = v < 0, abs(v)
    whole, frac = f"{v:.1f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    while len(head) > 2:
        tail, head = head[-2:] + "," + tail, head[:-2]
    return ("-" if neg else "") + (head + "," + tail if head else tail) + "." + frac


def explain(cube: dict, attr_map: dict, nd_map: dict, levels: list, path: list, filt: dict | None = None) -> dict:
    """Pure. How the Hierarchy row at `path` (or the Total row, path = []) gets its LY, TY, Growth % and Cont % - built
    from the very cells the row adds up, so its parts always add back to the number on screen (user, 2026-10-13: "a pop
    up of how the respective department or cluster is getting that number ... the number displayed should be the number
    we are trying to validate"). The plan rules behind each part:
      like-for-like (SSG) store: its own department LY x the BIS growth of that department and month
      other store: its division LY x the division's average BIS growth, split by its reference store's department mix
      new department: New dept % of its reference department's plan (before the reference's own cut)
      a division with new departments is then scaled by one factor per month back onto its BIS / AOP total."""
    want = dict(zip(levels, path))
    sinfo = _sinfo(cube)
    grow, st = cube.get("g") or {}, cube["stores"]
    new = {(dv, n): c for dv, e in (nd_map or {}).items() for n, c in (e or {}).items()}
    pct = lambda c, k: float(c.get(k, c.get("alloc_pct", 0)) or 0) / 100   # noqa: E731
    keep = {}   # (div, ref) -> share a reference keeps after its cuts
    for (dv, _), c in new.items():
        keep[(dv, c["ref_dept"])] = keep.get((dv, c["ref_dept"]), 1.0) * (1 - pct(c, "ref_reduction_pct"))
    parts = {k: {"ly": 0.0, "ty": 0.0, "exp": 0.0, "stores": set()} for k in ("lfl", "other", "new", "off")}
    off = cube.get("off") or {}
    off_dp = set()
    mon, depts, divs, nd_ty = {}, set(), set(), {}
    for dv, dp, at, s, m, ly, ty in _cells(cube, attr_map, want, sinfo, filt):
        part = ("off" if s in off.get(dv, {}).get(dp, {}) and m in off[dv][dp][s] and not ty else
                "new" if (dv, dp) in new else "lfl" if st[s].get("ssg") else "other")
        if part == "off":
            off_dp.add((dv, dp))
        P = parts[part]
        P["ly"] += ly
        P["ty"] += ty
        P["stores"].add(s)
        if part == "lfl":
            P["exp"] += ly * grow.get(dv, {}).get(dp, {}).get(m, 100.0) / 100 * keep.get((dv, dp), 1.0)
        if part == "new":
            nd_ty[(dv, dp)] = nd_ty.get((dv, dp), 0.0) + ty
        a = mon.setdefault(m, [0.0, 0.0])
        a[0] += ly
        a[1] += ty
        depts.add((dv, dp))
        divs.add(dv)
    LY = sum(P["ly"] for P in parts.values())
    TY = sum(P["ty"] for P in parts.values())
    label = " · ".join(str(x) for x in path) if path else "The total"
    out = {"label": label, "path": [{"level": lv, "value": v} for lv, v in zip(levels, path)],
           "ly": LY, "ty": TY, "growth": (TY / LY - 1) * 100 if LY else None, "source": (cube.get("source") or {}).get("note")}
    lines = []   # [{h: heading, t: text}] - plain words, numbers as on screen
    say = lambda h, t: lines.append({"h": h, "t": t})   # noqa: E731
    # the row's own three numbers
    say("The number", f"{label} plans ₹{_inr(TY)} L this year against ₹{_inr(LY)} L last year"
        + (f", over {len(mon)} months ({', '.join(m for m in TY_MONTHS if m in mon)})." if len(mon) > 1 else
           f", in {next(iter(mon))}." if mon else "."))
    if LY:
        say("Growth %", f"₹{_inr(TY)} ÷ ₹{_inr(LY)} − 1 = {out['growth']:+.1f}%.")
    if path:
        pw = dict(zip(levels, path[:-1]))
        pty = sum(c[6] for c in _cells(cube, attr_map, pw, sinfo, filt))
        plabel = " · ".join(str(x) for x in path[:-1]) or "the whole plan"
        out["parent"] = {"label": plabel, "ty": pty}
        out["cont"] = TY / pty * 100 if pty else None
        if pty:
            say("Cont %", f"its share of the level above ({plabel}): ₹{_inr(TY)} ÷ ₹{_inr(pty)} = {out['cont']:.1f}%.")
    # LY
    lf, ot, nw = parts["lfl"], parts["other"], parts["new"]
    bits = []
    if lf["ly"]:
        bits.append(f"₹{_inr(lf['ly'])} L is the like-for-like stores' LY - the AOP Forecaster's base (the one its "
                    "growth and BIS's are on), shared over departments by the Calendar's department mix")
    if ot["ly"]:
        bits.append(f"₹{_inr(ot['ly'])} L is the other stores' division sales (Calendar app, moved onto this year's "
                    "calendar), shared out by their reference store's department mix")
    if nw["ly"]:
        bits.append(f"₹{_inr(nw['ly'])} L is the new departments' own past sales")
    if parts["off"]["ly"]:
        bits.append(f"₹{_inr(parts['off']['ly'])} L is departments not planned this year")
    say("LY", "last year's sales of the same months"
        + (": " + "; ".join(bits) + "." if bits else "."))
    # TY, part by part
    one_dp = len(depts) == 1
    if lf["ty"]:
        g = (lf["exp"] / lf["ly"] - 1) * 100 if lf["ly"] else 0.0
        t = (f"{len(lf['stores'])} like-for-like store{'s' if len(lf['stores']) != 1 else ''}: own LY ₹{_inr(lf['ly'])} × "
             f"the BIS growth of each department and month ({'that is ' if one_dp else 'on average '}{g:+.1f}%) "
             f"= ₹{_inr(lf['exp'])}.")
        k = lf["ty"] / lf["exp"] if lf["exp"] else 1.0
        if abs(k - 1) > 5e-7:
            why = ("each division and month is then held on its AOP plan by one factor (BIS spreads it over its own "
                   "department mix, a little different from the Calendar's)"
                   + (", and kept there after the new departments are carved out" if any(d in nd_map for d in divs) else ""))
            t += f" {why[0].upper() + why[1:]}: × {k:.4f} → ₹{_inr(lf['ty'])}."
        out["k"] = k
        say("TY · like-for-like stores", t)
    if ot["ty"] or ot["ly"]:
        g = (ot["ty"] / ot["ly"] - 1) * 100 if ot["ly"] else None
        refs = sorted({st[s].get("ref") for s in ot["stores"] if st[s].get("ref")})
        one = len(ot["stores"]) == 1
        say("TY · other stores",
            f"{len(ot['stores'])} store{'s' if not one else ''} without a like-for-like year of their own "
            f"(new / non-LFL): {'its' if one else 'each store’s'} division LY grows at the division's average BIS growth "
            f"and is split by {'its' if one else 'its own'} reference store's department mix"
            + (f" (reference: {refs[0]})" if one and refs else "")
            + f": LY ₹{_inr(ot['ly'])} → ₹{_inr(ot['ty'])}" + (f" ({g:+.1f}%)" if g is not None else "")
            + ("; the same division scaling after the new departments applies here too." if any(d in nd_map for d in divs)
               else "."))
    for (dv, dp), ty in sorted(nd_ty.items()):
        c = new[(dv, dp)]
        rw = {**want, "department": c["ref_dept"]}
        rw.pop("attribute", None)
        rf = {k: v for k, v in (filt or {}).items() if k not in ("department", "attribute")}   # the reference itself
        rty = sum(x[6] for x in _cells(cube, attr_map, rw, sinfo, rf))
        npct, kp = pct(c, "new_dept_pct"), keep.get((dv, c["ref_dept"]), 1.0)
        exp = rty / kp * npct if kp else 0.0
        say(f"TY · new department {dp}",
            f"no plan of its own: it is {npct * 100:g}% of {c['ref_dept']}'s plan in the same stores and months "
            f"(₹{_inr(rty / kp if kp else 0.0)}" + (" before its own cut" if kp < 1 else "") + f") = ₹{_inr(exp)}"
            + (" ✓" if abs(exp - ty) < 0.05 else f" - the plan has ₹{_inr(ty)}: regenerate the base plan, the "
               "New departments template changed since") + ".")
        out.setdefault("new_depts", []).append({"dept": dp, "ref": c["ref_dept"], "pct": npct * 100, "ty": ty,
                                                "ref_ty": rty, "expected": exp})
    if parts["off"]["ly"]:
        say("Not planned this year", f"{len(off_dp)} department{'s' if len(off_dp) != 1 else ''} inactive / dropped in BIS "
            f"keep their LY ₹{_inr(parts['off']['ly'])} in the LY with a plan of 0 - as the AOP base does, so the growth "
            "matches AOP's.")
    if one_dp:
        (dv, dp), = depts
        if (dv, dp) not in new and grow.get(dv, {}).get(dp):
            gm = grow[dv][dp]
            say("BIS growth used", ", ".join(f"{m} {gm[m] - 100:+.1f}%" for m in TY_MONTHS if m in gm and m in mon) + ".")
        for (d2, n), c in new.items():
            if d2 == dv and c["ref_dept"] == dp:
                say("Reference department", f"{dp} is the reference of the new department {n} ({pct(c, 'new_dept_pct') * 100:g}% "
                    f"of its plan)" + (f"; it gives up {pct(c, 'ref_reduction_pct') * 100:g}%." if pct(c, "ref_reduction_pct") else
                                       "; its own plan is not cut."))
    if want.get("store"):
        x = st.get(want["store"], {})
        say("This store", f"{want['store']} is in {x.get('cluster')}"
            + (", a like-for-like store." if x.get("ssg") else
               f", not like-for-like (tag {x.get('tag') or '-'}); its department mix follows {x.get('ref') or 'its own LY'}."))
    used = [(n, parts[k]["ty"]) for k, n in (("lfl", "like-for-like stores"), ("other", "other stores"),
                                               ("new", "new departments")) if parts[k]["ty"]]
    if parts["off"]["ly"]:
        used.append(("not planned", 0.0))
    say("Check", " + ".join(f"₹{_inr(v)} ({n})" for n, v in used) + f" = ₹{_inr(TY)} - the number on screen ✓"
        if len(used) > 1 else f"₹{_inr(TY)} - the number on screen ✓")
    if filt:
        lines.insert(0, {"h": "Filters on", "t": "; ".join(f"{LEVEL_NAME.get(k, k)}: {', '.join(sorted(v))}"
                                                          for k, v in filt.items()) + " - every figure here is inside them."})
    out["lines"] = lines
    out["parts"] = {k: {"ly": P["ly"], "ty": P["ty"], "stores": len(P["stores"])} for k, P in parts.items()}
    out["months"] = [{"month": m, "ly": mon[m][0], "ty": mon[m][1]} for m in TY_MONTHS if m in mon]
    if one_dp and next(iter(depts)) in new:
        _ref_angle(out, cube, attr_map, sinfo, want, filt, next(iter(depts)), new[next(iter(depts))], pct, keep)
    return out


def _ref_angle(out, cube, attr_map, sinfo, want, filt, key, c, pct, keep):
    """A new department's ⓘ on its reference (user, 2026-10-15: "in such cases it should give the ref angle also as
    calirifcation that LY is not the key factor"): its plan is New dept % of the reference's plan, so the growth that
    means something is the reference's - its own LY (little or none) is not what the plan is built on. Growth tile and
    month table go on the reference's growth; its own growth stays in the text."""
    dv, dp = key
    ref = c["ref_dept"]
    rw = {**want, "department": ref}
    rw.pop("attribute", None)
    rf = {k: v for k, v in (filt or {}).items() if k not in ("department", "attribute")}
    rm = {}
    for _dv, _dp, _at, _s, m, ly, ty in _cells(cube, attr_map, rw, sinfo, rf):
        a = rm.setdefault(m, [0.0, 0.0])
        a[0] += ly
        a[1] += ty
    rly, rty = sum(v[0] for v in rm.values()), sum(v[1] for v in rm.values())
    g = (rty / rly - 1) * 100 if rly else None
    npct, kp = pct(c, "new_dept_pct"), keep.get((dv, ref), 1.0)
    own = out.get("growth")
    out.update(growth_own=own, growth=g, growth_label=f"Growth % · as {ref}",
               ref={"dept": ref, "ly": rly, "ty": rty, "growth": g, "pct": npct * 100, "cut_pct": (1 - kp) * 100})
    for x in out["months"]:
        r = rm.get(x["month"])
        x["growth_ref"] = (r[1] / r[0] - 1) * 100 if r and r[0] else None
    t = (f"a new department is not measured on its own LY (₹{_inr(out['ly'])} L"
         + (f" - {own:+,.1f}% on it says nothing" if own is not None else "") + f"): its plan is {npct * 100:g}% of "
         f"{ref}'s plan, so it grows as {ref} does - ₹{_inr(rly)} → ₹{_inr(rty)}"
         + (f" = {g:+.1f}%." if g is not None else "."))
    src = (f"{ref} is not cut (its New departments cut is 0%): the {npct * 100:g}% comes on top of it, and {dv} is then "
           f"scaled back onto its AOP by one factor a month - so every {dv} department gives up a little to make room, "
           f"not {ref} alone." if kp >= 1 else
           f"{ref} gives up {(1 - kp) * 100:g}% of its plan to it; {dv} is then scaled back onto its AOP by one factor a month.")
    lines = out["lines"]
    i = next((j for j, x in enumerate(lines) if x["h"] == "Growth %"), None)
    if i is None:
        i = next((j for j, x in enumerate(lines) if x["h"] == "The number"), -1) + 1
        lines.insert(i, {"h": "Growth %", "t": t})
    else:
        lines[i] = {"h": "Growth %", "t": t}
    lines.insert(i + 1, {"h": f"Where its ₹{_inr(out['ty'])} L comes from", "t": src})


def _whole(m: str) -> str:
    return str(m).partition(" ")[0]


def explain_half(cube: dict, attr_map: dict, nd_map: dict, levels: list, path: list, filt: dict | None = None) -> dict:
    """explain() in the P1 / P2 view: the working of the whole months, with the row's own fortnight numbers (LY, TY,
    Growth %, Cont %, the period table) on top - so the pop-up still shows the number on screen."""
    import numpy as np
    mi = levels.index("month") if "month" in levels else None
    out = explain(cube, attr_map, nd_map, levels, [(_whole(v) if i == mi else v) for i, v in enumerate(path)],
                  {k: ({_whole(x) for x in v} if k == "month" else v) for k, v in (filt or {}).items()})
    ix = _index(cube, attr_map, True)
    m = _mask(ix, dict(zip(levels, path)), filt)
    LY, TY = float(ix["ly"][m].sum()), float(ix["ty"][m].sum())
    g, n = ix["c"]["month"][m], len(ix["names"]["month"])
    Lm = np.bincount(g, weights=ix["ly"][m], minlength=n)
    Tm = np.bincount(g, weights=ix["ty"][m], minlength=n)
    per = sorted(((ix["names"]["month"][i], float(Lm[i]), float(Tm[i])) for i in np.unique(g)), key=lambda x: month_key(x[0]))
    out["months"] = [{"month": k, "ly": a, "ty": b} for k, a, b in per]
    rg = None
    if out.get("ref"):   # a new department: its fortnights on its reference's growth too (_ref_angle)
        rw = {**dict(zip(levels, path)), "department": out["ref"]["dept"]}
        rw.pop("attribute", None)
        rmk = _mask(ix, rw, {k: v for k, v in (filt or {}).items() if k not in ("department", "attribute")})
        RL = np.bincount(ix["c"]["month"][rmk], weights=ix["ly"][rmk], minlength=n)
        RT = np.bincount(ix["c"]["month"][rmk], weights=ix["ty"][rmk], minlength=n)
        for x in out["months"]:
            i = ix["pos"]["month"].get(x["month"])
            x["growth_ref"] = (RT[i] / RL[i] - 1) * 100 if i is not None and RL[i] else None
        rg = (RT.sum() / RL.sum() - 1) * 100 if RL.sum() else None
    note = {"h": "P1 / P2", "t": "P1 = days 1-15 of the month, P2 = the 16th to the month end. Each store x department's "
            "month LY is split into its own halves (actual half-month LY) and each half grows by BIS's own P1 / P2 growth "
            "(the plan engine's working); "
            "TY P1 + TY P2 = the month's TY."}
    head = [x for x in out["lines"] if x["h"] == "Filters on"]
    rest = [x for x in out["lines"] if x["h"] != "Filters on"]
    if abs(TY - out["ty"]) > 1e-6 or abs(LY - out["ly"]) > 1e-6:
        label = out["label"] if not path else " · ".join(str(x) for x in path)
        note["t"] += (f" The working below is for the whole month{'s' if len(per) > 2 else ''}: ₹{_inr(out['ty'])} L, "
                      f"of which this row is ₹{_inr(TY)} L.")
        ref_line = next((x for x in rest if x["h"] == "Growth %"), None) if out.get("ref") else None
        out.update(label=label, ly=LY, ty=TY, growth=rg if out.get("ref") else (TY / LY - 1) * 100 if LY else None)
        rest = [x for x in rest if x["h"] not in ("The number", "Growth %", "Cont %")]
        top = [{"h": "The number", "t": f"{label} plans ₹{_inr(TY)} L this year against ₹{_inr(LY)} L last year, in "
                f"{', '.join(k for k, _, _ in per)}."}]
        if ref_line:
            top.append({"h": "Growth %", "t": ref_line["t"] + f" This row's fortnights: {rg:+.1f}% as the reference." if rg is not None else ref_line["t"]})
        elif LY:
            top.append({"h": "Growth %", "t": f"₹{_inr(TY)} ÷ ₹{_inr(LY)} − 1 = {out['growth']:+.1f}%."})
        if path:
            pty = float(ix["ty"][_mask(ix, dict(zip(levels, path[:-1])), filt)].sum())
            plabel = " · ".join(str(x) for x in path[:-1]) or "the whole plan"
            out["parent"], out["cont"] = {"label": plabel, "ty": pty}, (TY / pty * 100 if pty else None)
            if pty:
                top.append({"h": "Cont %", "t": f"its share of the level above ({plabel}): ₹{_inr(TY)} ÷ ₹{_inr(pty)} = {out['cont']:.1f}%."})
        rest = top + [note] + rest
    else:
        rest.insert(min(3, len(rest)), note)
    out["lines"] = head + rest
    return out


def tree_xlsx(ix: dict, levels: list, names: dict, filt: dict | None, cols: tuple, title: str, about: list) -> bytes:
    """The Hierarchy view as an Excel sheet (user, 2026-10-14: "also available in excel download too keeping the same
    view"), in the classic pivot layout (tabular, item labels repeated): one row per combination of the Rows fields in
    the order the page shows it (months in calendar order, MRPs in price order, the rest by TY high to low), one column
    per Rows field, then LY, TY, Growth %, Cont % (share of the level above). about = [(label, text)] on sheet 2."""
    import io
    import pandas as pd
    import xlsxwriter
    # the store group as a column in every export (user, 2026-10-14: "the filters should be present to see actual sales
    # growth %" - the plan now has new / placeholder stores with no LY): when it isn't in the Rows, it is added as the
    # last field, so an Excel filter on SSG shows the like-for-like growth
    if "stype" in ix["c"] and "stype" not in levels:
        levels = list(levels) + ["stype"]
    m = _mask(ix, {}, filt)
    df = pd.DataFrame({lv: ix["c"][lv][m] for lv in levels})
    df["ly"], df["ty"] = ix["ly"][m], ix["ty"][m]
    tot_ly, tot_ty = float(df["ly"].sum()), float(df["ty"].sum())
    frames, prev = [], None
    for d, lv in enumerate(levels, 1):
        keys = list(levels[:d])
        g = df.groupby(keys, sort=False, as_index=False)[["ly", "ty"]].sum()
        g = g[(g["ly"].abs() > 1e-9) | (g["ty"].abs() > 1e-9)].reset_index(drop=True)
        nm = ix["names"][lv]
        if lv in ("month", "mrp", "old_mrp", "new_mrp"):
            key = month_key if lv == "month" else _mrp_key
            order = {c: i for i, c in enumerate(sorted(range(len(nm)), key=lambda c: key(nm[c])))}
            g["_s"] = g[lv].map(order)
        else:
            g["_s"] = -g["ty"]
        g[f"_r{d}"] = (g.groupby(keys[:-1], sort=False)["_s"] if d > 1 else g["_s"]).rank(method="first")
        if prev is not None:
            g = g.merge(prev[keys[:-1] + [f"_r{i}" for i in range(1, d)] + ["ty"]].rename(columns={"ty": "_pty"}),
                        on=keys[:-1], how="left")
        else:
            g["_pty"] = tot_ty
        g["_d"] = d
        prev = g
        frames.append(g)
    allr = pd.concat(frames, ignore_index=True)
    rk = [f"_r{i}" for i in range(1, len(levels) + 1)]
    allr[rk] = allr[rk].fillna(0)
    allr = allr.sort_values(rk, kind="stable").reset_index(drop=True)

    # classic pivot layout (user, 2026-10-14: "make the download happen in classic pivot table formats rather than straight
    # drill downs as it increases rows and blank space"): Excel's tabular form with every item label repeated - one row per
    # combination of the Rows fields (the deepest level, in the page's order), each field in its own column, no parent /
    # outline rows; Cont % = its share of the level above, as on the page; Grand Total last
    leaf = allr[allr["_d"] == len(levels)].reset_index(drop=True)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"constant_memory": True, "in_memory": True})
    ws = wb.add_worksheet(title[:31])
    hd = wb.add_format({"bold": True, "bg_color": "#E8EFEA", "border": 1, "text_wrap": True, "valign": "top"})
    num = wb.add_format({"num_format": "#,##0.0"})
    numb = wb.add_format({"num_format": "#,##0.0", "bold": True})
    pct = wb.add_format({"num_format": "+0.0%;-0.0%;0.0%"})
    cpc = wb.add_format({"num_format": "0.0%"})
    tb = wb.add_format({"bold": True, "top": 1})
    tbn = wb.add_format({"bold": True, "top": 1, "num_format": "#,##0.0"})
    tbp = wb.add_format({"bold": True, "top": 1, "num_format": "+0.0%;-0.0%;0.0%"})
    nc = len(levels)
    up = names.get(levels[-2], levels[-2]) if nc > 1 else "the total"
    ws.write_row(0, 0, [names.get(x, x) for x in levels] + [cols[0], cols[1], cols[2], f"Cont % (of {up})"], hd)
    ws.set_column(0, nc - 1, 18)
    ws.set_column(nc, nc + 3, 13)
    ws.freeze_panes(1, nc)
    codes = leaf[list(levels)].to_numpy()
    names_of = [ix["names"][lv] for lv in levels]
    for i, (ly, ty, pty) in enumerate(zip(leaf["ly"].to_numpy(), leaf["ty"].to_numpy(), leaf["_pty"].to_numpy()), 1):
        row = codes[i - 1]
        for j in range(nc):
            ws.write_string(i, j, str(names_of[j][int(row[j])]))
        ws.write_number(i, nc, float(ly), num)
        ws.write_number(i, nc + 1, float(ty), numb)
        if ly > 0:
            ws.write_number(i, nc + 2, float(ty / ly - 1), pct)
        if pty:
            ws.write_number(i, nc + 3, float(ty / pty), cpc)
    r = len(leaf) + 1
    ws.write_string(r, 0, "Grand Total", tb)
    for j in range(1, nc):
        ws.write_blank(r, j, None, tb)
    ws.write_number(r, nc, tot_ly, tbn)
    ws.write_number(r, nc + 1, tot_ty, tbn)
    if tot_ly > 0:
        ws.write_number(r, nc + 2, tot_ty / tot_ly - 1, tbp)
    ws.write_number(r, nc + 3, 1.0, wb.add_format({"bold": True, "top": 1, "num_format": "0.0%"}))
    ws.autofilter(0, 0, r - 1, nc + 3)
    ab = wb.add_worksheet("About")
    ab.set_column(0, 0, 18)
    ab.set_column(1, 1, 110)
    for i, (k, v) in enumerate(about):
        ab.write_string(i, 0, k, hd)
        ab.write_string(i, 1, v)
    wb.close()
    return buf.getvalue()


def xlsx_response(data: bytes, name: str):
    from fastapi.responses import Response
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def export_about(levels: list, names: dict, filt: dict | None, period: str, source: str, extra=()) -> list:
    import datetime
    return [("View", " › ".join(names.get(x, x) for x in levels)),
            ("Months", "P1 / P2 - P1 = days 1-15, P2 = 16th to month end" if period == "half" else "by month"),
            ("Filters", "; ".join(f"{names.get(k, k)}: {', '.join(sorted(v))}" for k, v in (filt or {}).items()) or "none"),
            ("From", source or "-"), *extra,
            ("Exported", datetime.datetime.now().strftime("%d %b %Y %H:%M")),
            ("Units", "₹ lakh · Growth % = TY ÷ LY − 1 · Cont % = share of the level above")]


@router.get("/hierarchy-export")
def get_hierarchy_export(levels: str, filters: str = "{}", version: str = "", period: str = "month"):
    """The Final Results Hierarchy view as on screen (Rows, filters, version, month or P1 / P2) as an Excel file."""
    lv = [x for x in levels.split(",") if x]
    if not lv or len(set(lv)) != len(lv) or any(x not in HIER_LEVELS for x in lv):
        raise HTTPException(status_code=422, detail=f"levels: pick from {', '.join(HIER_LEVELS)}, each once")
    c, am, _ = _view(version)
    f = parse_filters(filters)
    src = (c.get("source") or {}).get("note") or ""
    data = tree_xlsx(_index(c, am, _halves(period)), lv, LEVEL_NAME, f, ("LY (₹L)", "TY (₹L)", "Growth %"),
                     "Department plan", export_about(lv, LEVEL_NAME, f, period, src + (f" · version {version}" if version else "")))
    return xlsx_response(data, f"Department plan{' P1-P2' if period == 'half' else ''}.xlsx")


@router.get("/explain")
def get_explain(levels: str, path: str = "[]", filters: str = "{}", version: str = "", period: str = "month"):
    """?levels=division,department&path=["MENS","ML_JEANS"] -> how that row's numbers are made (view only)."""
    lv = [x for x in levels.split(",") if x]
    if not lv or len(set(lv)) != len(lv) or any(x not in HIER_LEVELS for x in lv):
        raise HTTPException(status_code=422, detail=f"levels: pick from {', '.join(HIER_LEVELS)}, each once")
    try:
        pth = json.loads(path)
    except ValueError:
        raise HTTPException(status_code=422, detail="path must be a JSON list")
    if not isinstance(pth, list) or len(pth) > len(lv):
        raise HTTPException(status_code=422, detail="path can't be longer than levels")
    c, am, nd = _view(version)
    return (explain_half if _halves(period) else explain)(c, am, nd, lv, [str(p) for p in pth], parse_filters(filters))



# ── MRP Plan Output as the department plan's tree (user, 2026-10-14: "merge all the views similarly to the department
# view which is the final design") ────────────────────────────────────────────────────────────────────────────────────
# The same plan cube as Final Results with one more level, MRP: each store x department x fortnight's TY (TY P1 / TY P2)
# x the department's MRP share of that fortnight (effective_shares - what MRP Output, Display Type and Reconciliation
# split by), LY = the store's department LY x that store's own LY mix over the new MRPs (the MRP Re-apportionment's
# after side; the plan's MRP share where the store has no re-apportioned sales). A department / month with no MRP split
# keeps its plan under "No MRP split", so every department adds back to its plan. Active departments only (as MRP Output).
MRP_LEVELS = ("cluster", "store", "stype", "division", "attribute", "department", "mrp", "month")
MRP_LEVEL_NAME = {**LEVEL_NAME, "mrp": "MRP"}
NO_SPLIT = "No MRP split"
NOT_PLANNED = "Not planned"   # inactive departments: their LY with a plan of 0, as Final Results shows them
_mx: dict = {}
_mx_lock = threading.Lock()


def _split_source() -> str:
    try:
        from engines.art_nm_engine import promoted_shares
        if promoted_shares() is not None:
            return "the Article Name plan, promoted to the MRP stage"
    except Exception:   # noqa: BLE001
        pass
    from engines.mrp_plan_engine import get_source, _reapp_shares
    if get_source() == "reapp" and _reapp_shares():
        return "the re-apportioned LY sales of the latest MRP Re-apportionment run"
    return "the buyers' MRP Cont % file"


_mix_mem: dict = {}


def _reapp_mix():
    """(DataFrame store, department, mrp, month ("Mar'27"), lw = share of the store x department x month's LY on the new
    MRPs, about, key) - from the MRP Re-apportionment's after side (Unmapped left out), or (None, reason, None).
    Memoised on the re-apportionment's inputs and kept on disk (Output/_store_mix.pkl, written by this server only), so
    after a restart the MRP tree is ready in seconds instead of re-running the re-apportionment (~40 s; 2026-10-14)."""
    import pandas as pd
    try:
        from engines.mrp_reapportionment_engine import compare_key, OUTPUT_DIR
        key = compare_key()
    except Exception as e:   # noqa: BLE001 - no master / sales: LY is split by the plan's shares
        return None, f"no MRP Re-apportionment to read ({e})", None
    if _mix_mem.get("key") == key:
        return _mix_mem["v"]
    path = os.path.join(OUTPUT_DIR, "_store_mix.pkl")
    try:
        disk = pd.read_pickle(path)
        if disk.get("key") == key:
            _mix_mem.update(key=key, v=(disk["mix"], disk["about"], key))
            return _mix_mem["v"]
    except Exception:   # noqa: BLE001 - none yet / unreadable: build it
        pass
    v = _build_mix()
    if v[0] is not None:
        _mix_mem.update(key=key, v=(v[0], v[1], key))
        try:
            pd.to_pickle({"key": key, "mix": v[0], "about": v[1]}, path)
        except OSError:
            pass
        return _mix_mem["v"]
    return v


def _build_mix():
    try:
        from engines.mrp_reapportionment_engine import _compare, _plan_period, get_basis
        c = _compare()
    except Exception as e:   # noqa: BLE001
        return None, f"no MRP Re-apportionment to read ({e})", None
    f = c["flows"]
    f = f[f["new"] != "Unmapped"]
    g = f.groupby(["store", "department", "new", "month"], sort=False, as_index=False)["v"].sum()
    g = g[g["v"] > 0]
    g["month"] = g["month"].map({m: _plan_period(m) for m in g["month"].unique()})
    g["lw"] = g["v"] / g.groupby(["store", "department", "month"])["v"].transform("sum")
    return (g.rename(columns={"new": "mrp"})[["store", "department", "mrp", "month", "lw"]],
            f"master {c['master']}, {get_basis()} LY sales", id(c))


def _mrp_index(cube: dict, attr_map: dict, halves: bool) -> dict:
    import numpy as np
    import pandas as pd
    from engines.mrp_plan_engine import effective_shares
    try:
        sh = effective_shares()[0]
    except (OSError, ValueError):
        sh = {}
    mix, about, mid = _reapp_mix()
    from engines import plan_file_mix as pfm   # the buyers' plan file's mix (2026-10-15)
    fmix = pfm.load()
    from engines.mrp_plan_engine import effective_shares_key
    # the split's input file times, not the split serialised on every request (2026-10-15 latency)
    key = (id(cube), json.dumps(attr_map, sort_keys=True, default=str), effective_shares_key(), mid,
           (fmix or {}).get("imported_at"))
    with _mx_lock:
        if _mx.get("key") == key:
            return _mx["v"][halves]
    want, halves = halves, True   # built once by fortnight; the month index is derived from it (_unhalve, ms)
    sinfo = _sinfo(cube)
    # departments / stores / months as integer codes, so the million-row split stays light
    dkeys, base = [], []
    for dv, deps in cube["dept"].items():
        for dp, ss in deps.items():
            d = len(dkeys)
            dkeys.append((dv, dp, (attr_map.get(dv, {}) or {}).get(dp) or "-"))
            for st, mm in ss.items():
                for m, (ly, _ty, p1, p2, *rest) in mm.items():
                    base.append((st, d, m, ly, p1, p2, rest[0] if rest else ly / 2))
    b = pd.DataFrame(base, columns=["store", "d", "month", "ly", "p1", "p2", "l1"])
    off = []
    for dv, deps in (cube.get("off") or {}).items():
        for dp, ss in deps.items():
            d = len(dkeys)
            dkeys.append((dv, dp, (attr_map.get(dv, {}) or {}).get(dp) or "-"))
            for st, mm in ss.items():
                for m, ly in mm.items():
                    for h in (("P1", "P2") if halves else ("",)):
                        off.append((st, d, f"{m} {h}" if h else m, NOT_PLANNED, ly / 2 if h else ly, 0.0, 0.0, 0.0, 0.0))
    # mk = the share table a row takes: the buyers' plan file's departments (plan_file_mix, user 2026-10-15) by the mix of
    # the store's cluster (a non-SSG store: its reference store's), the chain's where the file has no such cluster; every
    # other department by the chain MRP split (effective_shares) as before
    fdep = pfm.departments() if fmix else set()
    mk_of = pfm.store_keys(cube["stores"]) if fdep else {}
    srows = []
    for d, (dv, dp, _) in enumerate(dkeys):
        if dp in fdep:
            for mk in set(mk_of.values()) | {pfm.CHAIN}:
                for p in fmix["periods"]:
                    m, _, h = p.partition(" ")
                    for k, v in (pfm.mrp_shares(mk, dp, p) or {}).items():
                        if v > 0:
                            srows.append((mk, d, m, k, h, float(v)))
            continue
        for k, per in (sh.get(dv, {}).get(dp) or {}).items():
            for pk, v in (per or {}).items():
                m, _, h = str(pk).partition(" ")
                if h in ("P1", "P2") and v and float(v) > 0:
                    srows.append((pfm.CHAIN, d, m, str(k), h, float(v)))
    S = pd.DataFrame(srows, columns=["mk", "d", "month", "mrp", "h", "w"])
    if len(S):
        S["w"] = S["w"] / S.groupby(["mk", "d", "month", "h"])["w"].transform("sum")
    fd = {d for d, (_, dp, _) in enumerate(dkeys) if dp in fdep}
    b["mk"] = [mk_of.get(s, pfm.CHAIN) if d in fd else pfm.CHAIN for s, d in zip(b["store"], b["d"])]
    dept_of = {}
    for d, (_, dp, _) in enumerate(dkeys):
        dept_of.setdefault(dp, []).append(d)
    if mix is not None and len(mix):
        mix = mix[mix["department"].isin(dept_of)]
        mix = mix.assign(d=mix["department"].map(lambda x: dept_of[x][0]))[["store", "d", "mrp", "month", "lw"]]
    cols = ["store", "d", "month", "mrp", "ly", "ty", "ly_mix", "ly_sh", "ns"]
    parts = []
    for h, pc in (("P1", "p1"), ("P2", "p2")):
        x = b.assign(ly=b["l1"] if h == "P1" else b["ly"] - b["l1"], t=b[pc])   # the plan's LY halves (2026-10-15)
        if halves:
            x = x.assign(month=x["month"] + " " + h)
        sh_h = S[S["h"] == h].drop(columns="h")
        has = x[["mk", "d", "month"]].assign(month=x["month"].str.partition(" ")[0]).merge(
            sh_h[["mk", "d", "month"]].drop_duplicates(), how="left", indicator=True)["_merge"].eq("both").to_numpy()
        xs, xn = x[has], x[~has]
        xs = xs.assign(mo=xs["month"].str.partition(" ")[0])
        ty = xs.merge(sh_h.rename(columns={"month": "mo"}), on=["mk", "d", "mo"])
        ty = ty.assign(ty=ty["t"] * ty["w"], ly=0.0, ly_mix=0.0, ly_sh=0.0, ns=0.0)
        if mix is not None and len(mix):
            mk = mix[["store", "d", "month"]].drop_duplicates().rename(columns={"month": "mo"})
            inm = xs.merge(mk, on=["store", "d", "mo"], how="left", indicator=True)["_merge"].eq("both").to_numpy()
            lm = xs[inm].merge(mix.rename(columns={"month": "mo"}), on=["store", "d", "mo"])
            lm = lm.assign(ly=lm["ly"] * lm["lw"], ty=0.0, ly_sh=0.0, ns=0.0)
            lm["ly_mix"] = lm["ly"]
            xs_sh = xs[~inm]
        else:
            lm, xs_sh = None, xs
        ls = xs_sh.merge(sh_h.rename(columns={"month": "mo"}), on=["mk", "d", "mo"])
        ls = ls.assign(ly=ls["ly"] * ls["w"], ty=0.0, ly_mix=0.0, ns=0.0)
        ls["ly_sh"] = ls["ly"]
        ns = xn.assign(mrp=NO_SPLIT, ty=xn["t"], ly_mix=0.0, ly_sh=0.0, ns=1.0)
        parts += [f[cols] for f in (ty, lm, ls, ns) if f is not None and len(f)]
    if off:
        parts.append(pd.DataFrame(off, columns=cols))
    allp = pd.concat(parts, ignore_index=True)
    allp["ns"] = allp["ns"] * (allp["ly"].abs() + allp["ty"].abs())   # the No-split amount, for the pop-up
    g = allp.groupby(["store", "d", "month", "mrp"], sort=False, as_index=False)[["ly", "ty", "ly_mix", "ly_sh", "ns"]].sum()
    g = g[(g["ly"].abs() > 1e-12) | (g["ty"].abs() > 1e-12)].reset_index(drop=True)
    names, pos, c = {}, {}, {}

    def put(lv, values):
        codes, uniq = pd.factorize(pd.Series(values, dtype=object), sort=False)
        names[lv], pos[lv], c[lv] = list(uniq), {v: i for i, v in enumerate(uniq)}, codes.astype(np.int32)

    put("store", g["store"].to_numpy())
    put("cluster", g["store"].map(lambda x: sinfo.get(x, {}).get("cluster", NO_CLUSTER)).to_numpy())
    put("stype", g["store"].map(lambda x: sinfo.get(x, {}).get("stype", "NSO")).to_numpy())
    dk = np.array(dkeys, dtype=object)
    di = g["d"].to_numpy()
    put("division", dk[di, 0])
    put("department", dk[di, 1])
    put("attribute", dk[di, 2])
    put("mrp", g["mrp"].to_numpy())
    put("month", g["month"].to_numpy())
    v = {"names": names, "pos": pos, "c": c, "ly": g["ly"].to_numpy(float), "ty": g["ty"].to_numpy(float),
         "x": {k: g[k].to_numpy(float) for k in ("ly_mix", "ly_sh", "ns")}, "about": about,
         "source": _split_source()}
    both = {True: v, False: _unhalve(v)}
    with _mx_lock:
        _mx.update(key=key, v=both)
    return both[want]


def _unhalve(ix: dict) -> dict:
    """A by-fortnight index read by month: "Mar'27 P1" and "Mar'27 P2" cells both count under "Mar'27" (the tree adds
    cells up, so nothing needs regrouping)."""
    import numpy as np
    base, bpos = [], {}
    remap = np.empty(len(ix["names"]["month"]), dtype=np.int32)
    for i, m in enumerate(ix["names"]["month"]):
        b = _whole(m)
        if b not in bpos:
            bpos[b] = len(base)
            base.append(b)
        remap[i] = bpos[b]
    return {**ix, "names": {**ix["names"], "month": base}, "pos": {**ix["pos"], "month": bpos},
            "c": {**ix["c"], "month": remap[ix["c"]["month"]]}}


def _mrp_lv_path(levels: str, path: str, longest: int = 0):
    lv = [x for x in levels.split(",") if x]
    if not lv or len(set(lv)) != len(lv) or any(x not in MRP_LEVELS for x in lv):
        raise HTTPException(422, f"levels: pick from {', '.join(MRP_LEVELS)}, each once")
    try:
        pth = json.loads(path)
    except ValueError:
        raise HTTPException(422, "path must be a JSON list")
    if not isinstance(pth, list) or len(pth) >= len(lv) + longest:
        raise HTTPException(422, "path too long for these levels")
    return lv, [str(p) for p in pth]


MRP_SOURCE = {"kind": "mrp", "name": "MRP plan", "note": "the department plan split over its MRPs"}


@router.get("/mrp-view/hierarchy")
def get_mrp_hierarchy(levels: str, path: str = "[]", filters: str = "{}", period: str = "month"):
    lv, pth = _mrp_lv_path(levels, path)
    ix = _mrp_index(_cube(), _load_attr(), _halves(period))
    return {**rows_of(ix, lv, pth, parse_filters(filters, MRP_LEVELS)),
            "source": {**MRP_SOURCE, "note": f"the department plan split by {ix['source']}"}}


@router.get("/mrp-view/hierarchy-options")
def get_mrp_hierarchy_options(filters: str = "{}", level: str = "", period: str = "month"):
    if level and level not in MRP_LEVELS:
        raise HTTPException(422, f"level: one of {', '.join(MRP_LEVELS)}")
    return values_of(_mrp_index(_cube(), _load_attr(), _halves(period)), parse_filters(filters, MRP_LEVELS),
                     [level] if level else MRP_LEVELS)


@router.get("/mrp-view/hierarchy-export")
def get_mrp_hierarchy_export(levels: str, filters: str = "{}", period: str = "month"):
    lv, _ = _mrp_lv_path(levels, "[]")
    f = parse_filters(filters, MRP_LEVELS)
    ix = _mrp_index(_cube(), _load_attr(), _halves(period))
    data = tree_xlsx(ix, lv, MRP_LEVEL_NAME, f, ("LY (₹L)", "TY (₹L)", "Growth %"), "MRP plan",
                     export_about(lv, MRP_LEVEL_NAME, f, period, f"the department plan split by {ix['source']}",
                                  [("LY by MRP", f"each store's department LY x its own re-apportioned LY mix ({ix['about']})")]))
    return xlsx_response(data, f"MRP plan{' P1-P2' if period == 'half' else ''}.xlsx")


def _load_attr() -> dict:
    from engines.final_results_engine import _load_dept_attr_map
    return _load_dept_attr_map()


def explain_mrp(ix: dict, dix: dict, levels: list, path: list, filt: dict | None, halves: bool) -> dict:
    """Pure (on the indexes). How the MRP tree's row at `path` gets its numbers; dix = the department plan's index of
    the same period, for the check that the MRPs add back to the department plan."""
    import numpy as np
    want = dict(zip(levels, path))
    m = _mask(ix, want, filt)
    LY, TY = float(ix["ly"][m].sum()), float(ix["ty"][m].sum())
    X = {k: float(a[m].sum()) for k, a in ix["x"].items()}
    label = " · ".join(str(x) for x in path) if path else "The total"
    out = {"label": label, "path": [{"level": lv, "value": v} for lv, v in zip(levels, path)], "ly": LY, "ty": TY,
           "growth": (TY / LY - 1) * 100 if LY else None, "source": f"the department plan split by {ix['source']}"}
    g, n = ix["c"]["month"][m], len(ix["names"]["month"])
    Lm, Tm = np.bincount(g, weights=ix["ly"][m], minlength=n), np.bincount(g, weights=ix["ty"][m], minlength=n)
    per = sorted(((ix["names"]["month"][i], float(Lm[i]), float(Tm[i])) for i in np.unique(g)), key=lambda x: month_key(x[0]))
    out["months"] = [{"month": k, "ly": a, "ty": b} for k, a, b in per]
    lines = []
    say = lambda h, t: lines.append({"h": h, "t": t})   # noqa: E731
    if filt:
        say("Filters on", "; ".join(f"{MRP_LEVEL_NAME.get(k, k)}: {', '.join(sorted(v))}" for k, v in filt.items())
            + " - every figure here is inside them.")
    say("The number", f"{label} plans ₹{_inr(TY)} L this year against ₹{_inr(LY)} L last year"
        + (f", over {', '.join(k for k, _, _ in per)}." if per else "."))
    if LY:
        say("Growth %", f"₹{_inr(TY)} ÷ ₹{_inr(LY)} − 1 = {out['growth']:+.1f}%.")
    if path:
        pty = float(ix["ty"][_mask(ix, dict(zip(levels, path[:-1])), filt)].sum())
        plabel = " · ".join(str(x) for x in path[:-1]) or "the whole plan"
        out["parent"], out["cont"] = {"label": plabel, "ty": pty}, (TY / pty * 100 if pty else None)
        if pty:
            say("Cont %", f"its share of the level above ({plabel}): ₹{_inr(TY)} ÷ ₹{_inr(pty)} = {out['cont']:.1f}%.")
    if want.get("mrp") == NOT_PLANNED or ("mrp" not in want and float(ix["ly"][m & (ix["c"]["mrp"] == ix["pos"]["mrp"].get(NOT_PLANNED, -1))].sum())):
        npl = float(ix["ly"][m & (ix["c"]["mrp"] == ix["pos"]["mrp"].get(NOT_PLANNED, -1))].sum())
        say("Not planned", f"₹{_inr(npl)} L of LY is departments inactive / dropped in BIS - kept in the LY with a plan "
            "of 0, as Final Results and the AOP base do.")
    ns = want.get("mrp") == NO_SPLIT
    if want.get("mrp") and not ns:
        say("TY", f"each store's department plan for each fortnight (P1 = days 1-15, P2 = 16th to month end) × the "
            f"department's MRP {want['mrp']} share of that fortnight, from {ix['source']}.")
    elif not ns:
        say("TY", f"each store x department x fortnight's plan (P1 = days 1-15, P2 = 16th to month end) split over the "
            f"department's MRPs by its share of that fortnight, from {ix['source']}.")
    ly_ns = float(ix["ly"][m & (ix["c"]["mrp"] == ix["pos"]["mrp"].get(NO_SPLIT, -1))].sum())
    if not ns:
        bits = []
        if X["ly_mix"]:
            bits.append(f"₹{_inr(X['ly_mix'])} L is each store's department LY x that store's own LY mix over the new MRPs "
                        f"(MRP Re-apportionment: {ix['about']})")
        if X["ly_sh"] > 0.05:
            bits.append(f"₹{_inr(X['ly_sh'])} L is stores with no re-apportioned sales for that department and month - "
                        "their LY is split by the plan's MRP share")
        if bits:
            say("LY", "; ".join(bits) + ".")
    if X["ns"] or ns:
        nty = TY if ns else float(ix["ty"][m & (ix["c"]["mrp"] == ix["pos"]["mrp"].get(NO_SPLIT, -1))].sum())
        say("No MRP split", f"₹{_inr(nty)} L of plan (₹{_inr(ly_ns if not ns else LY)} L LY) is in departments / months "
            "the MRP split does not cover - kept as 'No MRP split' so every department adds back to its plan. Rebuild "
            "the MRP Cont % (MRP Plan · Buyer's Input) or cover them in the master to split it.")
    if want.get("department") and want.get("mrp") and not ns:
        dw = {k: v for k, v in want.items() if k != "mrp"}
        dm = _mask(ix, dw, {k: v for k, v in (filt or {}).items() if k != "mrp"})
        dg, dn = ix["c"]["month"][dm], len(ix["names"]["month"])
        Dt = np.bincount(dg, weights=ix["ty"][dm], minlength=dn)
        rows = []
        for k, _a, t in per:
            dt = float(Dt[ix["pos"]["month"][k]])
            rows.append([k, f"{t / dt * 100:.1f}%" if dt else "–", _inr(dt), _inr(t)])
        out["table"] = {"title": f"MRP {want['mrp']}: its share of {want['department']} by {'fortnight' if halves else 'month'}",
                        "cols": ["Period", "MRP share", "Department plan (₹L)", f"MRP {want['mrp']} (₹L)"], "rows": rows}
    if "mrp" not in want and "mrp" not in (filt or {}):
        dw = {k: v for k, v in want.items() if k != "mrp"}
        dt = float(dix["ty"][_mask(dix, dw, filt)].sum())
        dl = float(dix["ly"][_mask(dix, dw, filt)].sum())
        say("Check", f"the MRPs add back to the department plan: TY ₹{_inr(TY)} = ₹{_inr(dt)}, LY ₹{_inr(LY)} = ₹{_inr(dl)}"
            + (" ✓" if abs(TY - dt) < 0.005 and abs(LY - dl) < 0.005 else " - they differ: reopen the page after a plan change"))
    else:
        say("Check", f"₹{_inr(TY)} - the number on screen ✓")
    out["lines"] = lines
    return out


@router.get("/mrp-view/explain")
def get_mrp_explain(levels: str, path: str = "[]", filters: str = "{}", period: str = "month"):
    lv, pth = _mrp_lv_path(levels, path, longest=1)
    c, am, hv = _cube(), _load_attr(), _halves(period)
    return explain_mrp(_mrp_index(c, am, hv), _index(c, am, hv), lv, pth, parse_filters(filters, MRP_LEVELS), hv)



# ── Display Type plan as the department plan's tree (user, 2026-10-14: "Cont % should be according the Re-apportioned
# MRPs and their respective Display types % as per LY sales. the MRP plan should break and it should be highlighted as
# per that only") ───────────────────────────────────────────────────────────────────────────────────────────────────
# The MRP tree's cells, each MRP broken into its display types by display_type_engine.display_shares (the store's own
# LY mix on that new MRP that month, then the fallbacks there). LY and TY split by the same %, so a display type's Cont %
# under its MRP is its LY share. "No MRP split" / "Not planned" rows keep display "-" so every level ties to the MRP plan.
DT_LEVELS = ("cluster", "store", "stype", "division", "attribute", "department", "mrp", "display", "month")
DT_LEVEL_NAME = {**MRP_LEVEL_NAME, "display": "Display type"}
_dx: dict = {}


def _display_index(cube: dict, attr_map: dict, halves: bool) -> dict:
    import numpy as np
    import pandas as pd
    from engines.display_type_engine import display_shares, mix_key, MIX_NOTE
    mi = _mrp_index(cube, attr_map, True)
    key = (id(mi), mix_key())
    if _dx.get("key") == key:
        return _dx["v"][halves]
    N = mi["names"]
    df = pd.DataFrame({lv: np.asarray(N[lv], dtype=object)[mi["c"][lv]] for lv in ("store", "department", "mrp", "month")})
    df["mo"] = df["month"].str.partition(" ")[0]
    df["i"] = np.arange(len(df))
    # the buyers' plan file's departments: its display type % of the MRP, per the store's mix cluster x half (plan_file_mix,
    # 2026-10-15); the rest by the store's LY mix as before
    from engines import plan_file_mix as pfm
    F = pfm.display_table()
    fj = None
    if F is not None and len(F):
        df["mk"] = df["store"].map(pfm.store_keys(cube["stores"])).fillna(pfm.CHAIN)
        fj = df.merge(F, on=["mk", "department", "month", "mrp"], how="inner").assign(src="file").drop(columns="mk")
        df = df[~df["i"].isin(fj["i"])].drop(columns="mk")
    keys = df.loc[~df["mrp"].isin([NO_SPLIT, NOT_PLANNED]), ["store", "department", "mrp", "mo"]].drop_duplicates()
    sh = display_shares(keys.rename(columns={"mo": "month"})).rename(columns={"month": "mo"})
    j = df.merge(sh, on=["store", "department", "mrp", "mo"], how="left")
    if fj is not None:
        j = pd.concat([fj, j], ignore_index=True)
    j["display"] = j["display"].fillna("-")
    j["pct"] = j["pct"].fillna(100.0)
    j["src"] = j["src"].fillna("none")
    i, w = j["i"].to_numpy(), j["pct"].to_numpy(float) / 100
    ly, ty = mi["ly"][i] * w, mi["ty"][i] * w
    c = {lv: a[i] for lv, a in mi["c"].items()}
    codes, uniq = pd.factorize(j["display"], sort=True)
    names = {**N, "display": list(uniq)}
    pos = {**mi["pos"], "display": {v: k for k, v in enumerate(uniq)}}
    c["display"] = codes.astype(np.int32)
    src = j["src"].to_numpy()
    x = {f"src_{k}": np.where(src == k, ty, 0.0) for k in MIX_NOTE if k != "none"}
    x["src_none"] = np.where((src == "none") & ~j["mrp"].isin([NO_SPLIT, NOT_PLANNED]).to_numpy(), ty, 0.0)
    v = {"names": names, "pos": pos, "c": c, "ly": ly, "ty": ty, "x": x, "about": mi["about"], "source": mi["source"]}
    both = {True: v, False: _unhalve(v)}
    _dx.update(key=key, v=both)
    return both[halves]


# ── Built on cluster (preview) ────────────────────────────────────────────────────────────────────────────────────
# user, 2026-10-15: "in sales plan if the plan was made on Cluster then it should break on Store too keeping the LY cont %
# for department and making the same working auto for it. New MRPs should be given way in this case as per LY actual
# cont % and the same for display and in case for store to cluster it should be just a sum of the stores as per the
# clusters mentioned" / "both views should be availble for preview" (choice: the Sales Plan builds on cluster).
# From the Display tree's cells (store x department x merged MRP x display x fortnight), for the SSG (like-for-like)
# stores of each cluster:
#   1. the cluster's department plan = the sum of its stores' (cluster x department x fortnight - the same totals the
#      plan has now: the cluster cap and the store balance both keep them);
#   2. it goes to the cluster's stores by each store's LY share of that department in the cluster (LY cont %); a
#      department with no LY in the cluster by the store's share of the cluster's division LY, else equally;
#   3. inside the cluster x department x fortnight, the merged MRPs (new MRPs included, through the Re-apportionment) x
#      display types go to the stores by a two-way fit (the store balance's RAS): each store keeps step 2's department
#      plan and the cluster keeps its MRP x display plan exactly as now (the buyers' plan file / the MRP split), each
#      store's mix as close to its own LY as both allow; an MRP x display (or a store) with no LY starts from the store's
#      department share of the cluster's plan, so a new MRP is given way by LY cont %.
# Non-SSG stores keep their plan (they follow their reference store). Store -> cluster is the plain sum, so every cluster
# total at every level stays exactly as it is. A preview: nothing is written, the plan in use stays store-built.
_cbx: dict = {}


def _cluster_built(cube: dict, attr_map: dict, halves: bool) -> dict:
    import numpy as np
    import pandas as pd
    ix = _display_index(cube, attr_map, True)
    if _cbx.get("ix") is ix:
        return _cbx["v"][halves]
    N, C = ix["names"], ix["c"]
    keys = ["store", "cluster", "stype", "division", "attribute", "department", "mrp", "display", "month"]
    df = pd.DataFrame({k: C[k] for k in keys})
    df["ly"], df["ty"] = ix["ly"], ix["ty"]
    ssg = N["stype"].index("SSG") if "SSG" in N["stype"] else -1
    on = df["stype"].to_numpy() == ssg
    R, S = df[~on], df[on].copy()
    S["lyp"] = S["ly"].clip(lower=0)
    K = ["cluster", "department", "month"]
    cty = S.groupby(K, sort=False)["ty"].sum().rename("cty")
    cly = S.groupby(K, sort=False)["lyp"].sum().rename("cly")
    sly = S.groupby(["store"] + K, sort=False)["lyp"].sum().rename("sly")
    T = pd.concat([cty, cly], axis=1).reset_index()
    T = T[T["cty"].abs() > 1e-12]
    # 2. the department plan to the stores
    t1 = T[T["cly"] > 0].merge(sly[sly > 0].reset_index(), on=K)
    t1["tsd"] = t1["cty"] * t1["sly"] / t1["cly"]
    t2 = T[~(T["cly"] > 0)]
    parts = [t1[["store"] + K + ["tsd"]]]
    if len(t2):
        d2v = S[["department", "division"]].drop_duplicates("department")
        DK = ["cluster", "division", "month"]
        sdl = S.groupby(["store"] + DK, sort=False)["lyp"].sum().rename("sdl").reset_index()
        cdl = S.groupby(DK, sort=False)["lyp"].sum().rename("cdl").reset_index()
        t2 = t2.merge(d2v, on="department").merge(cdl, on=DK, how="left").fillna({"cdl": 0.0})
        a = t2[t2["cdl"] > 0].merge(sdl[sdl["sdl"] > 0], on=DK)
        a["tsd"] = a["cty"] * a["sdl"] / a["cdl"]
        parts.append(a[["store"] + K + ["tsd"]])
        b = t2[~(t2["cdl"] > 0)].merge(S[["store", "cluster"]].drop_duplicates(), on="cluster")
        b["tsd"] = b["cty"] / b.groupby(K)["store"].transform("count")
        parts.append(b[["store"] + K + ["tsd"]])
    TS = pd.concat(parts, ignore_index=True).merge(sly.reset_index(), on=["store"] + K, how="left").fillna({"sly": 0.0})
    TS = TS[TS["tsd"].abs() > 1e-12]
    # 3. the cluster's MRP x display plan (column) to its stores (row): a two-way fit seeded on the store's own LY
    colk = K + ["mrp", "display", "division", "attribute"]
    col = S.groupby(colk, sort=False)["ty"].sum().rename("colT").reset_index()
    col = col[col["colT"].abs() > 1e-12].merge(cty.reset_index(), on=K)
    seed_own = S[S["lyp"] > 0].merge(TS[["store"] + K + ["tsd"]], on=["store"] + K).merge(col[colk], on=colk)[["store"] + colk + ["lyp"]]
    seed_own = seed_own.rename(columns={"lyp": "seed"})
    # no own-LY start: every store x column of the cluster x department x fortnight from the store's department share
    full = TS[["store"] + K + ["tsd"]].merge(col, on=K)
    full["seed0"] = full["tsd"] * full["colT"] / full["cty"]
    have_r = seed_own.groupby(["store"] + K, sort=False)["seed"].sum().rename("hr").reset_index()
    have_c = seed_own.groupby(colk, sort=False)["seed"].sum().rename("hc").reset_index()
    full = full.merge(have_r, on=["store"] + K, how="left").merge(have_c, on=colk, how="left").fillna({"hr": 0.0, "hc": 0.0})
    need = full[(full["hr"] <= 0) | (full["hc"] <= 0)][["store"] + colk + ["seed0"]].rename(columns={"seed0": "seed"})
    E = pd.concat([seed_own, need], ignore_index=True).groupby(["store"] + colk, sort=False, as_index=False)["seed"].sum()
    E = E.merge(TS[["store"] + K + ["tsd"]], on=["store"] + K).merge(col[colk + ["colT"]], on=colk)
    rid = E.groupby(["store"] + K, sort=False).ngroup().to_numpy()
    cid = E.groupby(colk, sort=False).ngroup().to_numpy()
    rT = np.bincount(rid, weights=E["tsd"].to_numpy()) / np.bincount(rid)
    cT = np.bincount(cid, weights=E["colT"].to_numpy()) / np.bincount(cid)
    w = E["seed"].to_numpy(float).clip(min=0)
    for _ in range(60):   # ponytail: fixed RAS rounds, ample here (the check reports the residual)
        rs = np.bincount(rid, weights=w, minlength=len(rT))
        w = w * np.divide(rT, rs, out=np.zeros_like(rT), where=rs > 0)[rid]
        cs = np.bincount(cid, weights=w, minlength=len(cT))
        w = w * np.divide(cT, cs, out=np.zeros_like(cT), where=cs > 0)[cid]   # columns last: the cluster's plan exact
    rs = np.bincount(rid, weights=w, minlength=len(rT))
    _cbx["residual"] = float(np.abs(rs - rT).max()) if len(rT) else 0.0   # store department plan off its LY share, L
    fit = E.assign(ty=w, ly=0.0, stype=ssg)[keys + ["ly", "ty"]]
    base = S.assign(ty=0.0)[keys + ["ly", "ty"]]
    SS = pd.concat([base, fit], ignore_index=True).groupby(keys, sort=False, as_index=False)[["ly", "ty"]].sum()
    out = pd.concat([R[keys + ["ly", "ty"]], SS], ignore_index=True)
    out = out[(out["ly"].abs() > 1e-12) | (out["ty"].abs() > 1e-12)]
    v = {"names": N, "pos": ix["pos"], "c": {k: out[k].to_numpy(np.int32) for k in keys},
         "ly": out["ly"].to_numpy(float), "ty": out["ty"].to_numpy(float), "x": {}, "about": ix.get("about"),
         "source": ix.get("source"), "store_built": ix}
    both = {True: v, False: _unhalve(v)}
    _cbx.update(ix=ix, v=both)
    return both[halves]


def _dt_ix(build: str, halves: bool) -> dict:
    """The Display tree's index: the plan in use (store-built), or built on cluster (preview)."""
    if build not in ("", "store", "cluster"):
        raise HTTPException(422, "build: store or cluster")
    c, am = _cube(), _load_attr()
    return _cluster_built(c, am, halves) if build == "cluster" else _display_index(c, am, halves)


CB_NOTE = ("built on cluster (preview): each SSG cluster's department plan to its stores by their LY share of the "
           "department, its MRP x display plan to the stores by their own LY (a two-way fit - both totals kept) - "
           "non-SSG stores as they are")


def explain_cluster_built(cb: dict, sb: dict, levels: list, path: list, filt: dict | None) -> dict:
    """Pure. The ⓘ of a row of the cluster-built preview: its numbers, the store-built plan's at the same row, the rule."""
    want = dict(zip(levels, path))
    m, ms = _mask(cb, want, filt), _mask(sb, want, filt)
    ly, ty, ts = float(cb["ly"][m].sum()), float(cb["ty"][m].sum()), float(sb["ty"][ms].sum())
    up = _mask(cb, dict(zip(levels, path[:-1])), filt) if path else None
    cont = (ty / float(cb["ty"][up].sum()) * 100) if path and float(cb["ty"][up].sum()) else None
    lines = [{"h": "Built on cluster", "t": "the SSG cluster's department plan (the same as the plan in use) goes to its stores by each "
              "store's LY share of that department in the cluster - a department with no LY there by the store's share of the "
              "cluster's division LY. The cluster's MRP x display plan (also as in use) goes to the stores by a two-way fit: "
              "each store keeps its department plan, the cluster keeps its MRP x display plan, and each store's mix stays as "
              "close to its own LY on the merged MRPs as both allow - a new MRP is given way by the store's LY cont %. "
              "Non-SSG stores keep their plan."},
             {"h": "Plan in use (store-built)", "t": f"Rs {ts:,.2f} L here - built on cluster is {ty - ts:+,.2f} L."},
             {"h": "Check", "t": "store to cluster is the plain sum: every cluster total, at every level, is the same in both builds"
              + (" - this row is a cluster-level total, so the two agree." if "store" not in want and abs(ty - ts) < 0.005 else ".")}]
    return {"ly": round(ly, 4), "ty": round(ty, 4), "growth": (ty / ly - 1) * 100 if ly else None, "cont": cont, "lines": lines}


def _dt_lv_path(levels: str, path: str, longest: int = 0):
    lv = [x for x in levels.split(",") if x]
    if not lv or len(set(lv)) != len(lv) or any(x not in DT_LEVELS for x in lv):
        raise HTTPException(422, f"levels: pick from {', '.join(DT_LEVELS)}, each once")
    try:
        pth = json.loads(path)
    except ValueError:
        raise HTTPException(422, "path must be a JSON list")
    if not isinstance(pth, list) or len(pth) >= len(lv) + longest:
        raise HTTPException(422, "path too long for these levels")
    return lv, [str(p) for p in pth]


def _dt_about() -> str:
    from engines.display_type_engine import mix_about
    return mix_about()


@router.get("/display-view/hierarchy")
def get_dt_hierarchy(levels: str, path: str = "[]", filters: str = "{}", period: str = "month", build: str = ""):
    lv, pth = _dt_lv_path(levels, path)
    ix = _dt_ix(build, _halves(period))
    return {**rows_of(ix, lv, pth, parse_filters(filters, DT_LEVELS)),
            "source": {"kind": "display", "name": "Display Type plan" + (" - built on cluster (preview)" if build == "cluster" else ""),
                       "note": CB_NOTE if build == "cluster" else f"the MRP plan split by display type on the {_dt_about()}"}}


@router.get("/display-view/hierarchy-options")
def get_dt_hierarchy_options(filters: str = "{}", level: str = "", period: str = "month", build: str = ""):
    if level and level not in DT_LEVELS:
        raise HTTPException(422, f"level: one of {', '.join(DT_LEVELS)}")
    return values_of(_dt_ix(build, _halves(period)), parse_filters(filters, DT_LEVELS),
                     [level] if level else DT_LEVELS)


@router.get("/display-view/hierarchy-export")
def get_dt_hierarchy_export(levels: str, filters: str = "{}", period: str = "month", build: str = ""):
    lv, _ = _dt_lv_path(levels, "[]")
    f = parse_filters(filters, DT_LEVELS)
    ix = _dt_ix(build, _halves(period))
    cb = build == "cluster"
    data = tree_xlsx(ix, lv, DT_LEVEL_NAME, f, ("LY (₹L)", "TY (₹L)", "Growth %"), "Display Type plan" + (" - built on cluster (preview)" if cb else ""),
                     export_about(lv, DT_LEVEL_NAME, f, period, CB_NOTE if cb else f"the MRP plan (split by {ix['source']})",
                                  [("Display type %", f"each store x department x MRP x month's LY mix by display type - {_dt_about()}")]))
    return xlsx_response(data, f"Display Type plan{' built on cluster' if cb else ''}{' P1-P2' if period == 'half' else ''}.xlsx")


def explain_display(ix: dict, mx: dict, levels: list, path: list, filt: dict | None, halves: bool) -> dict:
    """Pure (on the indexes). How the Display tree's row at `path` gets its numbers; mx = the MRP tree's index of the
    same period, for the check that the display types add back to the MRP plan."""
    import numpy as np
    from engines.display_type_engine import MIX_NOTE
    want = dict(zip(levels, path))
    m = _mask(ix, want, filt)
    LY, TY = float(ix["ly"][m].sum()), float(ix["ty"][m].sum())
    label = " · ".join(str(x) for x in path) if path else "The total"
    out = {"label": label, "path": [{"level": lv, "value": v} for lv, v in zip(levels, path)], "ly": LY, "ty": TY,
           "growth": (TY / LY - 1) * 100 if LY else None, "source": f"the MRP plan split by display type on the {_dt_about()}"}
    g, n = ix["c"]["month"][m], len(ix["names"]["month"])
    Lm, Tm = np.bincount(g, weights=ix["ly"][m], minlength=n), np.bincount(g, weights=ix["ty"][m], minlength=n)
    per = sorted(((ix["names"]["month"][k], float(Lm[k]), float(Tm[k])) for k in np.unique(g)), key=lambda x: month_key(x[0]))
    out["months"] = [{"month": k, "ly": a, "ty": b} for k, a, b in per]
    lines = []
    say = lambda h, t: lines.append({"h": h, "t": t})   # noqa: E731
    if filt:
        say("Filters on", "; ".join(f"{DT_LEVEL_NAME.get(k, k)}: {', '.join(sorted(v))}" for k, v in filt.items())
            + " - every figure here is inside them.")
    say("The number", f"{label} plans ₹{_inr(TY)} L this year against ₹{_inr(LY)} L last year"
        + (f", over {', '.join(k for k, _, _ in per)}." if per else "."))
    if LY:
        say("Growth %", f"₹{_inr(TY)} ÷ ₹{_inr(LY)} − 1 = {out['growth']:+.1f}%.")
    if path:
        pty = float(ix["ty"][_mask(ix, dict(zip(levels, path[:-1])), filt)].sum())
        plabel = " · ".join(str(x) for x in path[:-1]) or "the whole plan"
        out["parent"], out["cont"] = {"label": plabel, "ty": pty}, (TY / pty * 100 if pty else None)
        if pty:
            say("Cont %", f"its share of the level above ({plabel}): ₹{_inr(TY)} ÷ ₹{_inr(pty)} = {out['cont']:.1f}%.")
    d = want.get("display")
    if d and d != "-":
        mw = {k: v for k, v in want.items() if k != "display"}
        mf = {k: v for k, v in (filt or {}).items() if k != "display"}
        base = float(ix["ty"][_mask(ix, mw, mf)].sum())
        say("Display split", f"{d} is {TY / base * 100 if base else 0:.1f}% of the MRP plan here (₹{_inr(TY)} of ₹{_inr(base)}): "
            f"each store's MRP plan x {d}'s share of its LY sales on that new MRP and month ({_dt_about()}).")
    elif d != "-":
        say("Display split", "each store x department x MRP x month's plan is split over the display types by that "
            f"store's LY sales on the new MRP that month, by display type ({_dt_about()}).")
    used = [(MIX_NOTE[k], float(ix["x"][f"src_{k}"][m].sum())) for k in MIX_NOTE]
    used = [(t, v) for t, v in used if abs(v) > 0.05]
    if used and d != "-":
        say("Which LY mix", "; ".join(f"₹{_inr(v)} L on {t}" for t, v in used) + ".")
    dash = float(ix["ty"][m & (ix["c"]["display"] == ix["pos"]["display"].get("-", -1))].sum())
    if d == "-" or abs(dash) > 0.005:
        say("Not split", f"₹{_inr(dash)} L has no display type: departments / months with no MRP split, departments "
            "not planned, or a department with no LY on the re-apportioned MRPs at all.")
    if "display" not in want and "display" not in (filt or {}):
        dt = float(mx["ty"][_mask(mx, want, filt)].sum())
        say("Check", f"the display types add back to the MRP plan: ₹{_inr(TY)} = ₹{_inr(dt)}"
            + (" ✓" if abs(TY - dt) < 0.005 else f" - off by ₹{_inr(TY - dt)} L"))
    else:
        say("Check", f"₹{_inr(TY)} - the number on screen ✓")
    out["lines"] = lines
    return out


@router.get("/display-view/explain")
def get_dt_explain(levels: str, path: str = "[]", filters: str = "{}", period: str = "month", build: str = ""):
    lv, pth = _dt_lv_path(levels, path, longest=1)
    c, am, hv = _cube(), _load_attr(), _halves(period)
    if build == "cluster":
        return explain_cluster_built(_cluster_built(c, am, hv), _display_index(c, am, hv), lv, pth, parse_filters(filters, DT_LEVELS))
    return explain_display(_display_index(c, am, hv), _mrp_index(c, am, hv), lv, pth, parse_filters(filters, DT_LEVELS), hv)


_register_live_cube()
