"""
Builds app/sales.json from the RS sales data lake parquet (SL_V by store/department/month),
aligned to the same month axis as app/kb.json so the frontend can tag sales with listing
history. See PRD_LOGIC.md for the schema and scope this produces.

Source: latest full re-export in the sales data_lake folder (same "always read only the
latest file" pattern as the Calendar Engine day-wise source -- see memory).

Usage: python build_sales.py
"""
import json
import os
import re
import pyarrow.parquet as pq

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import sales_dir  # noqa: E402  - same data-lake setting as the core syncs
SALES_DIR = sales_dir()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # repo root
from rs_common.lake_files import latest_path  # noqa: E402 - the one "which file" rule (29 Sep 2026)

# Same apparel-only scope as extract_one.py / build_knowledge_base.py.
ALLOWED_TOKENS = {
    'ACCESSORIES', 'BOYS DESIGNER', 'FABRIC-SUITING', 'GIRLS DESIGNER', 'KB', 'KBW',
    'KG', 'KGW', 'KI', 'KIW', 'KW', 'L', 'LW', 'LWW', 'M', 'ME', 'ML', 'MSE', 'MU',
    'MW', 'RAINCOAT',
}
MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def category_token(dept):
    return dept.split('_', 1)[0] if '_' in dept else dept


def latest_sales_file():
    """The newest complete month-wise export - the same file the Calendar engine and BIS read (rs_common.lake_files;
    it used to go by the _YYYYMMDDTHHMMSS in the name, which a 'master.parquet' export doesn't have)."""
    p = latest_path(SALES_DIR)
    if not p:
        raise ValueError(f"No parquet files found in {SALES_DIR}")
    return p


def build():
    kb_path = os.path.join(BASE, 'app', 'kb.json')
    with open(kb_path, encoding='utf-8') as f:
        kb_months = json.load(f)['months']
    # canonical "Mon'YY" (no trailing "(Till Date)" etc.) -> the exact kb.json month label
    canon_to_label = {re.match(r"[A-Za-z]{3}'\d{2}", m).group(0): m for m in kb_months}

    path = latest_sales_file()
    print(f"Using {path}")
    table = pq.ParquetFile(path).read(columns=['STORE_NAME', 'DEPARTMENT', 'BILLMONTH', 'SL_V'])

    stores = table.column('STORE_NAME').to_pylist()
    depts = table.column('DEPARTMENT').to_pylist()
    bmonths = table.column('BILLMONTH').to_pylist()
    values = table.column('SL_V').to_pylist()

    agg = {}  # (store, dept, label) -> sum(SL_V)
    skipped_scope = 0
    skipped_range = 0
    for store, dept, bm, v in zip(stores, depts, bmonths, values):
        if store is None or dept is None or bm is None:
            continue
        if category_token(dept) not in ALLOWED_TOKENS:
            skipped_scope += 1
            continue
        canon = f"{MONTH_ABBR[bm.month - 1]}'{bm.year % 100:02d}"
        label = canon_to_label.get(canon)
        if label is None:
            skipped_range += 1
            continue
        key = (store, dept, label)
        agg[key] = agg.get(key, 0.0) + (v or 0.0)

    data = {}
    for (store, dept, label), total in agg.items():
        data.setdefault(store, {}).setdefault(dept, {})[label] = round(total, 2)

    out = {'months': kb_months, 'metric': 'SL_V', 'data': data}
    out_path = os.path.join(BASE, 'app', 'sales.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))

    print(f"OK: {len(agg)} store/dept/month sales rows (skipped {skipped_scope} non-apparel, "
          f"{skipped_range} outside kb.json's month range) -> {out_path} "
          f"({os.path.getsize(out_path)/1024/1024:.2f} MB)")


def demo():
    """Smallest runnable check: category_token + canonical month matching."""
    assert category_token('LW_U_TEES') == 'LW'
    assert category_token('RAINCOAT') == 'RAINCOAT'
    canon_to_label = {"Sep'26": "Sep'26(Till Date)", "Jan'23": "Jan'23"}
    assert canon_to_label.get("Sep'26") == "Sep'26(Till Date)"
    print("demo OK")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        demo()
    else:
        build()
