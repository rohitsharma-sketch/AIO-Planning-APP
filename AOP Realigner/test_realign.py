"""python test_realign.py — synthetic data, no network, no server."""
import io
import numpy as np
import pandas as pd
import importer
import engine
from engine import listing_targets, realign, split_targets, verify

# ------------------------------------------------------------------ engine

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
assert any("locked months" in w for w in warn)
# overflow (the cap, 2026-09-30): S2 Sep revised A=20 > the month's cap 10 -> A is cut to 10, B Sep -> 0, and the
# excess 10 moves into A's other live month (Nov: room 20-5=15 -> A Nov 15, B Nov 5). Every month stays on its cap
# (Sep 10, Nov 20) and A keeps its season total (20+5 = 10+15)
assert np.isclose(g("S2", "A", 299, "Sep'26"), 10) and np.isclose(g("S2", "B", 299, "Sep'26"), 0)
assert np.isclose(g("S2", "A", 299, "Nov'26"), 15) and np.isclose(g("S2", "B", 299, "Nov'26"), 5)
assert np.isclose(bucket("S2", "Sep'26"), 10) and np.isclose(bucket("S2", "Nov'26"), 20)
assert any("excess" in w and "S2/LADIES" in w for w in warn)
# S3: sole department revised down, nothing else to absorb -> bucket stays under original, flagged
assert np.isclose(g("S3", "A", 299, "Sep'26"), 5) and any("couldn't fully land" in w and "S3/LADIES" in w for w in warn)
# qty = value / original ASP of that Department x MRP x Display Type x Month
assert np.isclose(cell("S1", "B", 299, "Sep'26", " Plan Qty"), 9.166666666 / 2)
assert np.isclose(cell("S1", "C", 299, "Nov'26", " Plan Qty"), 18.75 / 2)
assert np.isclose(cell("S1", "A", 399, "Nov'26", " Plan Qty"), 2)                 # no qty that month -> all-month ASP
assert np.isclose(cell("S1", "A F/S", 299, "Sep'26", " Plan Qty"), 1.8)           # new dept uses parent's ASP
assert np.isclose(cell("S1", "D", 299, "Jan'27 P1", " Plan Qty"), 40)             # unchanged -> original qty
# comparison table
assert c.loc[("S2", "A", 299, "Sep'26"), "Status"] == "kept, moved to fit the cap" and c.loc[("S1", "B", 299, "Sep'26"), "Status"] == "absorbed"
assert c.loc[("S1", "A", 299, "Sep'26"), "Status"] == "kept"
assert ("S1", "A", 299, "Jan'27 P1") not in c.index
# verify(): independent checks agree with the rules
checks, table = verify(orig, rev, out, M)
status = {ch["name"]: ch["status"] for ch in checks}
assert status["Revised values kept exactly"] == "warn" and status["Grand total unchanged"] == "fail"  # S2 moved to fit; S3 short
assert status["Store × Division × Month = original (the cap)"] == "fail"   # S3: sole dept revised down, nothing to absorb
# the comparison levels: every store x division x month, flagged against the cap; S3 Sep is the only one off
sdm, sdd = engine.compare_levels(orig, out, M)
assert len(sdm) == 3 * len(M) and set(sdm.loc[sdm["Within cap"] != "Yes", "Store Name"]) == {"S3"}
assert sdm.loc[(sdm["Store Name"] == "S3") & (sdm["Month"] == "Sep'26"), "Within cap"].item() == "No - under the original"
assert ((sdd["Store Name"] == "S2") & (sdd["DEPARTMENT"] == "A") & (sdd["Month"] == "Nov'26")).any() and not (sdd["Locked month"] == "Yes").any()
assert status["Locked months untouched (value and qty)"] == "ok"
assert [t["dept"] for t in table] == ["A", "A F/S"] and np.isclose(table[0]["months"][0]["revised"], 37)

# user-chosen locks (2026-09-29): lock Nov instead of Jan -> Nov stays exactly as the original, Jan follows the file
import engine  # noqa: E402
engine.LOCKED = {"Nov'26"}
out2, _, _, _ = realign(orig, rev, M)
g2 = lambda s, d, mrp, m: out2[(out2["Store Name"] == s) & (out2.DEPARTMENT == d) & (out2.MRP == mrp)][m + " Plan"].sum()
for s_, d_, mrp_ in [("S1", "A", 299), ("S1", "B", 299), ("S1", "D", 299), ("S2", "B", 299), ("S3", "A", 299)]:
    o_ = orig[(orig["Store Name"] == s_) & (orig.DEPARTMENT == d_) & (orig.MRP == mrp_)]["Nov'26 Plan"].sum()
    assert np.isclose(g2(s_, d_, mrp_, "Nov'26"), o_), (s_, d_)            # locked month = original, value for value
# unlocked Jan now takes the revised 99 - up to the cap: S1 LADIES Jan is 70 in the original, so A is cut to 70
# (A 299 = 70 x 60%) and the other 29 moves into A's other live month (Sep, which has room)
assert np.isclose(g2("S1", "A", 299, "Jan'27 P1"), 70 * 0.6)
assert np.isclose(out2[out2["Store Name"] == "S1"]["Jan'27 P1 Plan"].sum(), 70)
assert {ch["name"]: ch["status"] for ch in verify(orig, rev, out2, M)[0]}["Locked months untouched (value and qty)"] == "ok"
engine.LOCKED = None   # back to the default (Jan / Feb) for the rest of the checks

# a pure re-phase (D's season kept, months moved): D keeps its new months exactly and the other departments absorb it,
# so every store x division x month stays on the original - the cap ("stay as they are" was removed, 2026-09-30)
rephase = pd.DataFrame([{"Store Name": "S1", "DEPARTMENT": "D", "Sep'26": 20, "Nov'26": 60, "Jan'27 P1": 40}])
out4, _, _, _ = realign(orig, rephase, M)
g4 = lambda s, d, m: out4[(out4["Store Name"] == s) & (out4.DEPARTMENT == d)][m + " Plan"].sum()
assert np.isclose(g4("S1", "D", "Sep'26"), 20) and np.isclose(g4("S1", "D", "Nov'26"), 60)
assert np.isclose(out4[out4["Store Name"] == "S1"]["Sep'26 Plan"].sum(), 70) and np.isclose(out4[out4["Store Name"] == "S1"]["Nov'26 Plan"].sum(), 80)
st4 = {ch["name"]: ch["status"] for ch in verify(orig, rephase, out4, M)[0]}
assert st4["Store × Division × Month = original (the cap)"] == "ok" and st4["Revised values kept exactly"] == "ok", st4

# ------------------------------------------------------------------ method 1: store listing changes
o1 = orig.assign(CLUSTER=orig["Store Name"].map({"S1": "X", "S2": "X", "S3": "Y"}), **{"REF Name": "R-" + orig["Store Name"]})
changes = [{"store": "S1", "dept": "D", "listing": "N", "start": 1, "values": None},   # delisted from Nov
           {"store": "S2", "dept": "C", "listing": "Y", "start": 0, "values": None}]   # newly listed, sized from S1
r1, src1, counts = listing_targets(o1, changes, M)
assert src1 == {("S2", "C"): ("S1", "C")} and counts == {"delisted": 1, "estimated": 1, "given": 0}
rv = r1.set_index(["Store Name", "DEPARTMENT"])
assert list(rv.loc[("S1", "D")]) == [40, 0, 40]                    # Sep before FROM, Jan frozen
assert np.allclose(rv.loc[("S2", "C")], [10 * 10 / 70, 20 * 20 / 80, 0])  # C's share of LADIES in S1 x S2's LADIES
out1, _, warn1, _ = realign(o1, r1, M, src1)
g1 = lambda s, d, m, col=" Plan": out1[(out1["Store Name"] == s) & (out1.DEPARTMENT == d)][m + col].sum()
assert g1("S1", "D", "Nov'26") == 0 and np.isclose(g1("S1", "D", "Sep'26"), 40)
assert np.isclose(out1[out1["Store Name"] == "S1"]["Nov'26 Plan"].sum(), 80)   # the rest of S1 LADIES absorbed D
assert np.isclose(g1("S2", "C", "Sep'26"), 10 / 7) and np.isclose(out1[out1["Store Name"] == "S2"]["Sep'26 Plan"].sum(), 10)
cl = out1[(out1["Store Name"] == "S2") & (out1.DEPARTMENT == "C")]
assert list(cl["REF Name"]) == ["R-S2"] and list(cl["CLUSTER"]) == ["X"]      # borrowed rows take the new store's own tags
assert np.isclose(g1("S2", "C", "Nov'26", " Plan Qty"), 5 / 2)                 # priced at C's own Nov ASP
try:
    listing_targets(o1, [{"store": "S1", "dept": "NOPE", "listing": "Y", "start": 0, "values": None}], M)
    raise AssertionError("a listing nobody plans must fail")
except ValueError as e:
    assert "Method 3" in str(e)

# ------------------------------------------------------------------ method 3: split an existing department
splits = [{"parent": "B", "child": "B H/S", "share": 0.4, "store": None},
          {"parent": "B", "child": "B H/S", "share": 1.0, "store": "S2"}]  # S2: B moves entirely
r3, src3 = split_targets(orig, splits, M)
assert src3 == {("S1", "B H/S"): ("S1", "B"), ("S2", "B H/S"): ("S2", "B")}
out3, _, _, cmp3 = realign(orig, r3, M, src3)
g3 = lambda s, d, m, col=" Plan": out3[(out3["Store Name"] == s) & (out3.DEPARTMENT == d)][m + col].sum()
assert np.isclose(g3("S1", "B", "Sep'26"), 6) and np.isclose(g3("S1", "B H/S", "Sep'26"), 4)
assert np.isclose(g3("S1", "B", "Jan'27 P1"), 10) and g3("S1", "B H/S", "Jan'27 P1") == 0    # Jan stays on the parent
assert g3("S2", "B", "Nov'26") == 0 and np.isclose(g3("S2", "B H/S", "Nov'26"), 15)
assert np.isclose(g3("S1", "B H/S", "Sep'26", " Plan Qty"), 2)                 # parent's ASP (B/299/TABLE Sep = 2)
assert set(cmp3["DEPARTMENT"]) == {"B", "B H/S"}                             # nothing else moved
try:
    split_targets(orig, [{"parent": "B", "child": "X", "share": 0.7, "store": None},
                         {"parent": "B", "child": "Y", "share": 0.5, "store": None}], M)
    raise AssertionError("shares over 100% must fail")
except ValueError as e:
    assert "more than 100%" in str(e)

# ------------------------------------------------------------------ method 4: listing / delisting shifted to a target
from engine import growth_targets, shift_targets
sec = {"B": "SEC1", "C": "SEC1"}
ch4 = [{"store": "S1", "dept": "D", "listing": "N", "start": 1, "values": None, "target": "B"},      # D -> B from Nov
       {"store": "S1", "dept": "A", "listing": "N", "start": 0, "values": None, "target": "SEC1"},   # A -> section B + C
       {"store": "S2", "dept": "C", "listing": "Y", "start": 0, "values": None, "target": "B"},      # C listed out of B
       {"store": "S3", "dept": "B", "listing": "Y", "start": 0, "values": [50, 0, 0], "target": "A"}]  # wants more than A has
r4, src4, notes4 = shift_targets(orig, ch4, M, sec)
v4 = r4.set_index(["Store Name", "DEPARTMENT"])
assert list(v4.loc[("S1", "D")]) == [40, 0, 40] and list(v4.loc[("S1", "A")]) == [0, 0, 10]
assert np.allclose(v4.loc[("S1", "B")], [15, 60, 10]) and np.allclose(v4.loc[("S1", "C")], [15, 20, 10])  # +5/+5 Sep, +40 Nov to B
assert np.allclose(v4.loc[("S2", "C")], [10 / 7, 5, 0]) and np.allclose(v4.loc[("S2", "B")], [5 - 10 / 7, 10, 5])
assert list(v4.loc[("S3", "B")]) == [8, 0, 0] and list(v4.loc[("S3", "A")]) == [0, 8, 8] and notes4["capped"] == ["S3 / B"]
out4, _, _, cmp4 = realign(orig, r4, M, src4)
for st, m in [("S1", "Sep'26"), ("S1", "Nov'26"), ("S2", "Sep'26"), ("S3", "Sep'26")]:   # store x division x month untouched
    assert np.isclose(out4[out4["Store Name"] == st][m + " Plan"].sum(), orig[orig["Store Name"] == st][m + " Plan"].sum())
assert not len(cmp4[cmp4["Status"] == "absorbed"])                                         # nothing outside the targets moved
try:
    shift_targets(orig, [{"store": "S1", "dept": "D", "listing": "N", "start": 0, "values": None, "target": "ZZ"}], M, sec)
    raise AssertionError("an unplanned target must fail")
except ValueError as e:
    assert "isn't planned" in str(e)

# ------------------------------------------------------------------ method 5: growth vs last year
ly = {("S1", "B"): {"Sep'25": 5, "Nov'25": 10}, ("S2", "B"): {"Sep'25": 5, "Nov'25": 5}}
r5, det5 = growth_targets(orig, [{"dept": "B", "store": None, "growth": 0.2}], M, ly)   # now +100% (50 vs 25) -> +20%
v5 = r5.set_index(["Store Name", "DEPARTMENT"])
assert np.isclose(det5[0]["current"], 1.0) and np.isclose(det5[0]["factor"], 0.6)
assert np.allclose(v5.loc[("S1", "B")], [6, 12, 10]) and np.allclose(v5.loc[("S2", "B")], [3, 9, 5])   # Jan frozen
r5b, _ = growth_targets(orig, [{"dept": "B", "store": None, "growth": 0.2}, {"dept": "B", "store": "S2", "growth": 0.5}], M, ly)
v5b = r5b.set_index(["Store Name", "DEPARTMENT"])
assert np.allclose(v5b.loc[("S2", "B")], [3.75, 11.25, 5]) and np.allclose(v5b.loc[("S1", "B")], [6, 12, 10])  # store row wins
# per-month growth: Nov judged on its own plan (20 + 15) vs its own last year (10 + 5); Sep has no value -> unchanged
r5m, det5m = growth_targets(orig, [{"dept": "B", "store": None, "growth": None, "months": {1: 0.0}}], M, ly)
v5m = r5m.set_index(["Store Name", "DEPARTMENT"])
assert np.allclose(v5m.loc[("S1", "B")], [10, 20 * 15 / 35, 10]) and np.allclose(v5m.loc[("S2", "B")], [5, 15 * 15 / 35, 5])
assert np.isclose(det5m[0]["months"][0]["current"], 35 / 15 - 1)
r5c, _ = growth_targets(orig, [{"dept": "B", "store": None, "growth": 0.2, "months": {1: 0.0}}], M, ly)   # season + one month
assert np.allclose(r5c.set_index(["Store Name", "DEPARTMENT"]).loc[("S1", "B")], [6, 20 * 15 / 35, 10])
out5, _, _, _ = realign(orig, r5, M)
assert np.isclose(out5[out5["Store Name"] == "S1"]["Sep'26 Plan"].sum(), 70)                 # capped at store x division
checks5, _ = verify(orig, r5, out5, M)
assert {c["name"]: c["status"] for c in checks5}["Display-type cont % kept as in the original"] == "ok"
checks4, _ = verify(orig, r4, out4, M)
assert {c["name"]: c["status"] for c in checks4}["Display-type cont % kept as in the original"] == "ok"

# ------------------------------------------------------------------ importer

def xlsx(rows, sheet="Sheet1", extra=None):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        for name, rr in (extra or []):
            pd.DataFrame(rr).to_excel(w, sheet_name=name, header=False, index=False)
        pd.DataFrame(rows).to_excel(w, sheet_name=sheet, header=False, index=False)
    return buf.getvalue()

def load_orig(rows, **kw):
    df, info, rep = importer.read_table(xlsx(rows, **kw), "orig.xlsx", importer.NEED_ORIGINAL, "original plan")
    return (importer.prepare_original(df, info, rep) if df is not None else (None, [], info, rep))

# messy original: totals row on top, loose header spellings, a text number, junk sheet first
hdr = ["store", "Department ", "DIV", "MRP", "Display", "Sep '26 Plan", "Sep’26 Plan Qty", "Notes", "Jan'27 P1 Plan", "Jan'27 P1 Plan Qty"]
o_rows = [[None, None, None, None, None, 36, 36, None, 30, 30], hdr,
          ["s1", "a", "Ladies", 299, "table", "1,000", 1000, "x", 5, 5],
          [None, None, None, None, None, None, None, None, None, None],
          ["S1", "B", "LADIES", 299, "TABLE", "n/a", 0, "", 25, 25]]
o_df, o_months, o_info, o_rep = load_orig(o_rows, extra=[("Notes", [["just a note"]])])
msgs = " | ".join(i["msg"] for i in o_rep.items)
assert o_rep.ok, msgs
assert o_months == ["Sep'26", "Jan'27 P1"] and o_info["sheet"] == "Sheet1" and o_info["header_row"] == 2
assert list(o_df["Store Name"]) == ["S1", "S1"] and list(o_df["DIVISION"]) == ["LADIES", "LADIES"]
assert o_df.loc[0, "Sep'26 Plan"] == 1000 and o_df.loc[1, "Sep'26 Plan"] == 0
assert "aren't numbers" in msgs and "empty row" in msgs and "Other sheets" in msgs

# duplicate key -> error with rows
_, _, _, rep = load_orig([hdr, ["S1", "A", "L", 299, "T", 1, 1, "", 1, 1], ["S1", "A", "L", 299, "T", 2, 2, "", 2, 2]])
assert not rep.ok and "duplicate" in rep.first_error() and "rows 2, 3" in str(rep.items)

# header not found -> says what's missing where
_, _, rep = importer.read_table(xlsx([["Store Name", "Department", "Sep'26 Plan"]]), "x.xlsx", importer.NEED_ORIGINAL, "original plan")
assert not rep.ok and "missing DIVISION, MRP, DISPLAY TYPE" in rep.first_error()

def load_rev(data, name="rev.xlsx"):
    df, info, rep = importer.read_table(data, name, importer.NEED_REVISED, "revised plan")
    return importer.prepare_revised(df, info, rep, o_df, o_months) if df is not None else (None, [], {}, info, rep)

# a revised plan dropped into the original slot
_, _, rep = importer.read_table(xlsx([["Store Name", "Department", "Sep'26 New"], ["S1", "A", 1]]), "x.xlsx", importer.NEED_ORIGINAL, "original plan")
assert not rep.ok and "looks like a revised plan" in rep.first_error()

# a full plan dropped into the revised slot
_, _, _, _, rep = load_rev(xlsx(o_rows))
assert not rep.ok and "looks like a full plan" in rep.first_error()

# good revised (CSV, semicolons): new dept with parent, unchanged Jan, preview numbers
r, use, src, info, rep = load_rev("Store Name;Dept;Sep'26 New;Jan'27 P1 New;TTL Val TY New\ns1;A;1200;5;1205\nS1;A F/S;50;0;50\n".encode(), "rev.csv")
assert rep.ok, rep.items
assert not any("aren't months" in i["msg"] for i in rep.items)  # a totals column ending in "New" is not a month
assert use == ["Sep'26", "Jan'27 P1"] and list(r["DEPARTMENT"]) == ["A", "A F/S"]
assert any("New department A F/S" in i["msg"] for i in rep.items)
pv = info["preview"]["rows"]
assert pv[0]["original"] == [1000, 5] and pv[0]["revised"] == [1200, 5] and pv[1]["tag"] == "new · copies A"
assert not any("plan B" in i["msg"] for i in rep.items)  # B isn't revised at all - normal, no note

# unknown store, orphan department, changed Jan -> errors / warning
_, _, _, _, rep = load_rev(xlsx([["STORE NAME", "DEPARTMENT", "Sep'26 New", "Jan'27 P1 New"],
                              ["S9", "A", 1, 1], ["S1", "ZZ", 1, 1], ["S1", "A", 1, 99]]))
errs = [i["msg"] for i in rep.items if i["level"] == "error"]
assert any("aren't in the original" in e for e in errs) and any("no department to copy" in e for e in errs)
assert any("values in locked months" in i["msg"] for i in rep.items if i["level"] == "warning")

# method 3, new department with an explicit COPY FROM
r, use, src, info, rep = load_rev(b"Store Name,Department,Copy From,Sep'26 New\nS1,ZZ NEW,B,5\n", "new.csv")
assert rep.ok, rep.items
assert src == {("S1", "ZZ NEW"): ("S1", "B")} and info["preview"]["rows"][0]["tag"] == "new · copies B"
_, _, _, _, rep = load_rev(b"Store Name,Department,Copy From,Sep'26 New\nS1,ZZ NEW,QQ,5\n", "new.csv")
assert not rep.ok and "COPY FROM QQ" in str(rep.items)

def read_as(data, need, prep, name="x.csv"):
    df, info, rep = importer.read_table(data, name, need, "file")
    return prep(df, info, rep, o_df, o_months) if df is not None else (None, [], {}, info, rep)

# method 1 via the importer: loose headers, FROM MONTH as text, bad values reported
r, use, src, info, rep = read_as(b"Store,Dept,MC_Listing,From\nS1,A,N,September 2026\nS1,B,Y,\n",
                                 importer.NEED_LISTING, importer.prepare_listing)
assert rep.ok, rep.items
assert r.set_index("DEPARTMENT").loc["A", "Sep'26"] == 0 and r.set_index("DEPARTMENT").loc["A", "Jan'27 P1"] == 5
assert any("already planned" in i["msg"] for i in rep.items)       # B is planned (Jan) - listing it changes nothing
# value columns: a row with a value is "given"; a row whose value cells are blank is sized from peers
df_, info_, rep_ = importer.read_table(b"Store,Dept,Listing,Sep'26 New\nS1,A,N,\nS3,A,Y,7\n", "x.csv", importer.NEED_LISTING, "file")
_, _, _, _, rep_ = importer.prepare_listing(df_, info_, rep_, o_df, o_months)
assert not rep_.ok and "S3" in str(rep_.items)                       # S3 isn't a store of the original
df_, info_, rep_ = importer.read_table(b"Store,Dept,Listing,Sep'26 New\nS1,A,N,\n", "x.csv", importer.NEED_LISTING, "file")
r_, _, _, _, rep_ = importer.prepare_listing(df_, info_, rep_, o_df, o_months)
assert rep_.ok and r_.loc[0, "Sep'26"] == 0, rep_.items
_, _, _, _, rep = read_as(b"Store,Dept,Listing,From\nS1,A,X,Mar'27\n", importer.NEED_LISTING, importer.prepare_listing)
errs = " | ".join(i["msg"] for i in rep.items if i["level"] == "error")
assert "isn't Y or N" in errs and "FROM MONTH" in errs
assert [importer.from_month(v, M) for v in ("", "Nov '26", "Jan'27", "Mar'27")] == [0, 1, 2, None]
import datetime
assert importer.from_month(datetime.datetime(2026, 11, 1), M) == 1

# method 3 split via the importer: shares as percentages
r, use, src, info, rep = read_as(b"Parent Department,New Department,Share %\nA,A2,40\n", importer.NEED_SPLIT, importer.prepare_split)
assert rep.ok, rep.items
rv = r.set_index("DEPARTMENT")
assert rv.loc["A", "Sep'26"] == 600 and rv.loc["A2", "Sep'26"] == 400 and src == {("S1", "A2"): ("S1", "A")}
assert any("percentages" in i["msg"] for i in rep.items)

# method 5 via the importer: a per-month growth column only (NEW GROWTH % blank)
lyi = {("S1", "A"): {"Sep'25": 500}, ("S1", "B"): {"Sep'25": 1}}
df_, info_, rep_ = importer.read_table(b"Department,New Growth %,Sep '26 Growth %\nA,,10\n", "g.csv", importer.NEED_GROWTH, "file")
r_, _, _, info_, rep_ = importer.prepare_growth(df_, info_, rep_, o_df, o_months, lyi)
assert rep_.ok, rep_.items
assert np.isclose(r_.set_index("DEPARTMENT").loc["A", "Sep'26"], 550) and r_.set_index("DEPARTMENT").loc["A", "Jan'27 P1"] == 5
assert any("Per-month growth" in i["msg"] for i in rep_.items)
tg = importer.template_growth(o_df, o_months, lyi)
assert "Sep'26 GROWTH %" in tg.columns and np.isclose(tg.set_index("DEPARTMENT").loc["A", "Sep'26 CURRENT %"], 100)

# templates
t, _ = importer.template_listing(o_df, o_months, {"months": ["Aug'26", "Sep'26(Till Date)"],
                                               "data": {"S1": {"A": "YN", "B": "YY", "C": "NY"}}})
assert list(zip(t["DEPARTMENT"], t["LISTING"])) == [("A", "N")]     # C isn't a plan department; B is planned and listed
t, sk = importer.template_listing(o_df, o_months, {"months": ["Sep'26(Till Date)"], "data": {"S1": {"A": "N", "B": "N"}}})
assert not len(t) and list(sk["DEPARTMENT"]) == ["A", "B"]          # whole store x division delisted -> not included
assert list(importer.template_split().columns) == ["PARENT DEPARTMENT", "NEW DEPARTMENT", "SHARE %", "Store Name"]

# ------------------------------------------------------------------ jobs: steps and progress are per job
import server
j1, j2 = server.Job("a", "x", "one"), server.Job("b", "y", "two")
with j1.step("long export"):
    j1.progress(5, 10)
    with j2.step("short upload"):
        pass
    assert j1.view()["steps"][0]["done"] == 5 and j1.view()["steps"][0]["total"] == 10
assert j2.view()["steps"][0]["status"] == "done" and j1.view()["steps"][0]["status"] == "done"

# ------------------------------------------------------------------ re-phase from last year (rule set R2-R7)
RM = ["Sep'26", "Oct'26", "Nov'26", "Jan'27 P1"]     # Jan locked -> the window is Sep-Nov
def rrow(store, ref, tag, clus, dept, *v):
    d = {"Store Name": store, "REF Name": ref, "SSG TAG": tag, "CLUSTER": clus, "DIVISION": "LADIES", "DEPARTMENT": dept,
         "MRP": 299, "DISPLAY TYPE": "TABLE"}
    for m, x in zip(RM, v):
        d[m + " Plan"], d[m + " Plan Qty"] = x, x
    return d
ro = pd.DataFrame([
    rrow("S1", "S1", "SSG",    "C1", "A", 8, 0, 0, 5),    # own shape (A F/S LY 1 / 3 / 0) -> 2 / 6 / 0
    rrow("S2", "S1", "OTHERS", "C1", "A", 0, 4, 0, 5),    # REF S1's shape, but S2 doesn't trade in Sep -> 0 / 4 / 0
    rrow("S2", "S1", "OTHERS", "C1", "B", 0, 3, 3, 5),
    rrow("S3", "S4", "OTHERS", "C1", "A", 1, 2, 1, 5),    # REF S4 isn't SSG -> the cluster's SSG stores (S1) -> 1 / 3 / 0
    rrow("S4", "S4", "OTHERS", "C1", "A", 1, 1, 1, 5),    # its own REF, not SSG -> cluster C1 (S1)
    rrow("S5", "",   "OTHERS", "C9", "A", 3, 1, 0, 5),    # nothing usable -> keeps its planned phasing
    rrow("S1", "S1", "SSG",    "C1", "C", 9, 9, 9, 5),    # another department: never in the file
])
rly = {("S1", "A F/S"): {"Sep'25": 1, "Oct'25": 3, "Nov'25": 0}, ("S4", "A F/S"): {"Sep'25": 9, "Oct'25": 0, "Nov'25": 1},
       ("S1", "C"): {"Sep'25": 1, "Oct'25": 1, "Nov'25": 1}}      # S1 sold in LADIES in every month last year: comparable
rv, rh, rnotes = importer.template_rephase(ro, RM, rly, "A", "A F/S")
got = rv.set_index("Store Name")[["Sep'26 New", "Oct'26 New", "Nov'26 New"]]
assert list(rv.columns) == ["Store Name", "DIVISION", "DEPARTMENT", "Sep'26 New", "Oct'26 New", "Nov'26 New"]  # Jan locked: not in the file
assert np.allclose(got.loc["S1"], [2, 6, 0]) and np.allclose(got.loc["S2"], [0, 4, 0])
assert np.allclose(got.loc["S3"], [1, 3, 0]) and np.allclose(got.loc["S4"], [0.75, 2.25, 0]) and np.allclose(got.loc["S5"], [3, 1, 0])
src = rh.set_index("STORE NAME")["SHAPE FROM"].to_dict()
assert src == {"S1": "own", "S2": "REF", "S3": "cluster comparable stores", "S4": "cluster comparable stores",
               "S5": "planned phasing (no last-year shape)"}, src
assert rh.set_index("STORE NAME").at["S2", "NOT TRADING"] == "Sep'26"
assert np.allclose(got.sum(axis=1), ro[ro.DEPARTMENT == "A"].groupby("Store Name")[["Sep'26 Plan", "Oct'26 Plan", "Nov'26 Plan"]].sum().sum(axis=1))
ro2 = ro.assign(**{"REF OLD": ro["Store Name"].map({"S3": "S1"})})   # a REF OLD column is used before the cluster
assert importer.template_rephase(ro2, RM, rly, "A", "A F/S")[1].set_index("STORE NAME").at["S3", "SHAPE FROM"] == "REF OLD"
assert any("planned phasing" in n and "S5" in n for n in rnotes) and any("don't trade" in n for n in rnotes), rnotes
for bad in (lambda: importer.template_rephase(ro, RM, rly, "Z"), lambda: importer.template_rephase(ro, RM, rly, "A", "NOPE")):
    try:
        bad()
        raise AssertionError("expected a ValueError")
    except ValueError:
        pass
# the file reads back as a Method 2 upload and runs with every store x division x month on the original (the cap)
rdf, rinfo, rrep = importer.read_table(engine.write_xlsx([("Revised plan", rv), ("How it was built", rh)]), "r.xlsx",
                                       importer.NEED_REVISED, "revised plan")
rr, ruse, rsrc, rinfo, rrep = importer.prepare_revised(rdf, rinfo, rrep, ro, RM)
assert rrep.ok, rrep.items
rout, _, rwarn, _ = realign(ro, rr, RM, rsrc)
rsdm = engine.compare_levels(ro, rout, RM)[0].set_index("Store Name")
assert (rsdm.loc[["S1", "S2"], "Within cap"] == "Yes").all()   # stores with another department to absorb: exactly on the cap
# S3 / S4 / S5 plan only A in LADIES: nothing can absorb a re-phase there, so they are flagged, never hidden
assert any("couldn't fully land" in w and "S3/LADIES" in w for w in rwarn), rwarn
assert np.allclose(rout[rout["Store Name"] == "S1"].query("DEPARTMENT == 'A'")[["Sep'26 Plan", "Oct'26 Plan", "Nov'26 Plan"]], [[2, 6, 0]])

# store overrides: REF OLD (before the cluster) and a fixed month mix (any scale, rescaled to 100%)
ovx = engine.write_xlsx([("o", pd.DataFrame([{"STORE NAME": "S3", "REF OLD": "S1"},
                                             {"STORE NAME": "S5", "DEPARTMENT": "A", "Sep'26 %": 25, "Oct'26 %": 25, "Nov'26 %": 50},
                                             {"STORE NAME": "ZZ", "REF OLD": "S1"}]))])
ovs, ovrep = importer.read_rephase_overrides(ovx, "o.xlsx", ro, RM)
assert ovrep.ok and ovs["S3"] == {"ref_old": "S1"} and np.isclose(ovs["S5"]["mix"]["A"]["Nov'26"], 0.5), ovrep.items
assert any(i["level"] == "warning" and "ZZ" in i["examples"] for i in ovrep.items)      # not in the plan: flagged
rv2, rh2, _ = importer.template_rephase(ro, RM, rly, "A", "A F/S", ovs)
src2 = rh2.set_index("STORE NAME")["SHAPE FROM"]
assert src2["S3"] == "REF OLD" and src2["S5"] == "fixed mix (override)"
assert np.allclose(rv2.set_index("Store Name").loc["S5", ["Sep'26 New", "Oct'26 New", "Nov'26 New"]], [1, 1, 2])
assert importer.read_rephase_overrides(engine.write_xlsx([("o", pd.DataFrame([{"STORE NAME": "S5", "DEPARTMENT": "A", "Sep'26 %": -1}]))]),
                                       "o.xlsx", ro, RM)[0] is None                    # negative mix: refused
nd, ndrep = importer.read_rephase_overrides(engine.write_xlsx([("o", pd.DataFrame([{"STORE NAME": "S5", "Sep'26 %": 1}]))]), "o.xlsx", ro, RM)
assert nd is None and "no DEPARTMENT" in ndrep.first_error()                         # a mix must name its department
ovc = {"S1": {"mix": {"C": {"Sep'26": 1.0}}}}                                        # a mix for department C ...
assert importer.template_rephase(ro, RM, rly, "A", "A F/S", ovc)[1].set_index("STORE NAME").at["S1", "SHAPE FROM"] == "own"  # ... never moves A
tov = importer.template_rephase_overrides(ro, RM, rly, "A", "A F/S")
assert list(tov["STORE NAME"][:3]) == ["S3", "S4", "S5"] and tov["NEEDS A LOOK"].sum() == 3   # cluster / planned first

# generic rules (2026-09-30): no SSG TAG column -> comparable = sold in the division in every month last year
rly3 = {**rly, ("S4", "A"): {"Sep'25": 1, "Oct'25": 1, "Nov'25": 1},     # S4: a full year in LADIES -> comparable
        ("S1", "C"): {"Sep'25": 1, "Oct'25": 1, "Nov'25": 0}}               # S1: no Nov last year -> not comparable
# with the tag column kept, S1 is tagged SSG but has a part-year history -> left out; S4 isn't tagged -> nobody lends
_, h5, n5 = importer.template_rephase(ro, RM, rly3, "A", "A F/S")
assert h5.set_index("STORE NAME").at["S1", "SHAPE FROM"].startswith("planned"), h5
assert any("part-year history: S1" in n for n in n5), n5
rv3, rh3, n3 = importer.template_rephase(ro.drop(columns=["SSG TAG"]), RM, rly3, "A", "A F/S")
h3 = rh3.set_index("STORE NAME")
assert h3.at["S4", "SHAPE FROM"] == "own" and h3.at["S1", "SHAPE FROM"] == "cluster comparable stores" and h3.at["S1", "SHAPE STORE"] == "CLUSTER:C1"
assert np.allclose(rv3.set_index("Store Name").loc["S1", ["Sep'26 New", "Oct'26 New", "Nov'26 New"]], [7.2, 0, 0.8])   # S4's 9 / 0 / 1
assert any("every one of these months" in n for n in n3), n3
# last year's month must be in the data and complete
for kw, msg in (({"partial": {"Oct'25"}}, "isn't complete"), ({}, "No last-year sales in the data for Nov'25")):
    lyx = rly if kw else {k: {m: v for m, v in mm.items() if m != "Nov'25"} for k, mm in rly.items()}
    try:
        importer.template_rephase(ro, RM, lyx, "A", "A F/S", **kw)
        raise AssertionError("expected a ValueError")
    except ValueError as e:
        assert msg in str(e), e
# an unlocked half-month has no last year: not re-phased, and the notes say so
engine.LOCKED = set()
_, _, n4 = importer.template_rephase(ro, RM, rly, "A", "A F/S")
assert any("Jan'27 P1" in n and "half-month" in n for n in n4), n4
engine.LOCKED = None

# ------------------------------------------------------------------ the cap per attribute (user, 2026-10-01)
# S1 LADIES: A, B are REGULAR; C, D are SUMMER. A Sep 10 -> 15: only B (same attribute) gives way, C / D untouched
oa = orig.assign(ATTRIBUTE=orig["DEPARTMENT"].map({"A": "REGULAR", "B": "REGULAR", "C": "SUMMER", "D": "SUMMER"}))
outa, _, _, cmpa = realign(oa, pd.DataFrame([{"Store Name": "S1", "DEPARTMENT": "A", "Sep'26": 15}]), ["Sep'26"])
ga = lambda d: outa[(outa["Store Name"] == "S1") & (outa.DEPARTMENT == d)]["Sep'26 Plan"].sum()
assert np.isclose(ga("A"), 15) and np.isclose(ga("B"), 5) and np.isclose(ga("C"), 10) and np.isclose(ga("D"), 40)
assert set(cmpa["DEPARTMENT"]) == {"A", "B"}                                    # nothing moved outside REGULAR
sta = {ch["name"]: ch["status"] for ch in verify(oa, pd.DataFrame([{"Store Name": "S1", "DEPARTMENT": "A", "Sep'26": 15}]), outa, ["Sep'26"])[0]}
assert sta["Store × Division × Attribute × Month = original (the cap)"] == "ok" and sta["Store × Division × Month = original"] == "ok", sta
capa = engine.compare_levels(oa, outa, ["Sep'26"])[0]
assert "ATTRIBUTE" in capa and (capa["Within cap"] == "Yes").all()
try:   # a shift must stay inside its attribute
    shift_targets(oa, [{"store": "S1", "dept": "D", "listing": "N", "start": 0, "values": None, "target": "B"}], M, sec)
    raise AssertionError("a cross-attribute shift must fail")
except ValueError as e:
    assert "another attribute" in str(e), e

# plan to plan (user, 2026-10-01): every row of either plan, original vs final, changed ones flagged
pp = engine.plan_to_plan(orig, out, M)
assert len(pp) == len(out) and (pp["Row"] == "new in final").sum() == 2            # A F/S: 2 new MRP rows in S1
r_ = pp[(pp["Store Name"] == "S1") & (pp.DEPARTMENT == "B")].iloc[0]
assert r_["Changed"] == "Yes" and np.isclose(r_["Sep'26 Original"], 10) and np.isclose(r_["Sep'26 Final"], 9.166666666)
assert np.isclose(r_["Sep'26 Difference"], r_["Sep'26 Final"] - 10) and r_["Months changed"] == 2   # Sep, Nov (Jan locked)
assert np.isclose(pp["Season Final"].sum(), out[[m + " Plan" for m in M]].to_numpy().sum())
assert (pp.loc[pp["Changed"] == "", [f"{m} Difference" for m in M]].abs() <= engine.SHOWN).all().all()

print("all realign checks passed")
