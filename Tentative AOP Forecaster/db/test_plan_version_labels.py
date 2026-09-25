"""No-DB check for db.plan_version_labels.renumbered. Run: python db/test_plan_version_labels.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db.plan_version_labels import renumbered

v = [{"id": "b", "label": "Version 2 — 25 Sept 2026", "createdAt": "2026-09-25T07:17"},
     {"id": "c", "label": "Version 3 — 25 Sept 2026", "createdAt": "2026-09-25T08:35"}]
assert renumbered(v) == [("b", "Version 1 — 25 Sept 2026"), ("c", "Version 2 — 25 Sept 2026")], renumbered(v)
# A renamed version keeps its name but still counts; gap-free list -> no changes.
v2 = [{"id": "a", "label": "Diwali plan", "createdAt": "1"}, {"id": "c", "label": "Version 3 — x", "createdAt": "2"}]
assert renumbered(v2) == [("c", "Version 2 — x")], renumbered(v2)
assert renumbered([{"id": "a", "label": "Version 1 — x", "createdAt": "1"}]) == []
print("test_plan_version_labels: OK")
