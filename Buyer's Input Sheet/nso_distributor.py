"""
NSO Sales Plan Distributor v2
4-input algorithm:
  1. NSO Details       – Store Code, Ref Code, Grade, month AOP targets
  2. Division Cont %   – % of each division (GM/KIDS/LADIES/MENS/RETAIL) per month per store
  3. Sales Plan        – Full breakdown to Division × Dept × MRP × Display Type + Val + Qty
  4. Attribute Grid    – (loaded but applied only for Sep/Oct; skipped for Nov+ openings)

Algorithm per NSO:
  NSO_div_month  = NSO_total_month × div_pct
  For JAN/FEB    = split via J1/J2 or F1/F2 then recombine → same as div_pct × total
  NSO_row_val    = NSO_div_month × (ref_row_val / ref_div_total_val)
  NSO_row_qty    = NSO_row_val / ASP   (ASP = ref_row_val / ref_row_qty)
"""

from flask import Flask, request, jsonify, send_file, render_template_string, Response
import pandas as pd
import numpy as np
from io import BytesIO
import openpyxl, json
from openpyxl.styles import PatternFill, Font, Alignment
import traceback, os, datetime
import threading, uuid, time, glob, re
from collections import OrderedDict

app = Flask(__name__)
PORT = 8060

# ── Column helpers ──────────────────────────────────────────────────────────────
PLAN_MONTHS = ['SEP', 'OCT', 'NOV', 'DEC', 'JAN', 'FEB']
VAL = {m: f'{m} - Val' for m in PLAN_MONTHS}
QTY = {m: f'{m} - Qty' for m in PLAN_MONTHS}

# Sales Plan CAT → Division Cont % CAT mapping
# In Sales Plan: CAT = GM | APPS | RETAIL
# APPS rows are further split by Division column: KIDS | LADIES | MENS
# Division Cont % uses: GM | KIDS | LADIES | MENS | RETAIL
DIVCONT_CATS = ['GM', 'KIDS', 'LADIES', 'MENS', 'RETAIL']
PLAN_CAT_MAP = {
    'GM':    ('GM',    None),          # plan CAT='GM', Division=any
    'KIDS':  ('APPS',  'KIDS'),        # plan CAT='APPS', Division='KIDS'
    'LADIES':('APPS',  'LADIES'),
    'MENS':  ('APPS',  'MENS'),
    'RETAIL':('RETAIL', None),
}

# Division Cont % datetime-column → short month label
DIVCONT_DATE_MAP = {
    '2026-09': 'SEP', '2026-10': 'OCT',
    '2026-11': 'NOV', '2026-12': 'DEC',
    '2027-01': 'JAN', '2027-02': 'FEB', '2027-03': 'MAR',
}

# ── File scan patterns ───────────────────────────────────────────────────────────
FILE_PATTERNS = {
    'nso_details':    ['NSO Details*.xlsx', 'NSO Details*.xls'],
    'sales_plan':     ['Sales Plan*.xlsx', 'Sales Plan*.xls'],
    'div_cont':       ['Division Cont*.xlsx', 'Division Cont*.xls'],
    'attr_grid':      ['Attribute Grid*.xlsx', 'Attribute Grid*.xls'],
    'apps_exclusion': ['APPS Exclusion*.xlsx', 'Apps Exclusion*.xlsx', 'APPS Exclusion*.xls'],
    'attr_master':    ['Attribute Master*.xlsx', 'Att Master*.xlsx', 'att master*.xlsx',
                       'ATT MASTER*.xlsx', 'ATTRIBUTE MASTER*.xlsx'],
}

# ── GM Listing Master (bundled, loaded once at startup) ──────────────────────────
_GM_MASTER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'GM Listing Master(Excl).xlsx')
_GM_MASTER_DF: 'pd.DataFrame | None' = None

def _load_gm_master():
    global _GM_MASTER_DF
    if os.path.exists(_GM_MASTER_PATH):
        try:
            df = pd.read_excel(_GM_MASTER_PATH, header=1)
            _clean_xa0(df)
            _GM_MASTER_DF = df
            type_cols = [c for c in df.columns if c not in ('DIVISION', 'SECTION', 'DEPARTMENT', 'ATTRIBUTE-1')]
            print(f'[GM Master] Loaded {len(df)} rows — store-type columns: {type_cols}')
        except Exception as e:
            print(f'[GM Master] Failed to load: {e}')
    else:
        print(f'[GM Master] Not found at {_GM_MASTER_PATH} — GM rows will not be filtered')

# ── Job queue ────────────────────────────────────────────────────────────────────
JOBS = OrderedDict()
JOBS_LOCK = threading.Lock()
MAX_JOBS = 20

# ── Loaders ──────────────────────────────────────────────────────────────────────

def _clean_xa0(df):
    """Strip \xa0 from all columns regardless of pandas version dtype representation."""
    for col in df.columns:
        try:
            df[col] = df[col].apply(
                lambda x: str(x).replace('\xa0', '').strip() if isinstance(x, str) else x
            )
        except Exception:
            pass
    return df


_load_gm_master()   # Now safe to call: _clean_xa0 is defined above


def load_nso_details(file_bytes):
    df = pd.read_excel(BytesIO(file_bytes), header=0)
    _clean_xa0(df)
    # Rename datetime month columns
    rename = {}
    for col in df.columns:
        s = str(col)[:7]
        if s in DIVCONT_DATE_MAP:
            rename[col] = DIVCONT_DATE_MAP[s]
    df = df.rename(columns=rename)
    # Convert month cols to numeric
    month_labels = list(DIVCONT_DATE_MAP.values()) + ['APR', 'MAY', 'JUN', 'JUL', 'AUG']
    for col in df.columns:
        if col in month_labels:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def load_div_cont(file_bytes):
    # Row 1 is blank; header is row 2 (index 1)
    df = pd.read_excel(BytesIO(file_bytes), header=1)
    _clean_xa0(df)
    rename = {}
    for col in df.columns:
        s = str(col)[:7]
        if s in DIVCONT_DATE_MAP:
            rename[col] = DIVCONT_DATE_MAP[s]
    df = df.rename(columns=rename)
    num_cols = list(DIVCONT_DATE_MAP.values()) + ['J1 %', 'J2 %', 'F1 %', 'F2 %']
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df


def load_sales_plan(file_bytes):
    # Use calamine engine (C-based, 5-10x faster than openpyxl for large files)
    try:
        df = pd.read_excel(BytesIO(file_bytes), header=2, engine='calamine')
    except Exception:
        df = pd.read_excel(BytesIO(file_bytes), header=2)
    df = df[df['Store Name'].notna()].copy()
    for m in PLAN_MONTHS:
        for c in [VAL[m], QTY[m]]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    return df


def load_attr_grid(file_bytes):
    df = pd.read_excel(BytesIO(file_bytes), header=0)
    _clean_xa0(df)
    if 'Cont %' in df.columns:
        df['Cont %'] = pd.to_numeric(df['Cont %'], errors='coerce').fillna(0)
    # Normalize Month column to 3-letter uppercase abbreviation for reliable matching
    _MONTH_ABBREV = {
        'SEPTEMBER': 'SEP', 'OCTOBER': 'OCT', 'NOVEMBER': 'NOV',
        'DECEMBER': 'DEC', 'JANUARY': 'JAN', 'FEBRUARY': 'FEB',
        'MARCH': 'MAR', 'APRIL': 'APR', 'JUNE': 'JUN',
        'JULY': 'JUL', 'AUGUST': 'AUG',
    }
    for col in df.columns:
        if col.strip().lower() == 'month':
            df[col] = df[col].astype(str).str.strip().str.upper().map(
                lambda x: _MONTH_ABBREV.get(x, x)
            )
            break
    return df


def _build_attr_weight_fn(attr_df, zone, division, opening_month, attr_master_df=None):
    """
    Builds a weight function dept_name → float [0, 1] from the Attribute Grid
    for the given zone + division + opening_month combination.

    Returns (weight_fn, found):
      found=False → no grid rows matched; caller should skip grid and use full ref plan
      found=True  → weight_fn(dept) returns the Cont% multiplier for that department
                    (0 = exclude, 0.5 = half weight, 1 = full weight)
                    Departments not listed in the grid return 0 (not in season)
    """
    if attr_df is None or attr_df.empty:
        return None, False

    def _find_col(keywords):
        # Prefer exact match to avoid 'Month 2' matching before 'Month'
        for c in attr_df.columns:
            if c.strip().lower() in keywords:
                return c
        # Substring fallback
        for c in attr_df.columns:
            cl = c.strip().lower()
            if any(k in cl for k in keywords):
                return c
        return None

    col_zone = _find_col(['zone'])
    col_div  = _find_col(['division', 'div'])
    col_attr = _find_col(['attribute', 'attr'])
    col_cont = _find_col(['cont'])
    col_mon  = _find_col(['month'])

    if not all([col_zone, col_div, col_attr, col_cont]):
        return None, False

    zone_u = str(zone).strip().upper()
    div_u  = division.strip().upper()
    mon_u  = opening_month.strip().upper()

    mask = (
        (attr_df[col_zone].astype(str).str.strip().str.upper() == zone_u) &
        (attr_df[col_div].astype(str).str.strip().str.upper() == div_u)
    )
    if col_mon:
        mask &= (attr_df[col_mon].astype(str).str.strip().str.upper() == mon_u)

    grid_rows = attr_df[mask]
    if grid_rows.empty:
        return None, False

    # Build (attribute_group_upper, cont_pct) pairs from the grid rows
    entries = [
        (str(row[col_attr]).strip().upper(), float(row[col_cont] or 0))
        for _, row in grid_rows.iterrows()
        if str(row[col_attr]).strip() and str(row[col_attr]).strip().lower() not in ('nan', '')
    ]

    # Build dept → attribute_group lookup from the master (if provided)
    dept_to_attr = {}
    if attr_master_df is not None and not attr_master_df.empty:
        dept_col  = next((c for c in attr_master_df.columns if 'dept' in c.strip().lower()), None)
        attr1_col = next((c for c in attr_master_df.columns if 'attr' in c.strip().lower()), None)
        if dept_col and attr1_col:
            for _, row in attr_master_df.iterrows():
                d = str(row[dept_col]).strip()
                a = str(row[attr1_col]).strip().upper()
                if d and d.lower() not in ('nan', ''):
                    dept_to_attr[d] = a

    def weight_fn(dept):
        d = str(dept).strip()
        if dept_to_attr:
            # Exact dept → attribute group → grid Cont%
            attr_group = dept_to_attr.get(d) or dept_to_attr.get(d.upper())
            if attr_group is not None:
                for grid_attr, cont in entries:
                    if grid_attr == attr_group:
                        return cont
                return 1.0  # dept's attribute not listed in grid = in season
            return 1.0  # dept not in master = include at full weight
        else:
            # No master: substring match on attribute name in dept name (legacy fallback)
            du = d.upper()
            for pattern, cont in entries:
                if pattern in du or du in pattern:
                    return cont
            return 1.0

    return weight_fn, True


def load_attr_master(file_bytes):
    """Dept → Attribute1 mapping. Columns: DIVISION, SECTION, DEPARTMENT, ATTRIBUTE1."""
    df = pd.read_excel(BytesIO(file_bytes), header=0)
    _clean_xa0(df)
    df = df[df['DEPARTMENT'].notna() & (df['DEPARTMENT'].astype(str).str.strip() != '')].copy()
    return df


def load_gm_exclusion(file_bytes):
    """GM Exclusion list.
    Format: blank first row; header at row 1 with columns
    DIVISION, SECTION, DEPARTMENT, ATTRIBUTE-1, <NSO_CODE1>, <NSO_CODE2>, ...
    Each NSO column has Y (include) or N (exclude) per department row."""
    df = pd.read_excel(BytesIO(file_bytes), header=1)
    _clean_xa0(df)
    return df


def load_apps_exclusion(file_bytes):
    """APPS Exclusion list.
    Format: columns Store Name, Ref Store, APPS Excl
    Each row = for this NSO+Ref pair, exclude APPS rows whose Department contains APPS Excl."""
    df = pd.read_excel(BytesIO(file_bytes), header=0)
    _clean_xa0(df)
    return df


# ── Exclusion filter helpers ─────────────────────────────────────────────────────

def _apply_gm_exclusion(dr, store_type):
    """Exclude GM departments per store type (T1+/T1/T2/T3/T4) from the bundled GM Listing Master.
    Departments where the store-type column = 'N' are dropped from dr."""
    master = _GM_MASTER_DF
    if master is None or master.empty or not store_type:
        return dr
    st = store_type.strip().upper()
    type_col = next((c for c in master.columns if str(c).strip().upper() == st), None)
    if type_col is None:
        return dr  # Unrecognised store type → include all GM rows
    excl_depts = set(
        str(d).strip()
        for d in master.loc[master[type_col].astype(str).str.strip().str.upper() == 'N', 'DEPARTMENT']
        if str(d).strip()
    )
    if not excl_depts:
        return dr
    return dr[~dr['Department'].astype(str).str.strip().isin(excl_depts)]


def _apply_apps_exclusion(dr, store_code, ref_code, excl_df):
    """Exclude APPS departments per APPS Exclusion list (Store Name, Ref Store, APPS Excl).
    Each row in excl_df maps an NSO store to a department substring to exclude."""
    if excl_df is None or excl_df.empty:
        return dr
    store_upper = str(store_code).strip().upper()
    # Locate the Store Name column (first column) and APPS Excl column (last / named)
    sn_col   = next((c for c in excl_df.columns if 'store name' in str(c).lower()), excl_df.columns[0])
    excl_col = next(
        (c for c in excl_df.columns if 'apps excl' in str(c).lower() or 'apps_excl' in str(c).lower()),
        excl_df.columns[-1]
    )
    mask = excl_df[sn_col].astype(str).str.strip().str.upper() == store_upper
    if not mask.any():
        return dr
    excl_vals = [str(v).strip() for v in excl_df.loc[mask, excl_col].dropna() if str(v).strip()]
    if not excl_vals:
        return dr
    def is_excluded(dept):
        d = str(dept).strip().upper()
        return any(v.upper() in d for v in excl_vals)
    return dr[~dr['Department'].astype(str).apply(is_excluded)]


# ── Core algorithm ───────────────────────────────────────────────────────────────

def _ref_rows_for_div(ref_plan, div_cat):
    """Filter ref plan rows for a Division Cont % category (GM/KIDS/LADIES/MENS/RETAIL)."""
    plan_cat, plan_div = PLAN_CAT_MAP[div_cat]
    mask = ref_plan['CAT'].astype(str) == plan_cat
    if plan_div:
        mask &= ref_plan['Division'].astype(str) == plan_div
    return ref_plan[mask].copy()


def _div_pct(div_row, month):
    """Return the effective division % for a month, applying J1/J2 or F1/F2 split-and-club."""
    base = float(div_row.get(month, 0) or 0)
    if month == 'JAN':
        j1 = float(div_row.get('J1 %', 0) or 0)
        j2 = float(div_row.get('J2 %', 0) or 0)
        # If split data exists (j1+j2 > 0) → apply split then club back
        if j1 + j2 > 0:
            return base * (j1 + j2)   # = base × 1.0 when J1+J2=100%, preserves meaning
        return base
    if month == 'FEB':
        f1 = float(div_row.get('F1 %', 0) or 0)
        f2 = float(div_row.get('F2 %', 0) or 0)
        if f1 + f2 > 0:
            return base * (f1 + f2)
        return base
    return base


def generate_plan(nso_df, div_df, plan_df, attr_df=None, gm_excl_df=None, apps_excl_df=None, attr_master_df=None):
    """
    Returns (output_rows list, log list).
    output_rows: list of dicts matching Sales Plan column structure.
    """
    TARGET_MONTHS = ['SEP', 'OCT', 'NOV', 'DEC', 'JAN', 'FEB']
    log = []
    all_rows = []

    for _, nso in nso_df.iterrows():
        store = str(nso['Store Code']).strip()
        ref   = str(nso['Ref Code']).strip()
        store_type = '1 - NSO'

        # Store type drives GM exclusion (T1+/T1/T2/T3/T4); try 'Store Type', then 'Type', then 'Grade'
        nso_grade = str(nso.get('Store Type', nso.get('Type', nso.get('Grade', '')))).strip()
        nso_zone  = str(nso.get('Zone', '')).strip()

        # Month total targets (Rs Lakh) — all 6 plan months
        month_targets = {m: float(nso.get(m, 0) or 0) for m in TARGET_MONTHS}

        # Determine opening month (first month with a non-zero target)
        opening_month = next((m for m in TARGET_MONTHS if month_targets.get(m, 0) > 0), 'NOV')

        log.append(f"NSO: {store}  Ref: {ref}  StoreType: {nso_grade}  Opens: {opening_month}  Targets: {month_targets}")

        if attr_df is not None and not attr_df.empty and opening_month in ('SEP', 'OCT'):
            log.append(f"  Attribute Grid: provided for {opening_month} opener — seasonal mix from ref store's {opening_month} values")

        # Reference store's Division Cont % rows
        ref_div_rows = div_df[div_df['Store Name'] == ref]
        if ref_div_rows.empty:
            log.append(f"  SKIP: {ref} not in Division Cont %")
            continue

        # Use NSO's own plan rows when they exist — dept listing and proportions
        # are then correct for this specific store (zeros in the plan = dept not stocked).
        # Fall back to ref store's plan when the NSO has no own rows.
        own_plan = plan_df[plan_df['Store Name'] == store]
        if not own_plan.empty:
            ref_plan = own_plan.copy()
            log.append(f"  Own plan rows found: {len(ref_plan)} — using NSO's own dept mix")
        else:
            ref_plan = plan_df[plan_df['Store Name'] == ref].copy()
            # Exclude SAREE_TANT from ref store proportions (underscore-safe)
            ref_plan = ref_plan[
                ~ref_plan['Department'].astype(str).str.upper().str.contains('SAREE_TANT', na=False)
            ]
        if ref_plan.empty:
            log.append(f"  SKIP: neither {store} nor {ref} found in Sales Plan")
            continue

        log.append(f"  Ref plan rows: {len(ref_plan)}")

        # Accumulate output: key = (plan_cat, division, dept, mrp, display_type)
        # value = {month: {val, qty}}
        out_acc = {}  # key → {NOV-Val: float, NOV-Qty: float, ...}

        for div_cat in DIVCONT_CATS:
            # Division Cont % row for this ref store + div_cat
            dc_rows = ref_div_rows[ref_div_rows['CAT'] == div_cat]
            if dc_rows.empty:
                log.append(f"    No div-cont for {ref}/{div_cat}")
                continue
            dc_row = dc_rows.iloc[0]

            # Reference plan rows for this division
            dr = _ref_rows_for_div(ref_plan, div_cat)
            if dr.empty:
                log.append(f"    No plan rows for {ref}/{div_cat}")
                continue

            # Apply exclusion rules
            if div_cat == 'GM':
                dr = _apply_gm_exclusion(dr, nso_grade)
                if _GM_MASTER_DF is not None:
                    log.append(f"    GM after exclusion: {len(dr)} rows (master type={nso_grade})")
            elif div_cat in ('KIDS', 'LADIES', 'MENS'):
                dr = _apply_apps_exclusion(dr, store, ref, apps_excl_df)

            if dr.empty:
                log.append(f"    No plan rows remain for {ref}/{div_cat} after exclusion")
                continue

            # Build Attribute Grid weight function for Sep/Oct openers (KIDS/LADIES/MENS only)
            attr_weight_fn = None
            if opening_month in ('SEP', 'OCT') and div_cat in ('KIDS', 'LADIES', 'MENS'):
                wfn, found = _build_attr_weight_fn(attr_df, nso_zone, div_cat, opening_month, attr_master_df)
                if found:
                    attr_weight_fn = wfn
                    if nso_zone:
                        log.append(f"    AttrGrid applied: zone={nso_zone} div={div_cat} open={opening_month}")
                    else:
                        log.append(f"    AttrGrid: no Zone on store {store} — skipping grid for {div_cat}")
                else:
                    log.append(f"    AttrGrid: no rows for zone={nso_zone!r} div={div_cat} open={opening_month} — full ref proportions")

            plan_cat, plan_div = PLAN_CAT_MAP[div_cat]

            for month in TARGET_MONTHS:
                total = month_targets.get(month, 0)
                if total == 0:
                    continue

                # Division target for this month
                pct = _div_pct(dc_row, month)
                div_target = total * pct   # Rs Lakh

                val_c = VAL[month]
                qty_c = QTY[month]
                if val_c not in dr.columns:
                    continue

                # Weighted ref total for proportion denominator (grid weights applied when available)
                if attr_weight_fn is not None:
                    ref_div_total_val = sum(
                        float(r2.get(val_c, 0) or 0) * attr_weight_fn(str(r2.get('Department', '')))
                        for _, r2 in dr.iterrows()
                    )
                else:
                    ref_div_total_val = dr[val_c].sum()

                if ref_div_total_val == 0:
                    continue

                for _, ref_row in dr.iterrows():
                    ref_val = float(ref_row.get(val_c, 0) or 0)
                    ref_qty = float(ref_row.get(qty_c, 0) or 0)

                    # Apply attribute weight (0 = exclude this dept entirely)
                    w = attr_weight_fn(str(ref_row.get('Department', ''))) if attr_weight_fn else 1.0
                    ref_val_w = ref_val * w
                    if ref_val_w == 0:
                        continue

                    row_pct = ref_val_w / ref_div_total_val
                    pdh_val = div_target * row_pct

                    # ASP-based qty — use actual unweighted ASP from ref store
                    if ref_val > 0 and ref_qty > 0:
                        asp = ref_val / ref_qty
                        pdh_qty = pdh_val / asp
                    else:
                        pdh_qty = 0.0

                    # Row key uses the PLAN's CAT (GM/APPS/RETAIL) + Division + rest
                    key = (
                        plan_cat,
                        str(ref_row.get('Division', '')),
                        str(ref_row.get('Department', '')),
                        str(ref_row.get('MRP', '')),
                        str(ref_row.get('Display Type', '')),
                    )
                    if key not in out_acc:
                        out_acc[key] = {f'{m}-Val': 0.0 for m in PLAN_MONTHS}
                        out_acc[key].update({f'{m}-Qty': 0.0 for m in PLAN_MONTHS})

                    out_acc[key][f'{month}-Val'] += pdh_val
                    out_acc[key][f'{month}-Qty'] += pdh_qty

        # Build flat output rows
        for (plan_cat, division, dept, mrp, disp), vals in out_acc.items():
            row = {
                'Store Name':   store,
                'Ref Store':    ref,
                'Store Type':   store_type,
                'CAT':          plan_cat,
                'Division':     division,
                'Department':   dept,
                'MRP':          mrp,
                'Display Type': disp,
                '.':            None,
                'SEP - Val':    round(vals.get('SEP-Val', 0), 4),
                'OCT - Val':    round(vals.get('OCT-Val', 0), 4),
                'NOV - Val':    round(vals.get('NOV-Val', 0), 4),
                'DEC - Val':    round(vals.get('DEC-Val', 0), 4),
                'JAN - Val':    round(vals.get('JAN-Val', 0), 4),
                'FEB - Val':    round(vals.get('FEB-Val', 0), 4),
                '..1':          None,
                'SEP - Qty':    round(vals.get('SEP-Qty', 0), 4),
                'OCT - Qty':    round(vals.get('OCT-Qty', 0), 4),
                'NOV - Qty':    round(vals.get('NOV-Qty', 0), 4),
                'DEC - Qty':    round(vals.get('DEC-Qty', 0), 4),
                'JAN - Qty':    round(vals.get('JAN-Qty', 0), 4),
                'FEB - Qty':    round(vals.get('FEB-Qty', 0), 4),
            }
            all_rows.append(row)

        log.append(f"  Output rows for {store}: {len(out_acc)}")

    return all_rows, log


def build_xlsx(rows, log, nso_df=None):
    """Build a styled XLSX workbook from output rows."""
    wb = openpyxl.Workbook()
    hdr_fill = PatternFill('solid', fgColor='312E81')
    hdr_font = Font(color='FFFFFF', bold=True, size=10)
    alt_fill = PatternFill('solid', fgColor='EEF2FF')

    # ── NSO AOP Targets sheet (first) ────────────────────────────
    ws0 = wb.active
    ws0.title = 'NSO AOP Targets'
    if nso_df is not None and not nso_df.empty:
        aop_show = ['Store Code', 'Ref Code', 'Grade', 'Type', 'SEP', 'OCT', 'NOV', 'DEC', 'JAN', 'FEB']
        aop_month_cols = {'SEP', 'OCT', 'NOV', 'DEC', 'JAN', 'FEB'}
        aop_cols = [c for c in aop_show if c in nso_df.columns]
        for ci, col in enumerate(aop_cols, 1):
            cell = ws0.cell(row=1, column=ci, value=col)
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.alignment = Alignment(horizontal='center')
        for ri, (_, row) in enumerate(nso_df.iterrows(), 2):
            for ci, col in enumerate(aop_cols, 1):
                v = row.get(col, '')
                if hasattr(v, 'item'):
                    v = v.item()
                cell = ws0.cell(row=ri, column=ci, value=v)
                if isinstance(v, (int, float)) and col in aop_month_cols:
                    cell.number_format = '#,##0.00'
        ws0.freeze_panes = 'A2'
        for ci in range(1, len(aop_cols) + 1):
            ws0.column_dimensions[ws0.cell(1, ci).column_letter].width = 16

    # ── Detail sheet ─────────────────────────────────────────────
    ws = wb.create_sheet('NSO Plan - Detail')

    if not rows:
        ws['A1'] = 'No rows generated. Check log sheet.'
    else:
        cols = list(rows[0].keys())

        # Header
        for ci, col in enumerate(cols, 1):
            cell = ws.cell(row=1, column=ci, value=col)
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.alignment = Alignment(horizontal='center')

        # Data
        for ri, row in enumerate(rows, 2):
            fill = alt_fill if ri % 2 == 0 else None
            for ci, col in enumerate(cols, 1):
                v = row[col]
                cell = ws.cell(row=ri, column=ci, value=v)
                if fill:
                    cell.fill = fill
                if isinstance(v, float) and v != 0:
                    cell.number_format = '#,##0.0000'

        # Column widths
        for ci, col in enumerate(cols, 1):
            if 'Val' in col or 'Qty' in col:
                ws.column_dimensions[ws.cell(1, ci).column_letter].width = 13
            elif col in ('Store Name', 'Ref Store', 'Store Type', 'CAT', 'Division'):
                ws.column_dimensions[ws.cell(1, ci).column_letter].width = 16
            elif col in ('Department', 'MRP'):
                ws.column_dimensions[ws.cell(1, ci).column_letter].width = 24
            else:
                ws.column_dimensions[ws.cell(1, ci).column_letter].width = 14
        ws.freeze_panes = 'A2'

    # ── Summary sheet ────────────────────────────────────────────
    ws2 = wb.create_sheet('Monthly Summary')
    val_months = ['NOV', 'DEC', 'JAN', 'FEB']
    sum_cols = ['Store Name', 'Ref Store', 'Store Type', 'CAT', 'Division'] + \
               [f'{m} - Val' for m in val_months] + ['Total Val'] + \
               [f'{m} - Qty' for m in val_months] + ['Total Qty']

    for ci, col in enumerate(sum_cols, 1):
        cell = ws2.cell(row=1, column=ci, value=col)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal='center')

    # Build summary by Store × CAT × Division
    if rows:
        df = pd.DataFrame(rows)
        grp_cols = ['Store Name', 'Ref Store', 'Store Type', 'CAT', 'Division']
        agg = {f'{m} - Val': 'sum' for m in val_months}
        agg.update({f'{m} - Qty': 'sum' for m in val_months})
        sumdf = df.groupby(grp_cols, as_index=False).agg(agg)
        sumdf['Total Val'] = sumdf[[f'{m} - Val' for m in val_months]].sum(axis=1)
        sumdf['Total Qty'] = sumdf[[f'{m} - Qty' for m in val_months]].sum(axis=1)

        for ri, (_, row) in enumerate(sumdf.iterrows(), 2):
            fill = alt_fill if ri % 2 == 0 else None
            for ci, col in enumerate(sum_cols, 1):
                v = row.get(col, '')
                cell = ws2.cell(row=ri, column=ci, value=v)
                if fill:
                    cell.fill = fill
                if isinstance(v, float) and v != 0:
                    cell.number_format = '#,##0.00'

    ws2.freeze_panes = 'A2'

    # ── Log sheet ────────────────────────────────────────────────
    ws3 = wb.create_sheet('Processing Log')
    ws3.column_dimensions['A'].width = 90
    for ri, line in enumerate(log, 1):
        ws3.cell(row=ri, column=1, value=line)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── Job queue helpers ─────────────────────────────────────────────────────────────

def _job_set(job_id, **kwargs):
    with JOBS_LOCK:
        j = JOBS.get(job_id, {})
        j.update(kwargs)
        if 'pct' in kwargs or 'msg' in kwargs:
            j.setdefault('events', []).append({
                'pct': kwargs.get('pct', j.get('pct', 0)),
                'msg': kwargs.get('msg', j.get('msg', '')),
                'status': kwargs.get('status', j.get('status', 'running')),
            })
        JOBS[job_id] = j


def _apply_overrides(nso_df, overrides):
    for idx, row in nso_df.iterrows():
        sc = row['Store Code']
        if sc in overrides:
            zone_val = overrides[sc].get('zone', '')
            if zone_val:
                nso_df.at[idx, 'Zone'] = str(zone_val)
            for m, v in overrides[sc].items():
                if m == 'zone':
                    continue
                if m in nso_df.columns:
                    try:
                        nso_df.at[idx, m] = float(v)
                    except (ValueError, TypeError):
                        pass
    return nso_df


def _run_job(job_id, nso_bytes, div_bytes, plan_bytes, attr_bytes,
             gm_excl_bytes, apps_excl_bytes, attr_master_bytes, aop_overrides):
    try:
        _job_set(job_id, pct=5, msg='Parsing NSO Details...')
        nso_df = load_nso_details(nso_bytes)
        if aop_overrides:
            nso_df = _apply_overrides(nso_df, aop_overrides)

        _job_set(job_id, pct=12, msg='Parsing Division Cont % Chart...')
        div_df = load_div_cont(div_bytes)

        _job_set(job_id, pct=18, msg='Loading exclusion rules...')
        gm_excl_df   = load_gm_exclusion(gm_excl_bytes)    if gm_excl_bytes   else None
        apps_excl_df = load_apps_exclusion(apps_excl_bytes) if apps_excl_bytes else None

        _job_set(job_id, pct=22, msg='Reading Sales Plan (large file — ~30s)...')
        # Ticker thread: animates bar 22→70 over ~30s while calamine reads
        _plan_done = threading.Event()
        def _ticker():
            t0 = time.time()
            while not _plan_done.wait(timeout=1.5):
                elapsed = time.time() - t0
                pct = min(69, int(22 + (elapsed / 30) * 48))
                _job_set(job_id, pct=pct, msg='Reading Sales Plan (large file — ~30s)...')
        _tick_t = threading.Thread(target=_ticker, daemon=True)
        _tick_t.start()
        try:
            plan_df = load_sales_plan(plan_bytes)
        finally:
            _plan_done.set()

        _job_set(job_id, pct=72, msg='Parsing Attribute Grid...')
        attr_df        = load_attr_grid(attr_bytes)     if attr_bytes         else None
        attr_master_df = load_attr_master(attr_master_bytes) if attr_master_bytes else None

        _job_set(job_id, pct=76, msg='Running distribution algorithm...')
        rows, log = generate_plan(nso_df, div_df, plan_df, attr_df, gm_excl_df, apps_excl_df, attr_master_df)

        if not rows:
            _job_set(job_id, status='error', pct=0,
                     msg='No rows generated. ' + ' | '.join(log[-5:]))
            return

        _job_set(job_id, pct=92, msg='Building XLSX output...')
        buf = build_xlsx(rows, log, nso_df=nso_df)
        result_bytes = buf.read()

        fname = f"NSO_Plan_{datetime.date.today().isoformat()}.xlsx"
        done_msg = f'Done — {len(rows):,} rows generated'
        with JOBS_LOCK:
            j = JOBS[job_id]
            j['status'] = 'done'
            j['pct']    = 100
            j['msg']    = done_msg
            j['result'] = result_bytes
            j['fname']  = fname
            j['row_count'] = len(rows)
            j.setdefault('events', []).append({'pct': 100, 'msg': done_msg, 'status': 'done'})

    except Exception as e:
        _job_set(job_id, status='error', pct=0, msg=str(e))
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id]['trace'] = traceback.format_exc()


# ── Flask routes ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    html_path = os.path.join(os.path.dirname(__file__), 'nso_distributor.html')
    with open(html_path, encoding='utf-8') as f:
        return f.read()


@app.route('/api/generate', methods=['POST'])
def api_generate():
    try:
        # Require NSO Details, Division Cont %, Sales Plan
        for key in ('nso_details', 'div_cont', 'sales_plan'):
            if key not in request.files:
                return jsonify({'error': f'Missing file: {key}'}), 400

        nso_bytes  = request.files['nso_details'].read()
        div_bytes  = request.files['div_cont'].read()
        plan_bytes = request.files['sales_plan'].read()
        attr_bytes = request.files['attr_grid'].read() if 'attr_grid' in request.files else None

        nso_df  = load_nso_details(nso_bytes)
        div_df  = load_div_cont(div_bytes)
        plan_df = load_sales_plan(plan_bytes)
        attr_df = load_attr_grid(attr_bytes) if attr_bytes else None

        # Apply any AOP overrides submitted by the UI
        if 'aop_overrides' in request.form:
            try:
                overrides = json.loads(request.form['aop_overrides'])
                nso_df = _apply_overrides(nso_df, overrides)
            except Exception:
                pass

        rows, log = generate_plan(nso_df, div_df, plan_df, attr_df,
                                  gm_excl_df=None, apps_excl_df=None)

        if not rows:
            return jsonify({'error': 'No rows generated. ' + ' | '.join(log[-10:])}), 422

        buf = build_xlsx(rows, log)
        fname = f"NSO_Plan_{datetime.date.today().isoformat()}.xlsx"
        return send_file(
            buf,
            as_attachment=True,
            download_name=fname,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/preview', methods=['POST'])
def api_preview():
    """Quick preview — returns JSON summary without building full XLSX."""
    try:
        for key in ('nso_details', 'div_cont', 'sales_plan'):
            if key not in request.files:
                return jsonify({'error': f'Missing file: {key}'}), 400

        nso_df  = load_nso_details(request.files['nso_details'].read())
        div_df  = load_div_cont(request.files['div_cont'].read())
        plan_df = load_sales_plan(request.files['sales_plan'].read())

        rows, log = generate_plan(nso_df, div_df, plan_df,
                                  gm_excl_df=None, apps_excl_df=None)

        # Quick summary per NSO × CAT × month
        summary = []
        if rows:
            df = pd.DataFrame(rows)
            val_cols = ['NOV - Val', 'DEC - Val', 'JAN - Val', 'FEB - Val']
            qty_cols = ['NOV - Qty', 'DEC - Qty', 'JAN - Qty', 'FEB - Qty']
            grp = df.groupby(['Store Name', 'CAT'])[val_cols + qty_cols].sum().reset_index()
            for _, r in grp.iterrows():
                summary.append({
                    'store': r['Store Name'],
                    'cat': r['CAT'],
                    'months': {m.replace(' - Val','').replace(' - Val',''): {
                        'val': round(r.get(f'{m} - Val', 0), 2),
                        'qty': round(r.get(f'{m} - Qty', 0), 0)
                    } for m in ['NOV', 'DEC', 'JAN', 'FEB']},
                    'total_val': round(sum(r.get(f'{m} - Val', 0) for m in ['NOV', 'DEC', 'JAN', 'FEB']), 2),
                })

        nso_names = nso_df['Store Code'].tolist()
        return jsonify({
            'nso_count': len(nso_df),
            'nso_names': nso_names,
            'output_rows': len(rows),
            'summary': summary,
            'log': log,
        })

    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/scan-folder', methods=['POST'])
def api_scan_folder():
    data = request.get_json(force=True)
    folder = str(data.get('path', '')).strip()
    if not folder or not os.path.isdir(folder):
        return jsonify({'error': f'Folder not found: {folder}'}), 400
    found = {}
    for key, patterns in FILE_PATTERNS.items():
        found[key] = None
        for pat in patterns:
            matches = glob.glob(os.path.join(folder, pat))
            if matches:
                found[key] = os.path.basename(sorted(matches)[-1])
                break
    return jsonify({'folder': folder, 'found': found})


@app.route('/api/start', methods=['POST'])
def api_start():
    """Start a generation job. Supports folder-path mode (reads from disk) or file-upload mode."""
    job_id = uuid.uuid4().hex[:8]

    use_folder = 'folder' in request.form and request.form['folder'].strip()

    try:
        aop_overrides = json.loads(request.form.get('aop_overrides', '{}'))
    except Exception:
        aop_overrides = {}

    if use_folder:
        folder = request.form['folder'].strip()
        try:
            file_names = json.loads(request.form.get('files', '{}'))
        except Exception:
            file_names = {}

        def _read(key):
            p = _input_path(folder, file_names.get(key))
            if p:
                with open(p, 'rb') as f:
                    return f.read()
            return None

        nso_bytes         = _read('nso_details')
        div_bytes         = _read('div_cont')
        plan_bytes        = _read('sales_plan')
        attr_bytes        = _read('attr_grid')
        attr_master_bytes = _read('attr_master')
        gm_bytes   = request.files['gm_exclusion'].read()   if 'gm_exclusion'   in request.files else _read('gm_exclusion')
        apps_bytes = request.files['apps_exclusion'].read() if 'apps_exclusion'  in request.files else _read('apps_exclusion')
    else:
        for key in ('nso_details', 'div_cont', 'sales_plan'):
            if key not in request.files:
                return jsonify({'error': f'Missing required file: {key}'}), 400
        nso_bytes         = request.files['nso_details'].read()
        div_bytes         = request.files['div_cont'].read()
        plan_bytes        = request.files['sales_plan'].read()
        attr_bytes        = request.files['attr_grid'].read()        if 'attr_grid'      in request.files else None
        attr_master_bytes = request.files['attr_master'].read()      if 'attr_master'    in request.files else None
        gm_bytes          = request.files['gm_exclusion'].read()     if 'gm_exclusion'   in request.files else None
        apps_bytes        = request.files['apps_exclusion'].read()   if 'apps_exclusion' in request.files else None

    if not nso_bytes or not div_bytes or not plan_bytes:
        return jsonify({'error': 'Required files (NSO Details, Sales Plan, Division Cont %) missing'}), 400

    with JOBS_LOCK:
        JOBS[job_id] = {'status': 'running', 'pct': 0, 'msg': 'Queued...', 'events': [], 'result': None}
        while len(JOBS) > MAX_JOBS:
            JOBS.popitem(last=False)

    t = threading.Thread(
        target=_run_job,
        args=(job_id, nso_bytes, div_bytes, plan_bytes, attr_bytes,
              gm_bytes, apps_bytes, attr_master_bytes, aop_overrides),
        daemon=True
    )
    t.start()
    return jsonify({'job_id': job_id})


@app.route('/api/progress/<job_id>')
def api_progress(job_id):
    """SSE stream of progress events for a job."""
    def stream():
        sent = 0
        for _ in range(1200):  # max 10min at 0.5s intervals
            with JOBS_LOCK:
                j = JOBS.get(job_id)
            if not j:
                yield 'data: {"status":"not_found"}\n\n'
                return
            evts = j['events'][sent:]
            for ev in evts:
                yield f'data: {json.dumps(ev)}\n\n'
            sent += len(evts)
            if j['status'] in ('done', 'error'):
                return
            time.sleep(0.5)
    return Response(
        stream(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


@app.route('/api/result/<job_id>')
def api_result(job_id):
    """Download the XLSX result for a completed job."""
    with JOBS_LOCK:
        j = JOBS.get(job_id)
    if not j:
        return jsonify({'error': 'Job not found'}), 404
    if j['status'] != 'done':
        return jsonify({'error': f'Job status: {j["status"]}'}), 409
    return send_file(
        BytesIO(j['result']),
        as_attachment=True,
        download_name=j.get('fname', f'NSO_Plan_{datetime.date.today().isoformat()}.xlsx'),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/api/job-status/<job_id>')
def api_job_status(job_id):
    with JOBS_LOCK:
        j = JOBS.get(job_id)
    if not j:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'status': j['status'],
        'pct': j['pct'],
        'msg': j['msg'],
        'row_count': j.get('row_count', 0),
    })


SHEET_EXT = ('.xlsx', '.xlsm', '.xlsb', '.xls', '.csv')


def _input_path(folder, name):
    """The input file `name` inside `folder`, or None. A bare file name with a spreadsheet extension only (audit
    2026-10-06: folder + name came straight from the request, so any signed-in user could read any file on the host
    through Landing's /nso/ route, e.g. a name climbing out of the folder with "..")."""
    if (not folder or not name or os.path.basename(name) != name or name in ('.', '..')
            or not name.lower().endswith(SHEET_EXT) or not os.path.isdir(folder)):
        return None
    path = os.path.join(folder, name)
    return path if os.path.isfile(path) else None


@app.route('/api/read-file')
def api_read_file():
    """Serve a file from the scanned folder for client-side parsing (AOP table)."""
    folder = request.args.get('folder', '').strip()
    name   = request.args.get('name', '').strip()
    if not folder or not name:
        return jsonify({'error': 'Missing folder or name'}), 400
    path = _input_path(folder, name)
    if not path:
        return jsonify({'error': 'File not found'}), 404
    return send_file(path, as_attachment=False)


@app.route('/api/parse-nso')
def api_parse_nso():
    """Parse NSO Details server-side and return AOP rows as JSON.
    Avoids xlsx.js date-column off-by-one issues in the browser."""
    folder = request.args.get('folder', '').strip()
    name   = request.args.get('name', '').strip()
    if not folder or not name:
        return jsonify({'error': 'Missing folder or name'}), 400
    path = _input_path(folder, name)
    if not path:
        return jsonify({'error': 'File not found'}), 404
    try:
        with open(path, 'rb') as f:
            data = f.read()
        df = load_nso_details(data)
        stores = []
        for _, row in df.iterrows():
            sc = str(row.get('Store Code', '')).strip()
            if not sc or sc.lower() == 'nan':
                continue
            stores.append({
                'storeCode': sc,
                'refCode':   str(row.get('Ref Code', '')).strip(),
                'grade':     str(row.get('Grade', '')).strip(),
                'type':      str(row.get('Type', row.get('Store Type', ''))).strip(),
                'zone':      str(row.get('Zone', '')).strip(),
                'sep': float(row.get('SEP', 0) or 0),
                'oct': float(row.get('OCT', 0) or 0),
                'nov': float(row.get('NOV', 0) or 0),
                'dec': float(row.get('DEC', 0) or 0),
                'jan': float(row.get('JAN', 0) or 0),
                'feb': float(row.get('FEB', 0) or 0),
            })
        return jsonify({'stores': stores})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    import os as _os
    port = int(_os.environ.get('PORT', PORT))
    print(f"Starting NSO Plan Distributor v2 on http://localhost:{port}")
    app.run(host='127.0.0.1', port=port,   # reached via Landing /nso/ (one address)
            debug=False)
