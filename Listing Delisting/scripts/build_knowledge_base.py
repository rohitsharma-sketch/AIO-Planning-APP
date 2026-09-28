"""
Builds app/kb.json from the 4 Directory Listing xlsx files (2023-2026).
See PRD_LOGIC.md for the schema this produces and why.

Usage: python build_knowledge_base.py
"""
import json
import os
import re
import openpyxl

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import DATA_DIR  # noqa: E402
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = {
    '23': "Directories/2023/Directory - Listing'23.xlsx",
    '24': "Directories/2024/Directory - Listing'24.xlsx",
    '25': "Directories/2025/Directory - Listing'25.xlsx",
    '26': "Directories/2026/Directory - Listing'26.xlsx",
}
MONTH_ORDER = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def month_sort_key(m):
    # "Sep'26(Till Date)" -> ('26', 'Sep')
    base = re.match(r"([A-Za-z]{3})'(\d{2})", m)
    mon, yy = base.group(1), base.group(2)
    return (yy, MONTH_ORDER.index(mon))


# Data-lake department split (5 Sep 2026 export, back to 2019): the listing sheets use the new names from Jan'26
# and the old ones before. Each part takes its old department's listing for the months it has no record of its own,
# so its history is continuous; an old name that is not one of its own parts then drops out (user, 2026-09-28).
DEPT_SPLITS = {
    "MSE_PYJAMA": ["MSE_HSR PYJAMA", "MSE_TXTL PYJAMA"], "KB_T-SHIRT H/S": ["KB_R/N T-SHIRT H/S", "KB_POLO T-SHIRT H/S"],
    "KB_BERMUDA": ["KB_HSR BERMUDA", "KB_TXTL BERMUDA"], "LW_L_PALAZZO": ["LW_L_WES PALAZZO", "LW_L_ETH PALAZZO"],
    "LW_L_JEGGING": ["LW_L_DNM JOGGER", "LW_L_WVN JOGGER"], "L_IN_BRA": ["L_IN_BRA", "L_IN_SPRT BRA"],
}


def apply_dept_splits(combos):
    """combos {(store, dept): {month: rev}} -> the same, on the new department names."""
    for (store, dept) in [k for k in combos if k[1] in DEPT_SPLITS]:
        old = combos[(store, dept)]
        for part in DEPT_SPLITS[dept]:
            own = combos.setdefault((store, part), {})
            for month, rev in old.items():
                own.setdefault(month, rev)
        if dept not in DEPT_SPLITS[dept]:
            del combos[(store, dept)]
    return combos


def build():
    combos = {}  # (store, dept) -> {month: rev}
    months_seen = set()
    seen_keys = set()

    for yy, relpath in FILES.items():
        path = os.path.join(DATA_DIR, relpath)   # RS_planning/data/listing (moved 2026-09-26)
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = next(rows)
        idx = {h: i for i, h in enumerate(header)}
        for r in rows:
            store, dept, rev, month = r[idx['STORE_NAME']], r[idx['DEPARTMENT']], r[idx['MC_LISTING(Rev)']], r[idx['Month']]
            if store is None or dept is None or month is None:
                continue
            key = (store, dept, month)
            if key in seen_keys:
                raise ValueError(f"Duplicate {key} found while building KB (from {relpath})")
            seen_keys.add(key)
            months_seen.add(month)
            combos.setdefault((store, dept), {})[month] = rev
        wb.close()
        print(f"{yy}: done, running combos={len(combos)}")

    apply_dept_splits(combos)
    months = sorted(months_seen, key=month_sort_key)
    stores = sorted({s for s, _ in combos})
    departments = sorted({d for _, d in combos})

    data = {}
    for (store, dept), month_map in combos.items():
        data.setdefault(store, {})[dept] = ''.join(month_map.get(m, '.') for m in months)

    kb = {'months': months, 'stores': stores, 'departments': departments, 'data': data}

    out_path = os.path.join(BASE, 'app', 'kb.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(kb, f, separators=(',', ':'))

    print(f"OK: {len(combos)} combos, {len(stores)} stores, {len(departments)} departments, "
          f"{len(months)} months -> {out_path} ({os.path.getsize(out_path)/1024/1024:.2f} MB)")


def demo():
    """Smallest runnable check: month_sort_key orders correctly incl. the '(Till Date)' suffix."""
    months = ["Sep'26(Till Date)", "Jan'23", "Dec'23", "Apr'23", "Feb'26"]
    ordered = sorted(months, key=month_sort_key)
    assert ordered == ["Jan'23", "Apr'23", "Dec'23", "Feb'26", "Sep'26(Till Date)"], ordered
    c = apply_dept_splits({("S", "MSE_PYJAMA"): {"Dec'25": "Y"}, ("S", "MSE_HSR PYJAMA"): {"Jan'26": "N"},
                           ("S", "L_IN_BRA"): {"Dec'25": "Y"}})
    assert c == {("S", "MSE_HSR PYJAMA"): {"Jan'26": "N", "Dec'25": "Y"}, ("S", "MSE_TXTL PYJAMA"): {"Dec'25": "Y"},
                 ("S", "L_IN_BRA"): {"Dec'25": "Y"}, ("S", "L_IN_SPRT BRA"): {"Dec'25": "Y"}}, c
    print("demo OK")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        demo()
    else:
        build()
