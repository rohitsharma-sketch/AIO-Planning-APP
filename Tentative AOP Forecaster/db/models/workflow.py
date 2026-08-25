"""workflow schema — the Planner->Buyer->Reviewer->Approver plan_cycle
state machine. See the spec for the full transition table."""
import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

STATUSES = ("draft", "pending_buyer", "pending_review", "pending_approval", "approved")


class PlanCycle(Base):
    __tablename__ = "plan_cycles"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    current_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engine.forecast_runs.run_id"), nullable=True
    )
    buyer_adjusted_totals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlanCycleTransition(Base):
    __tablename__ = "plan_cycle_transitions"
    __table_args__ = {"schema": "workflow"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow.plan_cycles.id"), nullable=False
    )
    from_status: Mapped[str] = mapped_column(String, nullable=False)
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engine.forecast_runs.run_id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
