"""
Actuals Manager
================
LY store x department sales for Sales Plan, read from the Calendar app's own output (user, 2026-09-28:
"remove sales sync ... replace the manual import of sales ... with the output from calendar sales - for actual
and reindexed sales"). The nightly calendar_reindex_sync saves a department-level month-wise snapshot to
calendar.sales_snapshots: kind 'trend_shifted_dept' = REINDEXED (last year's sales moved onto the plan calendar)
and 'actual_dept' = the same sales on their own dates. Nothing is imported or locked here any more - a LY month is
available once it has closed and is in the snapshot (the old actuals_store.json / actuals_lock.json / "Actual
Sales" Excel import is gone).

- load_actuals()            -> REINDEXED, the plan base (user choice): {store: {plan_div: {dept: {LY label: Rs L}}}},
                               keyed by the LY label of the TY month it lands in (Apr'27 -> "Apr'26"), so every
                               engine keeps its LY-month lookup.
- load_actuals("actual")    -> the same stores / departments on their own LY dates.
- load_store_div_actuals()  -> store x plan division totals of the reindexed sales (non-SSG stores' base).
"""

import calendar as _cal
import datetime as _dt
import functools
import os, re, sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Tentative AOP Forecaster"))

LAKH = 1e5   # snapshots hold SL_V in rupees
KINDS = {"reindexed": "trend_shifted_dept", "actual": "actual_dept"}
# LY months of the plan year Mar'27..Mar'28 (same list as dept_sales_engine.LY_MONTHS) - older closed months in the
# snapshot (e.g. Jan'26 -> Jan'27) fall outside the plan and are not offered.
PLAN_LY_MONTHS = ["Mar'26", "Apr'26", "May'26", "Jun'26", "Jul'26", "Aug'26", "Sep'26", "Oct'26", "Nov'26",
                  "Dec'26", "Jan'27", "Feb'27", "Mar'27"]

# Divisions to include in plan (OTHERS excluded)
PLAN_DIVISIONS = {"GM", "KIDS", "LADIES", "MENS", "RETAIL"}

# Maps DIVISION column value → planning division used throughout the engine
# DIV_NEW column is a system artefact, NOT the planning division
DIVISION_COL_TO_PLAN = {
    "KIDS":              "KIDS",
    "LADIES":            "LADIES",
    "MENS":              "MENS",
    "RETAIL":            "RETAIL",
    "NON FOOD":          "GM",       # was RETAIL; GM like the AOP base (user, 2026-10-08)
    "DND":               "RETAIL",   # user, 2026-10-08: "add DND to the retail division"
    "FOOTWEAR":          "GM",
    "HOME FURNISHING":   "GM",
    "HOUSEHOLD":         "GM",
    "LIFESTYLE":         "GM",
    "SPORTS  & TOYS":    "GM",   # double-space as in source data
    "SPORTS & TOYS":     "GM",
    "STATIONERY":        "GM",
    "TRAVEL ACCESSORIES":"GM",
    # DIVISION values to exclude: NON-TRADING, FIXED ASSETS, CONSIGNMENT, CDIT
}



def _plan_div(raw):
    return DIVISION_COL_TO_PLAN.get(" ".join(str(raw or "").upper().split())) or DIVISION_COL_TO_PLAN.get(str(raw or "").upper())


@functools.lru_cache(maxsize=None)   # a handful of distinct month columns, asked ~1.5M times per plan run
def _ly_label(col, kind):
    """'2027-04' (reindexed: the TY month) or '2026-04' (actual: the LY month) -> "Apr'26"."""
    y, m = int(col[:4]), int(col[5:7])
    if kind == "reindexed":
        y -= 1
    return f"{_cal.month_abbr[m]}'{str(y)[2:]}", (y, m)


def _closed(y, m, today=None):
    """A LY month is usable once it has fully elapsed (same rule as the Calendar app's month cache)."""
    today = today or _dt.date.today()
    return (y, m) < (today.year, today.month)


_cache = {}


def _snapshot(kind):
    """(computed_at, rows) of a department-level snapshot, re-read only when the nightly sync replaced it."""
    from sqlalchemy import text
    from db.base import SessionLocal
    with SessionLocal() as s:
        at = s.execute(text("SELECT computed_at FROM calendar.sales_snapshots WHERE source_type = 'mw' AND kind = :k"),
                       {"k": KINDS[kind]}).scalar()
        if at is None:
            return None, []
        if _cache.get(kind, (None,))[0] != at:
            rows = s.execute(text("SELECT rows FROM calendar.sales_snapshots WHERE source_type = 'mw' AND kind = :k"),
                             {"k": KINDS[kind]}).scalar() or []
            _cache[kind] = (at, rows)
    return _cache[kind]


_built = {}


def load_actuals(kind: str = "reindexed") -> dict:
    """Returns {store: {division: {dept: {ly_month: Rs lakhs}}}} for closed LY months (see module docstring).
    Built once per snapshot and day, then shared (2026-10-01: it was rebuilt on every call - twice per plan run and
    on every page load); callers only read it."""
    at, rows = _snapshot(kind)
    key = (kind, at, _dt.date.today())
    if _built.get(kind, (None,))[0] == key:
        return _built[kind][1]
    out = {}
    for r in rows:
        div = _plan_div(r.get("division"))
        dept = str(r.get("DEPARTMENT") or "").strip().upper()
        if not div or not dept:
            continue
        label, (y, m) = _ly_label(r["col"], kind)
        if not _closed(y, m):
            continue
        d = out.setdefault(str(r["store"]).strip().upper(), {}).setdefault(div, {}).setdefault(dept, {})
        d[label] = d.get(label, 0.0) + float(r["value"]) / LAKH
    if kind == "reindexed" and at is not None and _registered.get("at") != at:
        _sync_depts_to_master(out)          # once per new snapshot, as the old Excel import did
        _registered["at"] = at
    _built[kind] = (key, out)
    return out


_registered = {}


def _sync_depts_to_master(actuals: dict):
    """
    Auto-registers any department seen in the Calendar sales that isn't already in the master or the custom dept
    JSON (department_custom.json), so its sales aren't silently left out of the plan (26-28 Sep 2026: e.g.
    MSE_HSR PYJAMA / MSE_TXTL PYJAMA, Rs 36.5 Cr). Attribute defaults to REGULAR - adjust in Master Setup;
    whether it is ACTIVE is set by "Sync from Buyer's Input".
    """
    from engines.department_plan import _MASTER_RAW, _load_custom, _save_custom
    known = {(div, dept) for div, dept, _ in _MASTER_RAW}
    custom = _load_custom()
    known |= {(c["division"], c["name"]) for c in custom}
    new_entries = []
    for store_data in actuals.values():
        for div, div_data in store_data.items():
            if div not in PLAN_DIVISIONS:
                continue
            for dept in div_data:
                if (div, dept) not in known:
                    known.add((div, dept))
                    new_entries.append({"division": div, "name": dept, "attribute": "REGULAR"})
    if new_entries:
        custom.extend(new_entries)
        _save_custom(custom)


def load_store_div_actuals(kind: str = "reindexed") -> dict:
    """{store: {division: {ly_month: Rs lakhs}}} - the department snapshot summed per plan division (built once per
    snapshot and day, like load_actuals)."""
    key = ("div", kind, _snapshot(kind)[0], _dt.date.today())
    if _built.get(("div", kind), (None,))[0] == key:
        return _built[("div", kind)][1]
    out = {}
    for store, divs in load_actuals(kind).items():
        for div, depts in divs.items():
            acc = out.setdefault(store, {}).setdefault(div, {})
            for months in depts.values():
                for m, v in months.items():
                    acc[m] = acc.get(m, 0.0) + v
    _built[("div", kind)] = (key, out)
    return out


def locked_ly_months() -> list[str]:
    """LY months the plan can use: closed and present in the reindexed snapshot (name kept for callers). Cached per
    snapshot and day."""
    at, rows = _snapshot("reindexed")
    key = ("ly", at, _dt.date.today())
    if _built.get("ly", (None,))[0] == key:
        return list(_built["ly"][1])
    labels = {}
    for r in rows:
        label, ym = _ly_label(r["col"], "reindexed")
        if _closed(*ym) and label in PLAN_LY_MONTHS:
            labels[label] = ym
    out = sorted(labels, key=labels.get)
    _built["ly"] = (key, out)
    return list(out)


def actuals_source() -> dict:
    """What the actuals status endpoint shows: where the numbers come from and when they were refreshed."""
    info = {}
    for kind in KINDS:
        at, rows = _snapshot(kind)
        info[kind] = {"snapshot": "calendar.sales_snapshots mw/" + KINDS[kind],
                      "computed_at": at.isoformat() if at else None, "rows": len(rows)}
    return info


def ly_to_ty_month(ly_month: str) -> str | None:
    """
    Maps a LY month label to the corresponding TY month.
    Mar'26 → Mar'27, Apr'26 → Apr'27, … Jan'27 → Jan'28, Mar'27 → Mar'28
    """
    m = re.match(r"([A-Za-z]+)'(\d{2})$", ly_month)
    if not m:
        return None
    mon = m.group(1)
    yr  = int(m.group(2)) + 1
    return f"{mon}'{yr}"


def available_ty_months() -> list[str]:
    """
    Returns the TY months that have locked LY actuals, in calendar order.
    """
    order = ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb"]
    ly_locked = locked_ly_months()
    ty_months = [ly_to_ty_month(m) for m in ly_locked if ly_to_ty_month(m)]

    def sort_key(tm):
        mm = re.match(r"([A-Za-z]+)'(\d{2})$", tm)
        if not mm:
            return (99, 99)
        mon, yr = mm.group(1), int(mm.group(2))
        return (yr, order.index(mon) if mon in order else 99)

    return sorted(set(ty_months), key=sort_key)
