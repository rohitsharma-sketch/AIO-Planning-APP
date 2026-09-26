import csv
import glob
import sys
import openpyxl
from openpyxl.styles import Font

RESULTS_DIR = r"C:\Users\A9820\AppData\Local\Temp\claude\C--Users-A9820-Documents-CLaude---New-Projects-Buyer-s-Input-Sheet\373c0115-a433-4c82-b9ff-baf150a2c94c\scratchpad\results"

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


if __name__ == '__main__':
    files_2024 = [f"{m}24.csv" for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']]
    files_2025 = [f"{m}25.csv" for m in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']]

    n, nf = consolidate('2024', r"C:\Users\A9820\Downloads\New folder\Directories\2024\Directory - Listing'24.xlsx", "AIO Listing Master'24", files_2024)
    print(f"2024: {n} rows from {nf} files")

    n, nf = consolidate('2025', r"C:\Users\A9820\Downloads\New folder\Directories\2025\Directory - Listing'25.xlsx", "AIO Listing Master'25", files_2025)
    print(f"2025: {n} rows from {nf} files")
