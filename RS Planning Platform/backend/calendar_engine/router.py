import csv
import datetime
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, func, select

from auth.deps import require_login, require_role
from db.base import SessionLocal
from db.models.calendar import (
    Calendar,
    CalendarCluster,
    CalendarClusterFestival,
    CalendarDayPair,
    StoreCalendarCluster,
    StoreClusterLogEntry,
    StoreClusterMapMeta,
)

router = APIRouter()


# ─── Store / Cluster template parsing (ported verbatim from Calendar Engine/local_server.py) ──
def _pick_columns(header):
    """Return (store_idx, cluster_idx) from a header row; falls back to first two columns."""
    norm = [str(h or "").strip().lower() for h in header]
    s_idx = next((i for i, h in enumerate(norm) if "store" in h), 0)
    c_idx = next((i for i, h in enumerate(norm) if "cluster" in h and i != s_idx), 1 if s_idx != 1 else 0)
    return s_idx, c_idx


def _rows_from_table(table):
    """table: list of row lists (first row = header). Returns list of {store, cluster}."""
    if not table:
        raise ValueError("Template is empty")
    header = table[0]
    s_idx, c_idx = _pick_columns(header)
    out, seen = [], set()
    for r in table[1:]:
        if r is None or s_idx >= len(r):
            continue
        store = str(r[s_idx] if r[s_idx] is not None else "").strip()
        cluster = str(r[c_idx] if c_idx < len(r) and r[c_idx] is not None else "").strip()
        if not store:
            continue
        key = store.upper()
        if key in seen:
            continue  # keep first occurrence of a duplicated store code
        seen.add(key)
        out.append({"store": store, "cluster": cluster})
    if not out:
        raise ValueError("No store rows found (expected columns: Store Name, Calendar Cluster)")
    return out


def parse_template(data, filename):
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        import openpyxl  # available on this machine; error surfaces to the client if not
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        table = [list(r) for r in ws.iter_rows(values_only=True)]
        return _rows_from_table(table)
    # CSV / TSV / TXT
    text = data.decode("utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except Exception:
        dialect = csv.excel
    table = [row for row in csv.reader(io.StringIO(text), dialect)]
    return _rows_from_table(table)


@router.get("/calendar-library")
def list_calendars(user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        calendars = session.execute(select(Calendar).order_by(Calendar.saved_at.desc())).scalars().all()
        summaries = []
        for c in calendars:
            rows = session.execute(
                select(CalendarDayPair.cluster_name, func.count()).where(CalendarDayPair.calendar_id == c.calendar_id).group_by(CalendarDayPair.cluster_name)
            ).all()
            summaries.append({
                "id": c.calendar_id, "name": c.name, "refYear": c.ref_year, "futYear": c.fut_year,
                "savedAt": c.saved_at.isoformat(), "engine": c.engine,
                "mappingSummary": [{"cluster": cluster, "totalDays": count} for cluster, count in rows],
            })
        return summaries
    finally:
        session.close()


@router.get("/calendar-library/{calendar_id}")
def get_calendar(calendar_id: int, user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        c = session.get(Calendar, calendar_id)
        if c is None:
            raise HTTPException(404, "Calendar not found")

        clusters = session.execute(select(CalendarCluster).where(CalendarCluster.calendar_id == calendar_id)).scalars().all()
        cluster_out = []
        for cl in clusters:
            festivals = session.execute(
                select(CalendarClusterFestival).where(CalendarClusterFestival.calendar_cluster_id == cl.id)
            ).scalars().all()
            cluster_out.append({
                "name": cl.cluster_name, "region": cl.region,
                "festivals": [{"id": f.source_festival_id, "name": f.name, "refDate": f.ref_date.isoformat(),
                               "futDate": f.fut_date.isoformat(), "pre": f.pre, "core": f.core, "post": f.post}
                              for f in festivals],
            })

        pairs = session.execute(
            select(CalendarDayPair).where(CalendarDayPair.calendar_id == calendar_id).order_by(CalendarDayPair.cluster_name, CalendarDayPair.seq)
        ).scalars().all()
        day_map = {}
        mapping_counts = {}
        for p in pairs:
            day_map.setdefault(p.cluster_name, []).append([p.ref_date.isoformat(), p.fut_date.isoformat()])
            mapping_counts[p.cluster_name] = mapping_counts.get(p.cluster_name, 0) + 1

        return {
            "id": c.calendar_id, "name": c.name, "refYear": c.ref_year, "futYear": c.fut_year,
            "savedAt": c.saved_at.isoformat(), "engine": c.engine,
            "clusters": cluster_out, "dayMap": day_map,
            "mappingSummary": [{"cluster": k, "totalDays": v} for k, v in mapping_counts.items()],
        }
    finally:
        session.close()


@router.post("/calendar-library")
def create_calendar(body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    session = SessionLocal()
    try:
        calendar_id = int(body["id"])
        if session.get(Calendar, calendar_id) is not None:
            raise HTTPException(409, f"Calendar id {calendar_id} already exists")

        c = Calendar(calendar_id=calendar_id, name=body["name"], ref_year=body["refYear"], fut_year=body["futYear"],
                     saved_at=datetime.datetime.fromisoformat(body["savedAt"]), engine=body.get("engine"))
        session.add(c)

        for cluster in body.get("clusters", []):
            cl = CalendarCluster(calendar_id=calendar_id, cluster_name=cluster["name"], region=cluster.get("region"))
            session.add(cl)
            session.flush()  # need cl.id for the festival rows below
            for fest in cluster.get("festivals", []):
                session.add(CalendarClusterFestival(
                    calendar_cluster_id=cl.id, source_festival_id=fest["id"], name=fest["name"],
                    ref_date=datetime.date.fromisoformat(fest["refDate"]), fut_date=datetime.date.fromisoformat(fest["futDate"]),
                    pre=fest["pre"], core=fest["core"], post=fest["post"],
                ))

        rows = [
            {"calendar_id": calendar_id, "cluster_name": cluster, "seq": seq,
             "ref_date": datetime.date.fromisoformat(pair[0]), "fut_date": datetime.date.fromisoformat(pair[1])}
            for cluster, pairs in body.get("dayMap", {}).items()
            for seq, pair in enumerate(pairs)
        ]
        if rows:
            session.execute(CalendarDayPair.__table__.insert(), rows)

        session.commit()
        return {"ok": True, "id": calendar_id}
    finally:
        session.close()


@router.delete("/calendar-library/{calendar_id}")
def delete_calendar(calendar_id: int, actor: dict = Depends(require_role("planner"))):
    session = SessionLocal()
    try:
        c = session.get(Calendar, calendar_id)
        if c is None:
            raise HTTPException(404, "Calendar not found")
        cluster_ids = [row[0] for row in session.execute(select(CalendarCluster.id).where(CalendarCluster.calendar_id == calendar_id)).all()]
        if cluster_ids:
            session.execute(delete(CalendarClusterFestival).where(CalendarClusterFestival.calendar_cluster_id.in_(cluster_ids)))
        session.execute(delete(CalendarCluster).where(CalendarCluster.calendar_id == calendar_id))
        session.execute(delete(CalendarDayPair).where(CalendarDayPair.calendar_id == calendar_id))
        session.delete(c)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.get("/store-cluster-map")
def get_store_cluster_map(user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        rows = session.execute(select(StoreCalendarCluster).order_by(StoreCalendarCluster.store_id)).scalars().all()
        meta = session.get(StoreClusterMapMeta, 1)
        locked_at = rows[0].locked_at if rows else None
        return {
            "locked": locked_at is not None,
            "lockedAt": locked_at.isoformat() if locked_at else None,
            "source": meta.source if meta else None,
            "aliases": meta.aliases if meta else {},
            "editedAt": meta.edited_at.isoformat() if meta and meta.edited_at else None,
            "stores": [{"store": r.store_id, "cluster": r.cluster_name} for r in rows],
        }
    finally:
        session.close()


@router.put("/store-cluster-map")
def put_store_cluster_map(body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    session = SessionLocal()
    try:
        before = {r.store_id: r.cluster_name for r in session.execute(select(StoreCalendarCluster)).scalars().all()}
        after_rows = [{"store": s["store"].strip(), "cluster": s["cluster"].strip()} for s in body.get("stores", []) if s.get("store") and s.get("cluster")]
        after = {r["store"]: r["cluster"] for r in after_rows}

        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        reassigned = sorted(s for s in (set(after) & set(before)) if before[s] != after[s])
        details = (
            [{"type": "added", "store": s, "to": after[s]} for s in added] +
            [{"type": "removed", "store": s, "from": before[s]} for s in removed] +
            [{"type": "reassigned", "store": s, "from": before[s], "to": after[s]} for s in reassigned]
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        session.execute(delete(StoreCalendarCluster))
        if after_rows:
            session.execute(StoreCalendarCluster.__table__.insert(), [
                {"store_id": r["store"], "cluster_name": r["cluster"], "locked_at": now} for r in after_rows
            ])

        meta = session.get(StoreClusterMapMeta, 1)
        if meta is None:
            meta = StoreClusterMapMeta(id=1)
            session.add(meta)
        meta.source = body.get("source")
        meta.aliases = body.get("aliases", {})
        meta.edited_at = now

        if details:
            session.add(StoreClusterLogEntry(
                at=now, source=body.get("source"),
                summary=f"Replaced store-cluster map ({len(added)} added, {len(removed)} removed, {len(reassigned)} reassigned)",
                added=len(added), removed=len(removed), reassigned=len(reassigned), details=details,
            ))

        session.commit()
        return {"ok": True, "added": len(added), "removed": len(removed), "reassigned": len(reassigned)}
    finally:
        session.close()


@router.get("/store-cluster-log")
def get_store_cluster_log(user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        rows = session.execute(select(StoreClusterLogEntry).order_by(StoreClusterLogEntry.at.desc())).scalars().all()
        return [{"at": r.at.isoformat(), "source": r.source, "summary": r.summary, "added": r.added,
                  "removed": r.removed, "reassigned": r.reassigned, "details": r.details} for r in rows]
    finally:
        session.close()


@router.post("/import/store-cluster")
async def import_store_cluster(file: UploadFile = File(...), actor: dict = Depends(require_role("planner"))):
    data = await file.read()
    try:
        rows = parse_template(data, file.filename)
        return {"ok": True, "filename": file.filename, "rows": rows}
    except Exception as e:
        raise HTTPException(400, str(e))
