"""
sync.sources['calendar_library'] -> calendar.calendars + calendar.calendar_day_pairs

Reads the Calendar Engine's Local DB/calendar_library.json directly (a local
file now that the project folder is shared in) — no dependency on the
Calendar Engine's HTTP server. Each entry's dayMap is already fully built
(festival-window "shift-repair" logic lives in the Calendar Engine's own UI,
out of scope here); this only copies the finished per-cluster day pairs.

Run manually: python sync/calendar_library_sync.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.calendar import Calendar, CalendarDayPair
from db.models.sync import SyncSource
from sync.common import sync_run

SOURCE_KEY = "calendar_library"


def run():
    with sync_run(SOURCE_KEY) as (session, result):
        source = session.get(SyncSource, SOURCE_KEY)
        path = source.config["path"]

        with open(path, encoding="utf-8") as f:
            lib = json.load(f)
        entries = [c for c in lib if isinstance(c, dict) and c.get("dayMap")]
        result["rows_read"] = len(entries)

        pairs_written = 0
        for c in entries:
            calendar_id = int(c["id"])
            stmt = pg_insert(Calendar).values(
                calendar_id=calendar_id, name=c["name"], ref_year=c["refYear"], fut_year=c["futYear"],
                saved_at=c["savedAt"], engine=c.get("engine"),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["calendar_id"],
                set_={"name": stmt.excluded.name, "ref_year": stmt.excluded.ref_year,
                      "fut_year": stmt.excluded.fut_year, "saved_at": stmt.excluded.saved_at,
                      "engine": stmt.excluded.engine},
            )
            session.execute(stmt)

            session.execute(delete(CalendarDayPair).where(CalendarDayPair.calendar_id == calendar_id))
            rows = [
                {"calendar_id": calendar_id, "cluster_name": cluster, "seq": seq,
                 "ref_date": datetime.date.fromisoformat(pair[0]), "fut_date": datetime.date.fromisoformat(pair[1])}
                for cluster, pairs in c["dayMap"].items()
                for seq, pair in enumerate(pairs)
            ]
            if rows:
                session.execute(CalendarDayPair.__table__.insert(), rows)
            pairs_written += len(rows)

        result["rows_updated"] = len(entries)
        result["rows_added"] = 0
        result["detail"] = {"source_file": os.path.basename(path), "day_pairs_written": pairs_written}


if __name__ == "__main__":
    run()
    print("calendar_library_sync: done")
