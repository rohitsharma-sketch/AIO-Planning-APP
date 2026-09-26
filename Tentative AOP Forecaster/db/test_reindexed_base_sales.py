"""No-DB check: MW snapshot keeps 'division' and the AOP toggle splits by it.
Run: python db/test_reindexed_base_sales.py"""
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "RS Planning Platform", "backend", "calendar_engine"))

import scans  # noqa: E402
from db.reindexed_base_sales import get_reindexed_lfl_base_sales  # noqa: E402

# Producer: month-wise key_fields (lowercase 'division') survive persistence.
keep, _ = scans._collapse_for_persistence(["store", "division", "ATTRIBUTE1"], [])
assert keep == ["store", "division", "ATTRIBUTE1"], keep


class _Res:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows

    def scalar(self):
        return self._rows[0][0] if self._rows else None


class _Session:
    def __init__(self, mw_rows, dw_last="2026-08-31"):
        self.mw_rows, self.dw_last = mw_rows, dw_last

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "columns->>-1" in sql:                     # last day of the day-wise ACTUALS
            return _Res([(self.dw_last,)])
        if "SELECT key_fields" in sql:
            return _Res([(["store"], ["2027-04-01"])])
        if "masterdata.stores" in sql:
            return _Res([("S1", "032 - Stores", datetime.date(2020, 1, 1), "SAME STORE")])
        if "source_type = 'mw'" in sql:
            return _Res(self.mw_rows if "elem->>'division'" in sql else [])
        return _Res([("2027-04", 1_000_000.0)])  # DW monthly total: 10 Lakhs


mw = [(d, "2027-04", v) for d, v in [("GM", 2.0), ("KIDS", 3.0), ("LADIES", 3.0), ("MENS", 2.0)]]
out = get_reindexed_lfl_base_sales(_Session(mw))["base_sales"]
assert {d: out[d]["Apr'27"] for d in out} == {"GM": 2.0, "KIDS": 3.0, "LADIES": 3.0, "MENS": 2.0, "RETAIL": 0.0}, out

# No KIDS/LADIES/MENS rows -> no fake split, empty data + note.
res = get_reindexed_lfl_base_sales(_Session([("GM", "2027-04", 9.0), ("RETAIL", "2027-04", 1.0)]))
assert all(v == 0.0 for d in res["base_sales"].values() for v in d.values()), res["base_sales"]
assert res["availableMonths"] == [] and "KIDS/LADIES/MENS" in res["note"], res

# Day-wise export ends mid-April 2026 -> Apr'27 is incomplete: left out with a note, not shown short.
res = get_reindexed_lfl_base_sales(_Session(mw, dw_last="2026-04-27"))
assert res["base_sales"]["KIDS"]["Apr'27"] == 0.0 and "Apr'27" not in res["availableMonths"], res
assert "Apr'27 left out" in res["note"] and "2026-04-27" in res["note"], res["note"]
print("test_reindexed_base_sales: OK")
