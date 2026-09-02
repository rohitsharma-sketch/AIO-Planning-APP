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
import time

import pandas as pd

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
    # Short retry on Windows: this repo lives under Documents (OneDrive-synced
    # on this machine), which can briefly lock a just-written .tmp file to
    # sync it, turning a plain rename into a WinError 5 - see the matching
    # comment in reindex_worker.py's own _atomic_write_json, where this was
    # observed live failing an entire reindex run.
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


def _cluster_of(store_cluster, store):
    return store_cluster.get(store) or "(unmapped)"


def _load_festival_by_cluster_date(calendar_id):
    """{cluster_name -> {date -> [festival names]}} for this calendar, keyed
    both by exact futDate (day-wise columns) and its YYYY-MM prefix
    (month-wise columns) - same dual-keying the client's festivalByCluster
    builder in CalendarisedSalesTab/index.jsx uses, so a plain lookup by the
    column string works for both sources here too. Scoped PER CLUSTER (found
    live 2026-09-01: a single flat {date -> names} dict mixed every cluster's
    festivals into one lookup, so a cluster with no Onam configured at all
    still showed Onam in its output rows because some OTHER cluster in the
    same calendar has it). Returns {} if calendarId is missing (a result
    computed before this was threaded through) or the lookup fails for any
    reason - a missing Festival column is a labelling gap, not worth failing
    the whole CSV over.

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
                select(CalendarCluster.cluster_name, CalendarClusterFestival.name, CalendarClusterFestival.fut_date,
                       CalendarClusterFestival.pre, CalendarClusterFestival.core, CalendarClusterFestival.post)
                .join(CalendarCluster, CalendarCluster.id == CalendarClusterFestival.calendar_cluster_id)
                .where(CalendarCluster.calendar_id == int(calendar_id))
            ).all()
        finally:
            session.close()
        out = {}
        for cluster_name, name, fut_date, pre, core, post in rows:
            if not fut_date or not name:
                continue
            core = core or 1
            cluster_out = out.setdefault(cluster_name, {})
            for pos in range(-(pre or 0), (post or 0) + core):
                ds = (fut_date + timedelta(days=pos)).isoformat()
                cluster_out.setdefault(ds, set()).add(name)
                cluster_out.setdefault(ds[:7], set()).add(name)
        return {cl: {k: sorted(v) for k, v in m.items()} for cl, m in out.items()}
    except Exception:
        return {}


def _build_ref_by_cluster_col(payload, source):
    """{cluster_name -> {futureCol -> referenceDate}} straight from the
    reindex payload's own day-map - the same per-cluster scoping problem as
    festivals existed for "which reference date did this column come from":
    a single flat lookup mixed every cluster's mapping together, so it could
    show a reference date that isn't even this cluster's own (found live
    2026-09-01: UP+NCR's Holi pre-festive window maps 2027-03-15 from
    2026-02-25, but the mixed-cluster version showed 2026-03-09 - some other
    cluster's ordinary-day mapping for that date, winning a plurality vote
    across clusters that don't even share the same festival calendar).
    Exact for day-wise (one ref per future day, per cluster, even when a
    reference day is legitimately reused across two future days - see
    engine.js's "Same-Month Reuse"). Month-wise has no per-day source column
    to read back, so this buckets by the same plurality-of-days rule
    reindex_monthwise (scans.py) uses server-side, just scoped to one
    cluster instead of mixed across all of them."""
    day_map = payload.get("dayMap") or {}
    out = {}
    for cluster, pairs in day_map.items():
        if source == "dw":
            out[cluster] = {fut: ref for ref, fut in pairs}
        else:
            buckets = {}  # fut_month -> {ref_month: count}
            for ref, fut in pairs:
                rm, fm = ref[:7], fut[:7]
                b = buckets.setdefault(fm, {})
                b[rm] = b.get(rm, 0) + 1
            out[cluster] = {fm: max(counts, key=counts.get) for fm, counts in buckets.items()}
    return out


def _festival_of(festival_by_cluster_date, cluster, col):
    return ", ".join((festival_by_cluster_date.get(cluster) or {}).get(col, []))


def _ref_date_of(ref_by_cluster_col, global_ref_date_by_column, cluster, col):
    per_cluster = ref_by_cluster_col.get(cluster)
    if per_cluster is not None:
        return per_cluster.get(col, "")
    # No per-cluster map at all (e.g. calendarId missing from an older
    # payload) - fall back to the backend's global plurality rather than
    # showing nothing.
    return global_ref_date_by_column.get(col, "")


def write_wide_csv(result, store_cluster, festival_by_cluster_date, ref_by_cluster_col, out_path):
    key_fields = result.get("keyFields") or (["store", "division"] if result.get("grain") == "store_division" else ["store"])
    columns = sorted(result.get("columns") or [])
    global_ref_date_by_column = result.get("refDateByColumn") or {}
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

    # Wide is one row per store(+fields), one column per date - a single
    # Reference Date / Festival header row at the top can only ever be
    # accurate for ONE cluster's mapping at a time (see _festival_of's /
    # _ref_date_of's callers' docstrings for the cross-cluster bug this
    # replaced). Only emit them when every row in this export is the same
    # cluster; otherwise a wrong-for-most-rows header is worse than none -
    # use Stacked instead, where Reference Date/Festival are per-row.
    clusters_present = {_cluster_of(store_cluster, key_of[k].get("store", "")) for k in grouped}
    show_header_rows = len(clusters_present) == 1
    sole_cluster = next(iter(clusters_present)) if show_header_rows else None

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, **_CSV_KW)
        if show_header_rows:
            w.writerow(["Reference Date"] + [""] * len(key_fields)
                       + [_ref_date_of(ref_by_cluster_col, global_ref_date_by_column, sole_cluster, c) for c in columns])
            if festival_by_cluster_date:
                w.writerow(["Festival"] + [""] * len(key_fields)
                           + [_festival_of(festival_by_cluster_date, sole_cluster, c) for c in columns])
        elif len(clusters_present) > 1:
            w.writerow([f"Reference Date / Festival omitted - {len(clusters_present)} different clusters are mixed "
                        "in this export, and each can map a date differently. Use the Stacked view/download for "
                        "cluster-accurate values."])
        w.writerow(["Cluster"] + kf_headers + columns)
        for key in sorted(grouped.keys()):
            vals = grouped[key]
            row_key = key_of[key]
            store = row_key.get("store", "")
            w.writerow([_cluster_of(store_cluster, store)] + [row_key.get(f, "") for f in key_fields]
                       + [vals.get(c, "") for c in columns])


def write_stacked_csv(result, store_cluster, festival_by_cluster_date, ref_by_cluster_col, out_path):
    global_ref_date_by_column = result.get("refDateByColumn") or {}
    date_or_month_label = "Date" if result.get("source") == "dw" else "Month"

    totals = {}  # (store, col) -> summed value
    for row in result.get("rows") or []:
        key = (row.get("store", ""), row["col"])
        totals[key] = totals.get(key, 0) + row["value"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, **_CSV_KW)
        header = ["Cluster", "Store", date_or_month_label, "Reference Date"]
        if festival_by_cluster_date:
            header.append("Festival")
        header.append("Value")
        w.writerow(header)
        for (store, col) in sorted(totals.keys()):
            cluster = _cluster_of(store_cluster, store)
            row = [cluster, store, col, _ref_date_of(ref_by_cluster_col, global_ref_date_by_column, cluster, col)]
            if festival_by_cluster_date:
                row.append(_festival_of(festival_by_cluster_date, cluster, col))
            row.append(round(totals[(store, col)], 2))
            w.writerow(row)


def main():
    result_path, payload_path, view, out_path, done_path = sys.argv[1:6]

    try:
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        store_cluster, calendar_id, ref_by_cluster_col = {}, None, {}
        if os.path.exists(payload_path):
            with open(payload_path, encoding="utf-8") as f:
                payload = json.load(f)
            store_cluster = payload.get("storeCluster") or {}
            calendar_id = payload.get("calendarId")
            ref_by_cluster_col = _build_ref_by_cluster_col(payload, result.get("source"))
        festival_by_cluster_date = _load_festival_by_cluster_date(calendar_id)

        tmp_out = out_path + ".tmp"
        if view == "stacked":
            write_stacked_csv(result, store_cluster, festival_by_cluster_date, ref_by_cluster_col, tmp_out)
        else:
            write_wide_csv(result, store_cluster, festival_by_cluster_date, ref_by_cluster_col, tmp_out)
        os.replace(tmp_out, out_path)
        _atomic_write_json(done_path, {"ok": True, "error": None})
    except Exception as e:
        _atomic_write_json(done_path, {"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
