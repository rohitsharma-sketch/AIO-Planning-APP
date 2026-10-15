# Display Type Plan Engine
# Store × Dept × MRP × Display Type → ₹L plan and Qty
#
# Sources:
#   final_dept_plan.json  — store × div × dept × month → ty_p1, ty_p2 (₹L)
#   MRP split             — effective_shares(): div × dept × mrp × period → contrib%
#   Table / Non-Table %   — store × dept × new MRP × month: its LY sales on the re-apportioned MRPs by display type
#                           (MRP Re-apportionment, the master in use) - no upload (user, 2026-10-14)
#   dt_asp.json           — div × dept × mrp × dt × month → ASP ₹              (user upload, every time)

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
import os, json, datetime, io, sys
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from apportion import SHOWN, split  # noqa: E402

from plan_cache import load_json as _load_plan_json  # noqa: E402
from engines.engine_switch import plan_files  # noqa: E402

router = APIRouter()

_BASE          = os.path.dirname(__file__)
_PARENT        = os.path.join(_BASE, "..")
DT_ASP_PATH     = os.path.join(_PARENT, "dt_asp.json")
DT_RESULT_PATH  = os.path.join(_PARENT, "dt_plan_result.json")
DT_QTY_PATH     = os.path.join(_PARENT, "dt_qty_result.json")

DT_TABLE    = "Table"
DT_NONTABLE = "Non-Table"


def _ts(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _load(path):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None

_ASP_MEM: dict = {}


def load_asp():
    """The ASP master (dt_asp.json), parsed once per file version and kept (user, 2026-10-14: "keep the ASP masters in
    cache do not parse on every run") - re-read only when an Import / Add missing writes the file. Read-only: callers
    must not change what it returns (fill_missing copies before merging)."""
    if not os.path.exists(DT_ASP_PATH):
        return None
    mt = (DT_ASP_PATH, os.path.getmtime(DT_ASP_PATH))
    if _ASP_MEM.get("mt") != mt:
        _ASP_MEM.update(mt=mt, v=_load(DT_ASP_PATH))
    return _ASP_MEM["v"]


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ── helpers ────────────────────────────────────────────────────────────────────

def _month_from_period(period: str) -> str:
    """'Mar'27 P1' → 'Mar'27'"""
    return period.rsplit(" P", 1)[0]

def _derive_months(mrp_plan: dict) -> list[str]:
    """Extract unique months from mrp_plan periods."""
    seen, months = set(), []
    for div in mrp_plan.values():
        for dept in div.values():
            for mrp in dept.values():
                for period in mrp:
                    m = _month_from_period(period)
                    if m not in seen:
                        seen.add(m)
                        months.append(m)
    return months


# ── status ─────────────────────────────────────────────────────────────────────

@router.get("/status")
def status():
    asp     = load_asp()
    # the run times from the files' save times - the run files are ~150-200 MB, parsing them on every page open was the
    # page's wait (user, 2026-10-14: "fix the display type page latency too")
    when = lambda f: datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S") if os.path.exists(f) else None   # noqa: E731
    p_at, q_at = when(DT_RESULT_PATH), when(DT_QTY_PATH)
    try:   # the MRP split every MRP reader uses (mrp_plan.json alone is gone since the re-apportioned shares, 2026-10-14)
        from engines.mrp_plan_engine import effective_shares
        mrp_ok = bool(effective_shares()[0])
    except Exception:   # noqa: BLE001
        mrp_ok = False
    try:
        contrib_ok, contrib_from = True, mix_about()
    except Exception as e:   # noqa: BLE001 - no master / sales yet: the page says why
        contrib_ok, contrib_from = False, str(getattr(e, "detail", e))
    return {
        "dept_plan_ok":    _dept_plan() is not None,
        "mrp_plan_ok":     mrp_ok,
        "contrib_ok":      contrib_ok,
        "contrib_from":    contrib_from,
        "asp_imported":    asp is not None,
        "asp_rows":        asp.get("count", 0) if asp else 0,
        "asp_date":        asp.get("imported_at", "") if asp else "",
        "plan_run":        p_at is not None,
        "plan_date":       p_at or "",
        "qty_run":         q_at is not None,
        "qty_date":        q_at or "",
    }


# ── Table / Non-Table % from the re-apportioned LY sales ───────────────────────
# user, 2026-10-14: "Cont % should be according the Re-apportioned MRPs and their respective Display types % as per LY
# sales. the MRP plan should break and it should be highlighted as per that only" - no contributions upload any more.
# Each store x department x new MRP x plan month splits by its own LY sales on that MRP by display type (the MRP
# Re-apportionment's after side on the master in use, Unmapped left out). Where that store didn't sell the MRP that
# month: its own mix over all the months, then the chain's that month, the chain's over all months, then the
# department's - the first that has sales.
MIX_LEVELS = (("store-month", ["store", "department", "mrp", "month"]),
              ("store", ["store", "department", "mrp"]),
              ("chain-month", ["department", "mrp", "month"]),
              ("chain", ["department", "mrp"]),
              ("department-month", ["department", "month"]),
              ("department", ["department"]))
MIX_NOTE = {"file": "the buyers' plan file's mix (for ASP MAMJ 2.xlsx: the store's cluster, a non-SSG store its reference store's cluster; plan_file_mix)",
            "store-month": "the store's own LY mix of that MRP that month",
            "store": "the store's own LY mix of that MRP over all the months (none sold that month)",
            "chain-month": "the chain's LY mix of that MRP that month (the store didn't sell it)",
            "chain": "the chain's LY mix of that MRP over all the months",
            "department-month": "the department's LY mix that month (no LY on that MRP anywhere)",
            "department": "the department's LY mix over all the months",
            "reference": "its reference department's mix (a new department with no LY of its own, as its MRP split)",
            "none": "no LY sales in the department at all - not split"}
_MIX: dict = {}


def mix_key():
    from engines.mrp_reapportionment_engine import compare_key
    return compare_key()


def mix_about() -> str:
    """Which re-apportionment the split is read from - cheap (no run)."""
    k = mix_key()
    return f"re-apportioned LY sales on {os.path.basename(k[1])}, {k[0][3]} basis"


def _mix_tables() -> dict:
    """LY sales on the new MRPs per store x department x MRP x display x plan month, as % tables per fallback level."""
    from engines.mrp_reapportionment_engine import _compare, _plan_period
    key = mix_key()
    if _MIX.get("key") == key:
        return _MIX["v"]
    # the LY table is kept on disk for the re-apportionment's inputs, so a restart doesn't re-run it (~40 s; 2026-10-14)
    from engines.mrp_reapportionment_engine import OUTPUT_DIR
    path = os.path.join(OUTPUT_DIR, "_display_ly.pkl")
    ga = None   # signed (returns netted) - the MRP Cont % is made on it; the display split takes the positive cells
    try:
        disk = pd.read_pickle(path)   # written below by this server only
        if disk.get("key") == key and "g_all" in disk:
            ga = disk["g_all"]
    except Exception:   # noqa: BLE001 - none yet / unreadable: build it
        pass
    if ga is None:
        c = _compare()
        f = c["flows"]
        f = f[f["new"] != "Unmapped"]
        ga = f.groupby(["store", "department", "new", "display", "month"], as_index=False, sort=False)["v"].sum()
        ga = ga.rename(columns={"new": "mrp"})
        ga["month"] = ga["month"].map({m: _plan_period(m) for m in ga["month"].unique()})
        try:
            pd.to_pickle({"key": key, "g_all": ga}, path)
        except OSError:
            pass
    g = ga[ga["v"] > 0]
    tabs = []
    for name, ks in MIX_LEVELS:
        t = g.groupby(ks + ["display"], as_index=False, sort=False)["v"].sum()
        t["pct"] = t["v"] / t.groupby(ks)["v"].transform("sum") * 100
        tabs.append((name, ks, t[ks + ["display", "pct"]]))
    v = {"tabs": tabs, "displays": sorted(g["display"].unique()), "g_all": ga}   # g_all: the check-up's MRP-mix check
    _MIX.update(key=key, v=v)
    return v


def _ref_stores() -> dict:
    """{store: the like-for-like store its split follows} for the non-SSG stores of the plan in use (dept_sales_engine
    Step 2, 2026-10-14: "their respective ref stores plan cont % can be taken and moved forward on every step")."""
    try:
        from engines.grain_view import _cube
        return {s: x["ref_used"] for s, x in (_cube().get("stores") or {}).items() if not x.get("ssg") and x.get("ref_used")}
    except Exception:   # noqa: BLE001 - no plan: every store on its own mix
        return {}


def display_shares(keys: pd.DataFrame, _ref: bool = True) -> pd.DataFrame:
    """keys: store, department, mrp, month (plan month) -> one row per key x display: + pct (adds to 100 per key) and
    src (the MIX_LEVELS level it came from, or "reference": a new department with no LY takes its reference
    department's mix, as it takes its MRP split - effective_shares). A key with no LY anywhere is not returned.
    A non-SSG store takes its reference store's mix (the store's plan is split by that store at every step)."""
    K = ["store", "department", "mrp", "month"]
    rm = _ref_stores() if _ref else {}
    if rm and keys["store"].isin(list(rm)).any():
        k2 = keys[K].drop_duplicates().assign(_mix=lambda d: d["store"].map(lambda s: rm.get(s, s)))
        sh = _display_shares_own(k2[["_mix", "department", "mrp", "month"]].rename(columns={"_mix": "store"}).drop_duplicates())
        return k2.merge(sh.rename(columns={"store": "_mix"}), on=["_mix", "department", "mrp", "month"]).drop(columns="_mix")
    return _display_shares_own(keys, _ref=_ref)


def _display_shares_own(keys: pd.DataFrame, _ref: bool = True) -> pd.DataFrame:
    K = ["store", "department", "mrp", "month"]
    left = keys[K].drop_duplicates().reset_index(drop=True)
    out = []
    for name, ks, t in _mix_tables()["tabs"]:
        if left.empty:
            break
        hit = left.merge(t, on=ks)
        if len(hit):
            out.append(hit.assign(src=name))
            left = left.merge(hit[K].drop_duplicates(), on=K, how="left", indicator=True)
            left = left[left["_merge"] == "left_only"].drop(columns="_merge")
    if _ref and not left.empty:
        from engines.mrp_plan_engine import effective_shares
        refs = {k.split("|", 1)[-1]: v for k, v in (effective_shares()[1] or {}).items()}
        lr = left[left["department"].isin(refs)]
        if len(lr):
            lr = lr.assign(orig=lr["department"], department=lr["department"].map(refs))
            r = _display_shares_own(lr, _ref=False)
            if len(r):
                r = r.merge(lr[K + ["orig"]], on=K).assign(department=lambda d: d["orig"], src="reference")
                out.append(r.drop(columns="orig"))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=K + ["display", "pct", "src"])


def _asp_key(dept, mrp, dt) -> str:
    """One spelling for the ASP match - department x MRP x display type (department names are unique across
    divisions): case / spaces off, MRP as a whole number (749.0 -> 749), display type as the LY data writes it (Table /
    TABLE -> TABLE, Non-Table / NON TABLE / NON_TABLE -> NON_TABLE) - 2026-10-14."""
    try:
        mrp = str(int(round(float(mrp))))
    except (TypeError, ValueError):
        mrp = str(mrp).strip()
    d = str(dt).strip().upper().replace("-", "_").replace(" ", "_")
    return "|".join((str(dept).strip().upper(), mrp, d))


# ── ASP import / export (user, 2026-10-14: "calculate the ASP for P1 P2 and month wise ASPs too and convert the file
# like that, also remove the extras like sales and qty in the import file so that the preview is all about ASP on
# Company level. Make the template default and start the import and export functionality") ─────────────────────────
# The template (default, what Export gives and Import reads):
#     Division | Department | MRP | Display Type | Mar'27 P1 | Mar'27 P2 | Mar'27 | Apr'27 P1 | ...   (ASP, Rs per piece)
# Import also takes the planners' raw file - CLUSTER TAG | CLUSTER | ATTRIBUTE-1 | DEPARTMENT | ARTICLE NAME | MRP |
# DISPLAY TYPE | <Mon>'yy P1 / P2 VAL (Rs lakh) | ... QTY - and converts it: company level = every cluster, cluster tag,
# attribute and article added up per department x MRP x display type; P1 / P2 ASP = VAL x 1e5 / QTY, the month's ASP =
# (P1 + P2 VAL) / (P1 + P2 QTY), weighted by pieces. Sales and quantity are not kept - only the ASP.
import re  # noqa: E402

_PERIOD = re.compile(r"^([A-Za-z]{3})\s*'?\s*(\d{2})\s*(P[12])?\s*(VAL|QTY|ASP)?(\s*\(.*\))?$", re.I)
_CAL = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _period(col):
    """"MAR'27 P1 VAL" -> ("Mar'27 P1", "VAL"); "Mar'27" -> ("Mar'27", ""); anything else -> (None, None)."""
    m = _PERIOD.match(str(col).strip().replace("\u2019", "'"))
    if not m or m.group(1).title() not in _CAL:
        return None, None
    per = f"{m.group(1).title()}'{m.group(2)}" + (f" {m.group(3).upper()}" if m.group(3) else "")
    return per, (m.group(4) or "").upper()


def _period_key(per: str):
    """Calendar order; within a month P1, P2, then the month itself."""
    mon, _, half = per.partition(" ")
    return (int(mon[-2:]) * 12 + _CAL.index(mon[:3]), half or "P3")


def _plan_divisions() -> dict:
    """{DEPARTMENT: division} from the department plan (for the template's Division column)."""
    out = {}
    for sd in ((_dept_plan() or {}).get("stores") or {}).values():
        for dv, dd in (sd.get("divisions") or {}).items():
            for md in (dd.get("months") or {}).values():
                for dp in (md.get("departments") or {}):
                    out.setdefault(str(dp).upper(), dv)
    return out


def _col(df, *names):
    up = {str(c).strip().upper(): c for c in df.columns}
    return next((up[n] for n in names if n in up), None)


def _onto_new_mrps(base: pd.DataFrame, nums: pd.DataFrame, df: pd.DataFrame) -> tuple:
    """The raw file's value and pieces carried onto the new MRPs through the MRP master in use (user, 2026-10-14: "carry
    the ASP onto the new MRPs through the master") - the MRP Re-apportionment's own rule (_redistribute): a listed MRP
    moves 100% to its new MRP; a discontinued one splits to the nearest listed MRP below / above (Summer 60 / 40, others
    40 / 60, by the row's ATTRIBUTE-1); value and pieces split alike, so a new MRP's ASP = the piece-weighted mix of the
    old MRPs it took. An MRP the master doesn't list for its Department x Display is treated as the sales are
    (_expand_listed): listed to itself when it is one of the new MRPs there, else discontinued. A Department x Display
    the master doesn't cover keeps its own MRPs. Returns ({(dept, new mrp, display): sums}, how-it-went text)."""
    import numpy as np
    from engines.mrp_reapportionment_engine import _load_mapping, _redistribute, _find_mapping_file
    mp = _load_mapping()
    c_attr = _col(df, "ATTRIBUTE-1", "ATTRIBUTE1", "ATTRIBUTE")
    c_store = _col(df, "CLUSTER", "STORE")
    cols = [f"c{i}" for i in range(nums.shape[1])]
    s = pd.DataFrame({"STORE": df.loc[base.index, c_store].astype(str).to_numpy() if c_store else "ALL", "DIVISION": "",
                      "DEPARTMENT": base["dept"].to_numpy(), "MRP": base["mrp"].round().astype(int).to_numpy(),
                      "DISPLAY": base["dt"].to_numpy(),
                      "ATTRIBUTE": df.loc[base.index, c_attr].astype(str).str.strip().str.upper().to_numpy() if c_attr else ""})
    s[cols] = nums.to_numpy()
    k = (s[["DEPARTMENT", "DISPLAY", "MRP"]].drop_duplicates().rename(columns={"MRP": "MRP_CURRENT"})
         .merge(mp[["DEPARTMENT", "DISPLAY"]].drop_duplicates(), on=["DEPARTMENT", "DISPLAY"])
         .merge(mp[["DEPARTMENT", "DISPLAY", "MRP_CURRENT"]], how="left", indicator=True))
    k = k[k["_merge"] == "left_only"].drop(columns="_merge")
    newm = (mp.loc[mp["MRP_LISTED"] > 0, ["DEPARTMENT", "DISPLAY", "MRP_LISTED"]].drop_duplicates()
            .rename(columns={"MRP_LISTED": "MRP_CURRENT"}).assign(_n=1))
    k = k.merge(newm, how="left")
    k["MRP_LISTED"] = np.where(k["_n"].eq(1), k["MRP_CURRENT"], 0).astype(int)
    mp2 = pd.concat([mp, k[["DEPARTMENT", "DISPLAY", "MRP_CURRENT", "MRP_LISTED"]]], ignore_index=True)
    out, unm, _ = _redistribute(s, mp2, cols)
    moved = out.rename(columns={"LISTED_MRP": "mrp"})[["DEPARTMENT", "mrp", "DISPLAY"] + cols]
    kept = unm.rename(columns={"MRP_CURRENT": "mrp"})[["DEPARTMENT", "mrp", "DISPLAY"] + cols] if len(unm) else moved.iloc[:0]
    g = (pd.concat([moved, kept], ignore_index=True).rename(columns={"DEPARTMENT": "dept", "DISPLAY": "dt"})
         .groupby(["dept", "mrp", "dt"], sort=True)[cols].sum())
    g.columns = list(nums.columns)
    nv = len([c for c in cols[: len(cols) // 2]])
    vtot = float(nums.iloc[:, :nv].to_numpy().sum())
    vk = float(kept[cols[:nv]].to_numpy().sum()) if len(kept) else 0.0
    how = (f"carried onto the new MRPs through {os.path.basename(_find_mapping_file() or '')} "
           f"({int((out['SHARE_PCT'] >= 100).sum()):,} moved whole, {int((out['SHARE_PCT'] < 100).sum()):,} split parts"
           + (f"; ₹{vk:,.1f} L of ₹{vtot:,.1f} L value kept on its own MRP - Department × Display not in the master" if vk > 1e-6 else "") + ")")
    return g, how


def asp_from_frame(df: pd.DataFrame) -> tuple:
    """The raw VAL / QTY file or the ASP template -> ({key: record}, periods, level). record = {division, dept, mrp,
    display_type, months: {"Mar'27 P1": ASP, "Mar'27 P2": ASP, "Mar'27": ASP}} (division names from the plan)."""
    c_dept = _col(df, "DEPARTMENT", "DEPT")
    c_mrp = _col(df, "MRP", "FINAL MRP")
    c_dt = _col(df, "DISPLAY TYPE", "DISPLAY_TYPE", "UDF-06", "UDF06", "TYPE", "DT")
    if not (c_dept and c_mrp and c_dt):
        raise HTTPException(400, f"Need Department, MRP and Display Type columns. Got: {list(df.columns)}")
    kinds = {c: _period(c) for c in df.columns}
    val = {pp: c for c, (pp, k) in kinds.items() if k == "VAL"}
    qty = {pp: c for c, (pp, k) in kinds.items() if k == "QTY"}
    divs = _plan_divisions()
    base = pd.DataFrame({"dept": df[c_dept].astype(str).str.strip().str.upper(),
                         "mrp": pd.to_numeric(df[c_mrp], errors="coerce"),
                         "dt": df[c_dt].astype(str).str.strip().str.upper().str.replace("-", "_").str.replace(" ", "_")})
    # the planners' own new MRP / display type, when the file gives them (for ASP MAMJ 2.xlsx: NEW MRP, NEW DISPLAY
    # TYPE beside the old ones, 2026-10-14) - then the ASP is priced on them directly, not carried through the master
    c_nmrp, c_ndt = _col(df, "NEW MRP"), _col(df, "NEW DISPLAY TYPE")
    if c_nmrp:
        nm = pd.to_numeric(df[c_nmrp], errors="coerce")
        base["mrp"] = nm.where(nm > 0, base["mrp"])
        if c_ndt:
            nd = df[c_ndt].astype(str).str.strip().str.upper().str.replace("-", "_").str.replace(" ", "_")
            base["dt"] = nd.where(~nd.isin(["", "NAN", "NONE"]), base["dt"])
    base = base[base["dept"].ne("") & base["dept"].ne("NAN") & base["mrp"].notna()]
    out = {}
    if val and qty:   # the raw file: company-level ASP from value and pieces
        halves = sorted((pp for pp in val if pp in qty), key=_period_key)
        nums = df.loc[base.index, [val[pp] for pp in halves] + [qty[pp] for pp in halves]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        if c_nmrp:
            g = pd.concat([base, nums], axis=1).groupby(["dept", "mrp", "dt"], sort=True)[list(nums.columns)].sum()
            how = "priced on the file's own NEW MRP / NEW DISPLAY TYPE"
        else:
            g, how = _onto_new_mrps(base, nums, df)
        months = []
        for pp in halves:
            if pp.split(" ")[0] not in months:
                months.append(pp.split(" ")[0])
        periods = [x for mon in months for x in [h for h in halves if h.startswith(mon + " ")] + [mon]]
        for (dp, mr, dt), r in g.iterrows():
            ms = {}
            for mon in months:
                hs = [x for x in halves if x.startswith(mon + " ")]
                for x in hs:
                    v, q = r[val[x]], r[qty[x]]
                    ms[x] = round(v * 1e5 / q, 4) if q > 0 else None
                V, Q = sum(r[val[x]] for x in hs), sum(r[qty[x]] for x in hs)
                ms[mon] = round(V * 1e5 / Q, 4) if Q > 0 else None
            out[_asp_key(dp, mr, dt)] = {"division": divs.get(dp, ""), "dept": dp, "mrp": str(int(mr)), "display_type": dt, "months": ms}
        return out, periods, f"company, converted from VAL / QTY - {how}"
    # the ASP template (or the older month-only layout)
    pcs = sorted(((c, pp) for c, (pp, k) in kinds.items() if pp and k in ("", "ASP")), key=lambda x: _period_key(x[1]))
    if not pcs:
        raise HTTPException(400, "No period columns - expected Mar'27 P1 / Mar'27 P2 / Mar'27 ... (ASP) or ... VAL / ... QTY")
    periods = [pp for _, pp in pcs]
    for i, r in base.iterrows():
        ms = {}
        for c, pp in pcs:
            v = pd.to_numeric(df.at[i, c], errors="coerce")
            ms[pp] = float(v) if v == v and v > 0 else None
        for mon in {pp.split(" ")[0] for pp in periods if " " in pp}:   # a month column left out: P1 / P2 average
            if mon not in ms:
                h = [x for x in (ms.get(f"{mon} P1"), ms.get(f"{mon} P2")) if x]
                ms[mon] = sum(h) / len(h) if h else None
        out[_asp_key(r["dept"], r["mrp"], r["dt"])] = {"division": divs.get(r["dept"], ""), "dept": r["dept"],
                                                      "mrp": str(int(r["mrp"])), "display_type": r["dt"], "months": ms}
    if any(" " in pp for pp in periods):
        mons = []
        for pp in periods:
            if pp.split(" ")[0] not in mons:
                mons.append(pp.split(" ")[0])
        periods = [x for mon in mons for x in (f"{mon} P1", f"{mon} P2", mon)]
    return out, periods, "company (template)"


def fill_missing(cur: dict, records: dict, periods: list, source: str, level: str) -> tuple:
    """Pure. The ASP in use + a second file, only where the first has nothing (user, 2026-10-14: "add the ASPs from this
    file for missing entries"): a Department x MRP x Display Type it lacks is added whole; one it has gets only its
    empty periods. Nothing it has is overwritten. -> (merged dt_asp.json content, rows added, periods filled)."""
    data = {k: {**v, "months": dict(v["months"])} for k, v in cur["data"].items()}
    added = filled = 0
    for k, rec in records.items():
        if k not in data:
            if any(v for v in rec["months"].values()):
                data[k] = {**rec, "from": source}
                added += 1
            continue
        for pp, v in rec["months"].items():
            if v and not data[k]["months"].get(pp):
                data[k]["months"][pp] = v
                data[k].setdefault("filled", {})[pp] = source
                filled += 1
    pers = list(cur.get("months") or [])
    pers += [pp for pp in periods if pp not in pers]
    pers.sort(key=_period_key)
    out = {**cur, "imported_at": _ts(), "count": len(data), "months": pers, "data": data,
           "source": f"{cur.get('source')} + missing from {source}",
           "level": f"{cur.get('level', '')}; missing entries from {source} ({level})"}
    return out, added, filled


@router.post("/import/asp")
async def import_asp(file: UploadFile = File(...), mode: str = "replace"):
    """mode=replace: the file is the ASP master; mode=fill: it only fills what the ASP in use lacks (fill_missing)."""
    raw = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(raw)) if not file.filename.endswith(".csv") else pd.read_csv(io.BytesIO(raw))
        df.columns = [str(c).strip() for c in df.columns]
    except Exception as e:
        raise HTTPException(400, f"Parse error: {e}")
    records, periods, level = asp_from_frame(df)
    if not records:
        raise HTTPException(400, "No ASP rows in the file")
    cur = load_asp()
    if mode == "fill" and cur:
        out, added, filled = fill_missing(cur, records, periods, file.filename, level)
        _save(DT_ASP_PATH, out)
        return {"ok": True, "rows": out["count"], "added": added, "filled": filled, "months": out["months"], "level": out["level"]}
    out = {"imported_at": _ts(), "source": file.filename, "count": len(records), "level": level,
           "months": periods, "data": records}
    _save(DT_ASP_PATH, out)
    return {"ok": True, "rows": len(records), "months": periods, "level": level}


@router.post("/import/plan-file")
async def import_plan_file(file: UploadFile = File(...)):
    """The buyers' plan file (CLUSTER TAG | CLUSTER | ... | NEW MRP | NEW DISPLAY TYPE | NEW ARTICLE NAME | <Mon>'yy P1 / P2
    VAL / QTY; user 2026-10-15: 'keep "for ASP MAMJ 2.xlsx" as sole ASP file and the file for which plan should be matched
    on MRP and ART & UDF level'): one upload is both the sole ASP master (VAL / QTY on its new MRP / display type) and
    the plan's article x MRP x display mix (plan_file_mix). Run Display Type + Qty after it."""
    from engines import plan_file_mix as pfm
    raw = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(raw)) if not file.filename.endswith(".csv") else pd.read_csv(io.BytesIO(raw))
        df.columns = [str(c).strip() for c in df.columns]
        mix = pfm.build(df, file.filename)
    except Exception as e:   # noqa: BLE001
        raise HTTPException(400, f"Parse error: {e}")
    records, periods, level = asp_from_frame(df)
    if not records or not mix["mix"]:
        raise HTTPException(400, "No ASP / like-for-like rows in the file")
    _save(DT_ASP_PATH, {"imported_at": _ts(), "source": f"{file.filename} (sole ASP file)", "count": len(records),
                        "level": level, "months": periods, "data": records})
    pfm.save(mix)
    return {"ok": True, "asp_rows": len(records), "departments": len(mix["mix"].get(pfm.CHAIN, {})),
            "clusters": len(mix["mix"]) - 1, "periods": mix["periods"]}


@router.get("/export/article-plan")
def export_article_plan():
    """The department plan down to article x MRP x display type at the plan file's grain (plan_file_mix.article_plan)."""
    from engines import plan_file_mix as pfm
    ap = pfm.article_plan(_dept_plan() or {"stores": {}})
    if ap is None:
        raise HTTPException(404, "No buyers' plan file imported (Display Type - import plan file)")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        ap.sort_values(["Group", "Cluster", "Department", "Article", "MRP", "Display type", "Month", "Half"]).to_excel(
            xw, sheet_name="Article plan", index=False)
        xw.sheets["Article plan"].set_column(0, 9, 16)
        xw.sheets["Article plan"].freeze_panes(1, 0)
    from fastapi.responses import Response
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Article plan.xlsx"'})


_OTHER_DT = {"TABLE": "NON_TABLE", "NON_TABLE": "TABLE"}


def asp_lookup(data: dict, dept, mrp, dt, month) -> tuple:
    """(ASP, how) of a department x MRP x display type x month - its own ASP, else the same department x MRP x month's
    ASP on the other display type (user, 2026-10-14: "use the other display type ASP as fallback"); (None, None) when
    neither has one. how = "own" | "other display type"."""
    a = ((data.get(_asp_key(dept, mrp, dt)) or {}).get("months") or {}).get(month)
    if a:
        return a, "own"
    o = _OTHER_DT.get(str(dt).strip().upper().replace("-", "_").replace(" ", "_"))
    b = ((data.get(_asp_key(dept, mrp, o)) or {}).get("months") or {}).get(month) if o else None
    return (b, "other display type") if b else (None, None)


@router.get("/asp")
def get_asp_preview():
    """The ASP in use, as the preview shows it (company level, Rs per piece)."""
    a = load_asp()
    if not a:
        raise HTTPException(404, "No ASP imported yet")
    def mk(r):
        try:
            return float(r["mrp"])
        except (TypeError, ValueError):
            return 0.0
    rows = sorted(a["data"].values(), key=lambda r: (r.get("division", ""), r["dept"], mk(r), r["display_type"]))
    return {"imported_at": a.get("imported_at"), "source": a.get("source"), "level": a.get("level", ""),
            "periods": a.get("months", []), "rows": rows}


def asp_template_frame() -> tuple:
    """(DataFrame in the template layout, filled?) - the ASP in use, else a blank template of every department x MRP x
    display type the plan splits into (the MRP split x the LY display types), on the plan's periods."""
    a = load_asp()
    if a:
        periods = a.get("months") or []
        rows = [{"Division": r.get("division", ""), "Department": r["dept"], "MRP": int(float(r["mrp"])),
                 "Display Type": r["display_type"], **{pp: r["months"].get(pp) for pp in periods}} for r in a["data"].values()]
        return pd.DataFrame(rows).sort_values(["Division", "Department", "MRP", "Display Type"]), True
    from engines.mrp_plan_engine import effective_shares
    sh = effective_shares()[0] or {}
    mons = _derive_months(sh) if sh else []
    periods = [x for mon in mons for x in (f"{mon} P1", f"{mon} P2", mon)]
    try:
        chain = next(t for name, _, t in _mix_tables()["tabs"] if name == "chain")
        dts = chain.groupby(["department", "mrp"])["display"].apply(sorted).to_dict()
    except Exception:   # noqa: BLE001 - no re-apportionment: both display types on every MRP
        dts = {}
    rows = []
    for dv, deps in sh.items():
        for dp, bands in deps.items():
            for mr in sorted(bands, key=lambda x: float(x)):
                for dt in dts.get((dp, mr), ["NON_TABLE", "TABLE"]):
                    rows.append({"Division": dv, "Department": dp, "MRP": int(float(mr)), "Display Type": dt, **{pp: None for pp in periods}})
    return pd.DataFrame(rows, columns=["Division", "Department", "MRP", "Display Type"] + periods), False


def asp_xlsx(df: pd.DataFrame, filled: bool) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        df.to_excel(xw, index=False, sheet_name="ASP")
        ws, wb = xw.sheets["ASP"], xw.book
        ws.freeze_panes(1, 4)
        ws.set_column(0, 0, 10)
        ws.set_column(1, 1, 28)
        ws.set_column(2, 3, 12)
        num = wb.add_format({"num_format": "#,##0.00"})
        mon = wb.add_format({"num_format": "#,##0.00", "bold": True, "bg_color": "#EEF4F0"})
        for j, c in enumerate(df.columns[4:], 4):
            ws.set_column(j, j, 11, num if " " in str(c) else mon)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)
        nb = wb.add_worksheet("How to fill")
        nb.set_column(0, 0, 120)
        for i, t in enumerate([
            "ASP template - company level (every cluster and article added up), Rs per piece.",
            "Division | Department | MRP | Display Type, then per month: <Mon>'yy P1 (days 1-15), <Mon>'yy P2 (16th to month end), <Mon>'yy (the month).",
            "The month's ASP = (P1 + P2 value) / (P1 + P2 pieces). If you leave a month column out, Import takes the P1 / P2 average.",
            "Import also takes the raw planning file (CLUSTER ... DISPLAY TYPE, <Mon>'yy P1 VAL / QTY): it is converted to this layout on import.",
            "Qty Run uses the month's ASP of each Department x MRP x Display Type.",
            "Filled from the ASP in use." if filled else "Blank: no ASP imported yet - rows are the plan's Department x MRP x Display Type."]):
            nb.write(i, 0, t)
    return buf.getvalue()


@router.get("/export/asp")
def export_asp():
    """The ASP template - the ASP in use, or blank on the plan's department x MRP x display type rows."""
    df, filled = asp_template_frame()
    return StreamingResponse(io.BytesIO(asp_xlsx(df, filled)),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="ASP template.xlsx"'})


# ── run plan ───────────────────────────────────────────────────────────────────

def _dept_plan():
    """The latest department plan - corrected first, like every other engine (was the uncorrected plan only)."""
    for f in plan_files():   # minus a switched-off correction (2026-10-14)
        d = _load_plan_json(os.path.join(_PARENT, f))
        if d:
            return d
    return None


@router.get("/run-plan")
def run_plan():
    fp      = _dept_plan()
    from engines.mrp_plan_engine import effective_shares   # the same MRP split as MRP Output (2026-10-13)
    mrp_raw = effective_shares()[0] or None   # the buyers' split, or the promoted Article Name one
    if not fp:      raise HTTPException(400, "final_dept_plan not found")
    if not mrp_raw: raise HTTPException(400, "No MRP split - MRP Plan · Buyer's Input")

    months = _derive_months(mrp_raw)
    # the buyers' plan file's departments (plan_file_mix, user 2026-10-15): each half split over MRP x display type by the
    # file's mix of the store's cluster (a non-SSG store: its reference store's) - the same split as the Final Results trees
    from engines import plan_file_mix as pfm
    fdep = pfm.departments()
    mk_of = pfm.store_keys(fp["stores"]) if fdep else {}
    frows = []

    rows = []
    for store, sr in fp["stores"].items():
        # every planned store (2026-10-14: was the like-for-like stores only) - a non-SSG store's Table / Non-Table %
        # is its reference store's (display_shares)
        ssg = bool(sr.get("is_ssg"))
        divs = sr.get("divisions", {})
        for div, div_data in divs.items():
            if div not in mrp_raw: continue
            # 2026-09-30: this looped over the division's keys ("months") instead of its months - no rows were made
            for month, month_data in div_data.get("months", {}).items():
                if month not in months: continue   # a month with no MRP shares has nothing to split by
                depts_data = month_data.get("departments", {})
                for dept, dept_rec in depts_data.items():
                    if not dept_rec.get("active", True): continue   # inactive (e.g. off season): plan 0, nothing to split (2026-10-14)
                    if dept in fdep:
                        mk = mk_of.get(store, pfm.CHAIN)
                        ty_p1, ty_p2 = dept_rec.get("ty_p1", 0.0), dept_rec.get("ty_p2", 0.0)
                        if not ssg and not (ty_p1 or ty_p2): continue
                        h1, h2 = pfm.md_shares(mk, dept, f"{month} P1"), pfm.md_shares(mk, dept, f"{month} P2")
                        if h1 and h2:
                            cells = {}   # MRP -> display -> plan (each half x its own share)
                            for hv, hs in ((ty_p1, h1), (ty_p2, h2)):
                                for (m, dsp), w in hs.items():
                                    c_ = cells.setdefault(m, {})
                                    c_[dsp] = c_.get(dsp, 0.0) + hv * w
                            for m, dd in cells.items():
                                t, n = dd.get("TABLE", 0.0), dd.get("NON_TABLE", 0.0)
                                frows.append({"store": store, "division": div, "dept": dept, "mrp": m, "month": month,
                                              "ty_p1": ty_p1, "ty_p2": ty_p2, "mrp_plan": t + n,
                                              "table_contrib": t / (t + n) * 100 if t + n else 0.0,
                                              "nontable_contrib": n / (t + n) * 100 if t + n else 0.0,
                                              "table_plan": t, "nontable_plan": n, "has_contrib": True, "contrib_from": "file"})
                            continue
                    if dept not in mrp_raw.get(div, {}): continue
                    mrp_dept = mrp_raw[div][dept]
                    ty_p1 = dept_rec.get("ty_p1", 0.0)
                    ty_p2 = dept_rec.get("ty_p2", 0.0)
                    if not ssg and not (ty_p1 or ty_p2): continue   # a non-SSG store with no plan here: no rows
                    # each half split over the MRPs by its share - the MRPs add back to the department exactly
                    s1 = split(ty_p1, {m: pm.get(f"{month} P1", 0.0) for m, pm in mrp_dept.items()})
                    s2 = split(ty_p2, {m: pm.get(f"{month} P2", 0.0) for m, pm in mrp_dept.items()})

                    for mrp_str in mrp_dept:
                        rows.append({
                            "store": store, "division": div, "dept": dept, "mrp": mrp_str,
                            "month": month,
                            "ty_p1": ty_p1, "ty_p2": ty_p2,
                            "mrp_plan": s1[mrp_str] + s2[mrp_str],
                        })

    # Table / Non-Table % of each row from the re-apportioned LY sales (2026-10-14); they add back to the MRP plan exactly
    try:
        sh = display_shares(pd.DataFrame({"store": [r["store"] for r in rows], "department": [r["dept"] for r in rows],
                                          "mrp": [r["mrp"] for r in rows], "month": [r["month"] for r in rows]}))
    except HTTPException as e:
        raise HTTPException(409, f"Table / Non-Table % come from the MRP Re-apportionment: {e.detail}")
    pv = {}
    for st, dp, mr, mo, d, pc, src in sh[["store", "department", "mrp", "month", "display", "pct", "src"]].itertuples(index=False):
        pv.setdefault((st, dp, mr, mo), {"src": src})[d] = pc
    for r in rows:
        c = pv.get((r["store"], r["dept"], r["mrp"], r["month"]), {})
        tbl_pct, ntbl_pct = c.get("TABLE", 0.0), c.get("NON_TABLE", 0.0)
        dt = split(r["mrp_plan"], {"t": tbl_pct, "n": ntbl_pct})
        r.update(table_contrib=tbl_pct, nontable_contrib=ntbl_pct, table_plan=dt["t"], nontable_plan=dt["n"],
                 has_contrib=(tbl_pct + ntbl_pct) > 0, contrib_from=c.get("src", "none"))
    rows += frows

    out = {"run_at": _ts(), "months": months, "rows": rows, "contrib_from": mix_about()
           + (f"; the {len(fdep)} departments of the buyers' plan file by its mix ({(pfm.load() or {}).get('source')})" if fdep else "")}
    _save(DT_RESULT_PATH, out)
    return {"ok": True, "rows": len(rows), "months": months}


@router.get("/result")
def get_result():
    d = _load(DT_RESULT_PATH)
    if not d: raise HTTPException(404, "Plan not run yet")
    return d


# ── validate ───────────────────────────────────────────────────────────────────

@router.get("/validate")
def validate():
    result = _load(DT_RESULT_PATH)
    if not result: raise HTTPException(400, "Run plan first")

    rows = result["rows"]
    anomalies = []
    TOLS = SHOWN  # any gap that shows at 8 decimals (was 0.001 L)

    # Index by (store, div, dept, mrp, month)
    by_key: dict = {}
    for r in rows:
        k = (r["store"], r["division"], r["dept"], r["mrp"], r["month"])
        by_key[k] = r

    # 1. Display Type → MRP: table+nontable should equal mrp_plan (within tolerance)
    #    Also: missing contribution
    for r in rows:
        dt_sum = r["table_plan"] + r["nontable_plan"]
        gap    = abs(dt_sum - r["mrp_plan"])
        if not r["has_contrib"]:
            anomalies.append({
                "level": "Display Type → MRP",
                "severity": "error",
                "store": r["store"], "division": r["division"],
                "dept": r["dept"], "mrp": r["mrp"], "month": r["month"],
                "expected": round(r["mrp_plan"], 4), "actual": 0.0,
                "gap": round(r["mrp_plan"], 4),
                "message": (
                    f"{r['dept']} has no LY sales on the re-apportioned MRPs at all, so "
                    f"{r['store']} / MRP ₹{r['mrp']} in {r['month']} has no Table / Non-Table split - "
                    f"₹{r['mrp_plan']:.2f}L is unallocated."
                ),
            })
        elif gap > TOLS:
            contrib_sum = r["table_contrib"] + r["nontable_contrib"]
            anomalies.append({
                "level": "Display Type → MRP",
                "severity": "error",
                "store": r["store"], "division": r["division"],
                "dept": r["dept"], "mrp": r["mrp"], "month": r["month"],
                "expected": round(r["mrp_plan"], 4), "actual": round(dt_sum, 4),
                "gap": round(dt_sum - r["mrp_plan"], 4),
                "message": (
                    f"{r['store']} / {r['dept']} / MRP ₹{r['mrp']} / {r['month']}: "
                    f"Display Type plans sum to ₹{dt_sum:.4f}L but MRP plan is ₹{r['mrp_plan']:.4f}L. "
                    f"Contribution totals {contrib_sum:.1f}% — "
                    f"{'remaining ' + str(round(100 - contrib_sum, 1)) + '% unallocated' if contrib_sum < 100 else 'over-allocated by ' + str(round(contrib_sum - 100, 1)) + '%'}."
                ),
            })

    # 3. MRP → Dept check per store × month
    from collections import defaultdict
    mrp_by_dept: dict = defaultdict(float)
    dept_ty: dict     = defaultdict(float)
    for r in rows:
        dk = (r["store"], r["division"], r["dept"], r["month"])
        mrp_by_dept[dk] += r["mrp_plan"]
        dept_ty[dk]      = r["ty_p1"] + r["ty_p2"]

    for dk, mrp_sum in mrp_by_dept.items():
        store, div, dept, month = dk
        ty = dept_ty[dk]
        gap = abs(mrp_sum - ty)
        if gap > TOLS and ty > 0:
            anomalies.append({
                "level": "MRP → Department",
                "severity": "error",
                "store": store, "division": div, "dept": dept, "mrp": "ALL", "month": month,
                "expected": ty, "actual": mrp_sum,
                "gap": mrp_sum - ty,
                "message": (
                    f"{dept} in {store} / {month}: no MRP shares for this month in the MRP plan - "
                    f"₹{ty:.8f}L is not split to MRPs. Add its MRP shares." if mrp_sum == 0 else
                    f"{dept} in {store} / {month}: MRP plans total ₹{mrp_sum:.8f}L "
                    f"vs department plan ₹{ty:.8f}L (gap ₹{mrp_sum - ty:+.8f}L)."
                ),
            })

    # 4. Dept → Division check per store × month
    dept_sum_by_div: dict = defaultdict(float)
    div_ty: dict          = defaultdict(float)
    fp = _dept_plan()
    if fp:
        for store, sr in fp["stores"].items():
            for div, div_data in sr.get("divisions", {}).items():
                for month, mdata in div_data.get("months", {}).items():
                    div_ty[(store, div, month)] = mdata.get("div_total_ty", 0.0)
    for r in rows:
        dept_sum_by_div[(r["store"], r["division"], r["month"])] += r["mrp_plan"]
    for dk, dept_sum in dept_sum_by_div.items():
        store, div, month = dk
        div_total = div_ty.get(dk, 0.0)
        gap = abs(dept_sum - div_total)
        if gap > TOLS and div_total > 0:
            anomalies.append({
                "level": "Department → Division",
                "severity": "warning",
                "store": store, "division": div, "dept": "ALL", "mrp": "ALL", "month": month,
                "expected": div_total, "actual": dept_sum,
                "gap": dept_sum - div_total,
                "message": (
                    f"{div} in {store} / {month}: departments split to MRPs total ₹{dept_sum:.8f}L "
                    f"vs division plan ₹{div_total:.8f}L ({(dept_sum/div_total - 1)*100:+.2f}%) - "
                    f"departments with no MRP shares in the MRP plan are not split."
                ),
            })

    errors   = [a for a in anomalies if a["severity"] == "error"]
    warnings = [a for a in anomalies if a["severity"] == "warning"]

    summary = {
        "validated_at": _ts(),
        "total": len(anomalies),
        "errors": len(errors),
        "warnings": len(warnings),
        "gate_open": len(errors) == 0,
        "anomalies": anomalies,
    }
    return summary


# ── run qty ────────────────────────────────────────────────────────────────────

@router.get("/run-qty")
def run_qty():
    result = _load(DT_RESULT_PATH)
    asp    = load_asp()
    if not result: raise HTTPException(400, "Run plan first")
    if not asp:    raise HTTPException(400, "ASP not imported")

    asp_data = asp["data"]

    def get_asp(div, dept, mrp, dt, month):
        return asp_lookup(asp_data, dept, mrp, dt, month)[0] or 0.0

    qty_rows = []
    missing_asp = []
    for r in result["rows"]:
        div   = r["division"]
        dept  = r["dept"]
        mrp   = r["mrp"]
        month = r["month"]

        t_asp  = get_asp(div, dept, mrp, DT_TABLE,    month)
        nt_asp = get_asp(div, dept, mrp, DT_NONTABLE, month)

        def to_qty(plan_l, asp_val):
            if asp_val and asp_val > 0:
                return round(plan_l * 1e5 / asp_val, 0)
            return None

        t_qty  = to_qty(r["table_plan"],    t_asp)
        nt_qty = to_qty(r["nontable_plan"], nt_asp)

        # only a value that is projected needs a qty (2026-10-14: a display type with no plan there isn't "missing")
        if t_qty is None and r["table_plan"] > 1e-9:
            missing_asp.append({"store": r["store"], "dept": dept, "mrp": mrp, "dt": DT_TABLE, "month": month})
        if nt_qty is None and r["nontable_plan"] > 1e-9:
            missing_asp.append({"store": r["store"], "dept": dept, "mrp": mrp, "dt": DT_NONTABLE, "month": month})

        qty_rows.append({**r,
            "table_asp":  t_asp,  "table_qty":  t_qty,
            "nontable_asp": nt_asp, "nontable_qty": nt_qty,
        })

    out = {"run_at": _ts(), "months": result["months"], "rows": qty_rows, "missing_asp": missing_asp}
    _save(DT_QTY_PATH, out)
    return {"ok": True, "rows": len(qty_rows), "missing_asp": len(missing_asp)}


_QV: dict = {}
QV_COLS = ["store", "division", "dept", "mrp", "month", "table_contrib", "nontable_contrib", "mrp_plan", "table_plan",
           "nontable_plan", "table_asp", "table_qty", "nontable_asp", "nontable_qty", "has_contrib", "contrib_from"]


def _qty_frame():
    """The Qty run as a table, read once per run file version and kept (memory, and a pickle beside the file for after
    a restart) - the page asks for a filtered slice of it, not the ~200 MB file (2026-10-14 latency)."""
    if not os.path.exists(DT_QTY_PATH):
        return None
    mt = os.path.getmtime(DT_QTY_PATH)
    if _QV.get("mt") == mt:
        return _QV["v"]
    pk = DT_QTY_PATH[:-5] + ".view.pkl"
    v = None
    try:
        disk = pd.read_pickle(pk)   # written below by this server only
        if disk.get("mt") == mt and disk.get("cols") == QV_COLS:   # a cache with other columns is rebuilt
            v = disk["v"]
    except Exception:   # noqa: BLE001 - none yet: build it
        pass
    if v is None:
        q = _load(DT_QTY_PATH) or {}
        df = pd.DataFrame(q.get("rows", []))
        for c in QV_COLS:
            if c not in df.columns:
                df[c] = None
        df = df[QV_COLS]
        for c in ("store", "division", "dept", "mrp", "month"):
            df[c] = df[c].astype(str).astype("category")
        miss = sum(1 for m in q.get("missing_asp", []))
        v = {"df": df, "months": q.get("months", []), "run_at": q.get("run_at"), "missing": miss}
        try:
            pd.to_pickle({"mt": mt, "cols": QV_COLS, "v": v}, pk)
        except OSError:
            pass
    _QV.update(mt=mt, v=v)
    return v


@router.get("/qty-view")
def get_qty_view(month: str = "", store: str = "ALL", division: str = "ALL", dept: str = "ALL", limit: int = 500):
    """One month's slice of the Qty run inside the filters: up to `limit` rows (largest MRP plan first), the totals of all
    of them, and the filter choices - what the Qty tab shows."""
    v = _qty_frame()
    if not v:
        raise HTTPException(404, "Qty not run yet")
    df = v["df"]
    m = month if month in set(v["months"]) else (v["months"][0] if v["months"] else "")
    sel = df[df["month"] == m]
    for c, val in (("store", store), ("division", division), ("dept", dept)):
        if val and val != "ALL":
            sel = sel[sel[c] == val]
    num = lambda c: float(pd.to_numeric(sel[c], errors="coerce").fillna(0).sum())   # noqa: E731
    top = sel.assign(_p=pd.to_numeric(sel["mrp_plan"], errors="coerce")).sort_values("_p", ascending=False).head(max(1, min(limit, 5000)))
    rows = top.drop(columns="_p").astype(object).where(top.drop(columns="_p").notna(), None).to_dict("records")
    opt = lambda c, d: sorted(d[c].astype(str).unique().tolist())   # noqa: E731
    base = df[df["month"] == m]
    return {"run_at": v["run_at"], "months": v["months"], "month": m, "rows": rows, "total_rows": int(len(sel)),
            "totals": {"mrp_plan": num("mrp_plan"), "table_plan": num("table_plan"), "nontable_plan": num("nontable_plan"),
                       "table_qty": num("table_qty"), "nontable_qty": num("nontable_qty")},
            "missing_asp": v["missing"],
            "stores": opt("store", base), "divisions": opt("division", base),
            "depts": opt("dept", base if division in ("", "ALL") else base[base["division"] == division])}


@router.get("/qty-result")
def get_qty():
    d = _load(DT_QTY_PATH)
    if not d: raise HTTPException(404, "Qty not run yet")
    return d


# ── export ─────────────────────────────────────────────────────────────────────

@router.get("/export")
def export(format: str = "csv", division: str = "", group: str = "", store: str = ""):
    """Every field from the store to the display type and qty, one row per store x department x MRP x month (user,
    2026-10-14: "all the fields availble for export till display type so that the user can easily export the report for
    fact finding") - engines/journey.export_rows. CSV by default (the full run is ~700k rows); format=xlsx up to an Excel
    sheet's limit (filter by division / store group / store). Filters take comma-separated values."""
    from engines.journey import export_bytes
    data, ext, n = export_bytes(format, division=division, group=group, store=store)
    tag = "-".join(x for x in (division, group, store) if x).replace(",", "+") or "all stores"
    return StreamingResponse(io.BytesIO(data), media_type="text/csv" if ext == "csv" else
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="Plan to UDF - {tag} - {_ts()[:10]}.{ext}"',
                                      "X-Rows": str(n)})


@router.get("/journey/options")
def get_journey_options(store: str = "", dept: str = ""):
    """The Journey page's pickers: planned stores (group), the store's departments, months, the department's MRPs."""
    from engines.journey import options
    return options(store, dept)


@router.get("/journey/export")
def get_journey_export(store: str, dept: str, month: str, mrp: str = "", display: str = ""):
    """The journey on screen as an Excel file in plain words, plus every MRP of the department to UDF."""
    from engines.journey import journey_xlsx
    from urllib.parse import quote
    data, name = journey_xlsx(store, dept, month, mrp, display)
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@router.get("/journey")
def get_journey(store: str, dept: str, month: str, mrp: str = "", display: str = ""):
    """How one store x department x month (x MRP x display type) is made, step by step down to qty - engines/journey."""
    from engines.journey import journey
    return journey(store, dept, month, mrp, display)
