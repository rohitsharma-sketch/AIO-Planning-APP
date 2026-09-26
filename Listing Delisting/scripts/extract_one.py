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
