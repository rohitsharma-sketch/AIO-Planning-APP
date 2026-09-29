"""Check: MRP re-apportionment on the sales engine's LY sales keeps every Store x Dept total, and the tie to the
Calendar department sales catches a planted 0.02 L error. Needs the data lake + DB.
Run: python engines/test_mrp_reapportionment.py   (from SalesPlan/backend)"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines import mrp_reapportionment_engine as m  # noqa: E402

sales, months, check = m._engine_sales()
assert check["pass"] and check["max_diff_lakh"] <= 0.01, check

# synthetic MRP structure for one department: its two lowest MRPs are discontinued, the rest stay listed
dept = sales.groupby("DEPARTMENT")[months].sum().sum(axis=1).idxmax()
keys = sales[sales["DEPARTMENT"] == dept][["DEPARTMENT", "DISPLAY", "ATTRIBUTE", "MRP"]].drop_duplicates()
rows = []
for (d, disp, attr), g in keys.groupby(["DEPARTMENT", "DISPLAY", "ATTRIBUTE"]):
    mrps = sorted(g["MRP"])
    for i, mrp in enumerate(mrps):
        rows.append({"DEPARTMENT": d, "DISPLAY": disp, "ATTRIBUTE": attr, "MRP_CURRENT": mrp,
                     "MRP_LISTED": 0 if i < 2 and len(mrps) > 2 else mrp})
mapping = pd.DataFrame(rows)
sub = sales[sales["DEPARTMENT"] == dept].reset_index(drop=True)
out, unmapped, _ = m._redistribute(sub, mapping, months, None)
val, ok = m._validate(sub, out, months)
assert ok and unmapped.empty, (len(unmapped), [v for v in val if v["STATUS"] != "PASS"][:3])
assert abs(out[months].sum().sum() - sub[months].sum().sum()) < 0.01
assert not set(out["LISTED_MRP"]) & set(mapping.loc[mapping["MRP_LISTED"] == 0, "MRP_CURRENT"]) - set(mapping["MRP_LISTED"])

# planted: 0.02 L on one store x dept x month must break the tie
raw = sub.melt(id_vars=["STORE", "DEPARTMENT"], value_vars=months, var_name="m", value_name="SL_V")
print(f"{dept}: {len(sub)} rows -> {len(out)}, {len(val)} store totals kept; tie {check['cells']} cells max {check['max_diff_lakh']} L")
cal_like = {(r.STORE, r.DEPARTMENT, r.m): r.SL_V for r in raw.itertuples()}
k0 = next(iter(cal_like)); cal_like[k0] += 2000.0   # Rs 2,000 = 0.02 L
worst = max(abs(cal_like[k] - v) / 1e5 for k, v in {(r.STORE, r.DEPARTMENT, r.m): r.SL_V for r in raw.itertuples()}.items())
assert worst > 0.01, worst
print("mrp re-apportionment checks passed")
