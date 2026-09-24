"""No-DB check: two ref months landing on the same TY month are summed, not
overwritten - in _merge_reindex_results, the server-side wide CSV and
SalesPlan's get_sales_data pivot. Run: python test_reindex_merge.py"""
import csv
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "..", "SalesPlan", "backend"))

import scans  # noqa: E402
import reindex_csv_worker  # noqa: E402
from engines import sync_engine  # noqa: E402

KF = ["store", "division"]


def _res(month_rows):
    return {"ok": True, "source": "mw", "keyFields": KF, "grain": "store_division", "metric": "SL_V",
            "rows": month_rows, "actualRows": [], "columns": sorted({r["col"] for r in month_rows}),
            "actualColumns": [], "rowsRead": 1, "rowsMapped": len(month_rows)}


oct_ref = _res([{"store": "ABD", "division": "FOOTWEAR", "col": "2026-10", "value": 1.0},
                {"store": "ABD", "division": "FOOTWEAR", "col": "2026-11", "value": 10.0}])
nov_ref = _res([{"store": "ABD", "division": "FOOTWEAR", "col": "2026-11", "value": 5.5}])

merged = scans._merge_reindex_results([oct_ref, nov_ref])
by_col = {r["col"]: r["value"] for r in merged["rows"]}
assert by_col == {"2026-10": 1.0, "2026-11": 15.5} and len(merged["rows"]) == 2, merged["rows"]
assert oct_ref["rows"][1]["value"] == 10.0  # inputs not mutated

# Wide pivots must sum duplicate (key, col) rows too (unmerged input on purpose).
dup = _res(oct_ref["rows"] + nov_ref["rows"])
with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "w.csv")
    reindex_csv_worker.write_wide_csv(dup, {"ABD": "BIHAR"}, {}, {}, out)
    with open(out, encoding="utf-8") as f:
        data = [r for r in csv.reader(f) if r and r[0] == "BIHAR" and "ABD" in r]
    assert data and data[-1][-1] == "15.5", data

sync_engine._load_snapshot = lambda s, k: {"grain": "store_division", "keyFields": KF, "columns": ["2026-10", "2026-11"],
                                           "rows": dup["rows"], "computedAt": "x"}
preview = sync_engine.get_sales_data()["preview"]
assert preview[0]["2026-11"] == 15.5, preview
print("test_reindex_merge: OK")
