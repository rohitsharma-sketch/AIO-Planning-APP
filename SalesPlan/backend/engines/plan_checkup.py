"""Sales Plan full check-up (user, 2026-10-14: "i want a full check up from Calendar APP where the sales are being brought
in. i want the checks to show that the sales have been matched with what is currently displayed in Calendar - AOP
forecaster - BIS for LY and TY projections are aligned with AOP forecast (version name) and BIS (version Name) on what all
levels - Div/Dep/MRP/UDF. Separate checks for if the sales output is being generated on Re-apportioned MRP sales and the
sales plan is all the way backwards compatible and checked and forward checked too. Qtys should be there for all values
which are projected ... Where ever there is an issue it should be validated at your end and then signed off otherwise there
should be a button which rectifies by churning the whole system again and give me the final output. It should be fast
and accurate").

Every check ties the plan the pages show (the active plan file) to its source, from the top down and back up:
  1 Calendar -> LY      store x division x month LY = the Calendar's reindexed sales (other stores) / the AOP version's
                        base (like-for-like stores, as the engine anchors them), and each department = the Calendar's mix
  2 AOP -> TY           division x month like-for-like plan = the AOP version's division plan; built on that publish
  3 BIS -> TY           every like-for-like department x month on BIS's growth in use; TY = LY/2 x BIS P1 / P2 growth x
                        one division x month factor (the AOP hold and the new-department carve), new departments = their
                        % of the reference; the saved plan on today's inputs
  4 MRP                 the MRP Cont % = the latest re-apportionment on the master in use, and = its LY mix exactly;
                        department = sum of MRPs (TY forward, LY backward); what has no MRP split
  5 UDF (display type)  MRP = sum of display types; which LY mix split it; the Display Type run = the tree (SSG stores)
  6 Qty                 every projected department x MRP x display type x month has an ASP in the ASP master -> qty
A failed check says whether a re-run fixes it (Rectify re-runs the chain) or it needs an input (listed to fix)."""
import datetime
import json
import os
import threading
import time

TOL = 1e-6   # Rs lakh (Rs 0.10) for source tie-outs; the additivity checks above stay at 8 decimals
_HERE = os.path.dirname(os.path.abspath(__file__))
SIGNOFF_PATH = os.path.join(_HERE, "..", "checkup_signoff.json")
_RUN_LOCK = threading.Lock()

# Progress of the check-up / Rectify run (user, 2026-10-14: "give me a progress bar, elapsed time and remaining time true
# to the progress bar"). The run marks each step as it reaches it; remaining = what each step took the last time it ran
# (checkup_timing.json, git-ignored - first runs use rough defaults), the current step's left-over included; the page
# draws the bar as elapsed / (elapsed + remaining), so the bar and the two times always agree.
CHECK_STEPS = ["Reading the plan and the source versions", "Calendar, AOP, BIS and season checks",
               "Building the department, MRP and display trees", "MRP, display type and qty checks"]
TIMING_PATH = os.path.join(_HERE, "..", "checkup_timing.json")
_DEFAULT_SECS = {CHECK_STEPS[0]: 3, CHECK_STEPS[1]: 6, CHECK_STEPS[2]: 5, CHECK_STEPS[3]: 4,
                 "Department plan on today's inputs": 5, "MRP Cont % from the master in use": 30,
                 "Display Type run": 60, "Display Type validation": 10, "Qty run": 30}
_PROG: dict = {"running": False}


def _timing() -> dict:
    try:
        with open(TIMING_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _prog_start(kind: str, steps: list):
    now = time.time()
    _PROG.clear()
    _PROG.update(running=True, kind=kind, steps=steps, i=0, t0=now, ts=now, took={}, est={**_DEFAULT_SECS, **_timing()})


def _prog_mark(step: str):
    """The run has reached `step` (a later step of the list; anything else is ignored)."""
    p = _PROG
    if not p.get("running") or step not in p["steps"] or p["steps"].index(step) <= p["i"]:
        return
    now = time.time()
    p["took"][p["steps"][p["i"]]] = now - p["ts"]
    p["i"], p["ts"] = p["steps"].index(step), now


def _prog_end():
    p = _PROG
    if not p.get("running"):
        return
    p["took"][p["steps"][p["i"]]] = time.time() - p["ts"]
    t = _timing()
    t.update({k: round(v, 2) for k, v in p["took"].items()})
    try:
        with open(TIMING_PATH, "w", encoding="utf-8") as fh:
            json.dump(t, fh, indent=1)
    except OSError:
        pass
    p["running"] = False


def progress() -> dict:
    """{running, kind, step, i, n, elapsed, remaining, pct} of the run going now ({running: False} when none)."""
    p = dict(_PROG)
    if not p.get("running"):
        return {"running": False}
    now = time.time()
    steps, i, est = p["steps"], p["i"], p["est"]
    e = lambda st: max(float(est.get(st, 3)), 0.2)   # noqa: E731
    in_step = now - p["ts"]
    remaining = max(e(steps[i]) - in_step, min(1.0, e(steps[i]) * 0.1)) + sum(e(st) for st in steps[i + 1:])
    elapsed = now - p["t0"]
    return {"running": True, "kind": p["kind"], "step": steps[i], "i": i + 1, "n": len(steps),
            "elapsed": round(elapsed, 1), "remaining": round(remaining, 1),
            "pct": round(100 * elapsed / (elapsed + remaining), 1) if elapsed + remaining > 0 else 0}
ROWS_KEPT = 300      # rows a check shows on the page
ROWS_ALL = 20000     # rows a check keeps for the issues report (user, 2026-10-14: "1 button to download the report so that
                     # all issues can be addressed at one go ... in different spreadsheets in 1 file")


# Seasons (user, 2026-10-14: "if the attributes are Winter or PreWinter then they should be avoided as neither they have
# a Buyer's input so they donot have a plan so they can be avoided, check for SOR only since we are making for MAMJ").
# The attributes in season per plan month; a month not listed here puts no attribute off season (nothing is excluded
# on a guess). SalesPlan/backend/season_attributes.json overrides it: {"Mar": ["SUMMER", "OCCASIONAL", "REGULAR"], ...}.
SEASON_PATH = os.path.join(_HERE, "..", "season_attributes.json")
SEASON_DEFAULT = {m: ["SUMMER", "OCCASIONAL", "REGULAR"] for m in ("Mar", "Apr", "May", "Jun")}


def season(months) -> tuple:
    """(set of attributes in season over the plan months, or None = no rule for some month -> everything in season;
    the rule's text)."""
    try:
        with open(SEASON_PATH, encoding="utf-8") as fh:
            cfg = {k[:3].title(): [str(x).strip().upper() for x in v] for k, v in json.load(fh).items()}
        src = "season_attributes.json"
    except (OSError, ValueError):
        cfg, src = SEASON_DEFAULT, "default"
    ins = set()
    for m in months:
        if m[:3] not in cfg:
            return None, f"no season rule for {m} ({src}) - every attribute counted in season"
        ins |= set(cfg[m[:3]])
    return ins, f"{', '.join(sorted(ins))} in season for {', '.join(months)} ({src})"


def _in(attr, ins) -> bool:
    return ins is None or str(attr).upper() in ins or str(attr) in ("-", "")


class Acc:
    """Expected vs plan over many cells: count, off, largest difference and where, the first ROWS_KEPT off rows."""

    def __init__(self, tol=TOL):
        self.tol, self.cells, self.off, self.largest, self.where, self.rows = tol, 0, 0, 0.0, "", []

    def add(self, exp, got, **w):
        d = got - exp
        self.cells += 1
        if abs(d) > abs(self.largest):
            self.largest, self.where = d, " / ".join(str(v) for v in w.values())
        if abs(d) > self.tol:
            self.off += 1
            if len(self.rows) < ROWS_ALL:
                self.rows.append({**w, "Expected": exp, "Plan": got, "Difference": d})

    def out(self, stage, key, title, level, fix="rerun", note=""):
        st = "warn" if not self.cells else "pass" if not self.off else "fail"
        return {"stage": stage, "key": key, "title": title, "level": level, "status": st, "cells": self.cells,
                "off": self.off, "largest": self.largest, "where": self.where, "note": note, "rows": self.rows,
                "fix": fix if st == "fail" else None}


def _plain(stage, key, title, level, status, note, rows=None, fix=None, cells=0, off=0, largest=0.0, where=""):
    return {"stage": stage, "key": key, "title": title, "level": level, "status": status, "cells": cells, "off": off,
            "largest": largest, "where": where, "note": note, "rows": rows or [], "fix": fix if status == "fail" else None}


def _ly_h(x: dict, h: str) -> float:
    """A department's LY in half h ("p1" / "p2"): its actual half-month LY (2026-10-15), else LY / 2 (older plans)."""
    v = x.get("ly_" + h)
    return float(v) if v is not None else float(x.get("ly") or 0.0) / 2


def _lym(m: str) -> str:
    """Plan month "Mar'27" -> its LY month "Mar'26"."""
    return f"{m[:3]}'{int(m[-2:]) - 1:02d}"


def _try(fn, default=None):
    """fn() - or, when it raises, default (the exception itself when no default is given)."""
    try:
        return fn()
    except Exception as e:   # noqa: BLE001 - a source that is down is reported, not fatal
        return default if default is not None else e


# ── versions: what the plan is checked against ─────────────────────────────────────────────────────────────────────
_VER_DB: dict = {}


def _db_versions() -> dict:
    """The AOP publish, BIS save and Calendar snapshot names - database reads, kept a minute (ponytail: a minute-old
    name at worst; the plan stamp check catches a real change)."""
    import time
    if _VER_DB.get("at", 0) > time.time() - 60:
        return _VER_DB["v"]
    from engines.division_plan import _bis_aop, _versions
    from engines.final_results_engine import _bis_saved_at
    v = {}
    a = _try(_bis_aop)
    if isinstance(a, tuple) and a[0]:
        pub = next((x["published_at"] for x in (_try(_versions, []) or []) if x["id"] == a[0]), None)
        v["aop"] = f"{a[1]} (publish {a[0]}" + (f", {str(pub)[:16]}" if pub else "") + ")"
        v["aop_pid"] = a[0]
    else:
        v["aop"] = "not reachable"
    bv = _try(lambda: __import__("engines.department_plan", fromlist=["x"]).get_bis_versions(), [])
    saved = _try(_bis_saved_at)
    v["bis"] = "live BIS" + (f", saved {saved}" if isinstance(saved, str) else "") +         (f" - last saved version: {bv[0]['label']}" if isinstance(bv, list) and bv else "")
    from actuals_manager import _snapshot
    cs = _try(lambda: _snapshot("reindexed")[0])
    v["calendar"] = f"reindexed department sales, computed {str(cs)[:16]}" if not isinstance(cs, Exception) else "not reachable"
    _VER_DB.update(at=time.time(), v=v)
    return v


def versions(source, at, plan) -> dict:
    v = {"plan": f"{source} (made {at})", **_db_versions()}
    from engines.mrp_reapportionment_engine import read_shares
    rs = read_shares() or {}
    v["mrp"] = (f"re-apportionment shares {rs.get('built_at', '')[:16].replace('T', ' ')} on {rs.get('master')}, "
                f"{rs.get('basis')} basis") if rs else "no re-apportionment shares"
    from engines.display_type_engine import load_asp, DT_RESULT_PATH, DT_QTY_PATH
    asp = load_asp()
    v["asp"] = f"{asp.get('source')} ({asp.get('imported_at')}, {asp.get('count')} rows)" if asp else "no ASP imported"
    # the run times from the files' save times - not a load of the ~100 MB run files (2026-10-14 latency)
    when = lambda f: datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S") if os.path.exists(f) else None   # noqa: E731
    v["display_run"], v["qty_run"] = when(DT_RESULT_PATH), when(DT_QTY_PATH)
    v["lfl_ly_base"] = (plan.get("meta") or {}).get("lfl_ly_base")
    return v


# ── 1-3: Calendar, AOP, BIS - one pass over the plan ───────────────────────────────────────────────────────────────
def plan_checks(plan: dict, source: str, ver: dict) -> list:
    from actuals_manager import load_actuals, load_store_div_actuals
    from engines.dept_sales_engine import _aop_lfl_targets, _load_new_dept_map, _store_aop, DIVISIONS, BUYER_BAND_PCT, month_aop
    out = []
    corrected = source != "final_dept_plan.json"
    cal_div = _try(load_store_div_actuals)
    cal_dept = _try(load_actuals, {})
    act_dept = _try(lambda: load_actuals("actual"), {})   # the like-for-like department split is by actual LY (2026-10-14)
    cal_ok = isinstance(cal_div, dict) and bool(cal_div)
    from engines.department_plan import live_growth_matrix
    gm = _try(live_growth_matrix)
    gm_ok = isinstance(gm, dict) and bool(gm)
    nd = _try(_load_new_dept_map, {}) or {}
    new = {(dv, n): c for dv, e in (nd if isinstance(nd, dict) else {}).items() for n, c in (e or {}).items()}
    refs = {}
    for (dv, n), c in new.items():
        keep = 1 - float(c.get("ref_reduction_pct", c.get("alloc_pct", 0)) or 0) / 100
        refs[(dv, c["ref_dept"])] = refs.get((dv, c["ref_dept"]), 1.0) * keep

    c_oth, c_lfl, c_mix, nd_acc, nd_sum = Acc(), Acc(), Acc(), Acc(), {}
    b_g, b_ty = Acc(1e-9), Acc()
    chain, lfl_ty, all_ty = {}, {}, {}
    # non-SSG stores plan on the AOP Forecaster's store plan, split by their reference store (2026-10-14)
    from engines.dept_sales_engine import _aop_store_plan
    aop_st = _try(_aop_store_plan, {}) or {}
    c_aop, grp_ty, grp_n = Acc(), {}, {}
    ssg_st, cl_ty, dept_gr = {}, {}, {}   # (store, month) -> [TY, cluster]; (cluster, month) -> TY; (div, dept) -> [LY, TY, LY x g]
    ratios = {}       # (cluster, month) -> [TY P1 / (LY/2 x g P1 x store balance)] of plain like-for-like rows (2026-10-14)
    lfl_rows = []     # (store, div, month, dept, row, the month's departments, cluster) - checked once the factor is known
    seen_g = set()
    for store, sd in (plan.get("stores") or {}).items():
        lfl = bool(sd.get("is_ssg"))
        for dv, dd in (sd.get("divisions") or {}).items():
            for m, md in ((dd or {}).get("months") or {}).items():
                deps = {k: x for k, x in (md.get("departments") or {}).items() if isinstance(x, dict)}
                ly = sum(float(x.get("ly") or 0.0) for x in deps.values())
                ty = sum(float(x.get("ty") or 0.0) for x in deps.values() if x.get("active", True))
                cal = cal_div.get(store, {}).get(dv, {}).get(_lym(m), 0.0) if cal_ok else 0.0
                ch = chain.setdefault((dv, m), [0.0, 0.0])
                ch[0] += ly
                ch[1] += cal
                all_ty[(dv, m)] = all_ty.get((dv, m), 0.0) + ty
                g_ = sd.get("group") or ("SSG" if lfl else "NSO")
                grp_ty[(g_, dv, m)] = grp_ty.get((g_, dv, m), 0.0) + ty
                if ty > 0:
                    grp_n.setdefault(g_, set()).add(store)
                w = {"Store": store, "Division": dv, "Month": m}
                if not lfl and aop_st:
                    c_aop.add(float((aop_st.get(str(store).upper(), {}).get(dv) or {}).get(m) or 0.0), ty, Group=g_, **w)
                if lfl:
                    lfl_ty[(dv, m)] = lfl_ty.get((dv, m), 0.0) + ty
                    cl = sd.get("cluster") or ""
                    e = ssg_st.setdefault((store, m), [0.0, cl])
                    e[0] += ty
                    cl_ty[(cl, m)] = cl_ty.get((cl, m), 0.0) + ty
                    ad = act_dept.get(store, {}).get(dv, {}) if isinstance(act_dept, dict) else {}
                    asum = sum(v.get(_lym(m), 0.0) for v in ad.values() if isinstance(v, dict))
                    if cal_ok:
                        c_lfl.add(asum if asum > 0 else cal, ly, **w)
                        cd = ad if asum > 0 else (cal_dept.get(store, {}).get(dv, {}) if isinstance(cal_dept, dict) else {})
                        csum = asum if asum > 0 else sum(v.get(_lym(m), 0.0) for v in cd.values() if isinstance(v, dict))
                        k = ly / csum if csum else 0.0
                        for dp, x in deps.items():
                            if (dv, dp) in new:
                                continue
                            c_mix.add(cd.get(dp, {}).get(_lym(m), 0.0) * k, float(x.get("ly") or 0.0), **w, Department=dp)
                    for dp, x in deps.items():
                        if not x.get("active", True) or "g_p1" not in x:
                            continue
                        if gm_ok and (dv, dp, m) not in seen_g and (dv, dp) not in new:
                            seen_g.add((dv, dp, m))
                            for h in ("P1", "P2"):
                                b_g.add(float(gm.get(dv, {}).get(dp, {}).get(f"{m} {h}", 100.0)), float(x.get(f"g_{h.lower()}", 100.0)),
                                        Division=dv, Department=dp, Month=f"{m} {h}")
                        if (dv, dp) not in new and (dv, dp) not in refs and x.get("ly"):
                            for h in ("p1", "p2"):   # each half on its own LY half and factor (P1 / P2, 2026-10-15)
                                bb = _ly_h(x, h) * float(x["g_" + h]) / 100 * float(x.get("bal_" + h, 1.0))
                                if bb > 1e-6:
                                    ratios.setdefault((cl, m, h), []).append(float(x["ty_" + h]) / bb)
                        if (dv, dp) not in new:
                            dg = dept_gr.setdefault((dv, dp), [0.0, 0.0, 0.0])
                            dg[0] += float(x.get("ly") or 0.0)
                            dg[1] += float(x.get("ty") or 0.0)
                            dg[2] += sum(_ly_h(x, h) * float(x.get("g_" + h, x["g_p1"])) / 100 for h in ("p1", "p2"))
                        lfl_rows.append((store, dv, m, dp, x, deps, cl))
                elif cal_ok:
                    c_oth.add(cal, ly, **w)
                # a new department = its preset % of its reference's plan before the reference's own cut, every store x
                # month (user, 2026-10-14: "add a check that the new department - ref department ratio is maintained as per
                # the preset at BIS")
                for (dvn, n), c in new.items():
                    x, r = deps.get(n), deps.get(c["ref_dept"])
                    if dvn != dv or x is None or r is None or not r.get("active", True):
                        continue
                    kp = refs.get((dv, c["ref_dept"]), 1.0)
                    pct = float(c.get("new_dept_pct", c.get("alloc_pct", 0)) or 0) / 100
                    rt = float(r.get("ty") or 0.0) / kp if kp else 0.0
                    nd_acc.add(rt * pct, float(x.get("ty") or 0.0), **w, Department=n, Reference=c["ref_dept"])
                    e = nd_sum.setdefault((dv, n, c["ref_dept"]), [0.0, 0.0, pct, 1 - kp])
                    e[0] += float(x.get("ty") or 0.0)
                    e[1] += rt
    st1 = "Calendar → LY"
    if cal_ok:
        out.append(c_oth.out(st1, "ly_other", "Store × Division × Month (other stores): plan LY = Calendar reindexed sales", "Division"))
        out.append(c_lfl.out(st1, "ly_lfl", "Store × Division × Month (like-for-like): plan LY = actual LY sales (reindexed where it has none)", "Division",
                             note="The colleague's method (2026-10-14): the like-for-like LY is actual sales; the AOP enters as the cluster cap."))
        out.append(c_mix.out(st1, "ly_mix", "Store × Department × Month (like-for-like): department LY = the store-division LY split by actual LY department cont %", "Department",
                           note="Departments carry their actual LY sales (the reindexed mix only where a store × division × month has none)."))
        rows = [{"Division": dv, "Month": m, "Plan LY (₹L)": a, "Calendar (₹L)": c, "Plan − Calendar": a - c}
                for (dv, m), (a, c) in sorted(chain.items())]
        out.append(_plain(st1, "ly_chain", "Division × Month: plan LY vs Calendar (all stores)", "Division", "info",
                          "Not expected to be equal: like-for-like stores carry actual LY sales, the Calendar column is reindexed.", rows))
    else:
        out.append(_plain(st1, "ly_cal", "Calendar sales snapshot", "-", "fail", f"Calendar not reachable: {cal_div}", fix="input"))

    st2 = "AOP → TY"
    tg = _try(_aop_lfl_targets, {}) or {}
    tg = tg if isinstance(tg, dict) else {}
    # the cap (2026-10-14, the colleague's method): each SSG cluster x month = the AOP's plan for its SSG stores (all
    # divisions), the clusters scaled so they add to the AOP plan of the month; the division totals float
    a1, a_st, cl_a, mon_a = Acc(), Acc(), {}, {}
    for (store, m), (t_, cl) in ssg_st.items():
        a_ = _store_aop(aop_st, store, DIVISIONS, m) if aop_st else 0.0
        cl_a[(cl, m)] = cl_a.get((cl, m), 0.0) + a_
        mon_a[m] = mon_a.get(m, 0.0) + a_
    mon_t = {m: month_aop(sum(float(mm.get(m) or 0.0) for mm in tg.values()), mon_a[m], len(tg)) for m in mon_a}
    for (cl, m), a_ in sorted(cl_a.items()):
        k_ = mon_t[m] / mon_a[m] if mon_a.get(m) and mon_t.get(m) else 1.0
        a1.add(a_ * k_, cl_ty.get((cl, m), 0.0), Cluster=cl, Month=m)
    out.append(a1.out(st2, "aop_div", f"SSG cluster × Month (all divisions): like-for-like plan TY = AOP {ver.get('aop', '')}", "Cluster",
                      note=("Corrected plans move TY on purpose. " if corrected else "") +
                      "Capped at the cluster across divisions (the colleague's method): the division totals follow the buyer's growth."))
    # every SSG store x month on its AOP store plan (the store balance, scaled with its cluster)
    st_cl = {}
    for (store, m), (t_, cl) in ssg_st.items():
        a_ = _store_aop(aop_st, store, DIVISIONS, m) if aop_st else 0.0
        if a_ > 0 and t_ > 0:
            st_cl.setdefault((cl, m), []).append((store, t_, a_))
    for (cl, m), rs in sorted(st_cl.items()):
        T_, A_ = sum(r[1] for r in rs), sum(r[2] for r in rs)
        for store, t_, a_ in rs:
            a_st.add(a_ * T_ / A_, t_, Store=store, Cluster=cl, Month=m)
    out.append(a_st.out(st2, "aop_ssg_store", "Store × Month (SSG, all divisions): plan TY = the AOP Forecaster's store plan", "Store",
                        note="Each SSG store lands on its AOP store plan (scaled with its cluster); every department keeps its cluster total "
                             "(two-way balance). The store × division split follows the buyer's growth."))
    rows = [{"Division": dv, "Month": m, "AOP (₹L)": float(t), "Plan TY (₹L)": lfl_ty.get((dv, m), 0.0),
             "Plan − AOP": lfl_ty.get((dv, m), 0.0) - float(t)} for dv, mm in sorted(tg.items()) for m, t in mm.items() if (dv, m) in lfl_ty]
    out.append(_plain(st2, "aop_div_info", "Division × Month (SSG): plan TY vs AOP", "Division", "info",
                      "Not held per division since the cluster cap (2026-10-14): the months and clusters are on the AOP.", rows))
    want = f"AOP publish {ver.get('aop_pid')}"
    got = (plan.get("meta") or {}).get("aop_publish") or (plan.get("meta") or {}).get("lfl_ly_base")
    out.append(_plain(st2, "aop_pub", "The plan is built on the AOP version BIS plans on", "Division",
                      "pass" if got == want else "fail", f"plan: {got}; BIS plans on: {want}", fix="rerun"))
    if aop_st:
        out.append(c_aop.out(st2, "aop_store", "Store × Division × Month (NSO / Others): plan TY = the AOP Forecaster's store plan", "Store",
                             note="Stores outside the like-for-like 148 plan on the AOP Forecaster's own store plan, split by their "
                                  "reference store's department, P1 / P2, MRP and display type mix."))
    else:
        out.append(_plain(st2, "aop_store", "Store × Division × Month (NSO / Others): plan TY = the AOP Forecaster's store plan", "Store",
                          "fail", "the AOP store plan could not be read", fix="input"))
    G = sorted({g_ for g_, _, _ in grp_ty})
    rows = [{"Division": dv, "Month": m, "Plan TY all stores (₹L)": all_ty[(dv, m)],
             **{f"{g_} (₹L)": grp_ty.get((g_, dv, m), 0.0) for g_ in G}} for (dv, m) in sorted(all_ty)]
    out.append(_plain(st2, "aop_all", "Division × Month: TY by store group", "Division", "info",
                      "Stores with a plan: " + ", ".join(f"{g_} {len(grp_n.get(g_, ()))}" for g_ in G) +
                      ". SSG = like-for-like (BIS growth, capped at the cluster's AOP); NSO = named new / ramp-up stores; "
                      "Others = placeholder stores (NS- / AD- / MAMJ-) - both on the AOP Forecaster's store plan.", rows))

    st3 = "BIS → TY"
    if gm_ok:
        out.append(b_g.out(st3, "bis_g", "Department × Period (like-for-like): growth in the plan = BIS growth in use now", "Department",
                           note="Off = BIS changed after the plan was made; Rectify regenerates it."))
    else:
        out.append(_plain(st3, "bis_g", "BIS growth", "-", "fail", f"BIS growth not reachable: {gm}", fix="input"))
    F = {k: sorted(r)[len(r) // 2] for k, r in ratios.items() if r}
    for store, dv, m, dp, x, deps, cl in lfl_rows:
        if not x.get("ly") and (dv, dp) not in new:
            continue
        for h in ("p1", "p2"):
            f = F.get((cl, m, h))
            if f is None:
                continue
            if (dv, dp) in new:
                c = new[(dv, dp)]
                r = deps.get(c["ref_dept"])
                if not r or "g_" + h not in r:
                    continue
                exp = (_ly_h(r, h) * float(r["g_" + h]) / 100 * f * float(c.get("new_dept_pct", c.get("alloc_pct", 0)) or 0) / 100
                       * float(r.get("bal_" + h, 1.0)))
            else:
                exp = _ly_h(x, h) * float(x["g_" + h]) / 100 * f * refs.get((dv, dp), 1.0) * float(x.get("bal_" + h, 1.0))
            b_ty.add(exp, float(x.get("ty_" + h) or 0.0), Store=store, Division=dv, Department=dp, Month=f"{m} {h.upper()}")
    fs = sorted(F.values())
    fn = f"{len(fs)} cluster × month × half factors, {fs[0]:.4f} to {fs[-1]:.4f}" if fs else "none"
    out.append(b_ty.out(st3, "bis_ty", "Store × Department × Period (like-for-like): TY = LY half × BIS growth × one cluster-month-half factor × the store balance", "Department",
                        fix="rerun" if not corrected else "input",
                        note=("A corrected plan (" + source + ") moves TY on purpose. " if corrected else "") +
                        "New departments = their % of the reference's plan; references keep their share. Factors: " + fn))
    if new:
        rows = [{"Division": dv, "New department": n, "Reference": r, "Preset new %": pct * 100, "Preset reference cut %": cut * 100,
                 "New TY (₹L)": a, "Reference TY before its cut (₹L)": b, "Actual %": a / b * 100 if b else None}
                for (dv, n, r), (a, b, pct, cut) in sorted(nd_sum.items())]
        out.append(nd_acc.out(st3, "new_ratio", "Store × Month: new department = its preset % of the reference department (New Departments preset)",
                              "Department", note="The preset of the New Departments template (BIS new departments): new TY = preset % × the reference's plan "
                              "before its own cut; the reference keeps (1 − its cut %)."))
        out.append(_plain(st3, "new_ratio_sum", "New departments vs their reference - preset and actual %", "Department", "info",
                          f"{len(rows)} new departments", rows))
    # the buyer's growth vs the plan's, department total (user's colleague, 2026-10-14: "the diff buyer growth at total
    # level can be accepted at min of 3% and max of 3%" - their DR - EI column): flagged beyond the band, not capped
    rows = []
    for (dv, dp), (l_, t_, b_) in sorted(dept_gr.items()):
        if l_ > 0 and t_ > 0:
            gb, gp = (b_ / l_ - 1) * 100, (t_ / l_ - 1) * 100
            if abs(gp - gb) > BUYER_BAND_PCT:
                rows.append({"Division": dv, "Department": dp, "LY (₹L)": l_, "Plan TY (₹L)": t_, "Buyer's growth %": gb,
                             "Plan growth %": gp, "Plan − buyer (points)": gp - gb})
    rows.sort(key=lambda r: -abs(r["Plan − buyer (points)"]))
    n_ = sum(1 for v in dept_gr.values() if v[0] > 0 and v[1] > 0)
    out.append(_plain(st3, "buyer_band", f"Department (SSG, all months): plan growth within ±{BUYER_BAND_PCT:g} points of the buyer's growth",
                      "Department", "warn" if rows else "pass",
                      (f"{len(rows)} of {n_} departments outside the band - the cluster cap moved them; the buyer's growth is not changed "
                       "(a flag for the buyer to revise)") if rows else f"all {n_} departments within the band", rows, cells=n_, off=len(rows),
                      largest=rows[0]["Plan − buyer (points)"] if rows else 0.0, where=rows[0]["Department"] if rows else ""))
    from engines.dept_sales_engine import FINAL_STAMP_PATH, _inputs_stamp
    try:
        with open(FINAL_STAMP_PATH, encoding="utf-8") as fh:
            old = json.load(fh).get("inputs")
        cur = _inputs_stamp()
        out.append(_plain(st3, "inputs", "The saved plan is on today's inputs (BIS growth, AOP publish, Calendar snapshot, Department Master, months)",
                          "Division", "pass" if old == cur else ("info" if corrected else "fail"),
                          "current" if old == cur else ("a correction step is applied - regenerate from Final Results to take new inputs" if corrected
                                                        else "an input changed after the plan was made"), fix="rerun"))
    except Exception as e:   # noqa: BLE001
        out.append(_plain(st3, "inputs", "The saved plan is on today's inputs", "Division", "warn", f"could not read the stamp: {e}"))
    return out, (gm if gm_ok else None), new


# ── 4-6: MRP, display type, qty ────────────────────────────────────────────────────────────────────────────────────
def _sum_by(ix: dict, levels: tuple, mask=None) -> dict:
    """{(names of levels): [ly, ty]} of an index (grain_view.make_index layout), inside mask."""
    import numpy as np
    import pandas as pd
    m = np.ones(len(ix["ly"]), dtype=bool) if mask is None else mask
    df = pd.DataFrame({lv: ix["c"][lv][m] for lv in levels})
    df["ly"], df["ty"] = ix["ly"][m], ix["ty"][m]
    g = df.groupby(list(levels), sort=False)[["ly", "ty"]].sum()
    return {tuple(ix["names"][lv][c] for lv, c in zip(levels, k if isinstance(k, tuple) else (k,))): [a, b]
            for k, (a, b) in zip(g.index, g.to_numpy())}


_RUN: dict = {}


def _run_totals(path, load):
    """{run_at, R: {(dept, mrp, display, month): Rs L}} of the Display Type run file - read once per file version (the
    file is ~150 MB; 2026-10-14 latency)."""
    if not os.path.exists(path):
        return None
    mt = os.path.getmtime(path)
    if _RUN.get("mt") != mt:
        run = load(path)
        R, S = {}, {}
        for r in (run or {}).get("rows", []):
            for dt, k in (("TABLE", "table_plan"), ("NON_TABLE", "nontable_plan")):
                kk = (r["dept"], str(r["mrp"]), dt, r["month"])
                v = float(r.get(k) or 0.0)
                R[kk] = R.get(kk, 0.0) + v
                S[r["store"]] = S.get(r["store"], 0.0) + v
        _RUN.update(mt=mt, v={"run_at": (run or {}).get("run_at"), "R": R, "S": S} if run else None)
    return _RUN["v"]


def mrp_checks(gm=None, new=None) -> list:
    from engines import grain_view as gv
    from engines.final_results_engine import _load_dept_attr_map
    from engines.mrp_plan_engine import get_source
    from engines.mrp_reapportionment_engine import read_shares, _find_mapping_file, get_basis, _compare, _plan_period
    from engines.display_type_engine import _load, load_asp, DT_RESULT_PATH, _asp_key, MIX_NOTE, asp_lookup
    out = []
    _prog_mark(CHECK_STEPS[2])
    cube, am = gv._cube(), _load_dept_attr_map()
    dix, mix, xix = gv._index(cube, am, False), gv._mrp_index(cube, am, False), gv._display_index(cube, am, False)
    ins, rule = season(cube["months"])
    _prog_mark(CHECK_STEPS[3])

    st4 = "MRP (re-apportioned)"
    # the buyers' plan file (plan_file_mix, user 2026-10-15): its departments' MRP x display type split is the file's mix
    # per cluster; the re-apportionment check below covers the other departments only
    from engines import plan_file_mix as pfm
    fdep = pfm.departments()
    if fdep:
        fm = pfm.load() or {}
        out.append(_plain(st4, "mrp_file", "MRP x display type of the buyers' plan file's departments = the file's mix", "MRP", "pass",
                          f"{len(fdep)} departments split by {fm.get('source')} (imported {fm.get('imported_at')}): each store by its "
                          f"cluster's like-for-like mix (a non-SSG store by its reference store's cluster), the chain's where the "
                          f"file has no such cluster; shares add to 100% per cluster x department x half by construction"))
    promoted = _try(lambda: __import__("engines.art_nm_engine", fromlist=["x"]).promoted_shares())
    rs = read_shares() or {}
    mf = _find_mapping_file()
    if promoted is not None and not isinstance(promoted, Exception):
        out.append(_plain(st4, "mrp_src", "MRP Cont % in use", "MRP", "info", "the Article Name plan's promoted split (Article Name route)"))
    elif get_source() != "reapp":
        # the buyers' file picked (2026-10-14, for ASP MAMJ 2.xlsx): its departments take the file's split, the rest the
        # re-apportioned one (mrp_plan_engine._load) - checked: every file department x fortnight adds to 100 (or is 0)
        from engines.mrp_plan_engine import _file_shares
        fs = _file_shares()
        sums = {}
        for dv, dd in fs.items():
            for dp, bands in dd.items():
                for ps in bands.values():
                    for pp, v in ps.items():
                        sums[(dp, pp)] = sums.get((dp, pp), 0.0) + float(v or 0)
        bad = sorted(f"{dp} {pp} = {s:.4f}%" for (dp, pp), s in sums.items() if abs(s - 100) > 0.01 and abs(s) > 0.01)
        nf = sum(len(d) for d in fs.values())
        nr = sum(1 for dv, d in (rs.get("shares") or {}).items() for dp in d if dp not in fs.get(dv, {}))
        out.append(_plain(st4, "mrp_src", "MRP Cont % in use = the buyers' file (its departments) + the re-apportioned LY sales (the rest)",
                          "MRP", "fail" if bad else "pass",
                          f"{nf} departments from the buyers' MRP Cont % file, {nr} on the re-apportionment"
                          + (f"; not adding to 100: {', '.join(bad[:10])}" if bad else "; every file department × fortnight adds to 100% (or is 0)"),
                          fix="input"))
    else:
        cur_m, cur_b = os.path.basename(mf or ""), get_basis()
        fresh = bool(rs) and rs.get("master") == cur_m and rs.get("basis") == cur_b and bool(mf) and \
            rs.get("built_at", "") >= datetime.datetime.fromtimestamp(os.path.getmtime(mf)).isoformat(timespec="seconds")
        out.append(_plain(st4, "mrp_src", "MRP Cont % = the latest re-apportionment on the master in use", "MRP",
                          "pass" if fresh else "fail",
                          f"shares {rs.get('built_at', '-')} on {rs.get('master')} ({rs.get('basis')}); master in use {cur_m} ({cur_b})", fix="rerun"))
        # the shares in use = the re-apportioned LY mix, recomputed from the re-apportionment's LY on the new MRPs (the
        # table the display split reads, kept on disk - not a 30 s re-run of the re-apportionment; 2026-10-14 latency)
        from engines.display_type_engine import _mix_tables
        g = _mix_tables()["g_all"].groupby(["department", "mrp", "month"], sort=False)["v"].sum()
        tot = g.groupby(level=[0, 2]).transform("sum")
        pct = (g / tot * 100).where(tot > 0)
        sh = rs.get("shares") or {}
        dept_div = {dp: dv for dv, d in sh.items() for dp in d}
        acc = Acc(1e-6)
        seen = set()
        for (dp, mr, pm), v in pct.items():
            if v != v or v <= 0 or dp in fdep:   # the file's departments follow the file (mrp_file above)
                continue
            dv = dept_div.get(dp, "-")
            seen.add((dv, dp, mr, pm))
            acc.add(float(v), float(((sh.get(dv) or {}).get(dp) or {}).get(mr, {}).get(f"{pm} P1", 0.0)),
                    Division=dv, Department=dp, MRP=mr, Month=pm)
        for dv, d in sh.items():
            for dp, ks in d.items():
                if dp in fdep:
                    continue
                for mr, ps in ks.items():
                    for pk, v in ps.items():
                        if pk.endswith(" P1") and (dv, dp, mr, pk[:-3]) not in seen:
                            acc.add(0.0, float(v), Division=dv, Department=dp, MRP=mr, Month=pk[:-3])
        out.append(acc.out(st4, "mrp_mix", "Department × MRP × Month: MRP Cont % = the re-apportioned LY mix (backward)", "MRP"))
    a_ty, a_ly = Acc(), Acc()
    D = _sum_by(dix, ("division", "department", "month"))
    M = _sum_by(mix, ("division", "department", "month"))
    for k in set(D) | set(M):
        d, mm = D.get(k, [0.0, 0.0]), M.get(k, [0.0, 0.0])
        a_ty.add(d[1], mm[1], Division=k[0], Department=k[1], Month=k[2])
        a_ly.add(d[0], mm[0], Division=k[0], Department=k[1], Month=k[2])
    out.append(a_ty.out(st4, "mrp_fwd", "Division × Department × Month: department TY = Σ MRPs (forward)", "MRP"))
    out.append(a_ly.out(st4, "mrp_back", "Division × Department × Month: department LY = Σ MRPs (backward)", "MRP"))
    ns = mix["c"]["mrp"] == mix["pos"]["mrp"].get(gv.NO_SPLIT, -1)
    nsr = [(k, v) for k, v in sorted(_sum_by(mix, ("division", "department", "attribute"), ns).items()) if abs(v[1]) > 1e-9]
    rows = [{"Division": k[0], "Department": k[1], "Attribute": k[2], "LY (₹L)": v[0], "TY not split (₹L)": v[1]} for k, v in nsr if _in(k[2], ins)]
    off_s = sum(v[1] for k, v in nsr if not _in(k[2], ins))
    out.append(_plain(st4, "mrp_none", "In-season departments the MRP split doesn't cover", "MRP", "fail" if rows else "pass",
                      (f"₹{sum(r['TY not split (₹L)'] for r in rows):,.2f} L in {len(rows)} in-season departments sits under 'No MRP split' - cover them in the MRP master (or a buyers' file) to split it."
                       if rows else "every in-season department is split")
                      + (f" Off season, left out: ₹{off_s:,.2f} L ({rule})." if off_s > 1e-9 else ""), rows, fix="input", cells=len(D), off=len(rows)))

    st5 = "UDF (display type)"
    u_ty, u_ly = Acc(), Acc()
    MM = _sum_by(mix, ("division", "department", "mrp", "month"))
    XX = _sum_by(xix, ("division", "department", "mrp", "month"))
    for k in set(MM) | set(XX):
        a, b = MM.get(k, [0.0, 0.0]), XX.get(k, [0.0, 0.0])
        u_ty.add(a[1], b[1], Division=k[0], Department=k[1], MRP=k[2], Month=k[3])
        u_ly.add(a[0], b[0], Division=k[0], Department=k[1], MRP=k[2], Month=k[3])
    out.append(u_ty.out(st5, "dt_fwd", "Department × MRP × Month: MRP TY = Σ display types (forward)", "UDF"))
    out.append(u_ly.out(st5, "dt_back", "Department × MRP × Month: MRP LY = Σ display types (backward)", "UDF"))
    srcs = [{"Split from": MIX_NOTE[k], "TY (₹L)": float(xix["x"][f"src_{k}"].sum())} for k in MIX_NOTE]
    srcs = [r for r in srcs if abs(r["TY (₹L)"]) > 1e-6]
    nonef = float(xix["x"]["src_none"].sum())
    out.append(_plain(st5, "dt_mix", "Display type % = each store's re-apportioned LY mix on that MRP", "UDF",
                      "fail" if nonef > 1e-6 else "pass", f"₹{nonef:,.2f} L has no LY anywhere to split by" if nonef > 1e-6 else
                      "every split MRP has a display type mix (fallbacks listed)", srcs, fix="input"))
    run = _run_totals(DT_RESULT_PATH, _load)
    if not run:
        out.append(_plain(st5, "dt_run", "Display Type run (all planned stores) = the display tree", "UDF", "fail", "not run yet", fix="rerun"))
    else:
        R = run["R"]
        T = _sum_by(xix, ("department", "mrp", "display", "month"))
        acc = Acc()
        for k in set(R) | {k for k in T if k[2] != "-"}:
            acc.add(T.get(k, [0.0, 0.0])[1], R.get(k, 0.0), Department=k[0], MRP=k[1], Display=k[2], Month=k[3])
        out.append(acc.out(st5, "dt_run", f"Display Type run of {run.get('run_at')} (all planned stores) = the display tree", "UDF",
                           note="Off = the plan, the MRP split or the display mix changed after the run; Rectify re-runs it."))
        # every store with a plan reaches the display type level (2026-10-14: the run covered the 148 SSG stores only)
        st_plan = {k[0]: v[1] for k, v in _sum_by(dix, ("store",)).items() if v[1] > 1e-9}
        a_st = Acc()
        for s_, t_ in st_plan.items():
            a_st.add(t_, run.get("S", {}).get(s_, 0.0), Store=s_)
        out.append(a_st.out(st5, "dt_stores", f"Store: plan TY = its Display Type run total - {len(st_plan)} stores with a plan", "Store",
                            note="A non-SSG store takes its reference store's Table / Non-Table mix."))

    st6 = "Qty (ASP master)"
    asp = load_asp()
    proj_all = {k: v for k, v in _sum_by(xix, ("division", "department", "attribute", "mrp", "display", "month")).items()
                if k[4] != "-" and v[1] > 1e-9}
    proj = {k: v for k, v in proj_all.items() if _in(k[2], ins)}
    att = _attribute_checks(dix, mix, gm, new or {}, ins, rule, cube["months"])
    if not asp:
        out.append(_plain(st6, "qty", "Every projected value has an ASP → qty", "UDF", "fail", "no ASP imported (Display Type · ASP)", fix="input"))
        return att(None) + out
    data = asp["data"]
    by_dm = {}
    for r in data.values():
        by_dm.setdefault((r["dept"], str(r["mrp"])), set()).add(r["display_type"])
    depts = {r["dept"] for r in data.values()}
    miss, qty, ok_v, miss_v, cov, fb_v = {}, {}, 0.0, 0.0, {}, 0.0
    for (dv, dp, at, mr, dt, mo), (_, ty) in proj_all.items():
        rec = data.get(_asp_key(dp, mr, dt))
        a, how = asp_lookup(data, dp, mr, dt, mo)   # own, else the other display type's (user, 2026-10-14)
        c = cov.setdefault(at, [0.0, 0.0])
        c[0] += ty
        c[1] += ty if a else 0.0
        if not _in(at, ins):
            continue
        if a:
            ok_v += ty
            fb_v += ty if how != "own" else 0.0
            qty[dv] = qty.get(dv, 0.0) + ty * 1e5 / a
            continue
        miss_v += ty
        why = ("no ASP for this month" if rec else "only the other display type has an ASP" if (dp, mr) in by_dm else
               "MRP not in the ASP master" if dp in depts else "department not in the ASP master")
        k = (dv, dp, at, mr, dt, why)
        e = miss.setdefault(k, {"ty": 0.0, "months": []})
        e["ty"] += ty
        e["months"].append(mo)
    rows = [{"Division": k[0], "Department": k[1], "Attribute": k[2], "MRP": k[3], "Display type": k[4], "Why": k[5],
             "Months": ", ".join(v["months"]), "TY with no qty (₹L)": v["ty"]} for k, v in sorted(miss.items(), key=lambda kv: -kv[1]["ty"])]
    note = (f"₹{ok_v + miss_v:,.2f} L projected over {len(proj):,} department × MRP × display × month cells; "
            f"₹{ok_v:,.2f} L has a qty ({sum(qty.values()):,.0f} pieces: " + ", ".join(f"{d} {q:,.0f}" for d, q in sorted(qty.items())) + ")"
            + (f", ₹{fb_v:,.2f} L of it on the same department × MRP's other display type ASP (fallback)" if fb_v > 1e-9 else "")
            + (f"; ₹{miss_v:,.2f} L has no ASP in the ASP master ({asp.get('source')}) - fix it there and import again." if miss_v else "."))
    out.append(_plain(st6, "qty", "Every projected in-season value has an ASP → qty (all stores)", "UDF", "fail" if rows else "pass",
                      note + f" Season: {rule}.", rows[:ROWS_ALL],
                      fix="input", cells=len(proj), off=sum(len(v["months"]) for v in miss.values()), largest=miss_v))
    out[-1]["all_rows"] = len(rows)
    return att(cov) + out


def _attribute_checks(dix, mix, gm, new, ins, rule, months):
    """The Attributes (season) stage - returned as a function of the ASP coverage, which the qty step works out."""
    from engines import grain_view as gv
    st = "Attributes (season)"
    D = _sum_by(dix, ("division", "department", "attribute"))
    ns = mix["c"]["mrp"] == mix["pos"]["mrp"].get(gv.NO_SPLIT, -1)
    NS = {k[0]: v for k, v in _sum_by(mix, ("attribute",), ns).items()}
    by, off_rows, bis_rows = {}, [], []
    for (dv, dp, at), (ly, ty) in D.items():
        if ty <= 1e-9 and ly <= 1e-9:
            continue
        a = by.setdefault(at, {"depts": 0, "ly": 0.0, "ty": 0.0, "bis": 0})
        a["ly"] += ly
        a["ty"] += ty
        if ty > 1e-9:
            a["depts"] += 1
        has = gm is not None and all(f"{m} P1" in (gm.get(dv, {}).get(dp) or {}) for m in months)
        a["bis"] += 1 if (has and ty > 1e-9) else 0
        if not _in(at, ins) and ty > 1e-9:
            off_rows.append({"Division": dv, "Department": dp, "Attribute": at, "LY (₹L)": ly, "TY planned (₹L)": ty,
                             "BIS growth": "yes" if has else "no"})
        if _in(at, ins) and ty > 1e-9 and gm is not None and not has and (dv, dp) not in new:
            miss = [m for m in months if f"{m} P1" not in (gm.get(dv, {}).get(dp) or {})]
            bis_rows.append({"Division": dv, "Department": dp, "Attribute": at, "TY (₹L)": ty, "Months with no BIS growth": ", ".join(miss)})

    def build(cov):
        rows = []
        for at, a in sorted(by.items(), key=lambda kv: -kv[1]["ty"]):
            nsv = NS.get(at, [0.0, 0.0])[1]
            c = (cov or {}).get(at)
            rows.append({"Attribute": at, "Season": "in" if _in(at, ins) else "off", "Departments planned": a["depts"],
                         "LY (₹L)": a["ly"], "TY (₹L)": a["ty"], "With BIS growth": f"{a['bis']} of {a['depts']}",
                         "MRP split %": abs(round((1 - nsv / a["ty"]) * 100, 1)) if a["ty"] else None,
                         "ASP coverage %": round(c[1] / c[0] * 100, 1) if c and c[0] else None})
        offv = sum(r["TY planned (₹L)"] for r in off_rows)
        return [
            _plain(st, "att_season", "Attributes in / off season for the plan months", "Attribute", "info",
                   rule + ". Off-season attributes are left out of the MRP-split and qty checks.", rows),
            _plain(st, "att_off", "Off-season departments carrying a plan", "Department", "warn" if off_rows else "pass",
                   (f"₹{offv:,.2f} L planned in {len(off_rows)} off-season departments - they have no buyer's plan for these months; "
                    "make them inactive in the Department Master (or 0 in BIS) if they should carry none." if off_rows else "no off-season department carries a plan"),
                   sorted(off_rows, key=lambda r: -r["TY planned (₹L)"]), fix="input", off=len(off_rows)),
            _plain(st, "att_bis", "In-season departments with a BIS growth for every plan month", "Department",
                   "fail" if bis_rows else ("pass" if gm is not None else "warn"),
                   (f"{len(bis_rows)} in-season departments plan ₹{sum(r['TY (₹L)'] for r in bis_rows):,.2f} L with no BIS growth in some month (planned at LY there)"
                    if bis_rows else "every in-season department has BIS growth" if gm is not None else "BIS not reachable"),
                   bis_rows, fix="input", off=len(bis_rows)),
        ]
    return build


def _fingerprint(ver: dict) -> str:
    return json.dumps({k: ver.get(k) for k in ("plan", "aop", "bis", "calendar", "mrp", "asp", "display_run")}, sort_keys=True, default=str)


_LAST: dict = {}


def _inputs_fp() -> tuple:
    """Everything the check-up reads, cheaply: file times, the re-apportionment's key, the minute-cached versions."""
    from engines.final_results_engine import _pipeline_status
    from engines.display_type_engine import DT_ASP_PATH, DT_RESULT_PATH, DT_QTY_PATH
    from engines.mrp_reapportionment_engine import compare_key, SHARES_PATH
    from engines.dept_sales_engine import NEW_DEPT_MAP_PATH, FINAL_STAMP_PATH
    from engines.department_plan import STATE_PATH
    mt = lambda f: os.path.getmtime(f) if f and os.path.exists(f) else None   # noqa: E731
    return (tuple(mt(f) for f in (_pipeline_status().get("active_file"), FINAL_STAMP_PATH, DT_ASP_PATH, DT_RESULT_PATH, DT_QTY_PATH,
                                   SHARES_PATH, NEW_DEPT_MAP_PATH, STATE_PATH, SEASON_PATH)),
            _try(compare_key, None), json.dumps(_db_versions(), sort_keys=True, default=str))


def checkup(fresh: bool = False) -> dict:
    """The last check-up while none of its inputs changed (instant), else a new one. fresh = always check again."""
    fp = _try(_inputs_fp)
    if not fresh and _LAST.get("fp") == fp and not isinstance(fp, Exception):
        return {**_LAST["r"], "cached": True}
    r = run_checkup()
    if r.get("ok") and not isinstance(fp, Exception):
        _LAST.update(fp=fp, r=r)
    return r


def run_checkup() -> dict:
    own = not _PROG.get("running")   # a Rectify run has already started the bar with its own steps
    if own:
        _prog_start("check", CHECK_STEPS)
    try:
        return _run_checkup()
    finally:
        if own:
            _prog_end()


# The rules in force, recorded on every check-up (user, 2026-10-15: "update the rules wherever they are being changed ...
# I want the run through to be as smooth and as accurate to its manual counterpart as it can be unless i change or update
# the rules"): each rule setting the engines read, with the time any of them last changed (SalesPlan/backend/
# rules_log.json, newest first, business data). The rule book: docs/business-rules/RULE_BOOK.md.
RULES_LOG = os.path.join(_HERE, "..", "rules_log.json")


def rules_in_force(plan: dict) -> dict:
    from engines.mrp_plan_engine import get_source
    from engines import plan_file_mix as pfm
    from engines.display_type_engine import load_asp
    from engines.dept_sales_engine import _load_new_dept_map, BUYER_BAND_PCT
    ft = _try(lambda: json.load(open(os.path.join(_HERE, "..", "..", "..", "Buyer's Input Sheet", "factor_table.json"), encoding="utf-8")), {})
    nd = _try(_load_new_dept_map, {}) or {}
    asp = _try(load_asp, None) or {}
    fm = _try(pfm.load, None) or {}
    ins, rule = season((plan or {}).get("months") or ["Mar'27", "Apr'27", "May'27", "Jun'27"])
    meta = (plan or {}).get("meta") or {}
    return {
        "planner_growth": {"matrix": "Matrix", "weighted": "Weighted builder", "continuous": "Continuous", "ml": "Ridge regression (ML)",
                           "factor1": "Planner input (Factor 1)"}.get((ft or {}).get("mode") if isinstance(ft, dict) else None, "Matrix"),
        "aop_publish": meta.get("aop_publish"),
        "season": rule,
        "new_departments": sorted(f"{n} = {c.get('new_dept_pct')}% of {c.get('ref_dept')}" for e in nd.values() for n, c in (e or {}).items()),
        "buyer_band_pts": BUYER_BAND_PCT,
        "plan_file_mix": f"{fm.get('source')} ({fm.get('imported_at')})" if fm else None,
        "asp": f"{asp.get('source')} ({asp.get('imported_at')}, {asp.get('count')} rows)" if asp else None,
        "mrp_split_other_depts": get_source(),
    }


def _log_rules(r: dict) -> tuple:
    """(when the rules last changed, the keys that changed then) - appends to rules_log.json when they differ."""
    log = _try(lambda: json.load(open(RULES_LOG, encoding="utf-8")), []) or []
    if not isinstance(log, list):
        log = []
    last = log[0] if log else None
    if not last or last.get("rules") != r:
        changed = sorted(k for k in r if not last or (last.get("rules") or {}).get(k) != r[k])
        log.insert(0, {"at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "changed": changed, "rules": r})
        try:
            from plan_cache import save_json
            save_json(RULES_LOG, log[:500])
        except OSError:
            pass
        last = log[0]
    return last["at"], last.get("changed") or []


def _run_checkup() -> dict:
    from engines.reconciliation import _active_plan
    t0 = time.time()
    plan, source, at = _active_plan()
    if plan is None:
        return {"ok": False, "error": "No saved plan yet - Generate Base Plan first"}
    ver = versions(source, at, plan)
    _prog_mark(CHECK_STEPS[1])
    checks, gm, new = plan_checks(plan, source, ver)
    try:
        checks += mrp_checks(gm, new)
    except Exception as e:   # noqa: BLE001 - the MRP / display stage not ready: say so
        checks.append(_plain("MRP (re-apportioned)", "mrp_err", "MRP / display type / qty checks", "MRP", "fail", f"could not run: {e}", fix="rerun"))
    try:
        rr = rules_in_force(plan)
        at_, ch = _log_rules(rr)
        checks.insert(0, _plain("Rules", "rules", "Rules in force (docs/business-rules/RULE_BOOK.md)", "Rules", "info",
                                f"last changed {at_}" + (f" ({', '.join(ch)})" if ch else "") + " - log: rules_log.json",
                                [{"Rule": k, "In force": ", ".join(v) if isinstance(v, list) else v} for k, v in rr.items()]))
    except Exception as e:   # noqa: BLE001 - never block the check-up on the register
        checks.insert(0, _plain("Rules", "rules", "Rules in force", "Rules", "info", f"could not read: {e}"))
    fails = [c for c in checks if c["status"] == "fail"]
    status = "fail" if fails else "warn" if any(c["status"] == "warn" for c in checks) else "pass"
    try:
        with open(SIGNOFF_PATH, encoding="utf-8") as fh:
            so = json.load(fh)
        so["current"] = so.get("fingerprint") == _fingerprint(ver)
    except (OSError, ValueError):
        so = None
    return {"ok": True, "status": status, "versions": ver, "checks": checks, "signoff": so,
            "fixable": any(c["fix"] == "rerun" for c in fails),
            "needs_input": any(c["fix"] == "input" for c in checks if c["status"] in ("fail", "warn")),
            "checked_at": datetime.datetime.now().strftime("%d %b %Y %H:%M:%S"), "seconds": round(time.time() - t0, 1)}


def rectify() -> dict:
    """Re-run the chain - the saved plan on today's inputs, the MRP Cont % from the master in use, the Display Type run
    (and its Qty run when an ASP is imported) - then check again. Inputs (ASP, MRP master, BIS) are never changed."""
    if not _RUN_LOCK.acquire(blocking=False):
        from fastapi import HTTPException
        raise HTTPException(409, "A rectify run is already going")
    log = []
    from engines.mrp_plan_engine import get_source
    from engines import display_type_engine as dte
    steps = (["Department plan on today's inputs"] + (["MRP Cont % from the master in use"] if get_source() == "reapp" else [])
             + ["Display Type run", "Display Type validation"] + (["Qty run"] if dte.load_asp() else []) + CHECK_STEPS)
    _prog_start("rectify", steps)
    try:
        try:
            from engines.dept_sales_engine import refresh_saved_plan, _CORRECTED, _BASE
            if any(os.path.exists(os.path.join(_BASE, "..", f)) for f in _CORRECTED):
                log.append("Department plan: a correction step is applied - left as it is (regenerate from Final Results)")
            else:
                log.append("Department plan: regenerated on today's inputs" if refresh_saved_plan() else "Department plan: already on today's inputs")
            if get_source() == "reapp":
                _prog_mark("MRP Cont % from the master in use")
                from engines.mrp_reapportionment_engine import rebuild_shares
                r = rebuild_shares()
                log.append(f"MRP Cont %: rebuilt from {r.get('master')} ({r.get('departments')} departments)")
            _prog_mark("Display Type run")
            r = dte.run_plan()
            log.append(f"Display Type run: {r['rows']:,} rows")
            _prog_mark("Display Type validation")
            v = dte.validate()
            log.append(f"Display Type validation: {v['errors']} errors, {v['warnings']} warnings")
            if dte.load_asp():
                _prog_mark("Qty run")
                q = dte.run_qty()
                log.append(f"Qty run: {q['rows']:,} rows, {q['missing_asp']:,} without an ASP")
        except Exception as e:   # noqa: BLE001 - say where it stopped
            log.append(f"Stopped: {getattr(e, 'detail', e)}")
        return {**checkup(fresh=True), "log": log}   # the check steps run inside this bar too
    finally:
        _prog_end()
        _RUN_LOCK.release()


def sign_off(user: str) -> dict:
    r = checkup()
    if not r.get("ok"):
        return r
    fails = [c["title"] for c in r["checks"] if c["status"] == "fail"]
    if fails:
        from fastapi import HTTPException
        raise HTTPException(409, f"{len(fails)} check(s) still fail - Rectify or fix the inputs first: {fails[0]}")
    so = {"at": datetime.datetime.now().strftime("%d %b %Y %H:%M"), "by": user or "-", "fingerprint": _fingerprint(r["versions"]),
          "versions": r["versions"], "warnings": [c["title"] for c in r["checks"] if c["status"] == "warn"]}
    with open(SIGNOFF_PATH, "w", encoding="utf-8") as fh:
        json.dump(so, fh, ensure_ascii=False, indent=1)
    r["signoff"] = {**so, "current": True}
    return r


def for_page(r: dict) -> dict:
    """The check-up as the page gets it: each check's first ROWS_KEPT rows (all_rows = how many there are)."""
    if not r.get("checks"):
        return r
    return {**r, "checks": [{**c, "rows": c["rows"][:ROWS_KEPT], "all_rows": len(c["rows"])} for c in r["checks"]]}


SHEET = {"qty": "Qty - no ASP", "mrp_none": "MRP - not split", "att_off": "Off-season with plan", "att_bis": "No BIS growth",
         "dt_mix": "Display - no LY mix", "dt_run": "Display run vs tree", "mrp_mix": "MRP Cont % vs LY mix",
         "mrp_fwd": "Dept TY vs MRPs", "mrp_back": "Dept LY vs MRPs", "dt_fwd": "MRP TY vs displays", "dt_back": "MRP LY vs displays",
         "ly_other": "LY vs Calendar (other)", "ly_lfl": "LY vs AOP base (LFL)", "ly_mix": "Dept LY vs Calendar mix",
         "aop_div": "SSG cluster TY vs AOP", "aop_ssg_store": "SSG store vs AOP store plan", "buyer_band": "Buyer growth ±3 pts", "bis_g": "Growth vs BIS", "bis_ty": "TY vs BIS formula", "new_ratio": "New dept vs preset",
         "att_season": "i - Season by attribute", "new_ratio_sum": "i - New departments", "ly_chain": "i - LY vs Calendar",
         "aop_all": "i - TY by store group", "aop_store": "AOP store plan", "dt_stores": "Stores not at UDF"}


def export_xlsx(r: dict) -> bytes:
    """The issues report: one file - Summary (failures first, with their fix), Versions, then one sheet per failing /
    flagged check with every row it found, then the information tables (i - ...)."""
    import io
    pass  # sheet names cleaned below
    import pandas as pd
    rank = {"fail": 0, "warn": 1, "info": 3, "pass": 2}
    checks = sorted(r["checks"], key=lambda c: rank.get(c["status"], 9))
    used, sheets = set(), []

    def name(c):
        n = "".join("-" if ch in "[]:*?/\\" else ch for ch in SHEET.get(c["key"], c["title"]))[:31]   # Excel's banned sheet-name characters
        while n in used:
            n = n[:29] + "_" + str(len(used))
        used.add(n)
        return n
    for c in checks:
        if c["rows"] and c["status"] in ("fail", "warn"):
            sheets.append((name(c), c))
    for c in checks:
        if c["rows"] and c["status"] == "info":
            sheets.append((name(c), c))
    where = {id(c): n for n, c in sheets}
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        wb = xw.book
        hd = wb.add_format({"bold": True, "bg_color": "#E8EFEA", "border": 1, "text_wrap": True, "valign": "top"})
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})
        col = {"fail": wb.add_format({"bold": True, "font_color": "#B91C1C"}), "warn": wb.add_format({"bold": True, "font_color": "#B45309"}),
               "pass": wb.add_format({"bold": True, "font_color": "#15803D"}), "info": wb.add_format({"font_color": "#475569"})}
        summ = pd.DataFrame([{"Status": c["status"].upper(), "Stage": c["stage"], "Level": c["level"], "Check": c["title"],
                              "Cells checked": c["cells"], "Off": c["off"], "Largest gap (₹L)": c["largest"], "Where": c["where"],
                              "Fix": {"rerun": "Rectify (re-run the chain)", "input": "your input"}.get(c["fix"] or "", ""),
                              "Rows": len(c["rows"]), "Sheet": where.get(id(c), ""), "Note": c["note"]} for c in checks])
        summ.to_excel(xw, sheet_name="Summary", index=False, startrow=2)
        ws = xw.sheets["Summary"]
        ws.write(0, 0, f"Sales Plan reconciliation - checked {r.get('checked_at')} - {sum(c['status'] == 'fail' for c in checks)} fail, "
                       f"{sum(c['status'] == 'warn' for c in checks)} to look at, {sum(c['status'] == 'pass' for c in checks)} pass", hd)
        for j, h in enumerate(summ.columns):
            ws.write(2, j, h, hd)
        for i, c in enumerate(checks, 3):
            ws.write(i, 0, c["status"].upper(), col.get(c["status"]))
            if where.get(id(c)):
                ws.write_url(i, 10, f"internal:'{where[id(c)]}'!A1", string=where[id(c)])
        for j, w in enumerate((8, 20, 10, 70, 12, 8, 14, 30, 22, 7, 22, 90)):
            ws.set_column(j, j, w, wrap if j in (3, 11) else None)
        ws.freeze_panes(3, 0)
        pd.DataFrame([{"Source": k, "Version": str(v)} for k, v in r["versions"].items()]).to_excel(xw, sheet_name="Versions", index=False)
        xw.sheets["Versions"].set_column(0, 0, 16)
        xw.sheets["Versions"].set_column(1, 1, 110)
        for n, c in sheets:
            df = pd.DataFrame(c["rows"])
            df.to_excel(xw, sheet_name=n, index=False, startrow=3)
            w = xw.sheets[n]
            w.write(0, 0, f"{c['status'].upper()} - {c['stage']} - {c['title']}", col.get(c["status"]))
            w.write(1, 0, c["note"] or "")
            w.write(2, 0, f"{len(df):,} rows" + (" - fix: " + {"rerun": "Rectify (re-run the chain)", "input": "your input"}[c["fix"]] if c.get("fix") else ""))
            for j, h in enumerate(df.columns):
                w.write(3, j, h, hd)
                w.set_column(j, j, max(12, min(40, int(df[h].astype(str).str.len().max() if len(df) else 10) + 2)))
            w.freeze_panes(4, 0)
            if len(df):
                w.autofilter(3, 0, 3 + len(df), len(df.columns) - 1)
    return buf.getvalue()
