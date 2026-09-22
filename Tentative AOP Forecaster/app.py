"""
AOP Forecaster — FastAPI backend
Run: uvicorn app:app --reload --port 8000
"""
import json, os, uuid, shutil
from typing import Optional
from fastapi import FastAPI, HTTPException, Body, Request, APIRouter, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from engine_v3 import run_engine, get_file_info, EXCEL_PALETTES

router = APIRouter()

app = FastAPI(title="AOP Forecaster API")
# Installed even in standalone mode so request.session is always safely
# accessible (an unauthenticated standalone request just sees an empty
# session — see _get_actor below) — when mounted under the unified platform,
# the SAME session cookie/secret is used, so a real logged-in user's id/role
# comes through here too.
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "dev-only-change-me"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)


def _session_dir(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, session_id)

def _input_path(session_id: str) -> str:
    return os.path.join(_session_dir(session_id), "inputs.xlsx")

def _output_path(session_id: str) -> str:
    return os.path.join(_session_dir(session_id), "AOP_Forecast.xlsx")

def _detail_path(session_id: str) -> str:
    return os.path.join(_session_dir(session_id), "detail.json")

def _results_path(session_id: str) -> str:
    return os.path.join(_session_dir(session_id), "results.json")


_STANDALONE_USERNAME = "standalone-app"


def _get_actor(request: Request):
    """(actor_id, actor_role) for audit logging. A real logged-in session
    (present when this router is mounted under the unified platform, behind
    auth) wins; standalone :8000 has no login at all, so edits there are
    attributed to a fixed, auto-created 'standalone-app' system user rather
    than failing (audit.data_changes.actor_id is NOT NULL by design — every
    edit must be attributable to *someone*, even a system actor)."""
    user = request.session.get("user")
    if user:
        return uuid.UUID(user["id"]), user["role"]

    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.auth import User

    session = SessionLocal()
    try:
        u = session.execute(select(User).where(User.username == _STANDALONE_USERNAME)).scalar_one_or_none()
        if u is None:
            import hashlib
            u = User(
                username=_STANDALONE_USERNAME,
                password_hash=hashlib.sha256(os.urandom(32)).hexdigest(),  # unusable password — this account never logs in
                role="planner", is_admin=False,
            )
            session.add(u)
            session.commit()
            session.refresh(u)
        return u.id, u.role
    finally:
        session.close()


class RunRequest(BaseModel):
    palette: str = "classic"
    include_debug: bool = False
    growth_overrides: Optional[dict] = None
    overall_override: Optional[dict] = None

@router.post("/api/run/{session_id}")
async def run(session_id: str, body: RunRequest = RunRequest()):
    inp = _input_path(session_id)
    if not os.path.exists(inp):
        raise HTTPException(404, "Session not found — upload inputs.xlsx first")
    palette = body.palette if body.palette in EXCEL_PALETTES else "classic"
    # DB-built sessions include estimates for months not yet closed (source='import').
    # Pass open_months=set() so the engine uses all available data instead of
    # filtering out the current/future months — the sync already guards what
    # gets written as real actuals; these are deliberately loaded planning estimates.
    from_db = os.path.exists(os.path.join(_session_dir(session_id), ".from_db"))
    engine_open_months = set() if from_db else None
    try:
        results = run_engine(inp, _output_path(session_id), palette=palette,
                             detail_file=_detail_path(session_id),
                             include_debug=body.include_debug,
                             growth_overrides=body.growth_overrides,
                             overall_override=body.overall_override,
                             open_months=engine_open_months)
    except Exception as e:
        raise HTTPException(500, str(e))
    with open(_results_path(session_id), "w", encoding="utf-8") as f:
        json.dump(results, f)

    run_id = None
    detail_records = None
    if os.path.exists(_detail_path(session_id)):
        with open(_detail_path(session_id), encoding="utf-8") as f:
            detail_records = json.load(f)

    if os.path.exists(os.path.join(_session_dir(session_id), ".from_db")):
        from db.base import SessionLocal
        from db.persist_run import persist_forecast_run

        db_session = SessionLocal()
        try:
            run_id = str(persist_forecast_run(
                db_session, detail_records, palette=palette,
                growth_overrides=body.growth_overrides, overall_override=body.overall_override,
            ))
        finally:
            db_session.close()

    # Always publish division targets so Buyer's Input Sheet stays in sync
    if detail_records:
        from db.base import SessionLocal
        from db.publish_aop_targets import publish_aop_targets
        _pub = SessionLocal()
        try:
            publish_aop_targets(_pub, detail_records, session_id=session_id)
        except Exception:
            pass  # non-fatal: Buyer's Input Sheet falls back to previous values
        finally:
            _pub.close()

    return {**results, "run_id": run_id}


@router.get("/api/results/{session_id}")
def get_results(session_id: str):
    rp = _results_path(session_id)
    if not os.path.exists(rp):
        raise HTTPException(404, "Run the engine first")
    with open(rp, encoding="utf-8") as f:
        return json.load(f)


@router.get("/api/data/{session_id}")
def get_data(session_id: str):
    dp = _detail_path(session_id)
    if not os.path.exists(dp):
        raise HTTPException(404, "Run the engine first")
    with open(dp, encoding="utf-8") as f:
        return json.load(f)


@router.get("/api/palettes")
def list_palettes():
    labels = {
        "classic": "Classic Navy",
        "emerald": "Slate & Emerald",
        "amber":   "Midnight & Amber",
        "coral":   "Deep Purple & Coral",
        "forest":  "Forest & Gold",
    }
    return [{"id": k, "label": labels.get(k, k), **v} for k, v in EXCEL_PALETTES.items()]


@router.get("/api/download/{session_id}")
def download(session_id: str):
    out = _output_path(session_id)
    if not os.path.exists(out):
        raise HTTPException(404, "Run the engine first")
    return FileResponse(
        out,
        filename="AOP_Forecast.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    shutil.rmtree(_session_dir(session_id), ignore_errors=True)
    return {"ok": True}



@router.post("/api/config/session-from-db")
def session_from_db():
    """Start a forecast session sourced entirely from Postgres (rs_planning) —
    no levers.json, no Excel read at request time. See db/to_workbook.py.
    The only other way to start a session is /api/upload (a one-off run from
    an uploaded workbook, bypassing the database entirely)."""
    from db.base import SessionLocal
    from db.to_workbook import build_workbook_from_db

    session_id = str(uuid.uuid4())
    os.makedirs(_session_dir(session_id), exist_ok=True)
    db_session = SessionLocal()
    try:
        build_workbook_from_db(db_session, _input_path(session_id))
        info = get_file_info(_input_path(session_id))
    except Exception as e:
        shutil.rmtree(_session_dir(session_id), ignore_errors=True)
        raise HTTPException(422, f"Could not build inputs from database: {e}")
    finally:
        db_session.close()
    open(os.path.join(_session_dir(session_id), ".from_db"), "w").close()  # marks provenance for /api/run
    return {"session_id": session_id, "from_db": True, **info}


@router.get("/api/config/base-sales-reindexed")
def base_sales_reindexed():
    """The OTHER LFL base-sales source for ReviewStep's actuals-source toggle:
    Calendar Engine's own saved month-wise reindex output, not AOP's own
    independent replica of that same day-shift logic (see
    db/reindexed_base_sales.py for why these are two genuinely different
    computations today, not just two names for the same thing). Stateless -
    doesn't need a session_id, reads straight from the DB."""
    from db.base import SessionLocal
    from db.reindexed_base_sales import get_reindexed_lfl_base_sales

    db_session = SessionLocal()
    try:
        return get_reindexed_lfl_base_sales(db_session)
    finally:
        db_session.close()


@router.get("/api/config/aop-division-targets")
def aop_division_targets():
    """Latest MENS/LADIES/KIDS MAMJ targets published after the most recent
    forecast run.  Used by the Buyer's Input Sheet for live auto-sync — no
    authentication required (reads only, no user-specific data)."""
    from db.base import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT row_key, period_id, value, updated_at
            FROM planning_inputs.input_values
            WHERE lever_key = 'aop_division_target'
              AND row_key   IN ('MENS','LADIES','KIDS')
              AND period_id IN (202703,202704,202705,202706)
            ORDER BY row_key, period_id
        """)).all()

        if not rows:
            return {"targets": None, "published_at": None,
                    "note": "No AOP forecast has been run yet."}

        targets: dict[str, dict[int, float]] = {
            "MENS": {}, "LADIES": {}, "KIDS": {}
        }
        published_at = None
        for div, period_id, value, updated_at in rows:
            targets[div][period_id] = float(value or 0)
            if published_at is None or updated_at > published_at:
                published_at = updated_at

        return {
            "targets": targets,
            "published_at": published_at.isoformat() if published_at else None,
            "note": None,
        }
    finally:
        db.close()


@router.post("/api/config/buyer-department-growth")
def post_buyer_department_growth(body: dict = Body(...)):
    """Live push from Buyer's Input Sheet (otb-plan-app.html) after every
    save — feeds SalesPlan's Department Growth Matrix (see
    db/buyer_department_growth.py). Unauthenticated on this standalone port,
    same reasoning as /api/config/aop-division-targets: BIS has no server of
    its own with a DB session, its browser JS calls straight here."""
    from db.base import SessionLocal
    from db.buyer_department_growth import upsert_buyer_growth

    rows = body.get("rows") or []
    db = SessionLocal()
    try:
        updated = upsert_buyer_growth(db, rows)
        return {"ok": True, "updated": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/api/config/buyer-department-growth")
def get_buyer_department_growth(division: str | None = None):
    """Read side for SalesPlan's Department Growth Matrix — optionally
    scoped to one division (?division=MENS)."""
    from db.base import SessionLocal
    from db.buyer_department_growth import get_buyer_growth

    db = SessionLocal()
    try:
        return {"rows": get_buyer_growth(db, division)}
    finally:
        db.close()


@router.post("/api/promote-aop-targets")
def promote_aop_targets_endpoint():
    """Promote current staging AOP targets → locked, making them visible to the
    Planning Engine as the approved version."""
    from db.base import SessionLocal
    from db.publish_aop_targets import promote_aop_targets
    from fastapi import HTTPException
    db = SessionLocal()
    try:
        result = promote_aop_targets(db)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("reason", "Promote failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/api/aop-publish-history")
def aop_publish_history(limit: int = 20):
    """List available AOP publish history so the Planning Engine can show a
    version picker.  Returns newest-first; includes division MAMJ totals so
    the UI can display ₹Cr without a second call."""
    from db.base import SessionLocal
    from db.publish_aop_targets import list_aop_history
    db = SessionLocal()
    try:
        return {"versions": list_aop_history(db, limit=limit)}
    finally:
        db.close()


@router.post("/api/promote-aop-version/{version_id}")
def promote_aop_version(version_id: int):
    """Promote a specific historical AOP publish (by id) to aop_locked_target.
    The Planning Engine reads aop_locked_target as its stable approved version."""
    from db.base import SessionLocal
    from db.publish_aop_targets import promote_from_history
    db = SessionLocal()
    try:
        result = promote_from_history(db, version_id)
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result.get("reason", "Version not found"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/api/unlock-aop-targets")
def unlock_aop_targets_endpoint():
    """Undo a promote: clear aop_locked_target so the Planning Engine falls
    back to reading live staging targets (aop_division_target) again. Safe to
    call any time — a later "Promote to Planning" just re-locks from whatever
    staging holds at that point."""
    from db.base import SessionLocal
    from db.publish_aop_targets import unlock_aop_targets
    db = SessionLocal()
    try:
        return unlock_aop_targets(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/api/aop-lock-status")
def aop_lock_status():
    """Returns whether staging AOP targets have been promoted (locked) for the
    Planning Engine, and when."""
    from db.base import SessionLocal
    from sqlalchemy import text
    db = SessionLocal()
    try:
        locked_rows = db.execute(text("""
            SELECT row_key, period_id, value, updated_at
            FROM planning_inputs.input_values
            WHERE lever_key = 'aop_locked_target'
              AND row_key   IN ('MENS','LADIES','KIDS')
              AND period_id IN (202703,202704,202705,202706)
            ORDER BY row_key, period_id
        """)).all()

        if not locked_rows:
            return {"locked": False, "locked_at": None,
                    "total_mamj_lakhs": 0, "divisions": {}}

        locked_at = None
        by_div: dict[str, float] = {}
        for div, _pid, value, updated_at in locked_rows:
            by_div[div] = by_div.get(div, 0.0) + float(value or 0)
            if locked_at is None or updated_at > locked_at:
                locked_at = updated_at

        return {
            "locked": True,
            "locked_at": locked_at.isoformat() if locked_at else None,
            "total_mamj_lakhs": round(sum(by_div.values()), 2),
            "divisions": {d: round(v, 2) for d, v in by_div.items()},
        }
    finally:
        db.close()


DB_SYNC_JOBS = [
    ("site_master", "data_lake_site_master"),
    ("store_master_xlsx", "store_master_xlsx"),
    ("day_shift", "data_lake_day_shift"),
    ("store_actuals", "data_lake_sales"),
    # Runs Calendar Engine's own month-wise reindex (with ATTRIBUTE1) as a
    # subprocess and saves it to calendar.sales_snapshots - keeps the
    # "Calendar Engine Reindex" actuals-source toggle (ReviewStep.jsx) and
    # the Q1 attribute filter fed without a separate manual trip to the
    # Calendar Engine tab. Runs on every sync, same as the jobs above - see
    # sync/calendar_reindex_sync.py's docstring for why (confirmed with the
    # user, not a staleness-check).
    ("calendar_reindex", "calendar_reindex"),
]


@router.post("/api/config/db-sync")
def db_sync_all():
    """Spawns sync/run_all.py as a detached subprocess and returns immediately.
    Running the sync in-process blocked uvicorn's request thread for 2+ minutes
    (store_actuals reads a large parquet file) making the server appear hung.
    Progress is logged to sync.sync_runs — poll GET /api/config/db-sync/status."""
    import subprocess
    import sys
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync", "run_all.py")
    # DETACHED_PROCESS + CREATE_NO_WINDOW on Windows: subprocess runs without
    # inheriting our console and doesn't die when uvicorn restarts.
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [sys.executable, script],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **kwargs,
    )
    return {"status": "started", "message": "Sync running in background — poll /api/config/db-sync/status for progress"}


@router.get("/api/config/db-sync/status")
def db_sync_status():
    """Latest sync.sync_runs row per source, for display."""
    from sqlalchemy import select, func
    from db.base import SessionLocal
    from db.models.sync import SyncRun

    with SessionLocal() as session:
        latest_ids = session.execute(
            select(func.max(SyncRun.sync_run_id)).group_by(SyncRun.source_key)
        ).scalars().all()
        if not latest_ids:
            return {"runs": []}
        runs = session.execute(select(SyncRun).where(SyncRun.sync_run_id.in_(latest_ids))).scalars().all()

        # For offline runs, also fetch the last successful run timestamp so the UI
        # can show "last synced X ago" even when the most recent attempt was offline.
        offline_keys = [r.source_key for r in runs if r.status == "offline"]
        last_success = {}
        if offline_keys:
            success_ids = session.execute(
                select(func.max(SyncRun.sync_run_id))
                .where(SyncRun.source_key.in_(offline_keys), SyncRun.status == "success")
                .group_by(SyncRun.source_key)
            ).scalars().all()
            if success_ids:
                success_runs = session.execute(
                    select(SyncRun).where(SyncRun.sync_run_id.in_(success_ids))
                ).scalars().all()
                last_success = {r.source_key: r.completed_at.isoformat() if r.completed_at else None
                                for r in success_runs}

        return {"runs": [
            {"source_key": r.source_key, "status": r.status, "started_at": r.started_at.isoformat(),
             "completed_at": r.completed_at.isoformat() if r.completed_at else None,
             "rows_read": r.rows_read, "rows_updated": r.rows_updated, "rows_added": r.rows_added,
             "error_message": r.error_message, "detail": r.detail,
             "last_success_at": last_success.get(r.source_key)}
            for r in sorted(runs, key=lambda r: r.source_key)
        ]}


@router.get("/api/config/growth")
def get_growth_config():
    """Growth % grid: OVERALL + 5 divisions x Apr'27..Mar'28. Postgres-backed
    replacement for the removed LeverEditor's Growth % tab."""
    from db.base import SessionLocal
    from db.editor import get_growth

    with SessionLocal() as session:
        return get_growth(session)


@router.put("/api/config/growth")
def put_growth_config(request: Request, body: dict = Body(...)):
    from db.base import SessionLocal
    from db.editor import put_growth

    actor_id, actor_role = _get_actor(request)
    with SessionLocal() as session:
        try:
            return put_growth(session, body.get("rows") or [], actor_id, actor_role)
        except Exception as e:
            raise HTTPException(422, f"Could not save growth rates: {e}")


@router.get("/api/config/nso")
def get_nso_config():
    """NSO Opening Months (unnamed + Named NSO), unified. Postgres-backed
    replacement for the removed LeverEditor's NSO tabs."""
    from db.base import SessionLocal
    from db.editor import get_nso

    with SessionLocal() as session:
        return get_nso(session)


@router.put("/api/config/nso")
def put_nso_config(request: Request, body: dict = Body(...)):
    """Full-table replace: rows not included are deleted (see db/editor.py)."""
    from db.base import SessionLocal
    from db.editor import put_nso

    actor_id, actor_role = _get_actor(request)
    with SessionLocal() as session:
        try:
            return put_nso(session, body.get("rows") or [], actor_id, actor_role)
        except Exception as e:
            raise HTTPException(422, f"Could not save NSO openings: {e}")


@router.get("/api/config/aop-overrides")
def get_aop_overrides_config():
    """AOP (Optional) overrides — sparse store x division x month. Postgres-
    backed replacement for the removed LeverEditor's AOP tab."""
    from db.base import SessionLocal
    from db.editor import get_aop_overrides

    with SessionLocal() as session:
        return get_aop_overrides(session)


@router.put("/api/config/aop-overrides")
def put_aop_overrides_config(request: Request, body: dict = Body(...)):
    """Delta editor: only listed rows are touched; a null value deletes that
    override (see db/editor.py)."""
    from db.base import SessionLocal
    from db.editor import put_aop_overrides

    actor_id, actor_role = _get_actor(request)
    with SessionLocal() as session:
        try:
            return put_aop_overrides(session, body.get("rows") or [], actor_id, actor_role)
        except Exception as e:
            raise HTTPException(422, f"Could not save AOP overrides: {e}")


@router.post("/api/config/aop-overrides/import")
async def import_aop_overrides_config(file: UploadFile = File(...)):
    """Parses a CSV/XLSX (Store, Division, Month, Value columns) - does NOT
    write to the DB. Returns rows in the same shape put_aop_overrides()
    accepts, so AopTab merges them into its existing edits/review state and
    the user still clicks "Save changes" to commit, same as any manual edit
    - see db/editor.py's parse_aop_overrides_import() for why a bulk import
    doesn't get to skip that review step."""
    from db.base import SessionLocal
    from db.editor import parse_aop_overrides_import

    content = await file.read()
    with SessionLocal() as session:
        try:
            return parse_aop_overrides_import(session, content, file.filename or "")
        except ValueError as e:
            raise HTTPException(422, str(e))
        except Exception as e:
            raise HTTPException(422, f"Could not parse file: {e}")


@router.get("/api/config/store-master")
def get_store_master_config():
    """Current store records with planning attributes (tag, cluster, ref_store etc.)."""
    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.masterdata import Store

    with SessionLocal() as session:
        rows = session.execute(
            select(Store).where(Store.valid_to.is_(None)).order_by(Store.store_id)
        ).scalars().all()
        return [
            {
                "store_id": r.store_id,
                "store_name": r.store_name,
                "tag": r.tag,
                "cluster_key": r.cluster_key,
                "ref_store": r.ref_store,
                "region_type": r.region_type,
                "store_grade": r.store_grade,
                "gm_grade": r.gm_grade,
                "erp_cluster_type": r.erp_cluster_type,
                "store_status": r.store_current_status,
                "festival_grouping": r.festival_grouping,
            }
            for r in rows
        ]


def _invalidate_salesplan_store_cache():
    """SalesPlan's store_master.py (SalesPlan/backend/store_master.py)
    @lru_cache's its store list for the whole process lifetime — under the
    unified backend (sys.path includes SalesPlan/backend/), a ref_store/tag/
    cluster edit made here would otherwise sit invisible to SalesPlan's
    engines until someone hits its own reload endpoint or the whole process
    restarts. Best-effort + no-op on AOP's standalone port (8000), where
    SalesPlan isn't on sys.path at all — never let this fail the actual save."""
    try:
        import store_master as _salesplan_store_master
        _salesplan_store_master.reload()
    except ImportError:
        pass


@router.put("/api/config/store-master")
def put_store_master_config(body: dict = Body(...)):
    """Update editable planning fields (tag, cluster_key, ref_store) on current store rows."""
    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.masterdata import Store, RefStoreChangeLog

    rows = body.get("rows") or []
    with SessionLocal() as session:
        updated = 0
        for row in rows:
            store_id = row.get("store_id")
            if not store_id:
                continue
            current = session.execute(
                select(Store).where(Store.store_id == store_id, Store.valid_to.is_(None))
            ).scalar_one_or_none()
            if current:
                if "ref_store" in row:
                    new_ref = row["ref_store"] if row["ref_store"] != "" else None
                    # Logged BEFORE the mutation below overwrites current.ref_store -
                    # this is the only history a ref_store change gets (Store's own
                    # effective-dating isn't used for this field, see the model's
                    # docstring), so a no-op "save" with an unchanged value must
                    # never write a row here, or Revert would have to skip past its
                    # own noise to find the real prior value.
                    if new_ref != current.ref_store:
                        session.add(RefStoreChangeLog(
                            store_id=store_id, old_ref_store=current.ref_store, new_ref_store=new_ref,
                        ))
                for field in ("tag", "cluster_key", "ref_store"):
                    if field in row:
                        setattr(current, field, row[field] if row[field] != "" else None)
                updated += 1
        session.commit()
        _invalidate_salesplan_store_cache()
        return {"updated": updated}


@router.get("/api/config/ref-store-log")
def get_ref_store_log(store_id: Optional[str] = None, limit: int = 200):
    """Change history for stores.ref_store, most recent first - powers the Ref
    Store Mapping tab's Change Log (old value, new value, when) and its
    per-store Revert action."""
    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.masterdata import RefStoreChangeLog

    with SessionLocal() as session:
        q = select(RefStoreChangeLog)
        if store_id:
            q = q.where(RefStoreChangeLog.store_id == store_id)
        q = q.order_by(RefStoreChangeLog.changed_at.desc()).limit(limit)
        rows = session.execute(q).scalars().all()
        return {"entries": [
            {"id": r.id, "storeId": r.store_id, "oldRefStore": r.old_ref_store,
             "newRefStore": r.new_ref_store, "changedAt": r.changed_at.isoformat() if r.changed_at else None}
            for r in rows
        ]}


@router.get("/api/config/store-division-mix")
def get_store_division_mix(store_ids: str):
    """Division sales mix % for a comma-separated list of store_ids, computed
    from planning_inputs.input_values (lever_key='store_actuals' - the same
    FY27 base-sales data a ref store's forecast pattern actually feeds into,
    see nso_ramp()/pass1b_ramp_forecasts in engine_v3.py). Powers the Ref
    Store Mapping tab's drill-down: does this store's own division mix look
    more like the new buddy's than the old one's, as a quick sanity check on
    the reassignment - not a claim about which buddy is objectively "right",
    just the same data the forecast itself will lean on."""
    from sqlalchemy import select, func as sa_func
    from db.base import SessionLocal
    from db.models.planning_inputs import InputValue

    ids = [s.strip() for s in (store_ids or "").split(",") if s.strip()]
    if not ids:
        return {"stores": {}}
    with SessionLocal() as session:
        rows = session.execute(
            select(InputValue.store_id, InputValue.division_code, sa_func.sum(InputValue.value))
            .where(InputValue.lever_key == "store_actuals", InputValue.store_id.in_(ids))
            .group_by(InputValue.store_id, InputValue.division_code)
        ).all()
    by_store = {}
    totals = {}
    for store_id, div, val in rows:
        v = float(val or 0)
        by_store.setdefault(store_id, {})[div or "(none)"] = v
        totals[store_id] = totals.get(store_id, 0.0) + v
    result = {}
    for store_id, divs in by_store.items():
        total = totals[store_id] or 1.0
        result[store_id] = {"totalLakhs": round(total, 2), "mix": {d: round(100 * v / total, 1) for d, v in divs.items()}}
    return {"stores": result}


@router.delete("/api/config/store-master/untagged")
def delete_untagged_stores():
    """Remove all active store rows that have no tag (closed / unused system records)."""
    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.masterdata import Store
    from datetime import datetime, timezone

    with SessionLocal() as session:
        rows = session.execute(
            select(Store).where(
                Store.valid_to.is_(None),
                (Store.tag.is_(None) | (Store.tag == ""))
            )
        ).scalars().all()
        now = datetime.now(timezone.utc)
        for store in rows:
            store.valid_to = now
        session.commit()
        _invalidate_salesplan_store_cache()
        return {"deleted": len(rows)}


@router.get("/api/config/division-aop-summary")
def division_aop_summary():
    """Latest persisted run's division-level annual AOP target (Rs Lakhs),
    Apr'27..Mar'28 (next fiscal year only — Mar'27 is this year's last actual
    month, not part of the plan). Consumed by SalesPlan's Department Plan
    (POST /api/department-plan/calculate expects exactly this {division,
    annual_target} shape) via its own sync-from-aop-forecaster endpoint."""
    from sqlalchemy import select, func
    from db.base import SessionLocal
    from db.models.engine import ForecastResult, ForecastRun
    from db.models.planning_inputs import Period

    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "RS Planning Platform", "backend"))
    from workflow.service import latest_approved_cycle

    with SessionLocal() as session:
        cycle = latest_approved_cycle(session)
        if cycle is None or cycle.current_run_id is None:
            raise HTTPException(404, "No approved plan cycle yet")
        run_id = cycle.current_run_id
        latest = session.get(ForecastRun, run_id)

        if cycle.buyer_adjusted_totals:
            return {
                "run_id": str(latest.run_id), "computed_at": latest.created_at.isoformat(),
                "division_aops": [{"division": d, "annual_target": v} for d, v in cycle.buyer_adjusted_totals.items()],
            }

        # FY28 = Apr'27..Mar'28 (engine_v3.FY28_M minus its leading Mar'27, which
        # is this year's last actual month, not part of the plan being AOP'd)
        next_fy_labels = {"Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                          "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"}
        next_fy_periods = {
            p.period_id for p in session.execute(select(Period)).scalars().all()
            if p.label in next_fy_labels
        }
        rows = session.execute(
            select(ForecastResult.division_code, func.sum(ForecastResult.value))
            .where(ForecastResult.run_id == latest.run_id, ForecastResult.metric_key == "forecast",
                   ForecastResult.period_id.in_(next_fy_periods))
            .group_by(ForecastResult.division_code)
        ).all()
        return {
            "run_id": str(latest.run_id), "computed_at": latest.created_at.isoformat(),
            "division_aops": [{"division": div, "annual_target": round(float(total), 2)} for div, total in rows],
        }


def _division_totals_for_run(session, run_id) -> dict:
    # Local imports (matching division_aop_summary's own pattern above): this
    # module has no module-level sqlalchemy/db.models imports, so select/func/
    # Period/ForecastResult must be bound here rather than assumed in scope.
    from sqlalchemy import select, func
    from db.models.engine import ForecastResult
    from db.models.planning_inputs import Period

    next_fy_labels = {"Apr'27", "May'27", "Jun'27", "Jul'27", "Aug'27", "Sep'27",
                      "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"}
    next_fy_periods = {
        p.period_id for p in session.execute(select(Period)).scalars().all()
        if p.label in next_fy_labels
    }
    rows = session.execute(
        select(ForecastResult.division_code, func.sum(ForecastResult.value))
        .where(ForecastResult.run_id == run_id, ForecastResult.metric_key == "forecast",
               ForecastResult.period_id.in_(next_fy_periods))
        .group_by(ForecastResult.division_code)
    ).all()
    return {div: round(float(total), 2) for div, total in rows}


@router.get("/api/config/recent-runs")
def recent_runs():
    """Lists recent ForecastRuns for the planner's "submit for buyer review"
    picker in plan-cycles.html — nothing else in this app lists runs by id."""
    from sqlalchemy import select, func, desc
    from db.base import SessionLocal
    from db.models.engine import ForecastRun

    with SessionLocal() as session:
        runs = session.execute(select(ForecastRun).order_by(desc(ForecastRun.created_at)).limit(20)).scalars().all()
        return [
            {"run_id": str(r.run_id), "created_at": r.created_at.isoformat(), "status": r.status,
             "division_totals": _division_totals_for_run(session, r.run_id)}
            for r in runs
        ]


@router.get("/api/config/runs/{run_id}/division-totals")
def run_division_totals(run_id: str):
    """The buyer tab's totals source (Buyer's Input Sheet's AOP Review tab) -
    a cycle's current_run_id isn't guaranteed to still be within recent-runs'
    20-row window, so it looks a specific run up directly instead."""
    import uuid as _uuid
    from sqlalchemy import select
    from db.base import SessionLocal
    from db.models.engine import ForecastRun

    with SessionLocal() as session:
        run = session.get(ForecastRun, _uuid.UUID(run_id))
        if run is None:
            raise HTTPException(404, "Run not found")
        return {"run_id": run_id, "division_totals": _division_totals_for_run(session, run.run_id)}


# ── Plan Version Log (cross-machine, persisted in DB) ────────────────────────
# Versions were previously in localStorage — machine-local only. Storing them
# here means every machine that reaches this server sees the same version list.

_plan_versions_ready = False

def _ensure_plan_versions_table():
    global _plan_versions_ready
    if _plan_versions_ready:
        return
    from sqlalchemy import text
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS planning_inputs.plan_versions (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                last_modified_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        db.commit()
    _plan_versions_ready = True


@router.get("/api/plan-versions")
def get_plan_versions():
    _ensure_plan_versions_table()
    from sqlalchemy import text
    from db.base import SessionLocal
    with SessionLocal() as db:
        rows = db.execute(text(
            "SELECT data FROM planning_inputs.plan_versions "
            "ORDER BY last_modified_at DESC LIMIT 10"
        )).fetchall()
    return [row[0] for row in rows]


@router.post("/api/plan-versions")
def upsert_plan_version(body: dict = Body(...)):
    _ensure_plan_versions_table()
    if "id" not in body:
        raise HTTPException(400, "id required")
    from sqlalchemy import text
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text("""
            INSERT INTO planning_inputs.plan_versions (id, data, last_modified_at)
            VALUES (:id, CAST(:data AS jsonb), NOW())
            ON CONFLICT (id) DO UPDATE SET
                data = CAST(:data AS jsonb), last_modified_at = NOW()
        """), {"id": body["id"], "data": json.dumps(body)})
        db.commit()
    return {"ok": True}


@router.delete("/api/plan-versions/{version_id}")
def delete_plan_version(version_id: str):
    _ensure_plan_versions_table()
    from sqlalchemy import text
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text(
            "DELETE FROM planning_inputs.plan_versions WHERE id = :id"
        ), {"id": version_id})
        db.commit()
    return {"ok": True}


# Mount the extracted router onto this standalone app too — same routes,
# same paths, as before the extraction. The unified platform (RS Planning
# Platform/backend/app.py) imports `router` directly instead and mounts it
# under /api/aop with an auth dependency; this standalone `app` stays
# unprotected, for standalone use.
app.include_router(router)

# ── Serve built React app (must be last) ─────────────────────────────────────
_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    # index.html is requested by a bare, unchanging path - unlike the hashed
    # JS/CSS under /assets (safe to cache forever, since a rebuild changes
    # the filename), a cached index.html can keep serving a build from
    # before the last code change even after a normal reload. Explicit
    # no-store makes every reload behave like a hard reload here.
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        return FileResponse(os.path.join(_dist, "index.html"),
                             headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})
