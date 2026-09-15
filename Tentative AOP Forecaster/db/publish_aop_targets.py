"""
After every AOP forecast run, publish MENS/LADIES/KIDS MAMJ (Mar–Jun'27)
LFL-only division-level totals to planning_inputs.input_values so the
Buyer's Input Sheet can auto-populate its AOP targets.

Only LFL stores are included — BIS LY actuals are also LFL-only (148
stores), so comparing AOP vs LY in BIS is apples-to-apples.

Keying convention (avoids FK issues on masterdata.divisions):
  lever_key  = 'aop_division_target'
  store_id   = ''             (not a store-level measure)
  division_code = ''          (sentinel; FK satisfied by the '' row in masterdata.divisions)
  period_id  = 202703 … 202706
  row_key    = 'MENS' / 'LADIES' / 'KIDS'
  value      = Rs Lakhs       (system-wide unit; frontend converts ÷100 → Rs Cr)
  source     = 'aop_forecaster'

Every publish is recorded in planning_inputs.aop_publish_history so the
Planning Engine can show a version picker and promote any past run.
"""
import json
from sqlalchemy import text

LEVER_KEY = "aop_division_target"
PUBLISH_DIVS = {"MENS", "LADIES", "KIDS"}
MAMJ = {
    "Mar'27": 202703,
    "Apr'27": 202704,
    "May'27": 202705,
    "Jun'27": 202706,
}

# Must match engine_v3.LFL_TAGS exactly so the published totals agree
# with what the AOP Results dashboard shows as the LfL sub-total.
LFL_TAGS = {
    "032 - Stores", "080 - Stores", "095 - Stores", "125 - Stores",
    "3 - Stores", "FY26 - Q1", "FY26 - Q2", "FY26 - Q3",
    "LFL", "lfl",
}


def _ensure_history_table(session) -> None:
    """Create aop_publish_history if it doesn't exist yet (auto-migration)."""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS planning_inputs.aop_publish_history (
            id              SERIAL PRIMARY KEY,
            session_id      TEXT,
            published_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            division_totals JSONB       NOT NULL,
            total_mamj_lakhs NUMERIC(12,2)
        )
    """))


def publish_aop_targets(session, detail_records: list[dict], session_id: str = None) -> None:
    """Upsert MENS/LADIES/KIDS × MAMJ LFL forecast totals to planning_inputs.input_values.
    Also records a row in aop_publish_history so the Planning Engine can pick
    any past version to promote.  Idempotent: safe to call after every run."""
    # Ensure the lever definition row exists (FK parent for input_values.lever_key)
    session.execute(text("""
        INSERT INTO planning_inputs.lever_definitions (lever_key, label, required, shape)
        VALUES (:k, 'AOP Division Target (live from Forecaster)', false, 'named_row')
        ON CONFLICT (lever_key) DO NOTHING
    """), {"k": LEVER_KEY})

    # Aggregate LFL-only forecast totals: {(row_key, period_id): total_lakhs}
    totals: dict[tuple[str, int], float] = {}
    for rec in detail_records:
        if rec.get("Tag") not in LFL_TAGS:
            continue  # skip NSO and Ramp stores
        div = (rec.get("Division") or "").strip().upper()
        if div not in PUBLISH_DIVS:
            continue
        for month_label, period_id in MAMJ.items():
            val = rec.get(f"{month_label} | Forecast") or 0.0
            key = (div, period_id)
            totals[key] = totals.get(key, 0.0) + float(val)

    if not totals:
        return

    for (div, period_id), total in totals.items():
        session.execute(text("""
            INSERT INTO planning_inputs.input_values
                (lever_key, store_id, division_code, period_id, row_key, value, source)
            VALUES (:lk, '', '', :pid, :rk, :val, 'aop_forecaster')
            ON CONFLICT ON CONSTRAINT uq_input_values_identity
            DO UPDATE SET value = EXCLUDED.value,
                          source = EXCLUDED.source,
                          updated_at = now()
        """), {"lk": LEVER_KEY, "pid": period_id, "rk": div, "val": total})

    session.commit()

    # Record this publish in the history table (non-fatal if it fails)
    try:
        _ensure_history_table(session)
        # Build {div: {period_id_str: lakhs}} for JSONB storage
        div_totals: dict[str, dict[str, float]] = {}
        for (div, pid), val in totals.items():
            div_totals.setdefault(div, {})[str(pid)] = round(val, 2)
        total_mamj = round(sum(totals.values()), 2)
        session.execute(text("""
            INSERT INTO planning_inputs.aop_publish_history
                (session_id, division_totals, total_mamj_lakhs)
            VALUES (:sid, :dt::jsonb, :total)
        """), {"sid": session_id, "dt": json.dumps(div_totals), "total": total_mamj})
        session.commit()
    except Exception:
        session.rollback()


LOCKED_LEVER_KEY = "aop_locked_target"


def _seed_history_from_staging(session) -> bool:
    """One-time backfill: read the current aop_division_target rows from
    input_values and write them into aop_publish_history so the version picker
    has something to show before the next forecast run.
    Returns True if a row was inserted."""
    rows = session.execute(text("""
        SELECT row_key, period_id, value, updated_at
        FROM planning_inputs.input_values
        WHERE lever_key = :lk
          AND row_key   IN ('MENS','LADIES','KIDS')
          AND period_id IN (202703,202704,202705,202706)
        ORDER BY row_key, period_id
    """), {"lk": LEVER_KEY}).fetchall()

    if not rows:
        return False

    div_totals: dict[str, dict[str, float]] = {}
    latest_ts = None
    for div, pid, value, updated_at in rows:
        div_totals.setdefault(div, {})[str(pid)] = round(float(value or 0), 2)
        if latest_ts is None or (updated_at and updated_at > latest_ts):
            latest_ts = updated_at

    total_mamj = round(sum(v for d in div_totals.values() for v in d.values()), 2)

    session.execute(text("""
        INSERT INTO planning_inputs.aop_publish_history
            (session_id, published_at, division_totals, total_mamj_lakhs)
        VALUES ('backfill', :ts, :dt::jsonb, :total)
    """), {
        "ts": latest_ts,
        "dt": json.dumps(div_totals),
        "total": total_mamj,
    })
    session.commit()
    return True


def list_aop_history(session, limit: int = 20) -> list[dict]:
    """Return the most recent AOP publish history entries, newest first.
    On first call (empty table), auto-seeds from current staging data so the
    version picker is immediately useful without requiring a new forecast run."""
    try:
        _ensure_history_table(session)
        rows = session.execute(text("""
            SELECT id, session_id, published_at, division_totals, total_mamj_lakhs
            FROM planning_inputs.aop_publish_history
            ORDER BY published_at DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()

        if not rows:
            # Auto-seed from staging if history is empty (one-time backfill)
            if _seed_history_from_staging(session):
                rows = session.execute(text("""
                    SELECT id, session_id, published_at, division_totals, total_mamj_lakhs
                    FROM planning_inputs.aop_publish_history
                    ORDER BY published_at DESC
                    LIMIT :lim
                """), {"lim": limit}).fetchall()

        return [
            {
                "id": r[0],
                "session_id": r[1],
                "published_at": r[2].isoformat() if r[2] else None,
                "division_totals": r[3],
                "total_mamj_lakhs": float(r[4]) if r[4] is not None else 0.0,
            }
            for r in rows
        ]
    except Exception:
        return []


def promote_from_history(session, version_id: int) -> dict:
    """Promote a specific historical AOP publish to aop_locked_target.
    The Planning Engine reads aop_locked_target as its stable approved version."""
    try:
        _ensure_history_table(session)
    except Exception:
        pass

    row = session.execute(text("""
        SELECT division_totals, total_mamj_lakhs, published_at
        FROM planning_inputs.aop_publish_history
        WHERE id = :id
    """), {"id": version_id}).fetchone()

    if not row:
        return {"ok": False, "reason": f"Version {version_id} not found in publish history."}

    division_totals, total_mamj, published_at = row

    session.execute(text("""
        INSERT INTO planning_inputs.lever_definitions (lever_key, label, required, shape)
        VALUES (:k, 'AOP Division Target (locked for Planning Engine)', false, 'named_row')
        ON CONFLICT (lever_key) DO NOTHING
    """), {"k": LOCKED_LEVER_KEY})

    locked_count = 0
    for div, periods in division_totals.items():
        for pid_str, value in periods.items():
            session.execute(text("""
                INSERT INTO planning_inputs.input_values
                    (lever_key, store_id, division_code, period_id, row_key, value, source)
                VALUES (:lk, '', '', :pid, :rk, :val, 'aop_history')
                ON CONFLICT ON CONSTRAINT uq_input_values_identity
                DO UPDATE SET value = EXCLUDED.value,
                              source = EXCLUDED.source,
                              updated_at = now()
            """), {"lk": LOCKED_LEVER_KEY, "pid": int(pid_str), "rk": div, "val": float(value)})
            locked_count += 1

    session.commit()
    return {
        "ok": True,
        "version_id": version_id,
        "locked_rows": locked_count,
        "total_mamj_lakhs": float(total_mamj) if total_mamj is not None else 0.0,
        "original_published_at": published_at.isoformat() if published_at else None,
    }


def promote_aop_targets(session) -> dict:
    """Copy current staging AOP targets (aop_division_target) → locked
    (aop_locked_target) so the Planning Engine sees a stable, user-approved
    version even if subsequent forecast runs overwrite staging.
    Idempotent — safe to call multiple times.
    """
    session.execute(text("""
        INSERT INTO planning_inputs.lever_definitions (lever_key, label, required, shape)
        VALUES (:k, 'AOP Division Target (locked for Planning Engine)', false, 'named_row')
        ON CONFLICT (lever_key) DO NOTHING
    """), {"k": LOCKED_LEVER_KEY})

    staging_rows = session.execute(text("""
        SELECT row_key, period_id, value, source
        FROM planning_inputs.input_values
        WHERE lever_key = :lk
          AND row_key   IN ('MENS','LADIES','KIDS')
          AND period_id IN (202703,202704,202705,202706)
        ORDER BY row_key, period_id
    """), {"lk": LEVER_KEY}).fetchall()

    if not staging_rows:
        return {"ok": False, "reason": "No staged AOP targets found — run a forecast first."}

    for row_key, period_id, value, source in staging_rows:
        session.execute(text("""
            INSERT INTO planning_inputs.input_values
                (lever_key, store_id, division_code, period_id, row_key, value, source)
            VALUES (:lk, '', '', :pid, :rk, :val, :src)
            ON CONFLICT ON CONSTRAINT uq_input_values_identity
            DO UPDATE SET value      = EXCLUDED.value,
                          source     = EXCLUDED.source,
                          updated_at = now()
        """), {"lk": LOCKED_LEVER_KEY, "pid": period_id,
               "rk": row_key, "val": value, "src": source})

    session.commit()
    return {"ok": True, "locked_rows": len(staging_rows)}
