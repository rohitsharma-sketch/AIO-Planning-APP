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

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, func, SmallInteger, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
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


class CalendarCluster(Base):
    """The festival-config clusters actually used to compute a saved
    calendar's dayMap — calendar_library.json's `clusters` array, dropped
    by the existing sync job (which only captured dayMap)."""
    __tablename__ = "calendar_clusters"
    __table_args__ = (
        UniqueConstraint("calendar_id", "cluster_name", name="uq_calendar_clusters_identity"),
        {"schema": "calendar"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    calendar_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("calendar.calendars.calendar_id"), nullable=False)
    cluster_name: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str | None] = mapped_column(String, nullable=True)


class CalendarClusterFestival(Base):
    __tablename__ = "calendar_cluster_festivals"
    __table_args__ = {"schema": "calendar"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    calendar_cluster_id: Mapped[int] = mapped_column(ForeignKey("calendar.calendar_clusters.id"), nullable=False)
    source_festival_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    ref_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    fut_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    pre: Mapped[int] = mapped_column(Integer, nullable=False)
    core: Mapped[int] = mapped_column(Integer, nullable=False)
    post: Mapped[int] = mapped_column(Integer, nullable=False)
    # Manual-intervention exemption: when true, this cluster's row for this
    # festival name is excluded from the cross-cluster Pre/Core/Post cascade
    # (handleDayFieldChange) in both directions - editing it doesn't push out
    # to other clusters, and editing another cluster's same-named festival
    # doesn't overwrite it. Lets e.g. Kashmir keep a genuinely different
    # window for one festival while staying synced on every other festival.
    independent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StoreClusterMapMeta(Base):
    """Singleton row for store_cluster_map.json's fields the existing sync
    job drops: source, aliases, editedAt. `locked` itself is already
    represented by store_calendar_clusters rows existing at all plus
    locked_at being non-null — no separate boolean needed."""
    __tablename__ = "store_cluster_map_meta"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_store_cluster_map_meta_singleton"),
        {"schema": "calendar"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    aliases: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    edited_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ClusterProfile(Base):
    """The live, editable festival config the UI works against — app_state.json's
    clusterProfiles. Distinct from CalendarCluster, which is a frozen snapshot
    saved into calendar_library."""
    __tablename__ = "cluster_profiles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_cluster_profiles_name"),
        {"schema": "calendar"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_id: Mapped[int] = mapped_column(Integer, nullable=False)


class ClusterProfileFestival(Base):
    __tablename__ = "cluster_profile_festivals"
    __table_args__ = {"schema": "calendar"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cluster_profile_id: Mapped[int] = mapped_column(ForeignKey("calendar.cluster_profiles.id"), nullable=False)
    source_festival_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    ref_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    fut_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    pre: Mapped[int] = mapped_column(Integer, nullable=False)
    core: Mapped[int] = mapped_column(Integer, nullable=False)
    post: Mapped[int] = mapped_column(Integer, nullable=False)
    # See the matching field on CalendarClusterFestival - kept in sync across
    # both tables so Load & Preview / Create Calendar round-trips this flag
    # instead of silently dropping it.
    independent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AppStateMeta(Base):
    """Singleton row for app_state.json's scalar UI settings (everything
    except clusterProfiles, which lives in ClusterProfile/ClusterProfileFestival)."""
    __tablename__ = "app_state_meta"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_app_state_meta_singleton"),
        {"schema": "calendar"},
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    active_cluster_idx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ref_year: Mapped[str | None] = mapped_column(String, nullable=True)
    fut_year: Mapped[str | None] = mapped_column(String, nullable=True)
    max_shift: Mapped[str | None] = mapped_column(String, nullable=True)
    mo_pri: Mapped[str | None] = mapped_column(String, nullable=True)
    theme_id: Mapped[str | None] = mapped_column(String, nullable=True)
    saved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    migrations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class FestivalChangelogEntry(Base):
    __tablename__ = "festival_changelog"
    __table_args__ = (
        UniqueConstraint("range_key", "cluster_name", "festival_name", name="uq_festival_changelog_identity"),
        {"schema": "calendar"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    range_key: Mapped[str] = mapped_column(String, nullable=False)
    cluster_name: Mapped[str] = mapped_column(String, nullable=False)
    festival_name: Mapped[str] = mapped_column(String, nullable=False)
    ref_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    fut_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    saved_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StoreClusterLogEntry(Base):
    __tablename__ = "store_cluster_log"
    __table_args__ = {"schema": "calendar"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    added: Mapped[int] = mapped_column(Integer, nullable=False)
    removed: Mapped[int] = mapped_column(Integer, nullable=False)
    reassigned: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[list] = mapped_column(JSONB, nullable=False)


class SalesdataLinkSelection(Base):
    __tablename__ = "salesdata_link_selection"
    __table_args__ = (
        CheckConstraint("source_type IN ('mw', 'dw')", name="ck_salesdata_link_selection_source_type"),
        {"schema": "calendar"},
    )

    source_type: Mapped[str] = mapped_column(String, primary_key=True)
    months: Mapped[list] = mapped_column(JSONB, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    synced_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Persisted "customise output fields" choice (Run Reindex's extra dimensions
    # + metric column, both drawn from get_source_schema's real-column list) -
    # saved here so a planner picks them once and every later reindex reuses
    # the same fields without re-selecting.
    extra_dims: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metric: Mapped[str | None] = mapped_column(String, nullable=True)


class SalesSnapshot(Base):
    """The last successful Run Reindex output, one row per (source_type, kind):
    'actual' is the real sales grouped on their own reference date/month,
    'trend_shifted' is the same run's sales grouped on the calendar-shifted
    future date/month. Both come out of the same reindex pass and are
    replaced together on every run - same full-replace pattern as
    StoreCalendarCluster. Other apps (e.g. SalesPlan's Sales Sync) read this
    instead of re-running their own reindex or parquet parse, so both facts
    are single DB-backed values shared across apps rather than trapped in
    one browser tab's Calendar Engine session."""
    __tablename__ = "sales_snapshots"
    __table_args__ = (
        CheckConstraint("source_type IN ('mw', 'dw')", name="ck_sales_snapshots_source_type"),
        CheckConstraint("kind IN ('actual', 'trend_shifted')", name="ck_sales_snapshots_kind"),
        {"schema": "calendar"},
    )

    source_type: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    grain: Mapped[str] = mapped_column(String, nullable=False)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    # Ordered list of row dict keys that together identify one output row - e.g.
    # ['store','division'] by default, or ['store','division','SECTION'] when the
    # user picks extra output fields on Run Reindex. Consumers (ReindexOutputPanel,
    # SalesPlan's Sales Sync) key off this instead of guessing from `grain`.
    key_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["store"])
    columns: Mapped[list] = mapped_column(JSONB, nullable=False)
    rows: Mapped[list] = mapped_column(JSONB, nullable=False)  # long-form [{store, division?, col, value}]
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_mapped: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReindexMonthCache(Base):
    """Caches ONE reference month's own reindex sub-result (day-wise or
    month-wise), so a CLOSED month never needs its raw sales re-read and
    re-aggregated on a later Run Reindex - only genuinely open/current months
    (which can still change) get recomputed every time. See _is_month_closed
    and run_reindex in scans.py for how this is used - "closed" means the
    reference month has fully elapsed as of the server's system date.

    Keyed by (source_type, ref_month, calendar_fingerprint, fields_key):
    calendar_fingerprint is a hash of the day-map actually used (not just a
    calendar id), so editing an existing locked calendar's mappings
    self-invalidates every cache entry it touches instead of silently
    serving a result computed under the old mapping. fields_key folds in the
    exact extraDims + metric selection for the same reason - a cached row
    here is reused ONLY when calendar, extra output fields, and metric all
    match the current Run Reindex request exactly.

    result_blob holds this one month's own {rows, actualRows, columns,
    actualColumns, refDateByColumn, rowsRead, rowsMapped, unmappedStores,
    ...} sub-result exactly as reindex_daywise/reindex_monthwise returned it
    for months=[ref_month] alone - cached and freshly-computed sub-results
    get concatenated back together by _merge_reindex_results into one
    combined output for whatever full month range was actually requested.

    Stored as UTF-8-encoded JSON bytes (BYTEA), not JSONB: a day-wise month
    broken out by several extra fields easily exceeds Postgres's hard
    per-JSONB-value limit of ~256MB (confirmed live - "total size of jsonb
    object elements exceeds the maximum of 268435455 bytes" on a real
    2026-04 day-wise write). BYTEA has no such ceiling. _save_month_cache /
    _load_month_cache in scans.py do the json.dumps().encode() /
    json.loads() at the Python level."""
    __tablename__ = "reindex_month_cache"
    __table_args__ = (
        CheckConstraint("source_type IN ('mw', 'dw')", name="ck_reindex_month_cache_source_type"),
        {"schema": "calendar"},
    )

    source_type: Mapped[str] = mapped_column(String, primary_key=True)
    ref_month: Mapped[str] = mapped_column(String, primary_key=True)
    calendar_fingerprint: Mapped[str] = mapped_column(String, primary_key=True)
    fields_key: Mapped[str] = mapped_column(String, primary_key=True)
    result_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
