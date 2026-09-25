"""Keep auto-numbered plan version labels ("Version N — <date>") gap-free
after a delete (user request 2026-09-25: deleting Version 1 of 3 must leave
Version 1 and 2, not 2 and 3). Versions are ranked by createdAt; a label the
user renamed is left as-is but still holds its place in the count. Pure -
app.py's DELETE /api/plan-versions/{id} applies the result."""
import re

_AUTO = re.compile(r"^Version \d+(?P<rest>\s+—\s+.*)?$")


def renumbered(versions):
    """[(id, new_label)] for every auto-labelled version whose number changes.
    `versions`: dicts with id, label, createdAt (ISO strings sort by time)."""
    out = []
    for n, v in enumerate(sorted(versions, key=lambda v: v.get("createdAt") or ""), start=1):
        m = _AUTO.match(v.get("label") or "")
        if m:
            new = f"Version {n}{m.group('rest') or ''}"
            if new != v["label"]:
                out.append((v["id"], new))
    return out
