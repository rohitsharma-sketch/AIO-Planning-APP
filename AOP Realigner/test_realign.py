"""python test_realign.py — synthetic data, no network, no server."""
import io
import numpy as np
import pandas as pd
import importer
from engine import realign, verify

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
assert any("Jan/Feb" in w for w in warn)
# overflow: S2 Sep revised A=20 > month total 10 -> A stays EXACTLY 20, B Sep -> 0, and the excess 10 comes out
# of S2's other live month (Nov: room 20-5=15 -> target 10 -> B Nov 5); season total still = original 30
assert np.isclose(g("S2", "A", 299, "Sep'26"), 20) and np.isclose(g("S2", "B", 299, "Sep'26"), 0)
assert np.isclose(g("S2", "A", 299, "Nov'26"), 5) and np.isclose(g("S2", "B", 299, "Nov'26"), 5)
assert np.isclose(bucket("S2", "Sep'26") + bucket("S2", "Nov'26"), 30)
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
assert c.loc[("S2", "A", 299, "Sep'26"), "Status"] == "kept" and c.loc[("S1", "B", 299, "Sep'26"), "Status"] == "absorbed"
assert ("S1", "A", 299, "Jan'27 P1") not in c.index
# verify(): independent checks agree with the rules
checks, table = verify(orig, rev, out, M)
status = {ch["name"]: ch["status"] for ch in checks}
assert status["Revised values kept exactly"] == "ok" and status["Grand total unchanged"] == "fail"  # S3 shortfall -> total drops
assert status["Store × Division totals match — each month"] == "warn"   # S2's excess moved months
assert status["Jan / Feb untouched (value and qty)"] == "ok"
assert [t["dept"] for t in table] == ["A", "A F/S"] and np.isclose(table[0]["months"][0]["revised"], 37)

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
    return importer.prepare_revised(df, info, rep, o_df, o_months) if df is not None else (None, [], info, rep)

# a revised plan dropped into the original slot
_, _, rep = importer.read_table(xlsx([["Store Name", "Department", "Sep'26 New"], ["S1", "A", 1]]), "x.xlsx", importer.NEED_ORIGINAL, "original plan")
assert not rep.ok and "looks like a revised plan" in rep.first_error()

# a full plan dropped into the revised slot
_, _, _, rep = load_rev(xlsx(o_rows))
assert not rep.ok and "looks like a full plan" in rep.first_error()

# good revised (CSV, semicolons): new dept with parent, unchanged Jan, preview numbers
r, use, info, rep = load_rev("Store Name;Dept;Sep'26 New;Jan'27 P1 New;TTL Val TY New\ns1;A;1200;5;1205\nS1;A F/S;50;0;50\n".encode(), "rev.csv")
assert rep.ok, rep.items
assert not any("aren't months" in i["msg"] for i in rep.items)  # a totals column ending in "New" is not a month
assert use == ["Sep'26", "Jan'27 P1"] and list(r["DEPARTMENT"]) == ["A", "A F/S"]
assert any("New department A F/S" in i["msg"] for i in rep.items)
pv = info["preview"]["rows"]
assert pv[0]["original"] == [1000, 5] and pv[0]["revised"] == [1200, 5] and pv[1]["parent"] == "A"
assert not any("plan B" in i["msg"] for i in rep.items)  # B isn't revised at all - normal, no note

# unknown store, orphan department, changed Jan -> errors / warning
_, _, _, rep = load_rev(xlsx([["STORE NAME", "DEPARTMENT", "Sep'26 New", "Jan'27 P1 New"],
                              ["S9", "A", 1, 1], ["S1", "ZZ", 1, 1], ["S1", "A", 1, 99]]))
errs = [i["msg"] for i in rep.items if i["level"] == "error"]
assert any("aren't in the original" in e for e in errs) and any("no parent department" in e for e in errs)
assert any("Jan/Feb values" in i["msg"] for i in rep.items if i["level"] == "warning")

# ------------------------------------------------------------------ jobs: steps and progress are per job
import server
j1, j2 = server.Job("a", "x", "one"), server.Job("b", "y", "two")
with j1.step("long export"):
    j1.progress(5, 10)
    with j2.step("short upload"):
        pass
    assert j1.view()["steps"][0]["done"] == 5 and j1.view()["steps"][0]["total"] == 10
assert j2.view()["steps"][0]["status"] == "done" and j1.view()["steps"][0]["status"] == "done"

print("all realign checks passed")
