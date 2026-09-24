"""Shared attribute master: department -> ATTRIBUTE1 (REGULAR / SUMMER / PREWINTER /
LT WINTER / HVY WINTER / OCCASIONAL / GM / RETAIL).

One DB table every RS_planning app reads instead of its own copy of
`att master.xlsx` (the "hive mind" shared knowledge base). Mirrors the xlsx
columns DIVISION, SECTION, DEPARTMENT, ATTRIBUTE1; DEPARTMENT is unique in
every copy of the file seen, so it is the key. ATTRIBUTE1 is nullable - ~200
rows (FIXED ASSETS, NON-TRADING, ...) have none in the source.

Create + load (run from `Tentative AOP Forecaster/`):
    python -m db.attribute_master                          # repo xlsx
    python -m db.attribute_master "a.xlsx" "b.xlsx"        # several files, later wins per department

Upsert only: a department dropped from the xlsx stays in the table.
updated_at moves only when a row actually changes, so (count, max(updated_at))
is a valid cache fingerprint for readers (SalesPlan attribute_correction_engine).
"""
import os
import sys

import pandas as pd
from sqlalchemy import text

DEFAULT_XLSX = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "SalesPlan", "Attribute Master", "att master.xlsx"))

REQUIRED_COLS = ("DIVISION", "SECTION", "DEPARTMENT", "ATTRIBUTE1")

DDL = """
CREATE TABLE IF NOT EXISTS masterdata.attribute_master (
    department  TEXT PRIMARY KEY,
    division    TEXT NOT NULL,
    section     TEXT,
    attribute1  TEXT,
    source_file TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

UPSERT = """
INSERT INTO masterdata.attribute_master AS t (department, division, section, attribute1, source_file)
VALUES (:department, :division, :section, :attribute1, :source_file)
ON CONFLICT (department) DO UPDATE SET
    division = EXCLUDED.division, section = EXCLUDED.section,
    attribute1 = EXCLUDED.attribute1, source_file = EXCLUDED.source_file, updated_at = now()
WHERE (t.division, t.section, t.attribute1)
      IS DISTINCT FROM (EXCLUDED.division, EXCLUDED.section, EXCLUDED.attribute1)
"""


def _clean(v):
    if v is None or pd.isna(v):
        return None
    s = str(v).replace("\xa0", " ").strip()
    return s or None


def xlsx_to_rows(path: str) -> list[dict]:
    """att master.xlsx -> upsert rows, one per department (last occurrence wins)."""
    df = pd.read_excel(path)
    df.columns = [str(c).strip().upper() for c in df.columns]
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing column(s) {missing}; found {list(df.columns)}")
    rows = {}
    for r in df.to_dict("records"):
        dept, div = _clean(r["DEPARTMENT"]), _clean(r["DIVISION"])
        if not dept or not div:
            continue
        rows[dept] = {
            "department": dept, "division": div,
            "section": _clean(r["SECTION"]), "attribute1": _clean(r["ATTRIBUTE1"]),
            "source_file": os.path.basename(path),
        }
    return list(rows.values())


def load(paths: list[str]) -> None:
    from db.base import engine

    rows = {}
    for p in paths:
        rows.update({r["department"]: r for r in xlsx_to_rows(p)})
    with engine.begin() as c:
        c.execute(text(DDL))
        if rows:
            c.execute(text(UPSERT), list(rows.values()))
        total = c.execute(text("SELECT count(*) FROM masterdata.attribute_master")).scalar()
    print(f"attribute_master: {len(rows)} rows from {len(paths)} file(s) upserted; table now holds {total}")


if __name__ == "__main__":
    load(sys.argv[1:] or [DEFAULT_XLSX])
