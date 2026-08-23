"""
masterdata schema — stores, clusters, divisions/departments.

Canonical source going forward is the `site_master` snapshot in
INVENTORY AUTOMATION's data lake (refreshed daily), not the thin
Store Master lever. Columns here mirror the fields the AOP levers and
NSO logic actually use.
"""
import datetime

from sqlalchemy import Boolean, Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Cluster(Base):
    __tablename__ = "clusters"
    __table_args__ = {"schema": "masterdata"}

    cluster_key: Mapped[str] = mapped_column(String, primary_key=True)
    cluster_name: Mapped[str] = mapped_column(String, nullable=False)


class Division(Base):
    __tablename__ = "divisions"
    __table_args__ = {"schema": "masterdata"}

    division_code: Mapped[str] = mapped_column(String, primary_key=True)  # GM/KIDS/LADIES/MENS/RETAIL
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class Department(Base):
    """SECTION/DEPARTMENT names from the sales fact table, rolled up to a division
    (mirrors calendar_sync.py's GM_DEPTS set; excluded=True for DND/NON-TRADING/etc.)."""
    __tablename__ = "departments"
    __table_args__ = {"schema": "masterdata"}

    department_name: Mapped[str] = mapped_column(String, primary_key=True)
    division_code: Mapped[str] = mapped_column(ForeignKey("masterdata.divisions.division_code"), nullable=False)
    excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Store(Base):
    """Effective-dated: a store row is superseded by inserting a new row with a
    later valid_from and closing the prior row's valid_to, never overwritten in
    place, so history of cluster/status changes is preserved."""
    __tablename__ = "stores"
    __table_args__ = (
        UniqueConstraint("store_id", "valid_from", name="uq_stores_store_id_valid_from"),
        {"schema": "masterdata"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    store_id: Mapped[str] = mapped_column(String, nullable=False, index=True)  # SITE_CODE
    store_name: Mapped[str | None] = mapped_column(String, nullable=True)
    ref_store: Mapped[str | None] = mapped_column(String, nullable=True)
    cluster_key: Mapped[str | None] = mapped_column(ForeignKey("masterdata.clusters.cluster_key"), nullable=True)
    # site_master's operational CLUSTER_TYPE (e.g. "R6", "BR2") is a DIFFERENT value
    # space from the business planning Cluster above (e.g. "MP, CG, RJ - (NP)",
    # sourced from Store Master.xlsx) — kept as a plain field, not a masterdata.clusters FK.
    erp_cluster_type: Mapped[str | None] = mapped_column(String, nullable=True)
    store_status: Mapped[str | None] = mapped_column(String, nullable=True)
    store_current_status: Mapped[str | None] = mapped_column(String, nullable=True)
    store_grade: Mapped[str | None] = mapped_column(String, nullable=True)
    gm_grade: Mapped[str | None] = mapped_column(String, nullable=True)
    festival_grouping: Mapped[str | None] = mapped_column(String, nullable=True)
    region_type: Mapped[str | None] = mapped_column(String, nullable=True)
    opening_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    tag: Mapped[str | None] = mapped_column(String, nullable=True)
    valid_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)  # NULL = current


class NsoOpening(Base):
    __tablename__ = "nso_openings"
    __table_args__ = {"schema": "masterdata"}

    store_id: Mapped[str] = mapped_column(String, primary_key=True)
    opening_month: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    is_named: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'config_import' | 'manual'
