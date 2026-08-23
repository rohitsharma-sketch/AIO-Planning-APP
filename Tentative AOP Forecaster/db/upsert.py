"""
Effective-dated upsert for masterdata.stores: a change never overwrites the
current row in place. It closes the current row's valid_to and inserts a new
row with the merged fields, so store history (cluster/status/tag changes over
time) stays queryable.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.masterdata import Store

TRACKED_FIELDS = [
    "store_name", "ref_store", "cluster_key", "erp_cluster_type", "store_status",
    "store_current_status", "store_grade", "gm_grade", "festival_grouping",
    "region_type", "opening_date", "tag",
]


def upsert_store_fields(session: Session, store_id: str, changes: dict, as_of: datetime.date):
    """changes: subset of TRACKED_FIELDS this sync source owns. Fields not in
    `changes` are carried forward unchanged from the current row, if any."""
    current = session.execute(
        select(Store).where(Store.store_id == store_id, Store.valid_to.is_(None))
    ).scalar_one_or_none()

    merged = {f: getattr(current, f) for f in TRACKED_FIELDS} if current else {f: None for f in TRACKED_FIELDS}
    merged.update({k: v for k, v in changes.items() if k in TRACKED_FIELDS})

    if current and all(getattr(current, f) == merged[f] for f in TRACKED_FIELDS):
        return False  # no actual change — leave the current row alone

    if current and current.valid_from == as_of:
        # already superseded once today by an earlier source in the same sync run — update in place
        for f, v in merged.items():
            setattr(current, f, v)
        return True

    if current:
        current.valid_to = as_of
    session.add(Store(store_id=store_id, valid_from=as_of, valid_to=None, **merged))
    return True
