"""No-DB check for db.calendar_shift.month_shares: day-count split, sales-
weighted split (2026-09-25, option b) and its fallback. Run: python db/test_calendar_shift.py"""
import datetime as dt
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db.calendar_shift import month_shares, shift_month_totals

D = dt.date
# Mar'26: 3 days stay in Mar'27, 1 goes to Feb'27; Feb'26: 1 day comes into Mar'27.
pairs = [(D(2026, 3, 1), D(2027, 3, 1)), (D(2026, 3, 2), D(2027, 3, 2)), (D(2026, 3, 3), D(2027, 3, 3)),
         (D(2026, 3, 4), D(2027, 2, 27)), (D(2026, 2, 28), D(2027, 3, 4)), (D(2026, 2, 27), D(2027, 2, 28))]

cnt = month_shares(pairs)
assert cnt["2026-03"] == {"2027-03": 0.75, "2027-02": 0.25}, cnt

# Day 4 is a quiet day (10) vs 30 on the others: only 10/100 of March should leave.
w = {D(2026, 3, 1): 30, D(2026, 3, 2): 30, D(2026, 3, 3): 30, D(2026, 3, 4): 10, D(2026, 2, 28): 60, D(2026, 2, 27): 20}
ws = month_shares(pairs, w)
assert abs(ws["2026-03"]["2027-03"] - 0.9) < 1e-9 and abs(ws["2026-02"]["2027-03"] - 0.75) < 1e-9, ws
for r, fs in ws.items():
    assert abs(sum(fs.values()) - 1) < 1e-9, (r, fs)          # totals conserved

# Any day of a ref month missing from the weights -> that month keeps the day-count split.
part = dict(w); del part[D(2026, 3, 4)]
ps = month_shares(pairs, part)
assert ps["2026-03"] == cnt["2026-03"] and abs(ps["2026-02"]["2027-03"] - 0.75) < 1e-9, ps

out = shift_month_totals({"2026-03": 100.0, "2026-02": 80.0}, ws)
assert abs(out["2027-03"] - (90 + 60)) < 1e-9 and abs(out["2027-02"] - (10 + 20)) < 1e-9, out
print("test_calendar_shift: OK")

# Carry-forward (load_shift_maps): a 2026 day with no actuals inherits the 2025
# day mapped onto it, so a 2026->2027 split sees the festival value.
from db import calendar_shift as cs
class _S:  # minimal fake session for load_shift_maps
    def __init__(s): s.q = []
    def execute(s, sql, params=None):
        q = str(sql)
        class R(list):
            def all(self): return list(self)
            def first(self): return self[0] if self else None
            def scalar(self): return self[0] if self else None
        if "store_calendar_clusters" in q: return R([("S1", "C")])
        if "to_regclass" in q: return R(["calendar.cluster_day_sales"])
        if "cluster_day_sales" in q: return R([("C", D(2025, 10, 20), 90.0), ("C", D(2025, 10, 21), 10.0)])
        if "FROM calendar.calendars" in q:
            import types
            return R([types.SimpleNamespace(calendar_id=params["ry"], name=f"{params['ry']}->{params['fy']}")])
        if "calendar_day_pairs" in q:
            return R([("C", D(2025, 10, 20), D(2026, 11, 8)), ("C", D(2025, 10, 21), D(2026, 11, 9))] if params["id"] == "2025"
                     else [("C", D(2026, 11, 8), D(2027, 10, 29)), ("C", D(2026, 11, 9), D(2027, 11, 1))])
m = cs.load_shift_maps(_S())
nov = m["shares"][(2026, 2027)]["C"]["2026-11"]
assert abs(nov["2027-10"] - 0.9) < 1e-9 and abs(nov["2027-11"] - 0.1) < 1e-9, nov   # Diwali weight followed into Oct'27
print("test_calendar_shift carry-forward: OK")
