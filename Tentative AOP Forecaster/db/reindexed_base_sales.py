"""
Reads Calendar Engine's OWN saved DAY-WISE reindex output (calendar.
sales_snapshots, source_type='dw', kind='trend_shifted') and reshapes it into
the same {div: {fy28_month_label: value}} structure engine_v3.get_file_info()'s
base_sales.LFL uses.

Why this exists: store_actuals_sync.py (AOP's own sync) independently
re-reads the raw parquet and re-implements the ref-day -> fut-day day-shift
itself - it does NOT consume Calendar Engine's reindex output, even though
both are conceptually "the same" LFL actuals. This module is the OTHER path:
read what Calendar Engine actually computed and saved, so the toggle can show
AOP's own replica side by side with Calendar Engine's authoritative output,
instead of only ever trusting the replica.

Why DAY-wise, not month-wise: month-wise reindexing (reindex_monthwise() in
calendar_engine/scans.py) has no day-level detail to redistribute, so it
buckets each whole reference month to whichever future month WINS A
PLURALITY VOTE across that month's ~30 days. A festival window is typically
5-10 days - a small minority of any month - so it essentially never wins that
vote, and the "reindexed" month total comes back identical to actual (just
relabeled a year later) for any realistic calendar. Confirmed 2026-08-31: a
freshly-computed month-wise trend_shifted snapshot matched the DB's own
actuals to the rupee for every LFL division/month. Day-wise data has real
per-day resolution, so it's the only source that can actually show a
festival-driven shift between months.

Real constraint, not a bug here: this only has data for whatever calendar +
extra-dimension selection the LAST Calendar Engine day-wise reindex run
actually used, AND requires DIVISION to have been ticked under "Customise
Output Fields" before that run (day-wise's row grain is store-only by
default - see reindex_daywise()'s key_fields - division is opt-in, unlike
month-wise where it's baked into the grain). If nobody has run day-wise
reindex with DIVISION selected against the calendar this forecast needs,
this returns zeros / a `note` explaining why - not wrong, just genuinely not
there yet. See `available_months`/`hasAttribute`/`note` in the return value.
"""
from sqlalchemy import text

from engine_v3 import DIVS, LFL_TAGS, auto_tag, FY27_M, FY28_M, Q1_FY28_MONTHS, Q1_ALLOWED_VALUES, _open_months

GM_DEPTS = {"HOUSEHOLD", "LIFESTYLE", "NON FOOD", "HOME FURNISHING", "SPORTS & TOYS",
            "FOOTWEAR", "TRAVEL ACCESSORIES", "STATIONERY"}

# calendar.sales_snapshots stores its SL_V sums in raw Rupees (Calendar Engine's
# own convention) - AOP's base_sales is Lakhs everywhere else (ReviewStep.jsx's
# own comment: "already Rs Lakhs - the app's one consistent unit"), and
# store_actuals_sync.py's OWN reindex divides by this same constant before
# writing to Postgres. Missing this here first showed up as a ~2,000 Lakh
# GM month coming back as ~200,000,000 - a real bug caught by comparing this
# source's numbers against the 'own' source's for the same month, not a
# hypothetical.
LAKH = 1e5

MON_NAMES = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}


def _norm_div(d):
    """Same rollup rule as store_actuals_sync.py's _norm_div - the raw
    'division' field in Calendar Engine's own reindex rows uses the same raw
    source values (GM sub-departments appear AS the division value), not
    AOP's already-rolled-up GM/KIDS/LADIES/MENS/RETAIL taxonomy."""
    d = " ".join(str(d or "").upper().split())
    if d in DIVS:
        return d
    if d in GM_DEPTS:
        return "GM"
    if d == "DND":   # user, 2026-10-08: DND belongs to RETAIL
        return "RETAIL"
    return None


def _col_to_fy28_label(col):
    """'2027-04-15' -> \"Apr'27\" - day-wise reindex columns are individual
    ISO dates ('YYYY-MM-DD'), not months, so only the year-month prefix is
    used. FY28_M's labels are the future date's own calendar year directly
    (unlike FY27_M's, which shift the year back one), so this is a straight
    month-name + last-2-digits-of-year conversion, no year arithmetic needed."""
    try:
        y, m = col.split("-")[:2]
        return f"{MON_NAMES[int(m)]}'{y[2:]}"
    except (ValueError, KeyError):
        return None


def _dw_incomplete_months(session):
    """(FY28 labels whose last-year month the day-wise ACTUALS don't fully cover, last actual day).
    The day-wise export can end mid-month (e.g. 27 Aug 2026 while month-wise has all of August),
    and its reindexed month then comes back ~12% short - a data gap, not a festival shift
    (found 2026-09-26: Aug'27 -1,199 L vs month-wise). Such months are left out, with a note."""
    import calendar
    last = session.execute(text(
        "SELECT columns->>-1 FROM calendar.sales_snapshots WHERE source_type = 'dw' AND kind = 'actual'")).scalar()
    if not last:
        return set(), None
    ly, lm, ld = (int(x) for x in last.split("-")[:3])
    out = set()
    for label in FY28_M:
        mon = next(k for k, v in MON_NAMES.items() if v == label[:3])
        ref_y = 2000 + int(label[-2:]) - 1                     # same month, one year earlier
        if (ref_y, mon) > (ly, lm) or ((ref_y, mon) == (ly, lm) and ld < calendar.monthrange(ly, lm)[1]):
            out.add(label)
    return out, last


def _gap_note(gap, last):
    return (f" {', '.join(gap)} left out - the day-wise export ends {last}, so "
            f"{'that month is' if len(gap) == 1 else 'those months are'} incomplete there.") if gap else ""


def get_reindexed_lfl_base_sales(session):
    """Returns {"base_sales": {div: {fy28_month: value}}, "hasAttribute": bool,
    "availableMonths": [...], "note": str | None}. `note` is set (not raised)
    for the "nothing usable yet" case - the caller/frontend surfaces it as a
    message next to the toggle, not an error."""
    snap = session.execute(
        text("SELECT key_fields, columns FROM calendar.sales_snapshots "
             "WHERE source_type = 'dw' AND kind = 'trend_shifted'")
    ).first()
    empty = {div: {m: 0.0 for m in FY28_M} for div in DIVS}
    if snap is None:
        return {"base_sales": empty, "hasAttribute": False, "availableMonths": [],
                "note": "No Calendar Engine day-wise reindex has been saved yet."}

    key_fields, columns = snap
    has_attribute = "ATTRIBUTE1" in key_fields

    # Same auto LfL rule as the engine's Store Master (engine_v3.auto_tag)
    lfl_stores = sorted({r[0] for r in session.execute(
        text("SELECT store_id, tag, opening_date, store_current_status FROM masterdata.stores")
    ).all() if auto_tag(r[1], r[2], r[3]) in LFL_TAGS})

    # Unlike month-wise (DIVISION is always part of the grain), day-wise's
    # default grain is store-only.  When DIVISION was not ticked before the
    # last Day-wise Reindex run we still have correct monthly TOTALS — we just
    # don't know which division contributed what.  The loophole: pull DW monthly
    # totals (which carry the festival day-shift between months accurately) and
    # split them across divisions using the MW snapshot's proportions (MW is
    # always at div × month grain so it always has a division split).
    if "DIVISION" not in key_fields:
        # Step 1 — DW monthly totals for LfL stores
        dw_rows = session.execute(text("""
            SELECT SUBSTRING(elem->>'col' FROM 1 FOR 7) AS col,
                   SUM((elem->>'value')::numeric) AS total
            FROM calendar.sales_snapshots, jsonb_array_elements(rows) elem
            WHERE source_type = 'dw' AND kind = 'trend_shifted'
              AND elem->>'store' = ANY(:stores)
            GROUP BY 1
        """), {"stores": lfl_stores}).all()
        dw_total_by_month = {}
        for col, total in dw_rows:
            label = _col_to_fy28_label(col)
            if label in FY28_M:
                dw_total_by_month[label] = dw_total_by_month.get(label, 0.0) + float(total)

        if not dw_total_by_month:
            return {"base_sales": empty, "hasAttribute": has_attribute, "availableMonths": [],
                    "note": (f"Calendar Engine's saved reindex has no dates overlapping this "
                              f"forecast's period ({FY28_M[1]} – {FY28_M[-1]}) — "
                              "re-run Day-wise Reindex against the calendar that maps onto those dates first.")}

        # Step 2 — MW division proportions (MW always carries DIVISION in its grain)
        mw_div_total = {}    # {(div, label): raw-rupee total}
        mw_month_total = {}  # {label: raw-rupee total across all divs}
        # MW rows store the division under the lowercase 'division' key
        # (reindex_monthwise's key_fields) - ATTRIBUTE1 is a season/attribute
        # value (REGULAR, SUMMER, ...), not a division.
        mw_div_rows = session.execute(text("""
            SELECT elem->>'division' AS raw_div,
                   SUBSTRING(elem->>'col' FROM 1 FOR 7) AS col,
                   SUM((elem->>'value')::numeric) AS total
            FROM calendar.sales_snapshots, jsonb_array_elements(rows) elem
            WHERE source_type = 'mw' AND kind = 'trend_shifted'
              AND elem->>'store' = ANY(:stores)
            GROUP BY 1, 2
        """), {"stores": lfl_stores}).all()
        for raw_div, col, total in mw_div_rows:
            label = _col_to_fy28_label(col)
            if label not in FY28_M:
                continue
            div = _norm_div(raw_div)
            # The share's denominator is every division the DAY-wise total also holds - DND / CDIT / CONSIGNMENT
            # included - so their sales are not spread into the merchandise divisions (audit 2026-09-26: +4-9 L
            # a month). NON-TRADING and FIXED ASSETS are not in the day-wise export at all.
            if " ".join(str(raw_div or "").upper().split()) not in ("NON-TRADING", "FIXED ASSETS"):
                mw_month_total[label] = mw_month_total.get(label, 0.0) + float(total)
            if div is None:
                continue
            mw_div_total[(div, label)] = mw_div_total.get((div, label), 0.0) + float(total)

        # No KIDS/LADIES/MENS rows means the MW snapshot has no usable division
        # breakdown (missing, or saved without 'division') - any split from it
        # would be fake, so refuse rather than estimate.
        if not any(div in ("KIDS", "LADIES", "MENS") for div, _ in mw_div_total):
            return {"base_sales": empty, "hasAttribute": has_attribute, "availableMonths": [],
                    "note": ("Day-wise reindex has no Division breakdown and the month-wise snapshot has no "
                             "KIDS/LADIES/MENS rows to split it by - re-run Month-wise Reindex (or Day-wise "
                             "with DIVISION ticked) first.")}

        # Step 3 — Combine: DW total × MW division share → Lakhs
        base_sales = {div: {m: 0.0 for m in FY28_M} for div in DIVS}
        for m, dw_total in dw_total_by_month.items():
            mw_total = mw_month_total.get(m, 0.0)
            if mw_total <= 0:
                continue
            for div in DIVS:
                share = mw_div_total.get((div, m), 0.0) / mw_total
                base_sales[div][m] = dw_total * share / LAKH

        open_months = _open_months()
        gap, last = _dw_incomplete_months(session)
        closed_fy28_months = {fy28 for fy27, fy28 in zip(FY27_M, FY28_M) if fy27 not in open_months} - gap
        for div in base_sales:
            for m in base_sales[div]:
                base_sales[div][m] = round(base_sales[div][m], 2) if m in closed_fy28_months else 0.0
        available_fy28_months = sorted([m for m in dw_total_by_month if m in closed_fy28_months])

        note = ("Day-wise reindex has no Division breakdown — division split estimated from "
                "month-wise reindex proportions. Monthly totals (festival shifts) are from day-wise output."
                + _gap_note(sorted(gap & set(dw_total_by_month), key=FY28_M.index), last))

        return {"base_sales": base_sales, "hasAttribute": has_attribute,
                "availableMonths": available_fy28_months, "note": note}

    # --- Full path: DIVISION is in the DW snapshot key_fields ---
    available_fy28_months = sorted({m for c in columns if (m := _col_to_fy28_label(c)) in FY28_M})
    if not available_fy28_months:
        return {"base_sales": empty, "hasAttribute": has_attribute, "availableMonths": [],
                "note": ("Calendar Engine's saved reindex has no dates overlapping this forecast's "
                          f"period ({FY28_M[1]} - {FY28_M[-1]}) - run its reindex against the "
                          "calendar that maps onto those dates first.")}

    # 'col' is an individual ISO date ('YYYY-MM-DD') for day-wise, unlike
    # month-wise's 'YYYY-MM' - collapse to the year-month prefix in SQL so the
    # aggregate groups by month (≤13 buckets) rather than materializing one
    # row per distinct day (up to ~365/year) before summing in Python.
    group_cols = "elem->>'DIVISION' AS raw_div, SUBSTRING(elem->>'col' FROM 1 FOR 7) AS col" + \
        (", elem->>'ATTRIBUTE1' AS attribute" if has_attribute else "")
    rows = session.execute(
        text(f"""
            SELECT {group_cols}, SUM((elem->>'value')::numeric) AS total
            FROM calendar.sales_snapshots, jsonb_array_elements(rows) elem
            WHERE source_type = 'dw' AND kind = 'trend_shifted'
              AND elem->>'store' = ANY(:stores)
            GROUP BY {"1, 2, 3" if has_attribute else "1, 2"}
        """),
        {"stores": lfl_stores},
    ).all()

    base_sales = {div: {m: 0.0 for m in FY28_M} for div in DIVS}
    for row in rows:
        if has_attribute:
            raw_div, col, attribute, total = row
        else:
            raw_div, col, total = row
            attribute = None
        div = _norm_div(raw_div)
        label = _col_to_fy28_label(col)
        if div is None or label not in FY28_M:
            continue
        if Q1_ALLOWED_VALUES and has_attribute and label in Q1_FY28_MONTHS and attribute not in Q1_ALLOWED_VALUES:
            continue
        base_sales[div][label] += float(total) / LAKH

    # Zero out any FY28 month whose FY27-mapped predecessor hasn't fully
    # closed yet - the same rule pivot_actuals() applies to AOP's own
    # actuals (see module docstring above). Without this, a still-open
    # month (synced early, before month-end) showed up here but not in the
    # 'own' actuals source, making an artificial gap look like a genuine
    # reindex effect when it was really just an apples-to-oranges month set.
    open_months = _open_months()
    gap, last = _dw_incomplete_months(session)
    closed_fy28_months = {fy28 for fy27, fy28 in zip(FY27_M, FY28_M) if fy27 not in open_months} - gap
    for div in base_sales:
        for m in base_sales[div]:
            base_sales[div][m] = round(base_sales[div][m], 2) if m in closed_fy28_months else 0.0
    shown = set(available_fy28_months)
    available_fy28_months = [m for m in available_fy28_months if m in closed_fy28_months]

    return {"base_sales": base_sales, "hasAttribute": has_attribute,
            "availableMonths": available_fy28_months,
            "note": _gap_note(sorted(gap & shown, key=FY28_M.index), last).strip() or None}
