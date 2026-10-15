"""The buyers' plan file as the plan's MRP x Article x UDF mix (user, 2026-10-15: 'keep "for ASP MAMJ 2.xlsx" as sole ASP
file and the file for which plan should be matched on MRP and ART & UDF level. match it and stitch the department progress
with it'; choices: the department plan stays ours (BIS buyer growth = the colleague's sheet), and "stores should take their
respective ref stores and in case of clusters they should take it from their respective reference clusters").

The file (CLUSTER TAG | CLUSTER | ATTRIBUTE-1 | DEPARTMENT | ARTICLE NAME | MRP | DISPLAY TYPE | ... | NEW MRP | NEW DISPLAY
TYPE | NEW ARTICLE NAME | <Mon>'yy P1 / P2 VAL | ... QTY) is kept as values per SSG cluster x department x half-month x
(new article, new MRP, new display type) - its like-for-like rows; the NSO / OTHER rows follow no store tag of ours, so a
non-SSG store takes its reference store's cluster (its plan already follows that store, rule P6). Read as shares:
    a store's mix   = its cluster's (SSG) or its reference store's cluster's (non-SSG), else the chain's (all SSG clusters)
    a department    = the file's departments; one the file doesn't have keeps the MRP Cont % / LY display mix as before
The department plan x these shares -> MRP (per half), display type and article - the same in the Final Results MRP / Display
trees (grain_view), the Display Type run (display_type_engine.run_plan) and the chain MRP split (mrp_plan_engine.effective_shares).
Stored in SalesPlan/backend/plan_file_mix.json (business data, gitignored). Rule book: docs/business-rules/RULE_BOOK.md M4."""
import datetime
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
FILE_MIX_PATH = os.path.join(_HERE, "..", "plan_file_mix.json")
CHAIN = "*"   # the chain's mix (all SSG clusters together), for a store with no cluster mix
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_mem: dict = {}


def _key(art, mrp, disp) -> str:
    return f"{art}|{mrp}|{disp}"


def split_key(k: str) -> tuple:
    a, m, d = k.rsplit("|", 2)
    return a, m, d


def build(df, source: str) -> dict:
    """Pure. The file's frame -> {source, imported_at, periods, mix: {CLUSTER: {DEPT: {"Mar'27 P1": {"ART|MRP|DISP":
    Rs L}}}}} from its SSG rows, plus the chain (CHAIN) = every SSG cluster added up. Values <= 0 left out."""
    import re
    up = {str(c).strip().upper(): c for c in df.columns}
    col = lambda *n: next((up[x] for x in n if x in up), None)   # noqa: E731
    c_tag, c_cl, c_dp = col("CLUSTER TAG"), col("CLUSTER"), col("DEPARTMENT")
    c_art, c_mrp, c_dt = col("NEW ARTICLE NAME", "ARTICLE NAME"), col("NEW MRP", "MRP"), col("NEW DISPLAY TYPE", "DISPLAY TYPE")
    miss = [n for n, c in (("CLUSTER TAG", c_tag), ("CLUSTER", c_cl), ("DEPARTMENT", c_dp), ("ARTICLE NAME", c_art),
                           ("MRP", c_mrp), ("DISPLAY TYPE", c_dt)) if c is None]
    if miss:
        raise ValueError(f"missing column(s): {', '.join(miss)}")
    pat = re.compile(r"^([A-Z]{3})'(\d{2}) (P[12]) VAL$")
    per = {}
    for u, c in up.items():
        m = pat.match(u)
        if m:
            per[c] = f"{m.group(1).title()}'{m.group(2)} {m.group(3)}"
    if not per:
        raise ValueError("no <Mon>'yy P1 / P2 VAL columns")
    mix = {}
    ssg = df[df[c_tag].astype(str).str.strip().str.upper() == "SSG"]
    for _, rr in ssg.iterrows():
        cl, dp = str(rr[c_cl]).strip().upper(), str(rr[c_dp]).strip()
        try:
            mrp = str(int(float(rr[c_mrp])))
        except (TypeError, ValueError):
            continue
        k = _key(str(rr[c_art]).strip(), mrp, str(rr[c_dt]).strip().upper())
        for c, p in per.items():
            v = rr[c]
            v = float(v) if v is not None and v == v else 0.0
            if v <= 0:
                continue
            for cc in (cl, CHAIN):
                cell_ = mix.setdefault(cc, {}).setdefault(dp, {}).setdefault(p, {})
                cell_[k] = cell_.get(k, 0.0) + v
    periods = sorted(set(per.values()), key=lambda s: (s[4:6], _MON.index(s[:3]), s[-2:]))
    return {"source": source, "imported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "periods": periods,
            "mix": mix}


def save(d: dict):
    from plan_cache import save_json
    save_json(FILE_MIX_PATH, d)
    _mem.clear()


def load() -> dict | None:
    """The stored file mix, or None (no file imported: the engines split as before)."""
    try:
        mt = os.path.getmtime(FILE_MIX_PATH)
    except OSError:
        return None
    if _mem.get("mt") != mt:
        with open(FILE_MIX_PATH, encoding="utf-8") as fh:
            _mem.update(mt=mt, v=json.load(fh))
    return _mem["v"]


def departments() -> set:
    d = load()
    return set(((d or {}).get("mix") or {}).get(CHAIN, {})) if d else set()


def store_keys(stores: dict) -> dict:
    """{store: the cluster whose mix it takes}: an SSG store its own cluster, a non-SSG store its reference store's
    cluster (the like-for-like store its plan follows), else its own; CHAIN where the file has no such cluster.
    stores = {store: {"cluster", "is_ssg" / "ssg", optional "ref_used"}} - the plan's or the Final Results cube's store
    records (the cube's carry ref_used, the like-for-like store a non-SSG store's plan follows)."""
    d = load() or {}
    have = set(d.get("mix") or {})
    refs = {s: v["ref_used"] for s, v in stores.items() if (v or {}).get("ref_used")}
    if not refs:
        try:
            from engines.display_type_engine import _ref_stores
            refs = _ref_stores()
        except Exception:   # noqa: BLE001
            refs = {}
    cl = {s: str((v or {}).get("cluster") or "").strip().upper() for s, v in stores.items()}
    out = {}
    for s, v in stores.items():
        ssg = (v or {}).get("is_ssg", (v or {}).get("ssg"))
        r = refs.get(s)
        c = cl.get(r) if (not ssg and r in cl) else cl.get(s)
        out[s] = c if c in have else CHAIN
    return out


def cell(mk: str, dept: str, period: str) -> dict | None:
    """{"ART|MRP|DISP": share} adding to 1 for one mix x department x period ("Mar'27 P1", or "Mar'27" = both halves),
    the chain's where the cluster has none; None when the file has nothing for the department then."""
    d = load()
    if not d:
        return None
    mix = d["mix"]

    def raw(c):
        x = (mix.get(c) or {}).get(dept) or {}
        if " " in period:
            return x.get(period)
        out = {}
        for h in ("P1", "P2"):
            for k, v in (x.get(f"{period} {h}") or {}).items():
                out[k] = out.get(k, 0.0) + v
        return out or None

    v = raw(mk) or raw(CHAIN)
    if not v:
        return None
    t = sum(v.values())
    return {k: x / t for k, x in v.items()} if t > 0 else None


def mrp_shares(mk: str, dept: str, period: str) -> dict | None:
    """{MRP: share} (the file's articles and display types added up)."""
    c = cell(mk, dept, period)
    if not c:
        return None
    out = {}
    for k, v in c.items():
        _, m, _ = split_key(k)
        out[m] = out.get(m, 0.0) + v
    return out


_cache: dict = {}


def md_shares(mk: str, dept: str, period: str) -> dict:
    """{(MRP, DISPLAY): share} of one mix x department x half (articles added up); {} when the file has none."""
    ck = ("md", (load() or {}).get("imported_at"), mk, dept, period)
    if ck not in _cache:
        out = {}
        for k, v in (cell(mk, dept, period) or {}).items():
            _, m, dsp = split_key(k)
            out[(m, dsp)] = out.get((m, dsp), 0.0) + v
        _cache[ck] = out
    return _cache[ck]


def art_shares(mk: str, dept: str, period: str, mrp: str, disp: str) -> dict:
    """{ARTICLE: share} inside one MRP x display type of a mix x department x half."""
    c = cell(mk, dept, period) or {}
    out = {}
    for k, v in c.items():
        a, m, dsp = split_key(k)
        if m == mrp and dsp == disp:
            out[a] = out.get(a, 0.0) + v
    t = sum(out.values())
    return {a: v / t for a, v in out.items()} if t > 0 else {}


def display_table():
    """pandas DataFrame mk, department, month ("Mar'27 P1"), mrp, display, pct - each display type's % of its MRP in
    that mix x department x half (what the Display tree splits the file's departments by); None without a file."""
    d = load()
    if not d:
        return None
    ck = ("dt", d.get("imported_at"))
    if ck not in _cache:
        import pandas as pd
        rows = []
        for mk in d["mix"]:
            for dp in d["mix"][CHAIN]:
                for p in d["periods"]:
                    md = md_shares(mk, dp, p)
                    tot = {}
                    for (m, _), v in md.items():
                        tot[m] = tot.get(m, 0.0) + v
                    for (m, dsp), v in md.items():
                        if tot[m] > 0:
                            rows.append((mk, dp, p, m, dsp, v / tot[m] * 100.0))
        _cache[ck] = pd.DataFrame(rows, columns=["mk", "department", "month", "mrp", "display", "pct"])
    return _cache[ck]


def article_plan(plan: dict):
    """pandas DataFrame - the department plan down to article: each store x file department x half's plan (ty_p1 / ty_p2)
    x the file's ART x MRP x DISPLAY share of the store's mix, added up by the store's own cluster x group (SSG / NSO /
    Others) x department x article x MRP x display type x month x half (Rs L). The file's grain, so it compares with it
    line by line; None without a file."""
    d = load()
    if not d:
        return None
    import pandas as pd
    fdep = departments()
    mk_of = store_keys(plan["stores"])
    acc = {}
    for s, sr in plan["stores"].items():
        cl = str(sr.get("cluster") or "").strip().upper()
        grp = sr.get("group") or ("SSG" if sr.get("is_ssg") else "NSO")
        mk = mk_of.get(s, CHAIN)
        for dv, dd in (sr.get("divisions") or {}).items():
            for m, md in (dd.get("months") or {}).items():
                for dp, x in (md.get("departments") or {}).items():
                    if dp not in fdep or not x.get("active"):
                        continue
                    for h, ty in (("P1", x.get("ty_p1", 0.0)), ("P2", x.get("ty_p2", 0.0))):
                        if not ty:
                            continue
                        for k, w in (cell(mk, dp, f"{m} {h}") or {}).items():
                            a, mr, dsp = split_key(k)
                            kk = (cl, grp, dv, dp, a, mr, dsp, m, h)
                            acc[kk] = acc.get(kk, 0.0) + ty * w
    return pd.DataFrame([(*k, v) for k, v in acc.items()],
                        columns=["Cluster", "Group", "Division", "Department", "Article", "MRP", "Display type", "Month", "Half", "Plan (Rs L)"])


def chain_mrp_pct(divisions: dict) -> dict:
    """{div: {dept: {MRP: {"Mar'27 P1": %}}}} - the chain's MRP split from the file, in effective_shares' shape."""
    d = load()
    if not d:
        return {}
    out = {}
    for dp, pers in (d["mix"].get(CHAIN) or {}).items():
        dv = divisions.get(dp.upper())
        if not dv:
            continue
        for p in pers:
            for m, s in (mrp_shares(CHAIN, dp, p) or {}).items():
                out.setdefault(dv, {}).setdefault(dp, {}).setdefault(m, {})[p] = s * 100.0
    return out


if __name__ == "__main__":   # python engines/plan_file_mix.py - the share rules
    import pandas as pd
    df = pd.DataFrame({"CLUSTER TAG": ["SSG", "SSG", "NSO"], "CLUSTER": ["A", "A", "A"], "DEPARTMENT": ["D", "D", "D"],
                       "NEW ARTICLE NAME": ["x", "y", "x"], "NEW MRP": [299, 399, 299], "NEW DISPLAY TYPE": ["TABLE", "NON_TABLE", "TABLE"],
                       "MAR'27 P1 VAL": [3.0, 1.0, 50.0], "MAR'27 P2 VAL": [1.0, 1.0, 50.0]})
    b = build(df, "test")
    assert b["mix"]["A"]["D"]["Mar'27 P1"] == {"x|299|TABLE": 3.0, "y|399|NON_TABLE": 1.0}   # NSO rows left out
    _mem.update(mt=0, v=b)
    load = lambda: _mem["v"]   # noqa: E731
    assert cell("A", "D", "Mar'27 P1") == {"x|299|TABLE": 0.75, "y|399|NON_TABLE": 0.25}
    assert cell("A", "D", "Mar'27") == {"x|299|TABLE": 4 / 6, "y|399|NON_TABLE": 2 / 6}
    assert cell("Z", "D", "Mar'27 P1") == cell(CHAIN, "D", "Mar'27 P1")
    assert mrp_shares("A", "D", "Mar'27 P2") == {"299": 0.5, "399": 0.5}
    print("ok")
