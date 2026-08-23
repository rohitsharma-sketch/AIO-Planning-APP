"""audit schema — every Growth %/NSO/AOP override edit, old value -> new
value, who and when. See db/editor.py for the write path."""
import datetime
import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class DataChange(Base):
    __tablename__ = "data_changes"
    __table_args__ = {"schema": "audit"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    record_key: Mapped[dict] = mapped_column(JSON, nullable=False)
    old_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("auth.users.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)
    plan_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow.plan_cycles.id"), nullable=True
    )
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
