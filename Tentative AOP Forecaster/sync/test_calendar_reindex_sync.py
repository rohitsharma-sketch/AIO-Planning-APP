"""No-DB check: an unreachable source (0 rows read for every fresh month) skips
the MW snapshot save and the sync records it as 'offline'; a snapshot-save
failure is no longer swallowed. Run: python sync/test_calendar_reindex_sync.py"""
import contextlib
import datetime
import json
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "RS Planning Platform", "backend", "calendar_engine"))

import scans  # noqa: E402
import sync.calendar_reindex_sync as crs  # noqa: E402
from sync.common import _is_network_offline  # noqa: E402

# --- run_reindex: skip save when nothing was read, surface save errors ---
saved = []
scans._cached_months_status = lambda *a: {}
scans._get_raw = lambda *a, **k: None
scans._save_month_cache = lambda *a: None
rows_read = {"n": 0}
scans.reindex_monthwise = lambda **k: {"ok": True, "source": "mw", "keyFields": ["store"], "grain": "store",
                                       "metric": "SL_V", "rows": [], "actualRows": [], "columns": [],
                                       "actualColumns": [], "rowsRead": rows_read["n"], "rowsMapped": 0}
scans._save_calendarised_sales_snapshot = lambda r, suffix="": saved.append(r) or None
payload = {"source": "mw", "months": ["2026-08", "2026-09"], "dayMap": {"C": [["2026-08-01", "2027-08-01"]]},
           "persistSnapshot": True}   # as the sync jobs send it

r = scans.run_reindex(payload)
assert r.get("sourceUnreachable") is True and saved == [], (r, saved)

rows_read["n"] = 5
scans._save_calendarised_sales_snapshot = lambda r, suffix="": "OperationalError: boom"
r = scans.run_reindex(payload)
assert r.get("snapshotSaveError") == "OperationalError: boom" and "sourceUnreachable" not in r, r

# a what-if run from the page (no persistSnapshot) never replaces the shared snapshot (audit 2026-10-06)
scans._save_calendarised_sales_snapshot = lambda r, suffix="": saved.append(r) or None
r = scans.run_reindex({k: v for k, v in payload.items() if k != "persistSnapshot"})
assert r.get("ok") and saved == [], (r, saved)

# --- calendar_reindex_sync.run(): raises an error sync_run records as 'offline' ---
_obj = types.SimpleNamespace


class _Q:
    def __init__(self, v):
        self.v = v

    def scalars(self):
        return self

    def first(self):
        return self.v[0]

    def all(self):
        return self.v


class _Session:
    def __init__(self):
        cal = _obj(calendar_id=1, name="cal")
        pair = _obj(cluster_name="C", ref_date=datetime.date(2026, 8, 1), fut_date=datetime.date(2027, 8, 1))
        self.q = [[cal], [pair], [("S1", "C")]]

    def execute(self, stmt):
        return _Q(self.q.pop(0))


@contextlib.contextmanager
def _fake_sync_run(key):
    yield _Session(), {}


def _fake_subprocess_run(argv, **kw):
    with open(argv[4], "w", encoding="utf-8") as f:
        json.dump({"ok": True, "sourceUnreachable": True, "computedMonths": ["2026-09"]}, f)
    return _obj(returncode=0, stderr="", stdout="")


crs.sync_run = _fake_sync_run
crs.subprocess.run = _fake_subprocess_run
try:
    crs.run()
    raise AssertionError("run() should have raised")
except ConnectionError as e:
    assert _is_network_offline(e), e
print("test_calendar_reindex_sync: OK")
