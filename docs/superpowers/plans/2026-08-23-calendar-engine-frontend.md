# Calendar Engine Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React 18 + Vite frontend for Calendar Engine at `Calendar Engine/frontend/`, replacing `calendar_engine.html` + `local_server.py` (port 7822) with a UI that talks to the already-built `/api/calendar/*` REST API, then cut over and retire the old system.

**Architecture:** Five top-level tab components (no router — local `activeModule` state, matching the old app's own `switchModule()` pattern and AOP Forecaster's step-index convention), a pure-JS `lib/` layer for the day-shift calculation engine (ported near-verbatim, framework-free) and the API client, mounted into the unified platform at `/calendar/*` exactly like the existing `/aop/*` and `/planning/*` mounts.

**Tech Stack:** React 18 (`^18.2.0`), Vite (`^5.0.0`), plain `.jsx` (no TypeScript), no router, no HTTP client library (plain `fetch`), matching AOP Forecaster's stack choices throughout.

**Spec:** `docs/superpowers/specs/2026-08-23-calendar-engine-frontend-design.md`

## Global Constraints

- Visual theme: AOP Forecaster's actual CSS custom properties (`--navy: #1F3864`, `--bg: #F4F6FB`, system-font stack, `--radius: 10px`) — copied in, not approximated.
- `vite.config.js` sets `base: './'` — required for `/calendar/*` mounting to resolve asset paths.
- All API calls go through `src/lib/api.js`, base path `/api/calendar`, `credentials: 'same-origin'`.
- Write controls (Save, Delete, Replace Mapping, Import, Upsert) are hidden/disabled for any logged-in user whose role isn't `planner` — checked once via `GET /api/auth/me` on app load, not discovered via a failed 403.
- No test framework — manual browser verification, matching both sibling frontends' convention (neither has automated frontend tests).
- "Period Setting" is a real, reachable nav tab this time (the old one had a stub panel but no nav button) — same "Phase 2" placeholder content, nothing functional.
- The day-shift calculation logic itself is a faithful port — same behavior, not a rewrite, not a bug fix.

---

## File Structure

```
Calendar Engine/frontend/
  package.json
  vite.config.js
  index.html
  src/
    main.jsx
    App.jsx                      # tab bar + activeModule state
    index.css                    # AOP Forecaster's tokens, copied in
    lib/
      api.js                     # fetch wrappers, all 18 endpoints + /api/auth/me
      dateUtils.js                # parseDate, fmtISO, fmtDisp, addDays, dayOfYear, calDiff, yearDays, weekNum
      festivalData.js             # DEFAULT_FESTIVALS, FESTIVAL_DB (data consts)
      engine.js                   # buildFestMap, getWeights, scoreMapping, generateMappings,
                                   # repairExcessiveShifts, validate, computeMonthly
    components/
      VersionSettingTab.jsx
      PeriodSettingTab.jsx
      CalendarisationTab/
        index.jsx                 # layout: sub-nav, left filter panel, main area
        ClusterTabs.jsx            # drag-and-drop cluster tab bar
        FestivalTable.jsx          # drag-and-drop festival row table
        BulkAdjustPanels.jsx       # Bulk Future Date Shift + Bulk Pre/Core/Post Adjust
        OutputSection.jsx          # Day / Monthly / Validation sub-tabs
        CalendarLibrary.jsx        # saved-calendar list
      StoreClusterMappingTab/
        index.jsx                  # sub-nav: Store Mapping / Date Shift Preview
        StoreMappingPanel.jsx
        DateShiftPreviewPanel.jsx
      CalendarisedSalesTab/
        index.jsx                  # link status + reindex trigger + output section
        LinkStatusPanel.jsx
        ReindexOutputPanel.jsx     # 4 sub-tabs

RS Planning Platform/backend/app.py   # MODIFY — mount /calendar/*
```

---

### Task 1: Project scaffold

**Files:**
- Create: `Calendar Engine/frontend/package.json`
- Create: `Calendar Engine/frontend/vite.config.js`
- Create: `Calendar Engine/frontend/index.html`
- Create: `Calendar Engine/frontend/src/main.jsx`
- Create: `Calendar Engine/frontend/src/index.css`
- Create: `Calendar Engine/frontend/src/App.jsx`

**Interfaces:**
- Produces: a runnable `npm run dev` (port 5177, matching the pattern of AOP's 5173/SalesPlan's 5175 — next free slot) and `npm run build`. `App.jsx` exports the shell every later task's tab component plugs into via `activeModule` state.

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "calendar-engine-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.0.0"
  }
}
```

- [ ] **Step 2: Write `vite.config.js`**

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Relative base: this app is only ever served mounted at /calendar/* in
  // the unified platform (no standalone mode) — a relative base resolves
  // built asset links correctly under that subpath. Same fix AOP
  // Forecaster's own vite.config.js already documents needing.
  base: './',
  server: {
    port: 5177,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      }
    }
  }
})
```

- [ ] **Step 3: Write `index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Calendarisation Suite</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Write `src/main.jsx`**

```javascript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 5: Write `src/index.css`**

Copy AOP Forecaster's actual light-navy tokens (`Tentative AOP Forecaster/frontend/src/index.css`'s `:root` block) verbatim — do not re-derive values:

```css
:root {
  --navy: #1F3864;
  --navy2: #2F5597;
  --navy3: #4472C4;
  --light: #EEF3FB;
  --bg: #F4F6FB;
  --white: #FFFFFF;
  --char: #1A2332;
  --muted: #6B7A99;
  --border: #D0D9ED;
  --green: #1A6B3C;
  --red: #C0392B;
  --radius: 10px;
  --shadow: 0 1px 3px rgba(31,56,100,0.08), 0 4px 16px rgba(31,56,100,0.06);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 14px;
  line-height: 1.5;
  background: var(--bg);
  color: var(--char);
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.mod-nav {
  display: flex;
  gap: 4px;
  padding: 12px 20px 0;
  background: var(--white);
  border-bottom: 1px solid var(--border);
}

.mod-tab {
  padding: 10px 18px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  border-radius: var(--radius) var(--radius) 0 0;
}

.mod-tab.active {
  color: var(--navy);
  background: var(--light);
}

.mod-tab:disabled {
  opacity: 0.5;
  cursor: default;
}

.module-panel {
  flex: 1;
  padding: 20px;
}

.card {
  background: var(--white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 16px;
  margin-bottom: 16px;
}
```

- [ ] **Step 6: Write `src/App.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { getMe } from './lib/api'
import VersionSettingTab from './components/VersionSettingTab'
import CalendarisationTab from './components/CalendarisationTab'
import PeriodSettingTab from './components/PeriodSettingTab'
import StoreClusterMappingTab from './components/StoreClusterMappingTab'
import CalendarisedSalesTab from './components/CalendarisedSalesTab'

const TABS = [
  { id: 'version', label: 'Version Setting', Component: VersionSettingTab },
  { id: 'calendarisation', label: 'Calendarisation', Component: CalendarisationTab },
  { id: 'period', label: 'Period Setting', Component: PeriodSettingTab },
  { id: 'salesdata', label: 'Store-Cluster Mapping', Component: StoreClusterMappingTab },
  { id: 'calendarisedsales', label: 'Calendarised Sales', Component: CalendarisedSalesTab },
]

export default function App() {
  const [activeModule, setActiveModule] = useState('calendarisation')
  const [me, setMe] = useState(null)

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null))
  }, [])

  const isPlanner = me?.role === 'planner'
  const ActiveComponent = TABS.find(t => t.id === activeModule)?.Component

  return (
    <div className="app-shell">
      <nav className="mod-nav">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`mod-tab${activeModule === t.id ? ' active' : ''}`}
            onClick={() => setActiveModule(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {ActiveComponent && <ActiveComponent isPlanner={isPlanner} />}
    </div>
  )
}
```

Every tab component receives `isPlanner` as a prop — write controls check this, matching the Global Constraint (proactive hiding, not reactive 403 handling).

- [ ] **Step 7: Verify it builds**

```bash
cd "Calendar Engine/frontend"
npm install
npm run build
```
Expected: builds clean (component files referenced by `App.jsx` don't exist yet — this step will fail until Task 4+ create stub components; for THIS task, temporarily stub each imported component as `export default function X() { return null }` in throwaway files just to prove the scaffold itself is valid, then delete those stubs — later tasks create the real files at the same paths). Actually: since `App.jsx` imports 5 components that don't exist until later tasks, create minimal placeholder files now so the build succeeds:

```jsx
// Calendar Engine/frontend/src/components/VersionSettingTab.jsx (placeholder — Task 4 replaces this)
export default function VersionSettingTab() { return <div className="module-panel">Version Setting</div> }
```
Create the same one-line placeholder pattern for `CalendarisationTab.jsx` (as a single file for now — Task 6 will convert it into the `CalendarisationTab/` directory), `PeriodSettingTab.jsx`, `StoreClusterMappingTab.jsx`, `CalendarisedSalesTab.jsx`. Each later task replaces its own placeholder.

```bash
npm run build
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
cd "Calendar Engine/frontend"
git add package.json vite.config.js index.html src/
git commit -m "Scaffold Calendar Engine React frontend"
```

---

### Task 2: API client

**Files:**
- Create: `Calendar Engine/frontend/src/lib/api.js`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `fetchJson(path, opts)`, `getMe()`, plus one function per endpoint in the table below. Every later task's component imports from this module — function names here are final, later tasks must match them exactly.

- [ ] **Step 1: Write `src/lib/api.js`**

Every one of the 18 `/api/calendar/*` endpoints (per the backend spec's API Design table), plus `GET /api/auth/me` (already exists, used by AOP Forecaster's and SalesPlan's frontends the same way):

```javascript
const BASE = '/api/calendar'

export async function fetchJson(path, opts) {
  const res = await fetch(`${BASE}${path}`, { credentials: 'same-origin', ...opts })
  if (res.status === 401) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`
    throw new Error('Not authenticated')
  }
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

const jsonPost = (path, body, method = 'POST') =>
  fetchJson(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function getMe() {
  const res = await fetch('/api/auth/me', { credentials: 'same-origin' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

// calendar-library
export const listCalendarLibrary = () => fetchJson('/calendar-library')
export const getCalendar = (id) => fetchJson(`/calendar-library/${id}`)
export const saveCalendar = (payload) => jsonPost('/calendar-library', payload)
export const deleteCalendar = (id) => fetchJson(`/calendar-library/${id}`, { method: 'DELETE' })

// store-cluster-map
export const getStoreClusterMap = () => fetchJson('/store-cluster-map')
export const putStoreClusterMap = (payload) => jsonPost('/store-cluster-map', payload, 'PUT')
export const getStoreClusterLog = () => fetchJson('/store-cluster-log')
export async function importStoreCluster(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/import/store-cluster`, { method: 'POST', credentials: 'same-origin', body: form })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

// cluster-profiles
export const getClusterProfiles = () => fetchJson('/cluster-profiles')
export const putClusterProfiles = (payload) => jsonPost('/cluster-profiles', payload, 'PUT')

// app-state
export const getAppState = () => fetchJson('/app-state')
export const putAppState = (payload) => jsonPost('/app-state', payload, 'PUT')

// festival-changelog
export const getFestivalChangelog = (rangeKey) => fetchJson(`/festival-changelog${rangeKey ? `?range_key=${encodeURIComponent(rangeKey)}` : ''}`)
export const putFestivalChangelog = (payload) => jsonPost('/festival-changelog', payload, 'PUT')

// salesdata-link-selection
export const getSalesdataLinkSelection = (sourceType) => fetchJson(`/salesdata-link-selection/${sourceType}`)
export const putSalesdataLinkSelection = (sourceType, payload) => jsonPost(`/salesdata-link-selection/${sourceType}`, payload, 'PUT')

// scan endpoints
export const getSalesdataLink = (refresh) => fetchJson(`/salesdata/link${refresh ? '?refresh=1' : ''}`)
export const getSalesdataLinkDaywise = (refresh) => fetchJson(`/salesdata/link-daywise${refresh ? '?refresh=1' : ''}`)
export const runReindex = (payload) => jsonPost('/salesdata/reindex', payload)
```

This maps the old app's 12 endpoints to their new equivalents:
- `GET/POST /api/state/app_state` → `getAppState()`/`putAppState()`
- `GET/POST /api/changelog` → `getFestivalChangelog()`/`putFestivalChangelog()`
- `GET /api/state/store_cluster_map` + `POST /api/state/store_cluster_map` → `getStoreClusterMap()`/`putStoreClusterMap()`
- `GET /api/state/store_cluster_log` → `getStoreClusterLog()` (no POST equivalent — the new backend computes and appends this itself from `putStoreClusterMap()`'s diff, never accepts client-submitted log entries)
- `POST /api/import/store_cluster` → `importStoreCluster()`
- `GET/POST /api/state/salesdata_link_selection` (+ `_daywise` variant) → `getSalesdataLinkSelection('mw'|'dw')`/`putSalesdataLinkSelection(...)`
- `GET/POST /api/state/calendar_library` → `listCalendarLibrary()`/`getCalendar()`/`saveCalendar()`/`deleteCalendar()` (the old app read/wrote the whole library as one blob; the new API is resource-shaped per calendar)
- `GET /api/salesdata/link` (+ `_daywise`) → `getSalesdataLink()`/`getSalesdataLinkDaywise()`
- `POST /api/salesdata/reindex` → `runReindex()`

- [ ] **Step 2: Verify it builds**

```bash
cd "Calendar Engine/frontend"
npm run build
```
Expected: PASS (this file has no consumers yet, but must be syntactically valid).

- [ ] **Step 3: Commit**

```bash
git add src/lib/api.js
git commit -m "Add API client for /api/calendar/* endpoints"
```

---

### Task 3: Engine + date-utils port

**Files:**
- Create: `Calendar Engine/frontend/src/lib/dateUtils.js`
- Create: `Calendar Engine/frontend/src/lib/festivalData.js`
- Create: `Calendar Engine/frontend/src/lib/engine.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `parseDate, fmtISO, fmtDisp, addDays, dayOfYear, calDiff, yearDays, weekNum` (from `dateUtils.js`); `DEFAULT_FESTIVALS, FESTIVAL_DB` (from `festivalData.js`); `buildFestMap, getWeights, scoreMapping, generateMappings, repairExcessiveShifts, validate, computeMonthly` (from `engine.js`). Task 6 (Calendarisation) is the primary consumer of all of these.

- [ ] **Step 1: Port `dateUtils.js`**

Copy `Calendar Engine/calendar_engine.html` lines 1340–1375 verbatim (the `─── Date Utilities` section: `parseDate`, `fmtISO`, `fmtDisp`, `addDays`, `dayOfYear`, `calDiff`, `yearDays`, `weekNum`) into `dateUtils.js`, converting from global `function` declarations to `export function` declarations — no logic changes, this section has no DOM dependency.

- [ ] **Step 2: Port `festivalData.js`**

Copy lines 1097–1160 verbatim (`─── Default Festivals` and `─── Festival Date Database (2026/2027)`: the `DEFAULT_FESTIVALS` and `FESTIVAL_DB` const declarations) into `festivalData.js`, converting to `export const`.

- [ ] **Step 3: Port `engine.js`**

Copy lines 1376–1732 verbatim (`─── Festive Map` through `─── Monthly Summary`: `buildFestMap`, `getWeights`, `scoreMapping`, `generateMappings` (with its 4 internal phases — anchor assignment, remaining days, fallback, repair), `repairExcessiveShifts`, `validate`, `computeMonthly`) into `engine.js`, converting to `export function`, and add `import { parseDate, fmtISO, fmtDisp, addDays, dayOfYear, calDiff, yearDays, weekNum } from './dateUtils'` at the top for whichever of these functions this section's code actually calls (confirm by reading the copied code — the extraction confirmed none of these functions have stray DOM (`g(...)`) calls, but they do call into the date-utils functions).

**Do not** port lines 1161–1339 (`─── Multi-Year Festival Date Lookup`) into this module — that section mixes pure lookup logic (`getActiveRegion`, `getRegionalWindows`, `searchFestDB`) with DOM-coupled autocomplete UI (`getGlobalSugBox`, `showFestSuggestions`, `hideFestSuggestions`, `applyFestSuggestionEl`, `applyFestSuggestion`, plus the `FESTIVAL_DATES` const it builds). Task 6 (the Festival Table component, which is where the old app's autocomplete lived) reads this range directly and re-implements the pure lookup half (`getActiveRegion`/`getRegionalWindows`/`searchFestDB`/`FESTIVAL_DATES`) as local module-level helpers colocated with the component, and reimplements the DOM-coupled half as normal React state/JSX (a suggestions dropdown driven by component state, not manual `getElementById`/`innerHTML`) — not a verbatim port, since React's own state model replaces manual DOM manipulation here.

- [ ] **Step 4: Verify it builds**

```bash
cd "Calendar Engine/frontend"
npm run build
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/dateUtils.js src/lib/festivalData.js src/lib/engine.js
git commit -m "Port day-shift calculation engine and date utilities"
```

---

### Task 4: Version Setting tab

**Files:**
- Modify: `Calendar Engine/frontend/src/components/VersionSettingTab.jsx` (replaces Task 1's placeholder)

**Interfaces:**
- Consumes: `getAppState`, `putAppState` from `lib/api.js`.
- Produces: `VersionSettingTab({ isPlanner })` — no other component depends on this one directly (it writes to shared `app_state`, which Task 6 also reads independently via its own `getAppState()` call, matching the old app's own decoupled-panel behavior).

- [ ] **Step 1: Write `VersionSettingTab.jsx`**

Matches the old panel's 5 cards (Calendar Years, Month Priority, Display Theme, Festive Category Legend, Mapping Type Reference — the last two are static reference content, not interactive):

```jsx
import { useState, useEffect } from 'react'
import { getAppState, putAppState } from '../lib/api'

const MAPPING_TYPES = [
  'Exact Match', 'Nearest Weekday', 'Cross-Month Shift', 'Regional Override',
  'Fallback Assignment', 'Manual Override', 'Repaired (Excessive Shift)',
]

export default function VersionSettingTab({ isPlanner }) {
  const [refYear, setRefYear] = useState('')
  const [futYear, setFutYear] = useState('')
  const [maxShift, setMaxShift] = useState('45')
  const [moPri, setMoPri] = useState('prev')
  const [status, setStatus] = useState(null)

  useEffect(() => {
    getAppState().then(s => {
      if (s.refYear) setRefYear(s.refYear)
      if (s.futYear) setFutYear(s.futYear)
      if (s.maxShift) setMaxShift(s.maxShift)
      if (s.moPri) setMoPri(s.moPri)
    }).catch(() => {})
  }, [])

  async function save(partial) {
    if (!isPlanner) return
    try {
      await putAppState(partial)
      setStatus({ ok: true, msg: 'Saved' })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="module-panel">
      <div className="card">
        <h3>Calendar Years</h3>
        <label>Reference Year</label>
        <input type="number" value={refYear} disabled={!isPlanner}
          onChange={e => setRefYear(e.target.value)}
          onBlur={() => save({ refYear })} />
        <label>Future Year</label>
        <input type="number" value={futYear} disabled={!isPlanner}
          onChange={e => setFutYear(e.target.value)}
          onBlur={() => save({ futYear })} />
        <label>Max Date Shift</label>
        <input type="number" value={maxShift} disabled={!isPlanner}
          onChange={e => setMaxShift(e.target.value)}
          onBlur={() => save({ maxShift })} />
      </div>

      <div className="card">
        <h3>Month Priority (non-festive days)</h3>
        <label>
          <input type="radio" name="moPri" value="prev" checked={moPri === 'prev'} disabled={!isPlanner}
            onChange={() => { setMoPri('prev'); save({ moPri: 'prev' }) }} />
          Same → Previous → Next
        </label>
        <label>
          <input type="radio" name="moPri" value="next" checked={moPri === 'next'} disabled={!isPlanner}
            onChange={() => { setMoPri('next'); save({ moPri: 'next' }) }} />
          Same → Next → Previous
        </label>
      </div>

      <div className="card">
        <h3>Festive Category Legend</h3>
        <ul>
          <li><span style={{ color: 'var(--navy3)' }}>■</span> Pre-Festive</li>
          <li><span style={{ color: 'var(--navy)' }}>■</span> Core Festive</li>
          <li><span style={{ color: 'var(--muted)' }}>■</span> Post-Festive</li>
          <li><span style={{ color: 'var(--border)' }}>■</span> Non-Festive</li>
        </ul>
      </div>

      <div className="card">
        <h3>Mapping Type Reference</h3>
        <ul>{MAPPING_TYPES.map(t => <li key={t}>{t}</li>)}</ul>
      </div>

      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
```

The old app had a separate "Display Theme" swatch-picker card (theme variants `emerald`/`amber`/`coral`/`forest` beyond the default navy) — per the spec's Visual Identity section, this frontend uses only AOP Forecaster's default navy tokens and does not carry forward the multi-theme switcher (that's an AOP Forecaster-specific feature, not part of this port's scope).

- [ ] **Step 2: Verify it builds and loads**

```bash
npm run build
```
Then start the unified app (`RS Planning Platform/backend`, `python -m uvicorn app:app --port 8010`) and Vite dev server (`npm run dev` from `Calendar Engine/frontend`), log in as `planner1`, navigate to Version Setting, confirm the year/max-shift/priority fields load real values from `GET /api/calendar/app-state` and that editing + blurring a field persists (confirm via `curl`/psql that `calendar.app_state_meta` updated).

- [ ] **Step 3: Commit**

```bash
git add src/components/VersionSettingTab.jsx
git commit -m "Implement Version Setting tab"
```

---

### Task 5: Period Setting placeholder tab

**Files:**
- Modify: `Calendar Engine/frontend/src/components/PeriodSettingTab.jsx` (replaces Task 1's placeholder)

**Interfaces:**
- Consumes: nothing.
- Produces: `PeriodSettingTab()` — static, no props needed.

- [ ] **Step 1: Write `PeriodSettingTab.jsx`**

Same "Phase 2" stub copy as the old app's unreachable panel (lines 899–906), now actually reachable from the nav bar:

```jsx
export default function PeriodSettingTab() {
  return (
    <div className="module-panel">
      <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
        <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--navy3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Phase 2
        </div>
        <h2 style={{ color: 'var(--navy)' }}>Period Setting</h2>
        <p style={{ color: 'var(--muted)' }}>
          Define fiscal periods, week numbering, and planning horizons. Configure period
          start and end dates aligned to your financial year calendar.
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify it builds**

```bash
npm run build
```
Expected: PASS. Manually confirm the "Period Setting" nav tab is now clickable and shows this placeholder.

- [ ] **Step 3: Commit**

```bash
git add src/components/PeriodSettingTab.jsx
git commit -m "Implement Period Setting placeholder tab (now reachable)"
```

---

### Task 6: Calendarisation tab — cluster tabs and festival table

**Files:**
- Create: `Calendar Engine/frontend/src/components/CalendarisationTab/ClusterTabs.jsx`
- Create: `Calendar Engine/frontend/src/components/CalendarisationTab/FestivalTable.jsx`
- Delete: `Calendar Engine/frontend/src/components/CalendarisationTab.jsx` (Task 1's single-file placeholder — this task starts converting it into a directory; Task 7-8 finish it)
- Create: `Calendar Engine/frontend/src/components/CalendarisationTab/index.jsx` (partial — cluster tabs + festival table wired in; Tasks 7-8 add the rest)

**Interfaces:**
- Consumes: `getClusterProfiles`, `putClusterProfiles` from `lib/api.js`; `DEFAULT_FESTIVALS` from `lib/festivalData.js`.
- Produces: `ClusterTabs({ profiles, activeIdx, onSwitch, onReorder, onAdd, isPlanner })`, `FestivalTable({ festivals, onChange, isPlanner })`. Tasks 7-8 extend `CalendarisationTab/index.jsx` with the bulk-adjust panels and output section this task doesn't cover.

- [ ] **Step 1: Write `ClusterTabs.jsx`**

Ports the drag-and-drop cluster-tab bar (old lines 2352–2397, 2082–2096) to React state instead of direct DOM manipulation:

```jsx
import { useState } from 'react'

export default function ClusterTabs({ profiles, activeIdx, onSwitch, onReorder, onAdd, isPlanner }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)

  function handleDrop(e, idx) {
    e.preventDefault()
    setDragOverIdx(null)
    if (dragIdx === null || dragIdx === idx) { setDragIdx(null); return }
    onReorder(dragIdx, idx)
    setDragIdx(null)
  }

  return (
    <div id="clusterTabsRow" style={{ display: 'flex', gap: '4px' }}>
      {profiles.map((cp, i) => (
        <button
          key={i}
          type="button"
          className={`cluster-tab${i === activeIdx ? ' active' : ''}${dragOverIdx === i ? ' cluster-drag-over' : ''}`}
          draggable={isPlanner}
          style={dragIdx === i ? { opacity: 0.4 } : undefined}
          onClick={() => onSwitch(i)}
          onDragStart={() => setDragIdx(i)}
          onDragOver={(e) => { if (dragIdx !== null && dragIdx !== i) { e.preventDefault(); setDragOverIdx(i) } }}
          onDrop={(e) => handleDrop(e, i)}
          onDragEnd={() => { setDragIdx(null); setDragOverIdx(null) }}
        >
          {cp.name}
        </button>
      ))}
      {isPlanner && (
        <button type="button" className="cluster-add-btn" onClick={onAdd} title="Add new cluster">+</button>
      )}
    </div>
  )
}
```

The reorder logic itself (splice-and-reinsert, plus the active-index adjustment when the dragged item crosses the active one) is the parent (`CalendarisationTab/index.jsx`)'s job — see Step 3, since it owns `clusterProfiles` state. This mirrors old lines 2374–2382's index-adjustment logic exactly:
```javascript
// inside the parent's onReorder(from, to):
const next = [...profiles]
const [moved] = next.splice(from, 1)
next.splice(to, 0, moved)
let nextActive = activeIdx
if (activeIdx === from) nextActive = to
else if (from < activeIdx && to >= activeIdx) nextActive--
else if (from > activeIdx && to <= activeIdx) nextActive++
```

- [ ] **Step 2: Write `FestivalTable.jsx`**

Ports the drag-and-drop festival row table (old lines 2322–2350, 2010–2029), columns: drag-handle, #, Festival Name, Reference Date, Future Date, Pre(days), Core(days), Post(days), delete:

```jsx
import { useState } from 'react'

export default function FestivalTable({ festivals, onChange, isPlanner }) {
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)

  function reorder(from, to) {
    const next = [...festivals]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    onChange(next)
  }

  function updateField(idx, field, value) {
    const next = festivals.map((f, i) => i === idx ? { ...f, [field]: value } : f)
    onChange(next)
  }

  function removeRow(idx) {
    onChange(festivals.filter((_, i) => i !== idx))
  }

  return (
    <table id="festTable">
      <thead>
        <tr>
          <th></th><th>#</th><th>Festival Name</th><th>Reference Date</th><th>Future Date</th>
          <th>Pre(days)</th><th>Core(days)</th><th>Post(days)</th><th></th>
        </tr>
      </thead>
      <tbody id="festTbody">
        {festivals.map((f, idx) => (
          <tr key={f.id}
            className={dragOverIdx === idx ? 'fest-row-drag-over' : undefined}
            onDragOver={(e) => { if (dragIdx !== null) { e.preventDefault(); setDragOverIdx(idx) } }}
            onDrop={(e) => { e.preventDefault(); setDragOverIdx(null); if (dragIdx !== null && dragIdx !== idx) reorder(dragIdx, idx); setDragIdx(null) }}
          >
            <td className="drag-handle" draggable={isPlanner}
              onDragStart={() => setDragIdx(idx)}
              onDragEnd={() => { setDragIdx(null); setDragOverIdx(null) }}
              title="Drag to reorder">::</td>
            <td>{idx + 1}</td>
            <td><input value={f.name} disabled={!isPlanner} onChange={e => updateField(idx, 'name', e.target.value)} /></td>
            <td><input type="date" value={f.refDate} disabled={!isPlanner} onChange={e => updateField(idx, 'refDate', e.target.value)} /></td>
            <td><input type="date" value={f.futDate} disabled={!isPlanner} onChange={e => updateField(idx, 'futDate', e.target.value)} /></td>
            <td><input type="number" value={f.pre} disabled={!isPlanner} onChange={e => updateField(idx, 'pre', +e.target.value)} /></td>
            <td><input type="number" value={f.core} disabled={!isPlanner} onChange={e => updateField(idx, 'core', +e.target.value)} /></td>
            <td><input type="number" value={f.post} disabled={!isPlanner} onChange={e => updateField(idx, 'post', +e.target.value)} /></td>
            <td>{isPlanner && <button onClick={() => removeRow(idx)} title="Remove">×</button>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
```

The old table also had a festival-name autocomplete (suggestions dropdown driven by `searchFestDB`/`FESTIVAL_DATES`, old lines 1222–1301) — this task does not include it; it's deferred to this same task's Step 3 as a documented follow-up within `CalendarisationTab/index.jsx`, since it's cosmetic (typing a full festival name still works without autocomplete) and not required for the table to be functional. Note it in the task's commit message as a known simplification.

- [ ] **Step 3: Write the partial `CalendarisationTab/index.jsx`**

Wires the two components together with real state and API calls (bulk-adjust panels and output section are added by Tasks 7-8, appended to this same file):

```jsx
import { useState, useEffect } from 'react'
import { getClusterProfiles, putClusterProfiles } from '../../lib/api'
import ClusterTabs from './ClusterTabs'
import FestivalTable from './FestivalTable'
import { DEFAULT_FESTIVALS } from '../../lib/festivalData'

let _nextFestivalId = 1000

export default function CalendarisationTab({ isPlanner }) {
  const [profiles, setProfiles] = useState([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    getClusterProfiles().then(({ profiles }) => {
      setProfiles(profiles.length ? profiles : [{ name: 'Cluster 1', region: 'all', nextId: 20, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })) }])
    }).catch(e => setStatus({ ok: false, msg: e.message }))
  }, [])

  async function persist(nextProfiles) {
    setProfiles(nextProfiles)
    if (!isPlanner) return
    try {
      await putClusterProfiles({
        profiles: nextProfiles.map(cp => ({ name: cp.name, region: cp.region, nextId: cp.nextId, festivals: cp.festivals })),
      })
      setStatus({ ok: true, msg: 'Saved' })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  function handleReorder(from, to) {
    const next = [...profiles]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    let nextActive = activeIdx
    if (activeIdx === from) nextActive = to
    else if (from < activeIdx && to >= activeIdx) nextActive--
    else if (from > activeIdx && to <= activeIdx) nextActive++
    setActiveIdx(nextActive)
    persist(next)
  }

  function handleAdd() {
    const next = [...profiles, { name: `Cluster ${profiles.length + 1}`, region: 'all', nextId: 20, festivals: DEFAULT_FESTIVALS.map(f => ({ ...f })) }]
    persist(next)
  }

  function handleFestivalsChange(nextFestivals) {
    const next = profiles.map((cp, i) => i === activeIdx ? { ...cp, festivals: nextFestivals } : cp)
    persist(next)
  }

  if (!profiles.length) return <div className="module-panel">Loading…</div>

  return (
    <div className="module-panel" style={{ display: 'flex', gap: '16px' }}>
      <main style={{ flex: 1 }}>
        <div className="card">
          <ClusterTabs profiles={profiles} activeIdx={activeIdx} onSwitch={setActiveIdx}
            onReorder={handleReorder} onAdd={handleAdd} isPlanner={isPlanner} />
          <FestivalTable festivals={profiles[activeIdx].festivals} onChange={handleFestivalsChange} isPlanner={isPlanner} />
        </div>
        {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
      </main>
    </div>
  )
}
```

Note: `nextId`/`source_festival_id` round-tripping (each festival needs a stable `id` distinct from array position, matching the backend's `source_festival_id` field and the old app's own `nextId` counter) — when `handleAdd` or an "Add Festival" control (Task 7) creates a new festival row, its `id` must come from `_nextFestivalId++` (or equivalent per-cluster counter matching `cp.nextId`), never reuse an existing id.

- [ ] **Step 4: Verify it builds and the drag-and-drop works**

```bash
npm run build
```
Then manually test in the browser: switch clusters, drag-reorder cluster tabs, drag-reorder festival rows, edit a festival's dates/pre/core/post and confirm it persists (`GET /api/calendar/cluster-profiles` reflects the change after reload).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Implement Calendarisation tab: cluster tabs and festival table with drag-and-drop"
```

---

### Task 7: Calendarisation tab — bulk adjust panels and filters

**Files:**
- Modify: `Calendar Engine/frontend/src/components/CalendarisationTab/index.jsx`
- Create: `Calendar Engine/frontend/src/components/CalendarisationTab/BulkAdjustPanels.jsx`

**Interfaces:**
- Consumes: `addDays`, `parseDate`, `fmtISO` from `lib/dateUtils.js`; the `persist`/`profiles`/`activeIdx` state Task 6 already established in `index.jsx`.
- Produces: `BulkAdjustPanels({ festivals, onChange, isPlanner })`.

- [ ] **Step 1: Write `BulkAdjustPanels.jsx`**

Two collapsible cards matching the old app's "Bulk Future Date Shift" and "Bulk Pre / Core / Post Adjust" (old lines ~680-760):

```jsx
import { useState } from 'react'
import { addDays, parseDate, fmtISO } from '../../lib/dateUtils'

export default function BulkAdjustPanels({ festivals, onChange, isPlanner }) {
  const [shiftOpen, setShiftOpen] = useState(false)
  const [daysOpen, setDaysOpen] = useState(false)
  const [monthOffset, setMonthOffset] = useState(0)
  const [daysMode, setDaysMode] = useState('set')
  const [bulkPre, setBulkPre] = useState(0)
  const [bulkCore, setBulkCore] = useState(0)
  const [bulkPost, setBulkPost] = useState(0)

  function applyShift() {
    if (!isPlanner || !monthOffset) return
    onChange(festivals.map(f => {
      const d = parseDate(f.futDate)
      d.setMonth(d.getMonth() + Number(monthOffset))
      return { ...f, futDate: fmtISO(d) }
    }))
  }

  function resetDates() {
    if (!isPlanner) return
    onChange(festivals.map(f => ({ ...f, futDate: f.refDate })))
  }

  function applyBulkDays() {
    if (!isPlanner) return
    onChange(festivals.map(f => ({
      ...f,
      pre: daysMode === 'set' ? Number(bulkPre) : f.pre + Number(bulkPre),
      core: daysMode === 'set' ? Number(bulkCore) : f.core + Number(bulkCore),
      post: daysMode === 'set' ? Number(bulkPost) : f.post + Number(bulkPost),
    })))
  }

  return (
    <>
      <div className="card">
        <h4 onClick={() => setShiftOpen(!shiftOpen)} style={{ cursor: 'pointer' }}>Bulk Future Date Shift</h4>
        {shiftOpen && (
          <>
            <select value={monthOffset} disabled={!isPlanner} onChange={e => setMonthOffset(e.target.value)}>
              {[-3, -2, -1, 0, 1, 2, 3].map(n => <option key={n} value={n}>{n > 0 ? `+${n}` : n} month{Math.abs(n) === 1 ? '' : 's'}</option>)}
            </select>
            <button disabled={!isPlanner} onClick={applyShift}>Apply Shift</button>
            <button disabled={!isPlanner} onClick={resetDates}>Reset Dates</button>
          </>
        )}
      </div>

      <div className="card">
        <h4 onClick={() => setDaysOpen(!daysOpen)} style={{ cursor: 'pointer' }}>Bulk Pre / Core / Post Adjust</h4>
        {daysOpen && (
          <>
            <select value={daysMode} disabled={!isPlanner} onChange={e => setDaysMode(e.target.value)}>
              <option value="set">Set to value</option>
              <option value="add">Add / Subtract</option>
            </select>
            <label>Pre <input type="number" value={bulkPre} disabled={!isPlanner} onChange={e => setBulkPre(e.target.value)} /></label>
            <label>Core <input type="number" value={bulkCore} disabled={!isPlanner} onChange={e => setBulkCore(e.target.value)} /></label>
            <label>Post <input type="number" value={bulkPost} disabled={!isPlanner} onChange={e => setBulkPost(e.target.value)} /></label>
            <button disabled={!isPlanner} onClick={applyBulkDays}>Apply & Save</button>
          </>
        )}
      </div>
    </>
  )
}
```

The old app scoped bulk operations to a month-pill picker (apply only to festivals in selected reference months, old `buildMonthPills()`/`#monthPillsContainer`) — this task's version applies bulk operations to ALL festivals in the active cluster unconditionally, a deliberate simplification (documented here, not hidden) since month-scoped bulk-editing is a secondary convenience feature, not required for the tab to be functional; a follow-up can add the month-pill scope selector if it turns out to be needed in practice.

- [ ] **Step 2: Wire it into `CalendarisationTab/index.jsx`**

Add the import and render it inside the existing `<div className="card">` block, above `<FestivalTable ...>`:
```jsx
import BulkAdjustPanels from './BulkAdjustPanels'
// ...
<BulkAdjustPanels festivals={profiles[activeIdx].festivals} onChange={handleFestivalsChange} isPlanner={isPlanner} />
```

- [ ] **Step 3: Verify it builds and the bulk operations work**

```bash
npm run build
```
Manually test: apply a bulk month shift, confirm all festival future-dates in the active cluster shift by that many months and persist; apply bulk pre/core/post in both "set" and "add" modes.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Implement Calendarisation tab: bulk adjust panels"
```

---

### Task 8: Calendarisation tab — output section and calendar library

**Files:**
- Modify: `Calendar Engine/frontend/src/components/CalendarisationTab/index.jsx`
- Create: `Calendar Engine/frontend/src/components/CalendarisationTab/OutputSection.jsx`
- Create: `Calendar Engine/frontend/src/components/CalendarisationTab/CalendarLibrary.jsx`
- Create: `Calendar Engine/frontend/src/components/CalendarisationTab/ChangeLogViewer.jsx`

**Interfaces:**
- Consumes: `generateMappings`, `validate`, `computeMonthly` from `lib/engine.js`; `listCalendarLibrary`, `getCalendar`, `saveCalendar`, `deleteCalendar`, `getFestivalChangelog` from `lib/api.js`.
- Produces: `OutputSection({ dayMap, validationIssues, monthlySummary })`, `CalendarLibrary({ onLoad, isPlanner })`, `ChangeLogViewer({ rangeKey })`. This completes `CalendarisationTab`.

- [ ] **Step 1: Write `OutputSection.jsx`**

3 sub-tabs (Day / Monthly / Validation), matching old lines 835–889:

```jsx
import { useState } from 'react'

export default function OutputSection({ dayMap, validationIssues, monthlySummary }) {
  const [activeSub, setActiveSub] = useState('day')

  if (!dayMap) return null

  return (
    <div className="card">
      <div className="tabs">
        <button className={activeSub === 'day' ? 'active' : ''} onClick={() => setActiveSub('day')}>Day-by-Day Mapping</button>
        <button className={activeSub === 'monthly' ? 'active' : ''} onClick={() => setActiveSub('monthly')}>Monthly Summary</button>
        <button className={activeSub === 'validation' ? 'active' : ''} onClick={() => setActiveSub('validation')}>Validation</button>
      </div>

      {activeSub === 'day' && (
        <table>
          <thead>
            <tr>
              <th>Ref Date</th><th>Ref Day</th><th>Ref Wk</th><th>Festival</th><th>Category</th>
              <th>Position</th><th>→</th><th>Future Date</th><th>Future Day</th><th>Future Wk</th>
              <th>Fut Festival</th><th>Mapping Type</th><th>Score</th><th>Mo</th><th>Wd</th><th>Day Delta</th>
            </tr>
          </thead>
          <tbody>
            {dayMap.map((row, i) => (
              <tr key={i}>
                <td>{row.refDate}</td><td>{row.refDay}</td><td>{row.refWeek}</td><td>{row.festival}</td>
                <td>{row.category}</td><td>{row.position}</td><td>→</td><td>{row.futDate}</td>
                <td>{row.futDay}</td><td>{row.futWeek}</td><td>{row.futFestival}</td><td>{row.mappingType}</td>
                <td>{row.score}</td><td>{row.monthDelta}</td><td>{row.weekdayDelta}</td><td>{row.dayDelta}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {activeSub === 'monthly' && monthlySummary && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          <div>
            <h4>By Reference Month</h4>
            <pre>{JSON.stringify(monthlySummary.byRef, null, 2)}</pre>
          </div>
          <div>
            <h4>By Future Month</h4>
            <pre>{JSON.stringify(monthlySummary.byFut, null, 2)}</pre>
          </div>
        </div>
      )}

      {activeSub === 'validation' && (
        <ul>
          {validationIssues.length === 0
            ? <li style={{ color: 'var(--green)' }}>No issues found.</li>
            : validationIssues.map((issue, i) => <li key={i} style={{ color: 'var(--red)' }}>{issue}</li>)}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Write `CalendarLibrary.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { listCalendarLibrary, getCalendar, saveCalendar, deleteCalendar } from '../../lib/api'

export default function CalendarLibrary({ onLoad, isPlanner, buildSavePayload }) {
  const [items, setItems] = useState([])
  const [status, setStatus] = useState(null)

  function refresh() {
    listCalendarLibrary().then(setItems).catch(e => setStatus({ ok: false, msg: e.message }))
  }

  useEffect(refresh, [])

  async function handleSave() {
    if (!isPlanner) return
    try {
      await saveCalendar(buildSavePayload())
      setStatus({ ok: true, msg: 'Calendar saved' })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function handleLoad(id) {
    const full = await getCalendar(id)
    onLoad(full)
  }

  async function handleDelete(id) {
    if (!isPlanner) return
    await deleteCalendar(id)
    refresh()
  }

  return (
    <div className="card" id="calLibrary">
      <h3>Calendar Library</h3>
      {isPlanner && <button onClick={handleSave}>Lock & Save Calendar</button>}
      <ul>
        {items.map(c => (
          <li key={c.id}>
            {c.name} ({c.refYear}→{c.futYear})
            <button onClick={() => handleLoad(c.id)}>Load</button>
            {isPlanner && <button onClick={() => handleDelete(c.id)}>Delete</button>}
          </li>
        ))}
      </ul>
      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
```

- [ ] **Step 3: Write `ChangeLogViewer.jsx`**

The old app auto-recorded a `festival_changelog` entry (with `refDate`/`futDate`/`pre`/`core`/`post`) every time a festival's date or day-count was edited (`saveChangeLog()`, triggered from `saveStateNow()`). The new `calendar.festival_changelog` table — per sub-project A's spec, Open Risks — has no columns for `pre`/`core`/`post`, only `ref_date`/`fut_date`; extending it is explicitly deferred, not part of this plan. So this task adds a **read-only** viewer only (`GET /festival-changelog`), and does **not** attempt to auto-write an entry on every festival edit — writing meaningfully (capturing the day-count overrides, not just dates) needs that schema extension first. This is a deliberate, documented scope boundary, not an oversight:

```jsx
import { useState, useEffect } from 'react'
import { getFestivalChangelog } from '../../lib/api'

export default function ChangeLogViewer({ rangeKey }) {
  const [entries, setEntries] = useState([])
  const [open, setOpen] = useState(false)

  function load() {
    getFestivalChangelog(rangeKey).then(setEntries)
  }

  return (
    <div className="card">
      <h4 onClick={() => { setOpen(!open); if (!open) load() }} style={{ cursor: 'pointer' }}>Change Log</h4>
      {open && (
        <>
          <p style={{ color: 'var(--muted)', fontSize: '12px' }}>
            Shows recorded date overrides only — pre/core/post day-count overrides aren't
            captured by the current backend schema (known gap, tracked separately).
          </p>
          <ul>
            {entries.map((e, i) => (
              <li key={i}>{e.clusterName} — {e.festivalName}: {e.refDate} → {e.futDate} ({e.savedAt})</li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Wire the engine and all three new components into `CalendarisationTab/index.jsx`**

Add engine-run state and the "Create Calendar" trigger (also reachable from Version Setting per the old app, but the actual computation lives here since it needs `profiles`):
```jsx
import { generateMappings, validate, computeMonthly } from '../../lib/engine'
import OutputSection from './OutputSection'
import CalendarLibrary from './CalendarLibrary'
import ChangeLogViewer from './ChangeLogViewer'
// ... inside the component:
const [dayMap, setDayMap] = useState(null)
const [validationIssues, setValidationIssues] = useState([])
const [monthlySummary, setMonthlySummary] = useState(null)

function runEngine() {
  const cp = profiles[activeIdx]
  const mappings = generateMappings(cp.festivals, /* refYear, futYear, maxShift, moPri from Version Setting's app-state */)
  setDayMap(mappings)
  setValidationIssues(validate(mappings))
  setMonthlySummary(computeMonthly(mappings))
}

function buildSavePayload() {
  return {
    id: Date.now(),
    name: `${profiles[activeIdx].name} Calendar`,
    refYear: /* from app-state */, futYear: /* from app-state */,
    savedAt: new Date().toISOString(),
    clusters: profiles.map(cp => ({ name: cp.name, region: cp.region, festivals: cp.festivals })),
    dayMap: /* group dayMap by cluster_name into {clusterName: [[refDate, futDate], ...]} shape */,
  }
}

function handleLoadFromLibrary(full) {
  setDayMap(/* full.dayMap converted to the flat day-row shape OutputSection expects, or re-run validate/computeMonthly against it */)
}
```
The exact `generateMappings` call signature and `buildSavePayload`'s `dayMap` grouping depend on reading the actual function signature copied in Task 3 (the extraction confirmed `generateMappings` exists at old line 1437 but this plan didn't capture its full parameter list) — read `src/lib/engine.js`'s `generateMappings` signature (from Task 3's copy) before finishing this wiring, and match its real parameters exactly rather than guessing.

Render `<OutputSection dayMap={dayMap} validationIssues={validationIssues} monthlySummary={monthlySummary} />`, `<CalendarLibrary onLoad={handleLoadFromLibrary} isPlanner={isPlanner} buildSavePayload={buildSavePayload} />`, and `<ChangeLogViewer rangeKey={`${refYear}-${futYear}`} />` (matching the old app's own `range_key` shape, `"{refYear}-{futYear}"`) in the component's return, plus a "Create Calendar" button calling `runEngine`.

- [ ] **Step 5: Verify it builds and a full generate→save→load cycle works**

```bash
npm run build
```
Manually test: click "Create Calendar", confirm the Day/Monthly/Validation sub-tabs populate; save to the library; reload the page, load that saved calendar back, confirm the day-map matches. Also open the Change Log viewer and confirm it shows real entries (e.g. after editing a festival date in the Festival Table and saving — but recall this task doesn't wire automatic changelog writes, so pre-existing entries from the original app's usage, if any migrated, are what should show; a fresh edit through this new UI won't appear there since write-on-edit isn't implemented).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Implement Calendarisation tab: output section, calendar library, and read-only change log viewer"
```

---

### Task 9: Store-Cluster Mapping tab — store mapping panel

**Files:**
- Modify: `Calendar Engine/frontend/src/components/StoreClusterMappingTab.jsx` (converts Task 1's placeholder into a directory, matching Task 6's pattern)
- Create: `Calendar Engine/frontend/src/components/StoreClusterMappingTab/index.jsx`
- Create: `Calendar Engine/frontend/src/components/StoreClusterMappingTab/StoreMappingPanel.jsx`

**Interfaces:**
- Consumes: `getStoreClusterMap`, `putStoreClusterMap`, `getStoreClusterLog`, `importStoreCluster` from `lib/api.js`.
- Produces: `StoreClusterMappingTab({ isPlanner })`, `StoreMappingPanel({ isPlanner })`.

- [ ] **Step 1: Write `StoreMappingPanel.jsx`**

Matches old lines 915–954: import button, download-template, change-log, cluster grid, searchable table with add/remove:

```jsx
import { useState, useEffect } from 'react'
import { getStoreClusterMap, putStoreClusterMap, getStoreClusterLog, importStoreCluster } from '../../lib/api'

export default function StoreMappingPanel({ isPlanner }) {
  const [mapping, setMapping] = useState(null)
  const [log, setLog] = useState([])
  const [showLog, setShowLog] = useState(false)
  const [search, setSearch] = useState('')
  const [importPreview, setImportPreview] = useState(null)
  const [status, setStatus] = useState(null)

  function refresh() {
    getStoreClusterMap().then(setMapping).catch(e => setStatus({ ok: false, msg: e.message }))
  }
  useEffect(refresh, [])

  async function handleFile(file) {
    if (!isPlanner || !file) return
    try {
      const result = await importStoreCluster(file)
      setImportPreview({ filename: file.name, rows: result.rows })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function confirmImport() {
    if (!isPlanner || !importPreview) return
    try {
      await putStoreClusterMap({ stores: importPreview.rows, source: importPreview.filename })
      setImportPreview(null)
      setStatus({ ok: true, msg: 'Store-cluster map replaced' })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  function downloadTemplate() {
    if (!mapping) return
    const csv = ['Store Name,Calendar Cluster', ...mapping.stores.map(s => `${s.store},${s.cluster}`)].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'store_cluster_map.csv'
    a.click()
  }

  async function showChangeLog() {
    setLog(await getStoreClusterLog())
    setShowLog(true)
  }

  if (!mapping) return <p>Loading…</p>

  const clusters = [...new Set(mapping.stores.map(s => s.cluster))].sort()
  const filtered = mapping.stores.filter(s =>
    !search || s.store.toLowerCase().includes(search.toLowerCase()) || s.cluster.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <div className="card">
        <p>{mapping.stores.length} stores mapped. Locked: {mapping.locked ? 'Yes' : 'No'}.
           Source: {mapping.source || '—'}. Last edited: {mapping.editedAt || '—'}.</p>
        {isPlanner && (
          <>
            <input type="file" accept=".xlsx,.xlsm,.csv,.txt,.tsv" onChange={e => handleFile(e.target.files[0])} />
            <button onClick={downloadTemplate}>Download Current Template (CSV)</button>
            <button onClick={showChangeLog}>Change Log</button>
          </>
        )}
        <p style={{ color: 'var(--muted)', fontSize: '12px' }}>Expected columns: "Store Name", "CALENDAR CLUSTER"</p>
      </div>

      {importPreview && (
        <div className="card">
          <h4>Confirm import: {importPreview.filename} ({importPreview.rows.length} stores)</h4>
          <button onClick={confirmImport}>Confirm & Replace Mapping</button>
          <button onClick={() => setImportPreview(null)}>Cancel</button>
        </div>
      )}

      <div className="card">
        <h4>Stores per calendar cluster</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '8px' }}>
          {clusters.map(c => (
            <div key={c}>{c}: {mapping.stores.filter(s => s.cluster === c).length}</div>
          ))}
        </div>
      </div>

      <div className="card">
        <input placeholder="Search stores…" value={search} onChange={e => setSearch(e.target.value)} />
        <span>{filtered.length} of {mapping.stores.length}</span>
        <table>
          <thead><tr><th>#</th><th>Store Name</th><th>Calendar Cluster</th></tr></thead>
          <tbody>
            {filtered.map((s, i) => (
              <tr key={s.store}><td>{i + 1}</td><td>{s.store}</td><td>{s.cluster}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {showLog && (
        <div className="card">
          <h4>Change Log</h4>
          <ul>
            {log.map((entry, i) => (
              <li key={i}>{entry.at} — {entry.summary} (added {entry.added}, removed {entry.removed}, reassigned {entry.reassigned})</li>
            ))}
          </ul>
          <button onClick={() => setShowLog(false)}>Close</button>
        </div>
      )}
      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
```

The old app had inline per-store add/remove controls (`scmAddStore`/`scmRemoveStore`) alongside the bulk-import flow. This task's version supports only the bulk-import-and-replace path (which is the primary, backend-supported flow — `PUT /store-cluster-map` is a full replace, matching the API's own semantics) and drops the individual add/remove-one-store UI as a deliberate simplification — noted here, not silently dropped — since it duplicates what re-importing an edited CSV/xlsx already accomplishes.

- [ ] **Step 2: Write `index.jsx`**

```jsx
import { useState } from 'react'
import StoreMappingPanel from './StoreMappingPanel'
import DateShiftPreviewPanel from './DateShiftPreviewPanel'

export default function StoreClusterMappingTab({ isPlanner }) {
  const [sub, setSub] = useState('map')
  return (
    <div className="module-panel">
      <div className="cal-sub-nav">
        <button className={sub === 'map' ? 'active' : ''} onClick={() => setSub('map')}>Store Mapping</button>
        <button className={sub === 'shift' ? 'active' : ''} onClick={() => setSub('shift')}>Date Shift Preview</button>
      </div>
      {sub === 'map' ? <StoreMappingPanel isPlanner={isPlanner} /> : <DateShiftPreviewPanel />}
    </div>
  )
}
```
(`DateShiftPreviewPanel` doesn't exist yet — Task 10 creates it; for now this task can temporarily stub it as `export default function DateShiftPreviewPanel() { return null }` in its own file, which Task 10 replaces.)

- [ ] **Step 3: Verify it builds and import works end-to-end**

```bash
npm run build
```
Manually test: upload a real store/cluster CSV, confirm the preview shows parsed rows, confirm "Confirm & Replace" actually updates `calendar.store_calendar_clusters` (check via psql) and the change log records the diff.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Implement Store-Cluster Mapping tab: store mapping panel"
```

---

### Task 10: Store-Cluster Mapping tab — date shift preview panel

**Files:**
- Create: `Calendar Engine/frontend/src/components/StoreClusterMappingTab/DateShiftPreviewPanel.jsx` (replaces Task 9's stub)

**Interfaces:**
- Consumes: `listCalendarLibrary`, `getCalendar` from `lib/api.js`; `getStoreClusterMap` from `lib/api.js`.
- Produces: `DateShiftPreviewPanel()`.

- [ ] **Step 1: Write `DateShiftPreviewPanel.jsx`**

Matches old lines 956–993: calendar picker, level toggle, filters, sortable table:

```jsx
import { useState, useEffect, useMemo } from 'react'
import { listCalendarLibrary, getCalendar, getStoreClusterMap } from '../../lib/api'

export default function DateShiftPreviewPanel() {
  const [calendars, setCalendars] = useState([])
  const [calendarId, setCalendarId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [storeMap, setStoreMap] = useState(null)
  const [level, setLevel] = useState('store')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('storeDate')

  useEffect(() => {
    listCalendarLibrary().then(setCalendars)
    getStoreClusterMap().then(setStoreMap)
  }, [])

  useEffect(() => {
    if (calendarId) getCalendar(calendarId).then(setDetail)
  }, [calendarId])

  const rows = useMemo(() => {
    if (!detail || !storeMap) return []
    const out = []
    for (const store of storeMap.stores) {
      const pairs = detail.dayMap[store.cluster] || []
      for (const [refDate, futDate] of pairs) {
        out.push({ store: store.store, cluster: store.cluster, refDate, futDate })
      }
    }
    return out.filter(r => !search || r.store.toLowerCase().includes(search.toLowerCase()) || r.cluster.toLowerCase().includes(search.toLowerCase()))
  }, [detail, storeMap, search])

  return (
    <div className="card">
      <select value={calendarId || ''} onChange={e => setCalendarId(e.target.value)}>
        <option value="">Select a calendar…</option>
        {calendars.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <label><input type="radio" checked={level === 'store'} onChange={() => setLevel('store')} /> Store × Day</label>
      <label><input type="radio" checked={level === 'cluster'} onChange={() => setLevel('cluster')} /> Cluster × Day</label>
      <input placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} />
      <table>
        <thead><tr><th>Store</th><th>Cluster</th><th>Ref Date</th><th>Future Date</th></tr></thead>
        <tbody>
          {rows.map((r, i) => <tr key={i}><td>{r.store}</td><td>{r.cluster}</td><td>{r.refDate}</td><td>{r.futDate}</td></tr>)}
        </tbody>
      </table>
    </div>
  )
}
```

The "Cluster × Day" level aggregation (deduplicating rows to one per cluster instead of one per store) and CSV download are left as a follow-up — the current version always shows store-level rows regardless of the `level` toggle. Note this explicitly rather than half-implementing a silently-broken toggle.

- [ ] **Step 2: Wire it into `StoreClusterMappingTab/index.jsx`**, replacing the stub import.

- [ ] **Step 3: Verify it builds and shows real data**

```bash
npm run build
```
Manually test: select a saved calendar, confirm the table populates with real store/cluster/date rows from that calendar's `dayMap`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Implement Store-Cluster Mapping tab: date shift preview panel"
```

---

### Task 11: Calendarised Sales tab — link status and reindex trigger

**Files:**
- Modify: `Calendar Engine/frontend/src/components/CalendarisedSalesTab.jsx` (converts Task 1's placeholder into a directory)
- Create: `Calendar Engine/frontend/src/components/CalendarisedSalesTab/index.jsx`
- Create: `Calendar Engine/frontend/src/components/CalendarisedSalesTab/LinkStatusPanel.jsx`

**Interfaces:**
- Consumes: `getSalesdataLink`, `getSalesdataLinkDaywise`, `getSalesdataLinkSelection`, `putSalesdataLinkSelection`, `runReindex`, `listCalendarLibrary` from `lib/api.js`.
- Produces: `CalendarisedSalesTab({ isPlanner })`, `LinkStatusPanel({ sourceType, isPlanner })`.

- [ ] **Step 1: Write `LinkStatusPanel.jsx`**

One instance per source (`mw`/`dw`), matches old lines ~1000-1030:

```jsx
import { useState, useEffect } from 'react'
import { getSalesdataLink, getSalesdataLinkDaywise, getSalesdataLinkSelection, putSalesdataLinkSelection } from '../../lib/api'

const FETCHERS = { mw: getSalesdataLink, dw: getSalesdataLinkDaywise }
const LABELS = { mw: 'Month-wise', dw: 'Day-wise' }

export default function LinkStatusPanel({ sourceType, isPlanner, onSelectionChange }) {
  const [link, setLink] = useState(null)
  const [selection, setSelection] = useState(null)
  const [selectedMonths, setSelectedMonths] = useState([])

  function refresh(force) {
    FETCHERS[sourceType](force).then(setLink)
  }
  useEffect(() => {
    refresh(false)
    getSalesdataLinkSelection(sourceType).then(s => { setSelection(s); setSelectedMonths(s.months || []) })
  }, [sourceType])

  async function sync() {
    if (!isPlanner || !link) return
    const payload = { months: selectedMonths, path: link.path, syncedAt: new Date().toISOString() }
    await putSalesdataLinkSelection(sourceType, payload)
    setSelection(payload)
    onSelectionChange?.(sourceType, payload)
  }

  if (!link) return <p>Loading…</p>

  return (
    <div className="card">
      <h4>Link Sales Data Source · {LABELS[sourceType]}</h4>
      {link.ok ? (
        <>
          <p>{link.rowCount?.toLocaleString()} rows across {link.months?.length} months. Range: {link.dateRange?.min} – {link.dateRange?.max}.</p>
          <p>Stores: {link.stores?.matched?.length} matched, {link.stores?.unmatchedInSource?.length} unmatched in source.</p>
          <div>
            {(link.months || []).map(m => (
              <label key={m.month}>
                <input type="checkbox" checked={selectedMonths.includes(m.month)} disabled={!isPlanner}
                  onChange={e => setSelectedMonths(e.target.checked ? [...selectedMonths, m.month] : selectedMonths.filter(x => x !== m.month))} />
                {m.month} ({m.rows.toLocaleString()})
              </label>
            ))}
          </div>
          {isPlanner && <button onClick={sync}>Sync Selected Months</button>}
        </>
      ) : (
        <p style={{ color: 'var(--red)' }}>{link.error}</p>
      )}
      <button onClick={() => refresh(true)}>Refresh</button>
      {selection?.syncedAt && <p style={{ color: 'var(--muted)' }}>Last synced: {selection.syncedAt}</p>}
    </div>
  )
}
```

- [ ] **Step 2: Write `index.jsx`** (partial — Task 12 adds the reindex output section)

```jsx
import { useState } from 'react'
import LinkStatusPanel from './LinkStatusPanel'

export default function CalendarisedSalesTab({ isPlanner }) {
  const [selections, setSelections] = useState({})

  function handleSelectionChange(sourceType, payload) {
    setSelections(prev => ({ ...prev, [sourceType]: payload }))
  }

  return (
    <div className="module-panel">
      <LinkStatusPanel sourceType="mw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />
      <LinkStatusPanel sourceType="dw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />
    </div>
  )
}
```

- [ ] **Step 3: Verify it builds and both link panels show real data**

```bash
npm run build
```
Manually test: both month-wise and day-wise panels load real scan results (requires the `\\10.0.1.85\...` network path to be reachable — same environmental dependency noted in sub-project A), select some months, sync, confirm `calendar.salesdata_link_selection` updates.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Implement Calendarised Sales tab: link status panels"
```

---

### Task 12: Calendarised Sales tab — reindex trigger and output section

**Files:**
- Modify: `Calendar Engine/frontend/src/components/CalendarisedSalesTab/index.jsx`
- Create: `Calendar Engine/frontend/src/components/CalendarisedSalesTab/ReindexOutputPanel.jsx`

**Interfaces:**
- Consumes: `runReindex`, `listCalendarLibrary` from `lib/api.js`; `selections` state Task 11 established in `index.jsx`.
- Produces: `ReindexOutputPanel({ result })`. Completes `CalendarisedSalesTab`.

- [ ] **Step 1: Write `ReindexOutputPanel.jsx`**

4 sub-tabs matching old lines 1050–1053, 3990–4051:

```jsx
import { useState } from 'react'

export default function ReindexOutputPanel({ result }) {
  const [activeSub, setActiveSub] = useState('reindexed')
  if (!result) return null

  return (
    <div className="card">
      <div className="tabs">
        <button className={activeSub === 'reindexed' ? 'active' : ''} onClick={() => setActiveSub('reindexed')}>Reindexed Sales</button>
        <button className={activeSub === 'summary' ? 'active' : ''} onClick={() => setActiveSub('summary')}>Monthly Summary</button>
        <button className={activeSub === 'cluster' ? 'active' : ''} onClick={() => setActiveSub('cluster')}>By Cluster</button>
        <button className={activeSub === 'raw' ? 'active' : ''} onClick={() => setActiveSub('raw')}>Run Details</button>
      </div>

      {activeSub === 'reindexed' && (
        <table>
          <thead>
            <tr>
              <th>{result.grain === 'store_division' ? 'Store / Division' : 'Store'}</th>
              {result.columns.map(c => <th key={c}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {/* pivot result.rows (long-form: {store, division?, col, value}) wide by result.columns per store(+division) key */}
          </tbody>
        </table>
      )}

      {activeSub === 'summary' && <p>Monthly aggregation — sum {result.rows.length} rows by month across all stores.</p>}
      {activeSub === 'cluster' && <p>Cluster aggregation — sum rows by each store's calendar cluster.</p>}

      {activeSub === 'raw' && (
        <div>
          <p>Source: {result.source} ({result.grain}, metric {result.metric})</p>
          <p>Rows read: {result.rowsRead}, rows mapped: {result.rowsMapped}</p>
          <p>Used frozen sync: {result.usedFrozenSync ? 'Yes' : 'No'}</p>
          <p>Unmapped stores: {result.unmappedStores?.length || 0}</p>
          <p>Unmapped dates: {result.unmappedDateCount || 0} (sample: {(result.unmappedDateSample || []).join(', ')})</p>
        </div>
      )}
    </div>
  )
}
```

The "Reindexed Sales" table's wide-pivot rendering (long-form `rows` → one column per date/month) and both CSV download buttons (`rxDownload`) are left as a follow-up — the raw structure is displayed but not yet pivoted/exportable. Note this explicitly; it's real, scoped-out work, not an oversight to silently skip.

- [ ] **Step 2: Wire the reindex trigger and this panel into `index.jsx`**

```jsx
import { useState } from 'react'
import LinkStatusPanel from './LinkStatusPanel'
import ReindexOutputPanel from './ReindexOutputPanel'
import { runReindex, listCalendarLibrary } from '../../lib/api'

export default function CalendarisedSalesTab({ isPlanner }) {
  const [selections, setSelections] = useState({})
  const [calendars, setCalendars] = useState([])
  const [source, setSource] = useState('dw')
  const [calendarId, setCalendarId] = useState(null)
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState(null)

  useState(() => { listCalendarLibrary().then(cs => setCalendars(cs.filter(c => c.mappingSummary?.length))) }, [])

  function handleSelectionChange(sourceType, payload) {
    setSelections(prev => ({ ...prev, [sourceType]: payload }))
  }

  async function runRx() {
    if (!isPlanner || !calendarId) return
    try {
      const cal = calendars.find(c => c.id === Number(calendarId))
      const detail = await (await import('../../lib/api')).getCalendar(calendarId)
      const sel = selections[source]
      const r = await runReindex({
        source, months: sel?.months || [],
        storeCluster: {}, /* built from getStoreClusterMap() — {store: cluster} */
        dayMap: detail.dayMap, syncedAt: sel?.syncedAt,
      })
      setResult(r)
      if (!r.ok) setStatus({ ok: false, msg: r.error })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="module-panel">
      <LinkStatusPanel sourceType="mw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />
      <LinkStatusPanel sourceType="dw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />

      <div className="card">
        <h4>Run Reindex</h4>
        <select value={source} onChange={e => setSource(e.target.value)}>
          <option value="dw">Day-wise NETAMT</option>
          <option value="mw">Month-wise Sales Value</option>
        </select>
        <select value={calendarId || ''} onChange={e => setCalendarId(e.target.value)}>
          <option value="">Select a locked calendar…</option>
          {calendars.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {isPlanner && <button onClick={runRx}>Run Reindex</button>}
        {status && <p style={{ color: 'var(--red)' }}>{status.msg}</p>}
      </div>

      <ReindexOutputPanel result={result} />
    </div>
  )
}
```
The `storeCluster: {}` payload (a `{store: cluster}` lookup the backend's `run_reindex` needs) must be built from `getStoreClusterMap()`'s `stores` array — read that function's real return shape (Task 9 already established it: `{stores: [{store, cluster}, ...], ...}`) and convert it to a plain object before this task is done; don't ship it as a literal empty object.

- [ ] **Step 3: Verify it builds and a full reindex run works**

```bash
npm run build
```
Manually test: select a locked calendar, run reindex, confirm the 4 output sub-tabs populate with real data from `POST /api/calendar/salesdata/reindex`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Implement Calendarised Sales tab: reindex trigger and output panel"
```

---

### Task 13: Mount into the unified platform and verify end-to-end

**Files:**
- Modify: `RS Planning Platform/backend/app.py`

**Interfaces:**
- Consumes: `Calendar Engine/frontend/dist` (built by Task 1-12's `npm run build`).
- Produces: `/calendar/*` live on the unified app.

- [ ] **Step 1: Add the static mount and SPA fallback to `app.py`**

Add near the existing `/aop/*`/`/planning/*` mounts (after the `_planning_dist` block, before the `@app.get("/aop/{full_path:path}")` route):

```python
_calendar_dist = os.path.join(_HERE, "..", "..", "Calendar Engine", "frontend", "dist")
if os.path.isdir(_calendar_dist):
    app.mount("/calendar/assets", StaticFiles(directory=os.path.join(_calendar_dist, "assets")), name="calendar_assets")


@app.get("/calendar/{full_path:path}", include_in_schema=False)
def calendar_spa(full_path: str):
    return FileResponse(os.path.join(_calendar_dist, "index.html"))
```

- [ ] **Step 2: Build the frontend and restart the unified app**

```bash
cd "Calendar Engine/frontend"
npm run build
```
Then restart uvicorn on `:8010` from `RS Planning Platform/backend` (kill any process already bound to that port first).

- [ ] **Step 3: Live smoke test**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/calendar/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/calendar/assets/  # any hashed asset filename from dist/assets
```
Expected: both 200. Then in a real browser: log in as `planner1`, navigate to `/calendar/`, click through all 5 tabs, confirm each loads real data from the API (not errors), confirm write actions (editing a festival, replacing the store-cluster map) persist and are visible after a page reload.

Also confirm read-only enforcement: log in as `buyer1`, confirm write controls (Save, Delete, Replace Mapping, Import buttons) are hidden/disabled across all tabs, matching the Global Constraint.

- [ ] **Step 4: Commit**

```bash
cd "RS Planning Platform/backend"
git add app.py
git commit -m "Mount Calendar Engine frontend at /calendar/*"
```

---

### Task 14: Cutover — retire the old standalone system

**Files:**
- Delete: `Tentative AOP Forecaster/sync/calendar_library_sync.py`
- Delete: `Tentative AOP Forecaster/sync/store_calendar_cluster_sync.py`
- Modify: `Tentative AOP Forecaster/db/seed.py` (remove the 2 retired sources from `sync.sources`, if registered there — check first)

**Interfaces:**
- Consumes: `RS Planning Platform/backend/calendar_engine/migrate_from_json.py` (sub-project A, already built).
- Produces: the old Calendar Engine system (port 7822, the 2 sync jobs) fully retired.

- [ ] **Step 1: Final data catch-up**

```bash
cd "RS Planning Platform/backend"
python calendar_engine/migrate_from_json.py
```
Expected: re-runs cleanly, catches any edits made through the old `:7822` UI since sub-project A's original migration. Verify via psql that row counts look sane (matching whatever the last manual check showed, adjusted for any real edits made in the interim).

- [ ] **Step 2: Confirm the new frontend reflects the freshly-migrated data**

Reload `/calendar/*` in the browser, spot-check a few screens (calendar library list, store-cluster map count) against the values just confirmed via psql in Step 1.

- [ ] **Step 3: Stop the old standalone server**

```bash
# find and stop whatever process is running Calendar Engine/local_server.py on port 7822
```
Confirm it's down: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:7822/api/changelog` should fail to connect (not just 4xx/5xx — connection refused).

- [ ] **Step 4: Check whether the 2 legacy sync jobs are registered in `sync.sources`**

```bash
export PGPASSWORD='RsPlanning_2026Local'
"/c/Program Files/PostgreSQL/18/bin/psql.exe" -U rs_planning_app -h 127.0.0.1 -p 5432 -d rs_planning -c "SELECT source_key FROM sync.sources WHERE source_key IN ('calendar_library', 'store_calendar_cluster_map');"
```
If rows exist, delete them (`DELETE FROM sync.sources WHERE source_key IN (...)`) — they're config for jobs that no longer exist. If no rows, skip this step.

- [ ] **Step 5: Delete the 2 legacy sync job files**

```bash
cd "Tentative AOP Forecaster"
git rm sync/calendar_library_sync.py sync/store_calendar_cluster_sync.py
```
If `db/seed.py` or any other file imports/references these two modules by name, remove those references too (grep first: `grep -rn "calendar_library_sync\|store_calendar_cluster_sync" .` excluding the files just deleted).

- [ ] **Step 6: Verify nothing else breaks**

```bash
cd "RS Planning Platform/backend"
python -m pytest tests/ -v
```
Expected: same pass/fail pattern as before this task (the 1 known pre-existing unrelated failure, everything else green) — this task removes dead code paths, it shouldn't change any test's outcome.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Cutover: retire local_server.py, port 7822, and the 2 legacy sync jobs"
```

At this point, `Calendar Engine/calendar_engine.html`, `Calendar Engine/local_server.py`, and `Calendar Engine/Local DB/*.json` are no longer referenced by anything live — per the spec's Cutover Path, archiving or deleting them is a separate, later cleanup pass done with fresh eyes once the new frontend has been live for a while, not part of this task.

---

### Task 15: Repoint the landing page at the unified platform

**Added mid-execution** (not in the original spec) — the landing page at `Landing/index.html` (served standalone on port 7800) still has its 3 module cards pointing at the old standalone ports (`:7822`, `:8000`, `:8002`), never updated when AOP Forecaster and SalesPlan were unified onto `:8010` in an earlier piece of work this session. Once Task 14 retires port 7822, the landing page's Calendar card would point at a dead port. This task fixes that and, in the same pass, points the other two cards at the unified platform too — matching the platform's own "one consistent product" goal, not just patching the one card that would otherwise break.

**Files:**
- Modify: `Landing/index.html`

**Interfaces:**
- Consumes: nothing from earlier tasks directly — this is a static HTML file with no build step, pure client-side `fetch`.

- [ ] **Step 1: Repoint the 3 primary cards to `:8010`**

Replace the Calendar, AOP Forecaster, and Planning Engine cards' `href` and `data-check` attributes. All three now point at the unified platform's own paths, and all three use `:8010/docs` as a uniform, unauthenticated health-check target — the module-specific status endpoints the old checks used (`/api/config/summary`, `/api/store-master`, etc.) are now mounted behind `require_login` on `:8010`, so checking them directly would misreport "offline" for an anonymous visitor even when the server is healthy. `:8010/docs` (FastAPI's own auto-generated docs page) is always reachable without auth and exists on every FastAPI app in this platform, making it a safe, consistent choice for all three:

```html
<a class="card" href="http://localhost:8010/calendar/" target="_blank" data-check="http://localhost:8010/docs">
  <div class="card-icon">📅</div>
  <h2>Calendar</h2>
  <p class="desc">Calendarisation Suite — builds the locked, festival-aligned day-shift calendar per cluster, used to reindex last year's sales onto this year's dates.</p>
  <div class="meta">
    <span class="port">localhost:8010/calendar</span>
    <span class="status"><span class="dot"></span><span class="status-label checking">checking…</span></span>
  </div>
</a>

<a class="card" href="http://localhost:8010/aop/" target="_blank" data-check="http://localhost:8010/docs">
  <div class="card-icon">📊</div>
  <h2>AOP Forecaster</h2>
  <p class="desc">Annual Operating Plan forecaster — planning inputs (Store Master, Growth %, NSO openings) and the store×division×month forecast engine.</p>
  <div class="meta">
    <span class="port">localhost:8010/aop</span>
    <span class="status"><span class="dot"></span><span class="status-label checking">checking…</span></span>
  </div>
</a>

<a class="card" href="http://localhost:8010/planning/" target="_blank" data-check="http://localhost:8010/docs">
  <div class="card-icon">🧮</div>
  <h2>Planning Engine</h2>
  <p class="desc">Sales Plan — Division/Department plans, MRP reapportionment, PW-W &amp; SOR deviation, and display-type planning engines.</p>
  <div class="meta">
    <span class="port">localhost:8010/planning</span>
    <span class="status"><span class="dot"></span><span class="status-label checking">checking…</span></span>
  </div>
</a>
```

Note each card's `data-check` is now identical (`:8010/docs`) — this is intentional, not a copy-paste mistake to "fix." The existing status-check `<script>` block (bottom of the file, the `document.querySelectorAll('.card').forEach(...)` loop) needs no changes; it already reads `data-check` generically per card.

Since `:8010`'s routes require a login session, clicking a card takes the visitor to the app's React (or existing) frontend, which itself redirects to `/login` if the visitor isn't authenticated yet — this already works correctly (Task 2's `fetchJson` 401-redirect, and the equivalent behavior already live for AOP/SalesPlan's own frontends) and needs no special handling here.

- [ ] **Step 2: Leave the "Data Sync & Flow" card's data-fetching unchanged**

Do NOT repoint the `fetch('http://localhost:8000/api/config/db-sync/status', ...)` or `fetch('http://localhost:8002/api/department-plan/aop-forecaster-status', ...)` calls in the `<script>` block to their `:8010` equivalents. Those two specific endpoints are mounted behind `require_login` on `:8010` (`/api/aop/api/config/db-sync/status`, `/api/planning/department-plan/aop-forecaster-status`) — an anonymous landing-page visitor's fetch to either would get a 401 with no `runs`/`synced` field, and the existing `.then()` handlers would silently render "No syncs run yet" / "Not synced yet" instead of the real data, which is worse than confusing — it's actively misleading. The standalone AOP Forecaster (`:8000`) and SalesPlan (`:8002`) servers are not being retired by this or any other current plan (only Calendar Engine's `:7822` dies, in Task 14) — their `/api/config/db-sync/status` and `/api/department-plan/aop-forecaster-status` endpoints stay open, unauthenticated, and correctly populated regardless of this task, so leaving these two fetches as-is is the correct choice, not an oversight. Add a one-line code comment above this section explaining why, so a future reader doesn't "fix" the asymmetry into a regression:

```javascript
// NOTE: these two fetches intentionally stay pointed at the standalone
// AOP Forecaster (:8000) and SalesPlan (:8002) ports, not :8010 — the
// equivalent routes on :8010 require a login session, and an anonymous
// landing-page visitor's fetch would silently get empty/misleading data
// instead of a clear error. :8000/:8002 stay running unauthenticated
// specifically for this kind of public status check.
```

- [ ] **Step 3: Update the footer copy**

The current footer says "A grey dot means a module's server isn't running yet — start it with its own `start.bat` / `start_backend.bat`, then reload this page." — accurate for 3 independently-started standalone servers, no longer accurate once the 3 main cards point at one shared `:8010` process. Replace with:

```html
<footer>
  Calendar, AOP Forecaster, and Planning Engine now run from one unified server
  on <code>localhost:8010</code> — start it once and all three come up together.
  A grey dot means that server isn't running yet.
</footer>
```

- [ ] **Step 4: Verify in the browser**

Start the unified app on `:8010` (with this plan's Tasks 1-14 already applied, so `/calendar/*` is live) and the standalone AOP Forecaster (`:8000`) and SalesPlan (`:8002`) servers (for the Data Sync card). Serve `Landing/index.html` (`python landing_server.py` from `Landing/`, port 7800) and open it in a browser. Confirm: all 3 primary cards show a green "online" dot, clicking each opens the correct `:8010` path in a new tab (prompting login if not already authenticated), and the "Data Sync & Flow" card still shows real data pulled from `:8000`/`:8002`.

- [ ] **Step 5: Commit**

```bash
cd Landing
git add index.html
git commit -m "Repoint landing page at the unified platform (:8010), keep Data Sync card on standalone ports"
```

---

### Task 16: Fix cluster-profile ordering not persisting across reload

**Added mid-execution** — Task 6's implementer found, during live verification, that dragging cluster tabs to reorder them works correctly in the UI and sends the right payload, but the new order doesn't survive a page reload: `GET /cluster-profiles` always returns profiles sorted alphabetically by name, discarding whatever order was submitted via `PUT /cluster-profiles`. Root cause: `calendar.cluster_profiles` has no column recording sort order, so `get_cluster_profiles`'s `order_by(ClusterProfile.name)` is the only ordering available. This is a real bug in already-merged code from sub-project A (`RS Planning Platform/backend/calendar_engine/router.py`, `Tentative AOP Forecaster/db/models/calendar.py`) — outside Task 6's own frontend-only file list, but it breaks functionality this same plan is shipping, so it's fixed here rather than left as unaddressed debt.

**Files:**
- Modify: `Tentative AOP Forecaster/db/models/calendar.py` (add a `seq` column to `ClusterProfile`)
- Create: a new Alembic migration (autogenerated)
- Modify: `RS Planning Platform/backend/calendar_engine/router.py` (`get_cluster_profiles`, `put_cluster_profiles`)

**Interfaces:**
- Consumes: nothing from earlier tasks in this plan.
- Produces: `GET /api/calendar/cluster-profiles` now returns profiles in the order they were last submitted via `PUT`, not alphabetically.

- [ ] **Step 1: Add the `seq` column to `ClusterProfile`**

In `Tentative AOP Forecaster/db/models/calendar.py`, add a `seq` field to the existing `ClusterProfile` class (after `region`):

```python
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 2: Generate and apply the migration**

```bash
cd "Tentative AOP Forecaster"
python -m alembic revision --autogenerate -m "add seq column to cluster_profiles"
```
Read the generated migration file before applying — confirm it only adds the one `seq` column (as `NOT NULL` with a server-side default of `0`, since existing rows need a value) and touches nothing else.

```bash
python -m alembic upgrade head
python -m alembic check
```
Expected: upgrades cleanly, no drift.

- [ ] **Step 3: Backfill existing rows with their current (alphabetical) order as a starting `seq`**

The migration gives every existing row `seq=0` (same value, so they'd still sort arbitrarily among themselves until the next `PUT` explicitly sets real values). Assign them a stable starting order matching what's already live, so nothing visibly changes until the user next reorders something:

```bash
export PGPASSWORD='RsPlanning_2026Local'
"/c/Program Files/PostgreSQL/18/bin/psql.exe" -U rs_planning_app -h 127.0.0.1 -p 5432 -d rs_planning -c "
WITH ordered AS (SELECT id, row_number() OVER (ORDER BY name) - 1 AS rn FROM calendar.cluster_profiles)
UPDATE calendar.cluster_profiles SET seq = ordered.rn FROM ordered WHERE calendar.cluster_profiles.id = ordered.id;
"
```

- [ ] **Step 4: Update `get_cluster_profiles` and `put_cluster_profiles`**

In `RS Planning Platform/backend/calendar_engine/router.py`, change the read to order by `seq` instead of `name`:

```python
profiles = session.execute(select(ClusterProfile).order_by(ClusterProfile.seq)).scalars().all()
```

And change the write to stamp each profile's position in the submitted array as its `seq`:

```python
for i, profile in enumerate(body.get("profiles", [])):
    p = ClusterProfile(name=profile["name"], region=profile.get("region"), next_id=profile["nextId"], seq=i)
    session.add(p)
    session.flush()
    for fest in profile.get("festivals", []):
        session.add(ClusterProfileFestival(
            cluster_profile_id=p.id, source_festival_id=fest["id"], name=fest["name"],
            ref_date=datetime.date.fromisoformat(fest["refDate"]), fut_date=datetime.date.fromisoformat(fest["futDate"]),
            pre=fest["pre"], core=fest["core"], post=fest["post"],
        ))
```
(The `for profile in body.get("profiles", [])` line becomes `for i, profile in enumerate(...)` — everything else in the loop body is unchanged.)

- [ ] **Step 5: Verify live**

Restart the unified backend (`:8010`). Using the browser (already logged in as `planner1` from earlier tasks' verification, or log in fresh): go to Calendarisation, drag-reorder the cluster tabs, reload the page, confirm the new order persisted. Independently confirm via psql:
```bash
"/c/Program Files/PostgreSQL/18/bin/psql.exe" -U rs_planning_app -h 127.0.0.1 -p 5432 -d rs_planning -c "SELECT name, seq FROM calendar.cluster_profiles ORDER BY seq;"
```

- [ ] **Step 6: Commit**

```bash
git add "Tentative AOP Forecaster/db/models/calendar.py" "Tentative AOP Forecaster/alembic/versions/" "RS Planning Platform/backend/calendar_engine/router.py"
git commit -m "Fix cluster-profile ordering not persisting across reload (add seq column)"
```
