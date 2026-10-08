"""Check: MRP re-apportionment on the sales engine's LY sales keeps every Store x Dept total, and the tie to the
Calendar department sales catches a planted 0.02 L error. Needs the data lake + DB.
Run: python engines/test_mrp_reapportionment.py   (from SalesPlan/backend)"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines import mrp_reapportionment_engine as m  # noqa: E402

# the master's rule on a hand-made group (no data lake): old MRPs 199 / 249 / 299 / 349 / 399 / 449, listed 249 -> 250
# and 399 -> 399; 199 has nothing listed below (100% up), 299 / 349 split 40/60 (60/40 Summer), 449 nothing above
M = ["Mar 2026"]
mp = pd.DataFrame({"DEPARTMENT": "D", "DISPLAY": "T", "MRP_CURRENT": [199, 249, 299, 349, 399, 449],
                   "MRP_LISTED": [0, 250, 0, 0, 399, 0]})
mp = pd.concat([mp, pd.DataFrame({"DEPARTMENT": ["D"], "DISPLAY": ["NONE"], "MRP_CURRENT": [99], "MRP_LISTED": [0]})])
sl = pd.DataFrame({"STORE": "S", "DIVISION": "X", "DEPARTMENT": "D", "DISPLAY": ["T"] * 7 + ["NONE", "T"],
                   "ATTRIBUTE": ["REGULAR"] * 6 + ["SUMMER", "REGULAR", "REGULAR"],
                   "MRP": [199, 249, 299, 349, 399, 449, 299, 99, 999], "Mar 2026": [10.0] * 9})
o, u, _ = m._redistribute(sl, mp, M)
got = {(a, c, lst): round(v, 6) for a, c, lst, v in zip(o["ATTRIBUTE"], o["MRP_CURRENT"], o["LISTED_MRP"], o["Mar 2026"])}
assert got == {("REGULAR", 199, 250): 10, ("REGULAR", 249, 250): 10, ("REGULAR", 299, 250): 4, ("REGULAR", 299, 399): 6,
               ("REGULAR", 349, 250): 4, ("REGULAR", 349, 399): 6, ("REGULAR", 399, 399): 10, ("REGULAR", 449, 399): 10,
               ("SUMMER", 299, 250): 6, ("SUMMER", 299, 399): 4}, got
assert sorted(u["REASON"]) == ["MRP combination not in mapping master", "No listed MRP in this Department x Display"]
assert m._validate(sl, o, M, u)[1]

sales, months, check = m._engine_sales()
assert check["pass"] and check["max_diff_lakh"] <= 0.01, check

# synthetic MRP structure for one department: its two lowest MRPs are discontinued, the rest stay listed
dept = sales.groupby("DEPARTMENT")[months].sum().sum(axis=1).idxmax()
keys = sales[sales["DEPARTMENT"] == dept][["DEPARTMENT", "DISPLAY", "MRP"]].drop_duplicates()
rows = []
for (d, disp), g in keys.groupby(["DEPARTMENT", "DISPLAY"]):
    mrps = sorted(g["MRP"])
    for i, mrp in enumerate(mrps):
        rows.append({"DEPARTMENT": d, "DISPLAY": disp, "MRP_CURRENT": mrp,
                     "MRP_LISTED": 0 if i < 2 and len(mrps) > 2 else mrp})
mapping = pd.DataFrame(rows)
sub = sales[sales["DEPARTMENT"] == dept].reset_index(drop=True)
out, unmapped, _ = m._redistribute(sub, mapping, months)
val, ok = m._validate(sub, out, months, unmapped)
assert ok and unmapped.empty, (len(unmapped), [v for v in val if v["STATUS"] != "PASS"][:3])
assert abs(out[months].sum().sum() - sub[months].sum().sum()) < 5e-9 * len(out)   # exact: nothing lost to rounding
assert max(v["DIFF"] for v in val) < 5e-9, max(v["DIFF"] for v in val)            # every store x dept to 8 decimals
assert not set(out["LISTED_MRP"]) & set(mapping.loc[mapping["MRP_LISTED"] == 0, "MRP_CURRENT"]) - set(mapping["MRP_LISTED"])

# planted: 0.02 L on one store x dept x month must break the tie
raw = sub.melt(id_vars=["STORE", "DEPARTMENT"], value_vars=months, var_name="m", value_name="SL_V")
print(f"{dept}: {len(sub)} rows -> {len(out)}, {len(val)} store totals kept; tie {check['cells']} cells max {check['max_diff_lakh']} L")
cal_like = {(r.STORE, r.DEPARTMENT, r.m): r.SL_V for r in raw.itertuples()}
k0 = next(iter(cal_like)); cal_like[k0] += 2000.0   # Rs 2,000 = 0.02 L
worst = max(abs(cal_like[k] - v) / 1e5 for k, v in {(r.STORE, r.DEPARTMENT, r.m): r.SL_V for r in raw.itertuples()}.items())
assert worst > 0.01, worst
print("mrp re-apportionment checks passed")
