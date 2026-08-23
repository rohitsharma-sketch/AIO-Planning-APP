# Calendar Engine Frontend — Design Spec

**Sub-project B of 2**: build a React frontend for Calendar Engine against
the Postgres-backed `/api/calendar/*` REST API (sub-project A, already
built and merged — see
`docs/superpowers/specs/2026-08-23-calendar-engine-backend-migration-design.md`),
replacing the standalone vanilla-JS app (`Calendar Engine/calendar_engine.html`
+ `local_server.py`, port 7822). This is also the cutover point: once this
frontend is live and verified, the old standalone app, its 2 JSON→Postgres
sync jobs, and port 7822 finally retire — sub-project A deliberately left
all three running until this moment.

## Context

Calendar Engine builds the locked, festival-aligned day-shift calendar per
store cluster (used to reindex last year's sales onto this year's dates),
plus a store→cluster mapping editor and a sales-data-lake link/reindex
step. Today, all of that lives in one 4,165-line vanilla-JS HTML file
talking to a raw Python `http.server` backed by local JSON files. The
backend half of this migration is done: a FastAPI router at
`/api/calendar/*` (18 endpoints, resource-shaped, Postgres-backed,
`planner`-only writes) is mounted into the unified RS Planning Platform.
The old frontend was deliberately left untouched and still points at the
old backend — nothing yet points at the new one.

AOP Forecaster and SalesPlan — the platform's other two modules — turned
out NOT to share a design language, despite both being "part of the
platform": AOP Forecaster is a light navy/blue theme (`#1F3864` navy,
`#F4F6FB` background, CSS custom properties, system-font stack, 10px
border radius); SalesPlan is a dark charcoal/teal theme (`#1C2022`
background, `Satoshi`/`JetBrains Mono` fonts, a plain JS token object, no
radius token). Neither shares a token file with the other. This spec
settles on matching AOP Forecaster's theme specifically (see Visual
Identity below), not inventing a third look or attempting to unify the
other two.

## Goals

- Every screen in the old `calendar_engine.html` has a working React
  equivalent, calling the new `/api/calendar/*` API instead of the old
  JSON-blob endpoints.
- The festival-mapping/scoring "Engine" (the actual day-shift calculation
  logic — anchor assignment, remaining-day assignment, fallback, repair)
  ports with unchanged behavior, as a plain JS module with no framework
  coupling — this spec is about where the UI lives and what it talks to,
  not about redesigning the calculation.
- Visually matches AOP Forecaster's existing light navy theme, reusing its
  actual CSS custom properties rather than approximating them.
- Mounted into the unified platform at `/calendar/*`, following the exact
  static-serving + SPA-fallback pattern already used for `/aop/*` and
  `/planning/*`.
- Once this frontend is verified working end-to-end against real data, it
  becomes the trigger to retire `local_server.py`, port 7822, and the 2
  legacy sync jobs (`calendar_library_sync.py`,
  `store_calendar_cluster_sync.py`) — sub-project A's spec deferred all
  three to this exact point.

## Non-goals

- No changes to the `/api/calendar/*` API itself. If a genuine gap is
  found during implementation (the backend spec already documents one
  known gap — `festival_changelog`'s missing `pre`/`core`/`post` columns,
  deferred pending exactly this frontend needing them), that surfaces as
  a new, separately-scoped backend fix, not silently patched here.
- No redesign of the day-shift calculation algorithm itself — faithful
  port, not a rewrite. If the algorithm has bugs, they're preserved, not
  fixed, as part of this migration (a bug fix is separately-scoped work).
- No attempt to unify AOP Forecaster's and SalesPlan's visual themes with
  each other — out of scope, unrelated to this migration.
- No changes to AOP Forecaster's or SalesPlan's own frontends.
- The "Period Setting" tab stays a placeholder (its old "Phase 2" copy,
  reachable this time) — building actual period/fiscal-week functionality
  is future, separately-scoped work.

## Architecture

```
Calendar Engine/
  frontend/                      # NEW — sibling to local_server.py,
    package.json                 # matching how AOP Forecaster's and
    vite.config.js               # SalesPlan's frontends live under their
    index.html                   # own project folders, not under
    src/                         # RS Planning Platform/
      main.jsx
      App.jsx                    # tab bar + active-tab state (no router,
                                  # matching AOP Forecaster's approach)
      index.css                  # AOP Forecaster's actual CSS variables,
                                  # copied in (see Visual Identity)
      lib/
        api.js                   # fetch wrappers for all 18 endpoints
        engine.js                 # ported day-shift calculation (pure JS,
                                  # no React/DOM dependency)
        dateUtils.js              # ported date-math helpers the engine uses
      components/
        VersionSettingTab.jsx
        CalendarisationTab.jsx
        CalendarisationTab/
          ClusterTabs.jsx
          FestivalTable.jsx
          BulkAdjustPanel.jsx
          OutputPanel.jsx         # Day / Monthly / Validation sub-tabs
          CalendarLibrary.jsx     # saved-calendar list, embedded here
        PeriodSettingTab.jsx      # placeholder, reachable
        StoreClusterMappingTab.jsx
        StoreClusterMappingTab/
          StoreMappingPanel.jsx
          DateShiftPreviewPanel.jsx
        CalendarisedSalesTab.jsx
        CalendarisedSalesTab/
          LinkStatusPanel.jsx
          ReindexOutputPanel.jsx  # Reindexed Sales / Monthly Summary /
                                  # By Cluster / Run Details sub-tabs

RS Planning Platform/backend/app.py   # MODIFY — mount /calendar/*
```

Component boundaries mirror the old UI's own module-panel structure
(confirmed during exploration: 5 module panels, 2 of which have their own
internal sub-tab systems) — this is a faithful structural port, not a
reinterpretation. Each tab component owns its own screen's state and talks
to `lib/api.js`; there's no global state manager (Redux/Zustand/etc.) —
matching both existing frontends' approach of plain `useState`/`useEffect`,
appropriate at this scale (5 tabs, no cross-tab live sync requirement).

## Visual Identity

Copy AOP Forecaster's actual light-navy CSS custom properties into this
project's `src/index.css` — not re-derived, not approximated:
```css
--navy: #1F3864; --navy2: #2F5597; --navy3: #4472C4;
--light: #EEF3FB; --bg: #F4F6FB; --white: #FFFFFF; --char: #1A2332;
--muted: #6B7A99; --border: #D0D9ED; --green: #1A6B3C; --red: #C0392B;
--radius: 10px;
--shadow: 0 1px 3px rgba(31,56,100,0.08), 0 4px 16px rgba(31,56,100,0.06);
```
Font stack: `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`,
base `font-size: 14px`, `line-height: 1.5`. AOP Forecaster has multiple
swappable theme variants (`emerald`, `amber`, `coral`, `forest`) via
`[data-theme="..."]` attribute selectors — Calendar Engine's frontend
does NOT need to replicate the theme-switcher UI itself (that's an AOP
Forecaster feature, not a platform-wide one), just the default
navy/`:root` token values above.

## Tech Stack

- **React 18** (`^18.2.0`, matching AOP Forecaster's pin) + **Vite**
  (`^5.0.0`).
- **No router.** Tab navigation is local component state
  (`activeTab`/`setActiveTab` in `App.jsx`), matching AOP Forecaster's
  step-index approach — there's no case here for URL-addressable routes
  (no deep-linking requirement was raised, and the old UI itself was
  never URL-routed).
- **No HTTP client library** — plain `fetch`, matching AOP Forecaster
  (not SalesPlan's `axios`), consistent with matching AOP's approach
  throughout.
- **Plain `.jsx`, no TypeScript** — neither existing frontend uses it;
  introducing it here would be a platform-wide inconsistency for a
  YAGNI-violating reason (nothing about this migration specifically
  needs static typing that the other two modules don't already do
  without).
- `vite.config.js` sets `base: './'` — required for asset paths to
  resolve correctly once served under `/calendar/*` in the unified
  platform (same fix AOP Forecaster's own `vite.config.js` already
  documents needing, with the same explanatory comment carried over).

## API Integration (`src/lib/api.js`)

A thin wrapper module, one function per endpoint, matching the real
18-endpoint table (spec: `2026-08-23-calendar-engine-backend-migration-design.md`'s
API Design section) — e.g.:
```javascript
const BASE = '/api/calendar'

export async function fetchJson(path, opts) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'same-origin', ...opts })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

export const getCalendarLibrary = () => fetchJson('/calendar-library')
export const getCalendar = (id) => fetchJson(`/calendar-library/${id}`)
export const saveCalendar = (payload) => fetchJson('/calendar-library', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) })
export const deleteCalendar = (id) => fetchJson(`/calendar-library/${id}`, { method: 'DELETE' })
// ...one pair (or singleton) per remaining endpoint, same shape
```
`credentials: 'same-origin'` is required — this app is served from the
same origin as the unified platform's session cookie (set by the
platform's login page), not a separate origin needing CORS credential
handling. No dual "standalone vs. mounted" base-path logic (unlike AOP
Forecaster's `apiBase.js`) — this frontend has no meaningful standalone
mode; it only ever runs mounted under the unified platform, since it's
built to replace `local_server.py`, not to run alongside it.

Every `PUT`/`POST`/`DELETE` call can 401 (not logged in) or 403 (logged
in, wrong role — non-`planner` users). The UI shows read-only views by
default for non-planner roles (buyer/reviewer/approver) rather than
letting them attempt a write and hit a 403 — i.e., write controls (Save,
Delete, Replace Mapping, Import, Upsert Changelog Entry) are hidden or
disabled when the logged-in user's role isn't `planner`, discovered via
`GET /api/auth/me` (already exists, used by the platform's other two
frontends) called once on app load.

## The Engine Port (`src/lib/engine.js`, `src/lib/dateUtils.js`)

The old file's own comment-banner sections (`Default Festivals`,
`Festival Date Database`, `Multi-Year Festival Date Lookup`,
`Date Utilities`, `Festive Map`, `Scoring`, `Engine`, `Validation`,
`Monthly Summary`) contain the actual day-shift calculation — a 4-phase
algorithm (anchor assignment → remaining-day assignment → fallback →
repair-excessive-shifts) plus its supporting date math and scoring. This
is pure computation: no DOM access, no `fetch` calls, no framework
dependency in the original — confirmed during exploration. The
implementation plan extracts these sections verbatim into
`src/lib/engine.js` (calculation + scoring + validation) and
`src/lib/dateUtils.js` (date math), preserving function signatures and
logic exactly; only the persistence layer around them (`saveState`,
`loadState`, `_postState` in the old file) gets replaced by calls into
`lib/api.js`, since that's the part actually talking to the old backend.

## Component Breakdown

Five top-level tabs, matching the old UI's module panels exactly (no
panel added, none dropped except folding the previously-unreachable
"Period Setting" into a real, reachable tab per this project's own
decision):

1. **Version Setting** — reference/future year inputs, "Create Calendar"
   button (syncs years, triggers the engine). Small (~80 lines in the
   original).
2. **Calendarisation** — the core screen. Sub-components: drag-reorderable
   cluster tabs, a drag-reorderable festival table (pre/core/post day
   steppers, festival-date autocomplete), bulk-shift and bulk pre/core/post
   adjustment panels, an output section with 3 sub-tabs (Day / Monthly /
   Validation), and an embedded Calendar Library list (the saved-calendars
   view, backed by `GET/POST/DELETE /calendar-library[/{id}]`).
3. **Period Setting** — placeholder tab, same "Phase 2" copy as the
   original, now reachable from the nav bar.
4. **Store-Cluster Mapping** — 2 sub-tabs: Store Mapping (cluster grid,
   searchable table, `.xlsx`/`.csv` import with a diff-before-lock
   confirmation step, backed by `POST /import/store-cluster` then
   `PUT /store-cluster-map`, plus the change log via
   `GET /store-cluster-log`) and Date Shift Preview.
5. **Calendarised Sales** — data-lake link status (month-wise/day-wise,
   backed by `GET /salesdata/link` and `/salesdata/link-daywise`), a
   reindex trigger (`POST /salesdata/reindex`), and an output area with 4
   sub-tabs: Reindexed Sales, Monthly Summary, By Cluster, Run Details.

## Mounting (`RS Planning Platform/backend/app.py`)

Identical pattern to the existing `/aop/*` and `/planning/*` mounts:
```python
_calendar_dist = os.path.join(_HERE, "..", "..", "Calendar Engine", "frontend", "dist")
if os.path.isdir(_calendar_dist):
    app.mount("/calendar/assets", StaticFiles(directory=os.path.join(_calendar_dist, "assets")), name="calendar_assets")


@app.get("/calendar/{full_path:path}", include_in_schema=False)
def calendar_spa(full_path: str):
    return FileResponse(os.path.join(_calendar_dist, "index.html"))
```
No collision with the already-mounted `calendar_router` at `/api/calendar`
— static/SPA serving uses the bare `/calendar/*` path, exactly as `/aop/*`
(pages) and `/api/aop/*` (API) coexist today without conflict.

## Cutover Path

This is the deferred step sub-project A's spec called out repeatedly. Once
this frontend is built and verified against real data (see Testing):

1. Re-run `RS Planning Platform/backend/calendar_engine/migrate_from_json.py`
   one final time — it's re-runnable by design — to catch any edits made
   through the old `:7822` UI between sub-project A's original migration
   and this cutover.
2. Confirm the new frontend, now live at `/calendar/*` in the unified
   platform, shows that freshly-migrated data correctly.
3. Only then: stop `local_server.py` (port 7822), and delete
   `sync/calendar_library_sync.py` and
   `sync/store_calendar_cluster_sync.py` (the 2 legacy sync jobs — now
   fully superseded, since the new backend reads/writes Postgres directly
   and no longer needs a JSON-scraping bridge).
4. `Calendar Engine/calendar_engine.html` and `Calendar Engine/Local DB/*.json`
   can be archived or deleted once the cutover is confirmed stable — not
   part of this plan's own tasks (a follow-up cleanup step, done with
   fresh eyes after the new frontend has been live for a bit, not
   same-day as the cutover itself).

## Testing

Given there's no existing test tooling in either AOP Forecaster's or
SalesPlan's frontend (both are un-tested React apps, confirmed absent
during exploration — no `vitest`/`jest`/`@testing-library` in either
`package.json`), this plan matches that convention rather than
introducing a new one: verification is manual, browser-driven (build,
serve, click through each of the 5 tabs against the real `/api/calendar/*`
backend and real migrated data), not automated component tests. The
`lib/engine.js` port gets one exception — since it's pure, framework-free
logic, a lightweight verification step compares its output against the
old `calendar_engine.html`'s output for the same real input (open both
side by side, generate a calendar from the same reference/future year
pair, diff the resulting day-maps) — this is the byte-identical-output
check the backend spec's own Testing section already established as the
pattern for porting existing logic without introducing a test framework
neither sibling frontend has.

## Error Handling

Following the pattern already established by AOP Forecaster's frontend:
failed `fetch` calls surface as an inline error message near the action
that triggered them (not a global toast/modal system, since neither
sibling frontend has one). 401 (session expired) redirects to
`/login` (the unified platform's existing login page). 403 (wrong role)
is prevented proactively by hiding write controls for non-planner roles
(see API Integration), so a 403 in practice should only ever come from a
stale permission check (e.g. a role change mid-session) — shown as a
plain inline error, not specially handled.

## Open Risks

- **Old-UI persistence layer not read in detail.** The exploration pass
  identified `saveState()`/`loadState()`/`_postState()` in the old file
  as the current persistence layer but didn't read their bodies — the
  implementation plan needs to read them to confirm exactly what
  client-side state maps to which of the 18 new endpoints, since the old
  functions talk to the old JSON-blob shapes, not the new resource
  shapes.
- **Drag-and-drop reimplementation.** The old UI has hand-rolled
  drag-and-drop for both cluster tabs and festival table rows (native
  HTML5 drag events, per the exploration pass's section list). Porting
  this to React needs care — native drag events work differently inside
  React's synthetic event system than in vanilla JS; the plan should
  budget real implementation time here, not assume it's a trivial copy
  like the Engine port is.
- **`festival_changelog`'s known pre/core/post gap** (see sub-project A's
  spec, Goals section): if the Calendarisation tab's changelog UI needs
  to read/write `pre`/`core`/`post` overrides (the old UI's changelog
  clearly supports this — see the backend spec's own finding that real
  data carries these fields), this frontend will hit the exact schema gap
  sub-project A deferred. This needs to be resolved — likely the small
  follow-up schema migration sub-project A's Open Risks already
  anticipated — before or during this project's Calendarisation tab work,
  not discovered late.
- **No design-token unification effort.** This spec deliberately doesn't
  attempt to reconcile AOP Forecaster's and SalesPlan's differing themes
  — flagged again here since a future "make the platform look consistent"
  initiative would need to revisit all three frontends together, not just
  extend whatever Calendar Engine ends up doing.
