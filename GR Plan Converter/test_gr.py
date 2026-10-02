"""python test_gr.py - synthetic data, no network."""
import os
import tempfile
from datetime import datetime

import numpy as np
import pandas as pd

import gr_engine as ge

M = ["Dec'26", "Jan'27 P1", "Jan'27 P2", "Feb'27 P1", "Feb'27 P2"]
assert ge.ly_label("Jan'27 P1") == "Jan'26 P1" and ge.ly_label("Sep'26") == "Sep'25"
assert ge.blocks(M) == [("D", ["Dec'26"]), ("JF", M[1:])]
assert [b for b, _ in ge.blocks(["Sep'26", "Oct'26", "Nov'26", "Dec'26", "Jan'27 P1"])] == ["SOND", "J"]

# LY from a day-wise file: P1 = 1st..15th of Jan, 1st..14th of Feb (2026: 28 days); rupees -> lakhs
days = [("S1", "A", datetime(2025, 12, 5), 1e5, 10), ("S1", "A", datetime(2026, 1, 15), 2e5, 20),
        ("S1", "A", datetime(2026, 1, 16), 3e5, 30), ("S1", "A", datetime(2026, 2, 14), 4e5, 40),
        ("S1", "A", datetime(2026, 2, 15), 5e5, 50), ("S2", "A", datetime(2026, 1, 2), 1e5, 1),
        ("S1", "A", datetime(2026, 3, 1), 9e5, 9), ("S9", "Z", datetime(2026, 1, 3), 1e5, 1),   # Mar: outside; S9: not a plan store
        ("S1", "C  F/S", datetime(2025, 12, 9), 2e5, 2),   # KIDS dept the plan dropped (double space, as in the lake): counts
        ("S1", "FW_SHOE", datetime(2025, 12, 9), 7e5, 7)]  # FOOTWEAR: not a plan division - left out
div_attr = {"A": ("KIDS", "REGULAR"), "Z": ("KIDS", "REGULAR"), "C  F/S": ("KIDS", "PREWINTER"), "FW_SHOE": ("FOOTWEAR", "REGULAR")}
tmp = tempfile.mkdtemp()
f = os.path.join(tmp, "day.parquet")
dd = pd.DataFrame(days, columns=["STORE_NAME", "DEPARTMENT", "BILLDATE", "SL_V", "SL_Q"])
dd["DIVISION"], dd["ATTRIBUTE1"] = zip(*dd["DEPARTMENT"].map(div_attr))
dd.to_parquet(f)
ly, info = ge.load_ly(M, tmp, f)
assert list(ly.loc[("S1", "A"), ["Dec'25", "Jan'26 P1", "Jan'26 P2", "Feb'26 P1", "Feb'26 P2"]]) == [1, 2, 3, 4, 5], ly
assert ly.loc[("S1", "A"), "Jan'26 P2 Q"] == 30 and not info["cached"] and ge.load_ly(M, tmp, f)[1]["cached"]

# MAIN / PIVOT: S1 plans A (KIDS, REGULAR, SSG); S2 has no plan for A but sold it last year - it still counts in LY
row = lambda s, d, ssg, v: {"Store Name": s, "DIVISION": "KIDS", "DEPARTMENT": d, "MRP": 1, "DISPLAY TYPE": "T", "ATTRIBUTE": "REGULAR",
                            "SSG TAG": ssg, "ST TAG": "x", **{m + " Plan": v for m in M}, **{m + " Plan Qty": v * 10 for m in M}}
plan = pd.DataFrame([row("S1", "A", "SSG", 2.0), row("S1", "B", "SSG", 1.0), row("S2", "B", "OTHERS", 1.0)])
main = ge.build_main(plan, M, ly)
r = main.set_index(["STORE NAME", "DEPARTMENT"])
assert np.isclose(r.loc[("S1", "A"), "TTL Val TY"], 10) and np.isclose(r.loc[("S1", "A"), "TTL Val LY"], 15)
assert np.isclose(r.loc[("S1", "A"), "TTL JF Val LY"], 14) and np.isclose(r.loc[("S1", "A"), "TTL Growth % Val"], 10 / 15 - 1)
assert np.isclose(r.loc[("S2", "A"), "TTL Val LY"], 1) and r.loc[("S2", "A"), "SSG TAG"] == "OTHERS"   # LY-only row kept
assert ("S9", "Z") not in r.index and np.isclose(main["TTL Val TY"].sum(), 10 + 5 + 5)
assert np.isclose(r.loc[("S1", "C F/S"), "TTL Val LY"], 2) and r.loc[("S1", "C F/S"), "TTL Val TY"] == 0   # one space, LY kept
assert r.loc[("S1", "C F/S"), "ATTRIBUTE"] == "PREWINTER" and ("S1", "FW_SHOE") not in r.index
p = ge.pivot(main, M, ["SSG"])
g = p[p.Level == "Grand Total"].iloc[0]
assert np.isclose(g["TTL Val TY"], 15) and np.isclose(g["TTL Val LY"], 17) and np.isclose(g["TTL Growth %"], 15 / 17 - 1)
assert list(p.Level) == ["Division", "Attribute", "Department", "Attribute", "Department", "Department", "Grand Total"]
assert np.isclose(ge.pivot(main, M)["TTL Val LY"].iloc[-1], 18)                                     # all stores: S2's LY too
print("all growth-vs-LY checks passed")
