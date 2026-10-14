"""
Article Name route of the MRP stage (user, 2026-10-13: "Add a provision toggle if the user wants to go Article Name or
MRP route. Follow the MRP route as is"). The department plan is split over Article Names instead of MRP bands:

  (user, 2026-10-13, the steps as set out: "Department selection ... the ly sales data on cluster/store x dep x art name
  should be pitted against the input file cont % and deviation should be taken out ... below 50% cap it to 50% and max
  to 150% ... for every month the base ly sales cont % should be multiplied with the deviation ... Resultant should be
  apportioned to 100% ... and finally multiplied with the AOP resultant of the department engine")
  1. LY sales per Cluster (or Store - the header's Plan by) x Department x Article Name x month, from the sales engine
     (data lake, LY = the plan month a year back). Negative LY counts as 0 (no negative base).
  2. LY cont % = the article's share of its department, per Cluster/Store x month.
  3. Deviation = the buyers' Art Nm Cont % (imported, one % per Department x Article Name for the block, e.g. MAMJ) /
     that month's LY cont %, capped to 50%..150%. An IN-ACTIVE MC (MC TAG, or the article's MC STATUS) counts as 0%.
  4. Resultant = LY cont % x capped deviation, per Cluster/Store x Department x Article x month.
  5. Within each Cluster/Store x Department x month the resultant is apportioned to 100% and multiplied by the
     department's plan (its AOP in the department engine) - the articles add back to the department exactly, and a
     check says where they don't.
  New and split departments (the file's MC TAG "NEW ACTIVE MC" / "NEW SPLIT MC") take the buyers' Art Nm Cont % as it
  is, no deviation (user, 2026-10-13: "for new departments and split departments use the imported buyer's cont % at
  art nm"). The file names a split department by its OLD name (KB_BERMUDA ...); its parts' articles carry new codes
  ("01-EPP [KB46]" for "01-EPP [KB07]"), so a part takes the old department's % by article tier (EPP, ECO, ...).
  Fallbacks (each shown as the department's method): no buyer % -> LY mix; a store with no LY of its own -> its
  cluster's mix; no LY here -> buyer mix, else the chain's LY mix; none of those -> not allocated (the check goes red).
  A negative department plan (from negative LY in the plan) gives its articles 0 - no negative plan.
"""
import collections
import datetime
import io
import os
import re
import sys
import threading

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import SHOWN, split  # noqa: E402
from plan_cache import save_json  # noqa: E402
from engines.engine_switch import plan_files  # noqa: E402

router = APIRouter()

_HERE = os.path.dirname(os.path.abspath(__file__))
CONT_PATH = os.path.join(_HERE, "..", "art_nm_cont.json")       # the imported buyers' file, parsed
ROUTE_PATH = os.path.join(_HERE, "..", "mrp_route.json")        # {"route": "mrp" | "article", "grain": ...}
# the imported file exactly as uploaded - what Export gives back (gitignored with the other backend data files)
SOURCE_COPY = os.path.join(_HERE, "..", "art_nm_cont_source.xlsx")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CAP_LO, CAP_HI = 0.5, 1.5
# the data-lake department split (BIS DEPT_SPLITS, otb-plan-app.html): the buyers' file uses the old names
DEPT_SPLITS = {
    "MSE_PYJAMA": ["MSE_HSR PYJAMA", "MSE_TXTL PYJAMA"], "KB_T-SHIRT H/S": ["KB_R/N T-SHIRT H/S", "KB_POLO T-SHIRT H/S"],
    "KB_BERMUDA": ["KB_HSR BERMUDA", "KB_TXTL BERMUDA"], "LW_L_PALAZZO": ["LW_L_WES PALAZZO", "LW_L_ETH PALAZZO"],
    "LW_L_JEGGING": ["LW_L_DNM JOGGER", "LW_L_WVN JOGGER"], "L_IN_BRA": ["L_IN_BRA", "L_IN_SPRT BRA"],
}
DIRECT_TAGS = {"NEW ACTIVE MC": "new", "NEW SPLIT MC": "split"}
METHOD = {
    "deviation":  "LY mix x buyer deviation (capped 50-150%)",
    "inactive":   "In-active MC: input 0% (deviation at the 50% floor - LY mix)",
    "buyer":      "Buyer's Art Nm Cont %",
    "ly":         "LY mix (no buyer Art Nm Cont %)",
    "buyer_noly": "Buyer's Art Nm Cont % (no LY here)",
    "cluster":    "Cluster's mix (store has no LY)",
    "chain":      "Chain mix (no LY here, no buyer %)",
    "none":       "Not allocated",
}


def _read(path):
    import json
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def tier(article: str) -> str:
    """'02-ECO [LE01]' -> 'ECO', '07-SUPER-PREMIUM [LW33]' -> 'SUPER-PREMIUM' (the code and number differ by part)."""
    s = re.sub(r"\[.*?\]", "", str(article))
    return re.sub(r"^\s*\d+\s*[-.]\s*", "", s).strip().upper()


# ── the buyers' file ──────────────────────────────────────────────────────────

def parse_cont(df: pd.DataFrame) -> dict:
    """The buyers' sheet (DIVISION | DEPARTMENT | NEW ARTICLE_NAME | BUYERS INPUT AT MAMJ | MC TAG ...) ->
    {block, depts: {DEPT: {division, tag, arts: {ARTICLE: pct}}}, warnings}. Fractions (0.61) are read as %."""
    cols = {re.sub(r"\s+", " ", str(c)).strip().upper(): c for c in df.columns}
    pick = lambda *names: next((cols[n] for n in names if n in cols), None)   # noqa: E731
    c_dept, c_div = pick("DEPARTMENT", "DEPT"), pick("DIVISION", "DIV")
    c_art = pick("NEW ARTICLE_NAME", "ARTICLE_NAME", "ARTICLE NAME", "ART_NM", "ART NM")
    c_tag = pick("MC TAG", "DEPT TAG", "TAG")
    c_st = pick("MC STATUS", "STATUS")
    c_val = next((cols[k] for k in cols if k.startswith("BUYERS INPUT") or k.startswith("BUYER INPUT")
                  or "CONT %" in k or k.endswith("CONT%")), None)
    miss = [n for n, c in (("DEPARTMENT", c_dept), ("ARTICLE NAME", c_art), ("BUYERS INPUT AT <block>", c_val)) if c is None]
    if miss:
        raise ValueError(f"Columns not found: {', '.join(miss)}. Found: {', '.join(map(str, df.columns))}")
    m = re.search(r"\bAT\s+([A-Z]+)", re.sub(r"\s+", " ", str(c_val)).upper())
    v = pd.to_numeric(df[c_val], errors="coerce")
    if (v < 0).any():
        raise ValueError(f"{int((v < 0).sum())} negative Art Nm Cont % values")
    scale = 100.0 if v.max() <= 1.0001 else 1.0
    depts, warn = {}, []
    for i, r in df.iterrows():
        dept, art = str(r[c_dept]).strip().upper(), str(r[c_art]).strip()
        if not dept or dept == "NAN" or not art or art.upper() == "NAN":
            continue
        d = depts.setdefault(dept, {"division": str(r[c_div]).strip().upper() if c_div else "",
                                    "tag": str(r[c_tag]).strip().upper() if c_tag else "", "arts": {}})
        if art in d["arts"]:
            raise ValueError(f"{dept} / {art} is listed twice")
        pct = float(v[i]) * scale if pd.notna(v[i]) else 0.0
        # an IN-ACTIVE MC counts as 0% (user, 2026-10-13: "if the input file has an inactive mc then it should be
        # considered 0%") - the department's MC TAG, or the article's MC STATUS; what the file said is kept as "given"
        off = "IN-ACTIVE" in d["tag"] or (c_st is not None and "IN-ACTIVE" in str(r[c_st]).upper())
        if off and pct:
            d.setdefault("given", {})[art] = pct
        d["arts"][art] = 0.0 if off else pct
    for dept, d in depts.items():
        t = sum(d["arts"].values())
        if t > 0 and abs(t - 100) > 0.5:
            warn.append(f"{dept}: Art Nm Cont % adds to {t:.1f}%" + (" (in-active articles at 0%)" if d.get("given") else ""))
    return {"block": m.group(1) if m else "", "depts": depts, "warnings": warn}


def buyer_mix(cont: dict, plan_depts: set, lake_arts: dict) -> dict:
    """{plan dept: (tag, {article: pct})} - a split part on its old department's % by article tier, over the part's
    own articles (lake_arts = {dept: set of its LY article names})."""
    out = {}
    for dept, d in (cont or {}).get("depts", {}).items():
        tag = DIRECT_TAGS.get(d["tag"], "inactive" if "IN-ACTIVE" in d["tag"] else "existing")
        if tag == "split":
            by_tier = collections.defaultdict(float)
            for a, p in d["arts"].items():
                by_tier[tier(a)] += p
            for part in DEPT_SPLITS.get(dept, [dept]):
                arts = sorted(lake_arts.get(part) or [])
                n = collections.Counter(tier(a) for a in arts)
                out[part] = ("split", {a: by_tier.get(tier(a), 0.0) / n[tier(a)] for a in arts} if arts else dict(d["arts"]))
        elif dept not in out:
            out[dept] = (tag, dict(d["arts"]))
    return {k: v for k, v in out.items() if k in plan_depts}


# ── LY article sales ───────────────────────────────────────────────────────────

_LY: dict = {}
_LY_LOCK = threading.Lock()


def _ly_month(ty: str) -> str:
    """"Mar'27" -> "2026-03" (same month, a year back)."""
    d = datetime.datetime.strptime(ty, "%b'%y")
    return f"{d.year - 1}-{d.month:02d}"


def ly_sales(months: list) -> tuple:
    """({(store, dept): {article: {ty month: Rs lakh}}}, tie check) from the sales engine file. Cached per file."""
    from engines.mrp_reapportionment_engine import _calendar_scans, _engine_check
    scans = _calendar_scans()
    files = scans._latest_monthwise_files()
    if not files:
        raise ValueError(f"Sales engine file not reachable: {scans.PARQUET_DIR}")
    key = (files[0], os.path.getmtime(files[0]), tuple(months))
    with _LY_LOCK:
        if _LY.get("key") != key:
            lym = {_ly_month(m): m for m in months}
            lo, hi = scans._month_bounds(sorted(lym))
            raw = scans._read_file_filtered(files[0], ["BILLMONTH", "STORE_NAME", "SL_V", "DEPARTMENT", "ARTICLE_NAME"],
                                            "BILLMONTH", lo, hi)
            raw["ym"] = raw["BILLMONTH"].dt.strftime("%Y-%m")
            raw = raw[raw["ym"].isin(lym)]
            for c in ("STORE_NAME", "DEPARTMENT"):
                raw[c] = raw[c].fillna("(BLANK)").astype(str).str.strip().str.upper()
            raw["ARTICLE_NAME"] = raw["ARTICLE_NAME"].fillna("(BLANK)").astype(str).str.strip()
            raw["SL_V"] = pd.to_numeric(raw["SL_V"], errors="coerce").fillna(0.0)
            g = raw.groupby(["STORE_NAME", "DEPARTMENT", "ARTICLE_NAME", "ym"])["SL_V"].sum()
            ly = {}
            for (s, d, a, ym), v in g.items():
                ly.setdefault((s, d), {}).setdefault(a, {})[lym[ym]] = v / 1e5
            check = _engine_check(raw.rename(columns={"STORE_NAME": "STORE"})[["STORE", "DEPARTMENT", "ym", "SL_V"]])
            _LY.update(key=key, ly=ly, check=check)
        return _LY["ly"], _LY["check"]


# ── the plan ───────────────────────────────────────────────────────────────────

def _plan_months(plan: dict) -> list:
    from actuals_manager import plan_ty_months
    have = {m for sd in plan.get("stores", {}).values() for dd in (sd.get("divisions") or {}).values()
            for m in ((dd or {}).get("months") or {})}
    try:
        want = plan_ty_months()
    except Exception:   # noqa: BLE001 - BIS / AOP unreachable: the plan's own months
        want = None
    return sorted((m for m in have if not want or m in want), key=lambda m: datetime.datetime.strptime(m, "%b'%y"))


def shares_for(tag, bmix, lyg, months, new_arts=None):
    """One Cluster/Store x Department: ({month: {article: resultant}} or None, method, working). lyg = {article:
    {month: lakh}} of this group (already summed for a cluster). working = {article: {month: (LY base, LY cont %,
    buyer %, deviation, capped, resultant)}} - month by month: LY cont % = the article's share of the department's LY;
    deviation = buyer % / LY cont %, capped 50-150%; resultant = LY cont % x capped. A month with no LY of its own uses
    the block's LY cont %. Articles with no LY here get no resultant."""
    base = {a: {m: max(float(v.get(m, 0.0)), 0.0) for m in months} for a, v in (lyg or {}).items()}
    blk = {a: sum(v.values()) for a, v in base.items()}
    tot = sum(blk.values())
    bsum = sum(bmix.values()) if bmix else 0.0
    if tag in ("new", "split") and bsum > 0:
        return {m: dict(bmix) for m in months}, "buyer", {}
    if tot <= 0:
        return ({m: dict(bmix) for m in months}, "buyer_noly", {}) if bsum > 0 else (None, "none", {})
    how = "deviation" if bsum > 0 else "inactive" if tag == "inactive" else "ly"
    w, info = {}, {}
    for m in months:
        mb = {a: base[a][m] for a in base}
        t = sum(mb.values())
        if t <= 0:
            mb, t = blk, tot
        w[m] = {}
        for a in base:
            lyp = mb[a] / t * 100.0
            b = float(bmix.get(a, 0.0))
            dev = b / lyp if lyp > 0 else None
            cap = min(max(dev, CAP_LO), CAP_HI) if dev is not None else None
            res = lyp * cap if cap is not None else 0.0
            w[m][a] = res
            info.setdefault(a, {})[m] = (base[a][m], lyp, b, dev, cap, res)
    # a NEW article name (in the file, never sold in the chain) takes the imported % as it is (user, 2026-10-13: "new
    # departments introduced, new article name introduced, and split department introduced should be taken as per the
    # cont % imported"); the other articles share the rest by their resultants
    new = {a: p for a, p in (new_arts or {}).items() if p > 0 and a not in base}
    if new:
        keep = max(100.0 - sum(new.values()), 0.0)
        for m in months:
            t = sum(w[m].values())
            w[m] = {**({a: v / t * keep for a, v in w[m].items()} if t > 0 else {}), **new}
            for a, p in new.items():
                info.setdefault(a, {})[m] = (0.0, None, p, None, None, None)
    return w, how, info


def build(grain: str, plan: dict, cont: dict | None, ly: dict, check: dict, months: list) -> dict:
    """Every Cluster/Store x Division x Department x Article x month of the plan - see the module docstring."""
    clus = {s: (sd.get("cluster") or "(no cluster)") for s, sd in plan["stores"].items()}
    aop = collections.defaultdict(lambda: collections.defaultdict(float))   # (store, div, dept) -> {m: lakh}
    for s, sd in plan["stores"].items():
        for dv, dd in (sd.get("divisions") or {}).items():
            for m, md in ((dd or {}).get("months") or {}).items():
                if m not in months or not isinstance(md, dict):
                    continue
                for dp, x in (md.get("departments") or {}).items():
                    if isinstance(x, dict) and x.get("active", True) and float(x.get("ty") or 0.0):
                        aop[(s, dv, dp)][m] += float(x["ty"])
    plan_depts = {k[2] for k in aop}
    lake_arts = collections.defaultdict(set)
    for (s, d), arts in ly.items():
        lake_arts[d].update(arts)
    bm = buyer_mix(cont, plan_depts, lake_arts)

    def summed(keys):
        out = collections.defaultdict(dict)
        for k in keys:
            for a, mv in (ly.get(k) or {}).items():
                for m, v in mv.items():
                    out[a][m] = out[a].get(m, 0.0) + v
        return out

    members = collections.defaultdict(list)
    for s in plan["stores"]:
        members[clus[s]].append(s)
    groups = collections.defaultdict(lambda: collections.defaultdict(float))   # (group, div, dept) -> aop {m}
    for (s, dv, dp), mv in aop.items():
        for m, v in mv.items():
            groups[(clus[s] if grain == "cluster" else s, dv, dp)][m] += v
    rows, cl_cache, ch_cache = [], {}, {}
    for (g, dv, dp), mv in groups.items():
        tag, bmix = bm.get(dp, ("none", {}))
        new_arts = {a: p for a, p in bmix.items() if p > 0 and a not in lake_arts.get(dp, ())}   # never sold: new
        lyg = summed([(s, dp) for s in members[g]]) if grain == "cluster" else ly.get((g, dp))
        w, how, info = shares_for(tag, bmix, lyg, months, new_arts)
        if grain == "store" and how in ("none", "buyer_noly"):   # a store with no LY: its cluster's mix first
            c = clus[g]
            if (c, dp) not in cl_cache:
                cl_cache[(c, dp)] = shares_for(tag, bmix, summed([(s, dp) for s in members[c]]), months, new_arts)
            cw, chow, cinfo = cl_cache[(c, dp)]
            if cw is not None and chow not in ("none", "buyer_noly"):
                w, how, info = cw, "cluster", cinfo
        if how == "none":   # no LY here and no buyer %: the chain's LY mix of the department
            if dp not in ch_cache:
                ch_cache[dp] = shares_for(tag, bmix, summed([(s, dp) for s in plan["stores"]]), months, new_arts)
            if ch_cache[dp][0] is not None:
                w, how, info = ch_cache[dp][0], "chain", ch_cache[dp][2]
        arts = {}
        for m in months:
            for a, v in (split(max(mv.get(m, 0.0), 0.0), w[m]) if w else {}).items():
                arts.setdefault(a, {})[m] = v
        lyb = {a: sum(max(float(x), 0.0) for x in mvs.values()) for a, mvs in (lyg or {}).items()}
        rows.append({"g": g, "cluster": clus[g] if grain == "store" else g, "div": dv, "dept": dp, "tag": tag,
                     "method": how, "aop": dict(mv), "arts": arts, "ly": lyb, "info": info, "buyer": bmix,
                     "lym": {a: {m: float(x.get(m, 0.0)) for m in months} for a, x in (lyg or {}).items()},
                     "new_arts": sorted(new_arts),
                     "stype": ("SSG" if plan["stores"][g].get("is_ssg") else "NSO") if grain == "store" else ""})
    return {"grain": grain, "months": months, "rows": rows, "check": check, "cont": cont,
            "bm_depts": len(bm), "plan_depts": len(plan_depts)}


_BUILT: dict = {}
_BUILD_LOCK = threading.Lock()


def built(grain: str) -> dict:
    """build() for the live plan, cached on the plan, the imported file and the sales engine file."""
    from engines.mrp_plan_engine import _load_dept_plan   # the plan Plan Output splits
    if grain not in ("cluster", "store"):
        raise HTTPException(400, "grain must be 'cluster' or 'store'")
    plan = _load_dept_plan()
    if not plan.get("stores"):
        raise HTTPException(404, "No department plan yet - generate the plan first.")
    months = _plan_months(plan)
    ly, check = ly_sales(months)
    stamps = tuple(os.path.getmtime(p) if os.path.exists(p) else 0 for p in (CONT_PATH, *(
        os.path.join(_HERE, "..", f) for f in plan_files())))   # a switched-off correction drops out (2026-10-14)
    key = (grain, stamps, _LY["key"])
    with _BUILD_LOCK:
        if _BUILT.get(grain, {}).get("key") != key:
            _BUILT[grain] = {"key": key, "v": build(grain, plan, _read(CONT_PATH), ly, check, months)}
        return _BUILT[grain]["v"]


def checks(b: dict) -> list:
    """The route's checks: buyers' file, LY tie, caps and no negatives, articles = department AOP, the AOP's trace."""
    def c(key, label, ok, detail, fix=""):
        st = ok if isinstance(ok, str) else ("ok" if ok else "fail")
        return {"key": key, "label": label, "status": st, "detail": detail, "fix": "" if st == "ok" else fix}
    cont, rows, months = b["cont"], b["rows"], b["months"]
    out = []
    if cont:
        want = "".join(m[0] for m in months)
        blk = cont.get("block") or ""
        out.append(c("file", "Buyer's Art Nm Cont % imported", "ok" if not blk or blk == want else "warn",
                     f"{cont.get('source_file')} ({cont.get('imported_at')}): {len(cont['depts'])} departments, block "
                     f"{blk or '?'}; {b['bm_depts']} of the plan's {b['plan_depts']} departments covered",
                     f"The file is for {blk}, the plan for {want} - import the {want} file."))
        bad = cont.get("warnings") or []
        out.append(c("hundred", "Buyer's Art Nm Cont % adds to 100% per department", "ok" if not bad else "warn",
                     "every department" if not bad else f"{len(bad)} departments: " + "; ".join(bad[:4]),
                     "Correct those departments in the file and import it again."))
    else:
        out.append(c("file", "Buyer's Art Nm Cont % imported", "warn", "not imported - every department on its LY mix",
                     "Import the buyers' Art Nm Cont % file."))
    ch = b["check"]
    out.append(c("tie", "LY article sales tie to the Calendar department sales", bool(ch.get("pass")),
                 f"{ch.get('cells', 0):,} store x dept x month cells, max diff {ch.get('max_diff_lakh')} L",
                 "Wait for the nightly sales sync (or Sync now on Landing), then reopen."))
    caps = [x[4] for r in rows for am in r["info"].values() for x in am.values() if x[4] is not None]
    neg = sum(1 for r in rows for mv in r["arts"].values() for v in mv.values() if v < -SHOWN)
    out.append(c("caps", "Deviation capped 50-150%, no negative base or plan",
                 all(CAP_LO - 1e-12 <= x <= CAP_HI + 1e-12 for x in caps) and neg == 0,
                 f"{len(caps):,} article deviations within {CAP_LO:.0%}-{CAP_HI:.0%}" + (f", {neg} negative plans" if neg else ""),
                 "An engine fault - report it."))
    off, amt, depts, negs, neg_amt = 0, 0.0, set(), 0, 0.0
    for r in rows:
        for m in months:
            t = r["aop"].get(m, 0.0)
            d = sum(mv.get(m, 0.0) for mv in r["arts"].values()) - t
            if t < 0:   # a negative department plan: its articles stay 0 (no negative plan)
                negs, neg_amt = negs + 1, neg_amt + t
            elif abs(d) > SHOWN:
                off, amt = off + 1, amt + d
                depts.add(r["dept"])
    n = len(rows) * len(months)
    out.append(c("aop", "Article plan = department AOP (every group x department x month)",
                 "fail" if off else "warn" if negs else "ok",
                 f"{n - off - negs:,} of {n:,} match" + (f"; {off:,} don't ({-amt:,.2f} L not allocated) in "
                                                         f"{len(depts)} departments: {', '.join(sorted(depts)[:8])}" if off else "")
                 + (f"; {negs} negative department plans ({neg_amt:,.4f} L, from negative LY) kept at 0" if negs else ""),
                 "Not allocated = no LY in the chain and no buyer Art Nm Cont % - add those departments to the file and "
                 "import it again." if off else "The department plan is negative there (returns in LY) - nothing to split."))
    pc = post_check(b)
    s = pc["summary"]
    out.append(c("dept_plan", "Post-generation: article plan = department sales plan, every department x month",
                 "ok" if not s["dept_off"] else "fail",
                 f"{s['dept_cells'] - s['dept_off']:,} of {s['dept_cells']:,} department x month cells match "
                 f"(largest difference {s['dept_worst']:.8f} L)" + (f"; {s['dept_neg']} carry a negative store plan "
                                                                   f"({s['neg_total']:,.4f} L, kept at 0)" if s["dept_neg"] else ""),
                 "Those departments' articles don't add back to their plan - see the post-generation table."))
    out.append(c("aop_month", f"Post-generation: like-for-like department plan = AOP ({s['aop_label'] or 'publish'}), every division x month",
                 "warn" if s["aop_cells"] == 0 else "ok" if not s["aop_off"] else "fail",
                 "the AOP publish could not be read" if s["aop_cells"] == 0 else
                 f"{s['aop_cells'] - s['aop_off']:,} of {s['aop_cells']:,} division x month cells match, "
                 f"₹{s['aop_total']:,.2f} L in all (largest difference {s['aop_worst']:.6f} L)",
                 "The department plan has moved off the AOP - regenerate the base plan (it holds each division x month on "
                 "the AOP) or check the AOP publish BIS plans on." if s["aop_cells"] else "Check the AOP Forecaster / database."))
    return out


def post_check(b: dict) -> dict:
    """After the plan is generated (user, 2026-10-13: "make a check where the post generation of the data it should look
    if the department sales plan is matching for all departments x months and AOP is correct for all months"), traced
    from the plan file itself, not from the build: (1) every division x department x month - the article plan (all
    groups) = the department sales plan (department engine; a negative store-month plan counts as 0, its articles are
    0); (2) every division x month - the like-for-like stores' department plan = the AOP publish's division plan (the
    target the department engine holds them on), with the all-store plan and the article plan beside it."""
    from engines.mrp_plan_engine import _load_dept_plan
    from engines.dept_sales_engine import _aop_lfl_targets
    plan, months = _load_dept_plan(), b["months"]
    dept, grp, lfl, allp = (collections.defaultdict(float) for _ in range(4))
    for s, sd in (plan.get("stores") or {}).items():
        g = (sd.get("cluster") or "(no cluster)") if b["grain"] == "cluster" else s
        for dv, dd in (sd.get("divisions") or {}).items():
            for m, md in ((dd or {}).get("months") or {}).items():
                if m not in months or not isinstance(md, dict):
                    continue
                for dp, x in (md.get("departments") or {}).items():
                    if not (isinstance(x, dict) and x.get("active", True)):
                        continue
                    v = float(x.get("ty") or 0.0)
                    dept[(dv, dp, m)] += v
                    grp[(g, dv, dp, m)] += v
                    allp[(dv, m)] += v
                    if sd.get("is_ssg"):
                        lfl[(dv, m)] += v
    # what the articles must add to: the plan of each cluster / store (as the plan is built), a negative one counting 0
    due, neg = collections.defaultdict(float), collections.defaultdict(float)
    for (g, dv, dp, m), v in grp.items():
        due[(dv, dp, m)] += max(v, 0.0)
        neg[(dv, dp, m)] += min(v, 0.0)
    art, art_div = collections.defaultdict(float), collections.defaultdict(float)
    for r in b["rows"]:
        for mv in r["arts"].values():
            for m, v in mv.items():
                art[(r["div"], r["dept"], m)] += v
                art_div[(r["div"], m)] += v
    drows = []
    for k in sorted(set(dept) | set(art), key=lambda k: (k[0], k[1], months.index(k[2]) if k[2] in months else 99)):
        if not dept.get(k) and not art.get(k):
            continue
        d = art.get(k, 0.0) - due.get(k, 0.0)
        drows.append({"division": k[0], "department": k[1], "month": k[2], "plan": dept.get(k, 0.0), "articles": art.get(k, 0.0),
                      "negative": neg.get(k, 0.0), "diff": d, "ok": abs(d) <= 1e-6})
    try:
        from engines.division_plan import _bis_aop
        _, label, *_ = _bis_aop()
    except Exception:   # noqa: BLE001
        label = None
    aop = _aop_lfl_targets()
    arows = []
    for dv in sorted({k[0] for k in allp}):
        for m in months:
            a = (aop.get(dv) or {}).get(m)
            arows.append({"division": dv, "month": m, "aop": a, "lfl_plan": lfl.get((dv, m), 0.0),
                          "diff": None if a is None else lfl.get((dv, m), 0.0) - a,
                          "ok": None if a is None else abs(lfl.get((dv, m), 0.0) - a) <= 1e-4,
                          "all_plan": allp.get((dv, m), 0.0), "articles": art_div.get((dv, m), 0.0)})
    have = [r for r in arows if r["aop"] is not None]
    return {"months": months, "departments": drows, "divisions": arows, "summary": {
        "dept_cells": len(drows), "dept_off": sum(1 for r in drows if not r["ok"]),
        "dept_worst": max((abs(r["diff"]) for r in drows), default=0.0),
        "dept_neg": sum(1 for r in drows if r["negative"]), "neg_total": sum(r["negative"] for r in drows),
        "aop_cells": len(have), "aop_off": sum(1 for r in have if not r["ok"]),
        "aop_worst": max((abs(r["diff"]) for r in have), default=0.0), "aop_total": sum(r["aop"] for r in have),
        "aop_label": label}}


# ── promote to the MRP stage ──────────────────────────────────────────────────
# user, 2026-10-13: "also give a provision if the art nm plan has to be promoted to mrp planning stage" -> "Split it into
# MRP bands": each Cluster/Store x Department x Article Name plan is split over MRP bands by that group's LY article x
# MRP mix (MAMJ), the old MRPs moved to the new structure by the Re-apportionment master's own rule (listed -> its new
# MRP; discontinued -> nearest listed below / above, Summer 60/40, others 40/60; not in the master -> the MRP as sold).
# Fallbacks: the chain's mix of the article, then of the department. The result, summed over the groups, is the MRP
# stage's split (division x department x MRP x period %) while the route is Article Name - MRP Plan Output, Display
# Type, Reconciliation and the Store / Cluster MRP panel all read it (mrp_plan_engine.effective_shares).

PROMOTED_PATH = os.path.join(_HERE, "..", "mrp_promoted.json")
_AM: dict = {}


def ly_art_mrp(months: list) -> dict:
    """{(store, dept, article): {new MRP: LY lakh of the block}} (negative counts as 0). Cached per sales file."""
    from engines import mrp_reapportionment_engine as R
    scans = R._calendar_scans()
    files = scans._latest_monthwise_files()
    key = (files[0], os.path.getmtime(files[0]), tuple(months), R._find_mapping_file())
    with _LY_LOCK:
        if _AM.get("key") == key:
            return _AM["v"]
        lym = sorted(_ly_month(m) for m in months)
        lo, hi = scans._month_bounds(lym)
        raw = scans._read_file_filtered(files[0], ["BILLMONTH", "STORE_NAME", "SL_V", "DEPARTMENT", "ARTICLE_NAME", "MRP",
                                                   "DISPLAY_TYPE", "ATTRIBUTE1"], "BILLMONTH", lo, hi)
        raw = raw[raw["BILLMONTH"].dt.strftime("%Y-%m").isin(lym)]
        for c in ("STORE_NAME", "DEPARTMENT", "DISPLAY_TYPE", "ATTRIBUTE1"):
            raw[c] = raw[c].fillna("(BLANK)").astype(str).str.strip().str.upper()
        raw["ARTICLE_NAME"] = raw["ARTICLE_NAME"].fillna("(BLANK)").astype(str).str.strip()
        raw["MRP_CURRENT"] = pd.to_numeric(raw["MRP"], errors="coerce").fillna(0).round().astype(int)
        raw["SL_V"] = pd.to_numeric(raw["SL_V"], errors="coerce").fillna(0.0) / 1e5
        g = (raw.groupby(["STORE_NAME", "DEPARTMENT", "ARTICLE_NAME", "DISPLAY_TYPE", "ATTRIBUTE1", "MRP_CURRENT"])["SL_V"]
             .sum().reset_index().rename(columns={"DISPLAY_TYPE": "DISPLAY", "ATTRIBUTE1": "ATTRIBUTE"}))
        try:
            t = R._targets(R._load_mapping())
        except Exception:   # noqa: BLE001 - no master: the MRPs as sold
            t = pd.DataFrame(columns=["DEPARTMENT", "DISPLAY", "MRP_CURRENT", "MRP_LISTED", "BELOW", "ABOVE"])
        x = g.merge(t, on=["DEPARTMENT", "DISPLAY", "MRP_CURRENT"], how="left")
        listed = x["MRP_LISTED"].fillna(0) > 0
        lo_pct = x["ATTRIBUTE"].map(R.LOWER_PCT).fillna(R.LOWER_PCT_DEFAULT) / 100.0
        lo_pct = lo_pct.where(x["ABOVE"].fillna(0) > 0, 1.0).where(x["BELOW"].fillna(0) > 0, 0.0)
        moved = ~listed & ((x["BELOW"].fillna(0) > 0) | (x["ABOVE"].fillna(0) > 0))
        keep = ~listed & ~moved   # not in the master, or nothing listed in its Department x Display: as sold
        k = ["STORE_NAME", "DEPARTMENT", "ARTICLE_NAME"]
        parts = [x[listed].assign(NEW=x["MRP_LISTED"], V=x["SL_V"]),
                 x[moved].assign(NEW=x["BELOW"], V=x["SL_V"] * lo_pct),
                 x[moved].assign(NEW=x["ABOVE"], V=x["SL_V"] * (1 - lo_pct)),
                 x[keep].assign(NEW=x["MRP_CURRENT"], V=x["SL_V"])]
        y = pd.concat(parts, ignore_index=True)
        y = y[y["NEW"] > 0].groupby(k + ["NEW"])["V"].sum()
        v = {}
        for (s, d, a, mrp), val in y.items():
            if val > 0:
                v.setdefault((s, d, a), {})[str(int(mrp))] = float(val)
        _AM.update(key=key, v=v)
        return v


def promote_split(b: dict, mix: dict, clus: dict) -> tuple:
    """Pure. ({div: {dept: {mrp: {month: lakh}}}}, {how: lakh}) - every group x department x article plan of build `b`
    split over MRP bands by the group's LY article x MRP mix (mix = {(store, dept, article): {mrp: lakh}}), else the
    chain's mix of the article, else of the department; what has none is left out ("none")."""
    def add(acc, key, mm):
        t = acc.setdefault(key, {})
        for k2, v in mm.items():
            t[k2] = t.get(k2, 0.0) + v
    chain_art, chain_dept, by_group = {}, {}, {}
    for (s, d, a), mm in mix.items():
        add(chain_art, (d, a), mm)
        add(chain_dept, d, mm)
        add(by_group, (s, d, a), mm)
        if s in clus:
            add(by_group, (clus[s], d, a), mm)
    out, how = {}, collections.defaultdict(float)
    for r in b["rows"]:
        for a, pm in r["arts"].items():
            tot = sum(pm.values())
            if tot <= 0:
                continue
            for kind, w in (("own", by_group.get((r["g"], r["dept"], a))), ("chain article", chain_art.get((r["dept"], a))),
                            ("chain department", chain_dept.get(r["dept"]))):
                if w and sum(w.values()) > 0:
                    break
            else:
                how["none"] += tot
                continue
            how[kind] += tot
            dd = out.setdefault(r["div"], {}).setdefault(r["dept"], {})
            for m, v in pm.items():
                for mrp, part in split(v, w).items():
                    cell = dd.setdefault(mrp, {})
                    cell[m] = cell.get(m, 0.0) + part
    return out, dict(how)


def _stamp(b: dict) -> dict:
    c = b["cont"] or {}
    return {"grain": b["grain"], "file": c.get("source_file"), "imported_at": c.get("imported_at"),
            "plan": round(sum(sum(r["aop"].values()) for r in b["rows"]), 4), "months": b["months"]}


def promoted() -> dict | None:
    """The promoted split, while the route is Article Name (None otherwise)."""
    if get_settings()["route"] != "article":
        return None
    return _read(PROMOTED_PATH)


def promoted_shares() -> dict | None:
    """{div: {dept: {mrp: {"Mar'27 P1": %, "Mar'27 P2": %}}}} - the MRP stage's split from the promoted Article Name plan."""
    p = promoted()
    return p["shares"] if p else None


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/promote")
def get_promote():
    """The last promote, whether the MRP stage uses it (route) and whether the article plan changed since."""
    p = _read(PROMOTED_PATH)
    if not p:
        return {"promoted": False, "route": get_settings()["route"]}
    try:
        cur = _stamp(built(get_settings()["grain"]))
    except Exception:   # noqa: BLE001
        cur = None
    return {"promoted": True, "route": get_settings()["route"], "in_use": get_settings()["route"] == "article",
            "stale": cur is not None and cur != p["stamp"], "now": cur,
            **{k: p[k] for k in ("promoted_at", "by", "stamp", "how", "total", "bands", "depts")}}


@router.post("/promote")
def post_promote(request: Request):
    """Split the Article Name plan into MRP bands and make it the MRP stage's split (while the route is Article Name)."""
    s = get_settings()
    b = built(s["grain"])
    from engines.mrp_plan_engine import _load_dept_plan
    plan = _load_dept_plan()
    clus = {st: (sd.get("cluster") or "(no cluster)") for st, sd in plan["stores"].items()}
    mix = ly_art_mrp(b["months"])
    split_, how = promote_split(b, mix, clus)
    shares = {}
    for dv, dd in split_.items():
        for dp, bands in dd.items():
            for m in b["months"]:
                tot = sum(v.get(m, 0.0) for v in bands.values())
                if tot <= 0:
                    continue
                for mrp, v in bands.items():
                    pct = v.get(m, 0.0) / tot * 100.0
                    if pct:
                        cell = shares.setdefault(dv, {}).setdefault(dp, {}).setdefault(mrp, {})
                        cell[f"{m} P1"] = cell[f"{m} P2"] = pct
    user = ((request.scope.get("session") or {}).get("user") or {}).get("username") or ""
    out = {"promoted_at": datetime.datetime.now().strftime("%d %b %Y %H:%M"), "by": user, "stamp": _stamp(b),
           "how": how, "total": sum(how.values()), "shares": shares,
           "depts": sum(len(d) for d in shares.values()), "bands": sum(len(x) for d in shares.values() for x in d.values())}
    save_json(PROMOTED_PATH, out)
    if s["route"] != "article":
        set_settings({"route": "article"})
    return {k: v for k, v in out.items() if k != "shares"}


@router.get("/settings")
def get_settings():
    return {"route": "mrp", "grain": "cluster", **(_read(ROUTE_PATH) or {})}


@router.post("/settings")
def set_settings(body: dict):
    cur = get_settings()
    if body.get("route") in ("mrp", "article"):
        cur["route"] = body["route"]
    if body.get("grain") in ("cluster", "store"):
        cur["grain"] = body["grain"]
    save_json(ROUTE_PATH, cur)
    return cur


@router.get("/export")
def export_cont():
    """The Art Nm Cont % in use, exactly as it was imported - edit it and Import it back. Nothing imported yet: a
    template in the same layout, one row per plan department x LY article, filled with the chain's LY Art Nm cont %
    of the block (user, 2026-10-13: "give me an import and export function")."""
    c = _read(CONT_PATH)
    if c and os.path.exists(SOURCE_COPY):
        from fastapi.responses import FileResponse
        return FileResponse(SOURCE_COPY, media_type=XLSX, filename=c.get("source_file") or "Art Nm Cont %.xlsx")
    from engines.mrp_plan_engine import _load_dept_plan
    plan = _load_dept_plan()
    months = _plan_months(plan)
    ly, _ = ly_sales(months)
    depts = {}
    for sd in (plan.get("stores") or {}).values():
        for dv, dd in (sd.get("divisions") or {}).items():
            for md in ((dd or {}).get("months") or {}).values():
                for dp, x in ((md or {}).get("departments") or {}).items():
                    if isinstance(x, dict) and x.get("active", True) and x.get("ty"):
                        depts[dp] = dv
    arts = collections.defaultdict(lambda: collections.defaultdict(float))
    for (s, d), am in ly.items():
        if d in depts:
            for a, mm in am.items():
                arts[d][a] += sum(max(v, 0.0) for v in mm.values())
    block = "".join(m[0] for m in months)
    col = f"BUYERS INPUT\nAT {block}"
    rows = []
    for d in sorted(depts, key=lambda d: (depts[d], d)):
        tot = sum(arts[d].values())
        for a in sorted(arts[d]) or [""]:
            rows.append({"DIVISION": depts[d], "DEPARTMENT": d, "NEW ARTICLE_NAME": a,
                         col: arts[d][a] / tot if tot else 0.0, "MC TAG": "EXISTING ACTIVE MC"})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        pd.DataFrame(rows).to_excel(xw, sheet_name="Sheet1", index=False)
        ws = xw.sheets["Sheet1"]
        ws.set_column(0, 2, 26)
        ws.set_column(3, 3, 16, xw.book.add_format({"num_format": "0.0%"}))
        ws.set_column(4, 4, 20)
        ws.freeze_panes(1, 0)
    buf.seek(0)
    return StreamingResponse(buf, media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="Art Nm Cont % template {block}.xlsx"'})


@router.get("/cont")
def get_cont():
    """The Art Nm Cont % in use, as imported (Buyer's Input table)."""
    c = _read(CONT_PATH)
    if not c:
        raise HTTPException(404, "No Art Nm Cont % imported yet")
    return c


def _take(data: bytes, name: str) -> dict:
    try:
        cont = parse_cont(pd.read_excel(io.BytesIO(data)))
    except Exception as e:   # noqa: BLE001
        raise HTTPException(400, f"Not a usable Art Nm Cont % file - nothing changed: {e}")
    if not cont["depts"]:
        raise HTTPException(400, "No Department x Article Name rows - nothing changed")
    cont.update(source_file=name, imported_at=datetime.datetime.now().strftime("%d %b %Y %H:%M"))
    tmp = SOURCE_COPY + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, SOURCE_COPY)
    save_json(CONT_PATH, cont)
    tags = collections.Counter(d["tag"] for d in cont["depts"].values())
    return {"ok": True, "source_file": name, "departments": len(cont["depts"]),
            "articles": sum(len(d["arts"]) for d in cont["depts"].values()), "block": cont["block"], "tags": dict(tags),
            "warnings": cont["warnings"]}


@router.post("/import")
def import_cont(file: UploadFile = File(...)):
    """The buyers' Art Nm Cont % (.xlsx) uploaded - read and checked before it replaces the one in use."""
    if not (file.filename or "").lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Import the Art Nm Cont % as an .xlsx file")
    return _take(file.file.read(), os.path.basename(file.filename))


# ── the output page: a Hierarchy, as the department plan's Final Results ──────────────────────────────────────────
# user, 2026-10-13: "Mimic the working pop up for every entry and make similar output page as the department with all
# features similarly" - the same tree (Rows picked and ordered, one multi-select filter per field, Grand Total, Cont %,
# the ⓘ pop-up) over the Article Name plan: TY = the article plan, LY = the article's LY sales (sales engine). The
# Department filter comes first - the department selection.
ART_LEVELS_ALL = ("department", "article", "cluster", "store", "stype", "division", "attribute", "month")


def art_levels(grain: str) -> tuple:
    """The fields the tree offers: by cluster there is no store (and no store type)."""
    return ART_LEVELS_ALL if grain == "store" else tuple(x for x in ART_LEVELS_ALL if x not in ("store", "stype"))


def art_cells(b: dict, attr: dict):
    """Every (fields, row, article, month, LY, plan) of build `b`."""
    for r in b["rows"]:
        at = (attr.get(r["div"]) or {}).get(r["dept"]) or "-"
        for a in set(r["arts"]) | set(r["lym"]):
            pm, lm = r["arts"].get(a, {}), r["lym"].get(a, {})
            for m in b["months"]:
                key = {"department": r["dept"], "article": a, "cluster": r["cluster"], "store": r["g"], "stype": r["stype"],
                       "division": r["div"], "attribute": at, "month": m}
                yield key, r, a, m, lm.get(m, 0.0), pm.get(m, 0.0)


_HIX: dict = {}


def _hindex(grain: str) -> tuple:
    import json
    from engines.final_results_engine import _load_dept_attr_map
    from engines.grain_view import make_index
    b = built(grain)
    attr = _load_dept_attr_map()
    key = (id(b), json.dumps(attr, sort_keys=True, default=str))
    if _HIX.get(grain, {}).get("key") != key:
        _HIX[grain] = {"key": key, "attr": attr,
                       "ix": make_index(((k, ly, ty) for k, _r, _a, _m, ly, ty in art_cells(b, attr)), art_levels(grain))}
    return b, _HIX[grain]


def _levels_path(levels: str, path: str, grain: str, longest: int = 0) -> tuple:
    import json
    lv = [x for x in levels.split(",") if x]
    ok = art_levels(grain)
    if not lv or len(set(lv)) != len(lv) or any(x not in ok for x in lv):
        raise HTTPException(422, f"levels: pick from {', '.join(ok)}, each once")
    try:
        pth = json.loads(path)
    except ValueError:
        raise HTTPException(422, "path must be a JSON list")
    if not isinstance(pth, list) or len(pth) > len(lv) - longest:
        raise HTTPException(422, "path is too long for these levels")
    return lv, [str(p) for p in pth]


@router.get("/hierarchy")
def get_hierarchy(levels: str, path: str = "[]", filters: str = "{}", grain: str = "cluster"):
    """The children of one node of the Article Name plan tree (as /api/planning/grain/hierarchy)."""
    from engines.grain_view import parse_filters, rows_of
    lv, pth = _levels_path(levels, path, grain, longest=1)
    _, h = _hindex(grain)
    return {**rows_of(h["ix"], lv, pth, parse_filters(filters, art_levels(grain))),
            "source": {"kind": "article", "name": "Article Name plan", "note": f"the Article Name plan by {grain}"}}


@router.get("/hierarchy-options")
def get_hierarchy_options(filters: str = "{}", level: str = "", grain: str = "cluster"):
    from engines.grain_view import parse_filters, values_of
    if level and level not in art_levels(grain):
        raise HTTPException(422, f"level: one of {', '.join(art_levels(grain))}")
    _, h = _hindex(grain)
    return values_of(h["ix"], parse_filters(filters, art_levels(grain)), [level] if level else art_levels(grain))


ART_LEVEL_NAME = {"department": "Department", "article": "Article Name", "cluster": "Cluster", "store": "Store",
                  "stype": "Store type", "division": "Division", "attribute": "Attribute", "month": "Month"}


def explain_art(b: dict, attr: dict, levels: list, path: list, filt: dict | None, grain: str) -> dict:
    """Pure. How the Article Name tree's row at `path` (or the Total, path = []) gets its numbers - from the very cells
    the row adds up, month by month: LY sales, LY cont %, input %, deviation, capped, resultant, share, department AOP,
    plan (user, 2026-10-13: "Mimic the working pop up for every entry")."""
    from engines.grain_view import _inr
    want = dict(zip(levels, path))
    f = filt or {}
    fit = lambda k, w: all(k[x] == v for x, v in w.items()) and all(k[x] in s for x, s in f.items())   # noqa: E731
    G = "cluster" if grain == "cluster" else "store"
    sel = [c for c in art_cells(b, attr) if fit(c[0], want)]
    LY, TY = sum(c[4] for c in sel), sum(c[5] for c in sel)
    label = " · ".join(path) if path else "The total"
    mon = {}
    for c in sel:
        x = mon.setdefault(c[3], [0.0, 0.0])
        x[0] += c[4]
        x[1] += c[5]
    out = {"label": label, "path": [{"level": lv, "value": v} for lv, v in zip(levels, path)], "ly": LY, "ty": TY,
           "growth": (TY / LY - 1) * 100 if LY else None, "source": f"the Article Name plan by {grain}"}
    lines = []
    say = lambda h, t: lines.append({"h": h, "t": t})   # noqa: E731
    ms = [m for m in b["months"] if m in mon]
    say("The number", f"{label}: ₹{_inr(TY)} L of article plan against ₹{_inr(LY)} L LY sales of the same articles "
        f"(sales engine){', over ' + ', '.join(ms) if len(ms) > 1 else ', in ' + ms[0] if ms else ''}.")
    if LY:
        say("Growth %", f"₹{_inr(TY)} ÷ ₹{_inr(LY)} − 1 = {out['growth']:+.1f}%.")
    if path:
        pw = dict(zip(levels, path[:-1]))
        pty = sum(c[5] for c in art_cells(b, attr) if fit(c[0], pw))
        out["parent"] = {"label": " · ".join(path[:-1]) or "the whole plan", "ty": pty}
        out["cont"] = TY / pty * 100 if pty else None
        if pty:
            say("Cont %", f"its share of the level above ({out['parent']['label']}): ₹{_inr(TY)} ÷ ₹{_inr(pty)} = {out['cont']:.1f}%.")
    # the department AOP these cells split: each group x department x month once
    seen, aop, by_how, depts, groups = set(), 0.0, collections.defaultdict(float), set(), set()
    for k, r, a, m, ly, ty in sel:
        if (id(r), m) not in seen:
            seen.add((id(r), m))
            aop += max(r["aop"].get(m, 0.0), 0.0)
        by_how[r["method"]] += ty
        depts.add(r["dept"])
        groups.add(r["g"])
    at_article = "article" in want or "article" in f
    if not at_article:
        ok = abs(TY - aop) <= 1e-6
        say("Department AOP", f"₹{_inr(aop)} L is the plan of {len(depts)} department{'s' if len(depts) != 1 else ''} × "
            f"{len(groups)} {G}{'s' if len(groups) != 1 else ''} × {len(ms)} month{'s' if len(ms) != 1 else ''} from the "
            f"department engine; its Article Names add back to it" + (" ✓" if ok else f" - ₹{_inr(TY)} L (a negative "
                                                                      "department plan month keeps its articles at 0)") + ".")
    elif aop:
        say("Share of the department AOP", f"these articles take ₹{_inr(TY)} of their department's ₹{_inr(aop)} L "
            f"({TY / aop * 100:.1f}%) in the {len(groups)} {G}{'s' if len(groups) != 1 else ''} × months inside this row.")
    if by_how:
        say("How it is split", "; ".join(f"{METHOD[k]}: ₹{_inr(v)} L" for k, v in sorted(by_how.items(), key=lambda x: -x[1])) + ".")
    if set(by_how) & {"deviation", "inactive", "ly", "cluster", "chain"}:
        say("The steps", f"(1) LY sales of each {G} × department × Article Name × month (below 0 counts as 0); (2) LY cont % "
            "= the article's share of its department's LY that month; (3) deviation = the input Art Nm Cont % ÷ LY cont %, "
            f"capped to 50%–150% (an in-active MC is 0%); (4) resultant = LY cont % × capped deviation; (5) the resultants "
            f"are apportioned to 100% within the {G} × department × month and × the department AOP.")
    # the working, cell by cell, for one department and one article
    arts = {(c[1]["dept"], c[2]) for c in sel}
    if len(arts) == 1 and sel:
        many = len(groups) > 6
        cols = ["Month"] + ([] if many or len(groups) == 1 else [G.title()]) + [
            "LY ₹L", "LY cont %", "Input %", "Deviation", "Capped", "Resultant", "Share %", "Dept AOP ₹L", "Plan ₹L"]
        trows, agg = [], {}
        p = lambda v: "–" if v is None else f"{v:.1f}%"   # noqa: E731
        for k, r, a, m, ly, ty in sorted(sel, key=lambda c: (b["months"].index(c[3]), c[1]["g"])):
            w = (r["info"].get(a) or {}).get(m)
            dep_aop = max(r["aop"].get(m, 0.0), 0.0)
            if many:
                g = agg.setdefault(m, {"ly": 0.0, "dly": 0.0, "aop": 0.0, "ty": 0.0, "dev": [], "cap": [], "b": None})
                g["ly"] += max(ly, 0.0)
                g["dly"] += sum(((r["info"].get(x) or {}).get(m) or (0.0,))[0] for x in r["info"])
                g["aop"] += dep_aop
                g["ty"] += ty
                if w:
                    g["b"] = w[2]
                    if w[3] is not None:
                        g["dev"].append(w[3])
                        g["cap"].append(w[4])
                elif a in r["buyer"]:
                    g["b"] = r["buyer"][a]
                continue
            trows.append([m] + ([] if len(groups) == 1 else [r["g"]]) + [
                _inr(ly), p(w[1]) if w else "–", p(w[2] if w else r["buyer"].get(a)),
                "new article - input % as is" if a in r.get("new_arts", ()) else f"{w[3] * 100:.0f}%" if w and w[3] is not None else "–",
                f"{w[4] * 100:.0f}%" if w and w[4] is not None else "–", f"{w[5]:.2f}" if w and w[5] is not None else "–", p(ty / dep_aop * 100 if dep_aop else None), _inr(dep_aop), _inr(ty)])
        for m, g in agg.items():
            rng = lambda v: "–" if not v else f"{min(v) * 100:.0f}%" if abs(max(v) - min(v)) < 1e-9 else f"{min(v) * 100:.0f}–{max(v) * 100:.0f}%"   # noqa: E731
            trows.append([m, _inr(g["ly"]), p(g["ly"] / g["dly"] * 100 if g["dly"] else None), p(g["b"]), rng(g["dev"]),
                          rng(g["cap"]), "–", p(g["ty"] / g["aop"] * 100 if g["aop"] else None), _inr(g["aop"]), _inr(g["ty"])])
        out["table"] = {"title": "The working, month by month" + (f" (all {len(groups)} {G}s added up; deviation as a range)" if many else ""),
                        "cols": cols, "rows": trows}
        (dp, a), = arts
        if any(c[1]["method"] == "deviation" for c in sel):
            say("Read it as", f"in each {G} and month, {a}'s LY cont % × its capped deviation is its resultant; its share is its "
                "resultant ÷ the sum of all its department's resultants that month; × the department AOP = its plan.")
    say("Check", f"₹{_inr(TY)} - the number on screen ✓")
    if f:
        lines.insert(0, {"h": "Filters on", "t": "; ".join(f"{ART_LEVEL_NAME.get(k, k)}: {', '.join(sorted(v))}"
                                                          for k, v in f.items()) + " - every figure here is inside them."})
    out["lines"] = lines
    out["months"] = [{"month": m, "ly": mon[m][0], "ty": mon[m][1]} for m in ms]
    return out


@router.get("/explain")
def get_explain(levels: str, path: str = "[]", filters: str = "{}", grain: str = "cluster"):
    """?levels=department,article&path=["ML_JEANS","01-EPP [ML04]"] -> how that row's numbers are made."""
    from engines.grain_view import parse_filters
    lv, pth = _levels_path(levels, path, grain)
    b, h = _hindex(grain)
    return explain_art(b, h["attr"], lv, pth, parse_filters(filters, art_levels(grain)), grain)


@router.get("/post-check")
def get_post_check(grain: str = "cluster"):
    """The post-generation check in full: every department x month (article plan vs department sales plan) and every
    division x month (like-for-like department plan vs AOP; all-store plan and article plan beside it)."""
    return post_check(built(grain))


@router.get("/summary")
def get_summary(grain: str = "cluster"):
    """The checks, the file in use and the totals of the Article Name plan by `grain`."""
    try:
        b = built(grain)
    except HTTPException:
        raise
    except Exception as e:   # noqa: BLE001
        raise HTTPException(500, f"Article Name plan: {e}")
    return {"grain": grain, "months": b["months"], "checks": checks(b),
            "plan": sum(v for r in b["rows"] for mv in r["arts"].values() for v in mv.values()),
            "aop": sum(sum(r["aop"].values()) for r in b["rows"]),
            "cont": {k: b["cont"].get(k) for k in ("source_file", "imported_at", "block")} if b["cont"] else None}


@router.get("/plan-export")
def plan_export(grain: str = "cluster"):
    """Every group x department x article x month with its working: LY, LY cont %, input %, deviation, capped, resultant,
    share and plan; a Department Check sheet (AOP vs articles per month) and the Checks."""
    b = built(grain)
    months, recs, chk = b["months"], [], []
    G = "CLUSTER" if grain == "cluster" else "STORE"
    for r in sorted(b["rows"], key=lambda r: (r["div"], r["dept"], r["g"])):
        tot = {m: sum(((r["info"].get(x) or {}).get(m) or (0, 0, 0, 0, 0, 0.0))[5] or 0.0 for x in r["info"]) for m in months}
        for a in sorted(set(r["arts"]) | set(r["lym"])):
            for m in months:
                w = (r["info"].get(a) or {}).get(m)
                ty, dep = r["arts"].get(a, {}).get(m, 0.0), r["aop"].get(m, 0.0)
                recs.append({G: r["g"], **({"IN CLUSTER": r["cluster"]} if grain == "store" else {}), "DIVISION": r["div"],
                             "DEPARTMENT": r["dept"], "ARTICLE NAME": a, "MONTH": m, "TAG": r["tag"], "METHOD": METHOD[r["method"]],
                             "LY (L)": r["lym"].get(a, {}).get(m, 0.0), "LY CONT %": w[1] if w else None,
                             "INPUT %": w[2] if w else r["buyer"].get(a), "DEVIATION": w[3] if w else None,
                             "CAPPED": w[4] if w else None, "RESULTANT": w[5] if w else None,
                             "NEW ARTICLE": "yes" if a in r.get("new_arts", ()) else "",
                             "SHARE %": (w[5] / tot[m] * 100 if tot[m] else None) if w and w[5] is not None else (ty / dep * 100 if dep > 0 else None),
                             "DEPT AOP (L)": dep, "PLAN (L)": ty})
        for m in months:
            s = sum(mv.get(m, 0.0) for mv in r["arts"].values())
            t = r["aop"].get(m, 0.0)
            chk.append({G: r["g"], "DIVISION": r["div"], "DEPARTMENT": r["dept"], "MONTH": m, "METHOD": METHOD[r["method"]],
                        "DEPT AOP (L)": t, "ARTICLE PLAN (L)": s, "DIFF (L)": s - max(t, 0.0),
                        "CHECK": "OK" if abs(s - max(t, 0.0)) <= SHOWN else "NOT = AOP"})
    if len(recs) > 1_000_000:
        raise HTTPException(413, f"{len(recs):,} rows - over Excel's limit; export by cluster")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        for name, df in (("Article Plan", pd.DataFrame(recs)), ("Department Check", pd.DataFrame(chk)),
                         ("Checks", pd.DataFrame(checks(b))[["label", "status", "detail", "fix"]])):
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
            ws.set_column(0, max(len(df.columns) - 1, 0), 15)
    buf.seek(0)
    name = f"Article Name plan by {grain} {datetime.datetime.now():%d%b%Y_%H%M}.xlsx"
    return StreamingResponse(buf, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def warm():
    """Read the LY article sales once at server start when the Article Name branch is in use (route or a file)."""
    try:
        s = get_settings()
        if s["route"] == "article" or os.path.exists(CONT_PATH):
            built(s["grain"])
    except Exception as e:   # noqa: BLE001
        print(f"Article Name route warm-up skipped: {e}", flush=True)


@router.get("/hierarchy-export")
def get_hierarchy_export(levels: str, filters: str = "{}", grain: str = "cluster"):
    """The Article Name plan tree as on screen (Rows, filters) as an Excel file - every branch opened (2026-10-14)."""
    from engines.grain_view import export_about, parse_filters, tree_xlsx, xlsx_response
    lv, _ = _levels_path(levels, "[]", grain)
    f = parse_filters(filters, art_levels(grain))
    _, h = _hindex(grain)
    data = tree_xlsx(h["ix"], lv, ART_LEVEL_NAME, f, ("LY (₹L)", "TY (₹L)", "Growth %"), "Article Name plan",
                     export_about(lv, ART_LEVEL_NAME, f, "month", f"the Article Name plan by {grain}"))
    return xlsx_response(data, f"Article Name plan by {grain}.xlsx")
