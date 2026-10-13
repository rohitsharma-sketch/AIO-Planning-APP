"""No-server check for grain_view.hierarchy_rows (Final Results -> Hierarchy). Run: python engines/test_final_hierarchy.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines.grain_view import build_cube, explain, hierarchy_rows  # noqa: E402


def d(ly, ty, active=True):
    return {"ly": ly, "ty": ty, "active": active}


plan = {"stores": {
    "S1": {"cluster": "C1", "is_ssg": True, "divisions": {
        "MENS": {"months": {"Apr'27": {"departments": {"JEANS": d(10, 12), "OFF": d(5, 5, False)}},
                            "Mar'27": {"departments": {"JEANS": d(8, 9), "KURTA": d(2, 3)}}}},
        "GM": {"months": {"Mar'27": {"departments": {"TOYS": d(100, 100)}}}}}},
    "S2": {"cluster": "C1", "is_ssg": False, "divisions": {
        "KIDS": {"months": {"Mar'27": {"departments": {"FROCK": d(4, 6)}}}}}},
    "S3": {"cluster": "C2", "is_ssg": True, "divisions": {
        "MENS": {"months": {"Mar'27": {"departments": {"JEANS": d(1, 1)}}}}}},
    "WH": {"cluster": None, "is_ssg": False, "divisions": {   # no cluster, no sales: never listed
        "MENS": {"months": {"Mar'27": {"departments": {"JEANS": d(0, 0)}}}}}},
}}
cube = build_cube(plan, {})
attr = {"MENS": {"JEANS": "REGULAR", "KURTA": "SUMMER"}, "KIDS": {"FROCK": "SUMMER"}}

top = hierarchy_rows(cube, attr, ["cluster", "store", "division"], [])
# GM and inactive departments are left out; totals add up
assert top["total"] == {"ly": 25.0, "ty": 31.0}, top
assert [(r["key"], r["ty"]) for r in top["rows"]] == [("C1", 30.0), ("C2", 1.0)], top
kids = hierarchy_rows(cube, attr, ["cluster", "store", "division"], ["C1"])
assert [(r["key"], r["ty"]) for r in kids["rows"]] == [("S1", 24.0), ("S2", 6.0)] and kids["level"] == "store", kids
# any order: division -> attribute -> month; months come back in calendar order
m = hierarchy_rows(cube, attr, ["division", "attribute", "month"], ["MENS", "REGULAR"])
assert [(r["key"], r["ty"]) for r in m["rows"]] == [("Mar'27", 10.0), ("Apr'27", 12.0)], m
st = hierarchy_rows(cube, attr, ["stype", "division"], [])
assert {r["key"]: r["ty"] for r in st["rows"]} == {"SSG": 25.0, "NSO": 6.0}, st
# a leaf node: totals only
leaf = hierarchy_rows(cube, attr, ["division", "department"], ["MENS", "KURTA"])
assert leaf["level"] is None and leaf["rows"] == [] and leaf["total"] == {"ly": 2.0, "ty": 3.0}, leaf
# "how is this number made" (2026-10-13): parts add back to the row; LFL = LY x BIS growth x the new-dept re-balance
g = lambda ly, ty, gi: {"ly": ly, "ty": ty, "g_p1": gi, "g_p2": gi}   # noqa: E731
plan2 = {"stores": {
    "A": {"cluster": "C1", "is_ssg": True, "divisions": {"LADIES": {"months": {"Mar'27": {"departments": {
        "DRESS": g(100, 99, 110), "ETHNIC": g(0, 44, 100), "TOP": g(50, 54, 110)}}}}}},
    "B": {"cluster": "C1", "is_ssg": False, "ref_store": "A", "tag": "NSO", "divisions": {"LADIES": {"months": {"Mar'27": {
        "departments": {"DRESS": g(20, 22, 110), "ETHNIC": g(0, 22 / 0.9 * 0.4, 110), "TOP": g(10, 11, 110)}}}}}},
}}
c2 = build_cube(plan2, {"note": "test"})
nd = {"LADIES": {"ETHNIC": {"ref_dept": "DRESS", "new_dept_pct": 40, "ref_reduction_pct": 10}}}
e = explain(c2, {}, nd, ["division", "department"], ["LADIES", "DRESS"])
assert abs(e["ty"] - 121) < 1e-9 and abs(e["parts"]["lfl"]["ty"] - 99) < 1e-9 and abs(e["parts"]["other"]["ty"] - 22) < 1e-9
assert abs(e["k"] - 99 / (100 * 1.1 * 0.9)) < 1e-12 and abs(e["cont"] - 121 / (230 + 22 / 0.9 * 0.4) * 100) < 1e-9, e
n = explain(c2, {}, nd, ["division", "department"], ["LADIES", "ETHNIC"])
assert abs(n["new_depts"][0]["expected"] - 121 / 0.9 * 0.4) < 1e-9 and abs(n["new_depts"][0]["ty"] - 121 / 0.9 * 0.4) < 1e-9, n
whole = explain(c2, {}, nd, ["division", "department"], [])
assert abs(whole["ty"] - (230 + 22 / 0.9 * 0.4)) < 1e-9 and "parent" not in whole and whole["lines"][-1]["h"] == "Check"
st = explain(c2, {}, nd, ["store"], ["B"])
assert any("follows A" in x["t"] for x in st["lines"]), st["lines"]
print("final hierarchy checks passed")
# filters (2026-10-13): only the chosen values count - rows, totals, Cont % and the explanation alike
f = hierarchy_rows(cube, attr, ["cluster", "store", "division"], [], {"division": {"MENS"}, "month": {"Mar'27"}})
assert f["total"] == {"ly": 11.0, "ty": 13.0} and [(r["key"], r["ty"]) for r in f["rows"]] == [("C1", 12.0), ("C2", 1.0)], f
fe = explain(c2, {}, nd, ["division", "department"], ["LADIES", "DRESS"], {"store": {"A"}})
assert abs(fe["ty"] - 99) < 1e-9 and abs(fe["parent"]["ty"] - (99 + 44 + 54)) < 1e-9 and fe["lines"][0]["h"] == "Filters on", fe
print("filter checks passed")
