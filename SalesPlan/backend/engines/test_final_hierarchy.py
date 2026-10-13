"""No-server check for grain_view.hierarchy_rows (Final Results -> Hierarchy). Run: python engines/test_final_hierarchy.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines.grain_view import build_cube, hierarchy_rows  # noqa: E402


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
print("final hierarchy checks passed")
