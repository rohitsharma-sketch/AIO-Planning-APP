"""
Saved versions of the Final Results plan (user, 2026-10-13: "give me a save button and all tools related to version
selection, rename, save as, selection window which will help in making sure the changes are saved and can be easily
accessed. Also add a little know how as to what was changed from the 1st version to this").

A version = a frozen copy of the plan the Hierarchy shows (the plan cube: store x division x department x month LY / TY,
with the attribute and New-departments maps it was read with) plus the Hierarchy layout (Rows + Filters) at the time.
Save writes the live plan over the open version; Save as makes a new one; Rename renames; nothing is ever deleted.
Opening a version shows it exactly as saved (Hierarchy, filters, ⓘ); "What changed" compares it (or the live plan)
with Version 1.

Files: backend/plan_versions/index.json (the list) and <id>.json.gz (each copy).
"""
import datetime
import gzip
import json
import os
import threading

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plan_versions")
INDEX = os.path.join(DIR, "index.json")
_lock = threading.Lock()
_snap: dict = {}   # id -> (updated_at, snapshot) - the versions opened lately (ponytail: 3 kept, ~20 MB each in memory)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _index() -> list:
    try:
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _write_index(v: list):
    from plan_cache import save_json
    os.makedirs(DIR, exist_ok=True)
    save_json(INDEX, v, indent=1)


def _user(request: Request) -> str:
    """Who is signed in on 8010 (no sign-in on the standalone Sales Plan)."""
    return ((request.scope.get("session") or {}).get("user") or {}).get("username") or ""


def _find(v: list, vid: str) -> dict:
    for r in v:
        if r["id"] == vid:
            return r
    raise HTTPException(404, f"No version {vid}")


def live_snapshot() -> dict:
    """The live plan as Final Results shows it, with the maps it is read with."""
    from engines.grain_view import _cube
    from engines.final_results_engine import _load_dept_attr_map, _pipeline_status
    from engines.dept_sales_engine import _load_new_dept_map
    ps = _pipeline_status()
    return {"cube": _cube(), "attr_map": _load_dept_attr_map(), "nd_map": _load_new_dept_map() or {},
            "inputs": {k: ps.get(k) for k in ("active_source", "base_plan_at", "bis_saved_at")}}


def snapshot(vid: str) -> dict:
    """A saved version's copy (cached), its cube's source note saying which version it is."""
    r = _find(_index(), vid)
    hit = _snap.get(vid)
    if hit and hit[0] == r["updated_at"]:
        return hit[1]
    with gzip.open(os.path.join(DIR, f"{vid}.json.gz"), "rt", encoding="utf-8") as f:
        s = json.load(f)
    s["cube"]["source"] = {"kind": "version", "name": r["name"],
                           "note": f"version \"{r['name']}\" saved {r['updated_at'].replace('T', ' ')[:16]}"}
    while len(_snap) >= 3:
        _snap.pop(next(iter(_snap)))
    _snap[vid] = (r["updated_at"], s)
    return s


def totals(cube: dict) -> dict:
    """{ly, ty, divs: {div: [ly, ty]}, depts: {(div, dept): [ly, ty]}} of a cube (active + inactive LY)."""
    out = {"ly": 0.0, "ty": 0.0, "divs": {}, "depts": {}}
    for part, ty_on in (("dept", True), ("off", False)):
        for dv, dd in (cube.get(part) or {}).items():
            for dp, ss in dd.items():
                for mm in ss.values():
                    for v in mm.values():
                        ly, ty = (float(v[0]), float(v[1])) if ty_on else (float(v), 0.0)
                        for k in (out["divs"].setdefault(dv, [0.0, 0.0]), out["depts"].setdefault((dv, dp), [0.0, 0.0])):
                            k[0] += ly
                            k[1] += ty
                        out["ly"] += ly
                        out["ty"] += ty
    return out


def changes(base: dict, cur: dict, base_name: str, cur_name: str, base_view=None, cur_view=None) -> dict:
    """Pure. What changed from `base` to `cur` (snapshots), in plain words: totals, divisions, the departments that
    moved most, departments added / dropped, months, plan inputs, the layout."""
    a, b = totals(base["cube"]), totals(cur["cube"])
    L = lambda v: f"₹{v:,.1f} L"   # noqa: E731
    g = lambda t: (t["ty"] / t["ly"] - 1) * 100 if t["ly"] else 0.0   # noqa: E731
    lines = []
    say = lambda h, t: lines.append({"h": h, "t": t})   # noqa: E731
    d = b["ty"] - a["ty"]
    say("Plan", f"{cur_name}: {L(b['ty'])} vs {L(a['ty'])} in {base_name} - "
        + (f"{'+' if d >= 0 else ''}{d:,.2f} L ({d / a['ty'] * 100 if a['ty'] else 0:+.2f}%)" if abs(d) >= 0.005 else "no change")
        + f"; growth {g(b):+.2f}% vs {g(a):+.2f}%.")
    if abs(b["ly"] - a["ly"]) >= 0.005:
        say("LY", f"{L(b['ly'])} vs {L(a['ly'])} ({b['ly'] - a['ly']:+,.2f} L) - the sales base moved (a newer sales sync).")
    divs = []
    for dv in sorted(set(a["divs"]) | set(b["divs"])):
        x, y = a["divs"].get(dv, [0.0, 0.0]), b["divs"].get(dv, [0.0, 0.0])
        divs.append({"division": dv, "base_ty": x[1], "ty": y[1], "diff": y[1] - x[1]})
    moved = [f"{r['division']} {r['diff']:+,.1f} L" for r in divs if abs(r["diff"]) >= 0.05]
    say("Divisions", ", ".join(moved) + "." if moved else "every division's plan is the same.")
    da, db = a["depts"], b["depts"]
    act = lambda t, k: k in t and abs(t[k][1]) > 1e-9   # noqa: E731
    added = sorted(k for k in db if act(db, k) and not act(da, k))
    dropped = sorted(k for k in da if act(da, k) and not act(db, k))
    if added:
        say("Departments planned now", ", ".join(f"{dp} ({db[(dv, dp)][1]:,.1f} L)" for dv, dp in added[:8])
            + (f" and {len(added) - 8} more" if len(added) > 8 else "") + f" - not planned in {base_name}.")
    if dropped:
        say("Departments no longer planned", ", ".join(f"{dp} (was {da[(dv, dp)][1]:,.1f} L)" for dv, dp in dropped[:8])
            + (f" and {len(dropped) - 8} more" if len(dropped) > 8 else "") + ".")
    deps = sorted(({"division": k[0], "department": k[1], "base_ty": da.get(k, [0, 0])[1], "ty": db.get(k, [0, 0])[1],
                    "diff": db.get(k, [0, 0])[1] - da.get(k, [0, 0])[1]} for k in set(da) | set(db)),
                  key=lambda r: -abs(r["diff"]))
    top = [r for r in deps if abs(r["diff"]) >= 0.05][:8]
    if top:
        say("Biggest department moves", "; ".join(f"{r['department']} {r['diff']:+,.1f} L" for r in top) + ".")
    ma, mb = base["cube"].get("months") or [], cur["cube"].get("months") or []
    if ma != mb:
        say("Plan months", f"{', '.join(mb) or '-'} (were {', '.join(ma) or '-'}).")
    ia, ib = base.get("inputs") or {}, cur.get("inputs") or {}
    why = []
    if ia.get("bis_saved_at") != ib.get("bis_saved_at"):
        why.append(f"BIS saved again ({str(ib.get('bis_saved_at') or '-')[:16].replace('T', ' ')})")
    if ia.get("base_plan_at") != ib.get("base_plan_at"):
        why.append(f"the base plan was regenerated ({str(ib.get('base_plan_at') or '-')[:16].replace('T', ' ')})")
    if ia.get("active_source") != ib.get("active_source"):
        why.append(f"the plan now comes from {ib.get('active_source')} (was {ia.get('active_source')})")
    if (base.get("nd_map") or {}) != (cur.get("nd_map") or {}):
        why.append("the New departments template changed")
    if why:
        say("Why it moved", "; ".join(why) + ".")
    if base_view is not None and cur_view is not None and base_view != cur_view:
        f = lambda v: " › ".join((v or {}).get("levels") or []) + ((" · filters " + ", ".join(   # noqa: E731
            f"{k}: {', '.join(x)}" for k, x in ((v or {}).get("filters") or {}).items())) if (v or {}).get("filters") else "")
        say("Layout", f"{f(cur_view) or '-'} (was {f(base_view) or '-'}).")
    return {"lines": lines, "divisions": divs, "departments": top, "added": len(added), "dropped": len(dropped),
            "base": {"name": base_name, "ty": a["ty"], "ly": a["ly"]}, "cur": {"name": cur_name, "ty": b["ty"], "ly": b["ly"]}}


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
def list_versions():
    """Every saved version (oldest first) and the live plan's totals."""
    t = totals(live_snapshot()["cube"])
    return {"versions": _index(), "live": {"ly": t["ly"], "ty": t["ty"]}}


@router.post("/save")
def save(body: dict, request: Request):
    """{id} = Save: the live plan over that version; no id = Save as: a new version ({name}, default "Version n").
    {view} = the Hierarchy layout kept with it."""
    snap = live_snapshot()
    t = totals(snap["cube"])
    with _lock:
        v = _index()
        if body.get("id"):
            r = _find(v, body["id"])
            what = "saved over"
        else:
            n = max((x["n"] for x in v), default=0) + 1
            name = (body.get("name") or "").strip()[:80] or f"Version {n}"
            if any(x["name"].lower() == name.lower() for x in v):
                raise HTTPException(409, f"A version is already called \"{name}\" - pick another name")
            r = {"id": f"v{n}", "n": n, "name": name, "created_at": _now(), "history": []}
            v.append(r)
            what = "created"
        r.update(updated_at=_now(), saved_by=_user(request), ly=t["ly"], ty=t["ty"], months=snap["cube"]["months"],
                 inputs=snap["inputs"], view=body.get("view") or r.get("view"))
        r["history"] = (r.get("history") or []) + [{"at": r["updated_at"], "by": r["saved_by"], "what": what, "ty": t["ty"]}]
        os.makedirs(DIR, exist_ok=True)
        tmp = os.path.join(DIR, f".{r['id']}.tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump({**snap, "cube": {**snap["cube"], "source": None}}, f, separators=(",", ":"))
        os.replace(tmp, os.path.join(DIR, f"{r['id']}.json.gz"))
        _write_index(v)
        _snap.pop(r["id"], None)
    return r


@router.post("/rename")
def rename(body: dict, request: Request):
    name = (body.get("name") or "").strip()[:80]
    if not name:
        raise HTTPException(422, "Give the version a name")
    with _lock:
        v = _index()
        r = _find(v, body.get("id") or "")
        if any(x["name"].lower() == name.lower() and x["id"] != r["id"] for x in v):
            raise HTTPException(409, f"A version is already called \"{name}\"")
        r["history"] = (r.get("history") or []) + [{"at": _now(), "by": _user(request), "what": f"renamed from \"{r['name']}\""}]
        r["name"] = name
        _write_index(v)
    return r


@router.get("/changes")
def get_changes(id: str = "live", base: str = ""):
    """What changed from `base` (default Version 1) to version `id` (default the live plan)."""
    v = _index()
    if not v:
        raise HTTPException(404, "No saved version yet - Save the plan first")
    b = _find(v, base) if base else v[0]
    cur = live_snapshot() if id == "live" else snapshot(id)
    cname = "the live plan" if id == "live" else f"\"{_find(v, id)['name']}\""
    cview = None if id == "live" else _find(v, id).get("view")
    return {"id": id, "base_id": b["id"], **changes(snapshot(b["id"]), cur, f"\"{b['name']}\"", cname, b.get("view"), cview)}
