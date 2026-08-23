# Sales Plan — CityKart

Full-stack merchandise sales-planning tool: a **FastAPI** backend (Python 3.14) that runs the planning
engines and serves a pre-built **React 18 + Vite** frontend as a single-page app.

Everything runs from **one server on port 8002** — `http://localhost:8002` (LAN: `http://CKHO-L-A9820:8002`).

## Quick start (normal use)

Double-click **`start.bat`** (or the *Sales Plan* desktop shortcut). It:

1. Kills any stale server listening on port 8002.
2. Starts `uvicorn main:app --host 0.0.0.0 --port 8002` from `backend/`.
3. Waits until the port is actually listening, then opens the app in your default browser.

Closing the console window stops the server.

### One-time setup scripts (right-click → *Run with PowerShell*)

| Script | Purpose |
|---|---|
| `install_shortcut.ps1` | Creates a *Sales Plan* desktop shortcut pointing at `start.bat` (uses `icon.ico`). |
| `install_service.ps1` | Registers a scheduled task that auto-starts the server at login (hidden, auto-restart ×3). |
| `install_watchdog.ps1` | Registers a scheduled task that health-checks the server every 3 minutes and force-restarts it if it's down or hung (`watchdog.ps1`, logs to `watchdog.log`). Recommended alongside `install_service.ps1`. |
| `install_firewall.ps1` | **Run as Administrator** — opens inbound TCP 8002 so other devices on the LAN can use the app. |
| `uninstall_service.ps1` | Removes both the server and watchdog scheduled tasks. |
| `make_icon.ps1` | Regenerates `icon.ico`. |

## Developer setup

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

Dependencies: fastapi, uvicorn, pandas, numpy, pydantic, python-multipart, openpyxl
(pinned in `backend/requirements.txt`). Interactive API docs at `http://localhost:8002/docs`.

### Frontend

The backend serves `frontend/dist/` if it exists, so for normal use **no Node is required**.
Only rebuild when you change the UI:

```bash
cd frontend
npm install
npm run dev      # Vite dev server on http://localhost:5175, proxies /api → :8002
npm run build    # writes frontend/dist — restart the backend to pick it up
```

## Project layout

```
SalesPlan/
├── start.bat                 # launcher (server + browser)
├── install_*.ps1             # shortcut / startup task / firewall helpers
├── backend/
│   ├── main.py               # FastAPI app, mounts all engine routers + SPA
│   ├── store_master.py       # store master + cluster lookup
│   ├── actuals_manager.py    # actual-sales import & month locking
│   ├── engines/              # one module per planning engine (see below)
│   ├── data/                 # sync config, sales cache, sync status
│   └── *.json                # persisted engine state / results
├── frontend/
│   ├── src/pages/            # one page per screen (16)
│   ├── src/components/       # Sidebar, TopBar, Header, EngineCard, PipelineBanner, SearchSlicer
│   ├── src/pipelineState.js  # cross-page pipeline status
│   └── dist/                 # built bundle served by the backend
├── Actual Sales/             # Actual Sales Value - <period>.xlsx
├── Attribute Master/         # att master.xlsx + extracted KPI/contribution JSON
├── MRP Cont %/               # MRP contribution workbook
├── New Departments/          # NEW Departments.xlsx
├── PW-W Deviation/           # PPO Cont %.xlsx
├── SOR Deviation/            # SOR inputs
└── UDF Cont % + ASP/         # display-type contribution + ASP workbook
```

The Excel folders above are the **engine inputs** — the import/sync endpoints read them directly.
The Sync engine additionally pulls raw sales parquet files from the network share configured in
`backend/data/sync_config.json`.

## Engines, screens and API prefixes

All engines are active. Every router is mounted under `/api/...` in `backend/main.py`.

| Engine (module) | UI route(s) | API prefix |
|---|---|---|
| Division Plan (`division_plan.py`) | `/division-plan`, `/division-plan/growth` | `/api/division-plan` |
| Department Plan (`department_plan.py`) | `/department-plan`, `/department-plan/growth`, `/department-plan/new-depts` | `/api/department-plan` |
| Dept Sales / Base Plan (`dept_sales_engine.py`) | `/department-plan/new-depts` (+ actuals, cluster plan) | `/api/dept-sales` |
| Attribute Correction (`attribute_correction_engine.py`) | `/department-plan/attr-correction` | `/api/attr-correction` |
| Base Correction (`base_correction_engine.py`) | `/department-plan/base-correction` | `/api/base-correction` |
| Final Results (`final_results_engine.py`) | `/department-plan/final-results` | `/api/final-results` |
| MRP / Article Plan (`mrp_plan_engine.py`) | `/mrp-plan/import`, `/mrp-plan/output` | `/api/mrp-plan` |
| MRP Reapportionment (`mrp_reapportionment_engine.py`) | `/mrp-plan/reapportionment` | `/api/mrp-plan` |
| PW-W Deviation (`pww_deviation_engine.py`) | `/deviation/pww` | `/api/deviation/pww` |
| SOR Deviation (`sor_deviation_engine.py`) | `/deviation/sor` | `/api/deviation/sor` |
| Display Type Plan (`display_type_engine.py`) | `/display-type` | `/api/display-type` |
| Sync Engine (`sync_engine.py`) | `/sync` | `/api/sync` |
| Store Master (`store_master.py`) | — | `/api/store-master`, `POST /api/store-master/reload` |

### Key endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/division-plan/config` · `/stores` · `/growth-structure` | Division plan inputs |
| POST | `/api/division-plan/calculate` | Calculate monthly division plan |
| GET | `/api/division-plan/export` | Download CSV |
| GET/POST | `/api/department-plan/growth-matrix[/{division}]` | Department growth matrix (import/reset/export) |
| POST | `/api/department-plan/calculate` · `/auto-balance` · `/sync-from-buyer` | Department plan |
| GET | `/api/dept-sales/run` · `/plan-summary` · `/final-plan` · `/cluster-plan` | Store×department base plan |
| POST | `/api/dept-sales/actuals/import-from-dir` | Import actuals from `Actual Sales/` (month locking via `/actuals/*`) |
| GET/POST | `/api/attr-correction/preview` · `/comparison` · `/save` | Attribute-level correction |
| GET/POST | `/api/base-correction/check` · `/review` · `/apply` · `/export` | Base correction review |
| GET | `/api/final-results/dashboard` · `/data` · `/status` | Final consolidated results |
| POST | `/api/mrp-plan/sync` | Import MRP contribution workbook; `GET /data`, `/export`, `DELETE /clear` |
| POST | `/api/mrp-plan/run` | MRP reapportionment; `GET /template`, `/download` |
| GET | `/api/deviation/pww/run-phase1` · `/run-phase2` · `/reapportion` | PW-W deviation phases |
| POST | `/api/deviation/sor/import/sales-plan` · `/import/stock-ppo` | SOR inputs; `GET /run-avg`, `/reapportion`, `/export` |
| POST | `/api/display-type/import/contributions` · `/import/asp` | Display-type inputs; `GET /run-plan`, `/run-qty`, `/export` |
| GET/POST | `/api/sync/status` · `/config` · `/sync` · `/data` | Raw sales sync from the network share |

Full, always-current list: `http://localhost:8002/docs`.

## Troubleshooting

- **Port 8002 already in use** — `start.bat` kills the old listener automatically; otherwise
  `netstat -ano | findstr ":8002 .*LISTENING"` and `taskkill /PID <pid> /F`.
- **Python not found** — `start.bat` expects `C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe`
  and falls back to `python` on PATH. `install_service.ps1` has the same pinned path.
- **UI shows old version** — rebuild with `npm run build` and restart the server.
- **LAN users can't connect** — run `install_firewall.ps1` as Administrator.
- **App loads but clicks/pages hang** — the server process can stay alive without actually listening on
  8002. If `install_watchdog.ps1` is registered it self-heals within ~3 minutes (check `watchdog.log`);
  otherwise just re-run `start.bat`.
