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


MAMJ_BASE_MONTHS = ["Mar'27", "Apr'27", "May'27", "Jun'27"]


def _compute_mamj_growth(detail_records: list[dict]) -> float | None:
    """MAMJ LFL KLM: (sum Forecast / sum Base - 1) × 100. Returns None if no base data."""
    base_total = fc_total = 0.0
    for rec in detail_records:
        if rec.get("Tag") not in LFL_TAGS:
            continue
        div = (rec.get("Division") or "").strip().upper()
        if div not in PUBLISH_DIVS:
            continue
        for m in MAMJ_BASE_MONTHS:
            base_total += float(rec.get(f"{m} | Base") or 0)
            fc_total   += float(rec.get(f"{m} | Forecast") or 0)
    if base_total == 0:
        return None
    return round((fc_total / base_total - 1) * 100, 1)


def _ensure_history_table(session) -> None:
    """Create aop_publish_history if it doesn't exist yet, and add growth_pct column."""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS planning_inputs.aop_publish_history (
            id               SERIAL PRIMARY KEY,
            session_id       TEXT,
            published_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            division_totals  JSONB       NOT NULL,
            total_mamj_lakhs NUMERIC(12,2),
            growth_pct       NUMERIC(8,2)
        )
    """))
    # Add growth_pct to tables created before this column existed
    session.execute(text("""
        ALTER TABLE planning_inputs.aop_publish_history
        ADD COLUMN IF NOT EXISTS growth_pct NUMERIC(8,2)
    """))
    # division_base_totals: the LFL base (Rs Lakhs) AOP's own growth% was
    # computed against, per division/period - lets a downstream consumer
    # (BIS) derive AOP's OWN growth% (target/base - 1) instead of dividing
    # AOP's target by its own, separately-sourced LY baseline. See BIS's
    # DEPT_ACTUAL_LY comment/2026-09-22 fix for why that divergence mattered.
    session.execute(text("""
        ALTER TABLE planning_inputs.aop_publish_history
        ADD COLUMN IF NOT EXISTS division_base_totals JSONB
    """))
    # division_engine_totals: the pure engine forecast (Rs Lakhs, "Engine
    # Forecast" column - excludes the ref-store-mix deviation layer applied
    # on top for the final "Forecast"/target figure). AOP's own Output tab
    # displays growth% off THIS figure (drill.jsx's growthEng), not off the
    # deviation-inclusive target - confirmed 2026-09-23 the two diverge (e.g.
    # MENS MAMJ: engine/base = flat +10.0%, but target/base = +9.3% once the
    # ref-store redistribution is folded in). BIS must use this one for its
    # displayed growth%/vs-LY%, so it matches what the user sees in AOP.
    session.execute(text("""
        ALTER TABLE planning_inputs.aop_publish_history
        ADD COLUMN IF NOT EXISTS division_engine_totals JSONB
    """))


def _aggregate_lfl_totals(detail_records: list[dict]):
    """Pure aggregation, no DB I/O - kept separate from publish_aop_targets()
    so it's directly unit-testable (see test_publish_aop_targets.py). Returns
    three {(row_key, period_id): total_lakhs} dicts: forecast (deviation-
    inclusive target), base (LY actuals AOP's growth% is computed against),
    and engine (pure engine forecast, excl. the ref-store-mix deviation layer
    - what AOP's own Output tab displays growth% off; see drill.jsx's
    growthEng and BIS's S.aopEngine, 2026-09-23)."""
    totals: dict[tuple[str, int], float] = {}
    base_totals: dict[tuple[str, int], float] = {}
    engine_totals: dict[tuple[str, int], float] = {}
    for rec in detail_records:
        if rec.get("Tag") not in LFL_TAGS:
            continue  # skip NSO and Ramp stores
        div = (rec.get("Division") or "").strip().upper()
        if div not in PUBLISH_DIVS:
            continue
        for month_label, period_id in MAMJ.items():
            val = rec.get(f"{month_label} | Forecast") or 0.0
            base = rec.get(f"{month_label} | Base") or 0.0
            # Same fallback drill.jsx's toLeaf() uses: older sessions run
            # before "Engine Forecast" existed as its own column have no
            # deviation layer anyway, so Forecast IS the engine figure.
            engine = rec.get(f"{month_label} | Engine Forecast")
            if engine is None:
                engine = val
            key = (div, period_id)
            totals[key] = totals.get(key, 0.0) + float(val)
            base_totals[key] = base_totals.get(key, 0.0) + float(base)
            engine_totals[key] = engine_totals.get(key, 0.0) + float(engine)
    return totals, base_totals, engine_totals


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

    totals, base_totals, engine_totals = _aggregate_lfl_totals(detail_records)

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
        div_totals: dict[str, dict[str, float]] = {}
        for (div, pid), val in totals.items():
            div_totals.setdefault(div, {})[str(pid)] = round(val, 2)
        div_base_totals: dict[str, dict[str, float]] = {}
        for (div, pid), val in base_totals.items():
            div_base_totals.setdefault(div, {})[str(pid)] = round(val, 2)
        div_engine_totals: dict[str, dict[str, float]] = {}
        for (div, pid), val in engine_totals.items():
            div_engine_totals.setdefault(div, {})[str(pid)] = round(val, 2)
        total_mamj = round(sum(totals.values()), 2)
        growth_pct = _compute_mamj_growth(detail_records)
        session.execute(text("""
            INSERT INTO planning_inputs.aop_publish_history
                (session_id, division_totals, division_base_totals, division_engine_totals, total_mamj_lakhs, growth_pct)
            VALUES (:sid, CAST(:dt AS jsonb), CAST(:dbt AS jsonb), CAST(:det AS jsonb), :total, :gpct)
        """), {
            "sid": session_id,
            "dt": json.dumps(div_totals),
            "dbt": json.dumps(div_base_totals),
            "det": json.dumps(div_engine_totals),
            "total": total_mamj,
            "gpct": growth_pct,
        })
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
        VALUES ('backfill', :ts, CAST(:dt AS jsonb), :total)
    """), {
        "ts": latest_ts,
        "dt": json.dumps(div_totals),
        "total": total_mamj,
    })
    session.commit()
    return True


def list_aop_history(session, limit: int = 15) -> list[dict]:
    """Return only explicitly saved AOP plan versions, joined to publish history.
    Only sessions that appear in planning_inputs.plan_versions are shown — i.e.
    the versions the user deliberately saved in the AOP Forecaster."""
    try:
        _ensure_history_table(session)
        versions = session.execute(text("""
            SELECT data->>'label', data->>'sessionId', data->>'createdAt',
                   COALESCE(data->>'lastModifiedAt', last_modified_at::text)
            FROM planning_inputs.plan_versions
        """)).fetchall()
        pubs = session.execute(text("""
            SELECT id, session_id, published_at, division_totals, total_mamj_lakhs, growth_pct,
                   division_base_totals, division_engine_totals
            FROM planning_inputs.aop_publish_history
            WHERE session_id IN (SELECT data->>'sessionId' FROM planning_inputs.plan_versions)
            ORDER BY published_at
        """)).fetchall()
        return [
            {
                "id": p[0],
                "session_id": p[1],
                "published_at": p[2].isoformat() if p[2] else None,
                "division_totals": p[3],
                "total_mamj_lakhs": float(p[4]) if p[4] is not None else 0.0,
                "growth_pct": float(p[5]) if p[5] is not None else None,
                "lfl_growth_pct": lfl_growth_pct(p[6], p[3]),
                "version_label": label,
            }
            for label, _sid, p in pick_version_publishes(versions, pubs)[:limit]
        ]
    except Exception:
        return []


def live_version(session, session_id=None):
    """THE AOP every consumer follows (2026-09-25, user: "one source yet so many
    distinct numbers ... perma fix"): the publish of a SAVED plan version - that
    session's version when `session_id` is given (e.g. the version on screen),
    else the latest saved version. Unsaved what-if runs and runs of a deleted
    version are never live: before this, BIS / the Planning Engine lock followed
    "whichever run published last", so deleting Version 3 left its run (base
    387.4 Cr) live while AOP showed Version 2 (388.8 Cr).
    Returns a list_aop_history entry, or None when nothing is saved - and None when `session_id` has no saved
    version (2026-09-26: it used to fall back to the latest saved version, so "Lock to Planning" on a just-deleted
    Version 3 silently locked Version 2)."""
    hist = list_aop_history(session, limit=50)
    if session_id:
        return next((h for h in hist if h["session_id"] == session_id), None)
    return hist[0] if hist else None


def restage_live(session):
    """Staging (aop_division_target, what live readers get) := the live saved
    version's publish. Called after every plan-version save / delete."""
    h = live_version(session)
    if not h:
        return None
    for div, periods in (h["division_totals"] or {}).items():
        for pid, val in periods.items():
            session.execute(text("""
                INSERT INTO planning_inputs.input_values
                    (lever_key, store_id, division_code, period_id, row_key, value, source)
                VALUES (:lk, '', '', :pid, :rk, :val, 'aop_forecaster')
                ON CONFLICT ON CONSTRAINT uq_input_values_identity
                DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source, updated_at = now()
            """), {"lk": LEVER_KEY, "pid": int(pid), "rk": div, "val": float(val)})
    session.commit()
    return h


def lfl_growth_pct(base_totals, target_totals):
    """MAMJ LFL growth % of one publish = sum(published target) / sum(base) - 1
    over MENS/LADIES/KIDS. This is AOP Summary's "Overall Growth" (Forecast vs
    Base, LfL, KLM) and BIS's "Growth vs LY" once it seeds its plan to these
    targets - one definition in both apps (2026-09-25). The engine-only
    forecast is NOT used: it leaves out the ref-store deviation layer (8.7 Cr,
    all in March) and made BIS plan 423.1 against a 431.9 target. None when a
    publish predates the base column."""
    if not base_totals or not target_totals:
        return None
    b = sum(float(v) for d in PUBLISH_DIVS for v in (base_totals.get(d) or {}).values())
    t = sum(float(v) for d in PUBLISH_DIVS for v in (target_totals.get(d) or {}).values())
    return round((t / b - 1) * 100, 1) if b else None


def _ts(iso_or_dt):
    import datetime as _dt
    if iso_or_dt is None or isinstance(iso_or_dt, _dt.datetime):
        return iso_or_dt
    return _dt.datetime.fromisoformat(str(iso_or_dt).replace("Z", "+00:00"))


def pick_version_publishes(versions, pubs, tolerance_s=120):
    """[(label, session_id, publish_row)] newest version first - one entry PER
    SAVED VERSION: the latest publish of the version's session made at or
    before the version was last SAVED (+ `tolerance_s`, because a save lands
    seconds before OR after the run that publishes it).
    Why "last saved" and not "latest in the session" (2026-09-25): every AOP
    run publishes, including unsaved what-if runs, and several versions can
    share one session. Version 2 (saved 15 Sep at 10% flat) had an unsaved
    23 Sep run at MENS 15 / LADIES 12 / KIDS 9 in its session; BIS synced that
    run as "Version 2" (+12.2%) while AOP's card showed the saved +10.0%.
    Bounding by the save time keeps unsaved runs out of any saved version,
    and deleting another version (V3 was) can't change what a version shows.
    versions: (label, session_id, createdAt iso, savedAt iso);
    pubs: (id, session_id, published_at, ...) sorted by published_at."""
    import datetime as _dt
    tol = _dt.timedelta(seconds=tolerance_s)
    out = []
    for label, sid, created, saved in versions:
        cutoff = _ts(saved) or _ts(created)
        owned = [p for p in pubs if p[1] == sid and (cutoff is None or p[2] <= cutoff + tol)]
        if owned:
            out.append((label, sid, owned[-1]))
    out.sort(key=lambda t: t[2][2], reverse=True)
    return out


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


def unlock_aop_targets(session) -> dict:
    """Clear aop_locked_target — the Planning Engine's read (division_plan.py's
    _get_aop_targets, "prefers locked over staging") falls straight back to
    the live staging targets (aop_division_target) once no locked row exists,
    no separate 'is it locked' flag to flip. Reversible: promoting again just
    re-inserts these same rows."""
    result = session.execute(text("""
        DELETE FROM planning_inputs.input_values
        WHERE lever_key = :lk
          AND row_key    IN ('MENS','LADIES','KIDS')
          AND period_id  IN (202703,202704,202705,202706)
    """), {"lk": LOCKED_LEVER_KEY})
    session.commit()
    return {"ok": True, "unlocked_rows": result.rowcount}
