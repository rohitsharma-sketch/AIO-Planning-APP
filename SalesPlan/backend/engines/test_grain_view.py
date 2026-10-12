"""No-DB check of the Store / Cluster view (2026-10-12): clusters add up to their stores, stores carry their cluster,
nothing is lost. Run: python engines/test_grain_view.py   (from SalesPlan/backend)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engines.grain_view import NO_CLUSTER, build_cube, build_methods, rows  # noqa: E402

dep = lambda ly, ty, active=True: {"ly": ly, "ty": ty, "ty_p1": ty * 0.4, "ty_p2": ty * 0.6, "active": active}   # noqa: E731
plan = {"stores": {
    "A": {"cluster": "UP 1", "is_ssg": True, "divisions": {"MENS": {"months": {"Mar'27": {"departments": {
        "M_X": dep(10, 12), "M_Y": dep(5, 6), "M_Z": dep(3, 9, active=False)}}}}}},
    "B": {"cluster": "UP 1", "is_ssg": True, "divisions": {"MENS": {"months": {"Mar'27": {"departments": {
        "M_X": dep(4, 5)}}, "Apr'27": {"departments": {"M_X": dep(2, 2)}}}}}},
    "C": {"cluster": "", "is_ssg": False, "divisions": {"MENS": {"months": {"Apr'27": {"departments": {
        "M_Y": dep(1, 3)}}}}}},
}}
c = build_cube(plan, {"kind": "test"})
assert c["months"] == ["Mar'27", "Apr'27"] and c["stores"]["C"]["cluster"] == NO_CLUSTER
assert c["div"]["MENS"]["A"]["Mar'27"] == (15, 18)                 # inactive M_Z left out, as MRP Output does
per = {s: {m: {"ly": ly, "ty": ty} for m, (ly, ty) in ms.items()} for s, ms in c["div"]["MENS"].items()}
cl = rows(per, c["stores"], "cluster", c["months"])
up1 = next(r for r in cl["rows"] if r["key"] == "UP 1")
assert up1["n_stores"] == 2 and up1["total"] == {"ly": 21, "ty": 25} and [s["key"] for s in up1["stores"]] == ["A", "B"]
assert cl["rows"][-1]["key"] == NO_CLUSTER and cl["total"] == {"ly": 22, "ty": 28}
st = rows(per, c["stores"], "store", c["months"])
b = next(r for r in st["rows"] if r["key"] == "B")
assert b["cluster"] == "UP 1" and b["cluster_total"] == {"ly": 21, "ty": 25} and b["total"] == {"ly": 6, "ty": 7}
assert st["total"] == cl["total"] and st["n_stores"] == 3 and cl["n_clusters"] == 2
z = rows({**per, "W": {"Mar'27": {"ly": 0.0, "ty": 0.0}}}, {**c["stores"], "W": {"cluster": NO_CLUSTER}}, "store", c["months"])
assert z["n_stores"] == 3 and z["n_empty"] == 1 and z["total"] == st["total"]   # an empty warehouse is counted, not listed
# step 2: store-built / cluster-built AOP x BIS (2026-10-12)
aop = {"A": {"MENS": {"Mar'27": 30.0}}, "B": {"MENS": {"Mar'27": 10.0, "Apr'27": 4.0}}, "N": {"MENS": {"Mar'27": 6.0}}}
growth = {"MENS": {"M_X": {"Mar'27": 1.2}, "M_Y": {"Mar'27": 1.0}}}
M = build_methods(c, aop, growth, {"N": "UP 1"})
P = M["plan"]["MENS"]
sb = lambda s, m: sum(P[d].get(s, {}).get(m, {}).get("store_built", 0) for d in P)   # noqa: E731
cb = lambda s, m: sum(P[d].get(s, {}).get(m, {}).get("cluster_built", 0) for d in P)   # noqa: E731
assert abs(sb("A", "Mar'27") - 30) < 1e-9 and abs(sb("B", "Mar'27") - 10) < 1e-9     # each store lands on its AOP
# A's own mix: M_X 10 x 1.2 = 12, M_Y 5 x 1.0 = 5 -> 30 x 12/17 to M_X
assert abs(P["M_X"]["A"]["Mar'27"]["store_built"] - 30 * 12 / 17) < 1e-9
assert abs(sb("N", "Mar'27") - 6) < 1e-9                                               # no LY of its own -> its cluster's mix
# cluster-built: UP 1 Mar = 30 + 10 + 6 = 46 over the cluster mix (M_X 14 x 1.2, M_Y 5), then by store LY share
up = sum(cb(s, "Mar'27") for s in ("A", "B", "N"))
assert abs(up - 46) < 1e-9 and cb("N", "Mar'27") == 0                                  # N has no LY -> nothing
mx = 46 * 16.8 / 21.8
assert abs(P["M_X"]["A"]["Mar'27"]["cluster_built"] - mx * 10 / 14) < 1e-9             # A has 10 of M_X's 14 LY
assert abs(cb("B", "Apr'27") - 4) < 1e-9 and M["unalloc"] == {}
print("grain view checks passed")
