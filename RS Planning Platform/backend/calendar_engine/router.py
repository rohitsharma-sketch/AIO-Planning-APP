import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import delete, func, select

from auth.deps import require_login, require_role
from db.base import SessionLocal
from db.models.calendar import Calendar, CalendarCluster, CalendarClusterFestival, CalendarDayPair

router = APIRouter()


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
