import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "Tentative AOP Forecaster"))

from sqlalchemy import select

from calendar_engine.migrate_from_json import run
from db.base import SessionLocal
from db.models.calendar import StoreCalendarCluster, FestivalChangelogEntry


def test_migration_imports_all_223_stores_and_6_changelog_ranges():
    summary = run()
    assert summary["store_cluster_map"]["rows"] == 223
    assert summary["festival_changelog"]["rows"] >= 6  # at least the 6 range_keys seen this session; each may have multiple cluster/festival rows

    session = SessionLocal()
    try:
        aac = session.execute(select(StoreCalendarCluster).where(StoreCalendarCluster.store_id == "AAC")).scalar_one()
        assert aac.cluster_name == "JH + MP + CG"

        range_keys = {r[0] for r in session.execute(select(FestivalChangelogEntry.range_key)).all()}
        assert "2025-2026" in range_keys
        assert "2004-2027" in range_keys
    finally:
        session.close()
