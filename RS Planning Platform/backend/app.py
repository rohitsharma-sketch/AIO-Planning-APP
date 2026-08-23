"""RS Planning Platform — unified backend. Port 8010.
Mounts AOP Forecaster + SalesPlan's existing routers, adds auth/workflow/audit."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_AOP_DIR = os.path.join(_HERE, "..", "..", "Tentative AOP Forecaster")
_SALESPLAN_DIR = os.path.join(_HERE, "..", "..", "SalesPlan", "backend")
sys.path.insert(0, _HERE)
sys.path.insert(0, _AOP_DIR)
sys.path.insert(0, _SALESPLAN_DIR)

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auth.deps import require_login
from auth.routes import router as auth_router
from workflow.routes import router as workflow_router
from audit.routes import router as audit_router

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me")

app = FastAPI(title="RS Planning Platform")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router, prefix="/api/auth")
app.include_router(workflow_router, prefix="/api/aop/plan-cycles")
app.include_router(audit_router, prefix="/api/audit")

# AOP Forecaster — its own app.py's `router` (extracted for this purpose),
# protected here. This file is ALSO named app.py (uvicorn entrypoint
# `app:app` requires that), so a plain `from app import router` would
# collide: uvicorn pre-registers sys.modules['app'] as *this* file before
# executing it, so a same-named import resolves to itself, not AOP
# Forecaster's module. Load AOP's app.py explicitly under a distinct
# module name to sidestep the collision.
import importlib.util as _ilu  # noqa: E402

_aop_spec = _ilu.spec_from_file_location("aop_forecaster_app", os.path.join(_AOP_DIR, "app.py"))
_aop_module = _ilu.module_from_spec(_aop_spec)
sys.modules["aop_forecaster_app"] = _aop_module
_aop_spec.loader.exec_module(_aop_module)
aop_router = _aop_module.router
app.include_router(aop_router, prefix="/api/aop", dependencies=[Depends(require_login)])

# SalesPlan — its 11 existing routers, re-mounted with their own prefixes under /api/planning
from engines.division_plan import router as division_plan_router  # noqa: E402
from engines.department_plan import router as department_plan_router  # noqa: E402
from engines.dept_sales_engine import router as dept_sales_router  # noqa: E402
from engines.attribute_correction_engine import router as attr_correction_router  # noqa: E402
from engines.base_correction_engine import router as base_correction_router  # noqa: E402
from engines.final_results_engine import router as final_results_router  # noqa: E402
from engines.mrp_plan_engine import router as mrp_plan_router  # noqa: E402
from engines.pww_deviation_engine import router as pww_deviation_router  # noqa: E402
from engines.sor_deviation_engine import router as sor_deviation_router  # noqa: E402
from engines.display_type_engine import router as display_type_router  # noqa: E402
from engines.sync_engine import router as sync_router  # noqa: E402
import store_master as _sm  # noqa: E402

_dep = [Depends(require_login)]
app.include_router(division_plan_router,   prefix="/api/planning/division-plan",   dependencies=_dep)
app.include_router(department_plan_router, prefix="/api/planning/department-plan", dependencies=_dep)
app.include_router(dept_sales_router,      prefix="/api/planning/dept-sales",      dependencies=_dep)
app.include_router(attr_correction_router, prefix="/api/planning/attr-correction", dependencies=_dep)
app.include_router(base_correction_router, prefix="/api/planning/base-correction", dependencies=_dep)
app.include_router(final_results_router,   prefix="/api/planning/final-results",   dependencies=_dep)
app.include_router(mrp_plan_router,        prefix="/api/planning/mrp-plan",        dependencies=_dep)
app.include_router(pww_deviation_router,   prefix="/api/planning/deviation/pww",   dependencies=_dep)
app.include_router(sor_deviation_router,   prefix="/api/planning/deviation/sor",   dependencies=_dep)
app.include_router(display_type_router,    prefix="/api/planning/display-type",    dependencies=_dep)
app.include_router(sync_router,            prefix="/api/planning/sync",            dependencies=_dep)


@app.get("/api/planning/store-master", dependencies=_dep)
def get_store_master():
    return {"stores": list(_sm.load_store_master()), "clusters": _sm.get_clusters()}


@app.post("/api/planning/store-master/reload", dependencies=_dep)
def reload_store_master():
    _sm.reload()
    return {"ok": True, "stores": len(list(_sm.load_store_master())), "clusters": _sm.get_clusters()}


# Login page (plain HTML — Phase 2's unified frontend replaces this)
@app.get("/login")
def login_page():
    return FileResponse(os.path.join(_HERE, "static", "login.html"))


# Serve both existing frontends' built bundles under their own paths
_aop_dist = os.path.join(_AOP_DIR, "frontend", "dist")
if os.path.isdir(_aop_dist):
    app.mount("/aop/assets", StaticFiles(directory=os.path.join(_aop_dist, "assets")), name="aop_assets")

_planning_dist = os.path.join(os.path.dirname(_SALESPLAN_DIR), "frontend", "dist")
if os.path.isdir(_planning_dist):
    app.mount("/planning/assets", StaticFiles(directory=os.path.join(_planning_dist, "assets")), name="planning_assets")


@app.get("/aop/{full_path:path}", include_in_schema=False)
def aop_spa(full_path: str):
    return FileResponse(os.path.join(_aop_dist, "index.html"))


@app.get("/planning/{full_path:path}", include_in_schema=False)
def planning_spa(full_path: str):
    return FileResponse(os.path.join(_planning_dist, "index.html"))
