#!/usr/bin/env python3
"""
Tentative AOP Forecaster  v3
Base (Actuals) x (1 + growth%) = Forecasted AOP
NSO stores: 750L ramp via ref-store pattern
"""

import datetime
import json
import os
import shutil
import sys
from decimal import Decimal, ROUND_HALF_DOWN
import pandas as pd
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import xlsxwriter


def _round2(value):
    """Round to 2 decimals for display/export.

    Python's built-in round() uses banker's rounding, which can push a
    number up OR down unpredictably at the boundary depending on float
    representation noise accumulated through the ramp/MoM forecast chain.
    Business rule: forecasts must never be inflated by a rounding tie, so
    exact .xx5 ties round DOWN (toward zero), same as ROUND_HALF_DOWN.
    """
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN))

# ── Constants ──────────────────────────────────────────────────────────────────
DIVS        = ["GM", "KIDS", "LADIES", "MENS", "RETAIL"]
NSO_TARGET  = 750.0          # Lakhs per NSO store
UNNAMED_PFX = ("NS-", "AD-", "MAMJ")
NSO_REF     = "LAM"

FY28_M = ["Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27","Sep'27",
          "Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"]
FY27_M = ["Mar'26","Apr'26","May'26","Jun'26","Jul'26","Aug'26","Sep'26",
          "Oct'26","Nov'26","Dec'26","Jan'27","Feb'27","Mar'27"]
M_IDX  = {m: i for i, m in enumerate(FY28_M)}
_MON_NUM = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
            "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _open_months(as_of=None):
    """FY27_M labels that have NOT yet fully closed as of `as_of` (defaults
    to real today) - the current, in-progress calendar month and any later
    one. A month closes the instant the calendar moves past it (the 1st of
    the following month) - the exact same cutoff store_actuals_sync.py's
    _complete_months() already uses to decide what to sync, so the engine
    and the sync agree on the identical "is this month usable yet" line.
    pivot_actuals() uses this to refuse a not-yet-closed month's actuals even
    if a stale/partial sync already wrote something for it into the DB -
    defence in depth, since the sync-side skip only stops FUTURE partial
    writes, it can't retroactively hide one that already landed."""
    as_of = as_of or datetime.date.today()
    cur = (as_of.year, as_of.month)
    return {m for m in FY27_M if (2000 + int(m.split("'")[1]), _MON_NUM[m.split("'")[0]]) >= cur}

LFL_TAGS  = {"032 - Stores","080 - Stores","095 - Stores","125 - Stores","3 - Stores",
             "FY26 - Q1","FY26 - Q2","FY26 - Q3",
             "LFL","lfl"}                                    # simple labels from DB-backed flow
RAMP_TAGS = {"FY26 - Q4","FY27 - Q1","FY27 - Q2",
             "Ramp","RAMP","ramp"}                           # simple labels from DB-backed flow
NSO_TAGS  = {"NSO","MAMJ-NSO"}   # 750L ramp formula

# Q1's base sales (Apr'27/May'27/Jun'27 forecast columns, i.e. the Apr'26/
# May'26/Jun'26 LY actuals that feed them) are meant to only count specific
# attribute values - every other quarter counts every attribute.
#
# DISABLED as of 2026-08-26: the real SEASON_TYPE values turned out to be
# collection codes (AW26, SS26 Q1, SS25 Q2, ...), not "Summer"/"Regular"/
# "Occasional" as first given - confirmed by inspecting the actual synced
# data (see [[aop-forecaster-lfl-data-model]] memory). Q1_ALLOWED_VALUES is
# intentionally empty so the `if Q1_ALLOWED_VALUES and ...` guard below never
# filters anything - base_sales behaves exactly as it did before this
# feature, not silently zeroed - until the real column/values are confirmed.
Q1_FY28_MONTHS = {"Apr'27", "May'27", "Jun'27"}
Q1_ALLOWED_VALUES = set()  # populate once the real attribute/values are confirmed

MAMJ_DEFAULT_OPEN    = "Apr'27"
# Deviation% above which a named store is treated as ref-compliant (opening-month distortion)
ANOMALY_DEV_THRESHOLD = 9.99   # = 999 %

# ── File paths ─────────────────────────────────────────────────────────────────
_HERE       = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE  = "inputs.xlsx"
OUTPUT_DIR  = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "AOP_Forecast.xlsx")

# Drop a diff.xlsx at this path to apply manual adjustments on the next run.
# The file is consumed ONCE and then archived — re-runs without a new file are safe.
# Columns: Concat (Store+Division), Diff <Month> | Forecast … (one per FY28 month).
# Only concats listed in the file are touched; all others remain engine-computed.
DIFF_FILE            = r"C:\Users\A9820\Downloads\diff.xlsx"

# Processed diff files are moved here so they are never double-counted.
DIFF_ARCHIVE_DIR     = os.path.join(_HERE, "diff_archive")

# Accumulates every diff ever applied so the engine can reconstruct prior state
# precisely when a new residual diff arrives.  Updated automatically each run.
CUMULATIVE_DIFF_FILE = os.path.join(_HERE, "cumulative_diff.json")

# ── Manual-adjustment helpers ──────────────────────────────────────────────────
_DIV_ORDER = sorted(DIVS, key=len, reverse=True)   # longest-suffix-first for parsing

def _split_concat(concat):
    """'AACGM' → ('AAC','GM'),  'AD-NS-09LADIES' → ('AD-NS-09','LADIES')."""
    for d in _DIV_ORDER:
        if concat.endswith(d):
            return concat[: -len(d)], d
    return None, None


def _parse_diff_file(path):
    """Read a diff sheet → {(store, div, month): value} for every non-zero cell.
    Auto-detects whether the header is on row 1 (index 0) or row 2 (index 1).
    First column may be labelled 'Concat', 'Row Labels', or anything — treated as concat.
    Month columns are identified by containing 'Diff' in their name."""
    try:
        df0 = pd.read_excel(path, header=0)
    except Exception:
        return {}
    # If "Diff" columns appear with header=0, use it; else fall back to header=1
    if any("Diff" in str(c) for c in df0.columns):
        df = df0
    else:
        try:
            df = pd.read_excel(path, header=1)
        except Exception:
            return {}
    # Normalise: first column → "Concat"
    df = df.rename(columns={df.columns[0]: "Concat"})
    df["Concat"] = df["Concat"].astype(str).str.strip()
    month_cols = [c for c in df.columns if "Diff" in str(c)]
    out = {}
    for _, row in df.iterrows():
        store, div = _split_concat(row["Concat"])
        if store is None:
            continue
        for col in month_cols:
            try:
                val = float(row[col])
            except (TypeError, ValueError):
                continue
            if val == 0.0:
                continue
            month = col.replace("Diff ", "").replace(" | Forecast", "").strip()
            out[(store, div, month)] = val
    return out


def _load_adjustments():
    """Return a single {(store, div, month): total_adjustment} dict.

    Workflow:
      1. Load the persistent cumulative (all diffs applied in prior runs).
      2. If a new diff.xlsx is present at DIFF_FILE, merge it into the cumulative
         and immediately ARCHIVE the file (rename → diff_archive/diff_<timestamp>.xlsx).
         This guarantees each diff file is consumed exactly once — re-running the
         engine without a new file is always safe and produces identical output.
      3. Persist the updated cumulative and return it.

    build_df applies: forecast = engine_value + total_adjustment  (no rounding)
    """
    # Load previously accumulated adjustments
    cumulative = {}
    if os.path.exists(CUMULATIVE_DIFF_FILE):
        with open(CUMULATIVE_DIFF_FILE) as f:
            for k, v in json.load(f).items():
                s, d, m = k.split("|", 2)
                cumulative[(s, d, m)] = v

    # Consume the new diff file — once only
    if os.path.exists(DIFF_FILE):
        new_diffs = _parse_diff_file(DIFF_FILE)
        if new_diffs:
            for key, v in new_diffs.items():
                cumulative[key] = cumulative.get(key, 0.0) + v
            # Persist before archiving so a crash doesn't lose the data
            with open(CUMULATIVE_DIFF_FILE, "w") as f:
                json.dump({f"{s}|{d}|{m}": v for (s, d, m), v in cumulative.items()}, f)
            # Archive the diff file so it is never re-applied
            os.makedirs(DIFF_ARCHIVE_DIR, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.move(DIFF_FILE, os.path.join(DIFF_ARCHIVE_DIR, f"diff_{ts}.xlsx"))
            print(f"[adj] Applied {len(new_diffs)} diff entries; archived to diff_archive/diff_{ts}.xlsx")
        else:
            print("[adj] diff.xlsx present but contained no non-zero entries — skipped.")
    else:
        # No new diff — cumulative already up-to-date, just persist (no-op if unchanged)
        with open(CUMULATIVE_DIFF_FILE, "w") as f:
            json.dump({f"{s}|{d}|{m}": v for (s, d, m), v in cumulative.items()}, f)

    return cumulative

# ── Template creation (first run) ──────────────────────────────────────────────
def create_template():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    h_fill = PatternFill("solid", fgColor="1a2744")
    h_font = Font(bold=True, color="FFFFFF")

    def sheet(name, headers):
        ws = wb.create_sheet(name)
        for c, h in enumerate(headers, 1):
            cell = ws.cell(1, c, h)
            cell.fill = h_fill
            cell.font = h_font
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[chr(64+c)].width = max(len(str(h))+4, 12)
        return ws

    sheet("Store Master",       ["Store", "Tag", "Cluster", "Ref Store"])
    sheet("Store Actuals",      ["Store", "Division"] + FY27_M)
    ws_g = sheet("Growth %",    ["Division", "Growth %"])
    for r, d in enumerate(["OVERALL"] + DIVS, 2):
        ws_g.cell(r, 1, d)
    sheet("NSO Opening Months", ["Store", "Opening Month"])
    sheet("AOP (Optional)",     ["Store","Division"] + FY28_M)

    wb.save(INPUT_FILE)
    print(f"[OK] Template created: {INPUT_FILE}")
    print("[INFO] Fill in your data and run again.")

# ── Input loading ──────────────────────────────────────────────────────────────
def load_inputs(input_file=None):
    xl = pd.ExcelFile(input_file or INPUT_FILE, engine="calamine")

    def clean(df, key):
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(subset=[key])
        df[key] = df[key].astype(str).str.strip()
        return df

    def parse(sheet, skip=3):
        return xl.parse(sheet, skiprows=skip)

    sm       = clean(parse("Store Master"),  "Store")
    actuals  = clean(parse("Store Actuals"), "Store")
    actuals["Division"] = actuals["Division"].astype(str).str.strip()

    growth   = parse("Growth %")
    growth.columns = [str(c).strip() for c in growth.columns]
    growth   = growth[growth.iloc[:, 0].notna()]
    growth   = growth[~growth.iloc[:, 0].astype(str).str.upper().str.startswith("HOW")]

    nso_raw  = parse("NSO Opening Months")
    nso_raw.columns = [str(c).strip() for c in nso_raw.columns]
    # Column may be "Store Code" or "Store"
    if "Store Code" in nso_raw.columns:
        nso_raw = nso_raw.rename(columns={"Store Code": "Store"})
    nso_df   = clean(nso_raw, "Store")

    aop_df = None
    aop_sheet = "AOP (Optional)" if "AOP (Optional)" in xl.sheet_names else (
                "Mar27 Targets" if "Mar27 Targets" in xl.sheet_names else None)
    if aop_sheet:
        tgt_raw = xl.parse(aop_sheet, header=0, skiprows=[1])
        tgt_raw.columns = [str(c).strip() for c in tgt_raw.columns]
        tgt_raw = tgt_raw.dropna(subset=["Store"])
        tgt_raw["Store"] = tgt_raw["Store"].astype(str).str.strip()
        if "Division" not in tgt_raw.columns:
            # Legacy wide layout: Store + one column per division, Mar'27 only.
            tgt_raw = tgt_raw.melt(id_vars=["Store"], value_vars=[d for d in DIVS if d in tgt_raw.columns],
                                   var_name="Division", value_name="Mar'27")
        aop_df = tgt_raw

    return sm, actuals, growth, nso_df, aop_df

# ── Growth rate lookup ─────────────────────────────────────────────────────────
def build_growth_map(growth_df):
    """
    Returns {div_upper: {fy28_month: rate}} where rate is a decimal (e.g. 0.06).
    Growth % sheet has Division in col 0, then one column per FY28 month.
    Blank division cells fall back to OVERALL for that month.
    """
    col_d  = growth_df.columns[0]
    months = [c for c in growth_df.columns[1:] if str(c).strip() in FY28_M]

    raw = {}
    for _, row in growth_df.iterrows():
        d = str(row[col_d]).strip().upper()
        raw[d] = {}
        for m in months:
            v = row.get(m)
            if pd.notna(v):
                v = float(v)
                raw[d][m] = v / 100.0 if abs(v) > 1 else v

    overall = raw.get("OVERALL", {})
    # Fallback rate for any FY28_M month not present in the Growth % sheet
    # (e.g. Mar'27 when sheet only covers Apr'27-Mar'28): use average of all
    # defined overall rates, so the missing month inherits the same assumption.
    fallback = (sum(overall.values()) / len(overall)) if overall else 0.0

    gmap = {}
    for div in DIVS:
        gmap[div.upper()] = {}
        div_raw = raw.get(div.upper(), {})
        for m in FY28_M:
            rate = div_raw.get(m) if div_raw.get(m) is not None \
                   else overall.get(m, fallback)
            gmap[div.upper()][m] = rate if rate is not None else fallback
    return gmap

# ── Actuals pivot ──────────────────────────────────────────────────────────────
def pivot_actuals(actuals_df, aop_df=None, open_months=None):
    """Returns (actuals_pivot, mar27_anchor).

    actuals_pivot: {store: {div: {fy27_month: value}}} — the REAL synced FY27
    actuals grid only. A month in `open_months` (defaults to _open_months(),
    i.e. real today) is skipped entirely - any value synced for it stays
    untouched in the DB, but the engine treats that month as 0.0 (its normal
    "no data yet" default) until the real calendar moves past it. This is
    what every "base for FY28 month X" lookup throughout the engine reads
    (pass1_forecasts, the store_base dicts in pass1b/pass2, build_df's Base
    column) - since FY27_M's last entry ("Mar'27") pairs with FY28_M's last
    entry ("Mar'28") wherever the engine zips the two lists, this alone is
    what makes Mar'28 wait for a REAL, closed Mar'27 actual and never see
    the AOP-override figure below.

    mar27_anchor: {store: {div: value}} — Mar'27's OWN forecast anchor
    (FY28_M[0], used only by the Ramp/NSO passes to seed their MoM chain
    when Mar'27 itself has no real actual yet). If aop_df is provided (AOP
    (Optional) sheet), its Mar'27 column patches this anchor for any
    store-div where the real actual is zero/missing (fallback mode,
    unchanged from the legacy Mar27 Targets behaviour). Deliberately a
    SEPARATE dict from actuals_pivot, not written into it: the AOP override
    is a planner's deliberate figure for Mar'27 itself, valid as Mar'27's
    own anchor, but not a substitute for a real closed actual that Mar'28
    should be allowed to grow from — confirmed with the user 2026-08-27:
    "We will make mar 28 when we will get mar 27 actuals not based out of
    mar 27 aop." Apr'27..Mar'28 columns are handled separately by
    build_aop_overrides() as direct AOP forecast overrides.
    """
    open_months = _open_months() if open_months is None else open_months
    out = {}
    for _, row in actuals_df.iterrows():
        s = str(row["Store"]).strip()
        d = str(row["Division"]).strip()
        if s not in out:
            out[s] = {}
        # Store Actuals can now carry more than one row per (store, division) -
        # one per Attribute/ATTRIBUTE1 (see to_workbook.py) - so this has to
        # ACCUMULATE across rows, not assign. A plain `out[s][d] = {...}`
        # silently dropped every attribute's total but the last one iterated,
        # corrupting the real forecast base the moment a store/division had
        # more than one attribute row - the quarter-specific attribute filter
        # in get_file_info()'s own base_sales is a separate, LFL-preview-only
        # concern; the actual forecast engine always wants the full total.
        vals = out[s].setdefault(d, {m: 0.0 for m in FY27_M})
        for m in FY27_M:
            if m in open_months:
                continue
            v = row.get(m)
            if v is not None and v == v:  # not NaN
                vals[m] += float(v)

    mar27_anchor = {s: {d: vals.get("Mar'27", 0.0) for d, vals in divs.items()} for s, divs in out.items()}
    if aop_df is not None and "Mar'27" in aop_df.columns:
        for _, row in aop_df.iterrows():
            s = str(row["Store"]).strip()
            d = str(row.get("Division","")).strip().upper()
            if d not in DIVS or pd.isna(row.get("Mar'27")):
                continue
            val = float(row["Mar'27"])
            if val == 0:
                continue
            if s not in mar27_anchor:
                mar27_anchor[s] = {}
            if mar27_anchor[s].get(d, 0.0) == 0.0:
                mar27_anchor[s][d] = val

    return out, mar27_anchor


def build_aop_overrides(aop_df):
    """{(store, div, fy28_month): value} from the AOP (Optional) sheet's Mar'27..Mar'28
    columns — a direct, absolute override of the final AOP forecast for that cell
    (build_df() applies it in place of engine_val + adjustments entirely, not
    blended with them). Blank cells are left alone (the engine computes them as
    usual).

    Mar'27 WAS excluded here (pre-2026-08-27) on the theory that it's purely an
    actuals fallback, handled by pivot_actuals() instead - that meant a Mar'27
    override typed into the AOP (Optional) sheet was silently dropped before it
    ever reached build_df(), which otherwise already applies an override for
    any FY28 month unconditionally. Mar'27 is a real forecast month like any
    other and needs to be override-able the same way. Note pivot_actuals()
    separately reads this SAME sheet's Mar'27 column too, but only as an
    actuals-BASE fallback for a store/div whose real actual is zero/missing -
    that's a distinct use of the same source cell, not something this override
    conflicts with (Base and Forecast are different columns downstream)."""
    overrides = {}
    if aop_df is None:
        return overrides
    override_months = [m for m in FY28_M if m in aop_df.columns]
    for _, row in aop_df.iterrows():
        s = str(row["Store"]).strip()
        d = str(row.get("Division","")).strip().upper()
        if d not in DIVS:
            continue
        for m in override_months:
            v = row.get(m)
            if pd.notna(v):
                overrides[(s, d, m)] = float(v)
    return overrides

# ── Pass 1 — LfL forecasts (own actuals × growth%) ────────────────────────────
def pass1_forecasts(store_info, actuals_pivot, gmap):
    """{store: {div: {fy28_month: value}}} for LfL stores only."""
    fc = {}
    for store, si in store_info.items():
        if si["tag"] not in LFL_TAGS:
            continue
        fc[store] = {}
        for div in DIVS:
            rates = gmap.get(div.upper(), {})
            fc[store][div] = {}
            for fy27m, fy28m in zip(FY27_M, FY28_M):
                base = actuals_pivot.get(store, {}).get(div, {}).get(fy27m, 0.0)
                g    = rates.get(fy28m, 0.0)
                fc[store][div][fy28m] = base * (1.0 + g)
    return fc


# ── Pass 1b — Ramp forecasts (ref store cont% × scale × growth%) ───────────────
def _ref_fc_for_store(ref, store_info, actuals_pivot, lfl_fc, gmap, mar27_anchor=None):
    """
    Return a {div: {fy28m: value}} forecast for a ref store.
    Uses lfl_fc if available; otherwise builds actuals x growth% directly
    (handles the case where ref store is itself a Ramp store).
    """
    if ref in lfl_fc:
        return lfl_fc[ref]
    mar27_anchor = mar27_anchor or {}
    # Ref is a Ramp or unknown store — build a simple actuals x growth% forecast
    fc = {}
    for div in DIVS:
        rates = gmap.get(div.upper(), {})
        actual_mar27 = mar27_anchor.get(ref, {}).get(div, 0.0)
        fc[div] = {}
        for fy27m, fy28m in zip(FY27_M, FY28_M):
            if fy28m == FY28_M[0] and actual_mar27 > 0:
                fc[div][fy28m] = actual_mar27
            else:
                base = actuals_pivot.get(ref, {}).get(div, {}).get(fy27m, 0.0)
                g    = rates.get(fy28m, 0.0)
                fc[div][fy28m] = base * (1.0 + g)
    return fc


def pass1b_ramp_forecasts(store_info, actuals_pivot, lfl_fc, gmap, open_months=None, mar27_anchor=None):
    """
    For Ramp stores:
    - Months WITH FY27 actuals  → exactly base × (1 + growth%)
    - Months WITHOUT FY27 actuals (zero base):
        * FY27-Q1 / FY27-Q2: store was still ramping in FY27 so some early months
          have no actuals. Project those months using the ref store's monthly
          division contribution %, scaled to the store's known-actuals magnitude,
          then × (1 + growth%). Base stays 0 so deviation is positive.
        * All other Ramp tags (FY26-*): always have full FY27 actuals; zero stays zero.

    A month in `open_months` (defaults to _open_months(), i.e. real today) is
    excluded from the ref-store MoM chain below even when prev_derived>0 -
    that chain is a genuine TY assumption (project this month from the ref
    store's pattern), which is only valid once real LY data could exist at
    all. A month that hasn't closed yet has no LY by definition, not "LY
    happens to be missing" - the two look identical in actual_base (both
    0.0) but only the latter is fair game to bridge with the ref store's
    curve. Doesn't touch the actual_base>0 branch just below: that only
    fires on a real (or deliberately overridden) base value, never a guess.
    """
    PROJ_MISSING = {"FY27 - Q1", "FY27 - Q2"}
    open_months = _open_months() if open_months is None else open_months
    mar27_anchor = mar27_anchor or {}

    fc = {}
    for store, si in store_info.items():
        if si["tag"] not in RAMP_TAGS:
            continue

        ref     = si.get("ref_store") or NSO_REF
        ref_fcd = _ref_fc_for_store(ref, store_info, actuals_pivot, lfl_fc, gmap, mar27_anchor)
        fc[store] = {}

        for div in DIVS:
            rates = gmap.get(div.upper(), {})

            # Ref store monthly contribution shares for this division
            ref_fc_ann = sum(ref_fcd.get(div, {}).get(m, 0.0) for m in FY28_M)
            ref_contrib = {
                m: (ref_fcd.get(div, {}).get(m, 0.0) / ref_fc_ann if ref_fc_ann > 0 else 1.0 / 12)
                for m in FY28_M
            }

            # Store's FY27 base per (FY28) month
            store_base = {
                fy28m: actuals_pivot.get(store, {}).get(div, {}).get(fy27m, 0.0)
                for fy27m, fy28m in zip(FY27_M, FY28_M)
            }

            # Mar'27 anchor for this store-div (FY28_M[0]) - real actual, or the
            # AOP-override figure if that's all there is (see pivot_actuals()).
            actual_mar27 = mar27_anchor.get(store, {}).get(div, 0.0)

            # Ref store forecast values per FY28 month (for MoM chaining)
            ref_div_fc = ref_fcd.get(div, {})

            fc[store][div] = {}
            prev_derived = 0.0   # running value for MoM chain
            # (ref_val, derived_val) at the last month the ref store had real data,
            # within the current MoM-chain run — lets the chain survive a gap in the
            # ref store's own data and resume once the ref store's data reappears,
            # instead of permanently locking at 0 the first time ref_curr is 0.
            ref_anchor = None
            for i, (fy27m, fy28m) in enumerate(zip(FY27_M, FY28_M)):
                actual_base = store_base[fy28m]
                g_m         = rates.get(fy28m, 0.0)

                # Previous month's FY27 base (to detect opening-transition months)
                prev_actual_base = store_base.get(FY28_M[i - 1], 0.0) if i > 0 else 1.0

                if fy28m == FY28_M[0] and actual_mar27 > 0:
                    val = actual_mar27
                    ref_anchor = None
                elif actual_base > 0 and (prev_derived == 0 or (
                        prev_actual_base > 0
                        and actual_base / prev_actual_base <= ANOMALY_DEV_THRESHOLD)):
                    # Consecutive bases are comparable (no distorted opening-month jump),
                    # OR chain hasn't started yet — apply standard growth%
                    val = actual_base * (1.0 + g_m)
                    ref_anchor = None
                elif prev_derived > 0 and si["tag"] in PROJ_MISSING and fy27m not in open_months:
                    # MoM chain: either actual_base==0 (no FY27 history) OR
                    # prev_actual_base==0 (opening-transition month — deviation is 0%
                    # for this store, so use ref store's MoM ratio instead)
                    ref_curr = ref_div_fc.get(fy28m, 0.0)
                    if ref_anchor is None:
                        prev_fy28m = FY28_M[i - 1]
                        ref_anchor = (ref_div_fc.get(prev_fy28m, 0.0), prev_derived)
                    anchor_ref_val, anchor_derived_val = ref_anchor
                    if ref_curr > 0 and anchor_ref_val > 0:
                        val = anchor_derived_val * (ref_curr / anchor_ref_val)
                        ref_anchor = (ref_curr, val)
                    else:
                        # Ref store itself has no data this month (a gap in its own
                        # actuals) — hold the derived value flat rather than forcing
                        # it toward zero, and keep the existing anchor so the chain
                        # can resume the moment the ref store's data reappears.
                        val = prev_derived
                else:
                    val = 0.0
                    ref_anchor = None

                fc[store][div][fy28m] = val
                prev_derived = val

    return fc

# ── NSO ramp for one store ─────────────────────────────────────────────────────
def nso_ramp(store, ref_store, open_month, ref_fc):
    """
    Annual target = NSO_TARGET Lakhs distributed by ref store's monthly pattern.
    M1 (go-live) = 50% of proportional month; M2+ = 100%.
    Division split: ref store's division mix per month.
    """
    if open_month not in M_IDX:
        print(f"[WARN] Unknown opening month '{open_month}' for {store} — defaulting to Apr'27")
        open_month = "Apr'27"
    open_idx = M_IDX[open_month]

    if ref_store not in ref_fc:
        print(f"[WARN] Ref store '{ref_store}' missing for NSO {store} -> zeros")
        return {d: {m: 0.0 for m in FY28_M} for d in DIVS}

    ref = ref_fc[ref_store]
    ref_total = {m: sum(ref[d].get(m, 0.0) for d in DIVS) for m in FY28_M}

    S = sum(ref_total[m] for m in FY28_M[open_idx:])
    if S == 0:
        print(f"[WARN] Ref store '{ref_store}' has zero FY28 from {open_month} -> zeros for {store}")
        return {d: {m: 0.0 for m in FY28_M} for d in DIVS}

    result = {d: {} for d in DIVS}
    for i, m in enumerate(FY28_M):
        if i < open_idx:
            for d in DIVS:
                result[d][m] = 0.0
            continue

        weight      = ref_total[m] / S
        month_total = NSO_TARGET * weight * (0.5 if i == open_idx else 1.0)
        rt          = ref_total[m]

        for d in DIVS:
            div_pct    = ref[d].get(m, 0.0) / rt if rt > 0 else 1.0 / len(DIVS)
            result[d][m] = month_total * div_pct

    return result

# ── Pass 2 — NSO forecasts ─────────────────────────────────────────────────────
def pass2_forecasts(store_info, nso_open, ref_fc, actuals_pivot, gmap, mar27_anchor=None):
    """
    750L ramp formula for NSO stores.
    Floor: for stores that already have FY27 actuals (named NSO), ensure
    Forecast >= Base x (1+growth%) in every month so deviation is never negative.
    MoM chain: when base=0 or opening-transition (prev base=0) and a Mar'27 anchor
    exists, use ref store's MoM ratio x prev_derived instead of the ramp formula.
    """
    mar27_anchor = mar27_anchor or {}
    fc = {}
    for store, si in store_info.items():
        if si["tag"] not in NSO_TAGS:
            continue
        is_unnamed = any(store.startswith(p) for p in UNNAMED_PFX)
        ref    = NSO_REF if is_unnamed else (si.get("ref_store") or NSO_REF)
        open_m = nso_open.get(store, "")
        if not open_m or open_m.lower() in ("nan", "none", ""):
            # No opening month = store not opening this year — skip entirely
            continue
        ramp   = nso_ramp(store, ref, open_m, ref_fc)

        # Ref store monthly forecast for MoM chaining (ref_fc has lfl+ramp combined)
        ref_fcd = _ref_fc_for_store(ref, store_info, actuals_pivot, ref_fc, gmap, mar27_anchor)

        fc[store] = {}
        for div in DIVS:
            rates        = gmap.get(div.upper(), {})
            actual_mar27 = mar27_anchor.get(store, {}).get(div, 0.0)
            ref_div_fc   = ref_fcd.get(div, {})

            # FY27 base per FY28 month for this store-div
            store_base = {
                fy28m: actuals_pivot.get(store, {}).get(div, {}).get(fy27m, 0.0)
                for fy27m, fy28m in zip(FY27_M, FY28_M)
            }

            fc[store][div] = {}
            prev_derived = 0.0
            for i, (fy27m, fy28m) in enumerate(zip(FY27_M, FY28_M)):
                prev_actual_base = store_base.get(FY28_M[i - 1], 0.0) if i > 0 else 1.0
                base_m  = store_base[fy28m]
                g_m     = rates.get(fy28m, 0.0)
                floor_m = base_m * (1.0 + g_m)
                ramp_v  = ramp.get(div, {}).get(fy28m, 0.0)

                if fy28m == FY28_M[0] and actual_mar27 > 0:
                    val = actual_mar27
                elif base_m > 0 and (prev_derived == 0 or (
                        prev_actual_base > 0
                        and base_m / prev_actual_base <= ANOMALY_DEV_THRESHOLD)):
                    # Stable consecutive FY27 base — use max(ramp, floor)
                    val = max(ramp_v, floor_m)
                elif prev_derived > 0 and (base_m == 0 or prev_actual_base == 0):
                    # Base=0 OR opening-transition month (prev base=0, own deviation=0%)
                    # → chain from ref store's MoM ratio instead of ramp
                    prev_fy28m = FY28_M[i - 1]
                    ref_prev   = ref_div_fc.get(prev_fy28m, 0.0)
                    ref_curr   = ref_div_fc.get(fy28m, 0.0)
                    mom_ratio  = (ref_curr / ref_prev) if ref_prev > 0 else 1.0
                    val        = prev_derived * mom_ratio
                else:
                    val = max(ramp_v, floor_m)

                fc[store][div][fy28m] = val
                prev_derived = val

    return fc

# ── Build output DataFrame ─────────────────────────────────────────────────────
def build_df(store_info, actuals_pivot, all_fc, aop_overrides=None):
    """Assemble the flat forecast DataFrame.

    For every concat listed in any historical diff sheet:
        forecast = engine_value + cumulative_adjustment   (exact float64, no rounding)
    All other concats carry the engine-computed value unchanged.

    aop_overrides ({(store,div,fy28_month): value}, from the AOP (Optional) sheet)
    takes priority over the diff adjustment for that exact cell — the user has
    typed in the AOP number they want, so it is used as-is.
    """
    is_named = lambda s: not any(s.startswith(p) for p in UNNAMED_PFX)

    adjustments = _load_adjustments()
    aop_overrides = aop_overrides or {}

    rows = []
    for store, si in store_info.items():
        for div in DIVS:
            row = {
                "Store":    store,
                "Tag":      si.get("tag", ""),
                "Cluster":  si.get("cluster", ""),
                "Division": div,
            }
            for fy27m, fy28m in zip(FY27_M, FY28_M):
                base       = actuals_pivot.get(store, {}).get(div, {}).get(fy27m, 0.0)
                engine_val = all_fc.get(store, {}).get(div, {}).get(fy28m, 0.0)

                # AOP (Optional) override wins outright; otherwise engine + cumulative diff adjustment
                key = (store, div, fy28m)
                if key in aop_overrides:
                    fcst = aop_overrides[key]
                else:
                    fcst = engine_val + adjustments.get(key, 0.0)

                base       = _round2(base)
                engine_val = _round2(engine_val)
                fcst       = _round2(fcst)

                row[f"{fy28m} | Base"]            = base
                row[f"{fy28m} | Engine Forecast"] = engine_val   # pre-adjustment, exact growth%
                row[f"{fy28m} | Forecast"]        = fcst         # engine + cumulative adjustment
                if is_named(store) and base > 0 and (fcst - base) / base > ANOMALY_DEV_THRESHOLD:
                    row[f"{fy28m} | Deviation"] = 0.0
                else:
                    row[f"{fy28m} | Deviation"] = _round2(fcst - base)
            rows.append(row)
    return pd.DataFrame(rows)

# ── Excel palette definitions ──────────────────────────────────────────────────
# Each palette: primary (headers), mid (totals/thick border), light (row tint),
#               char (body text), border_thin (cell border colour).
EXCEL_PALETTES = {
    # ── Blues ──────────────────────────────────────────────────────────────────
    "classic":    {"primary":"1F3864","mid":"2F5597","light":"EEF3FB","light2":"E5EDF7","total_row":"D8E4F4","sep":"DDE6F2","char":"1A2332","border":"C5D0E0"},
    "royal":      {"primary":"1A56DB","mid":"2970FF","light":"EBF5FF","light2":"DBEAFE","total_row":"BFDBFE","sep":"DBEAFE","char":"1E3A5F","border":"BFDBFE"},
    "steel":      {"primary":"2E4057","mid":"3B5068","light":"EDF2F7","light2":"E2E8F0","total_row":"CBD5E1","sep":"E2E8F0","char":"1A2B3C","border":"CBD5E1"},
    "teal":       {"primary":"0F4C5C","mid":"0D6E83","light":"E6F7FA","light2":"CCEFF5","total_row":"99DDE8","sep":"CCEFF5","char":"072B36","border":"99DDE8"},
    # ── Greens ─────────────────────────────────────────────────────────────────
    "emerald":    {"primary":"1E293B","mid":"334155","light":"ECFDF5","light2":"D1FAE5","total_row":"A7F3D0","sep":"D1FAE5","char":"0F172A","border":"CBD5E1"},
    "forest":     {"primary":"14532D","mid":"166534","light":"F0FDF4","light2":"DCFCE7","total_row":"BBF7D0","sep":"D1FAE5","char":"052E16","border":"86EFAC"},
    "sage":       {"primary":"3D6B4F","mid":"4D8763","light":"F0FAF4","light2":"DCFAE4","total_row":"BBF4CF","sep":"DCFAE4","char":"1E3A28","border":"86EFB0"},
    "olive":      {"primary":"3B3A1F","mid":"5A5728","light":"FAFAF0","light2":"F5F4DC","total_row":"EBEBBB","sep":"F5F4DC","char":"1E1E0A","border":"D4D4A0"},
    # ── Warm ───────────────────────────────────────────────────────────────────
    "amber":      {"primary":"0F172A","mid":"1E293B","light":"FFFBEB","light2":"FEF3C7","total_row":"FDE68A","sep":"FEF3C7","char":"0C1222","border":"E7E5E4"},
    "burnt":      {"primary":"7C2D12","mid":"9A3412","light":"FFF7ED","light2":"FFEDD5","total_row":"FED7AA","sep":"FFEDD5","char":"431407","border":"FDBA74"},
    "burgundy":   {"primary":"6B1A2A","mid":"8B2038","light":"FFF1F4","light2":"FFE4EA","total_row":"FECDD3","sep":"FFE4EA","char":"3B0A14","border":"FDA4AF"},
    "coral":      {"primary":"3B1F6A","mid":"5B2D9E","light":"FAF5FF","light2":"F3E8FF","total_row":"E9D5FF","sep":"EDE9FE","char":"1A0A2E","border":"DDD6FE"},
    # ── Neutrals ───────────────────────────────────────────────────────────────
    "charcoal":   {"primary":"1C1C1E","mid":"3A3A3C","light":"F5F5F7","light2":"EBEBED","total_row":"D8D8DC","sep":"EBEBED","char":"111113","border":"C7C7CC"},
    "slate":      {"primary":"334155","mid":"475569","light":"F8FAFC","light2":"F1F5F9","total_row":"E2E8F0","sep":"F1F5F9","char":"1E293B","border":"CBD5E1"},
    "warm_gray":  {"primary":"44403C","mid":"57534E","light":"FAFAF9","light2":"F5F5F4","total_row":"E7E5E4","sep":"F5F5F4","char":"292524","border":"D6D3D1"},
}

# ── Excel output ───────────────────────────────────────────────────────────────
def _write_flat_detail_sheet(wb, df):
    """Append a 'Flat Detail' sheet — plain table, autofilter, good for pivot/debug."""
    from openpyxl.styles import PatternFill, Font, Alignment
    ws = wb.create_sheet("Flat Detail")

    H_FILL = PatternFill("solid", fgColor="374151")
    H_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    D_FONT = Font(name="Calibri", size=10)
    ALN_C  = Alignment(horizontal="center", vertical="center")
    ALN_R  = Alignment(horizontal="right",  vertical="center")

    cols = list(df.columns)
    label_cols = ["Store", "Tag", "Cluster", "Division"]

    for ci, col in enumerate(cols, 1):
        cell = ws.cell(row=1, column=ci, value=col)
        cell.fill  = H_FILL
        cell.font  = H_FONT
        cell.alignment = ALN_C
        # column width
        ws.column_dimensions[get_column_letter(ci)].width = (
            20 if col in ("Store", "Tag") else
            14 if col == "Cluster" else
            9  if col == "Division" else
            12
        )

    for ri, (_, row) in enumerate(df.iterrows(), 2):
        for ci, col in enumerate(cols, 1):
            val = row[col]
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.font = D_FONT
            if col not in label_cols:
                cell.number_format = "#,##0.0"
                cell.alignment = ALN_R
            else:
                cell.alignment = ALN_C

    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes    = "A2"
    ws.sheet_state     = "visible"


def write_excel(df, output_file=None, palette="classic", include_debug=False):
    _out = output_file or OUTPUT_FILE
    os.makedirs(os.path.dirname(os.path.abspath(_out)), exist_ok=True)

    FY27_RAMP_TAGS = {"FY27 - Q1", "FY27 - Q2"}
    P   = EXCEL_PALETTES.get(palette, EXCEL_PALETTES["classic"])
    RED = "C0392B"

    # ── xlsxwriter workbook ───────────────────────────────────────────────────
    wb = xlsxwriter.Workbook(_out, {"strings_to_numbers": False, "use_zip64": True})

    # ── Pre-create all format objects ONCE ───────────────────────────────────
    def _f(**kw):
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter",
                "border": 1, "border_color": "#" + P["border"]}
        base.update(kw)
        return wb.add_format(base)

    def _fL(**kw):          # thick left border (month boundary)
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter",
                "border": 1, "border_color": "#" + P["border"],
                "left": 2, "left_color": "#" + P["mid"]}
        base.update(kw)
        return wb.add_format(base)

    NAVY  = "#" + P["primary"]
    MID   = "#" + P["mid"]
    LIGHT = "#" + P["light"]
    LIT2  = "#" + P["light2"]
    TOTR  = "#" + P["total_row"]
    SEPC  = "#" + P["sep"]
    WHITE = "#FFFFFF"
    CHAR  = "#" + P["char"]
    NUM   = "#,##0.0"
    PCT   = "0.0%"

    # Header
    f_hdr  = _f(bg_color=NAVY, font_color=WHITE, bold=True, align="center",
                text_wrap=True, border=1, border_color="#" + P["border"])

    # Detail / Tag & Division / Cluster sheets — data columns
    f_base     = _f(bg_color=WHITE,       font_color=CHAR,      align="right", num_format=NUM)
    f_fcst     = _f(bg_color=WHITE,       font_color=NAVY,      bold=True, align="right", num_format=NUM)
    f_dev_pos  = _f(bg_color=WHITE,       font_color="#1A6B3C", bold=True, align="right", num_format=NUM)
    f_dev_neg  = _f(bg_color=WHITE,       font_color="#"+RED,   bold=True, align="right", num_format=NUM)
    f_dev_zero = _f(bg_color="#F5F5F5",   font_color="#9E9E9E",            align="right", num_format=NUM)
    f_grw_pos  = _f(bg_color=WHITE,       font_color=NAVY,      bold=True, align="right", num_format=PCT)
    f_grw_neg  = _f(bg_color=WHITE,       font_color="#"+RED,   bold=True, align="right", num_format=PCT)
    f_grw_zero = _f(bg_color="#F5F5F5",   font_color="#9E9E9E",            align="right", num_format=PCT)

    # Thick-left variants (first col of each month group)
    f_baseL     = _fL(bg_color=WHITE,     font_color=CHAR,      align="right", num_format=NUM)
    f_fcstL     = _fL(bg_color=WHITE,     font_color=NAVY,      bold=True, align="right", num_format=NUM)
    f_dev_posL  = _fL(bg_color=WHITE,     font_color="#1A6B3C", bold=True, align="right", num_format=NUM)
    f_dev_negL  = _fL(bg_color=WHITE,     font_color="#"+RED,   bold=True, align="right", num_format=NUM)
    f_dev_zeroL = _fL(bg_color="#F5F5F5", font_color="#9E9E9E",            align="right", num_format=NUM)
    f_grw_posL  = _fL(bg_color=WHITE,     font_color=NAVY,      bold=True, align="right", num_format=PCT)
    f_grw_negL  = _fL(bg_color=WHITE,     font_color="#"+RED,   bold=True, align="right", num_format=PCT)
    f_grw_zeroL = _fL(bg_color="#F5F5F5", font_color="#9E9E9E",            align="right", num_format=PCT)

    # Metadata cell formats (alternating rows — Detail & Cluster sheets)
    f_odd_ctr  = _f(bg_color=LIGHT, font_color=CHAR, align="center")
    f_odd_left = _f(bg_color=LIGHT, font_color=CHAR, bold=True, align="left")
    f_even_ctr  = _f(bg_color=WHITE, font_color=CHAR, align="center")
    f_even_left = _f(bg_color=WHITE, font_color=CHAR, bold=True, align="left")

    # Tag & Division Summary — tag-coloured rows
    f_tag_lfl_left  = _f(bg_color="#EEF3FB", font_color=CHAR, bold=True, align="left")
    f_tag_lfl_ctr   = _f(bg_color="#EEF3FB", font_color=CHAR, bold=True, align="center")
    f_tag_ramp_left = _f(bg_color="#E5EDF7", font_color=CHAR, bold=True, align="left")
    f_tag_ramp_ctr  = _f(bg_color="#E5EDF7", font_color=CHAR, bold=True, align="center")
    f_tag_nso_left  = _f(bg_color="#EEF3FB", font_color=CHAR, bold=True, align="left")
    f_tag_nso_ctr   = _f(bg_color="#EEF3FB", font_color=CHAR, bold=True, align="center")

    # Division Summary — group label and row fills
    f_lfl_lbl  = _f(bg_color=NAVY, font_color=WHITE, bold=True, align="center")
    f_lfl_row  = _f(bg_color=LIGHT, font_color=CHAR, align="right", num_format=NUM)
    f_fy27_lbl = _f(bg_color=NAVY, font_color=WHITE, bold=True, align="center")
    f_fy27_row = _f(bg_color=LIT2, font_color=CHAR, align="right", num_format=NUM)
    f_nso_lbl  = _f(bg_color=NAVY, font_color=WHITE, bold=True, align="center")
    f_nso_row  = _f(bg_color=LIGHT, font_color=CHAR, align="right", num_format=NUM)
    f_tot_lbl  = _f(bg_color=MID,  font_color=WHITE, bold=True, align="center")
    f_tot_row  = _f(bg_color=TOTR, font_color=CHAR, bold=True, align="right", num_format=NUM)
    f_sep      = wb.add_format({"bg_color": SEPC, "top": 1, "bottom": 1,
                                "top_color": "#CBD8E8", "bottom_color": "#CBD8E8"})

    # Division summary — Growth% formats per group
    f_grw_lfl  = _f(bg_color=LIGHT, font_color=NAVY, bold=True, align="right", num_format=PCT)
    f_grw_fy27 = _f(bg_color=LIT2,  font_color=NAVY, bold=True, align="right", num_format=PCT)
    f_grw_nso  = _f(bg_color=LIGHT, font_color=NAVY, bold=True, align="right", num_format=PCT)
    f_grw_tot  = _f(bg_color=MID,   font_color=WHITE, bold=True, align="right", num_format=PCT)
    # Thick-left variants for div summary month boundaries
    f_lfl_rowL  = _fL(bg_color=LIGHT, font_color=CHAR, align="right", num_format=NUM)
    f_fy27_rowL = _fL(bg_color=LIT2,  font_color=CHAR, align="right", num_format=NUM)
    f_nso_rowL  = _fL(bg_color=LIGHT, font_color=CHAR, align="right", num_format=NUM)
    f_tot_rowL  = _fL(bg_color=TOTR,  font_color=CHAR, bold=True, align="right", num_format=NUM)
    f_grw_lflL  = _fL(bg_color=LIGHT, font_color=NAVY, bold=True, align="right", num_format=PCT)
    f_grw_fy27L = _fL(bg_color=LIT2,  font_color=NAVY, bold=True, align="right", num_format=PCT)
    f_grw_nsoL  = _fL(bg_color=LIGHT, font_color=NAVY, bold=True, align="right", num_format=PCT)
    f_grw_totL  = _fL(bg_color=MID,   font_color=WHITE, bold=True, align="right", num_format=PCT)

    # Hdr thick-left variant
    f_hdr_L = _fL(bg_color=NAVY, font_color=WHITE, bold=True, align="center",
                  text_wrap=True, left=2, left_color="#" + P["mid"])

    # ── Helper: pick data format for a column header ──────────────────────────
    def _data_fmt(hdr, val, is_month_start=False):
        v = val if val is not None else 0.0
        if "| Base" in hdr or "| Engine" in hdr:
            return f_baseL     if is_month_start else f_base
        elif "| Forecast" in hdr:
            return f_fcstL     if is_month_start else f_fcst
        elif "| Deviation" in hdr:
            if v >  0.01: return f_dev_posL  if is_month_start else f_dev_pos
            elif v < -0.01: return f_dev_negL  if is_month_start else f_dev_neg
            else:           return f_dev_zeroL if is_month_start else f_dev_zero
        elif "| Growth%" in hdr:
            if v >  0.0005: return f_grw_posL  if is_month_start else f_grw_pos
            elif v < -0.0005: return f_grw_negL  if is_month_start else f_grw_neg
            else:             return f_grw_zeroL if is_month_start else f_grw_zero
        return f_base

    # ── Build aggregated sheets data ─────────────────────────────────────────
    agg_cols = {c: "sum" for c in df.columns if "|" in c}

    tag_div_df = df.groupby(["Tag", "Division"]).agg(agg_cols).reset_index()
    cluster_df = df.groupby(["Cluster", "Division"]).agg(agg_cols).reset_index()

    lfl_ramp_df = df[df["Tag"].isin(LFL_TAGS | (RAMP_TAGS - FY27_RAMP_TAGS))]
    fy27_new_df = df[df["Tag"].isin(FY27_RAMP_TAGS)]
    nso_agg_df  = df[df["Tag"].isin(NSO_TAGS)]

    # ── SHEET 1: Forecasted AOP Detail ───────────────────────────────────────
    ws1 = wb.add_worksheet("Forecasted AOP Detail")
    ws1.freeze_panes(1, 4)
    ws1.set_row(0, 34)

    cols1 = list(df.columns)
    meta_cols = ["Store", "Tag", "Cluster", "Division"]
    n_meta = len(meta_cols)

    # Build month-start set (cols whose 0-index is the first col of a month group)
    # stride=3 (Base, Engine Forecast, Forecast), Deviation isn't a month start
    # Actually stride over data: Base=month_start, Engine/Forecast/Deviation are within
    # Month boundary = every 4th col after meta (Base col of each month = col n_meta + 0, +4, +8 ...)
    month_start_cols1 = set()
    data_start = n_meta  # 0-indexed
    for mi in range(13):
        month_start_cols1.add(data_start + mi * 4)  # Base col of each month

    # Header row
    col_widths1 = [8, 13, 16, 22, 10]
    for ci, col in enumerate(cols1):
        is_ms = ci in month_start_cols1
        ws1.write(0, ci, col, f_hdr_L if is_ms and ci >= n_meta else f_hdr)
        if ci >= n_meta:
            ws1.set_column(ci, ci, 10.5)

    ws1.set_column(0, 0, 8)
    ws1.set_column(1, 1, 13)
    ws1.set_column(2, 2, 16)
    ws1.set_column(3, 3, 22)
    ws1.set_column(4, 4, 10)

    # Data rows
    tag_fmt_map = {}
    for t in LFL_TAGS:
        tag_fmt_map[t] = (f_tag_lfl_ctr, f_tag_lfl_left)
    for t in RAMP_TAGS - FY27_RAMP_TAGS:
        tag_fmt_map[t] = (f_tag_ramp_ctr, f_tag_ramp_left)
    for t in FY27_RAMP_TAGS:
        tag_fmt_map[t] = (f_tag_ramp_ctr, f_tag_ramp_left)
    for t in NSO_TAGS:
        tag_fmt_map[t] = (f_tag_nso_ctr, f_tag_nso_left)

    for ri, (_, row) in enumerate(df.iterrows(), 1):
        ws1.set_row(ri, 16)
        is_odd = (ri % 2 == 0)
        f_ctr  = f_odd_ctr  if is_odd else f_even_ctr
        f_left = f_odd_left if is_odd else f_even_left
        for ci, col in enumerate(cols1):
            val = row[col]
            if val != val: val = None  # NaN → None
            if ci < n_meta:
                ws1.write(ri, ci, val, f_left if ci == 1 else f_ctr)
            else:
                is_ms = ci in month_start_cols1
                hdr   = col
                fmt   = _data_fmt(hdr, val, is_ms)
                ws1.write(ri, ci, val, fmt)

    # ── SHEET 2: Tag & Division Summary ──────────────────────────────────────
    ws2 = wb.add_worksheet("Tag & Division Summary")
    ws2.freeze_panes(1, 2)
    ws2.set_row(0, 34)

    cols2 = list(tag_div_df.columns)
    month_start_cols2 = set()
    data_start2 = 2
    for mi in range(13):
        month_start_cols2.add(data_start2 + mi * 3)  # Base col of each month (stride=3: Base, Forecast, Deviation)

    ws2.set_column(0, 0, 18)
    ws2.set_column(1, 1, 11)
    for ci in range(2, len(cols2)):
        ws2.set_column(ci, ci, 10.5)

    for ci, col in enumerate(cols2):
        is_ms = ci in month_start_cols2
        ws2.write(0, ci, col, f_hdr_L if is_ms and ci >= data_start2 else f_hdr)

    for ri, (_, row) in enumerate(tag_div_df.iterrows(), 1):
        ws2.set_row(ri, 16)
        tag = str(row.get("Tag", "") or "")
        f_ctr, f_left = tag_fmt_map.get(tag, (f_even_ctr, f_even_left))
        for ci, col in enumerate(cols2):
            val = row[col]
            if val != val: val = None
            if ci < data_start2:
                ws2.write(ri, ci, val, f_left)
            else:
                is_ms = ci in month_start_cols2
                fmt   = _data_fmt(col, val, is_ms)
                ws2.write(ri, ci, val, fmt)

    # ── SHEET 3: Division Summary ─────────────────────────────────────────────
    ws3 = wb.add_worksheet("Division Summary")
    ws3.freeze_panes(1, 2)
    ws3.set_row(0, 34)

    div_meta = ["Division", "Store Group"]
    div_data_cols = []
    for m in FY28_M:
        div_data_cols += [f"{m} | Base", f"{m} | Forecast", f"{m} | Deviation", f"{m} | Growth%"]
    div_all_cols = div_meta + div_data_cols

    # Month-start set for div summary (stride=4: Base, Forecast, Deviation, Growth%)
    month_start_cols3 = set()
    for mi in range(13):
        month_start_cols3.add(2 + mi * 4)

    ws3.set_column(0, 0, 13)
    ws3.set_column(1, 1, 15)
    for ci, col in enumerate(div_all_cols):
        if ci >= 2:
            ws3.set_column(ci, ci, 8.0 if "Growth%" in col else 10.5)

    for ci, col in enumerate(div_all_cols):
        is_ms = ci in month_start_cols3
        ws3.write(0, ci, col, f_hdr_L if is_ms and ci >= 2 else f_hdr)

    GRP_FMTS = {
        "LfL + Ramp": (f_lfl_lbl,  f_lfl_row,  f_lfl_rowL,  f_grw_lfl,  f_grw_lflL),
        "FY27 New":   (f_fy27_lbl, f_fy27_row, f_fy27_rowL, f_grw_fy27, f_grw_fy27L),
        "NSO":        (f_nso_lbl,  f_nso_row,  f_nso_rowL,  f_grw_nso,  f_grw_nsoL),
        "Total":      (f_tot_lbl,  f_tot_row,  f_tot_rowL,  f_grw_tot,  f_grw_totL),
    }

    excel_row = 1
    for i_div, div in enumerate(DIVS):
        for grp_src, grp_name in [
            (lfl_ramp_df, "LfL + Ramp"),
            (fy27_new_df, "FY27 New"),
            (nso_agg_df,  "NSO"),
            (df,          "Total"),
        ]:
            sums = grp_src[grp_src["Division"] == div][list(agg_cols)].sum()
            f_lbl, f_row, f_rowL, f_grw, f_grwL = GRP_FMTS[grp_name]
            ws3.set_row(excel_row, 19)
            ws3.write(excel_row, 0, div, f_lbl)
            ws3.write(excel_row, 1, grp_name, f_lbl)
            for ci, col in enumerate(div_data_cols, 2):
                is_ms = ci in month_start_cols3
                if "| Growth%" in col:
                    # IFERROR formula: Forecast / Base - 1
                    # Col offsets within each 4-col block: base=0, fcst=1, dev=2, grw%=3
                    base_ci = ci - 3
                    fcst_ci = ci - 2
                    base_xl = xlsxwriter.utility.xl_col_to_name(base_ci)
                    fcst_xl = xlsxwriter.utility.xl_col_to_name(fcst_ci)
                    formula = f"=IFERROR({fcst_xl}{excel_row+1}/{base_xl}{excel_row+1}-1,0)"
                    ws3.write_formula(excel_row, ci, formula, f_grwL if is_ms else f_grw)
                else:
                    val = sums.get(col, 0.0)
                    if val != val: val = 0.0
                    ws3.write(excel_row, ci, val, f_rowL if is_ms else f_row)
            excel_row += 1

        # Separator row between divisions (not after last)
        if i_div < len(DIVS) - 1:
            ws3.set_row(excel_row, 4)
            for ci in range(len(div_all_cols)):
                ws3.write(excel_row, ci, None, f_sep)
            excel_row += 1

    # ── SHEET 4: Cluster Summary ──────────────────────────────────────────────
    ws4 = wb.add_worksheet("Cluster Summary")
    ws4.freeze_panes(1, 2)
    ws4.set_row(0, 34)

    cols4 = list(cluster_df.columns)
    month_start_cols4 = set()
    data_start4 = 2
    for mi in range(13):
        month_start_cols4.add(data_start4 + mi * 3)

    ws4.set_column(0, 0, 24)
    ws4.set_column(1, 1, 11)
    for ci in range(2, len(cols4)):
        ws4.set_column(ci, ci, 10.5)

    for ci, col in enumerate(cols4):
        is_ms = ci in month_start_cols4
        ws4.write(0, ci, col, f_hdr_L if is_ms and ci >= data_start4 else f_hdr)

    for ri, (_, row) in enumerate(cluster_df.iterrows(), 1):
        ws4.set_row(ri, 16)
        is_odd = (ri % 2 == 0)
        f_ctr  = f_odd_ctr  if is_odd else f_even_ctr
        f_left = f_odd_left if is_odd else f_even_left
        for ci, col in enumerate(cols4):
            val = row[col]
            if val != val: val = None
            if ci < data_start4:
                ws4.write(ri, ci, val, f_left)
            else:
                is_ms = ci in month_start_cols4
                fmt   = _data_fmt(col, val, is_ms)
                ws4.write(ri, ci, val, fmt)

    # ── SHEET 5: Flat Detail (optional debug) ─────────────────────────────────
    if include_debug:
        ws5 = wb.add_worksheet("Flat Detail")
        ws5.freeze_panes(1, 0)
        f_hdr5  = wb.add_format({"font_name":"Calibri","font_size":10,"bold":True,
                                  "bg_color":"#374151","font_color":"#FFFFFF","align":"center","valign":"vcenter"})
        f_lbl5  = wb.add_format({"font_name":"Calibri","font_size":10,"align":"center","valign":"vcenter"})
        f_num5  = wb.add_format({"font_name":"Calibri","font_size":10,"align":"right","valign":"vcenter","num_format":"#,##0.0"})
        label_cols5 = {"Store","Tag","Cluster","Division"}
        cols5 = list(df.columns)
        for ci, col in enumerate(cols5):
            ws5.write(0, ci, col, f_hdr5)
            ws5.set_column(ci, ci,
                20 if col in ("Store","Tag") else
                14 if col == "Cluster" else
                 9 if col == "Division" else 12)
        for ri, (_, row) in enumerate(df.iterrows(), 1):
            for ci, col in enumerate(cols5):
                val = row[col]
                if val != val: val = None
                ws5.write(ri, ci, val, f_lbl5 if col in label_cols5 else f_num5)
        ws5.autofilter(0, 0, len(df), len(cols5) - 1)

    wb.close()
    print(f"[OK] Excel -> {_out}")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if not os.path.exists(INPUT_FILE):
        print(f"[INFO] {INPUT_FILE} not found. Creating template...")
        create_template()
        return

    print("[OK] Loading inputs...")
    sm, actuals_df, growth_df, nso_df, aop_df = load_inputs(None)

    store_info = {}
    for _, row in sm.iterrows():
        store = str(row["Store"]).strip()
        store_info[store] = {
            "tag":       str(row.get("Tag","") or "").strip(),
            "cluster":   str(row.get("Cluster","") or "").strip(),
            "ref_store": str(row.get("Ref Store","") or "").strip(),
        }

    nso_open     = {str(r["Store"]).strip(): str(r["Opening Month"]).strip()
                    for _, r in nso_df.iterrows()}
    actuals_pivot, mar27_anchor = pivot_actuals(actuals_df, aop_df)
    aop_overrides = build_aop_overrides(aop_df)

    n_lfl  = sum(1 for si in store_info.values() if si["tag"] in LFL_TAGS)
    n_ramp = sum(1 for si in store_info.values() if si["tag"] in RAMP_TAGS)
    n_nso  = sum(1 for si in store_info.values() if si["tag"] in NSO_TAGS)
    print(f"[OK] {len(store_info)} stores | {n_lfl} LfL | {n_ramp} Ramp | {n_nso} NSO")

    gmap = build_growth_map(growth_df)

    print("[OK] Pass 1  -> LfL stores: own actuals x growth%...")
    lfl_fc = pass1_forecasts(store_info, actuals_pivot, gmap)

    print("[OK] Pass 1b -> Ramp stores: ref store cont% x scale (growth% embedded)...")
    ramp_fc = pass1b_ramp_forecasts(store_info, actuals_pivot, lfl_fc, gmap, mar27_anchor=mar27_anchor)

    ref_fc = {**lfl_fc, **ramp_fc}

    print("[OK] Pass 2  -> NSO ramp (750L target, LAM ref for unnamed)...")
    nso_fc = pass2_forecasts(store_info, nso_open, ref_fc, actuals_pivot, gmap, mar27_anchor=mar27_anchor)

    all_fc = {**ref_fc, **nso_fc}

    print("[OK] Assembling rows...")
    df = build_df(store_info, actuals_pivot, all_fc, aop_overrides)

    print("[OK] Writing Excel...")
    write_excel(df)

    base_cols = [f"{m} | Base"    for m in FY28_M]
    fcst_cols = [f"{m} | Forecast" for m in FY28_M]
    total_base = df[base_cols].sum().sum()
    total_fcst = df[fcst_cols].sum().sum()
    ovr = (total_fcst/total_base-1)*100 if total_base else 0

    print(f"\n  Base (Actuals) : Rs {total_base/100:,.1f} Cr")
    print(f"  Forecasted AOP : Rs {total_fcst/100:,.1f} Cr")
    print(f"  Growth         : {ovr:+.1f}%")
    print(f"\n[OK] Done. Output -> {OUTPUT_DIR}/")

# ── API helpers ────────────────────────────────────────────────────────────────
def _build_results(df, store_info):
    base_cols = [f"{m} | Base"     for m in FY28_M]
    fcst_cols = [f"{m} | Forecast" for m in FY28_M]

    total_base = df[base_cols].sum().sum()
    total_fcst = df[fcst_cols].sum().sum()

    monthly = []
    for m in FY28_M:
        b = float(df[f"{m} | Base"].sum())
        f = float(df[f"{m} | Forecast"].sum())
        monthly.append({"month": m, "base": round(b/100, 2), "forecast": round(f/100, 2)})

    divisions = []
    for div in DIVS:
        ddf = df[df["Division"] == div]
        b = float(ddf[base_cols].sum().sum())
        f = float(ddf[fcst_cols].sum().sum())
        divisions.append({
            "division": div,
            "base":     round(b/100, 2),
            "forecast": round(f/100, 2),
            "growth_pct": round((f/b - 1)*100, 1) if b > 0 else 0.0,
        })

    type_totals = {"LfL": [0.0,0.0,set()], "Ramp": [0.0,0.0,set()], "NSO": [0.0,0.0,set()]}
    for store, si in store_info.items():
        tag = si["tag"]
        if tag in LFL_TAGS:   t = "LfL"
        elif tag in RAMP_TAGS: t = "Ramp"
        elif tag in NSO_TAGS:  t = "NSO"
        else:                  continue
        sdf = df[df["Store"] == store]
        type_totals[t][0] += float(sdf[base_cols].sum().sum())
        type_totals[t][1] += float(sdf[fcst_cols].sum().sum())
        type_totals[t][2].add(store)
    store_types = [
        {"type": t, "base": round(v[0]/100,2), "forecast": round(v[1]/100,2), "count": len(v[2])}
        for t, v in type_totals.items()
    ]

    store_agg = df.groupby("Store")[base_cols + fcst_cols].sum()
    store_agg["_base"]    = store_agg[base_cols].sum(axis=1)
    store_agg["_forecast"]= store_agg[fcst_cols].sum(axis=1)
    store_agg["_growth"]  = (store_agg["_forecast"]/store_agg["_base"] - 1)*100
    store_agg             = store_agg.replace([float("inf"), float("-inf")], 0).fillna(0)
    top = store_agg.nlargest(15, "_forecast").reset_index()
    top_stores = []
    for _, r in top.iterrows():
        s = r["Store"]
        top_stores.append({
            "store":      s,
            "cluster":    store_info.get(s, {}).get("cluster", ""),
            "tag":        store_info.get(s, {}).get("tag", ""),
            "base":       round(float(r["_base"])/100, 2),
            "forecast":   round(float(r["_forecast"])/100, 2),
            "growth_pct": round(float(r["_growth"]), 1),
        })

    return {
        "summary": {
            "base_cr":     round(total_base/100, 1),
            "forecast_cr": round(total_fcst/100, 1),
            "growth_pct":  round((total_fcst/total_base - 1)*100, 1) if total_base else 0.0,
            "n_stores":    len(store_info),
            "n_lfl":       sum(1 for si in store_info.values() if si["tag"] in LFL_TAGS),
            "n_ramp":      sum(1 for si in store_info.values() if si["tag"] in RAMP_TAGS),
            "n_nso":       sum(1 for si in store_info.values() if si["tag"] in NSO_TAGS),
        },
        "monthly":     monthly,
        "divisions":   divisions,
        "store_types": store_types,
        "top_stores":  top_stores,
    }


def run_engine(input_file, output_file, palette="classic", detail_file=None, include_debug=False, growth_overrides=None, overall_override=None):
    """Called by the web API. Returns results dict and writes Excel.
    growth_overrides: optional {division: {month: rate_pct}} — overrides gmap values
      before forecasting.  Rates are in percent (e.g. 8.5 means 8.5 %, not 0.085).
    overall_override: optional {month: rate_pct} — fallback applied to any div/month
      not already covered by growth_overrides.
    If detail_file is given, also saves the full row-level DataFrame as JSON there.
    If include_debug is True, a 'Flat Detail' sheet is added to the Excel workbook.
    """
    sm, actuals_df, growth_df, nso_df, aop_df = load_inputs(input_file)

    store_info = {}
    for _, row in sm.iterrows():
        store = str(row["Store"]).strip()
        store_info[store] = {
            "tag":       str(row.get("Tag","") or "").strip(),
            "cluster":   str(row.get("Cluster","") or "").strip(),
            "ref_store": str(row.get("Ref Store","") or "").strip(),
        }

    nso_open      = {str(r["Store"]).strip(): str(r["Opening Month"]).strip()
                     for _, r in nso_df.iterrows()}
    actuals_pivot, mar27_anchor = pivot_actuals(actuals_df, aop_df)
    aop_overrides = build_aop_overrides(aop_df)
    gmap          = build_growth_map(growth_df)
    if growth_overrides:
        for div, months in growth_overrides.items():
            if div in gmap:
                for month, rate_pct in months.items():
                    if month in gmap[div]:
                        gmap[div][month] = float(rate_pct) / 100.0
    lfl_fc        = pass1_forecasts(store_info, actuals_pivot, gmap)
    ramp_fc       = pass1b_ramp_forecasts(store_info, actuals_pivot, lfl_fc, gmap, mar27_anchor=mar27_anchor)
    ref_fc        = {**lfl_fc, **ramp_fc}
    nso_fc        = pass2_forecasts(store_info, nso_open, ref_fc, actuals_pivot, gmap, mar27_anchor=mar27_anchor)
    all_fc        = {**ref_fc, **nso_fc}
    df            = build_df(store_info, actuals_pivot, all_fc, aop_overrides)

    # overall_override: adjust the UNFIXED divisions (those not in growth_overrides for
    # that month) so the blended LfL growth hits the target exactly, while leaving
    # explicitly-set division rates unchanged and NSO/Ramp stores untouched.
    # Growth % inputs govern LfL stores only, so the overall target is a LfL-level target.
    if overall_override:
        lfl_mask = df['Tag'].isin(LFL_TAGS)
        for month, target_pct in overall_override.items():
            col_base = f"{month} | Base"
            col_eng  = f"{month} | Engine Forecast"
            col_fcst = f"{month} | Forecast"
            if col_base not in df.columns or col_eng not in df.columns:
                continue
            target     = float(target_pct) / 100.0

            # Operate only on LfL rows — NSO/Ramp are unaffected by overall_override
            lfl_base = df.loc[lfl_mask, col_base].sum()
            if lfl_base <= 0:
                continue

            # Divisions explicitly overridden for this month — keep their LfL forecasts intact
            fixed_divs = {
                d for d in DIVS
                if growth_overrides and d in growth_overrides
                and month in growth_overrides.get(d, {})
            }
            # Individual store×division AOP overrides for this month are held fixed too
            cell_overridden = pd.Series(
                [(s, d, month) in aop_overrides for s, d in zip(df['Store'], df['Division'])],
                index=df.index) if aop_overrides else pd.Series(False, index=df.index)
            fixed_lfl   = lfl_mask & (df['Division'].isin(fixed_divs) | cell_overridden)
            unfixed_lfl = lfl_mask & ~df['Division'].isin(fixed_divs) & ~cell_overridden

            unfixed_lfl_base = df.loc[unfixed_lfl, col_base].sum()
            # Individual division rates always take priority.
            # If all divisions are explicitly set for this month, or if fixed divisions
            # already meet/exceed the overall target on their own, skip — the user's
            # per-division inputs cannot be overridden by overall_override.
            if unfixed_lfl_base <= 0:
                continue  # every division explicitly set; overall target cannot be applied
            fixed_lfl_eng   = df.loc[fixed_lfl,   col_eng].sum()
            unfixed_lfl_eng = df.loc[unfixed_lfl, col_eng].sum()
            target_lfl_eng  = (1.0 + target) * lfl_base
            if fixed_lfl_eng >= target_lfl_eng:
                continue  # fixed divisions already hit/exceed target; nothing for unfixed to do
            if abs(unfixed_lfl_eng) < 1e-10:
                continue
            # Solve: (fixed_lfl_eng + unfixed_lfl_eng_new) / lfl_base = 1 + target
            scale = (target_lfl_eng - fixed_lfl_eng) / unfixed_lfl_eng
            adj = df.loc[unfixed_lfl, col_fcst] - df.loc[unfixed_lfl, col_eng]
            df.loc[unfixed_lfl, col_eng]  = df.loc[unfixed_lfl, col_eng] * scale
            df.loc[unfixed_lfl, col_fcst] = df.loc[unfixed_lfl, col_eng] + adj

    write_excel(df, output_file, palette=palette, include_debug=include_debug)
    if detail_file:
        df.to_json(detail_file, orient="records")
    return _build_results(df, store_info)


def get_file_info(input_file):
    """Quick parse — reads Store Master, Growth %, and Store Actuals for base sales."""
    xl = pd.ExcelFile(input_file, engine="calamine")

    def parse(sheet, skip=3):
        return xl.parse(sheet, skiprows=skip)

    sm = parse("Store Master")
    sm.columns = [str(c).strip() for c in sm.columns]
    sm = sm.dropna(subset=["Store"])
    sm["Store"] = sm["Store"].astype(str).str.strip()

    growth = parse("Growth %")
    growth.columns = [str(c).strip() for c in growth.columns]
    growth = growth[growth.iloc[:, 0].notna()]
    growth = growth[~growth.iloc[:, 0].astype(str).str.upper().str.startswith("HOW")]

    tag_map = {str(r["Store"]).strip(): str(r.get("Tag","")).strip() for _, r in sm.iterrows()}
    n_lfl  = sum(1 for t in tag_map.values() if t in LFL_TAGS)
    n_ramp = sum(1 for t in tag_map.values() if t in RAMP_TAGS)
    n_nso  = sum(1 for t in tag_map.values() if t in NSO_TAGS)
    gmap   = build_growth_map(growth)
    growth_rates = {div: {m: round(gmap[div][m]*100, 2) for m in FY28_M} for div in DIVS}

    # ── Base sales by group × division × month (FY27 actuals, mapped to FY28 month keys) ──
    base_sales = {grp: {div: {m: 0.0 for m in FY28_M} for div in DIVS}
                  for grp in ("LFL", "Ramp", "NSO")}
    try:
        act = parse("Store Actuals")
        act.columns = [str(c).strip() for c in act.columns]
        act = act.dropna(subset=["Store"])
        act["Store"]    = act["Store"].astype(str).str.strip()
        act["Division"] = act["Division"].astype(str).str.strip() if "Division" in act.columns else ""
        # Attribute (ATTRIBUTE1) is a newer column - a file built before
        # to_workbook.py started writing it won't have it, and should behave
        # exactly as before (no filtering at all, every row counts every
        # quarter) rather than error or silently drop every Q1 row.
        has_attribute = "Attribute" in act.columns
        if has_attribute:
            act["Attribute"] = act["Attribute"].astype(str).str.strip()
        month_pairs = list(zip(FY27_M, FY28_M))
        for _, row in act.iterrows():
            store = str(row["Store"])
            div   = str(row.get("Division","")).strip().upper()
            if div not in DIVS:
                continue
            tag = tag_map.get(store, "")
            if tag in LFL_TAGS:
                grp = "LFL"
            elif tag in RAMP_TAGS:
                grp = "Ramp"
            elif tag in NSO_TAGS:
                grp = "NSO"
            else:
                continue
            attribute = str(row.get("Attribute", "")).strip() if has_attribute else None
            for fy27m, fy28m in month_pairs:
                if Q1_ALLOWED_VALUES and has_attribute and fy28m in Q1_FY28_MONTHS and attribute not in Q1_ALLOWED_VALUES:
                    continue  # Q1 only counts specific attribute values - this row's attribute isn't one of them
                v = row.get(fy27m, 0)
                try:
                    base_sales[grp][div][fy28m] += float(v) if v == v else 0.0
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass  # Store Actuals missing or malformed — preview will show zeros

    # Round to 2 dp
    for grp in base_sales:
        for div in base_sales[grp]:
            for m in base_sales[grp][div]:
                base_sales[grp][div][m] = round(base_sales[grp][div][m], 2)

    return {
        "n_stores":    len(sm),
        "n_lfl":       n_lfl,
        "n_ramp":      n_ramp,
        "n_nso":       n_nso,
        "growth_rates": growth_rates,
        "base_sales":  base_sales,
    }


if __name__ == "__main__":
    main()
