"""The ONE rule for which data-lake file every app reads (user, 2026-09-29: "always pick the latest file from the
folders to sync ... make sure that the data is flowing through all the apps consistently").

Each data-lake folder gets periodic FULL re-exports (every file covers the whole history), so exactly one file is
read: the newest by modified time - unless it is clearly incomplete, then the next newest good one. Incomplete =
unreadable / still being written, missing columns the previous file had, or fewer than MIN_ROW_SHARE of its rows
(29 Sep 2026: a sell-through export of exactly 50,000 rows landed next to a 7,069,667-row one).

Used by BIS (sync_server), the Calendar engine (scans - which also feeds Sales Plan, AOP syncs and MRP
Re-apportionment) and Listing / Delisting, so they can no longer drift onto different files.
"""
import glob
import os

MIN_ROW_SHARE = 0.9
_cache = {}  # (folder, pattern) -> (signature of the listing, result)


def _footer(path):
    """(row count, column names) from the parquet footer, or None if it can't be read (e.g. still being copied)."""
    try:
        import pyarrow.parquet as pq
        with open(path, "rb") as fh:   # an open handle: pyarrow mangles \\server\share paths given as strings
            f = pq.ParquetFile(fh)
            return f.metadata.num_rows, set(f.schema_arrow.names)
    except Exception:
        return None


def pick_latest(folder, pattern="*.parquet"):
    """-> (path or None, notes). notes explains every newer file that was skipped."""
    files = sorted(glob.glob(os.path.join(folder, pattern)), key=os.path.getmtime, reverse=True)
    sig = tuple((f, os.path.getmtime(f), os.path.getsize(f)) for f in files)
    hit = _cache.get((folder, pattern))
    if hit and hit[0] == sig:
        return hit[1]
    if not pattern.endswith(".parquet") or len(files) < 2:
        result = (files[0] if files else None), []
    else:
        foot = {f: _footer(f) for f in files[:4]}   # the newest few are enough to find the last good export
        notes, pick = [], None
        for i, f in enumerate(files[:4]):
            ft = foot[f]
            ref = next((foot[g] for g in files[i + 1:4] if foot[g]), None)   # the next readable older export
            why = ("unreadable (still being written?)" if ft is None else
                   f"missing columns {sorted(ref[1] - ft[1])}" if ref and not ref[1] <= ft[1] else
                   f"only {ft[0]:,} rows vs {ref[0]:,} in the previous export" if ref and ft[0] < MIN_ROW_SHARE * ref[0] else
                   None)
            if why is None:
                pick = f
                break
            notes.append(f"skipped {os.path.basename(f)}: {why}")
        result = (pick or files[0]), notes
    _cache[(folder, pattern)] = (sig, result)
    return result


def latest_path(folder, pattern="*.parquet"):
    """pick_latest without the notes - a drop-in for the old `max(files, key=getmtime)`."""
    return pick_latest(folder, pattern)[0]


if __name__ == "__main__":   # python rs_common/lake_files.py  -> what every app reads right now
    base = r"\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw"
    for d in ("rs_sales_19-_till_date", "rs_19_to_26_day_wise_sales_data_compiled", "rs_weekly_sell_ths_apps"):
        p, notes = pick_latest(os.path.join(base, d))
        print(f"{d}: {os.path.basename(p) if p else None}" + "".join(f"\n   {n}" for n in notes))
