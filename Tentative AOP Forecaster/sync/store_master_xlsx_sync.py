"""
sync.sources['store_master_xlsx'] -> masterdata.stores (ref_store, cluster_key, tag)
                                   -> masterdata.clusters (business planning clusters)

Store Master.xlsx is hand-maintained by the planning team (Store Name, Ref Name -
Merch, CLUSTER, STORE TAG) — confirmed byte-for-byte identical to the "Store
Master" lever the AOP Forecaster reads today. It is NOT on the data lake's
automated pipeline, so this is run on demand (ttl_minutes=0) rather than
nightly, e.g. whenever the planning team updates the file.

Run manually: python sync/store_master_xlsx_sync.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import openpyxl
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.masterdata import Cluster
from db.models.sync import SyncSource
from db.upsert import upsert_store_fields
from sync.common import sync_run

SOURCE_KEY = "store_master_xlsx"


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def run():
    with sync_run(SOURCE_KEY) as (session, result):
        source = session.get(SyncSource, SOURCE_KEY)
        path = source.config["path"]

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(min_row=2, values_only=True))  # row 1 = header
        wb.close()
        result["rows_read"] = len(rows)

        as_of = datetime.date.today()
        clusters_seen = set()
        changed = 0
        for store_name, ref_name, cluster, store_tag in rows:
            store_id = _clean(store_name)
            if not store_id:
                continue
            cluster_key = _clean(cluster)
            if cluster_key:
                clusters_seen.add(cluster_key)
            changes = {"ref_store": _clean(ref_name), "cluster_key": cluster_key, "tag": _clean(store_tag)}
            if upsert_store_fields(session, store_id, changes, as_of):
                changed += 1

        if clusters_seen:
            stmt = pg_insert(Cluster).values(
                [{"cluster_key": c, "cluster_name": c} for c in clusters_seen]
            ).on_conflict_do_nothing(index_elements=["cluster_key"])
            session.execute(stmt)

        result["rows_updated"] = changed
        result["rows_added"] = 0
        result["detail"] = {"source_file": os.path.basename(path), "clusters_seen": len(clusters_seen)}


if __name__ == "__main__":
    run()
    print("store_master_xlsx_sync: done")
