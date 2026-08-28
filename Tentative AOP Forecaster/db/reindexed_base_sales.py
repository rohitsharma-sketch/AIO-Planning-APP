"""
Reads Calendar Engine's OWN saved reindex output (calendar.sales_snapshots,
source_type='mw', kind='trend_shifted' - the same table SalesPlan's Sync
Engine already reads from) and reshapes it into the same
{div: {fy28_month_label: value}} structure engine_v3.get_file_info()'s
base_sales.LFL uses.

Why this exists: store_actuals_sync.py (AOP's own sync) independently
re-reads the raw parquet and re-implements the ref-month -> fut-month
day-shift itself - it does NOT consume Calendar Engine's reindex output, even
though both are conceptually "the same" LFL actuals. This module is the
OTHER path: read what Calendar Engine actually computed and saved, so
ReviewStep's actuals-source toggle can show AOP's own replica side by side
with Calendar Engine's authoritative output, instead of only ever trusting
the replica.

Real constraint, not a bug here: this only has data for whatever calendar +
extra-dimension selection the LAST Calendar Engine month-wise reindex run
actually used. If nobody has run that reindex against the "2026 -> 2027"
calendar (the cycle AOP's current FY28 forecast needs) with ATTRIBUTE1
selected as an extra output field, this returns zeros / no attribute
breakdown - not wrong, just genuinely not there yet. See
`available_months`/`has_attribute` in the return value.
"""
from sqlalchemy import text

from engine_v3 import DIVS, LFL_TAGS, FY27_M, FY28_M, Q1_FY28_MONTHS, Q1_ALLOWED_VALUES, _open_months

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
    return None


def _col_to_fy28_label(col):
    """'2027-04' -> \"Apr'27\" - FY28_M's labels are the future month's own
    calendar year directly (unlike FY27_M's, which shift the year back one),
    so this is a straight month-name + last-2-digits-of-year conversion, no
    year arithmetic needed."""
    try:
        y, m = col.split("-")
        return f"{MON_NAMES[int(m)]}'{y[2:]}"
    except (ValueError, KeyError):
        return None


def get_reindexed_lfl_base_sales(session):
    """Returns {"base_sales": {div: {fy28_month: value}}, "hasAttribute": bool,
    "availableMonths": [...], "note": str | None}. `note` is set (not raised)
    for the "nothing usable yet" case - the caller/frontend surfaces it as a
    message next to the toggle, not an error."""
    snap = session.execute(
        text("SELECT key_fields, columns FROM calendar.sales_snapshots "
             "WHERE source_type = 'mw' AND kind = 'trend_shifted'")
    ).first()
    empty = {div: {m: 0.0 for m in FY28_M} for div in DIVS}
    if snap is None:
        return {"base_sales": empty, "hasAttribute": False, "availableMonths": [],
                "note": "No Calendar Engine month-wise reindex has been saved yet."}

    key_fields, columns = snap
    has_attribute = "ATTRIBUTE1" in key_fields
    available_fy28_months = sorted({m for c in columns if (m := _col_to_fy28_label(c)) in FY28_M})
    if not available_fy28_months:
        return {"base_sales": empty, "hasAttribute": has_attribute, "availableMonths": [],
                "note": ("Calendar Engine's saved reindex has no months overlapping this forecast's "
                          f"period ({FY28_M[1]} - {FY28_M[-1]}) - run its reindex against the "
                          "calendar that maps onto those dates first.")}

    lfl_stores = [r[0] for r in session.execute(
        text("SELECT store_id FROM masterdata.stores WHERE tag = ANY(:tags)"),
        {"tags": list(LFL_TAGS)},
    ).all()]

    group_cols = "elem->>'division' AS raw_div, elem->>'col' AS col" + \
        (", elem->>'ATTRIBUTE1' AS attribute" if has_attribute else "")
    rows = session.execute(
        text(f"""
            SELECT {group_cols}, SUM((elem->>'value')::numeric) AS total
            FROM calendar.sales_snapshots, jsonb_array_elements(rows) elem
            WHERE source_type = 'mw' AND kind = 'trend_shifted'
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
    closed_fy28_months = {fy28 for fy27, fy28 in zip(FY27_M, FY28_M) if fy27 not in open_months}
    for div in base_sales:
        for m in base_sales[div]:
            base_sales[div][m] = round(base_sales[div][m], 2) if m in closed_fy28_months else 0.0
    available_fy28_months = [m for m in available_fy28_months if m in closed_fy28_months]

    return {"base_sales": base_sales, "hasAttribute": has_attribute,
            "availableMonths": available_fy28_months, "note": None}
