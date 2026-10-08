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
# post-run checks: all green on a good run, a planted half share turns "shares" red
st = lambda out: {x["key"]: x["status"] for x in m._post_checks(sl, out, u, M, mp, True)}  # noqa: E731
assert set(st(o).values()) == {"ok"}, st(o)
assert st(o.assign(SHARE_PCT=o["SHARE_PCT"].where(o.index != 0, 50.0)))["shares"] == "fail"

# importing a new master version: a bad file changes nothing; a good one goes live, the old one moves to Archive
import io, tempfile  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.datastructures import UploadFile  # noqa: E402
m.MAPPING_DIR = tempfile.mkdtemp()
def _up(name, df):  # noqa: E302
    b = io.BytesIO(); df.to_excel(b, index=False); b.seek(0)
    return m.upload_mapping(UploadFile(file=b, filename=name))
try:
    _up("bad.xlsx", pd.DataFrame({"X": [1]})); raise AssertionError("bad master accepted")
except HTTPException as e:
    assert e.status_code == 400 and os.listdir(m.MAPPING_DIR) == []
assert _up("v1.xlsx", mp)["changes"] == {"added": 7, "removed": 0, "changed": 0}
mp2 = mp.assign(MRP_LISTED=[0, 250, 299, 0, 399, 0, 0])   # 299 now listed
r = _up("v2.xlsx", mp2)
assert r["changes"] == {"added": 0, "removed": 0, "changed": 1} and len(r["archived"]) == 1, r
assert sorted(os.listdir(m.MAPPING_DIR)) == ["Archive", "v2.xlsx"]

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
print(f"{dept}: {len(sub)} rows -> {len(out)}, {len(val)} store totals kept; tie {check['cells']} cells max {check['max_diff_lakh']} L")
# through the real tie (audit 2026-10-08: this compared the sales with themselves)
import datetime  # noqa: E402
ym = {datetime.date(int(x[:4]), int(x[5:]), 1).strftime("%b %Y"): x for x in m.LY_MONTHS}
raw = sales.melt(id_vars=["STORE", "DEPARTMENT"], value_vars=months, var_name="m", value_name="SL_V")
raw["ym"] = raw["m"].map(ym)
assert m._engine_check(raw)["pass"]
raw.loc[raw.index[0], "SL_V"] += 2000.0   # Rs 2,000 = 0.02 L
assert not m._engine_check(raw)["pass"]
print("mrp re-apportionment checks passed")
