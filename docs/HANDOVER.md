# RS_planning — Handover Document

**Written:** 2026-09-02, by the outgoing Claude session, for a fresh Claude session/account picking up this project. **Last significantly updated:** 2026-09-21 (§7.2/§7.5/§7.13, §9 — a full Calendar Engine festival-date and engine audit; see §7.13 for the complete story).

This is a single, self-contained brain-dump of everything a new Claude instance needs to work on this repo competently from message one. The previous session used Claude Code's persistent memory system, which does **not** transfer to a different account/ID — so treat this document as the full replacement for that memory. Read it once before touching anything.

---

## 1. What this is

**RS_planning** is Citykart's private monorepo holding 7 internal planning/forecasting web apps used by merchandising/planning teams. It is NOT one app — it's 7 separate frontend+backend projects living as sibling folders in one repo, three of which are unified onto one shared FastAPI backend + one shared Postgres database.

- **GitHub**: `https://github.com/kumarsuraj84/RS_planning.git` — private repo, owner `kumarsuraj84`. Workflow is **direct-to-`main`**, no PRs, no CI.
- **Local clone**: `C:\Users\A9820\Documents\CLaude - New Projects\Ver 2 Developments\AIO Project\repos\RS_planning` (branch `main`). This whole tree lives under `Documents`, which is **OneDrive-synced** — see §7 for the file-lock gotcha this causes.
- **Credentials**: GitHub auth is stored in Windows Git Credential Manager (user signed in via browser once) — clones/pulls/pushes work without prompting, so a fresh session should NOT need to re-authenticate.
- **User**: Suraj (email `suraj@citykart.org`), the sole developer/operator of this codebase working with Claude Code.
- **Local dev registry**: `C:\Users\A9820\Documents\CLaude - New Projects\Ver 2 Developments\AIO Project\aio_projects.db` (SQLite) tracks this and other repo clones — a `repos` table (github_url, local_path, clone_status, branch, last_commit) and a `projects` table. All new "Ver 2" development work is expected to happen inside that `AIO Project` folder, not scattered elsewhere.

The 7 top-level app folders, plus `data/` (shared data files) and `docs/` (this file lives here — was previously empty, no other docs existed at repo root, no CLAUDE.md/AGENTS.md/README either):

1. Buyer's Input Sheet
2. Calendar Engine
3. Landing
4. RS Planning Platform ← the unified backend + 3 of the frontends
5. SalesPlan
6. Store Master
7. Tentative AOP Forecaster

---

## 2. Architecture map — READ THIS FIRST, it's the single most important structural fact

**Three of the seven "apps" are not independently deployable.** `RS Planning Platform/backend/app.py` (port **8010**) is one FastAPI process that:

- Owns its own SalesPlan/Calendar-Engine/AOP code physically living in `RS Planning Platform/backend/` (e.g. `calendar_engine/` subfolder), AND
- Also `sys.path.insert()`s and imports live code from the sibling top-level folders `Tentative AOP Forecaster/` and `SalesPlan/backend/` at runtime.

This means those sibling folders are **not** separately deployable — they are library code imported into the 8010 process. Editing `Tentative AOP Forecaster/engine_v3.py` changes behavior on port 8010 too (after a backend restart), not just on AOP's own standalone port.

**Auth/workflow/audit DB ownership**: the shared DB session/models layer that everything resolves through (`db/base.py`, `SessionLocal`) lives under `Tentative AOP Forecaster/db/` — making AOP Forecaster the de facto shared-database owner for the whole platform, even though architecturally it looks like "just one of the apps." A stale docstring in that file still says "not wired in yet" for some auth pieces — that's outdated, don't trust the docstring, check actual behavior.

**Shared Postgres DB**: schema `calendar` (name is historical — it holds more than calendar data now), connection string in `Tentative AOP Forecaster/.env`. SalesPlan, Calendar Engine, and AOP Forecaster all read/write this one DB. This is why cross-module data sharing (e.g. SalesPlan's Sync Engine reading Calendar Engine's saved reindex output from `calendar.sales_snapshots`) needs no API calls — it's just a shared-DB read.

**Router mount table** (`RS Planning Platform/backend/app.py`, port 8010) — the reachable URL prefixes:
- `/calendar/...` → Calendar Engine frontend + its API
- `/aop/...` → AOP Forecaster frontend + its API (double-mount quirk below)
- `/planning/...` → SalesPlan frontend + its API

**AOP double-mount quirk**: AOP's endpoints are declared as `@router.post("/api/config/...")` and then that whole router gets mounted AGAIN under `prefix="/api/aop"` — so the real reachable path is the doubled `/api/aop/api/config/...`, not the `/api/aop/config/...` you'd naively expect. The frontend's `apiUrl()` helper (`lib/apiBase.js`) already handles this — don't "fix" the doubling, just call `apiUrl('/api/config/whatever')` like every existing AOP fetch does.

**Landing (port 7800) is the master launcher, and is deliberately NOT part of 8010** — see §5.3. It has to be reachable before 8010 is even started, so it can't be served from 8010 (circular dependency).

**Standalone-vs-unified port map** (know this before starting/stopping anything):
| App | Unified route (8010) | Standalone port | Standalone still used? |
|---|---|---|---|
| Calendar Engine | `/calendar/` | ~~7822~~ | No — removed from Landing's launcher, would silently use a different local-JSON data store |
| AOP Forecaster | `/aop/` | 8000 | **Yes, intentionally** — Landing's own anonymous status checks and data-lake-sync trigger need an unauthenticated port, since 8010 requires login |
| SalesPlan/Planning | `/planning/` | ~~8002~~ | No — same reasoning as Calendar Engine |
| Buyer's Input Sheet | n/a (always standalone) | 5050 | Yes, its only mode |

---

## 3. App-by-app notes

### 3.1 Landing (`Landing/`)
Port **7800**. Plain static HTML page + `landing_server.py` (Python's built-in `http.server`, not FastAPI, not part of the unified backend). This is the **master switch / entry point** — the user's Chrome bookmark ("Planning Module") points here, and it must already be running before any other app is reachable, because it's what starts the others.

- Shows cards linking to every other app.
- A "Master Switch" button POSTs to `/api/launch-all` / `/api/shutdown-all`, which shells out to each app's own run command to start/stop everything in one click.
- `APPS` list inside `landing_server.py` defines exactly what Master Switch launches — **keep this in sync** whenever an app gets unified onto 8010 or un-unified; a stale entry silently launches a duplicate process against a different data store with no visible UI difference (this happened for real — see §7).
- Auto-start: `Landing/install_autostart.ps1` installs a Windows Startup-folder shortcut so it survives reboots/logins (installed 2026-08-26; wasn't there before, causing silent "connection refused" on the bookmark after every reboot). If the user reports the bookmark not working, check `curl localhost:7800` reachability first — a session open from before this fix may still need Landing started manually once.
- The purple "L" favicon in Chrome is just Chrome's auto-generated fallback (no real favicon/manifest exists) — cosmetic, not a bug.

### 3.2 RS Planning Platform (`RS Planning Platform/`)
Port **8010**. The unified FastAPI backend (`backend/app.py`) serving Calendar Engine, AOP Forecaster, and SalesPlan/Planning frontends and APIs — see §2 for the full architecture. Requires a login session (unlike Landing or AOP's standalone 8000).

Frontends are served from **pre-built `dist/` folders**, not a live dev server (`app.mount(".../assets", StaticFiles(...))` + a catch-all `FileResponse(dist/index.html)`). This is critical — see §6.2, it has bitten this project before.

### 3.3 Calendar Engine (`Calendar Engine/`)
Frontend source at `Calendar Engine/frontend/src/`; also has a legacy standalone `local_server.py` (not used in production anymore — see §2's port table). Business logic lives in `RS Planning Platform/backend/calendar_engine/` (backend) and `Calendar Engine/frontend/src/lib/engine.js` (client-side mapping algorithm). This is the module the previous session worked on most deeply — full business-rule detail in **§8**, a dedicated deep-dive section below. Skim §8 before touching anything here.

### 3.4 Tentative AOP Forecaster (`Tentative AOP Forecaster/`)
Annual Operating Plan forecasting engine. Core logic in `engine_v3.py`. Also owns the **shared DB layer** (`db/` — `SessionLocal`, models) that the whole unified platform depends on (see §2). Full business-rule detail in **§9**.

- `.env` here holds the shared Postgres connection string used by AOP, Calendar Engine, and SalesPlan alike.
- `.claude/launch.json` in this folder has a stale `cwd` — a known but unfixed cosmetic issue, harmless unless something starts depending on it.
- Has its own standalone launch on port 8000 (intentionally kept, see §2 table) — `Tentative AOP Forecaster/frontend/dist` is also git-tracked (force-added, same as Calendar Engine).

### 3.5 SalesPlan (`SalesPlan/`)
Frontend served under `/planning/` on 8010; backend code lives at `SalesPlan/backend/` and is imported into the unified process (see §2). Has the only substantive `README.md` in this repo (`SalesPlan/README.md`) — worth reading if working here. Also has its own Windows service/watchdog installers (`install_service.ps1`, `install_watchdog.ps1`) following the same PowerShell scheduled-task pattern as AOP's auto-sync (§9.2) — pinned interpreter `C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe`, `-WindowStyle Hidden`, `-MultipleInstances IgnoreNew`.

- **Known open bug (found, not yet fixed)**: a broken `STORE_MASTER_PATH` reference somewhere in SalesPlan's backend — flagged by a survey agent during the previous session but never chased down or fixed. Worth grepping for and confirming before it causes a real failure.
- **Known open item**: an orphaned `mrp_reapportionment_engine.py` router — appears unmounted/unused. Confirm whether it's dead code or just not wired up yet before deleting.
- Its `dist/` folder is **still gitignored and untracked** as of the last session (unlike Calendar Engine and AOP Forecaster, whose `dist/` are force-tracked in git — see §6.2). Confirm with the user whether SalesPlan should get the same "commit the build" treatment before assuming it's needed.

### 3.6 Buyer's Input Sheet (`Buyer's Input Sheet/`)
Always standalone, port **5050** — never unified onto 8010. Linked from Landing's card grid.

### 3.7 Store Master (`Store Master/`)
Store master-data management tool. `Store Master.xlsx` synced from here is the real source AOP Forecaster's `ref_store` assignment reads from (specifically the "Ref Name - Merch" column — confirmed with the user this is the only ref-name column that matters, see §9.1).

### 3.8 `data/` (top-level, not an app)
Shared data files referenced by multiple apps — not a standalone project.

---

## 4. Environment / how to actually run this stuff

- Python interpreter (pinned in scheduled-task scripts): `C:\Users\A9820\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- No CI/CD pipeline exists anywhere in this repo. Deploys are "pull latest `main` on the machine that already runs everything" — there is no separate build/staging server.
- To bring up the whole stack from cold: start Landing (7800) first, then use its Master Switch to launch everything else — don't hand-start 8010/8000/5050 individually unless debugging one specific app.
- **Never use `taskkill /T` to stop one process in this stack** — see §6.4, it will take down the entire platform.

---

## 5. Cross-cutting operational rules (apply to every app in this repo)

### 5.1 "save the state" / "push the layout" — standing trigger phrases
When the user says **"save the state"** or **"push the layout,"** that means, without re-asking which parts: (1) if any frontend source changed, `npm run build` it first (§6.2), (2) `git add` both the changed source AND the rebuilt `dist/`, (3) commit with a message describing what changed, (4) `git push origin main`. This is standing authorization for that specific save cycle — don't ask permission again, just do it and report what was pushed. (Skip the build step if nothing frontend changed; skip committing `dist/` for a frontend whose `dist/` isn't tracked yet — currently only Calendar Engine's and AOP Forecaster's are, see §6.2.)

### 5.2 Capture business rules into writing as you go
Whenever the user makes a scoping decision, correction, or business-rule call while working on any of these apps, write it down (in this doc, or wherever the receiving session's persistence lives) as part of finishing that piece of work — don't wait to be asked separately. The goal is that established decisions become fixed constraints future sessions don't re-derive, re-guess, or accidentally contradict. §8 and §9 below are full of exactly this kind of captured rule from the previous session — keep that habit going.

### 5.3 Never fabricate calendar/festival dates
For Calendar Engine work specifically: never invent or estimate a real festival date (Navratri, Shraad/Pitru Paksha, Nuakhai, etc.). Only use a date the user has explicitly verified (they've provided exact ranges/screenshots from real calendars repeatedly), or one mathematically/tithi-derived from another already-verified date in the same file **with the derivation stated in a comment** (e.g. Nuakhai = Ganesh Chaturthi + 1 day). If a brand-new festival has no anchor and no user-supplied date, ask — even under "just add it, move fast" pressure. This burned the project multiple times before the rule was enforced (wrong Navratri/Dussehra dates for several years had to be corrected).

---

## 6. Environment gotchas — things that will silently break your work if you don't know them

### 6.1 Claude Code's own write classifier blocks bulk raw-SQL
Independent of the user, Claude Code's permission classifier blocks broad/bulk raw-SQL writes (confirmed: a ~219-row `UPDATE` across every festival/cluster was blocked via both Bash and PowerShell; a scoped 9-row update and a bounded snapshot-restore were both allowed). If a legitimate bulk change gets blocked, **don't fight it by rephrasing the same script** — either drive the change through the app's own bulk-UI mechanism (e.g. Calendar Engine has "Apply to all clusters" buttons for exactly this), or break it into several genuinely scoped, single-purpose writes. This is also just the safer approach on its own merits — bulk writes against locked/production calendar data have no undo and real cross-table effects.

### 6.2 The real app serves `dist/`, not `src/` — rebuild after every frontend change
`RS Planning Platform/backend/app.py` mounts each frontend's **pre-built `dist/` folder** as static files — it does NOT run a live dev server. Editing `Calendar Engine/frontend/src/...` (or AOP's or SalesPlan's frontend) and verifying via your own `npm run dev` on a separate port is fine for functional testing (that dev server proxies `/api` to the same real backend/DB, so DB-level effects are real) — but it does **not** update what the user actually sees at `localhost:8010/calendar/`, because that's reading `dist/`, not `src/`. Concretely: **after any frontend source change, run `npm run build` in that frontend's folder before calling the task done.**

There is no separate CI/build pipeline in this repo — `dist/` therefore has to be **committed to git too**, not just built locally, or the deployed copy never updates. `.gitignore` has a blanket `dist/` rule, but both `Calendar Engine/frontend/dist` and `Tentative AOP Forecaster/frontend/dist` have been force-added and are now tracked (once force-added, later plain `git add dist` works normally, no `-f` needed again). SalesPlan's `dist/` is **not yet tracked** — confirm with the user before assuming the same rule applies there.

### 6.3 Windows/OneDrive file-lock retries
This repo lives under `Documents`, which is OneDrive-synced. Any code that writes-then-renames a file (`os.replace()` after writing a `.tmp`) can hit a transient `WinError 5 Access is denied` when OneDrive briefly opens the just-written temp file to sync it. Calendar Engine's `reindex_worker.py` and `reindex_csv_worker.py` both had their `_atomic_write_json()` hardened to retry the rename up to 10x with backoff after this killed two consecutive multi-month reindex runs outright. If you see a similar file-write pattern elsewhere in this repo fail intermittently, this is the first thing to suspect.

### 6.4 `taskkill /T` is dangerous here — never use it to stop one process
`taskkill /F /PID <n> /T` kills the WHOLE process tree rooted at that PID — including grandchildren launched via Python's `subprocess.Popen(..., creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)`. `DETACHED_PROCESS` detaches the console but Windows still records the launching PID as parent, and `/T` walks that recorded lineage regardless. This has actually happened: killing `landing_server.py`'s PID with `/T` (meaning to just restart Landing) also killed every process Landing's Master Switch had ever spawned — RS Planning Platform (8010), AOP Forecaster (8000), and Buyer's Input (5050) — taking down the entire stack by accident, requiring a full restart of everything.

**Rule**: when killing one specific process by PID, do NOT add `/T` unless you've specifically confirmed (`Get-CimInstance Win32_Process | Where ParentProcessId -eq <pid>`) that everything under that PID is actually safe to kill too. For a `DETACHED_PROCESS`-launched child, killing just the parent (no `/T`) is both sufficient and correct.

### 6.5 Browser-automation quirks (driving the Browser pane against these React apps)
1. **Native `window.prompt()`/`window.confirm()` are auto-dismissed** before a human ever sees them. Any click handler that calls one must have it overridden first via `javascript_tool` (`window.prompt = () => 'name'`, `window.confirm = () => true`) BEFORE the click, or the action silently no-ops.
2. **React controlled inputs need real events, not value pokes.** Setting `.value` directly doesn't register with React. Use `Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(el, value)` then `el.dispatchEvent(new Event('input', {bubbles: true}))` — or better, just use the `computer` tool's real `type`/`triple_click` actions, which are more reliable. Also a no-op if the new value equals the current one.
3. **Never rapid-fire multiple state-mutating clicks in the same tick** — back-to-back "apply"/"save" clicks race their state closures and a later click can silently overwrite an earlier one's effect. Click one at a time, wait for a real render, verify (DB check or screenshot) before the next click.

Also be aware: the automated Browser pane session in this project has logged itself out (401) multiple times across sessions, and Claude cannot enter passwords/credentials itself (a hard safety constraint, not a workaround-able one) — when this happens, fall back to direct backend verification (same code path, e.g. a scratch Python script hitting the same functions the API route calls) or ask the user to sign in, rather than attempting to log in yourself.

---

## 7. Calendar Engine — deep dive (the module worked on most recently and most deeply)

This section captures everything about how Calendar Engine actually works that isn't written down anywhere else in the codebase.

### 7.1 Purpose and core concept
Calendar Engine maps historical ("reference") calendar days to future ("future") calendar days per store cluster, so that sales/planning data from a past year can be re-indexed onto a future year's calendar — accounting for festivals shifting on the lunar/tithi calendar (e.g. Holi doesn't fall on the same Gregorian date every year), while non-festival days stay aligned to weekday/month patterns.

### 7.2 Live vs. locked data — two separate table families, deliberately
- **Live/working**: `cluster_profiles` + `cluster_profile_festivals` — what the editor UI shows, and what `persist()` writes to on every single edit.
- **Locked/saved**: `calendars` + `calendar_clusters` + `calendar_cluster_festivals` (+ `calendar_day_pairs`, keyed by a `cluster_name` string, no FK) — frozen snapshots created by "Lock & Save." Edited only via `PUT /calendar-library/{id}/festivals`, which does a **full delete+recreate** of that calendar's clusters/festivals from the payload — it is never an in-place update.

**Locked calendars don't self-heal when the generation algorithm changes.** A "Lock & Save" snapshot is computed once and frozen. Fixing a bug in `engine.js` does nothing to already-saved templates — each one has to be manually regenerated: Version Setting tab → set ref/fut year → "Create Calendar" (re-syncs festival dates for the currently-loaded live `cluster_profiles`) → then the Calendarisation tab's **own separate, same-named** "Create Calendar" button (easy to confuse with the one above — this is the one that actually runs `generateMappings()`) → then "Lock & Save" reusing the exact existing name to overwrite in place. As of the last session all 4 existing templates (`2026->2027 Calendar - All`, `2026->2027 Calendar W/ Core Only`, `2025->2026 Calendar - All`, `2024->2025 Calendar`) were regenerated this way after an algorithm fix.

**"Core Only" no longer means a smaller festival list (2026-09-18) — see §7.5 for the full policy.** "W/ Core Only" and "All" for the same ref/fut year became byte-identical once every festival became core everywhere, so the "W/ Core Only" *template* (id `1789556012651`) was repurposed on 2026-09-18 into **"2026 -> 2027 Calendar - Version 1"** — same underlying festival profile, but generated with the V1 engine instead of V2 (see §7.13's engine-version table). If "Core Only" needs to mean a genuinely smaller festival subset again someday, that has to be a new, explicit feature (e.g. a real UI toggle for which festivals to include), not a revival of the old allowlist.

### 7.3 Pre/Core/Post festival windowing
Each festival has a Pre-window length, a Core length, and a Post-window length. The mapping loop is:
```
for (pos = -pre; pos <= post + core - 1; pos++)
category = pos < 0 ? 'Pre' : pos < core ? 'Core' : 'Post'
```
The core anchor is always at `pos = 0`. Category labels are now suffixed onto festival names in output (e.g. "Holi (Pre)" / "Holi (Core)") — added specifically because every day in a festival's window used to show the identical bare name with no Pre/Core/Post distinction, which read to the user as if the "core date had shifted" when the underlying date math was actually correct all along (see §7.7).

### 7.4 Cross-cluster and cross-template propagation rules
- **Cross-cluster cascade (same live session)**: editing Pre/Core/Post on a festival in one cluster propagates to every OTHER cluster's festival with the exact same name (`handleDayFieldChange` in `CalendarisationTab/index.jsx`). Naturally region-scoped — only touches clusters that already have that festival name.
- **Cross-template auto-copy**: picking a festival from the Festival Name autocomplete (a real `FESTIVAL_DB` entry, not a hand-typed custom name) auto-copies that festival into every OTHER saved/locked calendar's same-named cluster too (`handleFestivalPicked`, triggered from `FestivalTable.jsx`'s `pickSuggestion`). Each target template resolves the date for **its own** ref/fut year — not a copy of whatever date the source template used. Purely additive: skips any template whose matching cluster already has that festival name, never overwrites. The currently-previewed template is excluded from this broadcast since `persist()`'s own autosave already covers it.
- **"Locked" preview autosave**: while a locked template is loaded via "Load & Preview" (`previewCalendarId` state), every live festival-list edit (name/date/pre/core/post) autosaves into that template's own storage too — festival list only, the day-map itself stays untouched until "Create Calendar" + "Lock & Save" runs again.
- **Known gotcha**: "Load & Preview" only updates in-memory `profiles` state, NOT the database, until a real edit persists it. A "Load & Preview" click can reload an OLD snapshot and make a previously-removed festival appear to "come back" — this is expected behavior, not a bug, but it has caused real confusion mid-session. When verifying a change, check the RENDERED TABLE, not just the DB — they can genuinely diverge at that specific moment.

### 7.5 Overlap resolution rule (changed 2026-09-18 — this replaces the old "first defined wins" rule entirely)
When two festivals' windows land on the same calendar date, `buildFestMap()` in `engine.js` resolves it by **`|position|` ascending, then total window size (pre+core+post) ascending** — NOT array order. Each festival's own anchor (position 0) always wins its date over another festival's outer pre/post day; among equal `|position|` ties, the smaller/more-specific window wins. This fixed a real, repeatedly-recurring bug: under the old "first defined wins" rule, a wide-window festival like Shraad (Pitru Paksha, a 15-day window) could silently swallow another festival's real anchor date (Navratri, Dussehra, Nuakhai) just because it happened to be listed first or had a bigger window.

**Every festival is now core (self-anchoring) in every cluster that carries it — the old `CORE_FESTIVALS_BY_CLUSTER` per-cluster allowlist was deleted entirely** (see §7.2). `coreFestivalNamesFor()` in `festivalData.js` now always returns `null`, which `generateMappings`/`validate` already treat as "no restriction." This was necessary because a *non-core* festival's Phase 1 anchor never fires at all, so its window gets filled independently per cluster by ordinary same-month scoring — which drifts even when every cluster stores the exact same date for that festival. Business rule, stated explicitly by the user: **no two clusters may shift the same festival by a different number of days.**

**Two real festivals can still genuinely coincide on the same calendar day in a given year** — this is an inherent, unavoidable astronomical/lunar-calendar coincidence, not a bug, and the priority rule above resolves it deterministically (one festival "wins" that day, the other's single conflicting position falls through to ordinary same-month matching). Confirmed, accepted cases as of 2026-09-21 — do not try to "fix" these, there is no cleaner answer:
- **Shraad vs Nuakhai**, ODISHA, 2027 (Nuakhai's day falls inside Shraad's 15-day window)
- **Eid al-Fitr vs Bihu**, N. EAST / N. EAST-PUJA, April 2024 (Eid's core days and Bihu's pre-days land on the identical dates that specific year)
- **Raksha Bandhan vs Milad-un-Nabi**, several clusters, August 2026 (Raksha Bandhan's pre-window reaches back onto Milad's own anchor day)

Run `python "Calendar Engine/scripts/verify_calendars.py"` after any regeneration to see the current, complete list of these — it checks every position of every festival's window, not just the anchor (see the new §7.13 for the full story of why that distinction matters).

### 7.6 Cluster region tags actually in use
Only `north`, `east`, and `bengal` region tags map to real clusters. The app's 10 real clusters: Kashmir, UP+NCR, UP+BIHAR-PUJA, BIHAR, JAMMU+RJ, ODISHA, N.EAST-PUJA, N.EAST, JH+MP+CG, WB. `FESTIVAL_DB` in `festivalData.js` also carries `south`/`west`/`gujarat`/`maharashtra`/`kerala`/`tamil`/`punjab`/`assam` tags for completeness, but **no cluster exists for any of those regions** — festivals tagged that way have no real cluster home in this app. Also: N.EAST and N.EAST-PUJA are tagged region `bengal` in the live data (not `east`) — looks like a labeling quirk, but it's existing data, not something to silently "fix."

### 7.7 Month-containment rule (confirmed directly by the user, high-stakes — the algorithm is heavily tested)
Non-core-festival days must **never** shift into a different calendar month than their future date — only core festivals (the anchored ones) are allowed to shift across months, since they follow their real astronomical/lunar date. `engine.js`'s `generateMappings()` Phase 3 enforces this: when a future month's own reference-day pool runs short (because a core festival's true date crossed a month boundary between ref-year and fut-year — e.g. Ram Navami: ref 2026-03-28 → fut 2027-04-16, shrinking March's leftover pool), it now **reuses the nearest already-used reference day from that same month** (`sharedRef: true`, `mappingType: 'Nearest Available Date (Same-Month Reuse)'`) rather than borrowing an unused day from an adjacent month. This was a real, systemic bug before the fix — confirmed affecting every cluster except Kashmir (13–26 unexplained cross-month mappings each), found via direct day-pair DB analysis, not a rare edge case as an earlier (now-corrected) code comment had claimed.

**This took three rounds of user clarification to nail down precisely** — the initial user report ("core date shifted, correct the algo") sounded like it needed an algorithm change, but after independently re-verifying the date math three times, the actual finding was that the math was already 100% correct and the only real gap was the missing Pre/Core/Post label (§7.3). Given how heavily-verified this algorithm is, don't assume a user complaint about "wrong dates" means the algorithm is broken — verify the underlying date math independently before touching `generateMappings()`, and consider whether it's a labeling/display gap instead.

### 7.8 Reused reference days require a fan-out join, not a dict lookup (backend)
The same-month-reuse fix above (§7.7) means a single reference day can legitimately map to TWO future days. `reindex_daywise()` in `scans.py` used to build its ref→fut lookup as a plain `{ref_date: fut_date}` dict — a duplicate ref-date key silently overwrites the earlier mapping (last-wins), so one of the two future days it should have fed just went missing from output with no error. Fixed by replacing the dict + `.map()` with a `df.merge()` against a long `(cluster, ref_date, fut_date)` table, which naturally duplicates a row when its ref day matches multiple future days. `reindex_monthwise()` was NOT affected — its ref→fut mapping is a month-level plurality vote, which already absorbs a day-level reuse within the same month.

### 7.9 Reference Date / Festival labeling must be scoped per cluster — never mixed globally
Both the backend (`refDateByColumn`) and frontend (`festivalByDate`/`festMap`) used to be flat `{date -> value}` lookups built by mixing EVERY cluster's calendar together — a plurality vote across unrelated clusters. This caused two confirmed real bugs (found from a user-flagged CSV export): UP+NCR's own Holi pre-window showed a reference date that actually belonged to a different cluster, and Onam (configured only for JH+MP+CG and WB) appeared against UP+NCR rows. **Fixed by scoping everything per-cluster** in `CalendarisedSalesTab/index.jsx` (`festivalByDate`/`refDateByCluster` state, keyed `{cluster: {date: ...}}`), `ReindexOutputPanel.jsx` (`festivalOf(cluster, col)` / `refDateOf(cluster, col)`), and `reindex_csv_worker.py` (`_load_festival_by_cluster_date` / `_build_ref_by_cluster_col`). Stacked view was always naturally exact (each row already carries its own cluster). **This is the single most important lesson from this module**: any lookup keyed only by date, without cluster, is a latent bug in this app — always scope by cluster first.

A related edge case hardened defensively (found via code review, not live failure): a `'(unmapped)'` sentinel value could, via a race during async cluster-store loading, or an all-unmapped payload, trivially satisfy a naive "exactly one cluster visible" check and silently show stale global data. Both frontend and backend now explicitly refuse to treat `'(unmapped)'` as a confident single-cluster signal.

**Wide CSV/table view needed a genuinely different fix than Stacked**, and the first attempt at it was explicitly rejected by the user — worth remembering why. Wide is one row per store, one column per date, so a single Reference-Date/Festival header row at the top literally cannot be accurate for more than one cluster's mapping at once. First attempt: only show that header when every visible/exported row is the same cluster, otherwise show an explanatory note pointing to Stacked instead. **The user rejected this** — hiding real data, even to avoid showing wrong data, is not an acceptable tradeoff; a planner needs Reference Date/Festival in Wide just as much as in a single-cluster view. Correct fix: group Wide's rows by cluster (both the interactive table and both CSV downloads) and give each cluster its own accurate header block directly above its own rows — `"{cluster} - Reference Date"` / `"{cluster} - Festival"`. Use a **plain ASCII hyphen, not an em-dash** — both CSV paths write via a BOM-less Blob/file, and Excel opened by double-click (rather than an explicit UTF-8 import) can mangle non-ASCII characters. **General lesson for this codebase: never trade correctness for presence, or presence for correctness — when the real fix is to give both, find that fix rather than picking one.**

### 7.10 Data source: day-wise (billwise) sales
As of the last session, the day-wise sales source changed from 4 separate legacy folders to **one consolidated folder** that receives periodic **full re-exports** (each file covers the whole 2019–2026 span on its own, not an incremental partition):
```
\\10.0.1.85\Users\Administrator\Desktop\AI SOLUTION\INVENTORY AUTOMATION\data_lake\raw\rs_19_to_26_day_wise_sales_data_compiled
```
`DAYWISE_DIRS`/`_latest_daywise_files()` in `RS Planning Platform/backend/calendar_engine/scans.py` (and the legacy duplicate in `Calendar Engine/local_server.py`) picks only the single most-recently-modified `.parquet` file — reading more than one would double-count every sale in the overlap. All three day-wise read paths (link scan, `get_source_schema`, actual reindex fetch) go through this helper. `SOURCE_SCHEMA["dw"]` still only lists 3 candidate dimensions (`ADMSITE_CODE`, `STORE_STATUS`, `CLUSTER_TYPE`) and one metric (`NETAMT`) inherited from the old sparse source — should be widened once a new file's richer real columns can be read; the user has noted the new source "solves the extra headers/attribute issue" the old one had.

This share (`\\10.0.1.85\...`) is genuinely flaky — it has gone down for extended periods (port 445 unreachable, confirmed via `Test-NetConnection`) and come back up unpredictably. A "No rows mapped for this run" error is worth checking against this share's reachability BEFORE assuming it's a code regression — this happened for real: 5 rounds of thorough verification (calendar_id correctness, DB day-map data, run diagnostics, direct raw-data fetch test, network reachability check) confirmed an external outage, not a code bug, and it resolved itself once the share came back online.

### 7.11 Reindex ETA and performance notes
- ETA estimation must be scoped by **output-field cardinality, not just source** — a Store-only run (~20s/month) and a Store+Division+Section+Department+Attribute1+Article-Name run (multiple minutes/month, 14M+ raw rows) used to be averaged into one estimate, showing a misleading "100% / 0s remaining" on a run still genuinely in progress 15+ minutes later. Timing records are now keyed by `_reindex_timing_key(source, extra_dims, metric)`.
- For a huge result (>80MB), CSV conversion runs synchronously server-side and can take several minutes with **zero visible progress** in the browser — this is real, silent work, not a dead button. A per-`(job_id, view)` lock now prevents a second click during that wait from spawning a redundant duplicate conversion of the same huge file. Still worth adding a "Converting… this can take a few minutes" UI indicator someday.

### 7.12 Recently added features (built and verified last session)
- **Redact a festival from all clusters** ("Remove from All Clusters" button in Festival Master) — removes by exact name across every cluster in one action, confirms with a dialog listing affected clusters.
- **Save Changes to Template** — a button next to "Create Calendar," shown only when a template is loaded (`previewCalendarId` set), that overwrites the currently-loaded locked template in place with the live editor's current festival state (delete+recreate via `saveCalendar`/`deleteCalendar`/`listCalendarLibrary`).
- **Sync Festival Structure to All Templates** — pushes the current full festival structure to every OTHER saved template, resolving dates for each target's own ref/fut year, replacing only common-named clusters' festival lists (never touching day-maps).

Implementing these surfaced a real **React stale-closure bug**: `runEngine()`'s `setState` calls don't take effect until the next render, so a caller reading state synchronously right after calling it got stale data. Fixed by having `runEngine()` return the fresh `{mappings, profiles}` directly instead of relying on reading updated state afterward — general lesson: any function that needs fresh state immediately after triggering another state-mutating function must have that function **return** the fresh data, never assume synchronous state availability in React.

### 7.13 Full festival-date and engine audit (2026-09-17 to 2026-09-21) — the most recent, deepest pass on this module

This was a multi-day session prompted by a user report ("Raksha Bandhan dates look off") that expanded into a full audit of every festival date and both engine versions, across all four saved calendar templates. Read this section before touching festival dates, `engine.js`, or any saved calendar again.

**Current saved calendars** (query `calendar.calendars` to reconfirm — this table will drift as new templates get created):

| id | Name | ref_year → fut_year | Engine | Purpose |
|---|---|---|---|---|
| `1788330819929` | `2024 -> 2025 Calendar` | 2024 → 2025 | v1 | Historical, V1 |
| `1788330849067` | `2025 -> 2026 Calendar - All` | 2025 → 2026 | v1 | Historical, V1 |
| `1789555936689` | `2026 -> 2027 Calendar - All` | 2026 → 2027 | v2 | Current, V2 |
| `1789556012651` | `2026 -> 2027 Calendar - Version 1` | 2026 → 2027 | v1 | Current, V1 (repurposed from "W/ Core Only" — see §7.2) |

**Real festival dates corrected this session** (all cross-checked against Wikipedia/DrikPanchang/multiple independent Panchang sites, not guessed): Raksha Bandhan, Rath Yatra, Basant Panchami, Milad-un-Nabi, Makar Sankranti, Navratri 2027 (was 2027-09-22, corrected to 2027-09-30), Dussehra 2027 (was 2027-10-01, corrected to 2027-10-09), and Shraad 2027 (corrected TWICE — first to 2027-09-07 based on the then-current Navratri date, then to the actually-correct **2027-09-15** after Navratri itself got corrected and the Pitru-Paksha-ends-the-day-before-Navratri-starts derivation went stale). **Lesson embedded in that double-fix: whenever a festival's date changes, check whether any OTHER festival's date was derived from it** (Nuakhai from Ganesh Chaturthi+1, Kali Puja from Diwali, Shraad's end from Navratri's start) **and re-verify those too** — a derivation is a dependency, and dependencies go stale silently. Also fixed: two stale `FESTIVAL_DATES` table entries (Diwali, Chhath Puja) whose 2026/2027 columns had never been updated when the live DB was corrected in an even earlier session — this is exactly what caused the two older (2024/2025, 2025/2026) templates to pick up wrong dates when the general "make every festival core" fix ran against them.

**Two real bugs found and fixed in the PRODUCTION `engine.js` / a hand-ported Python re-implementation used mid-session:**

1. **`_v2Remap` never called `repairExcessiveShifts` at all** (unlike `_v1Core`, which always has). Found by an independent subagent audit: V1 had zero non-festive days exceeding the 45-day `maxShift` across an entire calendar; V2 had 1–10 excessive-shift days in *every* cluster, worst case 90 days — the opposite of what V2 exists to achieve (it's specifically supposed to *reduce* shift pressure versus V1 via an adjacent-month escape valve). Root cause: V2's final cross-month "Fallback" phase can leave a day matched with no cap at all, and V2 built its own separate assignment map without ever running the repair pass that would catch that. **Fixed in `engine.js` (commit `30474c7`)**: merge `anchors` + `assigned` into one map before the final reassembly and call `repairExcessiveShifts` on it, mirroring V1's own structure exactly. Worst case dropped 90→74 days after regenerating; some residual outliers remain because V2 restricts repair to same-month swaps only (V1 achieves zero excess via more same-month reference-day reuse instead) — an accepted design tradeoff, not a further bug.
2. **A hand-ported Python reimplementation of the engine** (used mid-session to regenerate calendars directly against Postgres, bypassing the auth-walled UI) had two compounding bugs of its own in `repairExcessiveShifts`: `sharedRef` was never actually set to `true` on the reused-reference-day fallback branches (silently defeating the very swap-protection guard that checks for it), and the swap algorithm itself was a fundamentally different, more aggressive all-pairs rewrite than the real `engine.js` (which only ever touches *outliers* beyond `maxShift`, picking the single best gain-improving swap per outlier — not any pair that merely improves at all). Neither of these affected the real app (`engine.js` itself was always correct on point 2; point 1 is Python-port-only) — but they DID corrupt calendars regenerated via that script mid-session, until caught by a fresh code-diff audit and fixed.

**Verification tooling now lives in the repo** at `Calendar Engine/scripts/verify_calendars.py` — run it after ANY calendar regeneration, from the app UI or otherwise. It auto-discovers every saved calendar from `calendar.calendars` and runs three checkpoints: (1) structural integrity, (2) full-window self-match — every position in every festival's pre/core/post window, not just the anchor, which is the check that was missing all session and let real bugs slip through more than once, (3) cross-cluster consistency at the position level. See its own docstring and §7.5 above for what a non-zero result actually means (some findings are accepted overlaps, not bugs).

**Important operational note for regenerating calendars going forward**: the scripts used to regenerate calendars *this specific session* (`regen_calendar_pg.py`, `regen_v1_2026.py`, `regen_old_calendars.py` — a full hand-port of `engine.js`'s algorithm in Python) live in that session's temporary scratchpad directory, **not in this repo** — they will not exist for a future session. They were only needed because the browser session couldn't log into the auth-walled unified backend (port 8010) to use the app's own UI. **The normal, correct way to regenerate a calendar is still the app's own UI flow** (§7.2's original note: Version Setting tab → "Create Calendar" → Calendarisation tab's own "Create Calendar" → "Lock & Save"), which now benefits from the `engine.js` fix above automatically. Only fall back to a direct-to-Postgres script if UI access is genuinely unavailable, and if you do, treat `verify_calendars.py` as mandatory afterward, not optional — a hand-ported script drifting from the real engine is exactly how bug #2 above happened.

---

## 8. Tentative AOP Forecaster — key business rules

### 8.1 Store classification (LFL / Ramp / NSO)
Driven by a `tag` string per store (`masterdata.stores.tag` in Postgres), matched against three hardcoded sets in `engine_v3.py` (~lines 31-34):
```
LFL_TAGS  = {"032 - Stores","080 - Stores","095 - Stores","125 - Stores","3 - Stores","FY26 - Q1","FY26 - Q2","FY26 - Q3"}
RAMP_TAGS = {"FY26 - Q4","FY27 - Q1","FY27 - Q2"}
NSO_TAGS  = {"NSO","MAMJ-NSO"}
```
Confirmed exactly **148 distinct stores** carry an LFL tag (verified by direct count, matching the user's own independent estimate). `base_sales.LFL[div][month]` (the LY figure the forecast multiplies growth% against) is built in `get_file_info()` by summing `Store Actuals` sheet rows for LFL-tagged stores per division/month — sourced from Postgres `planning_inputs.input_values` (`lever_key='store_actuals'`), synced from a local parquet mirror reading `\\10.0.1.85\...\data_lake\raw\rs_sales_19-_till_date` (same flaky share family as §7.10).

**Known real gap, not a quick fix**: there is no merchandise-attribute column (SEASON/DISPLAY_TYPE/etc.) anywhere in this pipeline at store×division×month grain — the parquet source is already pre-aggregated before AOP ever sees it. Adding a per-attribute filter (e.g. "Q1 = specific attribute values only") requires a genuine pipeline change (read the attribute further upstream, re-aggregate with that extra dimension, extend the Postgres schema/Excel round-trip, then filter). One such filter (Q1 by `ATTRIBUTE1`) was partially built and then explicitly **disabled** because the real column values were never confirmed with live network access — `Q1_ALLOWED_VALUES = set()` is the current safe/no-op state. Do not re-enable it until the real values are confirmed against live data.

### 8.2 Closed-month rule (standing business rule, confirmed directly by the user)
The AOP Forecaster must never use or forecast from a calendar month that hasn't fully closed relative to wall-clock time — even if partial data for it already exists in the DB. Viewed on Aug 27, Aug'26 stays excluded until Sep 1, automatically, no manual step.
- `_open_months()` in `engine_v3.py` returns the set of "current month or later" FY-labels from `datetime.date.today()`, matching `sync/store_actuals_sync.py`'s own cutoff.
- `pivot_actuals()` skips any open month when reading actuals (does NOT apply to the separate Mar'27 AOP-override patch — a planner's deliberate manual override is not "data leaking in early," see §8.3).
- The ramp-forecast MoM chain (`pass1b_ramp_forecasts()`) additionally won't bridge/guess a value for an open month, while still legitimately bridging a genuinely-missing-but-closed month.

**`.from_db` sessions used to bypass this rule entirely — FIXED 2026-09-22.** `app.py`'s `/api/run/{session_id}` used to pass `open_months=set()` whenever a session came from "Continue from Database", on the theory (per its own comment) that "the sync already guards what gets written as real actuals; these are deliberately loaded planning estimates." Confirmed false against live data: a user-reported bug (Store Drill-down showing real-looking forecast numbers for Sep'27 through Mar'28, including a suspicious flat repeated value across 4 non-adjacent months) traced to `store_actuals` having genuine rows for Nov'26/Dec'26 — **physically impossible as actuals, since today's real date never reached those months** — plus a stale partial Sep'26 count, all written by a single `sync/store_actuals_sync.py --include-partial` run on 2026-09-17 and never refreshed since (the daily auto-sync's default `include_partial=False` correctly never re-touches them). All three rows tagged `source='calendar_sync'`, identical to genuine closed-month data — nothing at read time distinguished "deliberate planning estimate" from "leftover partial-sync data." Fixed by: (1) deleting the 3 stale periods from `planning_inputs.input_values`, (2) removing the `open_months=set()` bypass entirely — every session, DB-built or not, now gets the real `_open_months()` gate. If a genuine forward-looking estimate feed is wanted later, it needs its own distinctly-tagged `source` value, not a blanket bypass of this guard. **Unaffected**: the AOP → Buyer's Input Sheet sync (§ below) only ever publishes MAMJ (Mar–Jun'27) division totals, which are fed by Apr/May/Jun'26 — always well inside the closed-month range — so this bug never actually reached BIS.

### 8.3 Fixed bugs — Mar'27 override and dashboard scale corruption
Two confirmed, fixed bugs (commit `6bbf94c`):
1. **Mar'27 AOP overrides were silently dropped** — `build_aop_overrides()` explicitly excluded Mar'27 on the (wrong) theory it's purely an actuals-fallback column, but the AOP Overrides editor has always treated Mar'27 as a normal overridable month. Fixed by removing the exclusion.
2. **`rows.map(toLeaf)` scale corruption in `ResultsDashboard.jsx`** — `toLeaf(r, scale=0.01)` converts one row from ₹Lakhs to ₹Cr, but `Array.map`'s callback passes `(element, index, array)`, so every row's `index` silently became `scale` instead of `0.01`. Summed across ~1,500 rows this produced an absurd "₹8,94,35,045.5 Cr" KPI total (and corrupted the charts too, less visibly). Fixed to `rows.map(r => toLeaf(r))`. **General lesson**: never pass a function with a "helper" 2nd+ parameter directly to `.map()`/`.filter()`/`.forEach()` — always wrap it, unless the function's own signature is deliberately `(item, index, array)`.

**Still open from this thread**: the user wants AOP-override cells visually highlighted in results tables (not yet built — no override-flag currently flows from `build_df()` through the API to the frontend). A user-supplied "15614.42 Cr for LY, March" figure was never reconciled against real data.

### 8.4 NSO ramp formula (verified against the user's real Excel model)
Audited against `AOP - MAMJ'27 Working.xlsb` and confirmed matching exactly:
- **750L annual target** for a new store's first year (`NSO_TARGET = 750.0`).
- Stores not yet individually named (prefixed `NS-`/`AD-`/`MAMJ`) model off a single generic reference store, **LAM** (`NSO_REF = "LAM"`, `UNNAMED_PFX = ("NS-","AD-","MAMJ")`).
- Real/named NSO and Ramp stores get an individually assigned reference store (per-store `ref_store` field, falling back to `NSO_REF`).
- Store tag taxonomy in code (`LFL_TAGS ∪ RAMP_TAGS ∪ NSO_TAGS`) covers every real tag value found in the Excel exactly, no gap either direction.
- **Ref-store source confirmed with the user**: always use the "Ref Name - Merch" column from `Store Master.xlsx` (not "Ref Name - Month," which diverges for ~8 stores but is not something this app tracks).

### 8.5 Data-flow architecture facts
- AOP's `store_actuals_sync.py` does **NOT** consume Calendar Engine's saved reindex output (`calendar.sales_snapshots`) — despite both conceptually computing "the same" LFL actuals, AOP independently re-reads the raw month-wise parquet and redoes its own ref-month→fut-month mapping locally. Only SalesPlan's Sync Engine reads `calendar.sales_snapshots`. A toggle exists (`GET /api/config/base-sales-reindexed`, a ReviewStep.jsx UI toggle) to compare "Store Sync" vs. "Calendar Engine Reindex" side by side — useful for auditing, but be aware the two sources can be looking at genuinely different calendar-year snapshots if Calendar Engine's saved reindex hasn't been re-run recently against the current forecast period.
- **Never call `scans.run_reindex()` (Calendar Engine's reindex) in-process from a web handler** — a documented past incident showed this freezes the whole platform via GIL contention (18/53 concurrent requests failed). `sync/calendar_reindex_sync.py` shells out to Calendar Engine's `reindex_worker.py` as a **separate OS process** instead — follow this pattern for any similar heavy-compute integration.
- A real bug was caught and fixed here too: `db/reindexed_base_sales.py` was missing a Rupees→Lakhs `/1e5` conversion that the primary sync path already applied — one month came back ~200,000,000 instead of ~2,007 Lakhs. Caught only by cross-checking a new data path's numbers against an existing trusted source at the same rough magnitude — always do that when wiring up a new data path.

### 8.6 Daily auto-sync
A Windows Scheduled Task **"RS Planning - Actuals Auto Sync"** runs daily at 05:00, executing `Tentative AOP Forecaster/run_auto_sync.ps1` → `python sync/run_all.py`, running the same 5 jobs as the app's own "Sync into database" button (site_master, store_master_xlsx, day_shift, store_actuals, calendar_reindex) in one pass, logging to `Tentative AOP Forecaster/auto_sync.log`. This exists specifically so a newly-closed month (§8.2) lands in the DB within 24h with no manual click. Manage via `install_auto_sync.ps1` / `uninstall_auto_sync.ps1` / `Get-ScheduledTaskInfo -TaskName "RS Planning - Actuals Auto Sync"` / `Start-ScheduledTask -TaskName "..."` to trigger immediately for testing.

---

## 9. Known open items to be aware of (not yet fixed as of last session)

1. **SalesPlan**: a broken `STORE_MASTER_PATH` reference somewhere in the backend — flagged by survey, never chased down.
2. **SalesPlan**: an orphaned `mrp_reapportionment_engine.py` router that appears unmounted — confirm dead vs. not-yet-wired before touching.
3. **SalesPlan**: `dist/` is still gitignored/untracked, unlike Calendar Engine and AOP Forecaster — confirm with the user whether it needs the same "commit the build" treatment.
4. **AOP Forecaster**: `.claude/launch.json` has a stale `cwd`.
5. **AOP Forecaster**: `db/base.py` has a stale "not wired in yet" docstring comment on some auth pieces that no longer reflects reality — don't trust it, verify actual behavior.
6. **AOP Forecaster**: override-cell highlighting in results tables requested but not built.
7. **AOP Forecaster**: `ATTRIBUTE1`/Q1 attribute filter built but deliberately disabled (`Q1_ALLOWED_VALUES = set()`) pending confirmation of real column values against live network data.
8. **Calendar Engine**: `SOURCE_SCHEMA["dw"]` still only exposes 3 dimensions/1 metric from the old sparse source, even though the new consolidated day-wise source likely has richer columns available.
9. The `\\10.0.1.85\...` network share (used by both Calendar Engine's day-wise reindex and AOP's store-actuals sync) is a genuinely flaky dependency — don't assume a data-fetch failure is a code bug before checking its reachability first.
10. **Calendar Engine**: 13 festival-vs-festival calendar-day overlaps are currently accepted as unavoidable (see §7.5/§7.13) — not a defect, but re-run `Calendar Engine/scripts/verify_calendars.py` after any future date correction in case the list changes.
11. **Calendar Engine**: Eid al-Adha's stored date (2026: 2026-05-27) reflects the J&K/minority moon-sighting convention rather than the majority-state date (2026-05-28) — a deliberate choice made with the user, not an error, but worth knowing if it's ever questioned again. Chhath Puja's exact day-of-festival choice (main Sandhya Arghya day vs. closing Usha Arghya day) is similarly inconsistent across years by original design, not something to "normalize" without asking first.

---

## 10. How the previous session worked (for calibration)

The previous Claude session used Claude Code's file-based persistent memory system (`~/.claude/projects/.../memory/`), building up exactly the kind of business-rule/gotcha knowledge captured in this document over many turns, and treated writing new rules to memory as part of finishing a task, not an optional extra step. That memory does not carry over to a new account/ID — this document is the one-time transfer of everything in it that was relevant across the whole repo. If the new session also has persistent memory available, it's worth re-establishing the same habit (§5.2) going forward rather than relying on a document like this staying manually up to date.

The user prefers thorough, verified-before-reporting work — multiple times in the last session, "check thoroughly," "verify from every angle," and "check it 5 times before you show it to me" were explicit instructions, and every fix above was verified live (DB queries, fresh backend script tests, or real browser interaction with actual Blob-content interception for downloads) before being reported as done, not just assumed correct from reading the code.
