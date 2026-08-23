"""
sync schema — the only place external sources are ever touched. Everything else
in the system reads Postgres only. Sources are now file-based reads off the local
data lake (INVENTORY AUTOMATION\\data_lake\\raw\\...), not a live HTTP call to the
Calendar Engine server.
"""
import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class SyncSource(Base):
    __tablename__ = "sources"
    __table_args__ = {"schema": "sync"}

    source_key: Mapped[str] = mapped_column(String, primary_key=True)
    # e.g. 'data_lake_sales' | 'data_lake_day_shift' | 'data_lake_site_master'
    config: Mapped[dict] = mapped_column(JSON, nullable=False)  # {"path": "...\\data_lake\\raw\\site_master"}
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ttl_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = {"schema": "sync"}

    sync_run_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(ForeignKey("sync.sources.source_key"), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")  # running|success|failed|partial
    rows_read: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
