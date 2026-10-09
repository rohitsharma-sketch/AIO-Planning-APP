"""Cluster season curves for the STR Forecaster (user, 9 Oct: "Store-level seasonality: use each cluster's own season
curve from the day-wise sales ... Club it with their respective cluster").

Same method as the Listing - Delisting Analyser's season windows (Listing Delisting/scripts/build_suggestions.py):
day-wise data-lake sales (its daily.parquet cache), each store's calendar-cluster festival days left out, SL_V per
festival-free open store-day, every month vs that year's 12-month average, 2022-25 averaged. Done per AOP cluster x
department and chain-wide per department. A cluster with few stores selling a department leans on the chain curve:
    index = w x cluster + (1 - w) x chain,   w = stores / (stores + SHRINK)
-> season_cluster.json (gitignored) {built_at, source, years, cut, shrink, chain {DEPT: [12]}, cluster {CL: {DEPT: [12]}},
   stores {CL: {DEPT: n}}}. Rebuilt by the server when the day-wise cache or the AOP store master is newer.
Run: python str_season.py"""
import datetime
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LISTING = os.path.join(HERE, "..", "Listing Delisting", "scripts")
OUT = os.path.join(HERE, "season_cluster.json")
SHRINK = 3   # 3 stores selling it = half its own curve, half the chain's


def sources():
    """the files the curves come from (their mtimes decide a rebuild)"""
    if LISTING not in sys.path:
        sys.path.insert(0, LISTING)
    from build_daily import CACHE   # noqa: E402 - the Listing app's day-wise cache path
    import str_engine as se
    import config_store
    return [CACHE, config_store.CONFIG_FILE], se


def stale():
    try:
        files, _ = sources()
        return not os.path.exists(OUT) or os.path.getmtime(OUT) < max(os.path.getmtime(f) for f in files)
    except Exception:  # noqa: BLE001 - no day-wise cache on this machine: nothing to build
        return False


def index_by(sales, days, keys):
    """sales (keys + DEPARTMENT, y, m) and open days (keys, y, m) -> month index [12] per keys + DEPARTMENT"""
    s = sales.unstack("m").reindex(columns=range(1, 13)).fillna(0.0)
    d = days.unstack("m").reindex(columns=range(1, 13))
    di = pd.MultiIndex.from_arrays([s.index.get_level_values(k) for k in keys + ["y"]]) if keys else s.index.get_level_values("y")
    with np.errstate(divide="ignore", invalid="ignore"):
        rate = s.values / d.reindex(di).values                       # SL_V per festival-free open store-day
        mean = np.nanmean(np.where(np.isfinite(rate), rate, np.nan), axis=1, keepdims=True)
        yr = np.where(mean > 0, rate / mean, np.nan)
    lv = list(range(len(keys) + 1))
    return pd.DataFrame(yr, index=s.index, columns=range(1, 13)).groupby(level=lv).mean()   # average over the years


def build():
    t0 = time.time()
    files, se = sources()
    import build_suggestions as bs   # festival days per calendar cluster, YEARS and cut-offs - one source
    d = pd.read_parquet(files[0], columns=["STORE_NAME", "DEPARTMENT", "BILLDATE", "SL_V"])
    fdays, _, store_cl, _ = bs.festival_windows()
    d["day"] = d["BILLDATE"].values.astype("datetime64[D]").astype(np.int64)
    cal = d["STORE_NAME"].map(pd.Series({s: store_cl.get(s, "ALL") for s in d["STORE_NAME"].unique()})).values
    fest = np.zeros(len(d), bool)
    for cl, ix in pd.Series(cal).groupby(cal).indices.items():   # the store's own calendar cluster's festival days
        fest[ix] = np.isin(d["day"].values[ix], np.fromiter(fdays.get(cl, {}).keys(), np.int64))
    dt = pd.to_datetime(d["BILLDATE"])
    d["y"], d["m"] = dt.dt.year.values, dt.dt.month.values
    d = d[~fest & d["y"].isin(bs.YEARS)].copy()
    d["DEPARTMENT"] = d["DEPARTMENT"].astype(str).str.strip().str.upper()
    d["STORE_NAME"] = d["STORE_NAME"].astype(str).str.strip().str.upper()
    d["cl"] = d["STORE_NAME"].map(se.store_clusters())
    od = d.drop_duplicates(["STORE_NAME", "day"])                 # open store-days (the store sold anything)
    chain = index_by(d.groupby(["DEPARTMENT", "y", "m"])["SL_V"].sum(), od.groupby(["y", "m"]).size(), [])
    dc = d[d["cl"].notna()]
    clus = index_by(dc.groupby(["cl", "DEPARTMENT", "y", "m"])["SL_V"].sum(),
                    od[od["cl"].notna()].groupby(["cl", "y", "m"]).size(), ["cl"])
    n = dc[dc["SL_V"] > 0].groupby(["cl", "DEPARTMENT"])["STORE_NAME"].nunique()
    out = {"built_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "source": "Listing Delisting daily.parquet (festival days left out per calendar cluster), AOP Store Master clusters",
           "years": bs.YEARS, "cut": [bs.IN_AT, bs.OFF_AT], "shrink": SHRINK,
           "chain": {k: [round(float(v), 4) for v in row] for k, row in zip(chain.index, chain.fillna(1.0).values)},
           "cluster": {}, "stores": {}}
    for (cl, dep), row in zip(clus.index, clus.values):
        ch = np.array(out["chain"].get(dep, [1.0] * 12))
        k = int(n.get((cl, dep), 0))
        w = k / (k + SHRINK)
        out["cluster"].setdefault(cl, {})[dep] = [round(float(v), 4) for v in w * np.where(np.isfinite(row), row, ch) + (1 - w) * ch]
        out["stores"].setdefault(cl, {})[dep] = k
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    os.replace(tmp, OUT)
    print(f"season_cluster.json: {len(out['chain'])} departments, {len(out['cluster'])} clusters ({time.time() - t0:.0f}s)")
    return out


if __name__ == "__main__":
    build()
