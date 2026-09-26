# Listing/Delisting Impact Analysis — Handover

## Project
Building year-wise "Directory Listing" files (one row per **Store × Department × Month**) from raw MC allocation reports, matching the format of the 2026 reference file.

## Target format (from `Directories\2026\Directory - Listing'26.xlsx`)
- Sheet name: `AIO Listing Master'YY`
- Columns: `STORE_NAME, DEPARTMENT, MC_LISTING(Original), MC_LISTING(Rev), Month`
- `MC_LISTING(Rev)` = `MC_LISTING(Original)` with `-` replaced by `N` (`-` is a legacy notation for "unlisted dept / inactive store", not a distinct state)
- **Hard rule**: zero duplicates on (STORE_NAME, DEPARTMENT, Month) combo — this is the only integrity rule
- **Scope**: apparel-only, matching the 2026 file's 21 category-prefix families. Non-apparel categories (footwear `FW_`, home furnishing `HF_`/`HH_`, durables `CDIT_`, luggage/stationery/toys `LS_/ST_/TG_/SF_/TA_`) are excluded even when present in source files.

Allowed department-prefix tokens (text before first `_`, or full name if none):
```
ACCESSORIES, BOYS DESIGNER, FABRIC-SUITING, GIRLS DESIGNER, KB, KBW,
KG, KGW, KI, KIW, KW, L, LW, LWW, M, ME, ML, MSE, MU, MW, RAINCOAT
```

## Source data
`C:\Users\A9820\Downloads\New folder\RAW\<year>\` — one `.xlsb` file per month (12/year, except 2023 which is missing Jan-Mar — see below). Three different report-tool layouts exist across years/months, all with a `Data`/`DATA` sheet somewhere in the workbook:

| Variant | Header row | Notes |
|---|---|---|
| `Display_MC_Wise_Allocation_Report_*` (most of 2023-2025) | row 0 | `STORE_CODE, STORE_NAME, ..., MC_LISTING, ...` — 46-50 cols |
| `MC_Allocation_Requirment_*` type A (2025 Apr) | row 2 | `STORE_NAME, DIVISION, DEPARTMENT, ..., MC_LISTING, ...` — 47 cols |
| `MC_Allocation_Requirment_*` type B (2025 May/Jul/Aug/Sep/Oct/Dec) | row 1, sheet name `DATA` (uppercase) | 53 cols, includes full merchandise universe (not just apparel) — this is why the category filter matters |

Extraction script handles all 3 automatically (case-insensitive sheet name match, scans first 6 rows for the one containing `STORE_NAME` as header).

## Known data gap — 2023 Jan/Feb/Mar
These 3 files (`Display Wise MC_Wise_Allocation_Report_of_31-Jan-23.xlsb`, `28-Feb-23`, `31-Mar-23`) have **no `MC_LISTING` column anywhere** — verified 3 ways: (1) all 4 tabs' content checked, (2) raw zip inspection confirms only 4 worksheet parts exist (no hidden 5th sheet), (3) header row is contiguous columns 0-46/47 with no gap (46/47 cols vs 49 in months that have it). User touched these files on 2026-09-21 (timestamps changed) but re-check showed the column is still absent — likely just unhid the tab in Excel, which doesn't add data. **2023 output currently covers Apr-Dec only (9 months).** If real Q1'23 listing data is found, re-run extraction for those 3 files and re-merge.

## Scripts
Both scripts are saved at `C:\Users\A9820\Downloads\New folder\scripts\` (copies embedded below too, for reference).

### Extraction script
`extract_one.py` — usage: `python extract_one.py "<input.xlsb>" "<output.csv>"`

```python
import sys, os, re, csv
import pyxlsb

MONTH_MAP = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
             7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}

# Category tokens present in the 2026 reference file (AIO Listing Master'26) — apparel-only scope.
ALLOWED_TOKENS = {
    'ACCESSORIES', 'BOYS DESIGNER', 'FABRIC-SUITING', 'GIRLS DESIGNER', 'KB', 'KBW',
    'KG', 'KGW', 'KI', 'KIW', 'KW', 'L', 'LW', 'LWW', 'M', 'ME', 'ML', 'MSE', 'MU',
    'MW', 'RAINCOAT',
}


def category_token(dept):
    return dept.split('_', 1)[0] if '_' in dept else dept


def parse_month_from_filename(path):
    name = os.path.basename(path)
    m = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{2})\.', name)
    if m:
        return f"{m.group(2).title()}'{m.group(3)}"
    m = re.search(r'(\d{2})-(\d{2})-(\d{2})\.', name, re.IGNORECASE)
    if m:
        mm = int(m.group(2))
        return f"{MONTH_MAP[mm]}'{m.group(3)}"
    raise ValueError(f"Could not parse month from filename: {name}")


def find_data_sheet(wb):
    for s in wb.sheets:
        if s.strip().lower() == 'data':
            return s
    raise ValueError(f"No Data sheet found. Sheets: {wb.sheets}")


def find_header(rows_iter, max_scan=6):
    for _ in range(max_scan):
        row = next(rows_iter)
        vals = [c.v for c in row]
        if any(v == 'STORE_NAME' for v in vals):
            return vals
    raise ValueError("Header row with STORE_NAME not found in first rows scanned")


def extract(path, out_csv):
    month = parse_month_from_filename(path)
    with pyxlsb.open_workbook(path) as wb:
        sheet_name = find_data_sheet(wb)
        with wb.get_sheet(sheet_name) as sheet:
            rows_iter = sheet.rows()
            header = find_header(rows_iter)
            idx = {h: i for i, h in enumerate(header) if h is not None}
            for col in ('STORE_NAME', 'DEPARTMENT', 'MC_LISTING'):
                if col not in idx:
                    raise ValueError(f"Missing required column {col} in {path}. Header: {header}")

            combo = {}
            conflicts = []
            bad_values = set()
            for row in rows_iter:
                store = row[idx['STORE_NAME']].v
                dept = row[idx['DEPARTMENT']].v
                mc = row[idx['MC_LISTING']].v
                if store is None or dept is None:
                    continue
                if category_token(dept) not in ALLOWED_TOKENS:
                    continue
                if mc not in ('Y', 'N', '-'):
                    bad_values.add(mc)
                    continue
                key = (store, dept)
                if key in combo:
                    if combo[key] != mc:
                        conflicts.append((key, combo[key], mc))
                else:
                    combo[key] = mc

            if bad_values:
                raise ValueError(f"Unexpected MC_LISTING values in {path}: {bad_values}")
            if conflicts:
                raise ValueError(f"MC_LISTING conflicts within same file for {path}: {conflicts[:10]}")

    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['STORE_NAME', 'DEPARTMENT', 'MC_LISTING(Original)', 'MC_LISTING(Rev)', 'Month'])
        for (store, dept), mc in sorted(combo.items()):
            rev = 'N' if mc == '-' else mc
            w.writerow([store, dept, mc, rev, month])

    return len(combo), month


if __name__ == '__main__':
    path = sys.argv[1]
    out_csv = sys.argv[2]
    n, month = extract(path, out_csv)
    print(f"OK|{path}|{out_csv}|rows={n}|month={month}")
```

Dedup logic: rows differing only by `DISPLAY_TYPE` (TABLE/NON_TABLE fixture split) collapse to one row per (STORE_NAME, DEPARTMENT) — verified `MC_LISTING` is always consistent across these dupes; the script hard-fails if it ever finds a genuine conflict.

### Consolidation script
`consolidate.py` — merges a year's monthly CSVs into the final formatted xlsx, hard-fails on any missing file or any duplicate (store, dept, month) across the merged year. `RESULTS_DIR` below is a placeholder — set it to wherever you're staging per-month CSVs (this session used a temp scratchpad dir that no longer exists).

```python
import csv
import glob
import sys
import openpyxl
from openpyxl.styles import Font

RESULTS_DIR = r"<path to folder containing per-year subfolders of monthly CSVs>"

HEADER = ['STORE_NAME', 'DEPARTMENT', 'MC_LISTING(Original)', 'MC_LISTING(Rev)', 'Month']
COL_WIDTHS = {'A': 24.09, 'B': 28.54, 'C': 19.73, 'D': 17.63, 'E': 14.63}


def consolidate(year_yy, out_path, sheet_name, expected_files):
    csv_files = sorted(glob.glob(rf"{RESULTS_DIR}\{year_yy}\*.csv"))
    found_names = {f.split('\\')[-1] for f in csv_files}
    missing = set(expected_files) - found_names
    if missing:
        raise ValueError(f"Missing expected CSVs for {year_yy}: {missing}")
    if len(csv_files) != len(expected_files):
        raise ValueError(f"Expected {len(expected_files)} monthly CSVs for {year_yy}, found {len(csv_files)}: {found_names}")

    all_rows = []
    seen = {}
    for f in csv_files:
        with open(f, newline='', encoding='utf-8') as fh:
            r = csv.reader(fh)
            header = next(r)
            if header != HEADER:
                raise ValueError(f"Header mismatch in {f}: {header}")
            for row in r:
                key = (row[0], row[1], row[4])  # store, dept, month
                if key in seen:
                    raise ValueError(f"Duplicate store+department+month combo {key} (from {f}, also in {seen[key]})")
                seen[key] = f
                all_rows.append(row)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(HEADER)
    for c in ws[1]:
        c.font = Font(name='Aptos Narrow', bold=True, size=11)
    for col, width in COL_WIDTHS.items():
        ws.column_dimensions[col].width = width
    for row in all_rows:
        ws.append(row)
    wb.save(out_path)
    return len(all_rows), len(csv_files)
```

## Current state (as of 2026-09-21)

| Year | Output file | Rows | Months | Status |
|---|---|---|---|---|
| 2023 | `Directories\2023\Directory - Listing'23.xlsx` | 171,404 | Apr-Dec (9) | Done — Jan-Mar blocked on missing source column |
| 2024 | `Directories\2024\Directory - Listing'24.xlsx` | 278,194 | Jan-Dec (12) | Done |
| 2025 | `Directories\2025\Directory - Listing'25.xlsx` | 369,325 | Jan-Dec (12) | Done |
| 2026 | `Directories\2026\Directory - Listing'26.xlsx` | 373,339 | Jan-Sep(till date) | Pre-existing reference file, not built by this session |

All four files verified zero duplicates on (STORE_NAME, DEPARTMENT, Month).

## Open items
- 2023 Jan/Feb/Mar: no `MC_LISTING` column found in source `.xlsb` files by any check (all tabs, zip-level sheet count, header column continuity). User attempted a fix on 2026-09-21 but file structure was unchanged afterward. Needs either a different source file or confirmation this quarter simply wasn't tracked.
- Not yet asked: whether 2027+ or pre-2023 years exist / are wanted.
- Not yet started: the actual listing/delisting *comparison* analysis across years (this handover only covers building the per-year directories — the stated project goal is analyzing changes between them).
