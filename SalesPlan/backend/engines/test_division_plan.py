"""No-DB check: AOP months are planned at exactly the AOP target, the rest keeps the annual total.
Run: python engines/test_division_plan.py   (from SalesPlan/backend)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines.division_plan import _monthly_split  # noqa: E402

aop = {"KIDS": {202703: 4533.84, 202704: 3108.03, 202705: 3123.83, 202706: 2875.35}}
out = _monthly_split("KIDS", 57000.0, 1.10, 4, 2027, aop)
got = {n: p for n, p, _ in out}
assert (got["Apr"], got["May"], got["Jun"]) == (3108.03, 3123.83, 2875.35), got   # Mar'27 is outside Apr'27-Mar'28
assert abs(sum(got.values()) - 57000.0) < 1e-6, sum(got.values())
assert got["Nov"] > got["Jul"] > 0                                                   # the rest still follows the curve

# AOP months above the annual target: the others get 0, nothing negative.
out = _monthly_split("KIDS", 5000.0, 1.10, 4, 2027, aop)
assert all(p >= 0 for _, p, _ in out) and round(sum(p for _, p, _ in out), 2) == 9107.21, out

# No AOP: plain curve, sum = annual.
assert abs(sum(p for _, p, _ in _monthly_split("KIDS", 1200.0, 1.0, 4, 2027, {})) - 1200.0) < 1e-6
print("division plan checks passed")
