"""
sync.sources['data_lake_site_master'] -> masterdata.stores (operational fields only)

Enriches stores with ERP/operational attributes from the daily site_master
snapshot: status, grade, festival grouping, region, opening date, and the ERP
CLUSTER_TYPE (kept separate from the business planning Cluster, which comes
from Store Master.xlsx — see db/models/masterdata.py). Never touches
ref_store / cluster_key / tag, which that other source owns.

Run manually: python sync/site_master_sync.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from db.models.sync import SyncSource
from db.upsert import upsert_store_fields
from sync.common import latest_file, sync_run

SOURCE_KEY = "data_lake_site_master"

COLUMNS = [
    "STORE_NAME", "STORE_STATUS", "STORE_CURRENT_STATUS", "CLUSTER_TYPE",
    "STORE_GRADE", "GM_GRADE", "FESTIVAL_GROUPING", "REGION_TYPE", "OPENING_DATE",
]


def _blank_to_none(v):
    return None if v is None or (isinstance(v, str) and v.strip() in ("", "-")) else v


def run():
    with sync_run(SOURCE_KEY) as (session, result):
        source = session.get(SyncSource, SOURCE_KEY)
        path = latest_file(source.config["path"])

        df = pd.read_parquet(path, columns=COLUMNS)
        df = df.dropna(subset=["STORE_NAME"])
        result["rows_read"] = len(df)

        # site_master has occasional duplicate STORE_NAME rows for inactive
        # placeholder codes (e.g. "JGRxx" at two different SITE_CODEs, both
        # IN-ACTIVE) — STORE_NAME is our store identity key, so dedupe and
        # surface the count rather than fail the whole sync.
        dupe_mask = df.duplicated(subset=["STORE_NAME"], keep="last")
        dropped_duplicates = sorted(df.loc[dupe_mask, "STORE_NAME"].unique().tolist())
        df = df[~dupe_mask]

        as_of = datetime.date.today()
        changed = 0
        for row in df.itertuples():
            store_id = str(row.STORE_NAME).strip()
            opening_date = row.OPENING_DATE.date() if pd.notna(row.OPENING_DATE) else None
            changes = {
                "store_name": store_id,
                "store_status": _blank_to_none(row.STORE_STATUS),
                "store_current_status": _blank_to_none(row.STORE_CURRENT_STATUS),
                "erp_cluster_type": _blank_to_none(row.CLUSTER_TYPE),
                "store_grade": _blank_to_none(row.STORE_GRADE),
                "gm_grade": _blank_to_none(row.GM_GRADE),
                "festival_grouping": _blank_to_none(row.FESTIVAL_GROUPING),
                "region_type": _blank_to_none(row.REGION_TYPE),
                "opening_date": opening_date,
            }
            if upsert_store_fields(session, store_id, changes, as_of):
                changed += 1

        result["rows_updated"] = changed
        result["rows_added"] = 0
        result["detail"] = {"source_file": os.path.basename(path), "duplicate_store_names_dropped": dropped_duplicates}


if __name__ == "__main__":
    run()
    print("site_master_sync: done")
