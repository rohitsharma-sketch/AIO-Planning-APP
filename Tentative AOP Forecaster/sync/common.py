"""Shared helpers for sync jobs: pick the latest data-lake snapshot file, and
log every run to sync.sync_runs so every sync is auditable (started/completed/
status/rows/error), never silent."""
import contextlib
import datetime
import os

from db.base import SessionLocal
from db.models.sync import SyncRun


def latest_file(folder: str) -> str:
    """Data-lake folders hold one or more `<uuid>_<YYYYMMDDTHHMMSS>.parquet`
    snapshots; the lexicographically-last timestamp is the newest."""
    files = sorted(f for f in os.listdir(folder) if f.endswith(".parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet snapshot found in {folder}")
    return os.path.join(folder, files[-1])


def _is_network_offline(e: Exception) -> bool:
    """WinError 53 = network path not found (UNC share unreachable).
    Also catches WinError 67 (bad net name) and similar UNC errors."""
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
        run.completed_at = datetime.datetime.now(datetime.timezone.utc)
        session.add(run)
        session.commit()
        if run.status != "offline":
            raise  # only re-raise hard failures; offline is a graceful skip
    finally:
        session.close()
