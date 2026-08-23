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


@contextlib.contextmanager
def sync_run(source_key: str):
    """Wrap a sync job: opens a session + a sync_runs row, commits/marks
    success on clean exit, marks failed (with the error) and re-raises on
    exception. Yields (session, result) — the job fills `result` in place."""
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
        run.status = "failed"
        run.error_message = f"{type(e).__name__}: {e}"
        run.completed_at = datetime.datetime.now(datetime.timezone.utc)
        session.add(run)
        session.commit()
        raise
    finally:
        session.close()
