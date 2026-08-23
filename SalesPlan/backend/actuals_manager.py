"""
Actuals Manager
================
Single source of truth for imported LY dept-level actual sales.

Lock precedent
--------------
Once actuals for a LY month are imported they are LOCKED.
    - No UI can re-import different values for the same LY month.
    - No UI exposes an unlock button.
    - The only override path is: admin-unlock endpoint called explicitly by Claude,
      with header  X-Admin-Override: force  (not documented in any frontend).
    - Every unlock is journaled in actuals_lock.json under "unlock_log".

File: backend/actuals_lock.json
{
  "locked_ly_months": {
    "Mar'26": {
      "locked": true,
      "imported_at": "...",
      "source_file": "...",
      "record_count": 123
    }
  },
  "unlock_log": []
}
"""

import json, os, re, sys
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

DEPT_CUSTOM_PATH = os.path.join(os.path.dirname(__file__), "engines", "department_custom.json")

_BASE        = os.path.dirname(__file__)
LOCK_PATH    = os.path.join(_BASE, "actuals_lock.json")
ACTUALS_PATH = os.path.join(_BASE, "actuals_store.json")

# Actuals folder beside the backend
ACTUALS_DIR  = os.path.join(_BASE, "..", "Actual Sales")

# Divisions to include in plan (OTHERS excluded)
PLAN_DIVISIONS = {"GM", "KIDS", "LADIES", "MENS", "RETAIL"}

# Maps DIVISION column value → planning division used throughout the engine
# DIV_NEW column is a system artefact, NOT the planning division
DIVISION_COL_TO_PLAN = {
    "KIDS":              "KIDS",
    "LADIES":            "LADIES",
    "MENS":              "MENS",
    "RETAIL":            "RETAIL",
    "NON FOOD":          "RETAIL",
    "FOOTWEAR":          "GM",
    "HOME FURNISHING":   "GM",
    "HOUSEHOLD":         "GM",
    "LIFESTYLE":         "GM",
    "SPORTS  & TOYS":    "GM",   # double-space as in source data
    "SPORTS & TOYS":     "GM",
    "STATIONERY":        "GM",
    "TRAVEL ACCESSORIES":"GM",
    # DIVISION values to exclude: DND, NON-TRADING, FIXED ASSETS, CONSIGNMENT, CDIT
}

# Store tags to exclude
EXCLUDE_TAGS = {"DC", "CLOSED"}

# Month normalisation map (handles "June" → "Jun", "January" → "Jan" etc.)
_MONTH_ABBR = {
    "jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr",
    "may": "May", "jun": "Jun", "june": "Jun",
    "jul": "Jul", "aug": "Aug", "sep": "Sep",
    "oct": "Oct", "nov": "Nov", "dec": "Dec",
}


def _norm_month_col(col_name: str) -> str | None:
    """
    Converts 'Apr\'26 Actual Sales' → 'Apr\'26'
    Converts 'June\'26 Actual Sales' → 'Jun\'26'
    Returns None if not a recognisable month column.
    """
    s = str(col_name).strip()
    # Strip suffix variations
    s = re.sub(r"\s*Actual\s*Sales?.*$", "", s, flags=re.IGNORECASE).strip()
    # Match Mon'YY
    m = re.match(r"([A-Za-z]+)'(\d{2})$", s)
    if not m:
        return None
    mon_raw = m.group(1).lower()
    yr      = m.group(2)
    abbr    = _MONTH_ABBR.get(mon_raw)
    if not abbr:
        return None
    return f"{abbr}'{yr}"


def load_lock() -> dict:
    if os.path.exists(LOCK_PATH):
        with open(LOCK_PATH) as f:
            return json.load(f)
    return {"locked_ly_months": {}, "unlock_log": []}


def save_lock(data: dict):
    with open(LOCK_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_actuals() -> dict:
    """Returns {store: {division: {dept: {ly_month: value}}}}"""
    if os.path.exists(ACTUALS_PATH):
        with open(ACTUALS_PATH) as f:
            return json.load(f)
    return {}


def save_actuals(data: dict):
    with open(ACTUALS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def locked_ly_months() -> list[str]:
    return list(load_lock()["locked_ly_months"].keys())


def import_actuals_file(filepath: str, source_label: str = "") -> dict:
    """
    Parse an actuals Excel/CSV file and store.
    Only processes months NOT already locked.
    Returns summary dict.
    """
    lock = load_lock()
    already_locked = set(lock["locked_ly_months"].keys())

    # Read file
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    df.columns = [str(c).strip() for c in df.columns]

    # Detect month columns
    month_map = {}  # original_col → normalised label
    for col in df.columns:
        label = _norm_month_col(col)
        if label:
            month_map[col] = label

    if not month_map:
        return {"ok": False, "error": "No recognisable month columns found (expected format: Apr'27 Actual Sales)"}

    # Find required columns
    store_col    = next((c for c in df.columns if c.upper() in ("STORE_NAME", "STORE NAME", "STORE")), df.columns[0])
    division_col = next((c for c in df.columns if c.upper() == "DIVISION"), None)
    dept_col     = next((c for c in df.columns if c.upper() == "DEPARTMENT"), None)
    tag_col      = next((c for c in df.columns if c.upper() in ("ST TAG", "TAG", "STORE TAG")), None)

    if division_col is None:
        return {"ok": False, "error": "Could not find DIVISION column in file"}
    if dept_col is None:
        return {"ok": False, "error": "Could not find DEPARTMENT column in file"}

    # Filter rows
    df = df[df[store_col].notna()].copy()
    if tag_col:
        df = df[~df[tag_col].astype(str).str.strip().isin(EXCLUDE_TAGS)]

    # Map DIVISION column → planning division; drop rows not in mapping
    df["_plan_div"] = df[division_col].astype(str).str.strip().map(DIVISION_COL_TO_PLAN)
    df = df[df["_plan_div"].notna()]

    # Identify new months (skip already locked)
    new_months = {col: lbl for col, lbl in month_map.items() if lbl not in already_locked}
    skipped    = {lbl for lbl in month_map.values() if lbl in already_locked}

    if not new_months:
        return {
            "ok": False,
            "error": f"All months in file are already locked: {sorted(skipped)}",
            "locked_months": sorted(already_locked),
        }

    # Load existing actuals
    actuals = load_actuals()

    records = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, row in df.iterrows():
        store    = str(row[store_col]).strip().upper()
        plan_div = str(row["_plan_div"]).strip().upper()
        dept     = str(row[dept_col]).strip().upper()

        if not store or not plan_div or not dept:
            continue

        actuals.setdefault(store, {}).setdefault(plan_div, {}).setdefault(dept, {})

        for orig_col, ly_label in new_months.items():
            val = row.get(orig_col, 0)
            try:
                v = float(val) if pd.notna(val) else 0.0
            except (ValueError, TypeError):
                v = 0.0
            # Aggregate — multiple rows may share same store/plan_div/dept (e.g. sub-depts)
            actuals[store][plan_div][dept][ly_label] = actuals[store][plan_div][dept].get(ly_label, 0.0) + v

        records += 1

    save_actuals(actuals)
    _sync_depts_to_master(actuals)

    # Lock the new months
    for lbl in new_months.values():
        lock["locked_ly_months"][lbl] = {
            "locked": True,
            "imported_at": now_str,
            "source_file": source_label or os.path.basename(filepath),
            "record_count": records,
        }
    save_lock(lock)

    return {
        "ok": True,
        "months_imported": sorted(new_months.values()),
        "months_skipped_locked": sorted(skipped),
        "records_processed": records,
        "imported_at": now_str,
    }


def _sync_depts_to_master(actuals: dict):
    """
    Auto-registers any department seen in actuals that isn't already in
    the custom dept JSON (department_custom.json).
    Attribute defaults to REGULAR — user can adjust in Master Setup.
    """
    # Build set of known depts from master raw + existing custom
    from engines.department_plan import _MASTER_RAW, _load_custom, _save_custom
    known = set()
    for div, dept, _ in _MASTER_RAW:
        known.add((div, dept))
    custom = _load_custom()
    for c in custom:
        known.add((c["division"], c["name"]))

    new_entries = []
    for store_data in actuals.values():
        for div, div_data in store_data.items():
            if div not in PLAN_DIVISIONS:
                continue
            for dept in div_data.keys():
                if (div, dept) not in known:
                    known.add((div, dept))
                    new_entries.append({"division": div, "name": dept, "attribute": "REGULAR"})

    if new_entries:
        custom.extend(new_entries)
        _save_custom(custom)


def admin_unlock_month(ly_month: str, reason: str = "") -> dict:
    """
    ADMIN ONLY — removes lock for a LY month.
    Called only by Claude via X-Admin-Override: force header.
    Every call is journaled.
    """
    lock = load_lock()
    if ly_month not in lock["locked_ly_months"]:
        return {"ok": False, "error": f"{ly_month} is not locked"}

    entry = lock["locked_ly_months"].pop(ly_month)
    lock["unlock_log"].append({
        "month": ly_month,
        "original_import": entry,
        "unlocked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": reason,
    })
    save_lock(lock)

    # Remove from actuals store
    actuals = load_actuals()
    removed = 0
    for store_data in actuals.values():
        for div_data in store_data.values():
            for dept_data in div_data.values():
                if ly_month in dept_data:
                    del dept_data[ly_month]
                    removed += 1
    save_actuals(actuals)

    return {"ok": True, "month_unlocked": ly_month, "values_removed": removed}


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
