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
"""
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


def publish_aop_targets(session, detail_records: list[dict]) -> None:
    """Upsert MENS/LADIES/KIDS × MAMJ LFL forecast totals to planning_inputs.input_values.
    Idempotent: safe to call after every run."""
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
