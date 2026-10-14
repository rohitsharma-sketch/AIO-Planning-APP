"""Sell-thru growth factors for the cluster-built plan (user, 2026-10-13: "just import the logics ... i want the existing
apps to flow their respective components as in relation to the present columns" - the working of the MAMJ'27 cluster
workbook, "claude - mamj27.xlsx", as a way to build the plan, not a copy of its sheet).

Per department x plan month:
  sell-thru  = average weekly sell-thru of the LY month: per week sales qty / (sales qty + closing stock), the weeks with
               a sell-thru averaged (a week belongs to the month its Thursday falls in) - the BIS's live ST: same file,
               same filters (SEASON contains 26, ACTIVE stores). CHAIN LEVEL (user's choice, 2026-10-13): the sell-thru
               file has no store column, so every cluster gets the same figures; clusters differ by their own LY mix.
  MC tag     = status of the department's MAMJ sell-thru (every Mar-Jun'26 week): Low / Average / High / Excellent
  deviation  = department sell-thru / its division's, that month
  factor     = FACTOR[deviation band][tag];  growth = 1 + factor
grain_view uses growth as the weights of its cluster-built method (cluster x division AOP split over departments by LY x
growth - user's choice: each division holds its own AOP). Inactive departments (the workbook's -1) are not in the plan.
"""
import json
import os
import threading

import pandas as pd

from plan_cache import save_json

_HERE = os.path.dirname(os.path.abspath(__file__))
SELLTHRU_DIR = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw\rs_weekly_sell_ths_apps"
ST_CACHE = os.path.join(_HERE, "..", "sellthru_factor_st.json")   # per sell-thru file; git-ignored (SalesPlan/backend/*.json)
DIVS = ("KIDS", "LADIES", "MENS")
TAG_MONTHS = ("Mar'26", "Apr'26", "May'26", "Jun'26")   # MAMJ, "except Jul" as the workbook

# the workbook's FACTOR sheet. Status by average weekly sell-thru (lower bounds, as its lookup):
STATUS = ((0.151, "Excellent"), (0.111, "High"), (0.071, "Average"), (float("-inf"), "Low"))
TAGS = ("Low", "Average", "High", "Excellent")
# deviation (dept ST / division ST) lower bound, meaning, factor by tag (Low, Average, High, Excellent)
FACTOR = ((2.0, "Exceptional / outstanding", (0.18, 0.21, 0.25, 0.30)),
          (1.6, "Very strongly above division", (0.12, 0.15, 0.18, 0.21)),
          (1.4, "Strongly above division", (0.10, 0.12, 0.14, 0.17)),
          (1.2, "Above division", (0.08, 0.09, 0.10, 0.12)),
          (0.8, "Around division benchmark", (0.06, 0.06, 0.06, 0.06)),
          (0.65, "Below division", (0.04, 0.05, 0.06, 0.07)),
          (0.5, "Extremely below division", (0.02, 0.03, 0.04, 0.05)),
          (float("-inf"), "Very weak vs division", (0.0, 0.0, 0.0, 0.0)))


# the workbook's REVISED GROWTH FACTOR (MAIN DATA - 1 BF:BJ, read in its back-working file 2026-10-14; seen on 13 Oct as
# "20 manual zeroes"): a department whose MAMJ sell-thru is at most 4% AND whose deviation averages at most 50% over
# Mar-Jul'26 gets no factor (0%) in every month
REVISE_ST, REVISE_DEV = 0.04, 0.5
REVISE_MONTHS = ("Mar'26", "Apr'26", "May'26", "Jun'26", "Jul'26")


def status(st: float) -> str:
    return next(t for lo, t in STATUS if st >= lo)


def factor(dev: float, tag: str) -> float:
    return next(f for lo, _, f in FACTOR if dev >= lo)[TAGS.index(tag)]


_st = {"key": None, "v": None}
_st_lock = threading.Lock()
EMPTY = {"file": None, "dept": {}, "div": {}, "tag": {}}


def weekly_to_monthly(wk: pd.DataFrame, key: str) -> tuple[dict, dict]:
    """wk: rows of (key, WK_START_DT, SL_Q, CLS_STK_Q) -> ({key: {LY month: avg weekly ST}}, {key: MAMJ avg}). Sums to
    key x week first, ST = sales / (sales + closing stock), weeks without a sell-thru (0) left out of the averages."""
    g = wk.groupby([key, "WK_START_DT"], observed=True)[["SL_Q", "CLS_STK_Q"]].sum().reset_index()
    d = g.SL_Q + g.CLS_STK_Q
    g["p"] = (g.SL_Q / d).where(d > 0, 0.0)
    g = g[g.p > 0].copy()
    g["m"] = (pd.to_datetime(g.WK_START_DT) + pd.Timedelta(days=3)).dt.strftime("%b'%y")
    month = {}
    for (k, m), v in g.groupby([key, "m"]).p.mean().items():
        month.setdefault(str(k), {})[m] = float(v)
    tag = {str(k): float(v) for k, v in g[g.m.isin(TAG_MONTHS)].groupby(key).p.mean().items()}
    return month, tag


def sell_thru() -> dict:
    """{"file", "dept": {DEPT: {LY month: ST}}, "div": {DIV: {...}}, "tag": {DEPT: MAMJ ST}} - fractions (0.12 = 12%).
    Read once per sell-thru file (~30 s from the lake; 8010 warms it at start), then from ST_CACHE."""
    from rs_common.lake_files import latest_path
    p = latest_path(SELLTHRU_DIR)
    if not p:
        return EMPTY
    key = [os.path.basename(p), os.path.getmtime(p)]
    with _st_lock:
        if _st["key"] == key:
            return _st["v"]
        try:
            with open(ST_CACHE, encoding="utf-8") as fh:
                c = json.load(fh)
            if c.get("key") == key:
                _st.update(key=key, v=c["v"])
                return c["v"]
        except (OSError, ValueError, KeyError):
            pass
        cols = ["WK_START_DT", "STORE_STATUS", "SEASON", "DIVISION", "DEPARTMENT", "SL_Q", "CLS_STK_Q"]
        with open(p, "rb") as fh:   # an open handle: pyarrow mangles \\server\share paths given as strings
            df = pd.read_parquet(fh, columns=cols, filters=[("STORE_STATUS", "==", "ACTIVE")])
        df = df[df.SEASON.astype(str).str.contains("26", na=False) & df.DIVISION.isin(DIVS)].copy()
        df["DEPARTMENT"] = df.DEPARTMENT.astype(str).str.strip().str.upper()
        dept, tag = weekly_to_monthly(df, "DEPARTMENT")
        div, _ = weekly_to_monthly(df, "DIVISION")
        v = {"file": os.path.basename(p), "dept": dept, "div": div, "tag": tag}
        save_json(ST_CACHE, {"key": key, "v": v})
        _st.update(key=key, v=v)
        return v


def ly_of(ty: str) -> str:
    """"Mar'27" -> "Mar'26" (the same month a year back, as Sales Plan's MONTH_PAIR)."""
    return f"{ty[:4]}{int(ty[4:]) - 1:02d}"


def growth(depts: dict, months: list, st: dict | None = None) -> tuple[dict, dict]:
    """depts = {div: [dept]}; months = TY months -> ({div: {dept: {TY: 1 + factor}}},
    {div: {dept: {tag, tag_st, months: {TY: {st, div_st, dev, factor}}}}})."""
    st = sell_thru() if st is None else st
    g, info = {}, {}
    for dv, names in depts.items():
        for dp in names:
            tst = st["tag"].get(dp, 0.0)
            tag, ms = status(tst), {}
            devs = [st["dept"].get(dp, {}).get(m, 0.0) / b if (b := st["div"].get(dv, {}).get(m, 0.0)) > 0 else 0.0 for m in REVISE_MONTHS]
            off = tst <= REVISE_ST and sum(devs) / len(devs) <= REVISE_DEV
            for m in months:
                a, b = st["dept"].get(dp, {}).get(ly_of(m), 0.0), st["div"].get(dv, {}).get(ly_of(m), 0.0)
                dev = a / b if b > 0 else 0.0
                ms[m] = {"st": a, "div_st": b, "dev": dev, "factor": 0.0 if off else factor(dev, tag), "revised": off}
                g.setdefault(dv, {}).setdefault(dp, {})[m] = 1.0 + ms[m]["factor"]
            info.setdefault(dv, {})[dp] = {"tag": tag, "tag_st": tst, "months": ms}
    return g, info


def _check():
    """python -m engines.sellthru_factor: the workbook's lookups (its 1,764 rows matched: 0 tag, 0 factor differences)."""
    assert status(0.1411) == "High" and status(0.07) == "Low" and status(0.071) == "Average" and status(0.2) == "Excellent"
    assert factor(0.9888, "High") == 0.06 and factor(1.5555, "High") == 0.14 and factor(0.0, "Excellent") == 0.0
    assert factor(2.0, "Low") == 0.18 and factor(0.65, "Average") == 0.05
    assert ly_of("Mar'27") == "Mar'26" and ly_of("Jan'28") == "Jan'27"
    st = {"dept": {"A": {"Mar'26": 0.30}, "B": {"Mar'26": 0.10}}, "div": {"KIDS": {"Mar'26": 0.15}},
          "tag": {"A": 0.30, "B": 0.10}}
    g, info = growth({"KIDS": ["A", "B", "C"]}, ["Mar'27"], st)
    # A: dev 2.0, Excellent -> 1.30; B: dev 0.667, Average -> 1.05; C: no sell-thru -> very weak -> flat
    assert g["KIDS"] == {"A": {"Mar'27": 1.30}, "B": {"Mar'27": 1.05}, "C": {"Mar'27": 1.0}}
    assert info["KIDS"]["B"]["tag"] == "Average" and info["KIDS"]["C"]["tag"] == "Low"
    # revised: MAMJ ST 3% (<= 4%) and deviation 1.0 in Mar only -> average 0.2 over Mar-Jul (<= 0.5) -> no factor
    st2 = {"dept": {"D": {"Mar'26": 0.15}}, "div": {"KIDS": {m: 0.15 for m in REVISE_MONTHS}}, "tag": {"D": 0.03}}
    g2, info2 = growth({"KIDS": ["D"]}, ["Mar'27"], st2)
    assert g2["KIDS"]["D"]["Mar'27"] == 1.0 and info2["KIDS"]["D"]["months"]["Mar'27"]["revised"], (g2, info2)
    print("ok")


if __name__ == "__main__":
    _check()
