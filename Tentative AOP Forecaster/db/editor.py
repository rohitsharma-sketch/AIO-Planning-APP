"""
Read/write for the three planner-maintained levers that have no automated
sync source: Growth %, NSO Opening Months (incl. Named NSO), AOP overrides.
Backs the /api/config/growth, /api/config/nso, /api/config/aop-overrides
endpoints in app.py — the replacement for the removed LeverEditor.jsx, now
writing directly to Postgres instead of levers.json.

Conventions match db/to_workbook.py and db/migrate_manual_levers.py exactly:
month labels are "Mon'YY" (e.g. "Apr'27"), growth rate is a plain percent
number (6.0 means 6%, not 0.06), row_key/store_id/division_code use '' as
the "not applicable" sentinel (never NULL — see db/models/planning_inputs.py
for why: a nullable identity column silently breaks ON CONFLICT dedup).
"""
import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from db.models.audit import DataChange
from db.models.masterdata import NsoOpening, Store
from db.models.planning_inputs import InputValue, Period


def log_change(session, table_name, record_key, old_value, new_value, actor_id, actor_role, plan_cycle_id=None):
    """Every Growth %/NSO/AOP edit, old -> new, who and when. See
    docs/superpowers/specs/2026-08-22-...-design.md 'Audit trail'."""
    session.add(DataChange(
        table_name=table_name, record_key=record_key,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        actor_id=actor_id, actor_role=actor_role, plan_cycle_id=plan_cycle_id,
    ))

FY28_GROWTH_M = ["Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                 "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"]
FY28_AOP_M = ["Mar'27"] + FY28_GROWTH_M
DIVS = ["GM", "KIDS", "LADIES", "MENS", "RETAIL"]
ROW_KEYS = ["OVERALL"] + DIVS
MON = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
       "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def _label_to_period_id(label: str) -> int:
    mon, yy = label.split("'")
    return (2000 + int(yy)) * 100 + MON[mon]


def _period_ids(session: Session) -> dict:
    return {p.label: p.period_id for p in session.execute(select(Period)).scalars().all()}


# ── Growth % ──────────────────────────────────────────────────────────────────
def get_growth(session: Session) -> dict:
    rows = session.execute(select(InputValue).where(InputValue.lever_key == "growth_pct")).scalars().all()
    periods = _period_ids(session)
    label_by_id = {v: k for k, v in periods.items()}
    grid = {rk: {} for rk in ROW_KEYS}
    for v in rows:
        label = label_by_id.get(v.period_id)
        if v.row_key in grid and label in FY28_GROWTH_M:
            grid[v.row_key][label] = float(v.value)
    return {"months": FY28_GROWTH_M, "rows": [{"row_key": rk, "values": grid[rk]} for rk in ROW_KEYS]}


def put_growth(session: Session, rows: list, actor_id, actor_role: str) -> dict:
    """rows: [{"row_key": "OVERALL"|division, "values": {month: rate_or_null}}]"""
    periods = _period_ids(session)
    upsert_rows, delete_ids = [], []
    existing_full = {
        (v.row_key, v.period_id): v
        for v in session.execute(select(InputValue).where(InputValue.lever_key == "growth_pct")).scalars().all()
    }
    existing = {k: v.id for k, v in existing_full.items()}
    for row in rows:
        rk = row.get("row_key")
        if rk not in ROW_KEYS:
            continue
        for label, val in (row.get("values") or {}).items():
            if label not in FY28_GROWTH_M or label not in periods:
                continue
            pid = periods[label]
            current = existing_full.get((rk, pid))
            current_val = str(float(current.value)) if current else None
            record_key = {"lever_key": "growth_pct", "row_key": rk, "period_id": pid}
            if val is None or val == "":
                if (rk, pid) in existing:
                    delete_ids.append(existing[(rk, pid)])
                    log_change(session, "planning_inputs.input_values", record_key, current_val, None, actor_id, actor_role)
                continue
            if current_val != str(float(val)):
                log_change(session, "planning_inputs.input_values", record_key, current_val, float(val), actor_id, actor_role)
            upsert_rows.append({
                "lever_key": "growth_pct", "store_id": "", "division_code": "", "period_id": pid,
                "row_key": rk, "value": float(val), "source": "manual",
            })
    if delete_ids:
        session.query(InputValue).filter(InputValue.id.in_(delete_ids)).delete(synchronize_session=False)
    if upsert_rows:
        stmt = pg_insert(InputValue).values(upsert_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["lever_key", "store_id", "division_code", "period_id", "row_key"],
            set_={"value": stmt.excluded.value, "source": stmt.excluded.source,
                  "updated_at": datetime.datetime.now(datetime.timezone.utc)},
        )
        session.execute(stmt)
    session.commit()
    return get_growth(session)


# ── NSO Opening Months (unnamed + named) ─────────────────────────────────────
def get_nso(session: Session) -> list:
    rows = session.execute(select(NsoOpening)).scalars().all()
    return sorted([
        {"store_id": n.store_id, "opening_month": _period_label(n.opening_month), "is_named": n.is_named}
        for n in rows
    ], key=lambda r: r["store_id"])


def _period_label(d: datetime.date) -> str:
    names = {v: k for k, v in MON.items()}
    return f"{names[d.month]}'{d.year % 100:02d}"


def put_nso(session: Session, rows: list, actor_id, actor_role: str) -> list:
    """rows: [{"store_id", "opening_month" ("Mon'YY"), "is_named"}]. A store_id
    present in the DB but absent from `rows` is deleted (this is the full,
    authoritative list, mirroring how the old NSO Opening Months / Named NSO
    sheets were edited as complete tables, not deltas)."""
    existing_rows = {n.store_id: n for n in session.execute(select(NsoOpening)).scalars().all()}
    keep_ids = set()
    for row in rows:
        sid = (row.get("store_id") or "").strip()
        label = row.get("opening_month")
        if not sid or not label or "'" not in label:
            continue
        mon, yy = label.split("'")
        if mon not in MON:
            continue
        opening = datetime.date(2000 + int(yy), MON[mon], 1)
        keep_ids.add(sid)

        prev = existing_rows.get(sid)
        old = f"{prev.opening_month.isoformat()}|{prev.is_named}" if prev else None
        new = f"{opening.isoformat()}|{bool(row.get('is_named'))}"
        if old != new:
            log_change(session, "masterdata.nso_openings", {"store_id": sid}, old, new, actor_id, actor_role)

        stmt = pg_insert(NsoOpening).values(
            store_id=sid, opening_month=opening, is_named=bool(row.get("is_named")), source="manual",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["store_id"],
            set_={"opening_month": stmt.excluded.opening_month, "is_named": stmt.excluded.is_named,
                  "source": stmt.excluded.source},
        )
        session.execute(stmt)

    to_delete = set(existing_rows) - keep_ids
    for sid in to_delete:
        prev = existing_rows[sid]
        old = f"{prev.opening_month.isoformat()}|{prev.is_named}"
        log_change(session, "masterdata.nso_openings", {"store_id": sid}, old, None, actor_id, actor_role)
    if to_delete:
        session.query(NsoOpening).filter(NsoOpening.store_id.in_(to_delete)).delete(synchronize_session=False)
    session.commit()
    return get_nso(session)


# ── AOP (Optional) overrides ──────────────────────────────────────────────────
def get_aop_overrides(session: Session) -> list:
    rows = session.execute(select(InputValue).where(InputValue.lever_key == "aop_optional")).scalars().all()
    periods = _period_ids(session)
    label_by_id = {v: k for k, v in periods.items()}
    return sorted([
        {"store_id": v.store_id, "division": v.division_code, "month": label_by_id.get(v.period_id), "value": float(v.value)}
        for v in rows if label_by_id.get(v.period_id) in FY28_AOP_M
    ], key=lambda r: (r["store_id"], r["division"], r["month"]))


def put_aop_overrides(session: Session, rows: list, actor_id, actor_role: str) -> list:
    """rows: [{"store_id", "division", "month", "value"}] — sparse; a row with
    value None/'' deletes that override (falls back to the engine's own
    computed forecast for that cell). Unlisted existing overrides are left
    untouched (this is a delta editor, unlike NSO's full-table replace, since
    AOP overrides are sparse by nature — most store/division/month cells have
    no override at all)."""
    periods = _period_ids(session)
    stores = {s.store_id for s in session.execute(select(Store)).scalars().all()}
    existing_values = {
        (v.store_id, v.division_code, v.period_id): str(float(v.value))
        for v in session.execute(select(InputValue).where(InputValue.lever_key == "aop_optional")).scalars().all()
    }
    upsert_rows, delete_keys = [], []
    for row in rows:
        sid = (row.get("store_id") or "").strip()
        div = (row.get("division") or "").strip().upper()
        label = row.get("month")
        if not sid or div not in DIVS or label not in FY28_AOP_M or label not in periods:
            continue
        if sid not in stores:
            continue  # unknown store — refuse rather than write an orphan override
        val = row.get("value")
        pid = periods[label]
        current_val = existing_values.get((sid, div, pid))
        record_key = {"lever_key": "aop_optional", "store_id": sid, "division_code": div, "period_id": pid}
        if val is None or val == "":
            if current_val is not None:
                log_change(session, "planning_inputs.input_values", record_key, current_val, None, actor_id, actor_role)
            delete_keys.append((sid, div, pid))
            continue
        if current_val != str(float(val)):
            log_change(session, "planning_inputs.input_values", record_key, current_val, float(val), actor_id, actor_role)
        upsert_rows.append({
            "lever_key": "aop_optional", "store_id": sid, "division_code": div, "period_id": pid,
            "row_key": "", "value": float(val), "source": "manual",
        })
    if delete_keys:
        for sid, div, pid in delete_keys:
            session.query(InputValue).filter(
                InputValue.lever_key == "aop_optional", InputValue.store_id == sid,
                InputValue.division_code == div, InputValue.period_id == pid,
            ).delete(synchronize_session=False)
    if upsert_rows:
        stmt = pg_insert(InputValue).values(upsert_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["lever_key", "store_id", "division_code", "period_id", "row_key"],
            set_={"value": stmt.excluded.value, "source": stmt.excluded.source,
                  "updated_at": datetime.datetime.now(datetime.timezone.utc)},
        )
        session.execute(stmt)
    session.commit()
    return get_aop_overrides(session)
