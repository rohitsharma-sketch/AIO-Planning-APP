"""BIS buyer inputs for the planner's review (user, 2026-10-15: "delegate the BIS function for the specific division
only ... only the inputs should be open for them to do in the input tile"; "Save for the planner to review, then send").

A buyer (Users & access > BIS divisions) Saves their Block Growth% tiles here - never straight to Sales Plan. The
planner sees the pending ones in BIS, applies one to the plan (or dismisses it) and then sends the plan with their own
Save. Kept in data/bis_submissions.json (local state, gitignored), newest last; a buyer's newer Save for the same
division replaces their pending one."""
import datetime
import json
import math
import os
import threading
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException

from auth.deps import require_login
from auth.rights import divisions_of, rights_for

router = APIRouter()
_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bis_submissions.json")
_lock = threading.Lock()
KEEP = 500          # ponytail: one JSON file, last 500 kept - a table if it ever needs history
MAX_TILES = 400


def _load(path=None) -> list:
    try:
        with open(path or _FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save(items: list, path=None) -> None:
    path = path or _FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(items[-KEEP:], fh, indent=1)
    os.replace(path + ".tmp", path)


def clean_tiles(tiles) -> dict:
    """{department: growth % or None} - the buyer's typed tiles, checked (trust boundary)."""
    if not isinstance(tiles, dict) or not tiles:
        raise ValueError("No input tiles sent.")
    if len(tiles) > MAX_TILES:
        raise ValueError(f"Too many departments ({len(tiles)}).")
    out = {}
    for k, v in tiles.items():
        k = str(k).strip()
        if not k or len(k) > 80:
            raise ValueError("A department name is empty or too long.")
        if v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k}: not a number.")
            if not math.isfinite(v) or not -100 <= v <= 1000:
                raise ValueError(f"{k}: {v} is outside -100% .. 1000%.")
        out[k] = v
    return out


def submit(items: list, user: dict, divs: list, body: dict) -> dict:
    division = str(body.get("division") or "").strip().upper()
    if not divs:
        raise PermissionError("Only buyers send inputs for review - a planner Saves the plan.")
    if division not in divs:
        raise PermissionError(f"You are the buyer for {', '.join(divs)} - not {division or 'that division'}.")
    tiles = clean_tiles(body.get("tiles"))
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for it in items:   # their earlier pending Save for this division is replaced
        if it["status"] == "pending" and it["division"] == division and it["by_id"] == user["id"]:
            it.update(status="replaced", reviewed_at=now)
    item = {"id": uuid.uuid4().hex[:12], "division": division, "tiles": tiles, "note": str(body.get("note") or "")[:500],
            "by": user["username"], "by_id": user["id"], "at": now, "status": "pending", "reviewed_by": None, "reviewed_at": None}
    items.append(item)
    return item


@router.post("/submissions")
def post_submission(body: dict = Body(...), user: dict = Depends(require_login)):
    with _lock:
        items = _load()
        try:
            item = submit(items, user, divisions_of(user["id"], bool(user.get("is_admin")), user.get("role")), body)
        except PermissionError as e:
            raise HTTPException(403, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        _save(items)
    return item


@router.get("/submissions")
def list_submissions(status: str | None = None, user: dict = Depends(require_login)):
    """A buyer sees their own; a planner sees everyone's (newest first)."""
    mine = divisions_of(user["id"], bool(user.get("is_admin")), user.get("role"))
    items = [i for i in _load() if (not mine or i["by_id"] == user["id"]) and (not status or i["status"] == status)]
    return {"items": items[::-1][:100], "buyer_divisions": mine}


@router.post("/submissions/{sid}/review")
def review_submission(sid: str, body: dict = Body(...), user: dict = Depends(require_login)):
    """body {"status": "applied" | "dismissed"} - the planner (who can send to Sales Plan) marks it reviewed."""
    st = body.get("status")
    if st not in ("applied", "dismissed"):
        raise HTTPException(422, "status must be applied or dismissed")
    if divisions_of(user["id"], bool(user.get("is_admin")), user.get("role")) or "buyer_push" not in rights_for(user["id"]):
        raise HTTPException(403, "Only a planner who can send the plan to Sales Plan reviews buyer inputs.")
    with _lock:
        items = _load()
        it = next((i for i in items if i["id"] == sid), None)
        if it is None:
            raise HTTPException(404, "No such submission")
        if it["status"] != "pending":
            raise HTTPException(409, f"Already {it['status']}")
        it.update(status=st, reviewed_by=user["username"], reviewed_at=datetime.datetime.now().isoformat(timespec="seconds"))
        _save(items)
    return it


if __name__ == "__main__":   # python -m auth.bis_submissions - the rules, no server / database
    its = []
    u = {"id": "u1", "username": "ch-mens"}
    a = submit(its, u, ["MENS"], {"division": "mens", "tiles": {"ML_JEANS": "12.5", "MU_SHIRT": None}})
    assert a["division"] == "MENS" and a["tiles"] == {"ML_JEANS": 12.5, "MU_SHIRT": None}
    b = submit(its, u, ["MENS"], {"division": "MENS", "tiles": {"ML_JEANS": 10}})
    assert its[0]["status"] == "replaced" and b["status"] == "pending"
    for bad, err in (((["MENS"], {"division": "KIDS", "tiles": {"X": 1}}), PermissionError),
                     (([], {"division": "MENS", "tiles": {"X": 1}}), PermissionError),
                     ((["MENS"], {"division": "MENS", "tiles": {"X": 5000}}), ValueError),
                     ((["MENS"], {"division": "MENS", "tiles": {}}), ValueError)):
        try:
            submit(its, u, *bad)
            raise AssertionError(bad)
        except err:
            pass
    print("bis_submissions checks passed")
