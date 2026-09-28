"""Shared attribute master: xlsx -> rows transform, and SalesPlan's DB-first /
xlsx-fallback read (incl. cache fingerprint). No DB needed - db.base is stubbed.
Run directly: python test_attribute_master.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "SalesPlan", "backend"))

from attribute_master import DEFAULT_XLSX, xlsx_to_rows  # noqa: E402
from engines import attribute_correction_engine as ace  # noqa: E402


class _FakeEngine:
    def __init__(self, rows, ts="2026-09-24 10:00:00+05:30"):
        self.rows, self.ts = rows, ts

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql):
        s = str(sql)
        out = [(len(self.rows), self.ts)] if "count(*)" in s else \
              [(r["division"], r["section"], r["department"], r["attribute1"]) for r in self.rows]
        return types.SimpleNamespace(fetchall=lambda: out)


def _use_db(engine):
    """engine=None -> db layer unimportable (standalone SalesPlan / no DATABASE_URL)."""
    for m in ("db", "db.base"):
        sys.modules.pop(m, None)
    if engine is None:
        sys.modules["db.base"] = None  # makes `from db.base import engine` raise ImportError
        return
    pkg, base = types.ModuleType("db"), types.ModuleType("db.base")
    base.engine, pkg.base = engine, base
    sys.modules["db"], sys.modules["db.base"] = pkg, base


def test_xlsx_to_rows():
    rows = xlsx_to_rows(DEFAULT_XLSX)
    assert len(rows) == 978, len(rows)  # 974 + the 28 Sep 2026 department split (+9 new, -5 old)
    assert set(rows[0]) == {"department", "division", "section", "attribute1", "source_file"}
    by = {r["department"]: r for r in rows}
    assert by["MW_JACKET"]["attribute1"] == "HVY WINTER"
    assert by["MW_PULLOVER"]["attribute1"] == "LT WINTER"
    assert sum(r["attribute1"] is None for r in rows) == 206   # blanks stay NULL, not "nan"
    assert all(r["department"] == r["department"].strip() for r in rows)


def test_db_first_then_xlsx_fallback():
    rows = xlsx_to_rows(DEFAULT_XLSX)
    active = {d: {r["department"] for r in rows} for d in ace.PLAN_DIV_MASTERS}

    _use_db(None)
    assert isinstance(ace._mtime(ace.ATTR_MASTER_PATH), float)            # xlsx mtime
    from_xlsx = ace._build_attr_dept_map(active)
    assert from_xlsx["MENS"]["MW_JACKET"] == "HVY WINTER"

    _use_db(_FakeEngine([]))                                               # table empty -> xlsx
    assert isinstance(ace._mtime(ace.ATTR_MASTER_PATH), float)
    assert ace._build_attr_dept_map(active) == from_xlsx

    fake = _FakeEngine([dict(r) for r in rows])
    _use_db(fake)
    assert ace._mtime(ace.ATTR_MASTER_PATH)[:2] == ("db", 978)             # DB fingerprint
    assert ace._build_attr_dept_map(active) == from_xlsx                   # same data both paths

    # DB edit must be visible: flip one attribute, bump updated_at -> cache invalidates
    ace._cache.clear()
    assert ace._get_attr_map_cached(active)["MENS"]["MW_JACKET"] == "HVY WINTER"
    assert ace._cache_valid(next(iter(ace._cache)), ace.ATTR_MASTER_PATH)
    next(r for r in fake.rows if r["department"] == "MW_JACKET")["attribute1"] = "LT WINTER"
    fake.ts = "2026-09-24 11:00:00+05:30"
    assert ace._get_attr_map_cached(active)["MENS"]["MW_JACKET"] == "LT WINTER"


if __name__ == "__main__":
    test_xlsx_to_rows()
    test_db_first_then_xlsx_fallback()
    print("ok - attribute master: xlsx->rows transform + DB-first/xlsx-fallback read")
