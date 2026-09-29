"""Shared helpers for sync jobs: pick the latest data-lake snapshot file, and
log every run to sync.sync_runs so every sync is auditable (started/completed/
status/rows/error), never silent."""
import contextlib
import datetime
import os
import re
import threading
import time

from db.base import SessionLocal
from db.models.sync import SyncRun

NETWORK_TIMEOUT_SECONDS = 90
NETWORK_RETRIES = 2
NETWORK_RETRY_DELAY_SECONDS = 10


def call_with_timeout(fn, *args, timeout=NETWORK_TIMEOUT_SECONDS, retries=NETWORK_RETRIES,
                       delay=NETWORK_RETRY_DELAY_SECONDS, **kwargs):
    """Run a blocking call (a network file read) with a hard wall-clock timeout
    and a few retries with a short delay - the data-lake share (\\\\10.0.1.85\\...)
    is known to intermittently STALL rather than fail fast, and a stalled
    os.listdir/pq.read_table over SMB blocks forever with no exception to
    catch. `fn` runs in a daemon thread so a genuinely wedged syscall can't
    block this process from exiting even if a retry attempt never returns -
    daemon threads are hard-killed at interpreter shutdown, unlike the
    non-daemon workers a ThreadPoolExecutor uses by default."""
    last_exc = None
    for attempt in range(retries + 1):
        box = {}
        def _target():
            try:
                box["result"] = fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001 - re-raised on the calling thread below
                box["error"] = e
        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            last_exc = TimeoutError(f"{getattr(fn, '__name__', fn)} did not return within {timeout}s (attempt {attempt + 1}/{retries + 1}) - data-lake share may be stalled")
        elif "error" in box:
            last_exc = box["error"]
        else:
            return box["result"]
        if attempt < retries:
            time.sleep(delay)
    raise last_exc


def latest_file(folder: str) -> str:
    """The newest complete data-lake export in folder - the one rule every app uses (rs_common.lake_files, 29 Sep 2026).
    It used to take the alphabetically-last FILE NAME, which picked the old day-wise export once a newer one's uuid
    sorted lower ("31d59..." < "b9e58...") and only got 'master.parquet' right by luck."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))   # repo root
    from rs_common.lake_files import latest_path
    path = call_with_timeout(latest_path, folder)
    if not path:
        raise FileNotFoundError(f"No parquet snapshot found in {folder}")
    return path


def snapshot_last_day(filename: str):
    """Last sales day a data-lake export accounts for: the day BEFORE its
    `_<YYYYMMDD>T<HHMMSS>.parquet` snapshot stamp (verified on the day-wise
    export: its _20260828T... file's max BILLDATE is 2026-08-27). The
    month-wise source has no day grain (BILLMONTH only), so this stamp is its
    only "last day accounted" signal. None if the name carries no stamp."""
    m = re.search(r"_(\d{8})T\d{6}\.parquet$", filename)
    return datetime.datetime.strptime(m.group(1), "%Y%m%d").date() - datetime.timedelta(days=1) if m else None


def closed_through_from_last_day(last_day: datetime.date) -> str:
    """'YYYY-MM' of the last month whose final day is <= last_day - month-1
    unless last_day IS that month's last day."""
    nxt = last_day + datetime.timedelta(days=1)
    return (nxt.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")


CLOSED_THROUGH_TTL_SECONDS = 60
_CLOSED_THROUGH = {"at": 0.0, "val": None}


def get_closed_through():
    """Persisted 'closed_through' ('YYYY-MM') from the latest successful
    data_lake_sales sync (store_actuals_sync writes it into sync_runs.detail),
    cached per process for CLOSED_THROUGH_TTL_SECONDS so every step reads the
    same value without a re-sync or a DB hit per call. None = nothing
    persisted yet / DB unreachable -> callers fall back to the date rule."""
    if time.time() - _CLOSED_THROUGH["at"] > CLOSED_THROUGH_TTL_SECONDS:
        val = None
        try:
            from sqlalchemy import select
            with SessionLocal() as s:
                detail = s.execute(
                    select(SyncRun.detail)
                    .where(SyncRun.source_key == "data_lake_sales", SyncRun.status == "success")
                    .order_by(SyncRun.sync_run_id.desc()).limit(1)
                ).scalar()
            val = (detail or {}).get("closed_through")
        except Exception:  # noqa: BLE001 - no DB = date-rule fallback, never block a run
            pass
        _CLOSED_THROUGH.update(at=time.time(), val=val)
    return _CLOSED_THROUGH["val"]


def _is_network_offline(e: Exception) -> bool:
    """WinError 53 = network path not found (UNC share unreachable).
    Also catches WinError 67 (bad net name) and similar UNC errors, and a
    call_with_timeout give-up (the share stalled rather than failing fast -
    same practical outcome as being offline)."""
    if isinstance(e, TimeoutError):
        return True
    winerror = getattr(e, "winerror", None)
    if winerror in (53, 67, 1203, 1231):
        return True
    msg = str(e).lower()
    return "winerror 53" in msg or "network path was not found" in msg or "bad net name" in msg


@contextlib.contextmanager
def sync_run(source_key: str):
    """Wrap a sync job: opens a session + a sync_runs row, commits/marks
    success on clean exit, marks failed (with the error) and re-raises on
    exception. Yields (session, result) — the job fills `result` in place.

    Network-offline errors (WinError 53 — source machine unreachable) are
    recorded as status='offline' and do NOT re-raise, so the scheduled task
    shows an amber warning instead of a hard failure."""
    session = SessionLocal()
    run = SyncRun(source_key=source_key, status="running")
    session.add(run)
    session.commit()  # persist the "running" row now, independent of the job's own transaction
    result = {"rows_read": None, "rows_updated": None, "rows_added": None, "detail": None}
    try:
        yield session, result
        run.status = "success"
        run.rows_read = result["rows_read"]
        run.rows_updated = result["rows_updated"]
        run.rows_added = result["rows_added"]
        run.detail = result["detail"]
        run.completed_at = datetime.datetime.now(datetime.timezone.utc)
        session.commit()
    except Exception as e:
        session.rollback()
        if _is_network_offline(e):
            run.status = "offline"
            run.error_message = f"Source machine offline — last sync data still active. ({type(e).__name__}: {e})"
        else:
            run.status = "failed"
            run.error_message = f"{type(e).__name__}: {e}"
            run.detail = result["detail"]   # e.g. calendar_check's per-check results, kept for the failure too
        run.completed_at = datetime.datetime.now(datetime.timezone.utc)
        session.add(run)
        session.commit()
        if run.status != "offline":
            raise  # only re-raise hard failures; offline is a graceful skip
    finally:
        session.close()
