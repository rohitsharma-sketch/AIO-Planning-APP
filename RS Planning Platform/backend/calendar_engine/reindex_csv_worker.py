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
with the original request, so no extra DB lookup here). Festival names are
NOT included here (unlike the interactive table's optional Festival row) -
that mapping is built client-side from the calendar's festival records at
run time and isn't persisted anywhere this worker can reach; a large-result
CSV is missing that one enrichment column as a result.

Usage: python reindex_csv_worker.py <result.json> <payload.json> <wide|stacked> <out.csv> <done_marker.json>
"""
import csv
import json
import os
import sys

KEY_LABELS = {"store": "Store", "division": "Division"}


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _cluster_of(store_cluster, store):
    return store_cluster.get(store) or "(unmapped)"


def write_wide_csv(result, store_cluster, out_path):
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
        w = csv.writer(f)
        w.writerow(["Reference Date"] + [""] * len(key_fields) + [ref_date_by_column.get(c, "") for c in columns])
        w.writerow(["Cluster"] + kf_headers + columns)
        for key in sorted(grouped.keys()):
            vals = grouped[key]
            row_key = key_of[key]
            store = row_key.get("store", "")
            w.writerow([_cluster_of(store_cluster, store)] + [row_key.get(f, "") for f in key_fields]
                       + [vals.get(c, "") for c in columns])


def write_stacked_csv(result, store_cluster, out_path):
    ref_date_by_column = result.get("refDateByColumn") or {}
    date_or_month_label = "Date" if result.get("source") == "dw" else "Month"

    totals = {}  # (store, col) -> summed value
    for row in result.get("rows") or []:
        key = (row.get("store", ""), row["col"])
        totals[key] = totals.get(key, 0) + row["value"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Cluster", "Store", date_or_month_label, "Reference Date", "Value"])
        for (store, col) in sorted(totals.keys()):
            w.writerow([_cluster_of(store_cluster, store), store, col, ref_date_by_column.get(col, ""), round(totals[(store, col)], 2)])


def main():
    result_path, payload_path, view, out_path, done_path = sys.argv[1:6]

    try:
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
        store_cluster = {}
        if os.path.exists(payload_path):
            with open(payload_path, encoding="utf-8") as f:
                store_cluster = json.load(f).get("storeCluster") or {}

        tmp_out = out_path + ".tmp"
        if view == "stacked":
            write_stacked_csv(result, store_cluster, tmp_out)
        else:
            write_wide_csv(result, store_cluster, tmp_out)
        os.replace(tmp_out, out_path)
        _atomic_write_json(done_path, {"ok": True, "error": None})
    except Exception as e:
        _atomic_write_json(done_path, {"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
