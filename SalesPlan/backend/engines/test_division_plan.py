"""No-DB check: Division Plan = BIS's months only (Mar-Jun 2027), LY base and plan straight from the AOP publish.
Run: python engines/test_division_plan.py   (from SalesPlan/backend)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines.division_plan import _pick_publish, _plan_rows  # noqa: E402

totals = {"KIDS": {"202703": 4533.84, "202704": 3108.03, "202705": 3123.83, "202706": 2875.35}}
bases = {"KIDS": {"202703": 3807.91, "202704": 2825.49, "202705": 2839.87, "202706": 2614.0}}
k = {d["division_name"]: d for d in _plan_rows(totals, bases)}["KIDS"]
assert [m["month"] for m in k["months"]] == ["Mar'27", "Apr'27", "May'27", "Jun'27"], k   # nothing past Jun'27
assert k["plan_mamj"] == 13641.05 and k["ly_mamj"] == 12087.27, k
assert k["growth_pct"] == round((13641.05 / 12087.27 - 1) * 100, 2)                         # period total, not a monthly average
assert {d["division_name"]: d for d in _plan_rows(totals, bases)}["MENS"]["growth_pct"] is None   # no base -> no growth
# which publish (12 Oct 2026): BIS's stamped one while it is a listed version, else the live one (first listed)
hist = [{"id": 118, "version_label": "Version 2"}, {"id": 32, "version_label": "Version 1"}]
assert _pick_publish(32, hist) == (hist[1], None)          # stamped and still listed -> used
assert _pick_publish(116, hist) == (hist[0], 116)          # republished since BIS's Save -> live, flagged stale
assert _pick_publish(None, hist) == (hist[0], None)        # BIS never saved -> live
assert _pick_publish(116, []) == (None, None)              # nothing published
print("division plan checks passed")
