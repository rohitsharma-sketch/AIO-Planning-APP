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
# the plan's tags group the stores as they are (user, 2026-10-02): S3, tagged SSG with no LY, stays SSG with LY 0
main3 = ge.build_main(pd.concat([plan, pd.DataFrame([row("S3", "A", "SSG", 4.0)])]), M, ly)
r3 = main3.set_index(["STORE NAME", "DEPARTMENT"])
assert r3.loc[("S3", "A"), "SSG TAG"] == "SSG" and r3.loc[("S3", "A"), "TTL Val LY"] == 0
p3 = ge.pivot(main3, M, ["SSG"]).iloc[-1]
assert np.isclose(p3["TTL Val TY"], 15 + 20) and np.isclose(p3["TTL Val LY"], 17)
# "(blank)" from the page = the untagged stores
mb = main.copy(); mb.loc[mb["STORE NAME"] == "S2", "SSG TAG"] = ""
assert np.isclose(ge.pivot(mb, M, ["(blank)"])["TTL Val LY"].iloc[-1], ge.pivot(mb, M)["TTL Val LY"].iloc[-1] - ge.pivot(mb, M, ["SSG"])["TTL Val LY"].iloc[-1])
# the Sales Plan's own output (2026-10-15): Store x Department x merged MRP x Display, value only; MRPs in price order
SM = ["Mar'27 P1", "Mar'27 P2"]
cells = pd.DataFrame([("S1", "KIDS", "REG", "A", "999", "TABLE", "Mar'27 P1", 1.0, 2.0), ("S1", "KIDS", "REG", "A", "199", "TABLE", "Mar'27 P2", 1.0, 1.0),
                      ("S1", "KIDS", "REG", "A", "999", "NON_TABLE", "Mar'27 P1", 0.0, 3.0), ("S2", "KIDS", "REG", "B", "Not planned", "-", "Mar'27 P1", 4.0, 0.0)],
                     columns=["store", "division", "attribute", "department", "mrp", "display", "month", "ly", "ty"])
sp = {"months": SM, "cells": cells, "stores": {"S1": {"stype": "SSG", "tag": "x", "cluster": "C"}, "S2": {"stype": "NSO", "tag": "", "cluster": "C"}}}
ms = ge.build_main_sp(sp)
assert len(ms) == 4 and np.isclose(ms["TTL Val TY"].sum(), 6) and np.isclose(ms["TTL Val LY"].sum(), 6) and "Qty TY" not in " ".join(ms.columns)
ps = ge.pivot(ms, SM)
assert list(ps.Level) == ["Division", "Attribute", "Department", "MRP", "Display", "MRP", "Display", "Display",
                          "Department", "MRP", "Display", "Grand Total"], list(ps.Level)
assert list(ps[ps.Level == "MRP"]["MRP"]) == ["199", "999", "Not planned"]
for lv in ("Division", "Department", "MRP", "Display"):
    assert np.isclose(ps[ps.Level == lv]["TTL Val TY"].sum(), 6)
assert np.isclose(ge.pivot(ms, SM, ["SSG"]).iloc[-1]["TTL Val LY"], 2)
print("all growth-vs-LY checks passed")
