import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from engines.division_plan import router as division_plan_router
from engines.department_plan import router as department_plan_router
from engines.dept_sales_engine import router as dept_sales_router
from engines.attribute_correction_engine import router as attr_correction_router
from engines.base_correction_engine import router as base_correction_router
from engines.final_results_engine import router as final_results_router
from engines.mrp_plan_engine import router as mrp_plan_router
from engines.pww_deviation_engine import router as pww_deviation_router
from engines.sor_deviation_engine import router as sor_deviation_router
from engines.display_type_engine import router as display_type_router
from engines.sync_engine import router as sync_router

import store_master as _sm

app = FastAPI(title="Sales Plan API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(division_plan_router,   prefix="/api/division-plan")
app.include_router(department_plan_router, prefix="/api/department-plan")
app.include_router(dept_sales_router,      prefix="/api/dept-sales")
app.include_router(attr_correction_router, prefix="/api/attr-correction")
app.include_router(base_correction_router, prefix="/api/base-correction")
app.include_router(final_results_router,   prefix="/api/final-results")
app.include_router(mrp_plan_router,        prefix="/api/mrp-plan")

@app.get("/api/store-master")
def get_store_master():
    return {"stores": list(_sm.load_store_master()), "clusters": _sm.get_clusters()}

@app.post("/api/store-master/reload")
def reload_store_master():
    _sm.reload()
    stores = list(_sm.load_store_master())
    return {"ok": True, "stores": len(stores), "clusters": _sm.get_clusters()}
app.include_router(pww_deviation_router,   prefix="/api/deviation/pww")
app.include_router(sor_deviation_router,   prefix="/api/deviation/sor")
app.include_router(display_type_router,    prefix="/api/display-type")
app.include_router(sync_router,            prefix="/api/sync")

# Serve the built React frontend — mount after all API routes
_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        return FileResponse(os.path.join(_DIST, "index.html"))
