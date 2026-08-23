"""
calendar schema.

day_shift_map: the data lake's single global CURRENT_DATE -> LY_MAPPED_DATE
table. Kept, but NOT what the real reindex uses (see below) — it has no
cluster dimension, and the true festival-timing shift is cluster-specific.

calendars / calendar_day_pairs / store_calendar_clusters: the real artifacts,
sourced from the Calendar Engine's "Local DB" JSON (calendar_library.json,
store_cluster_map.json). The per-cluster day-by-day dayMap in
calendar_library.json is already fully built (festival-window "v2-shift-repair"
logic lives in the Calendar Engine's UI, out of scope here) — we only read the
finished result. "Calendar Cluster" (store_calendar_clusters) is a THIRD
cluster space, distinct from masterdata.stores.cluster_key (business planning
cluster, Store Master.xlsx) and .erp_cluster_type (site_master CLUSTER_TYPE) —
e.g. store AAC is "MP, CG, RJ - (NP)" / cluster_key business-side but
"JH + MP + CG" in store_calendar_clusters.
"""
import datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class DayShiftMap(Base):
    __tablename__ = "day_shift_map"
    __table_args__ = {"schema": "calendar"}

    current_date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    ly_mapped_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Calendar(Base):
    __tablename__ = "calendars"
    __table_args__ = {"schema": "calendar"}

    calendar_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)  # source's own id (JS Date.now()-scale)
    name: Mapped[str] = mapped_column(String, nullable=False)
    ref_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fut_year: Mapped[int] = mapped_column(Integer, nullable=False)
    saved_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine: Mapped[str | None] = mapped_column(String, nullable=True)


class CalendarDayPair(Base):
    __tablename__ = "calendar_day_pairs"
    __table_args__ = (
        UniqueConstraint("calendar_id", "cluster_name", "seq", name="uq_calendar_day_pairs_identity"),
        {"schema": "calendar"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    calendar_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("calendar.calendars.calendar_id"), nullable=False)
    cluster_name: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "JH + MP + CG"
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    fut_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)


class StoreCalendarCluster(Base):
    """Store -> Calendar Cluster, from store_cluster_map.json. Effective-dated
    like masterdata.stores would be overkill here — the source itself is a
    single "locked" snapshot, not a history; a full replace on each sync
    mirrors that."""
    __tablename__ = "store_calendar_clusters"
    __table_args__ = {"schema": "calendar"}

    store_id: Mapped[str] = mapped_column(String, primary_key=True)
    cluster_name: Mapped[str] = mapped_column(String, nullable=False)
    locked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
