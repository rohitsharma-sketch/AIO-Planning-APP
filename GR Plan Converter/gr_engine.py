"""Growth vs LY converter (user, 2026-10-02: "design a convertor ... input old data and the final sales plan it can
plot the data against ly according to the hierarchy given in the sales plan") - the GR % PLAN - 3.9.26 layout.

LY = the data lake's day-wise sales (the single latest export, rs_common.lake_files), per Store x Department, value in
lakhs (SL_V / 1e5) and qty (SL_Q), for the same months a year earlier. A plan month split into P1 / P2 is split the
same way last year: P1 = day 1 to the middle day (15th of a 31-day month, 14th of Feb), P2 = the rest - this
reproduces the 3.9.26 workbook's LY row for row (Jan 98%, Feb 99%; the rest are departments since split in the lake).
"""
import calendar
import hashlib
import os
import pickle
import re
from datetime import datetime

import numpy as np
import pandas as pd

LAKE = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw"
DAYWISE = os.path.join(LAKE, "rs_19_to_26_day_wise_sales_data_compiled")
STORE, DIV, DEPT = "Store Name", "DIVISION", "DEPARTMENT"   # the plan's columns once read by the Re-Aligner's importer
LABEL = re.compile(r"^([A-Z][a-z]{2})'(\d{2})(?: (P[12]))?$")


def ly_label(m):
    """Plan month -> the same month last year: "Sep'26" -> "Sep'25", "Jan'27 P1" -> "Jan'26 P1"."""
    mon, yy, half = LABEL.match(m).groups()
    return f"{mon}'{int(yy) - 1:02d}" + (f" {half}" if half else "")


def _month(m):
    """ "Jan'26 P1" -> (1, 2026, "P1")."""
    mon, yy, half = LABEL.match(m).groups()
    return datetime.strptime(mon, "%b").month, 2000 + int(yy), half


def blocks(months):
    """The plan's months grouped by calendar year, named by their initials: Sep'26..Feb'27 P2 -> SOND, JF."""
    out = []
    for m in months:
        y = _month(m)[1]
        if not out or out[-1][0] != y:
            out.append((y, []))
        out[-1][1].append(m)
    return [("".join(dict.fromkeys(m[0] for m in ms)), ms) for _, ms in out]


def load_ly(months, cache_dir, path=None):
    """-> (DataFrame indexed (Store Name, DEPARTMENT) with "<LY month>" value (lakhs) and "<LY month> Q" qty, info).
    Cached on disk per (lake file, its mtime, months): reading the day-wise file over the network takes ~1.5 min."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    if path is None:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        from rs_common.lake_files import latest_path
        path = latest_path(DAYWISE) if os.path.isdir(DAYWISE) else None
    if not path:
        raise FileNotFoundError("The data lake's day-wise sales can't be read - it is reachable only on the office LAN.")
    lm = [ly_label(m) for m in months]
    key = hashlib.md5(f"v2|{path}|{os.path.getmtime(path)}|{'|'.join(lm)}".encode()).hexdigest()[:16]
    cache = os.path.join(cache_dir, f"ly_{key}.pkl")
    info = {"file": os.path.basename(path), "months": lm,
            "exported": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d %b %Y %H:%M")}
    if os.path.exists(cache):
        with open(cache, "rb") as fh:
            return pickle.load(fh), dict(info, cached=True)
    span = [_month(m)[:2] for m in lm]
    lo = min(datetime(y, mo, 1) for mo, y in span)
    hi_mo, hi_y = max(span, key=lambda x: (x[1], x[0]))
    hi = datetime(hi_y + (hi_mo == 12), hi_mo % 12 + 1, 1)
    df = ds.dataset(path).to_table(columns=["STORE_NAME", "DIVISION", "DEPARTMENT", "ATTRIBUTE1", "BILLDATE", "SL_V", "SL_Q"],
                                   filter=(pc.field("BILLDATE") >= lo) & (pc.field("BILLDATE") < hi)).to_pandas()
    for c in ("STORE_NAME", "DIVISION", "DEPARTMENT", "ATTRIBUTE1"):   # one space, as the plan reader writes names
        df[c] = df[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()   # (2026-10-02: KI_AP_BABA SUIT NEW BORN  F/S)
    d = df.pop("BILLDATE")
    mo, yr, day = d.dt.month.to_numpy(), d.dt.year.to_numpy(), d.dt.day.to_numpy()
    lab = pd.Series(d.dt.strftime("%b'%y").to_numpy(), index=df.index)
    for hm, hy in {(m_, y_) for m_, y_, h in (_month(m) for m in lm) if h}:   # P1 = days 1..middle (Jan 15, Feb 14)
        on = (mo == hm) & (yr == hy)
        lab[on] = lab[on] + np.where(day[on] <= calendar.monthrange(hy, hm)[1] // 2, " P1", " P2")
    df["M"] = lab.to_numpy()
    g = df[df["M"].isin(lm)].groupby(["STORE_NAME", "DEPARTMENT", "M"])[["SL_V", "SL_Q"]].sum()
    v = (g["SL_V"].unstack("M") / 1e5).reindex(columns=lm).fillna(0.0)
    q = g["SL_Q"].unstack("M").reindex(columns=lm).fillna(0.0)
    q.columns = [c + " Q" for c in lm]
    ly = pd.concat([v, q], axis=1)
    ly.index.names = [STORE, DEPT]
    meta = df.groupby("DEPARTMENT")[["DIVISION", "ATTRIBUTE1"]].first()   # the lake's division / attribute of a department
    ly["_DIV"] = ly.index.get_level_values(1).map(meta["DIVISION"])
    ly["_ATTR"] = ly.index.get_level_values(1).map(meta["ATTRIBUTE1"])
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache + ".tmp", "wb") as fh:
        pickle.dump(ly, fh)
    os.replace(cache + ".tmp", cache)
    return ly, dict(info, cached=False)


def _col(df, *names):
    """The plan's column for any of these header spellings (case / space insensitive), or None."""
    want = {" ".join(n.split()).upper() for n in names}
    return next((c for c in df.columns if " ".join(str(c).split()).upper() in want), None)


def _growth(ty, ly):
    ty, ly = np.asarray(ty, float), np.asarray(ly, float)
    return np.divide(ty - ly, ly, out=np.full(len(ly), np.nan), where=np.abs(ly) > 1e-12)


def build_main(plan, months, ly):
    """The MAIN sheet: one row per Store x Department of the plan, plus every department of the plan's divisions its
    stores sold last year but have no plan for (TY 0 - user, 2026-10-02: LY must be the whole of last year, e.g.
    LW_U_T-TOP F/S, KB_BABA SUIT DNM F/S, which the final plan dropped), with the plan's hierarchy - Division, ST TAG,
    Attribute (the lake's for a department the plan doesn't have), SSG TAG - then TY value,
    TY qty, LY value, LY qty by month, each with its block (SOND / JF) and season totals, and growth % per block and
    season (TY / LY - 1)."""
    st_tag, ssg, attr = _col(plan, "ST TAG"), _col(plan, "SSG TAG"), _col(plan, "ATTRIBUTE")
    V = [m + " Plan" for m in months]
    Q = [m + " Plan Qty" for m in months if m + " Plan Qty" in plan.columns]
    ty = plan.groupby([STORE, DEPT])[V + Q].sum()
    divs = set(plan[DIV])
    in_div = ly["_DIV"].isin(divs).to_numpy() if "_DIV" in ly else ly.index.get_level_values(1).isin(set(plan[DEPT]))
    lyk = ly[ly.index.get_level_values(0).isin(set(plan[STORE])) & in_div]
    idx = ty.index.union(lyk.index)
    ty, lyk = ty.reindex(idx).fillna(0.0), lyk.reindex(idx).fillna(0.0)
    first = lambda by, c: plan.groupby(by)[c].agg(lambda x: x.dropna().astype(str).mode().iat[0] if x.notna().any() else "")
    s, d = idx.get_level_values(0), idx.get_level_values(1)
    lake = ly.groupby(level=1)[["_DIV", "_ATTR"]].first() if "_DIV" in ly else pd.DataFrame(columns=["_DIV", "_ATTR"])
    div = pd.Series(d.map(first(DEPT, DIV))).fillna(pd.Series(d.map(lake["_DIV"]))).fillna("").to_numpy()
    att = (pd.Series(d.map(first(DEPT, attr))) if attr else pd.Series([np.nan] * len(d))).fillna(pd.Series(d.map(lake["_ATTR"]))).fillna("").to_numpy()
    out = {"Div Conc": s + div, "Dep Conc": s + d, "Division": div, "STORE NAME": s, "DEPARTMENT": d,
           "ST TAG": s.map(first(STORE, st_tag)) if st_tag else "", "ATTRIBUTE": att,
           "SSG TAG": s.map(first(STORE, ssg)) if ssg else ""}
    lm = [ly_label(m) for m in months]
    bl = blocks(months)
    zero = np.zeros(len(idx))
    for what, cols, vals in (
            ("Val TY", months, [ty[m + " Plan"].to_numpy() for m in months]),
            ("Qty TY", [m + " Q" for m in months], [ty[m + " Plan Qty"].to_numpy() if m + " Plan Qty" in ty else zero for m in months]),
            ("Val LY", lm, [lyk[m].to_numpy() if m in lyk else zero for m in lm]),   # LY rows not sold: 0
            ("Qty LY", [m + " Q" for m in lm], [lyk[m + " Q"].to_numpy() if m + " Q" in lyk else zero for m in lm])):
        out.update(zip(cols, vals))
        for name, ms in bl:
            out[f"TTL {name} {what}"] = sum(vals[months.index(m)] for m in ms)
        out[f"TTL {what}"] = sum(vals)
    for name, _ in bl:
        out[f"{name} Growth % Val"] = _growth(out[f"TTL {name} Val TY"], out[f"TTL {name} Val LY"])
    out["TTL Growth % Val"] = _growth(out["TTL Val TY"], out["TTL Val LY"])
    return pd.DataFrame(out).sort_values(["Division", "STORE NAME", "DEPARTMENT"]).reset_index(drop=True)


def pivot(main, months, tags=None):
    """Division -> Attribute -> Department (the plan's hierarchy) over the stores whose SSG TAG is in `tags` (None =
    every store): TY, LY and growth % per month, block and season, then the grand total."""
    m = main if not tags else main[main["SSG TAG"].isin(tags)]
    lm = [ly_label(x) for x in months]
    bl = blocks(months)
    val = months + lm + [f"TTL {b} Val {w}" for b, _ in bl for w in ("TY", "LY")] + ["TTL Val TY", "TTL Val LY"]
    parts = []
    for div, gd in m.groupby("Division", sort=True):
        parts.append({"Level": "Division", "Division": div, "ATTRIBUTE": "", "DEPARTMENT": "", **gd[val].sum()})
        for at, ga in gd.groupby("ATTRIBUTE", sort=True):
            parts.append({"Level": "Attribute", "Division": div, "ATTRIBUTE": at, "DEPARTMENT": "", **ga[val].sum()})
            for dp, gp in ga.groupby("DEPARTMENT", sort=True):
                parts.append({"Level": "Department", "Division": div, "ATTRIBUTE": at, "DEPARTMENT": dp, **gp[val].sum()})
    parts.append({"Level": "Grand Total", "Division": "", "ATTRIBUTE": "", "DEPARTMENT": "", **m[val].sum()})
    p = pd.DataFrame(parts, columns=["Level", "Division", "ATTRIBUTE", "DEPARTMENT", *val])
    for t, l in zip(months, lm):
        p[f"{t} Growth %"] = _growth(p[t], p[l])
    for b, _ in bl:
        p[f"{b} Growth %"] = _growth(p[f"TTL {b} Val TY"], p[f"TTL {b} Val LY"])
    p["TTL Growth %"] = _growth(p["TTL Val TY"], p["TTL Val LY"])
    return p
