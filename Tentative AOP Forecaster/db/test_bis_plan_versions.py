"""No-DB check for db.bis_plan_versions.apply_save. Run: python db/test_bis_plan_versions.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db.bis_plan_versions import apply_save, MAX_VERSIONS


def save(rows, body):
    v, drop = apply_save(rows, body)
    if v is None:
        return rows
    return [v] + [r for r in rows if r["id"] != v["id"] and r["id"] not in drop]


# first save -> Original, whatever the browser called it
rows = save([], {"id": 1, "kind": "iteration", "iter": 7, "snapshot": "a"})
assert [(r["kind"], r.get("iter"), r["label"]) for r in rows] == [("original", None, "Original")], rows
# the Original is never overwritten
assert apply_save(rows, {"id": 1, "snapshot": "changed"}) == (None, [])
# new ids -> the next iteration, numbered by the server (a browser's stale guess is ignored)
rows = save(rows, {"id": 2, "kind": "original", "_pending": True})
rows = save(rows, {"id": 3, "kind": "iteration", "iter": 1})
assert [(r["id"], r["label"]) for r in rows] == [(3, "Iteration 2"), (2, "Iteration 1"), (1, "Original")], rows
assert "_pending" not in rows[1]
# a known iteration refreshes in place, keeping its number, and moves to the top
rows = save(rows, {"id": 2, "snapshot": "b", "kind": "original"})
assert [(r["id"], r["label"], r.get("snapshot")) for r in rows][:1] == [(2, "Iteration 1", "b")], rows
# the cap: 10 in all, the oldest iterations go, the Original stays; numbers never move
for i in range(4, 20):
    rows = save(rows, {"id": i})
assert len(rows) == MAX_VERSIONS and sum(r["kind"] == "original" for r in rows) == 1, rows
assert [r["label"] for r in rows if r["kind"] != "original"] == [f"Iteration {n}" for n in range(18, 9, -1)], rows
# string / number ids are the same version
assert apply_save([{"id": 5, "kind": "iteration", "iter": 3}], {"id": "5"})[0]["iter"] == 3
print("test_bis_plan_versions: OK")
# a re-save keeps the name it was given, even from a browser that hadn't seen the rename (2026-10-13)
assert apply_save([{"id": 5, "kind": "iteration", "iter": 3, "name": "Buyer pass 2"}], {"id": 5})[0]["name"] == "Buyer pass 2"
assert apply_save([{"id": 5, "kind": "iteration", "iter": 3, "name": "a"}], {"id": 5, "name": "b"})[0]["name"] == "b"
print("rename checks passed")
