"""Buyer's Input Sheet (otb-plan-app.html) -> SalesPlan's Department Growth
Matrix, live. BIS has no server of its own with DB access (its backend,
sync_server.py, is a plain static file server) - its browser JS pushes
growth% straight here after every save, the same way it already pulls AOP's
targets directly from this app's own /api/config/aop-division-targets.

Reuses planning_inputs.input_values exactly like publish_aop_targets.py's
aop_division_target lever: same table, same upsert pattern. Division and
department are packed into row_key (not division_code) for the same reason
aop_division_target sentinels division_code='' - this lever has no real FK
target in masterdata.divisions/departments either.
"""
from sqlalchemy import text

LEVER_KEY = "buyer_department_growth"

# mi -> period_id. Must stay in lockstep with otb-plan-app.html's own
# `periodOf`/`_PERIOD_TO_MI` (mi=11 is Mar'27, the stub anchor month before
# the FY starts; mi 0-10 are Apr'27..Feb'28 - BIS's plan cycle has no Mar'28
# slot at all, same as SalesPlan's Growth Matrix will simply never show a
# buyer value for it).
MI_TO_PERIOD = {
    11: 202703,
    0: 202704, 1: 202705, 2: 202706, 3: 202707, 4: 202708, 5: 202709,
    6: 202710, 7: 202711, 8: 202712, 9: 202801, 10: 202802,
}
PERIOD_TO_LABEL = {
    202703: "Mar'27", 202704: "Apr'27", 202705: "May'27", 202706: "Jun'27",
    202707: "Jul'27", 202708: "Aug'27", 202709: "Sep'27", 202710: "Oct'27",
    202711: "Nov'27", 202712: "Dec'27", 202801: "Jan'28", 202802: "Feb'28",
}


def _ensure_lever(session):
    session.execute(text("""
        INSERT INTO planning_inputs.lever_definitions (lever_key, label, required, shape)
        VALUES (:k, 'Buyer department growth % (live from Buyer''s Input Sheet)', false, 'named_row')
        ON CONFLICT (lever_key) DO NOTHING
    """), {"k": LEVER_KEY})


def upsert_buyer_growth(session, rows: list[dict]) -> int:
    """rows: [{division, department, mi, growth_pct}]. Silently skips any mi
    outside MI_TO_PERIOD (rather than raising) so one bad row never fails the
    whole save."""
    _ensure_lever(session)
    updated = 0
    for r in rows:
        period_id = MI_TO_PERIOD.get(r.get("mi"))
        if period_id is None:
            continue
        division = str(r.get("division", "")).strip().upper()
        department = str(r.get("department", "")).strip().upper()
        if not division or not department or r.get("growth_pct") is None:
            continue
        row_key = f"{division}|{department}"
        session.execute(text("""
            INSERT INTO planning_inputs.input_values
                (lever_key, store_id, division_code, period_id, row_key, value, source)
            VALUES (:lk, '', '', :pid, :rk, :val, 'buyer_input')
            ON CONFLICT ON CONSTRAINT uq_input_values_identity
            DO UPDATE SET value = EXCLUDED.value,
                          source = EXCLUDED.source,
                          updated_at = now()
        """), {"lk": LEVER_KEY, "pid": period_id, "rk": row_key, "val": r["growth_pct"]})
        updated += 1
    session.commit()
    return updated


def get_buyer_growth(session, division: str | None = None) -> list[dict]:
    """Returns [{division, department, period_id, month, growth_pct, updated_at}, ...]."""
    where = "WHERE lever_key = :lk"
    params: dict = {"lk": LEVER_KEY}
    if division:
        where += " AND row_key LIKE :prefix"
        params["prefix"] = f"{division.strip().upper()}|%"
    rows = session.execute(text(f"""
        SELECT row_key, period_id, value, updated_at
        FROM planning_inputs.input_values
        {where}
        ORDER BY row_key, period_id
    """), params).all()
    out = []
    for row_key, period_id, value, updated_at in rows:
        div, _, dept = row_key.partition("|")
        month = PERIOD_TO_LABEL.get(period_id)
        if month is None or value is None:
            continue
        out.append({
            "division": div, "department": dept, "period_id": period_id,
            "month": month, "growth_pct": float(value),
            "updated_at": updated_at.isoformat() if updated_at else None,
        })
    return out
