"""Buyer's Input Sheet plan versions in the DB (user, 2026-10-12: "move the BIS versions to the database").

BIS kept its version list in each browser's localStorage, so another machine saw none of it. It now lives in
planning_inputs.bis_plan_versions - one shared list, like AOP's own planning_inputs.plan_versions. BIS still keeps
a copy in the browser for instant reads and for when this server can't be reached.

The server owns the numbering, so two machines can't both make an Original or the same iteration number:
  - a new version is the Original when there is none, else the next iteration (numbers never move);
  - a known version keeps its kind / number, and the Original is never overwritten;
  - every saved version is kept (user, 2026-10-15: "save all the iterations which are being saved" - the old cap of 10
    dropped the oldest iterations); MAX_VERSIONS = None = no cap.
`data` is the BIS entry as-is: {id, kind, iter, label, savedAt, divisionTotals, snapshot, name?} - name = the user's own
name for it (user, 2026-10-13: "a rename button to rename existing iterations"); label stays "Original" / "Iteration N"."""
import json

MAX_VERSIONS = None   # no cap: every saved iteration is kept (2026-10-15)
_ready = False


def apply_save(rows, body):
    """Pure. rows = stored versions newest-first; body = the version BIS saved.
    Returns (version to store, or None when the Original is left as it is; ids the cap drops)."""
    old = next((r for r in rows if str(r["id"]) == str(body["id"])), None)
    if old and old.get("kind") == "original":
        return None, []
    v = {k: x for k, x in body.items() if not k.startswith("_")}
    if old:
        v["kind"], v["iter"] = old.get("kind"), old.get("iter")
        if "name" not in v and old.get("name"):   # a re-save from a browser that hadn't seen the rename keeps it
            v["name"] = old["name"]
    elif not any(r.get("kind") == "original" for r in rows):
        v["kind"] = "original"
        v.pop("iter", None)
    else:
        v["kind"], v["iter"] = "iteration", max([r.get("iter") or 0 for r in rows] + [0]) + 1
    v["label"] = "Original" if v["kind"] == "original" else f"Iteration {v['iter']}"
    if MAX_VERSIONS is None:
        return v, []
    keep = [v] + [r for r in rows if str(r["id"]) != str(v["id"])]
    room = MAX_VERSIONS - (1 if any(r.get("kind") == "original" for r in keep) else 0)
    drop = [r["id"] for r in keep if r.get("kind") != "original"][room:]
    return v, drop


def _ensure(db):
    global _ready
    if _ready:
        return
    from sqlalchemy import text
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS planning_inputs.bis_plan_versions (
            id TEXT PRIMARY KEY,
            data JSONB NOT NULL,
            last_modified_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    db.commit()
    _ready = True


def list_versions(db):
    """Newest first (the last one saved on top, as BIS shows it)."""
    from sqlalchemy import text
    _ensure(db)
    return [r[0] for r in db.execute(text(
        "SELECT data FROM planning_inputs.bis_plan_versions ORDER BY last_modified_at DESC")).fetchall()]


def save_version(db, body):
    """Store one saved BIS version (caller commits). Returns {version, dropped}."""
    from sqlalchemy import text
    rows = list_versions(db)
    v, drop = apply_save(rows, body)
    if v is None:
        return {"version": next(r for r in rows if str(r["id"]) == str(body["id"])), "dropped": []}
    db.execute(text("""
        INSERT INTO planning_inputs.bis_plan_versions (id, data, last_modified_at)
        VALUES (:id, CAST(:data AS jsonb), NOW())
        ON CONFLICT (id) DO UPDATE SET data = CAST(:data AS jsonb), last_modified_at = NOW()
    """), {"id": str(v["id"]), "data": json.dumps(v)})
    for i in drop:
        db.execute(text("DELETE FROM planning_inputs.bis_plan_versions WHERE id = :id"), {"id": str(i)})
    return {"version": v, "dropped": drop}


def remove_version(db, vid):
    """Remove one iteration (user, 2026-10-12: "give me a iteration remover"). The Original can't be removed; the other
    iterations keep their numbers. Caller commits. True when a row went."""
    from sqlalchemy import text
    _ensure(db)
    return db.execute(text(
        "DELETE FROM planning_inputs.bis_plan_versions WHERE id = :id AND data->>'kind' IS DISTINCT FROM 'original' "
        "RETURNING id"), {"id": str(vid)}).first() is not None


MAX_NAME = 60


def rename_version(db, vid, name):
    """Give a version its own name (empty = back to "Original" / "Iteration N"). Its place in the list (last saved
    first) does not move. Caller commits. True when the version exists."""
    from sqlalchemy import text
    _ensure(db)
    name = " ".join(str(name or "").split())[:MAX_NAME]
    sql = ("UPDATE planning_inputs.bis_plan_versions SET data = " +
           ("jsonb_set(data, '{name}', to_jsonb(CAST(:n AS text)))" if name else "data - 'name'") +
           " WHERE id = :id RETURNING id")
    return db.execute(text(sql), {"id": str(vid), "n": name}).first() is not None


def import_versions(db, versions):
    """First move to the DB: one browser's list goes in as it is (its Original and iteration numbers kept), only
    while the table is empty - after that the DB list is the one every browser follows. Caller commits.
    Returns the stored list, or None when the table already has versions."""
    from sqlalchemy import text
    if list_versions(db):
        return None
    for v in (versions if MAX_VERSIONS is None else versions[:MAX_VERSIONS]):
        v = {k: x for k, x in v.items() if not k.startswith("_")}
        db.execute(text("""
            INSERT INTO planning_inputs.bis_plan_versions (id, data, last_modified_at)
            VALUES (:id, CAST(:data AS jsonb), COALESCE(CAST(:at AS timestamptz), NOW()))
            ON CONFLICT (id) DO NOTHING
        """), {"id": str(v["id"]), "data": json.dumps(v), "at": v.get("savedAt")})
    return list_versions(db)
