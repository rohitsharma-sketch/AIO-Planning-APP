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

TOL = 1e-6   # Rs lakh (Rs 0.10) for source tie-outs; the additivity checks above stay at 8 decimals
_HERE = os.path.dirname(os.path.abspath(__file__))
SIGNOFF_PATH = os.path.join(_HERE, "..", "checkup_signoff.json")
_RUN_LOCK = threading.Lock()
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
    from engines.grain_view import aop_base_by_store
    from engines.dept_sales_engine import _aop_lfl_targets, _load_new_dept_map
    out = []
    corrected = source != "final_dept_plan.json"
    cal_div = _try(load_store_div_actuals)
    cal_dept = _try(load_actuals, {})
    cal_ok = isinstance(cal_div, dict) and bool(cal_div)
    base = _try(lambda: aop_base_by_store()[1], {})
    base = base if isinstance(base, dict) else {}
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
    ratios = {}       # (div, month) -> [TY P1 / (LY/2 x g P1)] of plain like-for-like rows
    lfl_rows = []     # (store, div, month, dept, row, the month's departments) - checked once the factor is known
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
                w = {"Store": store, "Division": dv, "Month": m}
                if lfl:
                    lfl_ty[(dv, m)] = lfl_ty.get((dv, m), 0.0) + ty
                    b = base.get(store, {}).get(dv, {}).get(m)
                    if cal_ok:
                        c_lfl.add(b if (b and cal > 0) else cal, ly, **w)
                        k = ly / cal if cal else 0.0
                        cd = cal_dept.get(store, {}).get(dv, {}) if isinstance(cal_dept, dict) else {}
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
                            bb = float(x["ly"]) / 2 * float(x["g_p1"]) / 100
                            if bb > 1e-6:
                                ratios.setdefault((dv, m), []).append(float(x["ty_p1"]) / bb)
                        lfl_rows.append((store, dv, m, dp, x, deps))
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
        out.append(c_lfl.out(st1, "ly_lfl", "Store × Division × Month (like-for-like): plan LY = AOP version's LY base (Calendar where it has none)", "Division",
                             note="The engine anchors like-for-like LY on the AOP base its growth was set on; the department mix stays the Calendar's."))
        out.append(c_mix.out(st1, "ly_mix", "Store × Department × Month (like-for-like): department LY = Calendar department mix", "Department"))
        rows = [{"Division": dv, "Month": m, "Plan LY (₹L)": a, "Calendar (₹L)": c, "Plan − Calendar": a - c}
                for (dv, m), (a, c) in sorted(chain.items())]
        out.append(_plain(st1, "ly_chain", "Division × Month: plan LY vs Calendar (all stores)", "Division", "info",
                          "Not expected to be equal: like-for-like stores sit on the AOP base (the gap here is AOP base − Calendar on them).", rows))
    else:
        out.append(_plain(st1, "ly_cal", "Calendar sales snapshot", "-", "fail", f"Calendar not reachable: {cal_div}", fix="input"))

    st2 = "AOP → TY"
    tg = _try(_aop_lfl_targets, {}) or {}
    a1 = Acc()
    for dv, mm in (tg if isinstance(tg, dict) else {}).items():
        for m, t in mm.items():
            if (dv, m) in lfl_ty:
                a1.add(float(t), lfl_ty[(dv, m)], Division=dv, Month=m)
    out.append(a1.out(st2, "aop_div", f"Division × Month: like-for-like plan TY = AOP {ver.get('aop', '')}", "Division",
                      note="Corrected plans move TY on purpose." if corrected else ""))
    want = f"AOP publish {ver.get('aop_pid')}"
    got = (plan.get("meta") or {}).get("lfl_ly_base")
    out.append(_plain(st2, "aop_pub", "The plan is built on the AOP version BIS plans on", "Division",
                      "pass" if got == want else "fail", f"plan: {got}; BIS plans on: {want}", fix="rerun"))
    rows = [{"Division": dv, "Month": m, "Plan TY all stores (₹L)": all_ty[(dv, m)], "LFL TY (₹L)": lfl_ty.get((dv, m), 0.0),
             "Other stores TY (₹L)": all_ty[(dv, m)] - lfl_ty.get((dv, m), 0.0)} for (dv, m) in sorted(all_ty)]
    out.append(_plain(st2, "aop_all", "Division × Month: TY by store group", "Division", "info",
                      "Other (non-LFL / new) stores grow at their division's average BIS growth - not tied to AOP.", rows))

    st3 = "BIS → TY"
    if gm_ok:
        out.append(b_g.out(st3, "bis_g", "Department × Period (like-for-like): growth in the plan = BIS growth in use now", "Department",
                           note="Off = BIS changed after the plan was made; Rectify regenerates it."))
    else:
        out.append(_plain(st3, "bis_g", "BIS growth", "-", "fail", f"BIS growth not reachable: {gm}", fix="input"))
    F = {k: sorted(r)[len(r) // 2] for k, r in ratios.items() if r}
    for store, dv, m, dp, x, deps in lfl_rows:
        f = F.get((dv, m))
        if f is None or (not x.get("ly") and (dv, dp) not in new):
            continue
        for h in ("p1", "p2"):
            if (dv, dp) in new:
                c = new[(dv, dp)]
                r = deps.get(c["ref_dept"])
                if not r or "g_" + h not in r:
                    continue
                exp = float(r["ly"]) / 2 * float(r["g_" + h]) / 100 * f * float(c.get("new_dept_pct", c.get("alloc_pct", 0)) or 0) / 100
            else:
                exp = float(x["ly"]) / 2 * float(x["g_" + h]) / 100 * f * refs.get((dv, dp), 1.0)
            b_ty.add(exp, float(x.get("ty_" + h) or 0.0), Store=store, Division=dv, Department=dp, Month=f"{m} {h.upper()}")
    hold = (plan.get("meta") or {}).get("lfl_hold_on_aop") or {}
    fn = "; ".join(f"{dv} {m} ×{F[(dv, m)]:.6f}" + (f" (AOP hold ×{hold[dv][m]:.6f})" if hold.get(dv, {}).get(m) else "")
                   for dv, m in sorted(F))
    out.append(b_ty.out(st3, "bis_ty", "Store × Department × Period (like-for-like): TY = LY/2 × BIS growth × one division-month factor", "Department",
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
        R = {}
        for r in (run or {}).get("rows", []):
            for dt, k in (("TABLE", "table_plan"), ("NON_TABLE", "nontable_plan")):
                kk = (r["dept"], str(r["mrp"]), dt, r["month"])
                R[kk] = R.get(kk, 0.0) + float(r.get(k) or 0.0)
        _RUN.update(mt=mt, v={"run_at": (run or {}).get("run_at"), "R": R} if run else None)
    return _RUN["v"]


def mrp_checks(gm=None, new=None) -> list:
    from engines import grain_view as gv
    from engines.final_results_engine import _load_dept_attr_map
    from engines.mrp_plan_engine import get_source
    from engines.mrp_reapportionment_engine import read_shares, _find_mapping_file, get_basis, _compare, _plan_period
    from engines.display_type_engine import _load, load_asp, DT_RESULT_PATH, _asp_key, MIX_NOTE, asp_lookup
    out = []
    cube, am = gv._cube(), _load_dept_attr_map()
    dix, mix, xix = gv._index(cube, am, False), gv._mrp_index(cube, am, False), gv._display_index(cube, am, False)
    ins, rule = season(cube["months"])

    st4 = "MRP (re-apportioned)"
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
            if v != v or v <= 0:
                continue
            dv = dept_div.get(dp, "-")
            seen.add((dv, dp, mr, pm))
            acc.add(float(v), float(((sh.get(dv) or {}).get(dp) or {}).get(mr, {}).get(f"{pm} P1", 0.0)),
                    Division=dv, Department=dp, MRP=mr, Month=pm)
        for dv, d in sh.items():
            for dp, ks in d.items():
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
        out.append(_plain(st5, "dt_run", "Display Type run (SSG stores) = the display tree", "UDF", "fail", "not run yet", fix="rerun"))
    else:
        R = run["R"]
        ssg = xix["c"]["stype"] == xix["pos"]["stype"].get("SSG", -1)
        T = _sum_by(xix, ("department", "mrp", "display", "month"), ssg)
        acc = Acc()
        for k in set(R) | {k for k in T if k[2] != "-"}:
            acc.add(T.get(k, [0.0, 0.0])[1], R.get(k, 0.0), Department=k[0], MRP=k[1], Display=k[2], Month=k[3])
        out.append(acc.out(st5, "dt_run", f"Display Type run of {run.get('run_at')} (SSG stores) = the display tree", "UDF",
                           note="Off = the plan, the MRP split or the display mix changed after the run; Rectify re-runs it."))

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
    import time
    from engines.reconciliation import _active_plan
    t0 = time.time()
    plan, source, at = _active_plan()
    if plan is None:
        return {"ok": False, "error": "No saved plan yet - Generate Base Plan first"}
    ver = versions(source, at, plan)
    checks, gm, new = plan_checks(plan, source, ver)
    try:
        checks += mrp_checks(gm, new)
    except Exception as e:   # noqa: BLE001 - the MRP / display stage not ready: say so
        checks.append(_plain("MRP (re-apportioned)", "mrp_err", "MRP / display type / qty checks", "MRP", "fail", f"could not run: {e}", fix="rerun"))
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
    try:
        from engines.dept_sales_engine import refresh_saved_plan, _CORRECTED, _BASE
        if any(os.path.exists(os.path.join(_BASE, "..", f)) for f in _CORRECTED):
            log.append("Department plan: a correction step is applied - left as it is (regenerate from Final Results)")
        else:
            log.append("Department plan: regenerated on today's inputs" if refresh_saved_plan() else "Department plan: already on today's inputs")
        from engines.mrp_plan_engine import get_source
        if get_source() == "reapp":
            from engines.mrp_reapportionment_engine import rebuild_shares
            r = rebuild_shares()
            log.append(f"MRP Cont %: rebuilt from {r.get('master')} ({r.get('departments')} departments)")
        from engines import display_type_engine as dte
        r = dte.run_plan()
        log.append(f"Display Type run: {r['rows']:,} rows")
        v = dte.validate()
        log.append(f"Display Type validation: {v['errors']} errors, {v['warnings']} warnings")
        if dte.load_asp():
            q = dte.run_qty()
            log.append(f"Qty run: {q['rows']:,} rows, {q['missing_asp']:,} without an ASP")
    except Exception as e:   # noqa: BLE001 - say where it stopped
        log.append(f"Stopped: {getattr(e, 'detail', e)}")
    finally:
        _RUN_LOCK.release()
    return {**checkup(fresh=True), "log": log}


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
         "aop_div": "LFL TY vs AOP", "bis_g": "Growth vs BIS", "bis_ty": "TY vs BIS formula", "new_ratio": "New dept vs preset",
         "att_season": "i - Season by attribute", "new_ratio_sum": "i - New departments", "ly_chain": "i - LY vs Calendar",
         "aop_all": "i - TY by store group"}


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
