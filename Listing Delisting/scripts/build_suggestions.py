"""
Season windows, festival windows and like-for-like delist / relist suggestions
-> app/windows.json + app/suggestions.json      (replaces build_risk_scores.py / risk.json, 2026-09-26)

User rule (2026-09-26): no suggestion may be driven by a festive period or any other surge, and two
different windows (a summer department's Mar-Jun in-season vs its Oct-Jan off-season) are never compared
with each other. Every number is analysed on calendar DATES and must trace back to its source.

1. Festival days, per store, on dates: the Calendar app's Festival Master (calendar.cluster_profile_festivals:
   each cluster's festivals + Pre/Core/Post days) placed on each year's date from
   calendar.festival_reference_dates (Bihu = 14 April when missing - the user's fixed-date rule);
   store -> cluster from calendar.store_calendar_clusters. A store with no cluster gets every cluster's
   festival days (conservative: more days left out, never a festival day left in).
2. Store "open days" = days the store sold anything (so closures, renovations and pre-opening days never
   count as zero-sales days). Every rate below is SL_V per festival-free open store-day.
3. Season windows per season category (ATTRIBUTE1, via seasonality.json; missing = regular): each calendar
   month's festival-free rate vs the category's own yearly average, full years 2022-2025, averaged ->
   in-season (index >= IN_AT), off-season (<= OFF_AT), normal (between).
4. Delist: a store x dept listed through its latest window (>= MIN_DAYS days, the most recent run of one
   window type) whose festival-free rate there is <= DELIST_AT of the SAME dates in earlier years it was
   selling, AND worse than the same department's other stores in its cluster over the same dates
   (relative <= REL_AT) - a store-specific fall, not a department-wide or regional dip. A window only counts
   when the store traded on >= COVER of its festival-free days and had been open >= 12 months before it
   began (a new store's launch surge is never a benchmark). An
   off-season read is HELD, not suggested, when the department's in-season starts within LOOKAHEAD days.
5. Relist: a delisted store x dept whose department's in-season (or normal) window starts within
   LOOKAHEAD days, and which the last time it sold in that window sold at >= RELIST_AT of its cluster
   peers' median rate there. Expected sales = its own rate that time x the window's festival-free days,
   plus its festival days at the department's own festival lift.
Every row carries the exact dates, days, sums and years used; windows.json holds the festival and season
windows, per-department window benchmarks + festival lift, and a day-wise vs month-wise reconciliation.
Usage: python build_suggestions.py
"""
import datetime
import functools
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import BASE, planning_session  # noqa: E402
from build_daily import CACHE  # noqa: E402

APP = os.path.join(BASE, "app")
YEARS = [2022, 2023, 2024, 2025]          # full benchmark years (the day-wise cache starts 2022-01-01)
IN_AT, OFF_AT = 1.15, 0.85                # season-window index cut-offs
MIN_DAYS, MAX_DAYS = 21, 90               # a window run must have >= 21 days; evaluate at most the last 90
DELIST_AT, REL_AT = 0.5, 0.6              # <= 50% of its own same-window benchmark AND <= 60% of its peers' change
MIN_BENCH_MONTHLY = 2000                  # benchmark must be worth >= Rs 2,000 a month (noise floor, as before)
MIN_PEERS = 3
MATURE_DAYS = 365                         # ...and had been open >= 12 months before that window began
COVER = 0.7                               # a store must have traded on >= 70% of a window's festival-free days
LOOKAHEAD, RELIST_AT, MIN_RELIST_VALUE = 75, 0.8, 10000
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
EPOCH = datetime.date(1970, 1, 1)
day_date = lambda n: EPOCH + datetime.timedelta(days=int(n))
iso = lambda n: str(day_date(n))
ordn = lambda d: (d - EPOCH).days
r2 = lambda v: round(float(v), 2)


def shift_years(day, k):
    """Epoch day -> the same date k years earlier (29 Feb -> 28 Feb)."""
    d = day_date(day)
    try:
        return ordn(d.replace(year=d.year - k))
    except ValueError:
        return ordn(d.replace(year=d.year - k, day=28))


def festival_windows():
    """-> ({cluster: {day: festival}}, [window rows for windows.json], store -> cluster, source notes)."""
    from sqlalchemy import text
    with planning_session() as s:
        prof = s.execute(text("SELECT p.name, f.name, f.pre, f.core, f.post FROM calendar.cluster_profile_festivals f "
                              "JOIN calendar.cluster_profiles p ON p.id = f.cluster_profile_id")).fetchall()
        ref = s.execute(text("SELECT festival, year, date, source FROM calendar.festival_reference_dates")).fetchall()
        store_cl = dict(s.execute(text("SELECT store_id, cluster_name FROM calendar.store_calendar_clusters")).fetchall())
    dates = {(f, y): (d, src) for f, y, d, src in ref}
    days, rows, missing = {}, [], set()
    for cl, fest, pre, core, post in prof:
        for y in range(YEARS[0], datetime.date.today().year + 2):
            d, src = dates.get((fest, y), (None, None))
            if d is None and fest == "Bihu":
                d, src = datetime.date(y, 4, 14), "fixed 14 April (user rule)"
            if d is None:
                missing.add(f"{fest} {y}")
                continue
            a, b = ordn(d) - pre, ordn(d) + core + post - 1
            rows.append({"cluster": cl, "festival": fest, "year": y, "date": str(d), "from": iso(a), "to": iso(b),
                         "pre": pre, "core": core, "post": post, "date_source": src})
            for n in range(a, b + 1):
                days.setdefault(cl, {}).setdefault(n, fest)
    days["ALL"] = {n: f for cl in list(days) for n, f in days[cl].items()}
    notes = {"festival_master": "calendar.cluster_profile_festivals", "dates": "calendar.festival_reference_dates",
             "store_clusters": "calendar.store_calendar_clusters", "clusters": sorted(k for k in days if k != "ALL"),
             "stores_mapped": len(store_cl), "missing_dates": sorted(missing),
             "unmapped_rule": "a store with no calendar cluster gets every cluster's festival days"}
    return days, rows, store_cl, notes


def build():
    t0 = time.time()
    trace_daily = json.loads(pq.read_schema(CACHE).metadata[b"trace"])
    d = pd.read_parquet(CACHE)
    kb = json.load(open(os.path.join(APP, "kb.json"), encoding="utf-8"))
    store_master = json.load(open(os.path.join(APP, "stores.json"), encoding="utf-8")).get("stores", {})
    seas = json.load(open(os.path.join(APP, "seasonality.json"), encoding="utf-8"))
    cat_of = {k: (v.get("season_category") or "regular") for k, v in seas["departments"].items()}
    fdays, fest_rows, store_cl, cal_notes = festival_windows()

    d["day"] = d["BILLDATE"].values.astype("datetime64[D]").astype(np.int64)
    d["cl"] = d["STORE_NAME"].map(lambda s: store_cl.get(s, "ALL"))
    fest = np.empty(len(d), dtype=object)
    for cl, ix in d.groupby("cl").indices.items():
        fest[ix] = pd.Series(d["day"].to_numpy()[ix]).map(fdays.get(cl, {})).fillna("").to_numpy()
    d["fest"] = fest
    dt = pd.to_datetime(d["day"], unit="D")
    d["y"], d["m"] = dt.dt.year.to_numpy(), dt.dt.month.to_numpy()
    d["cat"] = d["DEPARTMENT"].map(cat_of).fillna("regular")
    A = int(d["day"].max())                        # anchor: last day in the day-wise export
    print(f"loaded {len(d):,} rows, anchor {iso(A)} ({time.time() - t0:.0f}s)", flush=True)

    # open store-days (a day the store sold anything), festival flag per the store's cluster
    od = d.drop_duplicates(["STORE_NAME", "day"])[["STORE_NAME", "day", "cl", "fest", "y", "m"]]
    od_nf = od[od["fest"] == ""]
    # a benchmark / evidence window counts only once the store had traded 12 months before it began - a
    # new store's launch surge is a surge, not a like-for-like base. Opening date: the store master
    # (stores.json, planning DB), else the store's first trading day in the day-wise export.
    first_day = od.groupby("STORE_NAME")["day"].min()
    opened = {k: ordn(datetime.date.fromisoformat(v["opened"][:10])) for k, v in store_master.items() if v.get("opened")}
    mature = lambda st, a: opened.get(st, int(first_day.get(st, 0))) <= a - MATURE_DAYS
    days_ym = od_nf.groupby(["y", "m", "STORE_NAME"]).size()           # festival-free open days per store-month
    dym = {k: g.droplevel([0, 1]) for k, g in days_ym.groupby(level=[0, 1])}

    def open_days(a, b):
        return od_nf[(od_nf["day"] >= a) & (od_nf["day"] <= b)].groupby("STORE_NAME").size()

    @functools.lru_cache(maxsize=None)
    def nf_cal(cl, a, b):
        """Festival-free calendar days of cluster `cl` in [a, b]."""
        fd = fdays.get(cl, {})
        return sum(1 for n in range(a, b + 1) if n not in fd)

    nf = d[d["fest"] == ""]
    full = nf[nf["y"].isin(YEARS)]

    # ---- season windows per category (chain-wide, festival-free)
    all_days = od_nf[od_nf["y"].isin(YEARS)].groupby(["y", "m"]).size()
    cats = {}
    for cat, g in full.groupby("cat"):
        rate = (g.groupby(["y", "m"])["SL_V"].sum() / all_days).unstack().reindex(columns=range(1, 13)).fillna(0.0)
        idx = rate.div(rate.mean(axis=1).replace(0, np.nan), axis=0).mean(axis=0)
        typ = ["in" if v >= IN_AT else "off" if v <= OFF_AT else "normal" for v in idx]
        cats[cat] = {"index": {MON[i]: r2(idx.iloc[i]) for i in range(12)}, "type": {MON[i]: typ[i] for i in range(12)},
                     "years": [int(y) for y in rate.index]}
    for cat in set(cat_of.values()) | {"regular"}:
        cats.setdefault(cat, {"index": {m: 1.0 for m in MON}, "type": {m: "normal" for m in MON}, "years": []})
    type_on = lambda cat, n: cats[cat]["type"][MON[day_date(n).month - 1]]

    def run_back(cat, end):
        """The run of one window type ending at `end`, walking back (<= MAX_DAYS)."""
        t, a = type_on(cat, end), end
        while end - a + 1 < MAX_DAYS and type_on(cat, a - 1) == t:
            a -= 1
        return a, end, t

    def run_fwd(cat, start):
        t, b = type_on(cat, start), start
        while b - start + 1 < MAX_DAYS and type_on(cat, b + 1) == t:
            b += 1
        return start, b, t

    windows_now = {}
    for cat in cats:
        a, b, t = run_back(cat, A)
        cur_len = b - a + 1
        if cur_len < MIN_DAYS:                       # the current window just started: judge the one before it
            a, b, t = run_back(cat, a - 1)
        n0 = A + 1
        while n0 - A <= 366 and type_on(cat, n0) == type_on(cat, A):
            n0 += 1
        nxt = run_fwd(cat, n0)
        s = A + 1                                    # relist target: the in-season now/next, else a normal window now
        while s - A <= LOOKAHEAD and type_on(cat, s) != "in":
            s += 1
        tgt = run_fwd(cat, s) if s - A <= LOOKAHEAD else run_fwd(cat, A + 1)
        if tgt[1] - tgt[0] + 1 < MIN_DAYS:           # only a few days of it left: the window after, if it starts soon
            s = tgt[1] + 1
            tgt = run_fwd(cat, s) if s - A <= LOOKAHEAD else None
        if tgt and tgt[2] == "off":
            tgt = None
        windows_now[cat] = {"evaluate": {"from": iso(a), "to": iso(b), "type": t, "_a": a, "_b": b},
                            "current": {"type": type_on(cat, A), "days_so_far": cur_len},
                            "next": {"from": iso(nxt[0]), "to": iso(nxt[1]), "type": nxt[2]},
                            "relist_target": tgt and {"from": iso(tgt[0]), "to": iso(tgt[1]), "type": tgt[2], "_a": tgt[0], "_b": tgt[1]}}

    # ---- listing status (kb.json)
    kb_ix = {m[:6]: i for i, m in enumerate(kb["months"])}
    last_i = len(kb["months"]) - 1
    flags = lambda s, dep: (kb["data"].get(s, {}).get(dep) or "")

    def listed_through(s, dep, a, b):
        f = flags(s, dep)
        ix = {kb_ix.get(day_date(n).strftime("%b'%y")) for n in range(a, b + 1, 7)} | {kb_ix.get(day_date(b).strftime("%b'%y"))}
        return bool(f) and all(i is not None and i < len(f) and f[i] == "Y" for i in ix)

    # ---- delist: like-for-like on the latest window, vs own earlier years and vs cluster peers
    delist, held, scored = [], [], 0
    funnel = {"listed_now": 0, "listed_through_window": 0, "store_traded_window": 0, "with_benchmark": 0}
    for cat, w in windows_now.items():
        a, b = w["evaluate"]["_a"], w["evaluate"]["_b"]
        g = nf[nf["cat"] == cat]
        rec = g[(g["day"] >= a) & (g["day"] <= b)].groupby(["STORE_NAME", "DEPARTMENT"])["SL_V"].sum()
        rdays = open_days(a, b)
        bench = {}
        for y in YEARS:
            k = day_date(a).year - y
            if k > 0:
                ya, yb = shift_years(a, k), shift_years(b, k)
                bench[y] = (ya, yb, g[(g["day"] >= ya) & (g["day"] <= yb)].groupby(["STORE_NAME", "DEPARTMENT"])["SL_V"].sum(),
                            open_days(ya, yb))
        rows = []
        cal = {cl: nf_cal(cl, a, b) for cl in fdays}
        bcal = {(cl, y): nf_cal(cl, ya, yb) for cl in fdays for y, (ya, yb, _, _) in bench.items()}
        for s, row in kb["data"].items():
            for dep, f in row.items():
                if f[last_i:last_i + 1] != "Y" or cat_of.get(dep, "regular") != cat:
                    continue
                funnel["listed_now"] += 1
                if not listed_through(s, dep, a, b):
                    continue
                funnel["listed_through_window"] += 1
                cl = store_cl.get(s, "ALL")
                R, Rd = float(rec.get((s, dep), 0.0)), int(rdays.get(s, 0))
                if Rd < max(MIN_DAYS, COVER * cal.get(cl, b - a + 1)):
                    continue
                funnel["store_traded_window"] += 1
                yrs = [(y, ya, yb, float(bs.get((s, dep), 0.0)), int(bd.get(s, 0))) for y, (ya, yb, bs, bd) in bench.items()]
                # only years it was on the floor, in a store trading most of that window
                yrs = [x for x in yrs if x[3] > 0 and x[4] >= COVER * bcal.get((cl, x[0]), 1) and mature(s, x[1])]
                if yrs:
                    rows.append({"store": s, "dept": dep, "cl": store_cl.get(s, "ALL"), "R": R, "Rd": Rd,
                                 "Bs": sum(x[3] for x in yrs), "Bd": sum(x[4] for x in yrs), "yrs": yrs})
        if not rows:
            continue
        df = pd.DataFrame(rows)
        scored += len(df)
        funnel["with_benchmark"] += len(df)
        hold = (w["evaluate"]["type"] == "off" and w["next"]["type"] == "in"
                and (datetime.date.fromisoformat(w["next"]["from"]) - day_date(A)).days <= LOOKAHEAD)
        grp, cnt = df.groupby(["dept", "cl"])[["R", "Rd", "Bs", "Bd"]].sum(), df.groupby(["dept", "cl"]).size()
        chain, ccnt = df.groupby("dept")[["R", "Rd", "Bs", "Bd"]].sum(), df.groupby("dept").size()
        for x in df.itertuples():
            rate, brate = x.R / x.Rd, x.Bs / x.Bd
            basis, pool, n = "cluster", grp.loc[(x.dept, x.cl)], int(cnt[(x.dept, x.cl)]) - 1
            if n < MIN_PEERS or x.cl == "ALL":
                basis, pool, n = "all stores", chain.loc[x.dept], int(ccnt[x.dept]) - 1
            pb = (pool.Bs - x.Bs) / max(pool.Bd - x.Bd, 1)
            peer_ratio = ((pool.R - x.R) / max(pool.Rd - x.Rd, 1)) / pb if pb > 0 else None
            if brate * 30 < MIN_BENCH_MONTHLY or n < 1 or not peer_ratio:
                continue
            ratio = rate / brate
            rel = ratio / peer_ratio
            if ratio > DELIST_AT or rel > REL_AT:
                continue
            (held if hold else delist).append({
                "store": x.store, "dept": x.dept, "category": cat, "cluster": x.cl,
                "window": {"type": w["evaluate"]["type"], "from": iso(a), "to": iso(b), "days": x.Rd, "sales": r2(x.R), "rate": r2(rate)},
                "benchmark": {"rate": r2(brate), "days": int(x.Bd), "sales": r2(x.Bs),
                              "years": [{"year": y, "from": iso(ya), "to": iso(yb), "days": dd, "sales": r2(v)} for y, ya, yb, v, dd in x.yrs]},
                "ratio": round(ratio, 3), "peers": {"basis": basis, "stores": n, "ratio": round(peer_ratio, 3)},
                "relative": round(rel, 3), "shortfall_month": r2((brate - rate) * 30),
                "tier": "High" if ratio <= 0.2 else "Medium" if ratio <= 0.35 else "Low",
                "next_window": w["next"],
            })

    # ---- per department: festival-free rate per month vs its own window benchmark; festival lift
    carriers = full.groupby(["DEPARTMENT", "y"])["STORE_NAME"].unique()
    depts = {}
    for dep, g in full.groupby("DEPARTMENT"):
        cat = cat_of.get(dep, "regular")
        sales_ym = g.groupby(["y", "m"])["SL_V"].sum()
        dd = {(y, m): int(dym[(y, m)].reindex(carriers.get((dep, y), [])).fillna(0).sum()) if (y, m) in dym else 0
              for y in YEARS for m in range(1, 13)}
        tot = lambda ms: (sum(float(sales_ym.get((y, m), 0)) for y in YEARS for m in ms), sum(dd[(y, m)] for y in YEARS for m in ms))
        win = {}
        for t in ("in", "normal", "off"):
            ms = [m for m in range(1, 13) if cats[cat]["type"][MON[m - 1]] == t]
            if ms:
                s_, n_ = tot(ms)
                win[t] = {"months": [MON[m - 1] for m in ms], "rate": r2(s_ / n_) if n_ else 0.0, "days": n_, "sales": r2(s_)}
        months = []
        for m in range(1, 13):
            s_, n_ = tot([m])
            t = cats[cat]["type"][MON[m - 1]]
            rate = s_ / n_ if n_ else 0.0
            months.append({"month": MON[m - 1], "type": t, "rate": r2(rate), "days": n_, "sales": r2(s_),
                           "vs_window": round(rate / win[t]["rate"], 3) if win.get(t, {}).get("rate") else None})
        depts[dep] = {"category": cat, "windows": win, "months": months, "festivals": []}
    fz = d[(d["fest"] != "") & d["y"].isin(YEARS)]
    fzd = od[(od["fest"] != "") & od["y"].isin(YEARS)].groupby(["fest", "y", "m", "STORE_NAME"]).size()
    fz_days = {k: g.droplevel([0, 1, 2]) for k, g in fzd.groupby(level=[0, 1, 2])}
    full_by = dict(tuple(full.groupby("DEPARTMENT")))
    for (dep, fe), g in fz.groupby(["DEPARTMENT", "fest"]):
        if dep not in depts:
            continue
        ym = sorted(set(zip(g["y"], g["m"])))
        stores = sorted(set(g["STORE_NAME"]))
        fs = float(g["SL_V"].sum())
        fd = int(sum(fz_days[(fe, y, m)].reindex(stores).fillna(0).sum() for y, m in ym if (fe, y, m) in fz_days))
        base = full_by[dep]
        base = base[base["STORE_NAME"].isin(stores) & pd.MultiIndex.from_arrays([base["y"], base["m"]]).isin(ym)]
        bd = int(sum(dym[(y, m)].reindex(stores).fillna(0).sum() for y, m in ym if (y, m) in dym))
        bs = float(base["SL_V"].sum())
        if fd and bd and bs > 0:
            depts[dep]["festivals"].append({"festival": fe, "lift": round((fs / fd) / (bs / bd), 2), "festival_days": fd,
                                            "festival_sales": r2(fs), "normal_rate": r2(bs / bd), "stores": len(stores)})
    for v in depts.values():
        v["festivals"].sort(key=lambda x: -x["lift"])

    # ---- relist: delisted combos whose department's in-season / normal window is starting
    relist = []
    for cat, w in windows_now.items():
        t = w["relist_target"]
        if not t:
            continue
        ta, tb = t["_a"], t["_b"]
        g = nf[nf["cat"] == cat]
        combos = [(s, dep) for s, row in kb["data"].items() for dep, f in row.items()
                  if f[last_i:last_i + 1] == "N" and "Y" in f and cat_of.get(dep, "regular") == cat]
        per_year = []
        for k in range(1, len(YEARS) + 1):
            ya, yb = shift_years(ta, k), shift_years(tb, k)
            if day_date(ya).year < YEARS[0]:
                break
            s_ = g[(g["day"] >= ya) & (g["day"] <= yb)].groupby(["STORE_NAME", "DEPARTMENT"])["SL_V"].sum()
            dd = open_days(ya, yb)
            den = s_.index.get_level_values(0).map(dd).to_numpy(dtype=float)
            rates = pd.Series(s_.to_numpy() / den, index=s_.index).replace([np.inf, -np.inf], np.nan).dropna()
            per_year.append((ya, yb, s_, dd, rates))
        for s, dep in combos:
            cl = store_cl.get(s, "ALL")
            for ya, yb, s_, dd, rates in per_year:           # the most recent year it sold in this window
                v, n = float(s_.get((s, dep), 0.0)), int(dd.get(s, 0))
                if v <= 0 or n < max(1, COVER * nf_cal(cl, ya, yb)) or not mature(s, ya):
                    continue
                own = v / n
                pr = rates[(rates.index.get_level_values(1) == dep) & (rates.index.get_level_values(0) != s)]
                same = pr[np.array([store_cl.get(p, "ALL") == cl for p in pr.index.get_level_values(0)], dtype=bool)]
                basis, pool = ("cluster", same) if len(same) >= MIN_PEERS and cl != "ALL" else ("all stores", pr)
                if not len(pool):
                    break
                med = float(pool.median())
                tdays = nf_cal(cl, ta, tb)
                lift = {x["festival"]: x["lift"] for x in depts.get(dep, {}).get("festivals", [])}
                fest_in = {}
                for n_ in range(ta, tb + 1):
                    fe = fdays.get(cl, {}).get(n_)
                    if fe:
                        fest_in[fe] = fest_in.get(fe, 0) + 1
                exp_nf = own * tdays
                exp_f = sum(own * lift.get(fe, 1.0) * k for fe, k in fest_in.items())
                exp = exp_nf + exp_f
                if own >= RELIST_AT * med and exp >= MIN_RELIST_VALUE:
                    f = flags(s, dep)
                    relist.append({
                        "store": s, "dept": dep, "category": cat, "cluster": cl,
                        "target": {"type": t["type"], "from": t["from"], "to": t["to"], "festival_free_days": tdays},
                        "evidence": {"year": day_date(ya).year, "from": iso(ya), "to": iso(yb), "days": n, "sales": r2(v), "rate": r2(own)},
                        "peers": {"basis": basis, "stores": int(len(pool)), "median_rate": r2(med)},
                        "vs_peers": round(own / med, 3) if med else None,
                        "expected_sales": r2(exp), "expected_festival_free": r2(exp_nf), "expected_festival": r2(exp_f),
                        "festival_days": [{"festival": fe, "days": k, "lift": lift.get(fe, 1.0)} for fe, k in fest_in.items()],
                        "last_listed": kb["months"][f.rfind("Y")],
                    })
                break
    print(f"suggestions done ({time.time() - t0:.0f}s)", flush=True)

    # ---- reconciliation: day-wise cache vs the month-wise export the other tabs use
    sales = json.load(open(os.path.join(APP, "sales.json"), encoding="utf-8"))
    mtot = {}
    for row in sales["data"].values():
        for mm in row.values():
            for m, v in mm.items():
                mtot[m[:6]] = mtot.get(m[:6], 0.0) + v
    dm = d.groupby(d["BILLDATE"].dt.strftime("%b'%y"))["SL_V"].sum()
    partial = day_date(A).strftime("%b'%y") if day_date(A + 1).day != 1 else None
    recon = [{"month": m, "day_wise": r2(dm[m]), "month_wise": r2(mtot[m]), "diff_pct": round((dm[m] - mtot[m]) / mtot[m] * 100, 2),
              "partial": m == partial} for m in sorted(set(dm.index) & set(mtot), key=lambda m: kb_ix.get(m, 0)) if mtot[m]]

    now = datetime.datetime.now().isoformat(timespec="seconds")
    params = {"years": YEARS, "in_season_index": IN_AT, "off_season_index": OFF_AT, "min_window_days": MIN_DAYS,
              "max_window_days": MAX_DAYS, "delist_ratio": DELIST_AT, "delist_relative": REL_AT,
              "min_benchmark_monthly": MIN_BENCH_MONTHLY, "coverage": COVER, "mature_days": MATURE_DAYS, "min_peers": MIN_PEERS, "relist_lookahead_days": LOOKAHEAD,
              "relist_vs_peers": RELIST_AT, "min_relist_value": MIN_RELIST_VALUE}
    sources = {"daily": trace_daily, "calendar": cal_notes, "listing": {"file": "kb.json", "latest_month": kb["months"][-1]},
               "season_category": "seasonality.json season_category (ATTRIBUTE1); missing = regular"}
    for w in windows_now.values():
        for k in ("evaluate", "relist_target"):
            if w.get(k):
                w[k] = {kk: vv for kk, vv in w[k].items() if not kk.startswith("_")}
    with open(os.path.join(APP, "windows.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": now, "anchor": iso(A), "params": params, "sources": sources, "categories": cats,
                   "windows_now": windows_now, "festivals": fest_rows, "departments": depts, "reconciliation": recon},
                  fh, separators=(",", ":"))
    delist.sort(key=lambda r: -r["shortfall_month"])
    held.sort(key=lambda r: -r["shortfall_month"])
    relist.sort(key=lambda r: -r["expected_sales"])
    with open(os.path.join(APP, "suggestions.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at": now, "anchor": iso(A), "params": params, "sources": sources,
                   "counts": {"scored": scored, "delist": len(delist), "relist": len(relist), "held": len(held), "funnel": funnel,
                              "delist_by_tier": {t: sum(r["tier"] == t for r in delist) for t in ("High", "Medium", "Low")}},
                   "delist": delist, "held": held, "relist": relist}, fh, separators=(",", ":"))
    print(f"windows.json + suggestions.json: {scored:,} combos scored, {len(delist):,} delist, {len(relist):,} relist "
          f"suggestions, {len(fest_rows)} festival windows ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    build()
