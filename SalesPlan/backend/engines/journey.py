"""How a number is made, from its sources down to UDF - and the export of every field on the way (user, 2026-10-14:
"i want a journey mapper in the side tile where i can know about how a number was derived till udf. Make sure that each
and every contribution towards the numbers are mapped in a plain flow. Also i want all the fields availble for export
till display type so that the user can easily export the report for fact finding").

journey(store, dept, month, mrp, display) walks one store x department x month (and, when given, one MRP and display
type) through the saved plan, re-deriving each step from its own inputs and checking it lands on the saved number:
  SSG store      actual LY -> its P1 / P2 halves -> x BIS growth per half -> x AOP cap (SSG cluster x month x half, all
                 divisions) -> x store balance per half (onto its AOP store plan) -> x new-department step -> department plan
  NSO / Others   AOP Forecaster store plan (division x month) -> x reference store's department share -> department plan
  then           x MRP share (P1, P2) -> x Table / Non-Table share -> / ASP -> qty
export_rows() is the same chain as one row per store x department x MRP x month (Display Type run + Qty run + plan).
Rs lakh throughout (ASP in Rs per piece)."""
import io

import pandas as pd

from engines import display_type_engine as dte

TOL = 1e-6


def _plan():
    p = dte._dept_plan()
    if not p:
        from fastapi import HTTPException
        raise HTTPException(404, "No department plan yet - Generate Base Plan first")
    return p


def _active(md: dict) -> dict:
    return {d: v for d, v in (md.get("departments") or {}).items() if isinstance(v, dict) and v.get("active", True)}


def _group(sd: dict) -> str:
    return sd.get("group") or ("SSG" if sd.get("is_ssg") else "NSO")


def _mrp_source(div: str, dept: str) -> tuple:
    """(shares {mrp: {period: %}}, where they come from) of a department - the split every MRP reader uses."""
    from engines.mrp_plan_engine import effective_shares, get_source, _file_shares
    sh, inherited = effective_shares()
    bands = (sh.get(div) or {}).get(dept) or {}
    if f"{div}|{dept}" in (inherited or {}):
        src = f"its reference department {inherited[f'{div}|{dept}']}'s MRP split (a new department)"
    elif get_source() == "file" and dept in (_file_shares().get(div) or {}):
        src = "the buyers' MRP Cont % file (MRP Plan · Buyer's Input)"
    else:
        src = "the MRP re-apportionment (LY sales moved onto the new MRPs through the master)"
    return bands, src


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return 0.0


def options(store: str = "", dept: str = "") -> dict:
    """What the pickers offer: planned stores (with their group), the store's departments, months, the department's MRPs."""
    p = _plan()
    st = p["stores"]
    stores = []
    for s, sd in st.items():
        ty = sum(v["ty"] for dd in sd["divisions"].values() for md in dd["months"].values() for v in _active(md).values())
        if ty > 1e-9:
            stores.append({"store": s, "group": _group(sd), "cluster": sd.get("cluster", ""), "ty": ty})
    order = {"SSG": 0, "NSO": 1, "Others": 2}
    stores.sort(key=lambda x: (order.get(x["group"], 9), x["store"]))
    out = {"stores": stores, "months": (p.get("meta") or {}).get("ty_months_active") or [], "depts": [], "mrps": []}
    sd = st.get(store)
    if sd:
        dts = {}
        for dv, dd in sd["divisions"].items():
            for md in dd["months"].values():
                for d, v in _active(md).items():
                    dts[(dv, d)] = dts.get((dv, d), 0.0) + v["ty"]
        out["depts"] = [{"division": dv, "dept": d, "ty": t} for (dv, d), t in sorted(dts.items()) if t > 1e-9]
        dv = next((x["division"] for x in out["depts"] if x["dept"] == dept), None)
        if dv:
            out["mrps"] = sorted(_mrp_source(dv, dept)[0], key=_num)
    return out


def _new_dept_note(div: str, dept: str) -> str:
    from engines.dept_sales_engine import _load_new_dept_map
    nd = (_load_new_dept_map() or {}).get(div) or {}
    if dept in nd:
        c = nd[dept]
        return f"{dept} is a new department: its plan = {c.get('new_dept_pct', c.get('alloc_pct'))}% of {c.get('ref_dept')}'s."
    for new, c in nd.items():
        if c.get("ref_dept") == dept:
            return (f"{dept} is the reference of the new department {new} ({c.get('new_dept_pct', c.get('alloc_pct'))}% of it; "
                    f"{dept} kept at {100 - float(c.get('ref_reduction_pct', 0) or 0):g}%).")
    return ""


def journey(store: str, dept: str, month: str, mrp: str = "", display: str = "") -> dict:
    from fastapi import HTTPException
    from engines.dept_sales_engine import _load_new_dept_map
    p = _plan()
    sd = p["stores"].get(store)
    if not sd:
        raise HTTPException(404, f"Store {store} is not in the plan")
    div = next((dv for dv, dd in sd["divisions"].items()
                if dept in (((dd.get("months") or {}).get(month) or {}).get("departments") or {})), None)
    if not div:
        raise HTTPException(404, f"{dept} has no plan at {store} in {month}")
    rec = sd["divisions"][div]["months"][month]["departments"][dept]
    ssg, group = bool(sd.get("is_ssg")), _group(sd)
    steps, dev = [], []
    from engines.dept_sales_engine import _half_shares
    hs = _half_shares()

    def step(stage, title, text, value=None, formula="", unit="₹ L", **extra):
        steps.append({"stage": stage, "title": title, "text": text, "formula": formula, "value": value, "unit": unit, **extra})

    # the deviation journey (user, 2026-10-15: "explain in simplest words what affected to arrive at this number"):
    # kind "start" = where the number starts, "change" = something that moved it up or down, "split" = a share taken of it
    def move(kind, what, before, after, why, detail=None):
        dev.append({"kind": kind, "what": what, "before": before, "after": after, "change": after - before,
                    "pct": (after / before - 1) * 100 if before else None, "why": why, "detail": detail or []})

    L = lambda v: f"₹{v:,.4f} L"   # noqa: E731
    pc = lambda f: f"{(f - 1) * 100:+.2f}%"   # noqa: E731
    step("Store", f"{store} · {group}",
         f"Cluster {sd.get('cluster') or '-'}, tag {sd.get('tag') or '-'}. " +
         ("A like-for-like (SSG) store: planned on its own LY with BIS's growth." if ssg else
          f"Outside the like-for-like 148: planned on the AOP Forecaster's own store plan, split at every step like its "
          f"reference store {sd.get('ref_used') or '-'} (store master ref: {sd.get('ref_store') or '-'})."), unit="")
    ty, ty1, ty2, ly = rec.get("ty", 0.0), rec.get("ty_p1", 0.0), rec.get("ty_p2", 0.0), rec.get("ly", 0.0)
    lym = f"{month[:3]}'{int(month[-2:]) - 1:02d}"
    derived = None
    if not rec.get("active", True):
        step("Department", f"{dept} is inactive", "An inactive department carries its LY with a plan of 0: BIS sent it as switched "
             "off (-100%: off season, switched off by the buyer / planner, or every month at -100%) or the Department Master has it "
             "inactive.", 0.0)
        move("start", "Last year", ly, ly, f"{dept} sold {L(ly)} at {store} in {lym}.")
        move("change", "Department switched off", ly, 0.0, "It is inactive this month, so its plan is 0.")
        derived = 0.0
    elif ssg:
        from actuals_manager import load_actuals
        cal = float(((load_actuals("actual").get(store, {}).get(div, {}).get(dept) or {}).get(lym)) or 0.0)
        if not cal:   # no actual sales that month: the reindexed mix (the engine's fallback)
            cal = float(((load_actuals().get(store, {}).get(div, {}).get(dept) or {}).get(lym)) or 0.0)
        meta, cl = p.get("meta") or {}, sd.get("cluster") or ""
        hc = ((meta.get("lfl_hold_cluster") or {}).get(cl) or {}).get(month)
        hd = float(((meta.get("lfl_hold_on_aop") or {}).get(div) or {}).get(month) or 1.0)
        h1, h2 = (float(hc.get("P1", 1.0)), float(hc.get("P2", 1.0))) if isinstance(hc, dict) else ((float(hc), float(hc)) if hc else (hd, hd))
        b1, b2 = float(rec.get("bal_p1", rec.get("bal", 1.0))), float(rec.get("bal_p2", rec.get("bal", 1.0)))
        l1 = float(rec["ly_p1"]) if rec.get("ly_p1") is not None else ly / 2
        l2 = float(rec["ly_p2"]) if rec.get("ly_p2") is not None else ly / 2
        g1, g2 = float(rec.get("g_p1") or 0.0), float(rec.get("g_p2") or 0.0)
        step("Department", "Actual LY", f"{dept} at {store} in {lym}: its actual sales (Calendar, own dates) - the plan's LY.", ly,
             formula="Calendar actual snapshot" + ("" if abs(cal - ly) < TOL else f" (reindexed {L(ly)}: no actual sales that month)"))
        src_h = ("its own half-month sales in cluster " + (cl or "-") + " last year (the manual's LY halves)"
                 if (cl.strip().upper(), dept.strip().upper(), lym) in hs["dept"] else
                 f"{store}'s own day-by-day sales last year (the Calendar)" if (str(store).strip().upper(), lym) in hs["store"]
                 else "half and half (no half-month sales to go by)")
        step("Department", "LY halves", f"P1 = days 1-15, P2 = 16th to month end. Split by {src_h}.", ly,
             formula=f"P1 {L(l1)} ({l1 / ly * 100 if ly else 0:.2f}%) + P2 {L(l2)}")
        pre1, pre2 = l1 * g1 / 100, l2 * g2 / 100
        step("Department", "× BIS growth", f"The growth BIS sent for {dept}: P1 {g1 - 100:+.2f}%, P2 {g2 - 100:+.2f}% (each half = its LY × "
             "its growth). It is BIS's plan growth after BIS's own re-calibration to the division AOP (Re-cal Gr% in BIS), not "
             "necessarily the % the buyer typed.", pre1 + pre2, formula=f"{L(l1)} × {g1 / 100:.4f} + {L(l2)} × {g2 / 100:.4f}")
        move("start", "Last year", ly, ly, f"{dept} sold {L(ly)} at {store} in {lym} (actual sales).")
        move("change", "Buyer's growth (BIS)", ly, pre1 + pre2,
             f"BIS planned {((pre1 + pre2) / ly - 1) * 100 if ly else 0:+.2f}% on last year for {dept} "
             f"(P1 {g1 - 100:+.2f}%, P2 {g2 - 100:+.2f}%).",
             [f"P1 (1st-15th): last year {L(l1)} x {g1 / 100:.4f} = {L(pre1)}", f"P2 (16th-end): last year {L(l2)} x {g2 / 100:.4f} = {L(pre2)}",
              f"Last year split by {src_h}"])
        a1, a2 = pre1 * h1, pre2 * h2
        fc = (a1 + a2) / (pre1 + pre2) if pre1 + pre2 else 1.0
        step("Department", "× AOP cap (SSG cluster × month × half)", f"Every like-for-like department of cluster {cl or '-'} in each half "
             f"of {month}, all divisions together, is scaled by one factor so the cluster lands exactly on the AOP's plan for its SSG "
             "stores in that half (the AOP store plan's own total, not the 2-decimal published figure) - the buyer's mix kept, the "
             "division totals free (the colleague's method).", a1 + a2, formula=f"P1 × {h1:.6f}, P2 × {h2:.6f}", factor=fc)
        move("change", "AOP cap (cluster)", pre1 + pre2, a1 + a2,
             f"All the buyers' plans in cluster {cl or '-'} together came to {'more' if fc < 1 else 'less'} than the AOP target for "
             f"its like-for-like stores in {month}, so every department there (all divisions) was scaled {pc(fc)} "
             f"(P1 {pc(h1)}, P2 {pc(h2)}) to land on it." +
             (f" P1 and P2 moved differently because the AOP spreads {month} over its two halves differently from last year's "
              f"sales: it wants {'more' if h2 > h1 else 'less'} of the month in the second half (16th to month end)."
              if abs(h1 - h2) > 0.02 else ""),
             [f"P1: {L(pre1)} x {h1:.6f} = {L(a1)}", f"P2: {L(pre2)} x {h2:.6f} = {L(a2)}",
              f"One factor per half for every like-for-like department of cluster {cl or '-'}, all divisions; the cluster lands "
              "on the AOP store plans of its like-for-like stores (their own total, not the 2-decimal publish)."])
        after = a1 + a2
        if abs(b1 - 1) > 1e-12 or abs(b2 - 1) > 1e-12:
            after = a1 * b1 + a2 * b2
            fb = after / (a1 + a2) if a1 + a2 else 1.0
            step("Department", "× store balance", f"{store} is put on its AOP store plan (all divisions; each half by the AOP's P1 / P2 "
                 "split) while every department keeps its cluster total in that half (a two-way balance).", after,
                 formula=f"P1 × {b1:.6f}, P2 × {b2:.6f}", factor=fb)
            move("change", "Store balance", a1 + a2, after,
                 f"{store} on its own came out {'above' if fb < 1 else 'below'} its AOP target, so its departments were moved "
                 f"{pc(fb)} (P1 {pc(b1)}, P2 {pc(b2)}) to land the store on it; the other stores of the cluster moved the other way "
                 "so each department keeps its cluster total.",
                 [f"P1: {L(a1)} x {b1:.6f} = {L(a1 * b1)}", f"P2: {L(a2)} x {b2:.6f} = {L(a2 * b2)}",
                  f"{store}'s month total lands on its AOP store plan, split P1 / P2 by the AOP's own halves."])
        derived = after
        if _load_new_dept_map():   # the carve + re-balance: per SSG cluster over all divisions (2026-10-14), so every division
            f = ty / after if after else 1.0
            c = ((_load_new_dept_map() or {}).get(div) or {}).get(dept)
            if c:   # a new department: its plan is its reference's (after the re-balance) x its %
                rty = ((sd["divisions"][div]["months"][month]["departments"].get(c.get("ref_dept")) or {}).get("ty") or 0.0)
                pct = float(c.get("new_dept_pct", c.get("alloc_pct")) or 0)
                fml = f"= {c.get('ref_dept')} {L(rty)} × {pct:g}%"
            else:
                fml = f"× {f:.6f}"
            step("Department", "× new-department step", (_new_dept_note(div, dept) + " " if _new_dept_note(div, dept) else "") +
                 "New departments take their % of their reference; the cluster's like-for-like departments are then re-balanced by "
                 "one factor so the cluster stays on the AOP, and the stores back onto their store plans.", ty, formula=fml, factor=f)
            if c:   # a new department: no last year - its number IS its reference's share (the LY / growth lines are 0)
                dev[:] = []
                move("start", f"Reference {c.get('ref_dept')}", rty, rty, f"{dept} is a new department with no last year, so it "
                     f"is planned off its reference department {c.get('ref_dept')}: {L(rty)} at {store} in {month}.")
                move("split", f"{pct:g}% of the reference", rty, ty, f"{dept} = {pct:g}% of {c.get('ref_dept')} (the New "
                     f"departments setting) = {L(ty)}.")
            elif abs(ty - after) > TOL:
                move("change", "New departments", after, ty, (_new_dept_note(div, dept) + " " if c else "") +
                     ("Its plan is its reference's share." if c else
                      f"New departments were carved out of their references and the cluster re-balanced back onto the AOP, "
                      f"which moved {dept} {pc(f)}."))
            derived = ty if abs(f - 1) < 0.25 or _new_dept_note(div, dept) else after   # a large factor on a plain department = not explained
    else:
        from engines.dept_sales_engine import _aop_store_plan
        D = float(((_aop_store_plan().get(str(store).upper()) or {}).get(div) or {}).get(month) or 0.0)
        ref = sd.get("ref_used") or ""
        ract = _active((((p["stores"].get(ref) or {}).get("divisions") or {}).get(div) or {}).get("months", {}).get(month) or {})
        rdiv, rdept = sum(v["ty"] for v in ract.values()), ract.get(dept) or {}
        rshare = rdept.get("ty", 0.0) / rdiv if rdiv else 0.0
        own = _active(sd["divisions"][div]["months"][month])
        odiv = sum(v["ty"] for v in own.values())
        share = ty / odiv if odiv else rshare   # the share the store was split by (its reference's mix at that point)
        step("Department", "AOP Forecaster store plan", f"{store}'s {div} plan for {month} in the AOP version BIS plans on.", D,
             formula="AOP store × division × month")
        derived = D * share
        late = abs(share - rshare) > 1e-9
        step("Department", f"× {ref}'s department share", f"{dept} is {share * 100:.4f}% of {store}'s {div} plan in {month} - "
             f"{ref}'s mix when {store} was split" + (f" (the new-department step then re-balanced {ref}'s cluster, which moved "
             f"{dept} at {ref} to {rshare * 100:.4f}% - {store} keeps the share it was split by)" if late else "") + ".",
             derived, formula=f"{L(D)} × {share:.6f}", factor=share)
        move("start", "AOP target for the store", D, D, f"The AOP gives {store} {L(D)} for {div} in {month} - a store outside the "
             "like-for-like 148 is planned on that target, not on its own last year.")
        move("split", f"{dept}'s share, like {ref}", D, derived, f"{dept} takes {share * 100:.2f}% of it - the share it has in "
             f"{div} at the reference store {ref} (the merchandise-mix reference).")
        mref = hs["mref"].get(str(store).strip().upper()) or str(ref).strip().upper()
        pdv = hs["div"].get((mref, div, month))
        if pdv is not None:
            step("Department", f"P1 / P2 like {mref}", f"The month splits into halves like the month-mix reference {mref}'s {div} AOP: "
                 f"P1 {pdv * 100:.2f}% / P2 {100 - pdv * 100:.2f}% for the whole division (the manual's AOP sheet does the same); "
                 f"{dept} keeps its own shape inside it - P1 {ty1 / ty * 100 if ty else 0:.2f}%.", ty1 + ty2, formula=f"P1 {L(ty1)} + P2 {L(ty2)}")
        else:
            p1s = rdept.get("ty_p1", 0.0) / rdept["ty"] if rdept.get("ty") else 0.5
            step("Department", "P1 / P2 like the reference", f"No month-mix split for {store}: the halves follow {ref}'s plan - "
                 f"P1 {p1s * 100:.2f}% / P2 {100 - p1s * 100:.2f}%.", ty1 + ty2, formula=f"P1 {L(ty1)} + P2 {L(ty2)}")
        if ly > 0:
            step("Department", "Growth on its own LY", f"Its own LY {L(ly)} (Calendar, split like the reference): {(ty / ly - 1) * 100:+.2f}%.", unit="")
    ok = derived is not None and abs(derived - ty) <= TOL
    step("Department", "= Department plan (saved)", f"{dept} at {store}, {month}: P1 {L(ty1)} + P2 {L(ty2)}. "
         + ("The steps above land on it." if ok else f"The steps above give {L(derived or 0)} - {L((derived or 0) - ty)} off."),
         ty, formula=f"LY {L(ly)}" + (f" · {(ty / ly - 1) * 100:+.2f}%" if ly else ""), check=ok)

    mrps, bands, src = [], *_mrp_source(div, dept)
    if bands:
        from apportion import split
        s1 = split(ty1, {m: pm.get(f"{month} P1", 0.0) for m, pm in bands.items()})
        s2 = split(ty2, {m: pm.get(f"{month} P2", 0.0) for m, pm in bands.items()})
        mrps = [{"mrp": m, "p1_pct": bands[m].get(f"{month} P1", 0.0), "p2_pct": bands[m].get(f"{month} P2", 0.0), "ty": s1[m] + s2[m]}
                for m in bands]
    if mrp and mrp in bands:
        x = next(r for r in mrps if r["mrp"] == mrp)
        step("MRP", f"× MRP {mrp} share", f"From {src}: {month} P1 {x['p1_pct']:.4f}%, P2 {x['p2_pct']:.4f}%.", x["ty"],
             formula=f"{L(ty1)} × {x['p1_pct'] / 100:.6f} + {L(ty2)} × {x['p2_pct'] / 100:.6f}")
        move("split", f"MRP {mrp}", ty, x["ty"], f"MRP {mrp} gets {x['ty'] / ty * 100 if ty else 0:.2f}% of {dept} this month "
             f"(P1 {x['p1_pct']:.2f}%, P2 {x['p2_pct']:.2f}%) - from {src}.")
        q, row = dte._qty_frame(), None
        if q:
            df = q["df"]
            hit = df[(df["store"] == store) & (df["dept"] == dept) & (df["mrp"] == str(mrp)) & (df["month"] == month)]
            row = hit.iloc[0].to_dict() if len(hit) else None
        if row:
            how = row.get("contrib_from") or "-"
            who = "" if ssg else f"its reference store {sd.get('ref_used')}: "
            asp_data = (dte.load_asp() or {}).get("data", {})
            for dt, pc_k, pl_k, asp_k, q_k in (("TABLE", "table_contrib", "table_plan", "table_asp", "table_qty"),
                                              ("NON_TABLE", "nontable_contrib", "nontable_plan", "nontable_asp", "nontable_qty")):
                if display and display.upper() != dt:
                    continue
                nm = "Table" if dt == "TABLE" else "Non-Table"
                pc, pl, a, qq = float(row.get(pc_k) or 0), float(row.get(pl_k) or 0), row.get(asp_k), row.get(q_k)
                step("Display type", f"× {nm} share", f"{pc:.4f}% of the MRP - {who}{dte.MIX_NOTE.get(how, how)} (re-apportioned LY sales).", pl,
                     formula=f"{L(x['ty'])} × {pc / 100:.6f}")
                move("split", nm, x["ty"], pl, f"{nm} gets {pc:.2f}% of MRP {mrp} - {who}{dte.MIX_NOTE.get(how, how)}.")
                a = float(a) if a is not None and a == a else 0.0
                how_a = dte.asp_lookup(asp_data, dept, mrp, dt, month)[1] if a else None
                whose = "its own" if how_a == "own" else "the other display type's (fallback)" if how_a else "-"
                step("Qty", f"{nm} ÷ ASP = pieces", (f"ASP ₹{a:,.2f} per piece - {whose} ASP for {dept} × {mrp} × {month} in the ASP master."
                                                    if a else "No ASP - no qty."),
                     float(qq) if qq is not None and qq == qq else None, formula=f"{L(pl)} × 1e5 ÷ ₹{a:,.2f}" if a else "", unit="pieces")
                dev.append({"kind": "qty", "what": f"{nm} pieces", "before": pl, "after": float(qq) if qq is not None and qq == qq else None,
                            "change": None, "pct": None,
                            "why": (f"{L(pl)} at ₹{a:,.2f} a piece ({whose} ASP) = {float(qq):,.0f} pieces." if a and qq is not None and qq == qq
                                    else "No ASP for this MRP and display type, so no pieces.")})
        elif x["ty"] <= 1e-9:
            step("Display type", "No plan on this MRP here", "Nothing to split into Table / Non-Table, so no qty.", unit="")
        else:
            step("Display type", "Not in the Display Type run", "Run Display Type (Plan Run) to split this MRP into Table / Non-Table.", unit="")
    st0 = next((d for d in dev if d["kind"] == "start"), None)
    tot_dev = (ty - st0["after"]) if st0 else 0.0
    for d in dev:   # how much of the deviation (plan - where it started) this effect is
        d["share"] = d["change"] / tot_dev * 100 if d["kind"] == "change" and abs(tot_dev) > 1e-12 else None
    return {"store": store, "group": group, "division": div, "dept": dept, "month": month, "mrp": mrp, "display": display,
            "deviation_total": {"from": st0["what"] if st0 else None, "start": st0["after"] if st0 else None, "plan": ty, "change": tot_dev},
            "steps": steps, "ok": ok, "mrps": sorted(mrps, key=lambda r: -r["ty"]), "mrp_source": src if bands else None,
            "deviation": dev, "story": _story(dev, dept, store, month, ly, ty, ssg)}


def _story(dev: list, dept: str, store: str, month: str, ly: float, ty: float, ssg: bool) -> str:
    """The deviation journey as one short paragraph."""
    L = lambda v: f"₹{v:,.2f} L"   # noqa: E731
    ch = [d for d in dev if d["kind"] == "change"]
    st0 = next((d for d in dev if d["kind"] == "start"), None)
    if st0 and st0["what"].startswith("Reference "):   # a new department
        sp = next((d for d in dev if d["kind"] == "split"), None)
        return (f"{dept} is a new department with no last year, so it is planned as {sp['what'].split(' of')[0]} of its reference "
                f"department {st0['what'][10:]} at {store} in {month}: {L(st0['after'])} x {sp['what'].split(' of')[0]} = {L(ty)}."
                if sp else f"{dept} is a new department with no last year: plan {L(ty)}.")
    if not ssg:
        st = next((d for d in dev if d["kind"] == "start"), None)
        out = f"{store} is not a like-for-like store, so {dept} in {month} is planned on the AOP target: " + \
              (f"{L(st['after'])} for the division, of which {dept} takes its reference store's share = {L(ty)}." if st else f"{L(ty)}.")
        return out + (f" That is {(ty / ly - 1) * 100:+.1f}% on its own last year ({L(ly)})." if ly > 0 else "")
    if not ch:
        return f"{dept} at {store} in {month}: {L(ty)}."
    bis = next((d for d in ch if d["what"].startswith("Buyer")), None)
    parts = [f"Last year {dept} sold {L(ly)} at {store} in {month[:3]}."]
    if bis and bis["pct"] is not None:
        parts.append(f"The buyer's plan (BIS) {'raised' if bis['change'] >= 0 else 'cut'} it {bis['pct']:+.1f}% to {L(bis['after'])}.")
    for d in ch:
        if d is bis or abs(d["change"]) < 1e-9:
            continue
        parts.append(f"{d['what']}: {'+' if d['change'] >= 0 else '-'}{L(abs(d['change']))}" + (f" ({d['pct']:+.1f}%)." if d["pct"] is not None else "."))
    tot = (ty / ly - 1) * 100 if ly else None
    if tot is not None and bis and bis["pct"] is not None:
        parts.append(f"So the plan is {L(ty)}, {tot:+.1f}% on last year - {tot - bis['pct']:+.1f} points from what BIS planned.")
    else:
        parts.append(f"So the plan is {L(ty)}.")
    return " ".join(parts)


def journey_xlsx(store: str, dept: str, month: str, mrp: str = "", display: str = "") -> tuple:
    """The journey as an Excel file in plain words (user, 2026-10-14: "give me an excel downloader for this journey so
    that in plain words can be explained"): sheet Journey = the steps on screen (stage, step, explanation, calculation,
    value); sheet "All MRPs to UDF" = every MRP of the department that month down to Table / Non-Table and pieces."""
    j = journey(store, dept, month, mrp, display)
    sd = _plan()["stores"][store]
    head = [("Store", f"{store} ({j['group']})"), ("Cluster", sd.get("cluster") or "-"), ("Store tag", sd.get("tag") or "-"),
            ("Split follows", sd.get("ref_used") or store), ("Division", j["division"]), ("Department", dept), ("Month", month),
            ("MRP", mrp or "all - see the next sheet"), ("Display type", display or "Table and Non-Table"),
            ("How to read", "Each row is one step; its value is worked out from the row above with the calculation shown. "
                            "Rs lakh unless the unit says pieces. The department row is checked against the saved plan.")]
    steps = pd.DataFrame([{"#": i + 1, "Stage": x["stage"], "Step": x["title"], "In plain words": x["text"],
                           "Calculation": x["formula"], "Value": x["value"], "Unit": x["unit"] or "",
                           "Check": "lands on the saved plan" if x.get("check") is True else "does NOT land on the saved plan" if x.get("check") is False else ""}
                          for i, x in enumerate(j["steps"])])
    allm = export_rows(store=store)
    allm = allm[(allm["Department"] == dept) & (allm["Month"] == month)]
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        pd.DataFrame(head, columns=["", ""]).to_excel(xw, sheet_name="Journey", index=False, header=False)
        steps.to_excel(xw, sheet_name="Journey", index=False, startrow=len(head) + 1)
        mv = pd.DataFrame([{"#": i + 1, "What": d["what"], "Kind": {"start": "starts at", "change": "moved it", "split": "share taken",
                                                                     "qty": "pieces"}[d["kind"]],
                            "Before": d["before"], "After": d["after"], "Change": d["change"], "Change %": d["pct"], "Why, in plain words": d["why"]}
                           for i, d in enumerate(j["deviation"])])
        pd.DataFrame([[j["story"]]], columns=["What moved this number"]).to_excel(xw, sheet_name="What moved it", index=False)
        mv.to_excel(xw, sheet_name="What moved it", index=False, startrow=3)
        wm, wrap2 = xw.sheets["What moved it"], xw.book.add_format({"text_wrap": True, "valign": "top"})
        wm.set_column(0, 0, 100, wrap2); wm.set_column(1, 1, 28); wm.set_column(2, 6, 14); wm.set_column(7, 7, 100, wrap2)
        allm.to_excel(xw, sheet_name="All MRPs to UDF", index=False)
        ws = xw.sheets["Journey"]
        wrap = xw.book.add_format({"text_wrap": True, "valign": "top"})
        bold = xw.book.add_format({"bold": True})
        ws.set_column(0, 0, 14, bold); ws.set_column(1, 1, 14); ws.set_column(2, 2, 30); ws.set_column(3, 3, 80, wrap)
        ws.set_column(4, 4, 45, wrap); ws.set_column(5, 5, 14); ws.set_column(6, 7, 12)
        xw.sheets["All MRPs to UDF"].set_column(0, 40, 16)
    name = f"Journey - {store} - {dept} - {month}{' - ' + mrp if mrp else ''}.xlsx".replace("/", "-")
    return buf.getvalue(), name


# ── the company-level deviation bridge (user, 2026-10-16) ─────────────────────────────────────────────────────────

BRIDGE = [   # (key, name, plain words) - in the order the plan applies them; they add up to plan - last year exactly
    ("bis", "Buyer's growth (BIS)", "The growth the buyers' plan (BIS) put on last year's sales, department by department."),
    ("cap", "AOP cap (cluster)", "Each like-for-like cluster scaled, all divisions together, so each half-month lands on the AOP target."),
    ("bal", "Store balance", "Each like-for-like store moved onto its own AOP target; the other stores of its cluster move the other way."),
    ("newd", "New departments", "New departments carved out of their references and the clusters re-balanced back onto the AOP."),
    ("off", "Departments switched off", "Departments inactive in the plan (off season / switched off): their last year goes to 0."),
    ("nso", "New stores (NSO), on their AOP target", "New stores: planned on their AOP target with their reference store's mix, not on their own (short or no) last year."),
    ("oth", "Other stores, on their AOP target", "The other stores outside the like-for-like 148: planned on their AOP target, not on their last year."),
]
_hol_cache = {}


def _plan_stamp():
    import os
    from engines.dept_sales_engine import FINAL_PLAN_PATH
    return os.path.getmtime(FINAL_PLAN_PATH) if os.path.exists(FINAL_PLAN_PATH) else None


def _effects(p: dict, division: str = "", month: str = "", group: str = "") -> pd.DataFrame:
    """One row per store x department x month: last year, plan and each effect of BRIDGE (they add up to plan - LY)."""
    meta = p.get("meta") or {}
    hold_c, hold_d = meta.get("lfl_hold_cluster") or {}, meta.get("lfl_hold_on_aop") or {}
    recs = []
    for s, sd in p["stores"].items():
        ssg, cl, grp = bool(sd.get("is_ssg")), sd.get("cluster") or "", _group(sd)
        if group and grp != group:
            continue
        for dv, dd in sd["divisions"].items():
            if division and dv != division:
                continue
            for m, md in dd["months"].items():
                if month and m != month:
                    continue
                for d, r in (md.get("departments") or {}).items():
                    if not isinstance(r, dict):
                        continue
                    ly = float(r.get("ly") or 0.0)
                    ty = float(r.get("ty") or 0.0) if r.get("active", True) else 0.0
                    if not ly and not ty:
                        continue
                    e = dict.fromkeys([k for k, _, _ in BRIDGE], 0.0)
                    if not r.get("active", True):
                        e["off"] = -ly
                    elif not ssg:
                        e["nso" if grp == "NSO" else "oth"] = ty - ly
                    else:
                        l1 = float(r["ly_p1"]) if r.get("ly_p1") is not None else ly / 2
                        l2 = float(r["ly_p2"]) if r.get("ly_p2") is not None else ly / 2
                        g1, g2 = float(r.get("g_p1") or 0.0) / 100, float(r.get("g_p2") or 0.0) / 100
                        hc = (hold_c.get(cl) or {}).get(m)
                        hd = float((hold_d.get(dv) or {}).get(m) or 1.0)
                        if isinstance(hc, dict):
                            h1, h2 = float(hc.get("P1", 1.0)), float(hc.get("P2", 1.0))
                        else:
                            h1 = h2 = float(hc) if hc else hd
                        b1 = float(r.get("bal_p1", r.get("bal", 1.0)) or 1.0)
                        b2 = float(r.get("bal_p2", r.get("bal", 1.0)) or 1.0)
                        pre1, pre2 = l1 * g1, l2 * g2
                        a1, a2 = pre1 * h1, pre2 * h2
                        bal = a1 * b1 + a2 * b2
                        e["bis"], e["cap"], e["bal"], e["newd"] = pre1 + pre2 - ly, a1 + a2 - pre1 - pre2, bal - a1 - a2, ty - bal
                    recs.append({"Store": s, "Group": grp, "Cluster": cl, "Division": dv, "Month": m, "Department": d,
                                 "LY": ly, "Plan": ty, **e})
    return pd.DataFrame(recs)


def holistic(division: str = "", month: str = "", group: str = "") -> dict:
    """The company-level deviation bridge: last year -> each effect -> the plan, with the share of the deviation each
    takes, by division / month / store group / cluster / department - the store journey's effects added up."""
    key = (_plan_stamp(), division, month, group)
    if key in _hol_cache:
        return _hol_cache[key]
    df = _effects(_plan(), division, month, group)
    ks = [k for k, _, _ in BRIDGE]
    ly, ty = float(df["LY"].sum()), float(df["Plan"].sum())
    dev = ty - ly
    bridge = [{"key": k, "what": nm, "why": why, "change": float(df[k].sum()),
               "share": float(df[k].sum()) / dev * 100 if abs(dev) > 1e-12 else None,
               "pct_of_ly": float(df[k].sum()) / ly * 100 if ly else None} for k, nm, why in BRIDGE]
    bridge = [b for b in bridge if abs(b["change"]) > 1e-9]

    def by(col, top=None):
        g = df.groupby(col)[["LY", "Plan"] + ks].sum().reset_index()
        g["Change"] = g["Plan"] - g["LY"]
        g = g.sort_values("Change", key=abs, ascending=False).head(top) if top else g.sort_values(col)
        return [{"key": r[col], "ly": float(r["LY"]), "plan": float(r["Plan"]), "change": float(r["Change"]),
                 "pct": float((r["Plan"] / r["LY"] - 1) * 100) if r["LY"] > 0 else None, **{k: float(r[k]) for k in ks}}
                for _, r in g.iterrows()]
    biggest = max(bridge, key=lambda b: abs(b["change"])) if bridge else None
    scope = " ".join(x for x in ({"SSG": "the like-for-like stores", "NSO": "the new stores", "Others": "the other stores"}.get(group, ""),
                                 division, month) if x) or "the whole company"
    story = (f"Across {scope}, last year sold ₹{ly:,.2f} L and the plan is ₹{ty:,.2f} L ({(ty / ly - 1) * 100 if ly else 0:+.2f}%, "
             f"{'+' if dev >= 0 else '-'}₹{abs(dev):,.2f} L). " +
             " ".join(f"{b['what']}: {'+' if b['change'] >= 0 else '-'}₹{abs(b['change']):,.2f} L"
                      + (f" ({b['share']:.0f}% of the change)." if b["share"] is not None else ".") for b in bridge) +
             (f" The biggest single mover: {biggest['what']}." if biggest else ""))
    out = {"scope": {"division": division, "month": month, "group": group}, "ly": ly, "plan": ty, "change": dev,
           "pct": (ty / ly - 1) * 100 if ly else None, "bridge": bridge, "story": story,
           "names": {k: nm for k, nm, _ in BRIDGE},
           "by": {"Division": by("Division"), "Month": by("Month"), "Group": by("Group"), "Cluster": by("Cluster"),
                  "Department": by("Department", top=25)},
           "check": abs(sum(b["change"] for b in bridge) - dev) < 1e-6}
    _hol_cache.clear()
    _hol_cache[key] = out
    return out


def holistic_xlsx(division: str = "", month: str = "", group: str = "") -> tuple:
    """The company-level bridge as Excel: Bridge (+ the paragraph) and the effects by division / month / group / cluster /
    department / store - each effect's column and the change."""
    h = holistic(division, month, group)
    df = _effects(_plan(), division, month, group)
    ks = [k for k, _, _ in BRIDGE]
    names = {k: nm for k, nm, _ in BRIDGE}
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        pd.DataFrame([[h["story"]]], columns=["What moved the plan - company level"]).to_excel(xw, sheet_name="Bridge", index=False)
        pd.DataFrame([{"Step": "Last year", "Rs lakh": h["ly"], "Share of the change %": None, "% of last year": None,
                       "Why": "Actual sales last year (like-for-like stores); own sales (other stores)."}]
                     + [{"Step": b["what"], "Rs lakh": b["change"], "Share of the change %": b["share"], "% of last year": b["pct_of_ly"],
                         "Why": b["why"]} for b in h["bridge"]]
                     + [{"Step": "= Plan", "Rs lakh": h["plan"], "Share of the change %": 100.0 if h["change"] else None,
                         "% of last year": h["pct"], "Why": ""}]).to_excel(xw, sheet_name="Bridge", index=False, startrow=3)
        for col in ("Division", "Month", "Group", "Cluster", "Department", "Store"):
            g = df.groupby(col)[["LY", "Plan"] + ks].sum().reset_index()
            g["Change"] = g["Plan"] - g["LY"]
            g = g.rename(columns=names).sort_values("Change", key=abs, ascending=False)
            g.to_excel(xw, sheet_name=f"By {col}", index=False)
            xw.sheets[f"By {col}"].set_column(0, 0, 28)
            xw.sheets[f"By {col}"].set_column(1, 12, 16)
        ws = xw.sheets["Bridge"]
        wrap = xw.book.add_format({"text_wrap": True, "valign": "top"})
        ws.set_column(0, 0, 40, wrap); ws.set_column(1, 3, 18); ws.set_column(4, 4, 100, wrap)
    tag = " - ".join(x for x in (group, division, month) if x) or "company"
    return buf.getvalue(), f"Deviation bridge - {tag}.xlsx"


# ── the export: every field, store x department x MRP x month ─────────────────────────────────────────────────────

def export_rows(division: str = "", group: str = "", store: str = "") -> pd.DataFrame:
    p = _plan()
    q = dte._load(dte.DT_QTY_PATH) or dte._load(dte.DT_RESULT_PATH)
    if not q:
        from fastapi import HTTPException
        raise HTTPException(404, "No Display Type run yet")
    from engines.final_results_engine import _load_dept_attr_map
    from engines.mrp_plan_engine import effective_shares
    attrs, shares = _load_dept_attr_map(), effective_shares()[0]
    hold = (p.get("meta") or {}).get("lfl_hold_cluster") or {}
    st = p["stores"]
    df = pd.DataFrame(q["rows"])
    if division:
        df = df[df["division"].isin(division.split(","))]
    if store:
        df = df[df["store"].isin(store.split(","))]
    info = pd.DataFrame([{"store": s, "Store group": _group(x), "Cluster": x.get("cluster", ""), "Store tag": x.get("tag", ""),
                          "Reference store (split follows)": x.get("ref_used", "")} for s, x in st.items()])
    if group:
        info = info[info["Store group"].isin(group.split(","))]
    df = df.merge(info, on="store", how="inner")
    recs = []
    for s in df["store"].unique():
        for dv, dd in st[s]["divisions"].items():
            for m, md in dd["months"].items():
                act = _active(md)
                dtot = sum(v["ty"] for v in act.values())
                for d, v in act.items():
                    recs.append((s, dv, m, d, v.get("ly", 0.0), v.get("ty", 0.0), dtot, v.get("g_p1"), v.get("g_p2"),
                                 v["ty"] / dtot * 100 if dtot else 0.0, v.get("bal_p1"), v.get("bal_p2")))
    dp = pd.DataFrame(recs, columns=["store", "division", "month", "dept", "Dept LY (₹L)", "Dept TY (₹L)", "Store-division TY (₹L)",
                                     "BIS growth P1 (index)", "BIS growth P2 (index)", "Dept share of store-division %",
                                     "Store balance P1 (SSG)", "Store balance P2 (SSG)"])
    df = df.merge(dp, on=["store", "division", "month", "dept"], how="left")
    df["Dept growth %"] = ((df["Dept TY (₹L)"] / df["Dept LY (₹L)"] - 1) * 100).where(df["Dept LY (₹L)"] > 0)
    for h in ("P1", "P2"):
        df[f"AOP cap {h} (SSG cluster x month)"] = [((hold.get(cl) or {}).get(m) or {}).get(h) if g == "SSG" else None
                                                   for cl, m, g in zip(df["Cluster"], df["month"], df["Store group"])]
    for h in ("P1", "P2"):
        df[f"MRP share {h} %"] = [(((shares.get(dv) or {}).get(d) or {}).get(str(mr)) or {}).get(f"{m} {h}")
                                  for dv, d, mr, m in zip(df["division"], df["dept"], df["mrp"], df["month"])]
    df["Attribute"] = [(attrs.get(dv) or {}).get(d, "") for dv, d in zip(df["division"], df["dept"])]
    df["Display mix from"] = df["contrib_from"].map(lambda x: dte.MIX_NOTE.get(x, x))
    # a non-SSG store isn't on BIS growth (its plan is the AOP store plan) and its display mix is its reference store's
    nss = df["Store group"] != "SSG"
    df.loc[nss, ["BIS growth P1 (index)", "BIS growth P2 (index)"]] = None
    df.loc[nss, "Display mix from"] = "reference store " + df.loc[nss, "Reference store (split follows)"].astype(str) + ": " +         df.loc[nss, "Display mix from"].astype(str).str.replace("the store's", "its", regex=False)
    df = df.rename(columns={"store": "Store", "division": "Division", "dept": "Department", "mrp": "MRP", "month": "Month",
                            "ty_p1": "Dept TY P1 (₹L)", "ty_p2": "Dept TY P2 (₹L)", "mrp_plan": "MRP TY (₹L)",
                            "table_contrib": "Table %", "nontable_contrib": "Non-Table %", "table_plan": "Table TY (₹L)",
                            "nontable_plan": "Non-Table TY (₹L)", "table_asp": "Table ASP (₹)", "table_qty": "Table Qty",
                            "nontable_asp": "Non-Table ASP (₹)", "nontable_qty": "Non-Table Qty"})
    cols = ["Store", "Store group", "Cluster", "Store tag", "Reference store (split follows)", "Division", "Attribute", "Department",
            "Month", "Dept LY (₹L)", "BIS growth P1 (index)", "BIS growth P2 (index)", "AOP cap P1 (SSG cluster x month)", "AOP cap P2 (SSG cluster x month)", "Store balance P1 (SSG)", "Store balance P2 (SSG)", "Store-division TY (₹L)",
            "Dept share of store-division %", "Dept TY P1 (₹L)", "Dept TY P2 (₹L)", "Dept TY (₹L)", "Dept growth %", "MRP",
            "MRP share P1 %", "MRP share P2 %", "MRP TY (₹L)", "Table %", "Non-Table %", "Display mix from", "Table TY (₹L)",
            "Non-Table TY (₹L)", "Table ASP (₹)", "Non-Table ASP (₹)", "Table Qty", "Non-Table Qty"]
    df["_m"] = pd.to_numeric(df["MRP"], errors="coerce")
    return df.sort_values(["Division", "Store", "Department", "_m", "Month"])[[c for c in cols if c in df.columns]]


def export_bytes(fmt: str = "csv", **filters) -> tuple:
    """(file bytes, extension, rows). CSV by default (the full run is ~700k rows); Excel up to an Excel sheet's limit."""
    df = export_rows(**filters)
    if fmt == "xlsx":
        if len(df) > 1_000_000:
            from fastapi import HTTPException
            raise HTTPException(413, f"{len(df):,} rows - more than an Excel sheet holds: filter by division, store group or store, or take CSV")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:   # (constant_memory drops cells: pandas doesn't write row by row)
            df.to_excel(xw, index=False, sheet_name="Plan to UDF")
        return buf.getvalue(), "xlsx", len(df)
    return df.to_csv(index=False).encode("utf-8-sig"), "csv", len(df)


if __name__ == "__main__":   # self-check: one store of each group lands on its saved numbers, MRP and display included
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    o = options()
    for g in ("SSG", "NSO", "Others"):
        s = next(x["store"] for x in o["stores"] if x["group"] == g)
        dd = options(s)["depts"]
        d = max(dd, key=lambda x: x["ty"])["dept"]
        j = journey(s, d, o["months"][0])
        top = j["mrps"][0]["mrp"]
        j = journey(s, d, o["months"][0], top)
        print(g, s, d, top, "dept ok:", j["ok"], "| steps:", len(j["steps"]), "| last:", j["steps"][-1]["title"], j["steps"][-1]["value"])
        assert j["ok"]
    print("ok")
