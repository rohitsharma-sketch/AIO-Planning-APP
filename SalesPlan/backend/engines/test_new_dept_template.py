"""python engines/test_new_dept_template.py (from SalesPlan/backend) - the New Departments template's rules. No DB."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines.dept_sales_engine import ND_COLS, parse_new_dept_template  # noqa: E402

DIVS = {"KB_JEANS": "KIDS", "LW_KURTI": "LADIES", "M_SHIRT": "MENS"}
ok = pd.DataFrame([["KIDS", "KB_JEANS F/S", "KB_JEANS", 120, 20],     # a new dept may be bigger than its ref
                   ["", "LW_KURTI SET", "lw_kurti", 50, None]], columns=ND_COLS)   # division from REF; reduction = new %
m, p = parse_new_dept_template(ok, DIVS)
assert not p and m == {"KIDS": {"KB_JEANS F/S": {"ref_dept": "KB_JEANS", "new_dept_pct": 120.0, "ref_reduction_pct": 20.0}},
                       "LADIES": {"LW_KURTI SET": {"ref_dept": "lw_kurti", "new_dept_pct": 50.0, "ref_reduction_pct": 50.0}}}, (m, p)

bad = pd.DataFrame([["KIDS", "X1", "NOPE", 10, 10],          # unknown ref
                    ["MENS", "X2", "KB_JEANS", 10, 10],      # ref in another division
                    ["KIDS", "X3", "KB_JEANS", 10, 150],     # the ref can't lose more than it has
                    ["KIDS", "X4", "", 10, 10],              # ref missing
                    ["KIDS", "X5", "KB_JEANS", 10, 10],
                    ["KIDS", "x5", "KB_JEANS", 10, 10],      # duplicate new dept
                    ["KIDS", "KB_JEANS", "KB_JEANS", 120, 120]],   # its own ref: changes nothing
                   columns=ND_COLS)
m, p = parse_new_dept_template(bad, DIVS)
assert len(p) == 6 and all(any(f"Row {r}" in x for x in p) for r in (2, 3, 4, 5, 7, 8)), p
assert any("changes nothing" in x for x in p) and any("can't lose more" in x for x in p), p

legacy = pd.DataFrame({"NEW MC": ["KB_JEANS F/S"], "REF. MC": ["KB_JEANS"], "Mar P1": [0.4], "Mar P2": [0.6]})   # old folder file
m, p = parse_new_dept_template(legacy, DIVS)
assert not p and abs(m["KIDS"]["KB_JEANS F/S"]["new_dept_pct"] - 50.0) < 1e-12, (m, p)

assert parse_new_dept_template(pd.DataFrame(columns=ND_COLS), DIVS)[1] == ["The file has no new departments - fill at least one row."]

# a new department the master marks inactive (2026-10-01, LW_U_CORD SETS) is planned by the template: it turns active
# and its carve counts in the division total
from engines.dept_sales_engine import apply_new_dept_adjustments  # noqa: E402
plan = {"stores": {"S": {"divisions": {"LADIES": {"months": {"Mar'27": {"departments": {
    "LW_U_DRESS": {"ly": 10.0, "ty": 10.0, "ty_p1": 4.0, "ty_p2": 6.0, "active": True},
    "LW_U_CORD SETS": {"ly": 0.0, "ty": 0.0, "ty_p1": 0.0, "ty_p2": 0.0, "active": False}}}}}}}}}
md = apply_new_dept_adjustments(plan, {"LADIES": {"LW_U_CORD SETS": {"ref_dept": "LW_U_DRESS", "new_dept_pct": 20,
                                                                      "ref_reduction_pct": 20}}})["stores"]["S"]["divisions"]["LADIES"]["months"]["Mar'27"]
c = md["departments"]["LW_U_CORD SETS"]
assert c["active"] and abs(c["ty"] - 2) < 1e-12 and abs(md["div_total_ty"] - 10) < 1e-12 and abs(c["cont_pct"] - 20) < 1e-9, md
# 2026-10-13: the new department's plan IS ref x New dept % (its own plan is replaced, not added to), and the division is
# re-balanced on the mix back to its pre-carve total - one factor for every store, so the ratio holds everywhere
def _m(depts):
    return {"divisions": {"LADIES": {"months": {"Mar'27": {"departments": {
        k: {"ly": v, "ty": v, "ty_p1": v / 2, "ty_p2": v / 2, "active": True} for k, v in depts.items()}}}}}}
p2 = {"stores": {"A": _m({"FNCY": 6.0, "JAIPURI": 0.5, "KURTI": 10.0}), "B": _m({"FNCY": 2.0, "JAIPURI": 0.2, "KURTI": 5.0})}}
apply_new_dept_adjustments(p2, {"LADIES": {"JAIPURI": {"ref_dept": "FNCY", "new_dept_pct": 25, "ref_reduction_pct": 0}}})
dd = {s: p2["stores"][s]["divisions"]["LADIES"]["months"]["Mar'27"]["departments"] for s in "AB"}
for s_ in "AB":   # exactly 25% of the reference in every store, P1 + P2 = TY
    assert abs(dd[s_]["JAIPURI"]["ty"] / dd[s_]["FNCY"]["ty"] - 0.25) < 1e-12, dd[s_]
    assert all(abs(v["ty_p1"] + v["ty_p2"] - v["ty"]) < 1e-9 for v in dd[s_].values()), dd[s_]
tot = sum(v["ty"] for s_ in "AB" for v in dd[s_].values())
assert abs(tot - (16.5 + 7.2)) < 1e-9, tot   # the division total is what it was before the carve
assert abs(sum(dd[s_]["JAIPURI"]["ty"] for s_ in "AB") / sum(dd[s_]["FNCY"]["ty"] for s_ in "AB") - 0.25) < 1e-12
# the mix is kept: KURTI / FNCY unchanged by the re-balance
assert abs(dd["A"]["KURTI"]["ty"] / dd["A"]["FNCY"]["ty"] - 10 / 6) < 1e-12
print("new dept template checks passed")
