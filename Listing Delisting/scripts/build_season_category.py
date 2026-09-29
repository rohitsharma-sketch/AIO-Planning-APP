"""
Builds season_category per apparel department from the sales parquet's ATTRIBUTE1 column and
merges it into app/seasonality.json (alongside the existing seasonality_index/seasonality_tier
CV-based magnitude signal -- kept, just no longer the primary category).

ATTRIBUTE1 is real merchandise-master data (not derived): REGULAR, SUMMER, LT WINTER,
HVY WINTER, PREWINTER, OCCASIONAL (apparel departments) plus GM/RETAIL (non-apparel, out of
scope, same ALLOWED_TOKENS filter as build_sales.py/extract_one.py). Verified 100% pure per
department across 14.2M apparel rows / 263 departments -- zero nulls, zero multi-value depts.
This script re-asserts that purity and hard-fails if it ever stops holding (same
data-integrity convention as the rest of this project).

A handful of kb.json/seasonality.json departments have no apparel sales rows at all (no
ATTRIBUTE1 data to read) -- those get season_category: null, not a hard fail, same "coverage
gap, not corruption" treatment as seasonality.json's years_count_by_month gaps.

Usage: python build_season_category.py
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
import sys  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))  # repo root
from rs_common.lake_files import latest_path  # noqa: E402 - the one "which file" rule (29 Sep 2026)

# Same apparel-only scope as extract_one.py / build_sales.py / build_knowledge_base.py.
ALLOWED_TOKENS = {
    'ACCESSORIES', 'BOYS DESIGNER', 'FABRIC-SUITING', 'GIRLS DESIGNER', 'KB', 'KBW',
    'KG', 'KGW', 'KI', 'KIW', 'KW', 'L', 'LW', 'LWW', 'M', 'ME', 'ML', 'MSE', 'MU',
    'MW', 'RAINCOAT',
}


def category_token(dept):
    return dept.split('_', 1)[0] if '_' in dept else dept


def normalize(attr):
    return attr.strip().lower().replace(' ', '_')


def latest_sales_file():
    """The newest complete month-wise export - the same file the Calendar engine and BIS read (rs_common.lake_files;
    it used to go by the _YYYYMMDDTHHMMSS in the name, which a 'master.parquet' export doesn't have)."""
    p = latest_path(SALES_DIR)
    if not p:
        raise ValueError(f"No parquet files found in {SALES_DIR}")
    return p


def extract_season_category():
    path = latest_sales_file()
    print(f"Using {path}")
    table = pq.ParquetFile(path).read(columns=['DEPARTMENT', 'ATTRIBUTE1'])
    depts = table.column('DEPARTMENT').to_pylist()
    attrs = table.column('ATTRIBUTE1').to_pylist()

    dept_attr = {}
    violations = []
    for dept, attr in zip(depts, attrs):
        if dept is None or category_token(dept) not in ALLOWED_TOKENS:
            continue
        if attr is None:
            violations.append((dept, None, 'NULL'))
            continue
        norm = normalize(attr)
        if dept in dept_attr:
            if dept_attr[dept] != norm:
                violations.append((dept, dept_attr[dept], norm))
        else:
            dept_attr[dept] = norm

    if violations:
        raise ValueError(
            f"ATTRIBUTE1 is not pure per department -- {len(violations)} violations "
            f"(dept, first_value, conflicting_value), e.g. {violations[:10]}"
        )
    return dept_attr


def build():
    dept_attr = extract_season_category()
    print(f"OK: {len(dept_attr)} apparel departments, ATTRIBUTE1 100% pure (0 violations)")

    seasonality_path = os.path.join(BASE, 'app', 'seasonality.json')
    with open(seasonality_path, encoding='utf-8') as f:
        seasonality = json.load(f)

    missing = []
    for dept, entry in seasonality['departments'].items():
        cat = dept_attr.get(dept)
        entry['season_category'] = cat
        if cat is None:
            missing.append(dept)

    seasonality['season_categories'] = sorted(set(dept_attr.values()))
    if missing:
        print(f"Note: {len(missing)} departments have no apparel sales rows (no ATTRIBUTE1 "
              f"data) -- season_category left null: {missing[:10]}{'...' if len(missing) > 10 else ''}")

    with open(seasonality_path, 'w', encoding='utf-8') as f:
        json.dump(seasonality, f, separators=(',', ':'))
    print(f"OK: merged season_category into {seasonality_path} "
          f"({os.path.getsize(seasonality_path)/1024:.1f} KB)")


def demo():
    """Smallest runnable check: normalize() and purity-violation detection."""
    assert normalize('HVY WINTER') == 'hvy_winter'
    assert normalize('REGULAR') == 'regular'
    assert normalize('LT WINTER') == 'lt_winter'

    # Simulate the purity check inline (extract_season_category needs the real parquet).
    def check(rows):
        dept_attr = {}
        violations = []
        for dept, attr in rows:
            if attr is None:
                violations.append((dept, None, 'NULL'))
                continue
            norm = normalize(attr)
            if dept in dept_attr and dept_attr[dept] != norm:
                violations.append((dept, dept_attr[dept], norm))
            else:
                dept_attr[dept] = norm
        return dept_attr, violations

    pure = [('RAINCOAT', 'OCCASIONAL'), ('RAINCOAT', 'OCCASIONAL'), ('KBW_JACKET', 'HVY WINTER')]
    dept_attr, violations = check(pure)
    assert violations == [] and dept_attr['RAINCOAT'] == 'occasional'

    impure = [('RAINCOAT', 'OCCASIONAL'), ('RAINCOAT', 'SUMMER')]
    _, violations = check(impure)
    assert len(violations) == 1
    print("demo OK")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        demo()
    else:
        build()
