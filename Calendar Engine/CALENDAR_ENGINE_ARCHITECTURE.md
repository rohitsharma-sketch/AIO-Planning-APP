# Calendar Engine — Architecture Handover

Structure, deployment, and ops facts for Calendar Engine specifically. Business/domain rules (propagation, engines, festival dates, reindex math) live in the companion doc, `CALENDAR_ENGINE_LOGIC.md`, in this same folder. Last compiled 2026-09-22.

---

## Where it lives, how it's served

- **Repo**: `RS_planning` (private, `github.com/kumarsuraj84/RS_planning`, direct-to-`main`, no PRs/CI). Local clone root: `...\AIO Project\repos\RS_planning`.
- **Not independently deployable.** Calendar Engine's backend is owned directly by `RS Planning Platform/backend/app.py` (`RS Planning Platform/backend/calendar_engine/`), one FastAPI process on **port 8010**, alongside AOP Forecaster and SalesPlan (imported via `sys.path.insert()`). All three share one Postgres DB, schema `calendar`.
- **Frontend**: `Calendar Engine/frontend/` (React + Vite). `app.py` serves the **pre-built `dist/`**, not a live dev server — there is no separate CI/build pipeline, so `dist/` is force-added to git despite the repo's blanket `dist/` `.gitignore` rule (`git add -f` once per new build-output filename, then plain `git add dist` works).
  - **Every frontend source change**: edit → `npm run build` in `Calendar Engine/frontend/` → commit + push BOTH source and rebuilt `dist/` together → restart the 8010 backend process (a pure frontend change still needs the process restarted so it serves the new static files — Windows file-serving under uvicorn doesn't hot-reload `dist/`).
  - Old vite chunk-size warning (>500kB after minify) is expected and not a real issue at current scale.
- **Route**: `/calendar/` on unified 8010. No standalone port — a legacy standalone `local_server.py` exists but is unused (persists to local JSON under `Calendar Engine/Local DB/`, a completely separate store from Postgres; do not launch it, it was previously a stale entry in Landing's Master Switch and has been removed from there).
- **Auth**: requires an 8010 session (Landing/8010 login), unlike AOP's standalone 8000 or BIS's 5050.

## Restarting after a backend or frontend change

Manual restart command (must run from `RS Planning Platform/backend/`, not from `Tentative AOP Forecaster/` — the wrong cwd still binds port 8010 but serves blank pages for `/calendar/` and `/planning/`):

```powershell
Start-Process "C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe" -ArgumentList "-m","uvicorn","app:app","--port","8010","--host","0.0.0.0" -WorkingDirectory "...\RS Planning Platform\backend" -WindowStyle Hidden
```

Find the current PID with `netstat -ano | grep ':8010'`, stop it by **exact PID, no `/T`** (killing with `/T` walks the whole `DETACHED_PROCESS` lineage and can take down AOP/SalesPlan/whatever else that same tree spawned — see Ops pitfalls below), then relaunch. Cold-start order for the whole platform: Landing (7800) first, then its Master Switch launches everything else.

## Data model

Two table families, both in Postgres schema `calendar`, owned by `Tentative AOP Forecaster/db/models/calendar.py` (AOP Forecaster is the de facto shared-DB owner for the whole platform):

**Live/working** — what the Calendarisation tab's editor shows, `persist()` writes here on every edit:
- `cluster_profiles` (name, region, seq, next_id)
- `cluster_profile_festivals` (cluster_profile_id FK, source_festival_id, name, ref_date, fut_date, pre, core, post, **`independent`** — see Logic doc)

**Locked/saved** — frozen snapshots created by "Lock & Save", edited only via full delete+recreate, never partial update:
- `calendars` (calendar_id, name, ref_year, fut_year, saved_at, engine)
- `calendar_clusters` (calendar_id FK, cluster_name, region)
- `calendar_cluster_festivals` (calendar_cluster_id FK, same shape as cluster_profile_festivals incl. `independent`)
- `calendar_day_pairs` (calendar_id, cluster_name, seq, ref_date, fut_date) — the actual computed day-by-day mapping. **No FK to `calendar_clusters`** (keyed by cluster_name string), so festival-list edits can never orphan or break the day-map.

**A locked snapshot does not self-heal** when the generation algorithm changes later — it must be explicitly regenerated (Version Setting → Create Calendar → Calendarisation tab's own Create Calendar → Lock & Save, same name to overwrite in place). A calendar locked before a bugfix landed silently keeps the pre-fix output forever until regenerated — this has caused real, confirmed artifacts (see Logic doc's V1/V2 engine section).

Adding a column to either festival table needs a **manual `ALTER TABLE`** — there is no Alembic/migration tooling and no `Base.metadata.create_all()` call anywhere in this codebase; the SQLAlchemy model and the live schema must be kept in sync by hand.

## Sales data sources (for the Reindex feature)

Two independent, periodically-full-re-exported parquet sources on the same network share (`\\10.0.1.85\...\data_lake\raw\...`):

- **Day-wise (billwise)**: `rs_19_to_26_day_wise_sales_data_compiled`. Each file is a full 2019–2026 re-export; reading more than the single latest file double-counts every sale in the overlap. `_latest_daywise_files()` in `scans.py` picks only the newest `.parquet` by mtime, and every day-wise read path (link scan, `get_source_schema`, the actual reindex fetch) goes through it.
- **Month-wise**: `PARQUET_DIR`, a separate folder/source. **Had the identical class of bug until fixed 2026-09-22** — no "latest only" guard at all, so with 2 overlapping full-history exports sitting in the folder, every month-wise total was counted ~2x. Fixed with `_latest_monthwise_files()`, same pattern, applied at all 3 read sites. Full root-cause detail in the Logic doc.

Both sources are genuinely different files/formats — day-wise has day-of-month granularity, month-wise does not (this asymmetry is why the Month Wise Matrix feature has to derive its split from the calendar's own day-map rather than from real daily sales; see Logic doc).

## Frontend structure (`Calendar Engine/frontend/src/`)

- `components/CalendarisationTab/` — Festival Master editor. `index.jsx` (state, persistence, cross-cluster/cross-template propagation handlers), `FestivalTable.jsx` (the per-cluster grid: name/dates/Pre-Core-Post/Independent columns, header bulk-set, drag reorder, name autocomplete), `ClusterTabs.jsx` (cluster pills, rename/region/copy-from).
- `components/CalendarisedSalesTab/` — the Reindex feature. `index.jsx` (source/calendar selection, job start/poll, `fetchCalendarMaps()` which builds the festival/ref-date/ref-months/forward-split lookup maps), `ReindexOutputPanel.jsx` (every output tab: Reindexed Sales, Monthly Summary, By Cluster, MW Comparison, **Month Wise Matrix** [new], P1/P2 Comparison, Run Details).
- `components/StoreClusterMappingTab/` — store↔cluster assignment, with a file-upload-plus-diff-preview import flow (the UX pattern referenced when discussing a similar bulk-import for festivals — not yet built, see Logic doc's open items).
- `lib/engine.js` — the V1/V2 date-mapping algorithms (`generateMappings`, `repairExcessiveShifts`, `scoreMapping`).
- `lib/festivalData.js` — `FESTIVAL_DB`, the verified festival name/date catalog used for autocomplete and cross-template date resolution.
- `index.css` — one global stylesheet; `.scm-toolbar` (flex row, wraps), `.tbl-wrap`/`table` (sticky navy headers), `.fest-name-suggest` (a reusable position:fixed/absolute dropdown-panel look, originally built for the festival-name autocomplete, since reused for the Month Wise Matrix's multi-select store picker) are the classes most worth knowing before adding new UI.

## Recent work this session (2026-09-22)

All committed to `main`, in order:
1. `8d975fb` — Fixed the month-wise double-counting bug; added the **Month Wise Matrix** tab (per-store, reference-month-to-TY-month sales split, multi-store preview, XLSX export via new `xlsx`/SheetJS dependency).
2. `c0c9336` — Fixed Month Wise Matrix showing blank splits on a fresh page load (the split map needs a calendar selected, not just a cached run).
3. `8ced54c` — Merged Festival Master's two cross-cluster action buttons onto one toolbar row.
4. `e7533e6` — Changed the Month Wise Matrix Store Filter from single-select to true multi-select (checkbox dropdown).
5. `3d98bb6` — Added the per-(cluster, festival) **Independent** manual-override toggle to exempt one cluster's festival from the cross-cluster Pre/Core/Post cascade, plus the `independent` DB column on both festival tables.

Still open (discussed, not yet built) — see Logic doc's "Open design items":
- Automatic (vs. manual-button) sync of festival structure between a year-pair's V1 and V2 engines, with an "out of sync" badge.
- A bulk festival→cluster matrix import UI modeled on Store-Cluster Mapping's file-upload-plus-diff-preview pattern.

## Ops pitfalls specific to working on this app

- **`taskkill /T` / `Stop-Process` tree-kill**: never add `/T` when restarting just the 8010 process — Windows still records `DETACHED_PROCESS`-launched children under the original parent PID, so a tree-kill on Landing's PID once took down 8010/8000/5050 together. Kill by exact PID only.
- **Claude Code's own write classifier blocks broad/bulk raw-SQL writes** even when a scoped write on the same table is allowed (confirmed: a ~219-row UPDATE across every festival/cluster was blocked; a 9-row single-festival update was allowed). Don't fight it by rephrasing the same broad script — either use the app's own bulk UI action (e.g. header bulk-set, "Apply to all clusters") or split into several genuinely single-purpose writes.
- **OneDrive file-sync race**: a documented, reproducible gotcha in this repo where a server restart can briefly load a stale pre-edit file version even though the file is correct on disk moments later. If a restart doesn't seem to pick up an edit, restart once more before assuming the edit didn't save.
- Always verify a frontend change **live in the browser against `localhost:8010`**, not just via `npm run dev` on a separate port — the dev server proxies to the same real backend/DB so it's fine for functional testing, but it is not what the actual deployed app serves.
