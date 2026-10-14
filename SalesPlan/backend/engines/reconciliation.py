"""Sales Plan reconciliation (user, 2026-09-30: "embed the matrix to give me the least apportioned difference all time
in all models across apps wherever apportioning is present").

Re-checks, from the plan the pages use (the latest of base-corrected / attribute-corrected / department plan), that
every apportioned total adds back to its parts - to 8 decimals:
  Store x Division x Month   division total = sum of its departments; P1 / P2 likewise; contribution % add to 100
  Store x Dept x Month       TY = P1 + P2
  Division x Dept x Period   department TY = sum of its MRP bands (the MRP plan), for the periods the MRP file covers
What no maths can fill - departments / months the MRP file has no shares for - is listed apart as "not covered"."""
import datetime
import io
import os
import sys

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import SHOWN  # noqa: E402

from plan_cache import load_json as _load_plan_json  # noqa: E402

router = APIRouter()


def _active_plan():
    from engines.final_results_engine import _pipeline_status
    st = _pipeline_status()
    f = st.get("active_file")
    if not f or not os.path.exists(f):
        return None, None, None
    plan = _load_plan_json(f)
    return plan, st["active_source"], datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d %b %Y %H:%M")


ART_LEVEL = "{G} × Dept × Month: department AOP = Σ Article Names"


AOP_LEVEL = "Division × Month: like-for-like department plan = AOP"


def check(plan: dict, mrp_data: dict | None = None, art: dict | None = None, aop: dict | None = None):
    """(summary rows, off rows, not-covered rows). A row is "off" when its difference shows at 8 decimals.
    art = the Article Name branch's build (art_nm_engine.built) - checked when the MRP stage runs on the Article Name
    route (user, 2026-10-13: "think of it as another parallel branch to MRP"); with it promoted, its MRP bands too.
    aop = {DIVISION: {month: lakh}} of the AOP publish: every division x month's like-for-like plan must equal it (user,
    2026-10-13: "... AOP is correct for all months")."""
    stage = ART_LEVEL.format(G="Cluster" if art.get("grain") == "cluster" else "Store") if art is not None else None
    levels = {k: {"cells": 0, "off": 0, "largest": 0.0, "where": ""} for k in (
        *([AOP_LEVEL] if aop else []),
        "Store × Division × Month: division total = Σ departments",
        "Store × Division × Month: P1 / P2 totals = Σ departments",
        "Store × Dept × Month: TY = P1 + P2",
        "Store × Division × Month: Σ contribution % = 100",
        *([stage] if stage else []), *(["Division × Dept × Period: department TY = Σ MRP bands"] if mrp_data or not stage else []))}
    off, uncovered = [], []

    def rec(level, total, parts, **where):
        lv = levels[level]
        d = parts - total
        lv["cells"] += 1
        if abs(d) > lv["largest"]:
            lv["largest"], lv["where"] = abs(d), " / ".join(str(v) for v in where.values())
        if abs(d) > SHOWN:
            lv["off"] += 1
            off.append({"Level": level, **where, "Total": total, "Sum of parts": parts, "Difference": d})

    for store, sd in plan.get("stores", {}).items():
        for div, dd in sd.get("divisions", {}).items():
            for m, md in dd.get("months", {}).items():
                act = {n: v for n, v in md.get("departments", {}).items() if v.get("active")}
                w = {"Store": store, "Division": div, "Department": "", "Month": m}
                rec("Store × Division × Month: division total = Σ departments",
                    md.get("div_total_ty", 0.0), sum(v.get("ty", 0.0) for v in act.values()), **w)
                for half in ("p1", "p2"):
                    if f"div_total_{half}" in md:
                        rec("Store × Division × Month: P1 / P2 totals = Σ departments", md[f"div_total_{half}"],
                            sum(v.get(f"ty_{half}", 0.0) for v in act.values()), **{**w, "Month": f"{m} {half.upper()}"})
                if sum(v.get("ty", 0.0) for v in act.values()) > 0:
                    rec("Store × Division × Month: Σ contribution % = 100", 100.0,
                        sum(v.get("cont_pct", 0.0) for v in act.values()), **w)
                for n, v in act.items():
                    if "ty_p1" in v:
                        rec("Store × Dept × Month: TY = P1 + P2", v.get("ty", 0.0),
                            v.get("ty_p1", 0.0) + v.get("ty_p2", 0.0), **{**w, "Department": n})

    if aop:
        lfl = {}
        for sd in plan.get("stores", {}).values():
            if not sd.get("is_ssg"):
                continue
            for div, dd in sd.get("divisions", {}).items():
                for m, md in dd.get("months", {}).items():
                    lfl[(div, m)] = lfl.get((div, m), 0.0) + sum(
                        v.get("ty", 0.0) for v in md.get("departments", {}).values() if v.get("active"))
        for div, mm in aop.items():
            for m, target in mm.items():
                rec(AOP_LEVEL, target, lfl.get((div, m), 0.0), Store="(like-for-like)", Division=div, Department="", Month=m)

    if art is not None:
        miss = {}
        for r in art["rows"]:
            for m in art["months"]:
                t = r["aop"].get(m, 0.0)
                if t < 0:   # a negative department plan: its articles stay 0 (no negative plan)
                    k = (r["div"], r["dept"], "negative department plan - articles kept at 0")
                    miss[k] = miss.get(k, 0.0) + t
                    continue
                rec(stage, t, sum(v.get(m, 0.0) for v in r["arts"].values()),
                    Store=r["g"], Division=r["div"], Department=r["dept"], Month=m)
        uncovered = [{"Division": d, "Department": n, "Why": why, "TY not split to MRPs (₹ L)": ty}
                     for (d, n, why), ty in sorted(miss.items())]
    if mrp_data:
        periods = mrp_data.get("periods", [])
        covered = {(div, dept) for div, depts in mrp_data.get("data", {}).items() for dept, v in depts.items()
                   if not v.get("no_split")}   # listed without a split: "not covered" below, not a rounding gap
        for div, depts in mrp_data.get("data", {}).items():
            for dept, v in depts.items():
                if v.get("no_split"):
                    continue
                rec("Division × Dept × Period: department TY = Σ MRP bands", v["allocated_ty"] - v["difference"],
                    v["allocated_ty"], Store="(all)", Division=div, Department=dept, Month=f"{periods[0]} – {periods[-1]}" if periods else "")
        # plan TY the MRP file has no shares for: a department not in it, or a month it doesn't cover
        cov_months = {p.rsplit(" ", 1)[0] for p in periods}
        miss: dict = {}
        for sd in plan.get("stores", {}).values():
            for div, dd in sd.get("divisions", {}).items():
                for m, md in dd.get("months", {}).items():
                    for n, v in md.get("departments", {}).items():
                        if not v.get("active") or not v.get("ty"):
                            continue
                        why = ("department has no MRP shares" if (div, n) not in covered else
                               "month not in the MRP file" if m not in cov_months else None)
                        if why:
                            k = (div, n, why)
                            miss[k] = miss.get(k, 0.0) + v["ty"]
        uncovered += [{"Division": d, "Department": n, "Why": why, "TY not split to MRPs (₹ L)": ty}
                      for (d, n, why), ty in sorted(miss.items())]

    summary = [{"level": k, **v} for k, v in levels.items()]
    return summary, off, uncovered


def _run():
    plan, source, at = _active_plan()
    if plan is None:
        return None
    from engines.mrp_plan_engine import get_mrp_data
    from engines import art_nm_engine
    st = art_nm_engine.get_settings()
    art = mrp = None
    if st["route"] == "article":   # the MRP stage runs on the Article Name branch: check that split
        try:
            art = art_nm_engine.built(st["grain"])
        except Exception:  # noqa: BLE001 - no plan / lake: skip that level
            art = None
    if st["route"] != "article" or art_nm_engine.promoted():   # the MRP bands: the buyers' or the promoted split
        try:
            mrp = get_mrp_data()
        except Exception:  # noqa: BLE001 - no MRP plan yet: skip that level
            mrp = None
    from engines.dept_sales_engine import _aop_lfl_targets
    from engines.art_nm_engine import _plan_months
    pm = set(_plan_months(plan))   # the months Sales Plan plans (BIS's input months)
    aop = {dv: {m: v for m, v in mm.items() if m in pm} for dv, mm in (_aop_lfl_targets() or {}).items()}
    summary, off, uncovered = check(plan, mrp if mrp and mrp.get("has_plan") else None, art, aop)
    return {"source": source, "generated_at": at, "summary": summary, "off": off, "uncovered": uncovered,
            "route": st["route"]}


@router.get("")
def get_reconciliation():
    r = _run()
    if r is None:
        return {"source": None, "summary": [], "off_count": 0, "off": [], "uncovered": []}
    return {**{k: r[k] for k in ("source", "generated_at", "summary", "uncovered", "route")},
            "off_count": len(r["off"]), "off": r["off"][:500],
            "uncovered_total": sum(u["TY not split to MRPs (₹ L)"] for u in r["uncovered"])}


@router.get("/export")
def export_reconciliation():
    r = _run() or {"summary": [], "off": [], "uncovered": [], "source": None, "generated_at": None}
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        fmt = xw.book.add_format({"num_format": "0.00000000"})
        sheets = [("Summary", pd.DataFrame([{"Check": s["level"], "Cells checked": s["cells"], "Off at 8 dp": s["off"],
                                             "Largest difference": s["largest"], "Where": s["where"]} for s in r["summary"]])),
                  ("Off at 8 decimals", pd.DataFrame(r["off"] or [{"Level": "none - every check adds back exactly"}])),
                  ("Not covered by MRP", pd.DataFrame(r["uncovered"] or [{"Division": "none"}]))]
        for name, df in sheets:
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for j, c in enumerate(df.columns):
                ws.set_column(j, j, 18, fmt if pd.api.types.is_float_dtype(df[c]) else None)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=sales_plan_reconciliation.xlsx"})
