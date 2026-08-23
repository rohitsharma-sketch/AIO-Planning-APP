"""
Persists an engine_v3.run_engine() result into Postgres — engine.forecast_runs
/ engine.forecast_results — for runs started from session-from-db. Parses the
same flat records df.to_json(orient="records") already writes to detail.json,
so engine_v3.py itself is untouched; only what happens to its output changes.

Column shape per record (build_df, engine_v3.py): "Store", "Division", "Tag",
"Cluster", then per FY28 month "<month> | Base" / "<month> | Engine Forecast" /
"<month> | Forecast" / "<month> | Deviation" — all in Rs Lakhs.
"""
import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.engine import ForecastResult, ForecastRun
from db.models.planning_inputs import Period

FY28_M = ["Mar'27", "Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
          "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"]
METRICS = ["Base", "Engine Forecast", "Forecast", "Deviation"]
METRIC_KEYS = {"Base": "base", "Engine Forecast": "engine_forecast", "Forecast": "forecast", "Deviation": "deviation"}


def persist_forecast_run(session: Session, detail_records: list[dict], *, created_by=None,
                          palette=None, growth_overrides=None, overall_override=None) -> uuid.UUID:
    period_ids = {p.label: p.period_id for p in session.execute(select(Period)).scalars().all()}

    run = ForecastRun(
        run_id=uuid.uuid4(), created_by=created_by, palette=palette,
        growth_overrides=growth_overrides, overall_override=overall_override,
        input_snapshot_at=datetime.datetime.now(datetime.timezone.utc), status="success",
    )
    session.add(run)
    session.flush()

    rows = []
    for rec in detail_records:
        store, division = rec.get("Store"), rec.get("Division")
        for month in FY28_M:
            period_id = period_ids.get(month)
            if period_id is None:
                continue
            for metric in METRICS:
                col = f"{month} | {metric}"
                if col not in rec or rec[col] is None:
                    continue
                rows.append({
                    "run_id": run.run_id, "store_id": store, "division_code": division,
                    "period_id": period_id, "metric_key": METRIC_KEYS[metric], "value": rec[col],
                })
    if rows:
        session.execute(ForecastResult.__table__.insert(), rows)
    session.commit()
    return run.run_id
