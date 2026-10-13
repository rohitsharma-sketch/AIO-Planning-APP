"""plan_versions.changes: what moved between two saved plans. python -m pytest engines/test_plan_versions.py"""
from engines.plan_versions import changes, totals


def _snap(dept, off=None, months=("Mar'27",), bis="2026-10-13T10:00"):
    return {"cube": {"dept": dept, "off": off or {}, "months": list(months)}, "inputs": {"bis_saved_at": bis}, "nd_map": {}}


def test_changes():
    a = _snap({"MENS": {"ML_JEANS": {"S1": {"Mar'27": [10.0, 11.0, 5.5, 5.5]}},
                        "MU_OLD": {"S1": {"Mar'27": [2.0, 2.0, 1.0, 1.0]}}}})
    b = _snap({"MENS": {"ML_JEANS": {"S1": {"Mar'27": [10.0, 12.5, 6.0, 6.5]}},
                        "MU_NEW": {"S1": {"Mar'27": [0.0, 1.0, 0.5, 0.5]}}}},
              off={"MENS": {"MU_OLD": {"S1": {"Mar'27": 2.0}}}}, bis="2026-10-13T12:00")
    assert totals(b["cube"])["ly"] == 12.0 and totals(b["cube"])["ty"] == 13.5   # inactive LY counts, plan 0
    c = changes(a, b, "V1", "live", {"levels": ["division"]}, {"levels": ["division", "month"]})
    h = {x["h"]: x["t"] for x in c["lines"]}
    assert "+0.50 L" in h["Plan"] and "MENS +0.5 L" in h["Divisions"]
    assert "MU_NEW" in h["Departments planned now"] and "MU_OLD" in h["Departments no longer planned"]
    assert h["Biggest department moves"].startswith("MU_OLD -2.0 L") and "BIS saved again" in h["Why it moved"]
    assert "Layout" in h and c["added"] == 1 and c["dropped"] == 1
    assert {x["h"] for x in changes(a, a, "V1", "V1")["lines"]} == {"Plan", "Divisions"}
