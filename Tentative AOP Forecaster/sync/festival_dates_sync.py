"""
Google "Holidays in India" public calendar -> calendar.festival_reference_dates,
then re-dates the live Festival Master (cluster_profile_festivals, for
app_state_meta's ref/fut year) and every locked calendar's festival list
(calendar_cluster_festivals, for that calendar's OWN ref/fut year) from it.

Why: festival dates used to be hand-typed / hard-coded (festivalData.js's
FESTIVAL_DATES), and drifted (the live Festival Master held 2024/2025 dates).
Google's ICS feed needs no API key and covers ~2021-2031.

Rules (user-approved 2026-09-24):
  * GOOGLE_NAMES maps app festival name -> Google SUMMARY. A " (tentative)"
    suffix is stripped; a confirmed entry beats a tentative one for the same year.
  * DERIVED: Nuakhai = Ganesh Chaturthi + 1, Shraad = Sharad Navratri day 1 - 15
    (Pitru Paksha start, 15-day core), Kali Puja = Diwali.
  * OVERRIDES beat Google (deliberate earlier choices).
  * Only ref_date/fut_date change, only where a reference date exists and
    differs. pre/core/post, names, cluster membership and calendar_day_pairs
    are never touched (a locked calendar's day-map only changes when it is
    regenerated and re-saved in the UI).
  * Fetch failure -> table untouched, ConnectionError whose message
    sync/common.py's _is_network_offline() treats as 'offline'.

Run manually: python sync/festival_dates_sync.py
"""
import datetime
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

SOURCE_KEY = "festival_dates"
ICS_URL = ("https://calendar.google.com/calendar/ical/"
           "en.indian%23holiday%40group.v.calendar.google.com/public/basic.ics")
FETCH_TIMEOUT_SECONDS = 30

GOOGLE_NAMES = {
    "Holi": "Holi",
    "Eid al-Fitr": "Ramzan Id",
    "Eid al-Adha": "Bakrid",
    "Rath Yatra": "Rath Yatra",
    "Raksha Bandhan": "Raksha Bandhan",
    "Milad-un-Nabi": "Milad un-Nabi",
    "Dussehra": "Dussehra",
    "Diwali": "Diwali/Deepavali",
    "Bihu": "Bahag Bihu (Assam)",
    "Navratri": "First Day of Sharad Navratri",
    "Chhath Puja": "Chhat Puja (Pratihar Sashthi/Surya Sashthi)",
    "Makar Sankranti": "Makar Sankranti",
    "Basant Panchami": "Vasant Panchami",
    "Ganesh Chaturthi": "Ganesh Chaturthi",
    "Janmashtami": "Janmashtami",
}
# festival -> (base festival, day offset, rule text stored as source_name)
DERIVED = {
    "Nuakhai": ("Ganesh Chaturthi", 1, "Ganesh Chaturthi + 1 day"),
    "Shraad": ("Navratri", -15, "First Day of Sharad Navratri - 15 days (Pitru Paksha start, 15-day core)"),
    "Kali Puja": ("Diwali", 0, "Same day as Diwali"),
}
# (festival, year) -> (date, reason stored as source_name)
# Dates must be INDIAN, never global (user rule 2026-09-25): India sights the
# moon a day after Saudi/global, so Eid, Bakrid, Milad etc. fall one day later
# here - Google's India calendar already carries the Indian date. Never add an
# override that puts back a global date (the old Eid al-Adha 2026 = 05-27
# "J&K" override was the global date and was removed for this reason).
OVERRIDES = {
    ("Chhath Puja", 2027): ("2027-11-05", "Closing day (Google: 2027-11-04)"),
}

_DDL = """
CREATE TABLE IF NOT EXISTS calendar.festival_reference_dates (
    id SERIAL PRIMARY KEY,
    festival TEXT NOT NULL,
    year INTEGER NOT NULL,
    date DATE NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('google', 'derived', 'override')),
    source_name TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_festival_reference_dates UNIQUE (festival, year)
)
"""
_ready = False


def parse_ics(text):
    """{summary: {year: date}} - tentative suffix stripped, confirmed beats tentative."""
    text = re.sub(r"\r?\n[ \t]", "", text)  # RFC 5545 line unfolding
    out, tentative = {}, {}
    for block in re.findall(r"BEGIN:VEVENT.*?END:VEVENT", text, re.S):
        d = re.search(r"DTSTART;VALUE=DATE:(\d{8})", block)
        s = re.search(r"SUMMARY:(.*)", block)
        if not (d and s):
            continue
        name = s.group(1).strip().replace("\\,", ",")
        is_tent = name.endswith(" (tentative)")
        name = name.removesuffix(" (tentative)")
        date = datetime.date(int(d.group(1)[:4]), int(d.group(1)[4:6]), int(d.group(1)[6:]))
        prev_tent = tentative.get((name, date.year))
        if prev_tent is None or (prev_tent and not is_tent):
            out.setdefault(name, {})[date.year] = date
            tentative[(name, date.year)] = is_tent
    return out


def reference_rows(text):
    """[{festival, year, date, source, source_name}] from ICS text - pure, no DB."""
    events = parse_ics(text)
    rows = {}
    for fest, summary in GOOGLE_NAMES.items():
        for year, date in events.get(summary, {}).items():
            rows[(fest, year)] = {"date": date, "source": "google", "source_name": summary}
    for fest, (base, offset, rule) in DERIVED.items():
        for (b, year), r in list(rows.items()):
            if b == base:
                rows[(fest, year)] = {"date": r["date"] + datetime.timedelta(days=offset),
                                      "source": "derived", "source_name": rule}
    for (fest, year), (date, reason) in OVERRIDES.items():
        rows[(fest, year)] = {"date": datetime.date.fromisoformat(date), "source": "override", "source_name": reason}
    return [{"festival": f, "year": y, **r} for (f, y), r in sorted(rows.items())]


def ensure_schema():
    """Idempotent: the reference table + this job's sync.sources row (SyncRun
    has an FK to it). Same CREATE TABLE IF NOT EXISTS pattern as app.py's
    _ensure_plan_versions_table - db/models is owned elsewhere."""
    global _ready
    if _ready:
        return
    from sqlalchemy import text
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text(_DDL))
        db.execute(text(
            "INSERT INTO sync.sources (source_key, config, enabled, ttl_minutes) "
            "VALUES (:k, CAST(:cfg AS JSON), true, 1440) ON CONFLICT (source_key) DO NOTHING"
        ), {"k": SOURCE_KEY, "cfg": '{"url": "%s"}' % ICS_URL})
        db.commit()
    _ready = True


def _download():
    with urllib.request.urlopen(ICS_URL, timeout=FETCH_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8")


def _fetch():
    from sync.common import call_with_timeout
    try:
        return call_with_timeout(_download, timeout=FETCH_TIMEOUT_SECONDS + 15)
    except OSError as e:  # URLError, socket timeout, TimeoutError
        # Message matches sync/common.py's _is_network_offline -> status 'offline'.
        raise ConnectionError(f"Google holiday calendar unreachable ({type(e).__name__}: {e}) - "
                              "network path was not found; festival_reference_dates left untouched") from e


def plan_redate(profile_rows, locked_rows, ref, app_ref_year, app_fut_year):
    """Pure: list of changes. profile_rows: (row, cluster_name); locked_rows:
    (row, cluster_name, calendar); ref: {(festival, year): date}."""
    changes = []
    targets = [(r, "Festival Master", cl, app_ref_year, app_fut_year) for r, cl in profile_rows]
    targets += [(r, f"Calendar {c.calendar_id} {c.name}", cl, c.ref_year, c.fut_year) for r, cl, c in locked_rows]
    for row, scope, cluster, ry, fy in targets:
        for field, year in (("ref_date", ry), ("fut_date", fy)):
            new = ref.get((row.name, int(year))) if year else None
            old = getattr(row, field)
            if new and new != old:
                changes.append({"scope": scope, "cluster": cluster, "festival": row.name, "field": field,
                                "old": old.isoformat(), "new": new.isoformat(), "_row": row})
    return changes


def load_targets(session):
    from sqlalchemy import select
    from db.models.calendar import (AppStateMeta, Calendar, CalendarCluster, CalendarClusterFestival,
                                    ClusterProfile, ClusterProfileFestival)
    state = session.get(AppStateMeta, 1)
    profile_rows = session.execute(
        select(ClusterProfileFestival, ClusterProfile.name)
        .join(ClusterProfile, ClusterProfile.id == ClusterProfileFestival.cluster_profile_id)
    ).all()
    locked_rows = session.execute(
        select(CalendarClusterFestival, CalendarCluster.cluster_name, Calendar)
        .join(CalendarCluster, CalendarCluster.id == CalendarClusterFestival.calendar_cluster_id)
        .join(Calendar, Calendar.calendar_id == CalendarCluster.calendar_id)
    ).all()
    return (state.ref_year if state else None), (state.fut_year if state else None), profile_rows, locked_rows


def run():
    """Returns {"reference_rows": n, "changes": [...]}, or None if offline."""
    from sqlalchemy import text
    from sync.common import sync_run

    ensure_schema()
    out = None
    with sync_run(SOURCE_KEY) as (session, result):
        rows = reference_rows(_fetch())  # raises offline before anything is written
        now = datetime.datetime.now(datetime.timezone.utc)
        session.execute(text(
            "INSERT INTO calendar.festival_reference_dates (festival, year, date, source, source_name, fetched_at) "
            "VALUES (:festival, :year, :date, :source, :source_name, :fetched_at) "
            "ON CONFLICT (festival, year) DO UPDATE SET date = EXCLUDED.date, source = EXCLUDED.source, "
            "source_name = EXCLUDED.source_name, fetched_at = EXCLUDED.fetched_at"
        ), [{**r, "fetched_at": now} for r in rows])

        ref = {(r["festival"], r["year"]): r["date"] for r in rows}
        ry, fy, profile_rows, locked_rows = load_targets(session)
        changes = plan_redate(profile_rows, locked_rows, ref, ry, fy)
        for c in changes:
            setattr(c.pop("_row"), c["field"], datetime.date.fromisoformat(c["new"]))
            print(f"[{SOURCE_KEY}] {c['scope']} / {c['cluster']} / {c['festival']} {c['field']}: {c['old']} -> {c['new']}")

        result["rows_read"] = len(rows)
        result["rows_updated"] = len(changes)
        result["rows_added"] = 0
        result["detail"] = {"url": ICS_URL, "changes": changes}
        out = {"reference_rows": len(rows), "changes": changes}
    return out


if __name__ == "__main__":
    r = run()
    print("festival_dates_sync: " + ("offline - nothing changed" if r is None else f"done, {len(r['changes'])} date(s) changed"))
