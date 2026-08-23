"""
sync.sources['data_lake_day_shift'] -> calendar.day_shift_map

Straight 1:1 copy of the day_shifting_calender parquet (CURRENT_DATE,
LY_MAPPED_DATE) — a full replace each run since the source is small (455 rows)
and always ships as a complete snapshot, not a delta.

Run manually: python sync/day_shift_sync.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from sqlalchemy import delete

from db.models.calendar import DayShiftMap
from db.models.sync import SyncSource
from sync.common import latest_file, sync_run

SOURCE_KEY = "data_lake_day_shift"


def run():
    with sync_run(SOURCE_KEY) as (session, result):
        source = session.get(SyncSource, SOURCE_KEY)
        path = latest_file(source.config["path"])

        df = pd.read_parquet(path, columns=["CURRENT_DATE", "LY_MAPPED_DATE"])
        df = df.dropna(subset=["CURRENT_DATE", "LY_MAPPED_DATE"])
        result["rows_read"] = len(df)

        session.execute(delete(DayShiftMap))
        session.bulk_save_objects([
            DayShiftMap(current_date=row.CURRENT_DATE.date(), ly_mapped_date=row.LY_MAPPED_DATE.date())
            for row in df.itertuples()
        ])
        result["rows_updated"] = len(df)
        result["rows_added"] = 0
        result["detail"] = {"source_file": os.path.basename(path)}


if __name__ == "__main__":
    run()
    print("day_shift_sync: done")
