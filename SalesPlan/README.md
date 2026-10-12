# Sales Plan — CityKart

The Planning Engine of the RS Planning suite: Python engines (FastAPI routers) plus a React 18 + Vite frontend.
It is **not a server of its own any more** — the unified platform (`RS Planning Platform/backend/app.py`, port 8010)
imports these routers and serves the built frontend.

- **Open it:** `http://10.0.1.131:7800/planning/` (Landing, behind the suite sign-in) — or `http://localhost:8010/planning/` on this PC.
- **API:** every engine under `/api/planning/<engine>` on 8010, all behind sign-in (`require_login`).
- **Started by:** Landing (7800) — its launch list and 30 s watchdog keep 8010 up; nothing here needs installing.
  The old standalone port 8002, its start.bat, desktop shortcut, service/watchdog tasks and firewall rule were retired
  (declutter 12 Oct 2026); `uninstall_service.ps1` stays only to remove those old tasks if a PC still has them.

## Where the data comes from

| Input | Source |
|---|---|
| LY store × department sales | Calendar app's snapshots in Postgres (`calendar.sales_snapshots`, kinds `trend_shifted_dept` = plan base, `actual_dept`), written by the nightly `calendar_reindex_sync` — no manual import (`actuals_manager.py`) |
| Division targets | The AOP publish BIS was last saved on (`division_plan._bis_aop`); if that version has been published again since, the live saved version - the page says so until BIS is saved again |
| Department growth | BIS's growth push (`planning_inputs.input_values`, `buyer_department_growth`) |
| New departments | `backend/new_dept_mapping.json` — edited in BIS › New departments (or the ⚙ New depts config view) |
| Store master / clusters | Postgres `masterdata.stores` (`store_master.py`) |
| Attribute master | `SalesPlan/Attribute Master/att master.xlsx` (also read by AOP and the Re-Aligner) |
| MRP Cont %, PW-W, SOR workbooks | **Outside the repo:** `C:\Users\A9820\Documents\CLaude - New Projects\SalesPlan\{MRP Cont %, PW-W Deviation, SOR Deviation}` (hard-coded in the three engines). The repo's `MRP Cont %/` and `PW-W Deviation/` copies are versioned backups only. |
| MRP re-apportionment master + outputs | Outside the repo: `...\CLaude - New Projects\MRP Merging Engine\Sales Reapportionment\{MRP Mapping, Output}` |

Engine state and results are JSON files in `backend/` and `backend/engines/` (`department_state.json`,
`department_custom.json`, `mrp_plan.json`, `final_dept_plan.json`, ...).

## Engines, screens and API prefixes

| Engine (module) | Screen(s) under /planning | API prefix (8010) |
|---|---|---|
| Division Plan (`division_plan.py`) | `/division-plan` (`/division-plan/growth` exists but has no menu link) | `/api/planning/division-plan` |
| Department Plan (`department_plan.py`) | `/department-plan`, `/department-plan/growth` | `/api/planning/department-plan` |
| Dept Sales / Base Plan (`dept_sales_engine.py`) | Growth Matrix → Generate base plan, `/department-plan/new-depts` (config view) | `/api/planning/dept-sales` |
| Attribute Correction (`attribute_correction_engine.py`) | `/department-plan/attr-correction` | `/api/planning/attr-correction` |
| Base Correction (`base_correction_engine.py`) | `/department-plan/base-correction` | `/api/planning/base-correction` |
| Final Results (`final_results_engine.py`) | `/department-plan/final-results` | `/api/planning/final-results` |
| MRP Plan (`mrp_plan_engine.py`) | `/mrp-plan/import`, `/mrp-plan/output` | `/api/planning/mrp-plan` |
| MRP Re-apportionment (`mrp_reapportionment_engine.py`) | `/mrp-plan/reapportionment` | `/api/planning/mrp-reapportionment` |
| PW-W Deviation (`pww_deviation_engine.py`) | `/deviation/pww` | `/api/planning/deviation/pww` |
| SOR Deviation (`sor_deviation_engine.py`) | `/deviation/sor` | `/api/planning/deviation/sor` |
| Display Type Plan (`display_type_engine.py`) | `/display-type` | `/api/planning/display-type` |
| Sales Sync (`sync_engine.py`, read-only view of the Calendar snapshots) | `/sync` | `/api/planning/sync` |
| Reconciliation (`reconciliation.py`) | `/reconciliation` | `/api/planning/reconciliation` |
| Store Master (`store_master.py`) | — | `/api/planning/store-master` (+ `POST .../reload`) |

The routes themselves are in each engine module (`@router.get/post/...`); 8010's `/docs` lists them all after sign-in.

## Changing it

- **Backend:** edit `backend/` or `backend/engines/`, then restart 8010 (stop the process on 8010 — Landing's watchdog
  starts it again from `RS Planning Platform/backend`). Self-checks: `python test_actuals_manager.py` and
  `python engines/test_*.py` from `backend/` (plain assert scripts, no DB).
- **Frontend:** edit `frontend/src`, then `cd frontend && npm run build` — 8010 serves `frontend/dist/`, so a source
  change is invisible until it is built. Commit the build with `git add -A -f SalesPlan/frontend/dist`
  (`dist/assets` is git-ignored).
- **Live dev server:** `cd frontend && npm run dev` → `http://localhost:5175`, with `/api` proxied to 8010 (the real
  backend and data). Sign in once at `http://localhost:8010/login` first — the session cookie is host-only, so the
  dev server sends it too. Backend edits still need the 8010 restart. (`backend/main.py`, the old standalone 8002
  app, is no longer used by anything.)

## Layout

```
SalesPlan/
├── backend/
│   ├── engines/              # one module per engine + their JSON state + test_*.py
│   ├── actuals_manager.py    # LY sales from the Calendar snapshots
│   ├── store_master.py       # store master + clusters (Postgres)
│   ├── apportion.py          # shares that add to exactly 100 / split totals exactly
│   ├── plan_cache.py
│   ├── main.py               # old standalone app (8002) - unused
│   └── new_dept_mapping.json, final_dept_plan.json, ...
├── frontend/                 # React 18 + Vite; src/pages (one per screen), dist/ (served by 8010)
├── Attribute Master/         # att master.xlsx (live) + the manual KPI extractor
├── MRP Cont %/, PW-W Deviation/   # backup copies of the outside-repo workbooks
└── uninstall_service.ps1     # removes the retired 8002 tasks if present
```
