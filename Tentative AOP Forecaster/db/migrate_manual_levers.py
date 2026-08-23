"""
One-time migration of the planner-entered levers that have no sync source
(Growth %, NSO Opening Months, Named NSO, AOP overrides) from the current
config/levers.json into Postgres. Store Master / Store Actuals / masterdata
already come from the sync jobs — this fills in the rest so a DB-only run
has the exact same data as the current file-based one.

Run manually: python db/migrate_manual_levers.py
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

import config_store as cfg
from db.base import SessionLocal
from db.models.masterdata import NsoOpening
from db.models.planning_inputs import InputValue, Period

DIVS = {"GM", "KIDS", "LADIES", "MENS", "RETAIL"}
MON = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
       "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _label_to_date(label):
    """"Mar'27" -> date(2027, 3, 1)."""
    mon, yy = label.split("'")
    return datetime.date(2000 + int(yy), MON[mon], 1)


def _lever(c, key):
    return next(l for l in c["levers"] if l["key"] == key)


def main():
    c = cfg.load_config()
    session = SessionLocal()
    period_ids = {p.label: p.period_id for p in session.execute(select(Period)).scalars().all()}

    input_rows = []

    # Growth % — row_key = division or OVERALL, skip the "HOW IT WORKS" note rows
    growth = _lever(c, "growth_pct")
    for row in growth["rows"]:
        head = str(row[0]).strip().upper() if row[0] else ""
        if head not in DIVS and head != "OVERALL":
            continue
        for label, val in zip(growth["columns"][1:], row[1:]):
            if val is None or label not in period_ids:
                continue
            input_rows.append({"lever_key": "growth_pct", "store_id": "", "division_code": "",
                               "period_id": period_ids[label], "row_key": head, "value": float(val),
                               "source": "manual_import"})

    # AOP (Optional) — store x division x FY28 month
    aop = _lever(c, "aop_optional")
    for row in aop["rows"]:
        store, div = row[0], (row[1] or "").strip().upper()
        if not store or div not in DIVS:
            continue
        for label, val in zip(aop["columns"][2:], row[2:]):
            if val is None or label not in period_ids:
                continue
            input_rows.append({"lever_key": "aop_optional", "store_id": str(store).strip(), "division_code": div,
                               "period_id": period_ids[label], "row_key": "", "value": float(val),
                               "source": "manual_import"})

    if input_rows:
        stmt = pg_insert(InputValue).values(input_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["lever_key", "store_id", "division_code", "period_id", "row_key"],
            set_={"value": stmt.excluded.value, "source": stmt.excluded.source},
        )
        session.execute(stmt)

    # NSO Opening Months (unnamed) + Named NSO (Optional) -> masterdata.nso_openings
    nso_rows = []
    nso = _lever(c, "nso_opening_months")
    iS, iO = cfg._col(nso, "Store Code", "Store"), cfg._col(nso, "Opening Month")
    for row in nso["rows"]:
        store, opening = cfg._get(row, iS), cfg._get(row, iO)
        if store and opening:
            nso_rows.append({"store_id": str(store).strip(), "opening_month": _label_to_date(opening),
                             "is_named": False, "source": "manual_import"})

    named = _lever(c, "named_nso_optional")
    iS2, iO2 = cfg._col(named, "Store"), cfg._col(named, "Opening Month")
    for row in named["rows"]:
        store, opening = cfg._get(row, iS2), cfg._get(row, iO2)
        if store and opening:
            nso_rows.append({"store_id": str(store).strip(), "opening_month": _label_to_date(opening),
                             "is_named": True, "source": "manual_import"})

    if nso_rows:
        stmt = pg_insert(NsoOpening).values(nso_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["store_id"],
            set_={"opening_month": stmt.excluded.opening_month, "is_named": stmt.excluded.is_named,
                  "source": stmt.excluded.source},
        )
        session.execute(stmt)

    session.commit()
    print(f"Migrated {len(input_rows)} growth/AOP input_values rows, {len(nso_rows)} nso_openings rows.")
    session.close()


if __name__ == "__main__":
    main()
