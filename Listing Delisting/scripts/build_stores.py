"""app/stores.json - the RS Planning store master for the Listing/Delisting app
(2026-09-26): name, planning cluster, LfL / Ramp / NSO class, opening date and current
status per store code, straight from the planning DB (masterdata.stores), with the SAME
LfL rule the AOP Forecaster uses (engine_v3.auto_tag - December cut-off). STORE_NAME in
the listing KB is the store code, so it joins 1:1 (280 of 281 on 2026-09-26).

Run: python scripts/build_stores.py          (the daily sync runs it too)
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import BASE, planning_session  # noqa: E402


def build():
    from sqlalchemy import text
    with planning_session() as s:            # also puts the AOP Forecaster on sys.path
        from engine_v3 import LFL_TAGS, NSO_TAGS, RAMP_TAGS, auto_tag
        rows = s.execute(text(
            "SELECT store_id, store_name, cluster_key, tag, opening_date, store_current_status "
            "FROM masterdata.stores WHERE valid_to IS NULL")).all()
    stores = {}
    for code, name, cluster, tag, opened, status in rows:
        t = auto_tag(tag, opened, status) if tag else None
        kind = "LfL" if t in LFL_TAGS else "Ramp" if t in RAMP_TAGS else "NSO" if t in NSO_TAGS else None
        real_date = opened and opened > datetime.date(2000, 1, 1)      # 2000-01-01 = placeholder for upcoming sites
        stores[code] = {k: v for k, v in {
            "name": (name or "").strip() or None, "cluster": cluster, "type": kind,
            "opened": opened.isoformat() if real_date else None,
            "status": (status or "").title() or None}.items() if v}
    out = {"built_at": datetime.datetime.now().isoformat(timespec="seconds"), "stores": stores}
    path = os.path.join(BASE, "app", "stores.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    return len(stores)


if __name__ == "__main__":
    print(f"stores.json: {build()} stores")
