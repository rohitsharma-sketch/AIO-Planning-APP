"""Standalone subprocess worker for the "Link Sales Data Source" scan - see
start_link_scan_job() in scans.py. Same reasoning as reindex_worker.py: this
scan reads real columns out of every parquet file in the source directory
(day-wise: 86M+ rows across 6 files), in the same request-handling process as
before this existed it would have carried the exact same GIL-starvation risk
that was proven to freeze the whole platform for every user during Run
Reindex. Isolating it into its own OS process fixes that the same way.

Usage: python link_scan_worker.py <mw|dw> <force_refresh 0|1> <progress.json> <result.json>
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
    os.replace(tmp, path)


class _WatchedProgress(dict):
    def __init__(self, path, *a, **kw):
        super().__init__(*a, **kw)
        self._path = path

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        _atomic_write_json(self._path, dict(self))


def main():
    source_type, force_refresh_str, progress_path, result_path = sys.argv[1:5]
    force_refresh = force_refresh_str == "1"

    progress = _WatchedProgress(progress_path, done=0, total=0)
    _atomic_write_json(progress_path, dict(progress))

    try:
        if source_type == "dw":
            result = scans.get_salesdata_link_daywise(force_refresh=force_refresh, progress=progress)
        else:
            result = scans.get_salesdata_link(force_refresh=force_refresh, progress=progress)
    except Exception as e:  # belt-and-braces - get_salesdata_link* already catch their own errors
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    _atomic_write_json(result_path, result)


if __name__ == "__main__":
    main()
