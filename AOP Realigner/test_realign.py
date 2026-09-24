"""python test_realign.py — synthetic data, no network."""
import numpy as np
import pandas as pd
from server import realign

M = ["M1", "M2"]
def row(store, div, dept, mrp, disp, v1, v2, q1=None, q2=None):
    return {"Store Name": store, "DIVISION": div, "DEPARTMENT": dept, "MRP": mrp, "DISPLAY TYPE": disp,
            "M1 Plan": v1, "M2 Plan": v2, "M1 Plan Qty": v1 if q1 is None else q1, "M2 Plan Qty": v2 if q2 is None else q2,
            "Tag": "Original"}

orig = pd.DataFrame([
    row("S1", "LADIES", "A", 299, "TABLE", 6, 0), row("S1", "LADIES", "A", 399, "NON_TABLE", 4, 0),
    row("S1", "LADIES", "B", 299, "TABLE", 10, 20), row("S1", "LADIES", "C", 299, "TABLE", 10, 20),
    row("S1", "MENS", "X", 299, "TABLE", 50, 50),                       # other division: untouched
    row("S2", "LADIES", "A", 299, "TABLE", 5, 5), row("S2", "LADIES", "B", 299, "TABLE", 5, 5),
])
rev = pd.DataFrame([
    {"Store Name": "S1", "DEPARTMENT": "A", "M1": 12, "M2": 5},     # M2: A had 0 -> all-month mix 6:4
    {"Store Name": "S1", "DEPARTMENT": "A F/S", "M1": 3, "M2": 0},  # new dept -> cloned from A
    {"Store Name": "S2", "DEPARTMENT": "A", "M1": 20, "M2": 5},     # M1 overshoots S2's total of 10
])
out, summ, warn = realign(orig, rev, M)
g = lambda s, d, mrp, m: out[(out["Store Name"] == s) & (out.DEPARTMENT == d) & (out.MRP == mrp)][m + " Plan"].sum()

# revised values kept exactly, split by original MRP/display mix
assert np.isclose(g("S1", "A", 299, "M1"), 7.2) and np.isclose(g("S1", "A", 399, "M1"), 4.8)
assert np.isclose(g("S1", "A F/S", 299, "M1"), 1.8) and np.isclose(g("S1", "A F/S", 399, "M1"), 1.2)
assert np.isclose(g("S1", "A", 299, "M2"), 3) and np.isclose(g("S1", "A", 399, "M2"), 2)   # fallback mix
# others absorb pro-rata so S1 x LADIES x month total == original
assert np.isclose(g("S1", "B", 299, "M1"), 7.5) and np.isclose(g("S1", "C", 299, "M1"), 7.5)
s1l = out[(out["Store Name"] == "S1") & (out.DIVISION == "LADIES")]
assert np.isclose(s1l["M1 Plan"].sum(), 30) and np.isclose(s1l["M2 Plan"].sum(), 40)
assert np.isclose(g("S1", "X", 299, "M1"), 50)                                             # MENS untouched
# overshoot: revised kept, other dept -> 0, flagged; M2 lands exactly
assert np.isclose(g("S2", "A", 299, "M1"), 20) and np.isclose(g("S2", "B", 299, "M1"), 0)
assert np.isclose(g("S2", "B", 299, "M2"), 5)
assert any("S2/LADIES" in w for w in warn) and any("new store-departments" in w for w in warn)
# qty follows value at the row's ASP
q = out[(out["Store Name"] == "S1") & (out.DEPARTMENT == "B")]["M1 Plan Qty"].iloc[0]
assert np.isclose(q, 7.5)
assert (out[out.DEPARTMENT == "A F/S"]["Tag"] == "New Dept").all()
print("all realign checks passed")
