"""DB check, rolled back: a cluster saved in another case is rewritten everywhere to the saved spelling.
Run: python calendar_engine/test_cluster_spelling.py   (from RS Planning Platform/backend)"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(_HERE, ".."), os.path.join(_HERE, "..", "..", "..", "Tentative AOP Forecaster")]
from sqlalchemy import text  # noqa: E402
from db.base import SessionLocal  # noqa: E402
from calendar_engine.router import adopt_cluster_spelling  # noqa: E402

Q = ("SELECT DISTINCT n FROM (SELECT name n FROM calendar.cluster_profiles UNION ALL "
     "SELECT cluster_name FROM calendar.store_calendar_clusters UNION ALL "
     "SELECT cluster_name FROM calendar.calendar_clusters UNION ALL "
     "SELECT cluster_name FROM calendar.calendar_day_pairs) t WHERE lower(n) = 'kashmir'")

with SessionLocal() as s:
    adopt_cluster_spelling(s, [" Kashmir "])
    assert [r[0] for r in s.execute(text(Q))] == ["Kashmir"]
    adopt_cluster_spelling(s, ["KASHMIR"])
    assert [r[0] for r in s.execute(text(Q))] == ["KASHMIR"]
    # Both spellings for the same key (unique index): the old-spelling duplicate goes, the save doesn't fail.
    FC = "SELECT count(*) FROM calendar.festival_changelog WHERE lower(cluster_name) = 'kashmir'"
    before = s.execute(text(FC)).scalar()
    if before:
        s.execute(text("INSERT INTO calendar.festival_changelog (range_key, cluster_name, festival_name, ref_date, fut_date, saved_at) "
                       "SELECT range_key, 'Kashmir', festival_name, ref_date, fut_date, saved_at FROM calendar.festival_changelog "
                       "WHERE cluster_name = 'KASHMIR' LIMIT 1"))
        adopt_cluster_spelling(s, ["KASHMIR"])
        assert s.execute(text(FC)).scalar() == before
    s.rollback()
# A cached reindex month must not survive a store -> cluster map change (a rename left 4 stores out, 2026-09-26).
from calendar_engine.scans import _calendar_fingerprint  # noqa: E402
dm = {"KASHMIR": [["2026-01-01", "2027-01-01"]]}
assert _calendar_fingerprint(dm, {"ANG": "Kashmir"}) != _calendar_fingerprint(dm, {"ANG": "KASHMIR"})
assert _calendar_fingerprint(dm, {"ANG": "KASHMIR"}) == _calendar_fingerprint(dm, {"ANG": "KASHMIR"})
print("cluster spelling checks passed")
