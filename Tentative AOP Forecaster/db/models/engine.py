"""
engine schema — replaces per-session JSON/xlsx files (sessions/<uuid>/results.json,
detail.json, AOP_Forecast.xlsx) with a queryable run history. AOP_Forecast.xlsx
becomes a generated export from forecast_results, not a stored artifact.
"""
import datetime
import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = {"schema": "engine"}

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    palette: Mapped[str | None] = mapped_column(String, nullable=True)
    growth_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overall_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_snapshot_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")


class ForecastResult(Base):
    __tablename__ = "forecast_results"
    __table_args__ = {"schema": "engine"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engine.forecast_runs.run_id"), nullable=False)
    store_id: Mapped[str | None] = mapped_column(String, nullable=True)
    division_code: Mapped[str | None] = mapped_column(ForeignKey("masterdata.divisions.division_code"), nullable=True)
    period_id: Mapped[int | None] = mapped_column(ForeignKey("planning_inputs.periods.period_id"), nullable=True)
    metric_key: Mapped[str] = mapped_column(String, nullable=False)  # aop_forecast_lakhs | base | growth_applied ...
    value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
