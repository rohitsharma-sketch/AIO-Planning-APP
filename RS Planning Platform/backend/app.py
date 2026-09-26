"""RS Planning Platform — unified backend. Port 8010.
Mounts AOP Forecaster + SalesPlan's existing routers, adds auth/workflow/audit."""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_AOP_DIR = os.path.join(_HERE, "..", "..", "Tentative AOP Forecaster")
_SALESPLAN_DIR = os.path.join(_HERE, "..", "..", "SalesPlan", "backend")
sys.path.insert(0, _HERE)
sys.path.insert(0, _AOP_DIR)
sys.path.insert(0, _SALESPLAN_DIR)

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from auth.deps import get_session_user, require_login
from auth.routes import router as auth_router
from workflow.routes import router as workflow_router
from audit.routes import router as audit_router

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-only-change-me")

app = FastAPI(title="RS Planning Platform")
# max_age=None -> a browser-session-only cookie (no Max-Age/Expires), so a
# plain login ends when the browser closes. Longer persistence on the same
# machine is opt-in via the separate "remember me" cookie (auth/deps.py),
# not the default for every login.
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router, prefix="/api/auth")
app.include_router(workflow_router, prefix="/api/aop/plan-cycles")
app.include_router(audit_router, prefix="/api/audit")

from calendar_engine.router import router as calendar_router  # noqa: E402

app.include_router(calendar_router, prefix="/api/calendar", dependencies=[Depends(require_login)])

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


LANDING_PAGE_URL = "/"


# No-cache HTML entry points — every page below is either an auth screen or
# an SPA's index.html. Unlike the hashed JS/CSS under */assets (safe to cache
# forever: a rebuild changes the filename, so there's never a staleness
# risk), these get requested by their bare, unchanging path - a browser that
# caches them can keep serving a build from before the last code change even
# after a normal reload, and only a genuine hard-reload (which most users
# don't know to do) forces a re-fetch. Explicit no-store makes every reload
# behave like a hard reload for these specific paths. Confirmed with the
# user 2026-08-27: "make sure from now on for any app i want changes to be
# reflected if i hard reload the landing page."
_NO_CACHE_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}


def _html_no_cache(path: str) -> FileResponse:
    return FileResponse(path, headers=_NO_CACHE_HEADERS)


# Suite colour theme (user, 2026-09-26): ONE choice for every app, picked on
# Landing. Palettes live in static/suite-themes.json; the choice in
# data/suite_theme.json (local state, gitignored). The script GET is public -
# each app (even on the login screen) loads it before first paint.
_THEMES_FILE = os.path.join(_HERE, "static", "suite-themes.json")
_THEME_CHOICE = os.path.join(_HERE, "data", "suite_theme.json")


def _suite_themes() -> dict:
    with open(_THEMES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _suite_theme_choice(themes: dict) -> str:
    try:
        with open(_THEME_CHOICE, encoding="utf-8") as f:
            choice = json.load(f).get("theme")
    except (OSError, ValueError):
        choice = None
    return choice if choice in themes["themes"] else themes["default"]


@app.get("/api/suite-theme.js", include_in_schema=False)
def suite_theme_js():
    themes = _suite_themes()
    with open(os.path.join(_HERE, "static", "suite-theme.js"), encoding="utf-8") as f:
        runtime = f.read()
    body = (f"window.__SUITE_THEMES__={json.dumps(themes)};"
            f"window.__SUITE_THEME__={json.dumps(_suite_theme_choice(themes))};\n{runtime}")
    return Response(body, media_type="application/javascript", headers=_NO_CACHE_HEADERS)


@app.post("/api/suite-theme")
def save_suite_theme(payload: dict, user: dict = Depends(require_login)):
    themes = _suite_themes()
    theme = payload.get("theme")
    if theme not in themes["themes"]:
        raise HTTPException(400, f"Unknown theme {theme!r}")
    os.makedirs(os.path.dirname(_THEME_CHOICE), exist_ok=True)
    with open(_THEME_CHOICE, "w", encoding="utf-8") as f:
        json.dump({"theme": theme, "by": user.get("username") or user.get("email")}, f)
    return {"theme": theme}


# Bare root has no page of its own — route by session state instead of 404ing.
@app.get("/")
def root(request: Request):
    user = get_session_user(request)
    if user is not None:
        if user.get("must_change_password"):
            return RedirectResponse("/change-password")
        return RedirectResponse(LANDING_PAGE_URL)
    return RedirectResponse("/login")


# Login page (plain HTML — Phase 2's unified frontend replaces this)
@app.get("/login")
def login_page(request: Request):
    # Already authenticated (real session, or a "remember me" cookie from a
    # prior visit on this device) — skip the form instead of asking again.
    user = get_session_user(request)
    if user is not None:
        if user.get("must_change_password"):
            return RedirectResponse("/change-password")
        return RedirectResponse(LANDING_PAGE_URL)
    return _html_no_cache(os.path.join(_HERE, "static", "login.html"))


@app.get("/change-password")
def change_password_page(request: Request):
    # Reachable by anyone with a valid session (not just must_change_password
    # accounts) — a logged-in user can always choose to change their own
    # password, this isn't exclusively the forced-reset screen.
    if get_session_user(request) is None:
        return RedirectResponse("/login?next=/change-password")
    return _html_no_cache(os.path.join(_HERE, "static", "change-password.html"))


@app.get("/reset-password")
def reset_password_page():
    # No auth gate — a valid ?token= IS the credential, checked/expired
    # server-side by /api/auth/reset-password (auth/security.py's
    # RESET_MAX_AGE). Getting here with no or a stale token still renders
    # the page; the form submit is what surfaces "invalid or expired".
    return _html_no_cache(os.path.join(_HERE, "static", "reset-password.html"))


@app.get("/plan-cycles")
def plan_cycles_page(request: Request):
    if get_session_user(request) is None:
        return RedirectResponse(f"/login?next=/plan-cycles")
    return _html_no_cache(os.path.join(_HERE, "static", "plan-cycles.html"))


# Serve both existing frontends' built bundles under their own paths
_aop_dist = os.path.join(_AOP_DIR, "frontend", "dist")
if os.path.isdir(_aop_dist):
    app.mount("/aop/assets", StaticFiles(directory=os.path.join(_aop_dist, "assets")), name="aop_assets")

_planning_dist = os.path.join(os.path.dirname(_SALESPLAN_DIR), "frontend", "dist")
if os.path.isdir(_planning_dist):
    app.mount("/planning/assets", StaticFiles(directory=os.path.join(_planning_dist, "assets")), name="planning_assets")

_calendar_dist = os.path.join(_HERE, "..", "..", "Calendar Engine", "frontend", "dist")
if os.path.isdir(_calendar_dist):
    app.mount("/calendar/assets", StaticFiles(directory=os.path.join(_calendar_dist, "assets")), name="calendar_assets")


@app.get("/aop/{full_path:path}", include_in_schema=False)
def aop_spa(full_path: str, request: Request):
    if get_session_user(request) is None:
        return RedirectResponse(f"/login?next=/aop/")
    return _html_no_cache(os.path.join(_aop_dist, "index.html"))


@app.get("/planning/{full_path:path}", include_in_schema=False)
def planning_spa(full_path: str, request: Request):
    # SalesPlan builds with base './' (it also runs standalone at /), so a hard
    # refresh on a nested route asks for e.g. /planning/department-plan/assets/x.js
    # - send those to the real asset instead of answering with index.html.
    if "/assets/" in f"/{full_path}":
        return RedirectResponse(f"/planning/assets/{full_path.rsplit('/assets/', 1)[-1]}", status_code=301)
    if get_session_user(request) is None:
        return RedirectResponse(f"/login?next=/planning/")
    return _html_no_cache(os.path.join(_planning_dist, "index.html"))


@app.get("/calendar/{full_path:path}", include_in_schema=False)
def calendar_spa(full_path: str, request: Request):
    if get_session_user(request) is None:
        return RedirectResponse(f"/login?next=/calendar/")
    return _html_no_cache(os.path.join(_calendar_dist, "index.html"))
