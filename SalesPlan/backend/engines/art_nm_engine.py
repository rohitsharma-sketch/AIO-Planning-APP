"""
Article Name route of the MRP stage (user, 2026-10-13: "Add a provision toggle if the user wants to go Article Name or
MRP route. Follow the MRP route as is"). The department plan is split over Article Names instead of MRP bands:

  1. LY sales per Cluster (or Store - the toggle) x Department x Article Name x month, from the sales engine (data lake,
     LY = the plan month a year back). Negative LY counts as 0 (no negative base).
  2. The buyers' Art Nm Cont % (imported, one % per Department x Article Name for the block, e.g. MAMJ) against the
     cluster's own LY Art Nm cont % of the block: deviation = buyer % / cluster LY %, capped to 50%..150%.
  3. New base = LY x capped deviation (never negative), month by month; within each Cluster x Department x month the
     new base is apportioned to 100% and the department's plan (its AOP in the Sales Plan) is split by it - the
     articles add back to the department exactly, and a check says where they don't.
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
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import SHOWN, split  # noqa: E402
from plan_cache import save_json  # noqa: E402

router = APIRouter()

_HERE = os.path.dirname(os.path.abspath(__file__))
CONT_PATH = os.path.join(_HERE, "..", "art_nm_cont.json")       # the imported buyers' file, parsed
ROUTE_PATH = os.path.join(_HERE, "..", "mrp_route.json")        # {"route": "mrp" | "article", "grain": ...}
# the buyers drop their Art Nm Cont % here, as the MRP Cont % (Buyer's Input -> Sync from folder; the newest .xlsx)
SOURCE_DIR = r"C:\Users\A9820\Documents\CLaude - New Projects\SalesPlan\Art NM Cont %"
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
        d["arts"][art] = float(v[i]) * scale if pd.notna(v[i]) else 0.0
    for dept, d in depts.items():
        t = sum(d["arts"].values())
        if t > 0 and abs(t - 100) > 0.5:
            warn.append(f"{dept}: Art Nm Cont % adds to {t:.1f}%")
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


def shares_for(tag, bmix, lyg, months):
    """One Cluster/Store x Department: ({month: {article: weight}} or None, method, {article: (ly %, deviation,
    capped)}). lyg = {article: {month: lakh}} of this group (already summed for a cluster)."""
    base = {a: {m: max(float(v.get(m, 0.0)), 0.0) for m in months} for a, v in (lyg or {}).items()}
    blk = {a: sum(v.values()) for a, v in base.items()}
    tot = sum(blk.values())
    bsum = sum(bmix.values()) if bmix else 0.0
    if tag in ("new", "split") and bsum > 0:
        return {m: dict(bmix) for m in months}, "buyer", {}
    if tot <= 0:
        return ({m: dict(bmix) for m in months}, "buyer_noly", {}) if bsum > 0 else (None, "none", {})
    if bsum <= 0:
        cap, how = {a: 1.0 for a in base}, "ly"
    else:
        cap, how = {}, "deviation"
        for a in base:
            lyp = blk[a] / tot * 100.0
            cap[a] = min(max((bmix.get(a, 0.0) / lyp) if lyp > 0 else 0.0, CAP_LO), CAP_HI)
    nb = {m: {a: base[a][m] * cap[a] for a in base} for m in months}
    blk_nb = {a: blk[a] * cap[a] for a in base}
    for m in months:   # a month with no LY of its own takes the block's new base
        if sum(nb[m].values()) <= 0:
            nb[m] = dict(blk_nb)
    info = {a: (blk[a] / tot * 100.0, (bmix.get(a, 0.0) / (blk[a] / tot * 100.0)) if bsum > 0 and blk[a] > 0 else None,
                cap[a]) for a in base}
    return nb, how, info


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
        lyg = summed([(s, dp) for s in members[g]]) if grain == "cluster" else ly.get((g, dp))
        w, how, info = shares_for(tag, bmix, lyg, months)
        if grain == "store" and how in ("none", "buyer_noly"):   # a store with no LY: its cluster's mix first
            c = clus[g]
            if (c, dp) not in cl_cache:
                cl_cache[(c, dp)] = shares_for(tag, bmix, summed([(s, dp) for s in members[c]]), months)
            cw, chow, cinfo = cl_cache[(c, dp)]
            if cw is not None and chow not in ("none", "buyer_noly"):
                w, how, info = cw, "cluster", cinfo
        if how == "none":   # no LY here and no buyer %: the chain's LY mix of the department
            if dp not in ch_cache:
                ch_cache[dp] = shares_for(tag, bmix, summed([(s, dp) for s in plan["stores"]]), months)
            if ch_cache[dp][0] is not None:
                w, how, info = ch_cache[dp][0], "chain", ch_cache[dp][2]
        arts = {}
        for m in months:
            for a, v in (split(max(mv.get(m, 0.0), 0.0), w[m]) if w else {}).items():
                arts.setdefault(a, {})[m] = v
        lyb = {a: sum(max(float(x), 0.0) for x in mvs.values()) for a, mvs in (lyg or {}).items()}
        rows.append({"g": g, "cluster": clus[g] if grain == "store" else g, "div": dv, "dept": dp, "tag": tag,
                     "method": how, "aop": dict(mv), "arts": arts, "ly": lyb, "info": info, "buyer": bmix})
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
        os.path.join(_HERE, "..", f) for f in ("base_corrected_plan.json", "attr_corrected_plan.json", "final_dept_plan.json"))))
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
    caps = [x[2] for r in rows for x in r["info"].values()]
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
    tot = sum(sum(r["aop"].values()) for r in rows)
    out.append(c("trace", "Department AOP traced to the Sales Plan department plan", "ok",
                 f"{tot:,.2f} L over {', '.join(months)} = the department plan Plan Output splits"))
    return out


# ── endpoints ─────────────────────────────────────────────────────────────────

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


def _source_file():
    import glob
    fs = [f for f in glob.glob(os.path.join(SOURCE_DIR, "*.xls*")) if not os.path.basename(f).startswith("~$")]
    return max(fs, key=os.path.getmtime) if fs else None


@router.get("/sync-status")
def sync_status():
    """The newest Art Nm Cont % file in the source folder (what Sync would read)."""
    f = _source_file()
    if not f:
        return {"file_found": False, "source_path": SOURCE_DIR}
    return {"file_found": True, "source_path": SOURCE_DIR, "source_name": os.path.basename(f),
            "file_date": datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d %b %Y %H:%M"),
            "size_kb": round(os.path.getsize(f) / 1024, 1)}


@router.post("/sync")
def sync_cont():
    """Import the newest Art Nm Cont % file in the source folder (as MRP Plan's Buyer's Input does)."""
    f = _source_file()
    if not f:
        raise HTTPException(404, f"No .xlsx in {SOURCE_DIR} - drop the Art Nm Cont % file there and try again")
    with open(f, "rb") as fh:
        return _take(fh.read(), os.path.basename(f))


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


@router.get("/plan")
def get_plan(grain: str = "cluster", g: str = ""):
    """Per division x department (all groups, or the groups in g, '|'-separated): AOP, article plan, method, check,
    and its articles (LY cont %, buyer cont %, plan cont %, plan per month)."""
    try:
        b = built(grain)
    except HTTPException:
        raise
    except Exception as e:   # noqa: BLE001
        raise HTTPException(500, f"Article Name route: {e}")
    months = b["months"]
    want = set(filter(None, g.split("|")))
    rows = [r for r in b["rows"] if not want or r["g"] in want]
    one = len({r["g"] for r in rows}) == 1
    out = {}
    for r in rows:
        d = out.setdefault(r["div"], {}).setdefault(r["dept"], {
            "tag": r["tag"], "methods": collections.Counter(), "aop": dict.fromkeys(months, 0.0),
            "plan": dict.fromkeys(months, 0.0), "arts": {}, "ly": collections.defaultdict(float), "buyer": r["buyer"]})
        d["methods"][METHOD[r["method"]]] += 1
        for m in months:
            d["aop"][m] += r["aop"].get(m, 0.0)
            # what the articles must add to: a negative department plan cell gives its articles 0 (no negative plan)
            d.setdefault("due", dict.fromkeys(months, 0.0))[m] += max(r["aop"].get(m, 0.0), 0.0)
            d["neg"] = d.get("neg", 0) + (r["aop"].get(m, 0.0) < 0)
        for a, mv in r["arts"].items():
            x = d["arts"].setdefault(a, dict.fromkeys(months, 0.0))
            for m, v in mv.items():
                x[m] += v
                d["plan"][m] += v
        for a, v in r["ly"].items():
            d["ly"][a] += v
        if one:
            d["info"] = r["info"]
    res = {}
    for dv, depts in out.items():
        for dp, d in depts.items():
            lyt, pt = sum(d["ly"].values()), sum(d["plan"].values())
            arts = []
            for a in sorted(set(d["arts"]) | set(d["ly"]) | set(d["buyer"])):
                pm = d["arts"].get(a, dict.fromkeys(months, 0.0))
                inf = (d.get("info") or {}).get(a)
                arts.append({"article": a, "ly_pct": d["ly"].get(a, 0.0) / lyt * 100 if lyt else None,
                             "buyer_pct": d["buyer"].get(a), "plan": pm, "total": sum(pm.values()),
                             "plan_pct": sum(pm.values()) / pt * 100 if pt else 0.0,
                             "dev": inf[1] if inf else None, "cap": inf[2] if inf else None})
            gap = max(abs(d["plan"][m] - d["due"][m]) for m in months) if months else 0.0
            res.setdefault(dv, {})[dp] = {
                "tag": d["tag"], "method": d["methods"].most_common(1)[0][0], "methods": dict(d["methods"]),
                "aop": d["aop"], "plan": d["plan"], "aop_total": sum(d["aop"].values()), "plan_total": pt,
                "diff": pt - sum(d["due"].values()), "ok": gap <= SHOWN * max(1, len(rows)), "neg": d.get("neg", 0),
                "neg_total": sum(d["aop"].values()) - sum(d["due"].values()), "articles": arts}
    return {"grain": grain, "months": months, "groups": sorted({r["g"] for r in b["rows"]}),
            "single_group": one, "divisions": sorted(res), "data": res, "checks": checks(b),
            "cont": {k: b["cont"].get(k) for k in ("source_file", "imported_at", "block")} if b["cont"] else None}


@router.get("/export")
def export(grain: str = "cluster"):
    """Every group x department x article: tag, method, LY, LY %, buyer %, deviation, capped, per month cont % and plan;
    a Department Check sheet (AOP vs articles per month) and the Checks."""
    b = built(grain)
    months, recs, chk = b["months"], [], []
    G = "CLUSTER" if grain == "cluster" else "STORE"
    for r in sorted(b["rows"], key=lambda r: (r["div"], r["dept"], r["g"])):
        lyt = sum(r["ly"].values())
        for a in sorted(set(r["arts"]) | set(r["ly"])):
            pm, inf = r["arts"].get(a, {}), r["info"].get(a)
            rec = {G: r["g"], **({"IN CLUSTER": r["cluster"]} if grain == "store" else {}), "DIVISION": r["div"],
                   "DEPARTMENT": r["dept"], "ARTICLE NAME": a, "TAG": r["tag"], "METHOD": METHOD[r["method"]],
                   "LY (L)": r["ly"].get(a, 0.0), "LY CONT %": r["ly"].get(a, 0.0) / lyt * 100 if lyt else None,
                   "BUYER CONT %": r["buyer"].get(a), "DEVIATION": inf[1] if inf else None,
                   "CAPPED": inf[2] if inf else None}
            for m in months:
                tm = r["aop"].get(m, 0.0)
                rec[f"{m} CONT %"] = pm.get(m, 0.0) / tm * 100 if tm else None
                rec[f"{m} PLAN (L)"] = pm.get(m, 0.0)
            rec["PLAN TOTAL (L)"] = sum(pm.values())
            recs.append(rec)
        for m in months:
            s = sum(mv.get(m, 0.0) for mv in r["arts"].values())
            chk.append({G: r["g"], "DIVISION": r["div"], "DEPARTMENT": r["dept"], "MONTH": m, "METHOD": METHOD[r["method"]],
                        "DEPT AOP (L)": r["aop"].get(m, 0.0), "ARTICLE PLAN (L)": s, "DIFF (L)": s - r["aop"].get(m, 0.0),
                        "CHECK": "OK" if abs(s - r["aop"].get(m, 0.0)) <= SHOWN else "NOT = AOP"})
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
            ws.set_column(0, max(len(df.columns) - 1, 0), 16)
    buf.seek(0)
    name = f"Article Name plan by {grain} {datetime.datetime.now():%d%b%Y_%H%M}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


def warm():
    """Read the LY article sales once at server start when the Article Name branch is in use (route or a file)."""
    try:
        s = get_settings()
        if s["route"] == "article" or os.path.exists(CONT_PATH):
            built(s["grain"])
    except Exception as e:   # noqa: BLE001
        print(f"Article Name route warm-up skipped: {e}", flush=True)
