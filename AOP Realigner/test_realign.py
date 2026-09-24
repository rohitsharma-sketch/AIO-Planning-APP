"""python test_realign.py — synthetic data, no network."""
import numpy as np
import pandas as pd
from server import realign

M = ["Sep'26", "Nov'26", "Jan'27 P1"]
def row(store, div, dept, mrp, disp, *v):
    d = {"Store Name": store, "DIVISION": div, "DEPARTMENT": dept, "MRP": mrp, "DISPLAY TYPE": disp, "Tag": "Original"}
    for m, x in zip(M, v):
        d[m + " Plan"] = d[m + " Plan Qty"] = x
    return d

orig = pd.DataFrame([
    #                         Sep  Nov  Jan
    row("S1", "LADIES", "A", 299, "TABLE",     6,   0,  6),
    row("S1", "LADIES", "A", 399, "NON_TABLE", 4,   0,  4),
    row("S1", "LADIES", "B", 299, "TABLE",    10,  20, 10),
    row("S1", "LADIES", "C", 299, "TABLE",    10,  20, 10),
    row("S1", "LADIES", "D", 299, "TABLE",    40,  40, 40),
    row("S2", "LADIES", "A", 299, "TABLE",     5,   5,  5),
    row("S2", "LADIES", "B", 299, "TABLE",     5,   5,  5),
    row("S3", "LADIES", "A", 299, "TABLE",     8,   8,  8),   # sole department in its store-division
])
rev = pd.DataFrame([
    {"Store Name": "S1", "DEPARTMENT": "A",     "Sep'26": 12, "Nov'26": 5, "Jan'27 P1": 99},  # Jan must be ignored
    {"Store Name": "S1", "DEPARTMENT": "A F/S", "Sep'26": 3,  "Nov'26": 0, "Jan'27 P1": 0},
    {"Store Name": "S2", "DEPARTMENT": "A",     "Sep'26": 20, "Nov'26": 5, "Jan'27 P1": 5},   # Sep: revised alone (20) > bucket total (10)
    {"Store Name": "S3", "DEPARTMENT": "A",     "Sep'26": 5,  "Nov'26": 8, "Jan'27 P1": 8},   # Sep: nothing else to absorb the shortfall
])
out, summ, warn, compare = realign(orig, rev, M)
g = lambda s, d, mrp, m: out[(out["Store Name"] == s) & (out.DEPARTMENT == d) & (out.MRP == mrp)][m + " Plan"].sum()
bucket = lambda s, m: out[out["Store Name"] == s][m + " Plan"].sum()
c = compare.set_index(["Store Name", "DEPARTMENT", "MRP", "Month"])

# rule 2: revised kept, split by that month's cont % (6:4)
assert np.isclose(g("S1", "A", 299, "Sep'26"), 7.2) and np.isclose(g("S1", "A", 399, "Sep'26"), 4.8)
assert np.isclose(g("S1", "A F/S", 299, "Sep'26"), 1.8) and np.isclose(g("S1", "A F/S", 399, "Sep'26"), 1.2)
# rule 2: Nov had no A plan -> average cont % of the months A did have (Sep 60/40, Jan 60/40)
assert np.isclose(g("S1", "A", 299, "Nov'26"), 3) and np.isclose(g("S1", "A", 399, "Nov'26"), 2)
# rule 1: every other department in the store x division absorbs pro-rata, whole division, no attribute split
assert np.isclose(g("S1", "B", 299, "Sep'26"), 9.166666666) and np.isclose(g("S1", "D", 299, "Sep'26"), 36.66666666)
assert np.isclose(bucket("S1", "Sep'26"), 70) and np.isclose(bucket("S1", "Nov'26"), 80)
# rule 3: Jan untouched even though the revised file says 99
assert np.isclose(g("S1", "A", 299, "Jan'27 P1"), 6) and np.isclose(g("S1", "B", 299, "Jan'27 P1"), 10)
assert np.isclose(g("S1", "A F/S", 299, "Jan'27 P1"), 0)
assert any("Jan/Feb" in w for w in warn)
# overshoot: S2 Sep revised A=20 alone > bucket total 10 -> capped to 10, B -> 0, bucket stays exactly on original
assert np.isclose(g("S2", "A", 299, "Sep'26"), 10) and np.isclose(g("S2", "B", 299, "Sep'26"), 0)
assert np.isclose(bucket("S2", "Sep'26"), 10)
assert np.isclose(g("S2", "A", 299, "Nov'26"), 5) and np.isclose(g("S2", "B", 299, "Nov'26"), 5)  # Nov: no overshoot
assert any("capped" in w and "S2/LADIES" in w for w in warn)
# S3: sole department revised down, nothing else to absorb -> bucket stays under original, flagged
assert np.isclose(g("S3", "A", 299, "Sep'26"), 5) and np.isclose(bucket("S3", "Sep'26"), 5)
assert any("no other department" in w and "S3/LADIES" in w for w in warn)
# qty follows value at the row's ASP
assert np.isclose(out[(out["Store Name"] == "S1") & (out.DEPARTMENT == "B")]["Sep'26 Plan Qty"].iloc[0], 9.166666666)
assert np.isclose(out[(out["Store Name"] == "S2") & (out.DEPARTMENT == "A")]["Sep'26 Plan Qty"].iloc[0], 10)

# comparison table: only changed cells appear, tagged with why
assert np.isclose(c.loc[("S1", "A", 299, "Sep'26"), "Realigned"], 7.2) and c.loc[("S1", "A", 299, "Sep'26"), "Status"] == "kept"
assert np.isclose(c.loc[("S1", "B", 299, "Sep'26"), "Realigned"], 9.166666666) and c.loc[("S1", "B", 299, "Sep'26"), "Status"] == "absorbed"
assert np.isclose(c.loc[("S2", "A", 299, "Sep'26"), "Realigned"], 10) and c.loc[("S2", "A", 299, "Sep'26"), "Status"] == "capped"
assert np.isclose(c.loc[("S3", "A", 299, "Sep'26"), "Realigned"], 5) and c.loc[("S3", "A", 299, "Sep'26"), "Status"] == "kept"
assert np.isclose(c.loc[("S3", "A", 299, "Sep'26"), "Delta"], -3)
assert ("S1", "A", 299, "Jan'27 P1") not in c.index   # frozen month, never changes -> excluded
assert ("S2", "B", 299, "Nov'26") not in c.index      # nothing to absorb that month -> f==1, excluded
assert len(compare) == len(compare.drop_duplicates())  # no duplicate (store,dept,mrp,month) rows

# progress: a short operation finishing (e.g. an upload in another tab) must not wipe a long export's progress
import threading
import server
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
