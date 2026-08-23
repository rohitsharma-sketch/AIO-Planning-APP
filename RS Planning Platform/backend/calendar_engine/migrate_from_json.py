"""Re-runnable import: Calendar Engine's Local DB/*.json -> Postgres calendar
schema. Safe to run more than once (upsert/full-replace per table, matching
each table's own semantics) -- run once now to validate the new backend
against real data, and again immediately before sub-project B's frontend
cutover to catch anything edited via the old :7822 UI in between."""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.base import SessionLocal
from db.models.calendar import (
    AppStateMeta, Calendar, CalendarCluster, CalendarClusterFestival, CalendarDayPair,
    ClusterProfile, ClusterProfileFestival, FestivalChangelogEntry, SalesdataLinkSelection,
    StoreCalendarCluster, StoreClusterLogEntry, StoreClusterMapMeta,
)

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Calendar Engine", "Local DB")


def _load(name):
    with open(os.path.join(DB_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def _migrate_calendar_library(session):
    lib = _load("calendar_library.json")
    rows_written = 0
    for c in lib:
        if not isinstance(c, dict) or not c.get("dayMap"):
            continue
        calendar_id = int(c["id"])
        stmt = pg_insert(Calendar).values(
            calendar_id=calendar_id, name=c["name"], ref_year=c["refYear"], fut_year=c["futYear"],
            saved_at=c["savedAt"], engine=c.get("engine"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["calendar_id"],
            set_={"name": stmt.excluded.name, "ref_year": stmt.excluded.ref_year,
                  "fut_year": stmt.excluded.fut_year, "saved_at": stmt.excluded.saved_at, "engine": stmt.excluded.engine},
        )
        session.execute(stmt)

        old_cluster_ids = [r[0] for r in session.execute(
            select(CalendarCluster.id).where(CalendarCluster.calendar_id == calendar_id)).all()]
        if old_cluster_ids:
            session.execute(delete(CalendarClusterFestival).where(CalendarClusterFestival.calendar_cluster_id.in_(old_cluster_ids)))
        session.execute(delete(CalendarCluster).where(CalendarCluster.calendar_id == calendar_id))
        for cluster in c.get("clusters", []):
            cl = CalendarCluster(calendar_id=calendar_id, cluster_name=cluster["name"], region=cluster.get("region"))
            session.add(cl)
            session.flush()
            for fest in cluster.get("festivals", []):
                session.add(CalendarClusterFestival(
                    calendar_cluster_id=cl.id, source_festival_id=fest["id"], name=fest["name"],
                    ref_date=datetime.date.fromisoformat(fest["refDate"]), fut_date=datetime.date.fromisoformat(fest["futDate"]),
                    pre=fest["pre"], core=fest["core"], post=fest["post"],
                ))

        session.execute(delete(CalendarDayPair).where(CalendarDayPair.calendar_id == calendar_id))
        pairs = [
            {"calendar_id": calendar_id, "cluster_name": cluster, "seq": seq,
             "ref_date": datetime.date.fromisoformat(pair[0]), "fut_date": datetime.date.fromisoformat(pair[1])}
            for cluster, pp in c["dayMap"].items() for seq, pair in enumerate(pp)
        ]
        if pairs:
            session.execute(CalendarDayPair.__table__.insert(), pairs)
        rows_written += 1
    return rows_written


def _migrate_store_cluster_map(session):
    scm = _load("store_cluster_map.json")
    stores = scm.get("stores", [])
    locked_at = scm.get("lockedAt")

    session.execute(delete(StoreCalendarCluster))
    rows = [{"store_id": s["store"].strip(), "cluster_name": s["cluster"].strip(), "locked_at": locked_at}
            for s in stores if s.get("store") and s.get("cluster")]
    if rows:
        session.execute(StoreCalendarCluster.__table__.insert(), rows)

    meta = session.get(StoreClusterMapMeta, 1)
    if meta is None:
        meta = StoreClusterMapMeta(id=1)
        session.add(meta)
    meta.source = scm.get("source")
    meta.aliases = scm.get("aliases", {})
    meta.edited_at = scm.get("editedAt")
    return len(rows)


def _migrate_store_cluster_log(session):
    log = _load("store_cluster_log.json")
    session.execute(delete(StoreClusterLogEntry))
    rows = [{"at": e["at"], "source": e.get("source"), "summary": e["summary"], "added": e["added"],
              "removed": e["removed"], "reassigned": e["reassigned"], "details": e["details"]} for e in log]
    if rows:
        session.execute(StoreClusterLogEntry.__table__.insert(), rows)
    return len(rows)


def _migrate_app_state(session):
    state = _load("app_state.json")
    meta = session.get(AppStateMeta, 1)
    if meta is None:
        meta = AppStateMeta(id=1)
        session.add(meta)
    meta.active_cluster_idx = state.get("activeClusterIdx", 0)
    meta.ref_year = state.get("refYear")
    meta.fut_year = state.get("futYear")
    meta.max_shift = state.get("maxShift")
    meta.mo_pri = state.get("moPri")
    meta.theme_id = state.get("themeId")
    meta.saved_at = state.get("savedAt")
    meta.migrations = state.get("migrations", [])

    old_ids = [r[0] for r in session.execute(select(ClusterProfile.id)).all()]
    if old_ids:
        session.execute(delete(ClusterProfileFestival).where(ClusterProfileFestival.cluster_profile_id.in_(old_ids)))
        session.execute(delete(ClusterProfile).where(ClusterProfile.id.in_(old_ids)))
    profiles_written = 0
    for profile in state.get("clusterProfiles", []):
        p = ClusterProfile(name=profile["name"], region=profile.get("region"), next_id=profile["nextId"])
        session.add(p)
        session.flush()
        for fest in profile.get("festivals", []):
            session.add(ClusterProfileFestival(
                cluster_profile_id=p.id, source_festival_id=fest["id"], name=fest["name"],
                ref_date=datetime.date.fromisoformat(fest["refDate"]), fut_date=datetime.date.fromisoformat(fest["futDate"]),
                pre=fest["pre"], core=fest["core"], post=fest["post"],
            ))
        profiles_written += 1
    return profiles_written


def _migrate_festival_changelog(session):
    changelog = _load("festival_changelog.json")

    # A handful of real entries only record a partial diff (e.g. just `post`
    # changed, no refDate/futDate) -- these are artifacts of someone toggling
    # the app's refYear/futYear UI fields while testing a "post" duration
    # setting, not real historical calendar snapshots (confirmed: e.g. the
    # "2025-2025" entry has no relation to its own range_key's implied dates).
    # There is no correct ref_date/fut_date recoverable for these from the
    # source data -- never fabricate calendar dates. Since
    # FestivalChangelogEntry.ref_date/fut_date are NOT NULL (Task 1's
    # schema), entries missing either field are skipped entirely.
    rows_written = 0
    rows_skipped = 0
    for range_key, clusters in changelog.items():
        for cluster_name, festivals in clusters.items():
            for festival_name, entry in festivals.items():
                # `entry` may also carry `pre`/`core`/`post` day-count overrides
                # (the frontend writes a sparse override record). These are
                # intentionally NOT migrated -- calendar.festival_changelog has
                # no columns for them, and the controller ruled this deferred
                # to a follow-up schema change rather than reopening the table
                # design now. See the spec's Goals section
                # (docs/superpowers/specs/2026-08-23-calendar-engine-backend-migration-design.md).
                if "refDate" not in entry or "futDate" not in entry:
                    rows_skipped += 1
                    continue

                stmt = pg_insert(FestivalChangelogEntry).values(
                    range_key=range_key, cluster_name=cluster_name, festival_name=festival_name,
                    ref_date=datetime.date.fromisoformat(entry["refDate"]), fut_date=datetime.date.fromisoformat(entry["futDate"]),
                    saved_at=entry["savedAt"],
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["range_key", "cluster_name", "festival_name"],
                    set_={"ref_date": stmt.excluded.ref_date, "fut_date": stmt.excluded.fut_date, "saved_at": stmt.excluded.saved_at},
                )
                session.execute(stmt)
                rows_written += 1
    return rows_written, rows_skipped


def _migrate_salesdata_link_selection(session, filename, source_type):
    if not os.path.exists(os.path.join(DB_DIR, filename)):
        return 0
    sel = _load(filename)
    row = session.get(SalesdataLinkSelection, source_type)
    if row is None:
        row = SalesdataLinkSelection(source_type=source_type)
        session.add(row)
    row.months = sel.get("months", [])
    row.path = sel.get("path", "")
    row.synced_at = sel.get("syncedAt")
    return 1


def run():
    session = SessionLocal()
    try:
        changelog_rows, changelog_skipped = _migrate_festival_changelog(session)
        summary = {
            "calendar_library": {"rows": _migrate_calendar_library(session)},
            "store_cluster_map": {"rows": _migrate_store_cluster_map(session)},
            "store_cluster_log": {"rows": _migrate_store_cluster_log(session)},
            "app_state": {"rows": _migrate_app_state(session)},
            "festival_changelog": {"rows": changelog_rows, "skipped_incomplete": changelog_skipped},
            "salesdata_link_selection_mw": {"rows": _migrate_salesdata_link_selection(session, "salesdata_link_selection.json", "mw")},
            "salesdata_link_selection_dw": {"rows": _migrate_salesdata_link_selection(session, "salesdata_link_selection_daywise.json", "dw")},
        }
        session.commit()
        return summary
    finally:
        session.close()


if __name__ == "__main__":
    result = run()
    for key, info in result.items():
        print(f"{key}: {info['rows']} rows")
