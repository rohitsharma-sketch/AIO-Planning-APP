"""python test_nso_distributor.py - synthetic data, no network, no Sales Plan needed.
The NSO distributor's months follow the inputs (2026-10-15): a Mar-Jun plan, NSO Details / Division Cont % with 2027
date headers, and the Sales Plan link's fortnights added up to months."""
from io import BytesIO
from datetime import datetime

import pandas as pd

import nso_distributor as nd

M = ["MAR", "APR", "MAY", "JUN"]
D = [datetime(2027, m, 1) for m in (3, 4, 5, 6)]


def xlsx(df, blank_first=False):
    b = BytesIO()
    with pd.ExcelWriter(b, engine="openpyxl") as w:
        df.to_excel(w, index=False, startrow=1 if blank_first else 0)
    return b.getvalue()


# NSO Details: dated month headers (any year) -> MAR..JUN
nso = nd.load_nso_details(xlsx(pd.DataFrame([["NEW1", "REF1", "T1", 10.0, 20.0, 0.0, 5.0]],
                                            columns=["Store Code", "Ref Code", "Grade", *D])))
assert all(m in nso.columns for m in M) and nso.loc[0, "APR"] == 20.0, nso.columns.tolist()
# Division Cont %: blank first row, dated headers
div = nd.load_div_cont(xlsx(pd.DataFrame([["REF1", "KIDS", .25, .25, .25, .25], ["REF1", "LADIES", .75, .75, .75, .75]],
                                         columns=["Store Name", "CAT", *D]), blank_first=True))
assert div.loc[0, "MAR"] == .25 and "MAR" in div.columns
# the plan: two departments of the reference store, Mar-Jun
plan = pd.DataFrame([["REF1", "APPS", "KIDS", "K_A", 299, "TABLE", 1, 1, 1, 1, 10, 10, 10, 10],
                     ["REF1", "APPS", "LADIES", "L_A", 499, "TABLE", 3, 3, 3, 3, 20, 20, 20, 20]],
                    columns=["Store Name", "CAT", "Division", "Department", "MRP", "Display Type",
                             *[f"{m} - Val" for m in M], *[f"{m} - Qty" for m in M]])
assert nd.plan_months(plan) == M
rows, log = nd.generate_plan(nso, div, plan)
out = pd.DataFrame(rows)
assert set(f"{m} - Val" for m in M) <= set(out.columns) and "SEP - Val" not in out.columns
for m in M:   # each month = the store's target, split 25 / 75 by Division Cont %
    assert abs(out[f"{m} - Val"].sum() - nso.loc[0, m]) < 1e-6, (m, out[f"{m} - Val"].sum())
k = out.set_index("Department")
assert abs(k.loc["K_A", "APR - Val"] - 5.0) < 1e-9 and abs(k.loc["L_A", "APR - Val"] - 15.0) < 1e-9
assert abs(k.loc["L_A", "APR - Qty"] - 15.0 / (3 / 20)) < 1e-6   # pieces = value / the reference's ASP
assert nd.build_xlsx(rows, log, nso_df=nso).getbuffer().nbytes > 1000

# the Sales Plan link: fortnights -> months, value and pieces, CAT from the division
cells = pd.DataFrame([("S1", "KIDS", "REG", "K_A", "299", "TABLE", "Mar'27 P1", 0.0, 1.0, 10.0),
                      ("S1", "KIDS", "REG", "K_A", "299", "TABLE", "Mar'27 P2", 0.0, 2.0, 20.0),
                      ("S1", "GM", "REG", "G_A", "99", "-", "Apr'27 P1", 0.0, 4.0, 0.0)],
                     columns=["store", "division", "attribute", "department", "mrp", "display", "month", "ly", "ty", "qty"])
p = nd.plan_df_from_sp({"months": ["Mar'27 P1", "Mar'27 P2", "Apr'27 P1", "Apr'27 P2"], "cells": cells})
assert nd.plan_months(p) == ["MAR", "APR"], p.columns.tolist()
r = p.set_index("Department")
assert r.loc["K_A", "MAR - Val"] == 3.0 and r.loc["K_A", "MAR - Qty"] == 30.0 and r.loc["K_A", "CAT"] == "APPS"
assert r.loc["G_A", "CAT"] == "GM" and r.loc["G_A", "APR - Val"] == 4.0
print("all NSO distributor checks passed")
