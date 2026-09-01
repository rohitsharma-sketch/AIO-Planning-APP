import csv
import datetime
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select

from auth.deps import require_login, require_role
from calendar_engine.cluster_names import resolve_cluster_name
from calendar_engine.scans import (
    get_salesdata_link, get_salesdata_link_daywise, run_reindex,
    start_reindex_job, poll_reindex_job, get_reindex_result_stream_path,
    start_link_scan_job, poll_link_scan_job,
    get_source_schema, reindex_month_cache_status,
)
from db.base import SessionLocal
from db.models.calendar import (
    AppStateMeta,
    Calendar,
    CalendarCluster,
    CalendarClusterFestival,
    CalendarDayPair,
    ClusterProfile,
    ClusterProfileFestival,
    FestivalChangelogEntry,
    SalesdataLinkSelection,
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


@router.put("/calendar-library/{calendar_id}/festivals")
def update_calendar_festivals(calendar_id: int, body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    """Autosave path for editing while a locked calendar is on the preview
    board: replaces just that calendar's festival list (clusters + their
    festival rows) with the given ones, same shape as create_calendar's
    `clusters`. Deliberately does NOT touch calendar_day_pairs - the actual
    computed day-by-day mapping stays exactly as last generated; only running
    Create Calendar + Lock & Save again refreshes that. CalendarDayPair has no
    FK to CalendarCluster (it's keyed by the cluster_name string), so
    dropping and re-creating the cluster/festival rows here can't orphan or
    break the existing day-map."""
    session = SessionLocal()
    try:
        c = session.get(Calendar, calendar_id)
        if c is None:
            raise HTTPException(404, "Calendar not found")

        cluster_ids = [row[0] for row in session.execute(select(CalendarCluster.id).where(CalendarCluster.calendar_id == calendar_id)).all()]
        if cluster_ids:
            session.execute(delete(CalendarClusterFestival).where(CalendarClusterFestival.calendar_cluster_id.in_(cluster_ids)))
        session.execute(delete(CalendarCluster).where(CalendarCluster.calendar_id == calendar_id))

        for cluster in body.get("clusters", []):
            cl = CalendarCluster(calendar_id=calendar_id, cluster_name=cluster["name"], region=cluster.get("region"))
            session.add(cl)
            session.flush()
            for fest in cluster.get("festivals", []):
                session.add(CalendarClusterFestival(
                    calendar_cluster_id=cl.id, source_festival_id=fest["id"], name=fest["name"],
                    ref_date=datetime.datetime.fromisoformat(fest["refDate"]).date(), fut_date=datetime.datetime.fromisoformat(fest["futDate"]).date(),
                    pre=fest["pre"], core=fest["core"], post=fest["post"],
                ))

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


@router.put("/calendar-library/{calendar_id}/name")
def rename_calendar(calendar_id: int, body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "Name cannot be empty")
    session = SessionLocal()
    try:
        c = session.get(Calendar, calendar_id)
        if c is None:
            raise HTTPException(404, "Calendar not found")
        c.name = name
        session.commit()
        return {"ok": True, "id": calendar_id, "name": name}
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
        # Store the RESOLVED cluster name (see resolve_cluster_name above) so this
        # table's cluster_name always matches a real cluster_profiles.name — the key
        # every downstream day-map / month-map lookup is done with.
        profile_names = session.execute(
            select(ClusterProfile.name).order_by(ClusterProfile.seq, ClusterProfile.name)
        ).scalars().all()
        aliases = body.get("aliases") or {}
        after_rows = [
            {"store": s["store"].strip(), "cluster": resolve_cluster_name(s["cluster"].strip(), profile_names, aliases)}
            for s in body.get("stores", []) if s.get("store") and s.get("cluster")
        ]
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
    except Exception as e:
        raise HTTPException(400, str(e))
    # Also hand back the RESOLVED cluster name for each row (same resolution
    # put_store_cluster_map applies on write), so the client can diff an upload
    # against the already-resolved current mapping without pure alias/spelling
    # variants ("NE" vs "N. EAST") showing up as false reassignments. The raw
    # `cluster` value from the file is left untouched for existing consumers.
    session = SessionLocal()
    try:
        profile_names = session.execute(
            select(ClusterProfile.name).order_by(ClusterProfile.seq, ClusterProfile.name)
        ).scalars().all()
        meta = session.get(StoreClusterMapMeta, 1)
        aliases = (meta.aliases if meta else None) or {}
    finally:
        session.close()
    out = [
        {**r, "resolvedCluster": resolve_cluster_name(str(r.get("cluster", "")).strip(), profile_names, aliases)}
        for r in rows
    ]
    return {"ok": True, "filename": file.filename, "rows": out}


@router.get("/cluster-profiles")
def get_cluster_profiles(user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        # `name` is a tiebreaker only: seq is unique in practice (assigned per-row on
        # save), but tied seq values would otherwise leave Postgres free to return an
        # arbitrary — and unstable — order.
        profiles = session.execute(select(ClusterProfile).order_by(ClusterProfile.seq, ClusterProfile.name)).scalars().all()
        out = []
        for p in profiles:
            festivals = session.execute(select(ClusterProfileFestival).where(ClusterProfileFestival.cluster_profile_id == p.id)).scalars().all()
            out.append({
                "name": p.name, "region": p.region, "nextId": p.next_id,
                "festivals": [{"id": f.source_festival_id, "name": f.name, "refDate": f.ref_date.isoformat(),
                               "futDate": f.fut_date.isoformat(), "pre": f.pre, "core": f.core, "post": f.post}
                              for f in festivals],
            })
        return {"profiles": out}
    finally:
        session.close()


@router.put("/cluster-profiles")
def put_cluster_profiles(body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    session = SessionLocal()
    try:
        old_ids = [row[0] for row in session.execute(select(ClusterProfile.id)).all()]
        if old_ids:
            session.execute(delete(ClusterProfileFestival).where(ClusterProfileFestival.cluster_profile_id.in_(old_ids)))
            session.execute(delete(ClusterProfile).where(ClusterProfile.id.in_(old_ids)))

        for i, profile in enumerate(body.get("profiles", [])):
            p = ClusterProfile(name=profile["name"], region=profile.get("region"), next_id=profile["nextId"], seq=i)
            session.add(p)
            session.flush()
            for fest in profile.get("festivals", []):
                session.add(ClusterProfileFestival(
                    cluster_profile_id=p.id, source_festival_id=fest["id"], name=fest["name"],
                    ref_date=datetime.date.fromisoformat(fest["refDate"]), fut_date=datetime.date.fromisoformat(fest["futDate"]),
                    pre=fest["pre"], core=fest["core"], post=fest["post"],
                ))
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.get("/app-state")
def get_app_state(user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        s = session.get(AppStateMeta, 1)
        if s is None:
            return {"activeClusterIdx": 0, "refYear": None, "futYear": None, "maxShift": None,
                    "moPri": None, "themeId": None, "savedAt": None, "migrations": []}
        return {
            "activeClusterIdx": s.active_cluster_idx, "refYear": s.ref_year, "futYear": s.fut_year,
            "maxShift": s.max_shift, "moPri": s.mo_pri, "themeId": s.theme_id,
            "savedAt": s.saved_at.isoformat() if s.saved_at else None, "migrations": s.migrations,
        }
    finally:
        session.close()


@router.put("/app-state")
def put_app_state(body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    session = SessionLocal()
    try:
        s = session.get(AppStateMeta, 1)
        if s is None:
            s = AppStateMeta(id=1)
            session.add(s)
        if "activeClusterIdx" in body:
            s.active_cluster_idx = body["activeClusterIdx"]
        if "refYear" in body:
            s.ref_year = body["refYear"]
        if "futYear" in body:
            s.fut_year = body["futYear"]
        if "maxShift" in body:
            s.max_shift = body["maxShift"]
        if "moPri" in body:
            s.mo_pri = body["moPri"]
        if "themeId" in body:
            s.theme_id = body["themeId"]
        if "migrations" in body:
            s.migrations = body["migrations"]
        s.saved_at = datetime.datetime.now(datetime.timezone.utc)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.get("/festival-changelog")
def get_festival_changelog(range_key: str | None = None, user: dict = Depends(require_login)):
    session = SessionLocal()
    try:
        stmt = select(FestivalChangelogEntry)
        if range_key:
            stmt = stmt.where(FestivalChangelogEntry.range_key == range_key)
        rows = session.execute(stmt.order_by(FestivalChangelogEntry.range_key, FestivalChangelogEntry.cluster_name, FestivalChangelogEntry.festival_name)).scalars().all()
        return [{"rangeKey": r.range_key, "clusterName": r.cluster_name, "festivalName": r.festival_name,
                  "refDate": r.ref_date.isoformat(), "futDate": r.fut_date.isoformat(), "savedAt": r.saved_at.isoformat()}
                for r in rows]
    finally:
        session.close()


@router.put("/festival-changelog")
def put_festival_changelog(body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    session = SessionLocal()
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        now = datetime.datetime.now(datetime.timezone.utc)
        stmt = pg_insert(FestivalChangelogEntry).values(
            range_key=body["rangeKey"], cluster_name=body["clusterName"], festival_name=body["festivalName"],
            ref_date=datetime.date.fromisoformat(body["refDate"]), fut_date=datetime.date.fromisoformat(body["futDate"]),
            saved_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["range_key", "cluster_name", "festival_name"],
            set_={"ref_date": stmt.excluded.ref_date, "fut_date": stmt.excluded.fut_date, "saved_at": stmt.excluded.saved_at},
        )
        session.execute(stmt)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.get("/salesdata-link-selection/{source_type}")
def get_salesdata_link_selection(source_type: str, user: dict = Depends(require_login)):
    if source_type not in ("mw", "dw"):
        raise HTTPException(404, "source_type must be 'mw' or 'dw'")
    session = SessionLocal()
    try:
        row = session.get(SalesdataLinkSelection, source_type)
        if row is None:
            return {"months": [], "path": None, "syncedAt": None, "extraDims": [], "metric": None}
        return {"months": row.months, "path": row.path, "syncedAt": row.synced_at.isoformat(),
                "extraDims": row.extra_dims, "metric": row.metric}
    finally:
        session.close()


@router.put("/salesdata-link-selection/{source_type}")
def put_salesdata_link_selection(source_type: str, body: dict = Body(...), actor: dict = Depends(require_role("planner"))):
    """Partial update - every field is optional so this doubles as both the
    "Sync Range" write (months/path/syncedAt) and the "customise output
    fields" write (extraDims/metric, saved the moment a planner changes them
    in Run Reindex - see CalendarisedSalesTab/index.jsx) without either one
    clobbering fields the other doesn't send."""
    if source_type not in ("mw", "dw"):
        raise HTTPException(404, "source_type must be 'mw' or 'dw'")
    session = SessionLocal()
    try:
        row = session.get(SalesdataLinkSelection, source_type)
        if row is None:
            row = SalesdataLinkSelection(
                source_type=source_type, months=[], path="",
                synced_at=datetime.datetime.now(datetime.timezone.utc), extra_dims=[], metric=None,
            )
            session.add(row)
        if "months" in body:
            row.months = body["months"]
        if "path" in body:
            row.path = body["path"]
        if "syncedAt" in body:
            row.synced_at = datetime.datetime.fromisoformat(body["syncedAt"])
        if "extraDims" in body:
            row.extra_dims = body["extraDims"]
        if "metric" in body:
            row.metric = body["metric"]
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.get("/salesdata/link")
def salesdata_link(refresh: bool = False, user: dict = Depends(require_login)):
    return get_salesdata_link(force_refresh=refresh)


@router.get("/salesdata/link-daywise")
def salesdata_link_daywise(refresh: bool = False, user: dict = Depends(require_login)):
    return get_salesdata_link_daywise(force_refresh=refresh)


@router.post("/salesdata/link/start")
def salesdata_link_start(source_type: str, refresh: bool = False, user: dict = Depends(require_login)):
    """Background variant of /salesdata/link[-daywise] - returns a job id
    immediately instead of blocking for the whole scan (day-wise reads real
    columns across 86M+ rows). Poll /salesdata/link/poll/{job_id}."""
    if source_type not in ("mw", "dw"):
        raise HTTPException(422, "source_type must be 'mw' or 'dw'")
    return {"ok": True, "jobId": start_link_scan_job(source_type, force_refresh=refresh)}


@router.get("/salesdata/link/poll/{job_id}")
def salesdata_link_poll(job_id: str, user: dict = Depends(require_login)):
    return poll_link_scan_job(job_id)


@router.get("/salesdata/schema/{source_type}")
def salesdata_schema(source_type: str, user: dict = Depends(require_login)):
    """Real columns available for this source, split into optional group-by
    dimensions and summable metrics - lets Run Reindex offer a 'pick your own
    output fields' picker that's always true to what the source actually has,
    instead of the hardcoded store[+division]/SL_V-or-NETAMT shape."""
    if source_type not in ("mw", "dw"):
        raise HTTPException(404, "source_type must be 'mw' or 'dw'")
    result = get_source_schema(source_type)
    if not result.get("ok"):
        raise HTTPException(502, result.get("error", "Could not read source schema"))
    return result


@router.post("/salesdata/reindex")
def salesdata_reindex(payload: dict = Body(...), user: dict = Depends(require_login)):
    return run_reindex(payload)


@router.post("/salesdata/reindex/start")
def salesdata_reindex_start(payload: dict = Body(...), user: dict = Depends(require_login)):
    """Background variant of /salesdata/reindex - returns a job id immediately
    instead of blocking for the whole read (day-wise runs tens of millions of
    rows). Poll /salesdata/reindex/poll/{job_id} for progress and the result."""
    return {"ok": True, "jobId": start_reindex_job(payload)}


@router.get("/salesdata/reindex/poll/{job_id}")
def salesdata_reindex_poll(job_id: str, user: dict = Depends(require_login)):
    # A completed job's result is streamed straight off disk instead of being
    # parsed into Python and re-serialized - see get_reindex_result_stream_path's
    # docstring: doing that in-process for a large day-wise result was freezing
    # the entire server (every user, every route) for as long as the parse took.
    stream_path = get_reindex_result_stream_path(job_id)
    if stream_path:
        # filename=... makes FastAPI set Content-Disposition: attachment -
        # harmless for the normal fetch().json() case (that header doesn't
        # affect the Fetch API), but it's what lets a plain <a href> to this
        # same URL trigger a real browser file download instead of trying to
        # navigate/render a huge JSON payload as a page - see the frontend's
        # "too large to preview" fallback in CalendarisedSalesTab, which
        # links straight here for a result too big to hold in the tab's memory.
        return FileResponse(stream_path, media_type="application/json", filename=f"reindex_{job_id}.json")
    return poll_reindex_job(job_id)


@router.post("/salesdata/reindex/cache-status")
def salesdata_reindex_cache_status(payload: dict = Body(...), user: dict = Depends(require_login)):
    """Per-month Open/Cached/Pending status for the given (source, calendar,
    extraDims, metric) combination, computed WITHOUT running a reindex - lets
    Run Reindex show what a click would actually do (skip the closed months
    already cached, only do real work for the rest) before the planner
    commits to waiting on it. See ReindexMonthCache / run_reindex in scans.py."""
    source = payload.get("source")
    months = payload.get("months") or []
    extra_dims = payload.get("extraDims") or []
    metric = payload.get("metric")
    if source not in ("mw", "dw") or not payload.get("calendarId") or not months:
        raise HTTPException(400, "source, calendarId and months are required")
    try:
        calendar_id = int(payload["calendarId"])  # calendar_day_pairs.calendar_id is bigint; the frontend sends it as a <select> string value
    except (TypeError, ValueError):
        raise HTTPException(400, "calendarId must be an integer")
    session = SessionLocal()
    try:
        pairs = session.execute(
            select(CalendarDayPair.cluster_name, CalendarDayPair.ref_date, CalendarDayPair.fut_date)
            .where(CalendarDayPair.calendar_id == calendar_id)
        ).all()
    finally:
        session.close()
    if not pairs:
        raise HTTPException(404, "Calendar not found or has no mappings")
    day_map = {}
    for cluster, ref_date, fut_date in pairs:
        day_map.setdefault(cluster, []).append([ref_date.isoformat(), fut_date.isoformat()])
    return reindex_month_cache_status(source, months, day_map, extra_dims, metric)


@router.get("/salesdata/snapshot/{source_type}/{kind}")
def salesdata_snapshot(source_type: str, kind: str, user: dict = Depends(require_login)):
    """The last successful Run Reindex output for this source, saved by
    run_reindex() - 'actual' (real sales on their own date) or 'trend_shifted'
    (calendar-shifted). Read by other apps (e.g. SalesPlan's Sales Sync) so
    they stay in step with Calendar Engine's own DB instead of re-parsing
    sales themselves."""
    from db.models.calendar import SalesSnapshot

    if source_type not in ("mw", "dw") or kind not in ("actual", "trend_shifted"):
        raise HTTPException(404, "source_type must be 'mw'/'dw', kind must be 'actual'/'trend_shifted'")
    session = SessionLocal()
    try:
        row = session.get(SalesSnapshot, (source_type, kind))
        if row is None:
            return {"ok": False, "computedAt": None}
        return {
            "ok": True, "source": row.source_type, "kind": row.kind, "grain": row.grain, "metric": row.metric,
            "columns": row.columns, "rows": row.rows, "rowsRead": row.rows_read, "rowsMapped": row.rows_mapped,
            "computedAt": row.computed_at.isoformat(),
        }
    finally:
        session.close()
