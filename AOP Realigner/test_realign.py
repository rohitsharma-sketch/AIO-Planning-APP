"""python test_realign.py — synthetic data, no network."""
import threading
import numpy as np
import pandas as pd
import server
from server import realign

M = ["Sep'26", "Nov'26", "Jan'27 P1"]
def row(store, div, dept, mrp, disp, *v, qty=None):
    """qty: optional {month: qty} overrides; default qty = value (ASP 1 lakh/unit)."""
    d = {"Store Name": store, "DIVISION": div, "DEPARTMENT": dept, "MRP": mrp, "DISPLAY TYPE": disp, "Tag": "Original"}
    for m, x in zip(M, v):
        d[m + " Plan"] = x
        d[m + " Plan Qty"] = (qty or {}).get(m, x)
    return d

orig = pd.DataFrame([
    #                         Sep  Nov  Jan
    row("S1", "LADIES", "A", 299, "TABLE",     6,   0,  6),
    row("S1", "LADIES", "A", 399, "NON_TABLE", 4,   0,  4),
    row("S1", "LADIES", "B", 299, "TABLE",    10,  20, 10, qty={"Sep'26": 5}),    # B/299/TABLE Sep ASP = 2
    row("S1", "LADIES", "C", 299, "TABLE",    10,  20, 10, qty={"Nov'26": 10}),   # C/299/TABLE Nov ASP = 2, Sep = 1
    row("S1", "LADIES", "D", 299, "TABLE",    40,  40, 40),
    row("S2", "LADIES", "A", 299, "TABLE",     5,   5,  5),
    row("S2", "LADIES", "B", 299, "TABLE",     5,  15,  5, qty={"Sep'26": 2.5}),  # same combo, same ASP as S1's B
    row("S3", "LADIES", "A", 299, "TABLE",     8,   8,  8),   # sole department in its store-division
])
rev = pd.DataFrame([
    {"Store Name": "S1", "DEPARTMENT": "A",     "Sep'26": 12, "Nov'26": 5, "Jan'27 P1": 99},  # Jan must be ignored
    {"Store Name": "S1", "DEPARTMENT": "A F/S", "Sep'26": 3,  "Nov'26": 0, "Jan'27 P1": 0},
    {"Store Name": "S2", "DEPARTMENT": "A",     "Sep'26": 20, "Nov'26": 5, "Jan'27 P1": 5},   # Sep: revised alone (20) > month total (10)
    {"Store Name": "S3", "DEPARTMENT": "A",     "Sep'26": 5,  "Nov'26": 8, "Jan'27 P1": 8},   # Sep: nothing else to absorb the shortfall
])
out, summ, warn, compare = realign(orig, rev, M)
cell = lambda s, d, mrp, m, col=" Plan": out[(out["Store Name"] == s) & (out.DEPARTMENT == d) & (out.MRP == mrp)][m + col].sum()
g = cell
bucket = lambda s, m: out[out["Store Name"] == s][m + " Plan"].sum()
c = compare.set_index(["Store Name", "DEPARTMENT", "MRP", "Month"])

# revised kept, split by that month's cont % (6:4)
assert np.isclose(g("S1", "A", 299, "Sep'26"), 7.2) and np.isclose(g("S1", "A", 399, "Sep'26"), 4.8)
assert np.isclose(g("S1", "A F/S", 299, "Sep'26"), 1.8) and np.isclose(g("S1", "A F/S", 399, "Sep'26"), 1.2)
# Nov had no A plan -> average cont % of the months A did have (Sep 60/40, Jan 60/40)
assert np.isclose(g("S1", "A", 299, "Nov'26"), 3) and np.isclose(g("S1", "A", 399, "Nov'26"), 2)
# every other department in the store x division absorbs pro-rata
assert np.isclose(g("S1", "B", 299, "Sep'26"), 9.166666666) and np.isclose(g("S1", "D", 299, "Sep'26"), 36.66666666)
assert np.isclose(bucket("S1", "Sep'26"), 70) and np.isclose(bucket("S1", "Nov'26"), 80)
# Jan untouched even though the revised file says 99
assert np.isclose(g("S1", "A", 299, "Jan'27 P1"), 6) and np.isclose(g("S1", "B", 299, "Jan'27 P1"), 10)
assert np.isclose(g("S1", "A F/S", 299, "Jan'27 P1"), 0)
assert any("Jan/Feb" in w for w in warn)

# overflow: S2 Sep revised A=20 > month total 10 -> A stays EXACTLY 20, B Sep -> 0, and the excess 10 comes out
# of S2's other live month (Nov: room 20-5=15 -> target 10 -> B Nov 5); season total still = original 30
assert np.isclose(g("S2", "A", 299, "Sep'26"), 20) and np.isclose(g("S2", "B", 299, "Sep'26"), 0)
assert np.isclose(g("S2", "A", 299, "Nov'26"), 5) and np.isclose(g("S2", "B", 299, "Nov'26"), 5)
assert np.isclose(bucket("S2", "Sep'26") + bucket("S2", "Nov'26"), 30)
assert np.isclose(g("S2", "A", 299, "Jan'27 P1"), 5) and np.isclose(g("S2", "B", 299, "Jan'27 P1"), 5)  # frozen
assert any("excess" in w and "S2/LADIES" in w for w in warn)
# every revised value is kept exactly - department totals match the revised file
live = ["Sep'26", "Nov'26"]
got = out[out.DEPARTMENT.str.startswith("A")].groupby(["Store Name", "DEPARTMENT"])[[m + " Plan" for m in live]].sum()
want = rev.set_index(["Store Name", "DEPARTMENT"])[live]
assert np.allclose(got.loc[want.index].to_numpy(), want.to_numpy())
# S3: sole department revised down, nothing else to absorb -> bucket stays under original, flagged
assert np.isclose(g("S3", "A", 299, "Sep'26"), 5) and np.isclose(bucket("S3", "Sep'26"), 5)
assert any("couldn't fully land" in w and "S3/LADIES" in w for w in warn)

# qty = value / original ASP of that Department x MRP x Display Type x Month
assert np.isclose(cell("S1", "B", 299, "Sep'26", " Plan Qty"), 9.166666666 / 2)   # B Sep ASP 2
assert np.isclose(cell("S1", "C", 299, "Nov'26", " Plan Qty"), 18.75 / 2)         # C Nov ASP 2 (Sep's ASP 1 not used)
assert np.isclose(cell("S1", "C", 299, "Sep'26", " Plan Qty"), 9.166666666 / 1)   # C Sep ASP 1
assert np.isclose(cell("S1", "A", 399, "Nov'26", " Plan Qty"), 2)                 # no A/399 qty in Nov -> all-month ASP 1
assert np.isclose(cell("S1", "A F/S", 299, "Sep'26", " Plan Qty"), 1.8)           # new dept uses parent A's ASP
assert np.isclose(cell("S1", "D", 299, "Jan'27 P1", " Plan Qty"), 40)             # unchanged -> original qty
assert any("all-month ASP" in w for w in warn)

# comparison table: only changed cells appear, tagged with why
assert np.isclose(c.loc[("S1", "A", 299, "Sep'26"), "Realigned"], 7.2) and c.loc[("S1", "A", 299, "Sep'26"), "Status"] == "kept"
assert np.isclose(c.loc[("S1", "B", 299, "Sep'26"), "Realigned"], 9.166666666) and c.loc[("S1", "B", 299, "Sep'26"), "Status"] == "absorbed"
assert np.isclose(c.loc[("S2", "A", 299, "Sep'26"), "Realigned"], 20) and c.loc[("S2", "A", 299, "Sep'26"), "Status"] == "kept"
assert np.isclose(c.loc[("S2", "B", 299, "Nov'26"), "Delta"], -10) and c.loc[("S2", "B", 299, "Nov'26"), "Status"] == "absorbed"
assert np.isclose(c.loc[("S3", "A", 299, "Sep'26"), "Delta"], -3)
assert ("S1", "A", 299, "Jan'27 P1") not in c.index   # frozen month, never changes -> excluded
assert len(compare) == len(compare.drop_duplicates())

# progress: a short operation finishing (e.g. an upload in another tab) must not wipe a long export's progress
started, release = threading.Event(), threading.Event()
def long_op():
    with server.stage("long export"):
        server._progress(done=5, total=10)
        started.set()
        release.wait()
t = threading.Thread(target=long_op); t.start(); started.wait()
with server.stage("short upload"):
    pass
assert [(a["stage"], a["done"], a["total"]) for a in server.active.values()] == [("long export", 5, 10)]
release.set(); t.join()
assert not server.active
print("all realign checks passed")
