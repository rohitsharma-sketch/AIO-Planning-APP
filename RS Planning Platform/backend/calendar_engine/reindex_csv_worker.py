"""Standalone subprocess worker that converts an already-completed reindex
job's result.json into a CSV file, run in its own OS process for the same
reason reindex_worker.py is: json.load()-ing a huge (400+MB) result.json and
then building a CSV from it is real CPU-bound work that would otherwise hold
the GIL and freeze the main server for every user for however long that
takes - exactly the class of bug fixed elsewhere in this file's siblings.

This exists because ReindexOutputPanel's own client-side "Download CSV"
requires the full parsed result in the browser tab's memory first - fine for
a normal run, but a combined multi-month day-wise result can be too large to
safely hold there (see get_reindex_result_stream_path's docstring - this was
reproduced live as a renderer crash). The fix is NOT to fall back to hand the
user a raw JSON file (every download in this app has always been CSV, and a
raw JSON dump the user then has to convert themselves is not the same
deliverable) - it's to do the CSV conversion server-side, in a subprocess, so
neither the server nor the browser ever has to hold the whole thing at once.

Produces the same two layouts ReindexOutputPanel.jsx's downloadReindexed()/
downloadStacked() already write client-side:
  wide:    Reference Date row, then Cluster + keyFields + one column per
           date/month, one row per (store[+extra fields]) key.
  stacked: Cluster, Store, Date/Month, Reference Date, Value - one row per
           (store, column), summed across whatever extra fields the run was
           broken out by.
Cluster comes from the reindex payload's own storeCluster map (already sent
with the original request, so no extra DB lookup here). Festival names come
from a DB lookup keyed by the payload's calendarId (added to the reindex
request just for this) - same {date -> [names]} shape the interactive
table's Festival row builds client-side from getCalendar(), just built here
from calendar_cluster_festivals directly since this worker has no browser-
fetched calendar detail to read.

Usage: python reindex_csv_worker.py <result.json> <payload.json> <wide|stacked> <out.csv> <done_marker.json>
"""
import csv
import json
import os
import sys

# QUOTE_ALL to match the client-side csvField/downloadCsv convention every
# other CSV in this app already uses (ReindexOutputPanel.jsx) - a plain
# csv.writer() only quotes fields that need it, which is valid CSV either
# way but looks inconsistent next to a file downloaded from the interactive
# table instead of this large-result fallback.
_CSV_KW = {"quoting": csv.QUOTE_ALL}

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this dir, for `import scans`
# db.base / db.models live under Tentative AOP Forecaster - scans.py adds this
# same path at its own module level, but that only helps if scans is already
# imported first; _load_festival_by_date below imports db.base directly, so
# this needs to be on sys.path unconditionally, not depend on import order.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Tentative AOP Forecaster"))

KEY_LABELS = {"store": "Store", "division": "Division"}


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _cluster_of(store_cluster, store):
    return store_cluster.get(store) or "(unmapped)"


def _load_festival_by_date(calendar_id):
    """{date -> [festival names]} for every cluster in this calendar, keyed
    both by exact futDate (day-wise columns) and its YYYY-MM prefix
    (month-wise columns) - same dual-keying the client's festivalByDate
    builder in CalendarisedSalesTab/index.jsx uses, so a plain lookup by the
    column string works for both sources here too. Returns {} if calendarId
    is missing (a result computed before this was threaded through) or the
    lookup fails for any reason - a missing Festival column is a labelling
    gap, not worth failing the whole CSV over.

    Expands the FULL pre/core/post window around each festival's fut_date,
    not just the single anchor day - same loop engine.js's buildFestMap (and
    this function's client-side counterpart) use. Labeling only the exact
    fut_date was a real bug (found live 2026-09-01): a festival with
    pre=4/core=3/post=0 only had its single core day labeled, leaving the
    other 6 days of its real window blank."""
    if not calendar_id:
        return {}
    try:
        from datetime import timedelta
        from sqlalchemy import select
        from db.base import SessionLocal
        from db.models.calendar import CalendarCluster, CalendarClusterFestival

        session = SessionLocal()
        try:
            rows = session.execute(
                select(CalendarClusterFestival.name, CalendarClusterFestival.fut_date,
                       CalendarClusterFestival.pre, CalendarClusterFestival.core, CalendarClusterFestival.post)
                .join(CalendarCluster, CalendarCluster.id == CalendarClusterFestival.calendar_cluster_id)
                .where(CalendarCluster.calendar_id == int(calendar_id))
            ).all()
        finally:
            session.close()
        out = {}
        for name, fut_date, pre, core, post in rows:
            if not fut_date or not name:
                continue
            core = core or 1
            for pos in range(-(pre or 0), (post or 0) + core):
                ds = (fut_date + timedelta(days=pos)).isoformat()
                out.setdefault(ds, set()).add(name)
                out.setdefault(ds[:7], set()).add(name)
        return {k: sorted(v) for k, v in out.items()}
    except Exception:
        return {}


def _festival_of(festival_by_date, col):
    return ", ".join(festival_by_date.get(col, []))


def write_wide_csv(result, store_cluster, festival_by_date, out_path):
    key_fields = result.get("keyFields") or (["store", "division"] if result.get("grain") == "store_division" else ["store"])
    columns = sorted(result.get("columns") or [])
    ref_date_by_column = result.get("refDateByColumn") or {}
    kf_headers = [KEY_LABELS.get(f, f) for f in key_fields]

    # Group long-form rows into {key_tuple: {col: value}} - same grouping
    # rxWideRows()/the `wide` useMemo does client-side.
    grouped = {}
    key_of = {}
    for row in result.get("rows") or []:
        key = tuple(row.get(f, "") or "" for f in key_fields)
        e = grouped.setdefault(key, {})
        e[row["col"]] = row["value"]
        key_of.setdefault(key, {f: row.get(f, "") for f in key_fields})

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, **_CSV_KW)
        w.writerow(["Reference Date"] + [""] * len(key_fields) + [ref_date_by_column.get(c, "") for c in columns])
        if festival_by_date:
            w.writerow(["Festival"] + [""] * len(key_fields) + [_festival_of(festival_by_date, c) for c in columns])
        w.writerow(["Cluster"] + kf_headers + columns)
        for key in sorted(grouped.keys()):
            vals = grouped[key]
            row_key = key_of[key]
            store = row_key.get("store", "")
            w.writerow([_cluster_of(store_cluster, store)] + [row_key.get(f, "") for f in key_fields]
                       + [vals.get(c, "") for c in columns])


def write_stacked_csv(result, store_cluster, festival_by_date, out_path):
    ref_date_by_column = result.get("refDateByColumn") or {}
    date_or_month_label = "Date" if result.get("source") == "dw" else "Month"

    totals = {}  # (store, col) -> summed value
    for row in result.get("rows") or []:
        key = (row.get("store", ""), row["col"])
        totals[key] = totals.get(key, 0) + row["value"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, **_CSV_KW)
        header = ["Cluster", "Store", date_or_month_label, "Reference Date"]
        if festival_by_date:
            header.append("Festival")
        header.append("Value")
        w.writerow(header)
        for (store, col) in sorted(totals.keys()):
            row = [_cluster_of(store_cluster, store), store, col, ref_date_by_column.get(col, "")]
            if festival_by_date:
                row.append(_festival_of(festival_by_date, col))
            row.append(round(totals[(store, col)], 2))
            w.writerow(row)


def main():
    result_path, payload_path, view, out_path, done_path = sys.argv[1:6]

    try:
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        store_cluster, calendar_id = {}, None
        if os.path.exists(payload_path):
            with open(payload_path, encoding="utf-8") as f:
                payload = json.load(f)
            store_cluster = payload.get("storeCluster") or {}
            calendar_id = payload.get("calendarId")
        festival_by_date = _load_festival_by_date(calendar_id)

        tmp_out = out_path + ".tmp"
        if view == "stacked":
            write_stacked_csv(result, store_cluster, festival_by_date, tmp_out)
        else:
            write_wide_csv(result, store_cluster, festival_by_date, tmp_out)
        os.replace(tmp_out, out_path)
        _atomic_write_json(done_path, {"ok": True, "error": None})
    except Exception as e:
        _atomic_write_json(done_path, {"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
