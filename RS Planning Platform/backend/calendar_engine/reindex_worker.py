"""Standalone subprocess worker for Run Reindex - see start_reindex_job() in
scans.py. Runs in a genuinely separate OS process (not a thread), so its
sustained CPU-bound pandas/pyarrow work can never hold up the main server's
own GIL - a single large parquet decode can hold the GIL for minutes on its
own regardless of thread count (confirmed by live reproduction: reducing
_fetch_raw_daywise from 6 concurrent threads to 1 helped but did not fully
stop the whole platform from freezing for every user during a multi-month
day-wise run). Process isolation is the only fix that actually works,
because it gives this work its own separate interpreter/GIL.

The reindex functions this calls (_fetch_raw_*, reindex_*, run_reindex) do
not touch the database at all - confirmed by inspection - so there is no
SQLAlchemy session/connection-pool concern running them in a fresh process.

Usage: python reindex_worker.py <payload.json> <progress.json> <result.json>
Progress and the final result are written to those two files (atomically,
via write-to-temp + os.replace) rather than returned in-process, since the
parent (the web server) is a different OS process and cannot see this one's
memory.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # this dir, for `import scans`

import scans  # noqa: E402


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)  # atomic on both POSIX and Windows - the reader in
    # the parent process never sees a partially-written file, just the old
    # complete one or the new complete one.


class _WatchedProgress(dict):
    """Same dict interface _fetch_raw_monthwise/_fetch_raw_daywise already
    write to (progress["total"] = ..., progress["done"] += 1) - just flushes
    to disk on every write, since the parent process polls the file, not
    this process's memory."""
    def __init__(self, path, *a, **kw):
        super().__init__(*a, **kw)
        self._path = path

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        _atomic_write_json(self._path, dict(self))


def main():
    payload_path, progress_path, result_path = sys.argv[1:4]
    with open(payload_path, encoding="utf-8") as f:
        payload = json.load(f)

    progress = _WatchedProgress(progress_path, done=0, total=0)
    _atomic_write_json(progress_path, dict(progress))  # so a poll before the first file starts sees {0,0}, not nothing

    try:
        result = scans.run_reindex(payload, progress=progress)
    except Exception as e:  # belt-and-braces - run_reindex already catches its own errors
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    _atomic_write_json(result_path, result)


if __name__ == "__main__":
    main()
