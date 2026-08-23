"""
planning_inputs schema — replaces the opaque {columns, rows} "lever" blobs in
config/levers.json with a normalized fact table. lever_definitions keeps the
existing lever keys (store_actuals, growth_pct, store_master, ...) as a lookup
so the current UI/editor concept of "one lever per sheet" still makes sense.
"""
import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class LeverDefinition(Base):
    __tablename__ = "lever_definitions"
    __table_args__ = {"schema": "planning_inputs"}

    lever_key: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shape: Mapped[str] = mapped_column(String, nullable=False)  # store_division_period | named_row | scalar


class Period(Base):
    """Canonical month periods (YYYYMM), e.g. label "Apr'26" -> 202604.
    Replaces fragile string parsing of Excel column headers like "Mar'27"."""
    __tablename__ = "periods"
    __table_args__ = {"schema": "planning_inputs"}

    period_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # YYYYMM
    label: Mapped[str] = mapped_column(String, nullable=False, unique=True)  # "Apr'26"


class InputValue(Base):
    __tablename__ = "input_values"
    __table_args__ = (
        UniqueConstraint(
            "lever_key", "store_id", "division_code", "period_id", "row_key",
            name="uq_input_values_identity",
        ),
        {"schema": "planning_inputs"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lever_key: Mapped[str] = mapped_column(ForeignKey("planning_inputs.lever_definitions.lever_key"), nullable=False)
    # store_id/division_code/row_key are NOT NULL with '' meaning "not
    # applicable to this lever's shape" — Postgres unique constraints treat
    # NULL as distinct from NULL, so a nullable identity column silently
    # breaks ON CONFLICT dedup (caught live: a re-sync inserted a full second
    # copy of every store_actuals row instead of updating). '' is a real,
    # constraint-enforceable value; NULL is not. division_code's FK is
    # satisfied by the sentinel masterdata.divisions row ('', 'N/A — ...').
    store_id: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    division_code: Mapped[str] = mapped_column(ForeignKey("masterdata.divisions.division_code"), nullable=False, server_default="")
    period_id: Mapped[int] = mapped_column(ForeignKey("planning_inputs.periods.period_id"), nullable=False, server_default="0")
    row_key: Mapped[str] = mapped_column(String, nullable=False, server_default="")  # e.g. "OVERALL" for non-store rows
    value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)  # manual | calendar_sync | import
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InputValueHistory(Base):
    """Append-only ledger of every change to input_values — never overwrite
    without a trace, per the ledger principle."""
    __tablename__ = "input_values_history"
    __table_args__ = {"schema": "planning_inputs"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    input_value_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    old_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    new_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
