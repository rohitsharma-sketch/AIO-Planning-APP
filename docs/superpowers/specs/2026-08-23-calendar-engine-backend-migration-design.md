# Calendar Engine Backend Migration — Design Spec

**Sub-project A of 2**: migrate Calendar Engine's backend (data + API) from a
standalone Python `http.server` on port 7822, backed by local JSON files, to
a Postgres-backed FastAPI router mounted into the unified RS Planning
Platform (`:8010`). Sub-project B (a matching React frontend, restyled to
match the platform's existing look) is a separate, later spec — this
document does not cover it, beyond noting where sub-project A must leave
room for it.

## Context

Calendar Engine is the third of the three original planning modules (the
other two — AOP Forecaster and SalesPlan — were already merged into RS
Planning Platform earlier this session; see
`docs/superpowers/specs/2026-08-22-unified-backend-auth-design.md` and its
implementation plan). It builds the locked, festival-aligned day-shift
calendar per cluster, used to reindex last year's sales onto this year's
dates, plus a store→cluster mapping editor and a sales-data-lake link/sync
step. Today it runs as its own process:

- `local_server.py` — a raw `http.server.ThreadingHTTPServer`, no
  framework, no auth, open on the local network.
- `calendar_engine.html` — a single 4,165-line vanilla-JS file (the whole
  UI: festival-mapping engine, cluster editor, day-table renderer,
  changelog UI, store/cluster import, sales-data link/reindex UI).
- State persisted as local JSON files under `Local DB/`.

Two of Calendar Engine's eight JSON state files already have a one-way sync
job (`Tentative AOP Forecaster/sync/calendar_library_sync.py` and
`store_calendar_cluster_sync.py`) scraping them into Postgres for AOP
Forecaster to read — but each sync job only captures a subset of its
source file's fields (see Data Model below). The other six state files
have no Postgres presence at all today.

## Goals

- Every piece of Calendar Engine's persisted state lives in Postgres, in
  the existing `calendar` schema, with no field silently dropped versus
  what the JSON files hold today (the two partial-extraction sync jobs get
  fixed as part of this, not just replicated).
- A FastAPI router, `calendar_engine/router.py`, exposes this data at
  `/api/calendar/*`, mounted into `RS Planning Platform/backend/app.py`
  behind the unified platform's existing auth.
- Only the `planner` role can write; every authenticated role can read.
- The three pure read-only data-lake scan endpoints (`salesdata/link`,
  `salesdata/link_daywise`, `salesdata/reindex`) port over with unchanged
  behavior — they were never file-backed, so there's no migration for them,
  just relocation.
- The old two sync jobs (`calendar_library_sync.py`,
  `store_calendar_cluster_sync.py`) and `local_server.py`/port 7822 retire
  once the new backend is live, tested, and the frontend (sub-project B)
  has cut over — not before, since the old vanilla-JS frontend is the only
  thing keeping Calendar Engine's data current until then (see Migration
  Path).

## Non-goals

- No frontend work. The old `calendar_engine.html` keeps running against
  the old backend until sub-project B replaces it. This spec only builds
  the new backend; nothing points at it yet.
- No change to the three read-only data-lake scan endpoints' actual logic
  (parquet scanning, predicate pushdown, the frozen-cache-per-sync
  behavior) — they port with the same behavior, just as FastAPI routes
  instead of raw `http.server` handlers.
- No redesign of the calendar/reindex domain logic itself (festival
  pre/core/post day math, cluster resolution, etc.) — that logic lives in
  the frontend today and stays there until sub-project B; this spec is
  purely about where state is persisted and how it's read/written over
  HTTP.
- `period_log.json` is not migrated — confirmed dead on both the frontend
  (no `fetch` call anywhere references it) and functionally on the backend
  (whitelisted in `STATE_KEYS` but the file itself is `{}` and nothing
  writes to it). The new router simply doesn't expose an equivalent route.

## Architecture

```
RS Planning Platform/backend/
  calendar_engine/
    __init__.py
    router.py          # /api/calendar/* — all endpoints below
    scans.py            # ported salesdata/link, link_daywise, reindex logic
    migrate_from_json.py  # one-time+re-runnable import script (see Migration Path)
  app.py                 # adds: from calendar_engine.router import router as calendar_router
                          #       app.include_router(calendar_router, prefix="/api/calendar",
                          #                           dependencies=[Depends(require_login)])
```

This mirrors exactly how AOP Forecaster's and SalesPlan's routers are
mounted today — no new mounting pattern, no new auth mechanism. Read
endpoints use `require_login` (any of the 4 roles); write endpoints
additionally depend on `require_role("planner")`, the same factory already
used elsewhere in `auth/deps.py`.

## Data Model (schema `calendar`)

Eight JSON state keys map to Postgres as follows. Two tables already exist
(shown with their real current DDL, confirmed via `\d+` against the live
database) and get **extended**, not replaced, to stop dropping fields; six
are brand-new.

### Extended: `calendar.calendars` + `calendar.calendar_day_pairs`

Current schema (unchanged):
```
calendar.calendars(calendar_id bigint PK, name varchar not null,
                    ref_year int not null, fut_year int not null,
                    saved_at timestamptz not null, engine varchar)
calendar.calendar_day_pairs(id serial PK, calendar_id bigint FK,
                             cluster_name varchar not null, seq int not null,
                             ref_date date not null, fut_date date not null,
                             UNIQUE(calendar_id, cluster_name, seq))
```
These already capture `calendar_library.json`'s `id/name/refYear/futYear/
savedAt/engine` and `dayMap`. What's missing is the `clusters` array (the
per-calendar festival config actually used to compute `dayMap`) and
`mappingSummary`.

**New**: `calendar.calendar_clusters(id serial PK, calendar_id bigint FK
REFERENCES calendars, cluster_name varchar not null, region varchar,
UNIQUE(calendar_id, cluster_name))` and
`calendar.calendar_cluster_festivals(id serial PK, calendar_cluster_id int
FK REFERENCES calendar_clusters, source_festival_id int not null,
name varchar not null, ref_date date not null, fut_date date not null,
pre int not null, core int not null, post int not null)` —
`source_festival_id` preserves the JSON's own per-cluster `id`/`nextId`
sequencing so round-tripping doesn't renumber festivals the UI already
references.

`mappingSummary` (`{cluster, totalDays}`) is **not stored** — it's
`COUNT(*) GROUP BY cluster_name FROM calendar_day_pairs WHERE calendar_id =
:id`, computed on read. Storing it would be a derived value duplicated
from the day-pairs table, the same class of redundancy the append-only
ledger principle already applied elsewhere in this platform.

### Extended: `calendar.store_calendar_clusters`

Current schema (unchanged):
```
calendar.store_calendar_clusters(store_id varchar PK, cluster_name varchar
                                  not null, locked_at timestamptz,
                                  synced_at timestamptz not null default now())
```
Already captures `store_cluster_map.json`'s `stores` array + `lockedAt`.
Missing: `locked` (bool — today inferred from whether `locked_at` is
non-null, which is actually sufficient; no new column needed), `source`
(the imported filename), `aliases` (currently always empty in real data,
but the JSON schema supports it), `editedAt`.

**New**: `calendar.store_cluster_map_meta(id smallint PK DEFAULT 1 CHECK
(id = 1), source varchar, aliases jsonb not null default '{}'::jsonb,
edited_at timestamptz)` — a singleton row (there is exactly one store↔
cluster mapping at a time; `locked_at` on the existing table already
serves as the "locked" signal, so this table doesn't duplicate it).

### New: `calendar.cluster_profiles` + `calendar.cluster_profile_festivals`

For `app_state.json`'s `clusterProfiles` — the live, editable festival
configuration the UI works against before it's saved as a named calendar
into `calendar_library`. This is the most actively-written piece of state
in the whole app and deserves the same normalized shape as
`calendar_clusters`/`calendar_cluster_festivals` above:
```
calendar.cluster_profiles(id serial PK, name varchar not null,
                           region varchar, next_id int not null,
                           UNIQUE(name))
calendar.cluster_profile_festivals(id serial PK, cluster_profile_id int FK,
                                    source_festival_id int not null,
                                    name varchar not null,
                                    ref_date date not null, fut_date date not null,
                                    pre int not null, core int not null, post int not null)
```
`next_id` is carried over verbatim from the JSON (`clusterProfiles[i].
nextId`) — it's the frontend's own auto-increment counter for new festival
rows within that cluster; preserving it avoids ID collisions across a
save/reload cycle.

### New: `calendar.app_state_meta`

For `app_state.json`'s scalar fields (everything except `clusterProfiles`,
which lives in the tables above):
```
calendar.app_state_meta(id smallint PK DEFAULT 1 CHECK (id = 1),
                         active_cluster_idx int not null default 0,
                         ref_year varchar, fut_year varchar,
                         max_shift varchar, mo_pri varchar,
                         theme_id varchar, saved_at timestamptz,
                         migrations jsonb not null default '[]'::jsonb)
```
Singleton row, same pattern as `store_cluster_map_meta`. `migrations` stays
a JSON array (it's an append-only list of migration-tag strings the
frontend uses to avoid re-running one-time data fixups — small, not
relational, fine as JSONB).

### New: `calendar.festival_changelog`

`festival_changelog.json`'s 3-level nested dict
(`range_key → cluster_name → festival_name → {refDate, futDate, savedAt}`)
normalizes to:
```
calendar.festival_changelog(id serial PK, range_key varchar not null,
                             cluster_name varchar not null,
                             festival_name varchar not null,
                             ref_date date not null, fut_date date not null,
                             saved_at timestamptz not null,
                             UNIQUE(range_key, cluster_name, festival_name))
```
The unique constraint matches the JSON's own nesting (one entry per
range+cluster+festival combination) — safe under the NULL-in-unique-
constraint bug class audited earlier this session, since all three key
columns are `not null`.

### New: `calendar.store_cluster_log`

Append-only audit trail, same shape as the JSON, same pattern as
`audit.data_changes`:
```
calendar.store_cluster_log(id serial PK, at timestamptz not null,
                            source varchar, summary varchar not null,
                            added int not null, removed int not null,
                            reassigned int not null,
                            details jsonb not null)
```

### New: `calendar.salesdata_link_selection`

Two rows total (`mw`/`dw`), tiny selection-state:
```
calendar.salesdata_link_selection(source_type varchar PK
                                   CHECK (source_type IN ('mw', 'dw')),
                                   months jsonb not null,
                                   path varchar not null,
                                   synced_at timestamptz not null)
```

## API Design

New, clean resource-shaped endpoints — not required to preserve the old
full-file-replace JSON blob shapes, since the old frontend never talks to
this new backend (it's retired wholesale in sub-project B's cutover, not
gradually migrated endpoint-by-endpoint). Every endpoint below sits under
`/api/calendar` once mounted:

| Method | Path | Auth | Behavior |
|---|---|---|---|
| GET | `/calendar-library` | login | List saved calendars (id, name, ref/fut year, saved_at, engine, mapping summary per cluster) |
| GET | `/calendar-library/{id}` | login | One saved calendar, full detail: clusters+festivals, day_map |
| POST | `/calendar-library` | planner | Save a new named calendar (clusters+festivals+day_map) |
| DELETE | `/calendar-library/{id}` | planner | Remove a saved calendar |
| GET | `/store-cluster-map` | login | Current store→cluster mapping + meta (source, aliases, locked_at, edited_at) |
| PUT | `/store-cluster-map` | planner | Replace the mapping (full set, same semantics as today's lock-and-replace) — writes a `store_cluster_log` row describing the diff (added/removed/reassigned), same fields the frontend already computes today |
| GET | `/store-cluster-log` | login | Audit trail, newest first |
| POST | `/import/store-cluster` | planner | Unchanged stateless `.xlsx`/`.csv` parser — returns `[{store, cluster}]` for the client to review before PUT-ing `/store-cluster-map` |
| GET | `/cluster-profiles` | login | Current working festival config (all clusters + festivals) |
| PUT | `/cluster-profiles` | planner | Replace the working config |
| GET | `/app-state` | login | Scalar UI settings (active cluster, theme, ref/fut year, etc.) |
| PUT | `/app-state` | planner | Update scalar UI settings |
| GET | `/festival-changelog` | login | Full changelog, optionally filtered by `?range_key=` |
| PUT | `/festival-changelog` | planner | Upsert entries for a given range_key+cluster+festival |
| GET | `/salesdata/link` | login | Unchanged — month-wise data-lake scan (ported from `scans.py`) |
| GET | `/salesdata/link-daywise` | login | Unchanged — day-wise data-lake scan |
| POST | `/salesdata/reindex` | login | Unchanged — the reindex computation |
| GET/PUT | `/salesdata-link-selection/{source_type}` | login / planner | Small selection-state table (months, path, synced_at) |

Read access uses `require_login`; every write route above additionally
depends on `require_role("planner")`.

## Migration Path

1. Write `calendar_engine/migrate_from_json.py` — reads the 7 live JSON
   files under `Calendar Engine/Local DB/` (all except `period_log.json`)
   and upserts them into the tables above. Idempotent and re-runnable (not
   a one-shot script) — it's designed to run twice: once now, to prove out
   the new backend against real data, and once immediately before the
   sub-project B frontend cutover, to re-capture anything edited through
   the old `:7822` frontend in between.
2. Because the *old* Calendar Engine frontend stays the live system people
   actually edit in until sub-project B ships, this backend's Postgres
   data will go stale the moment the import script finishes — that's
   expected and fine. The new backend is built, tested, and left idle
   (not linked to by anything) until sub-project B is ready to cut over.
   No dual-write bridge is being built for this interim window — deemed
   not worth the complexity for what should be a short gap between the two
   sub-projects.
3. `local_server.py` (port 7822) and the two old sync jobs
   (`calendar_library_sync.py`, `store_calendar_cluster_sync.py`) are
   **not** retired at the end of this sub-project — they retire at
   sub-project B's cutover, once the new frontend is live and the old one
   is decommissioned. This spec's Non-goals section already calls this
   out; repeated here because it affects when "done" actually means "safe
   to delete the old code."

## Testing

Same rhythm as the AOP+SalesPlan build: pytest against the new router
using a real Postgres connection and `TestClient`/`httpx`, covering:
- CRUD round-trip for every new/extended table, including the "no field
  silently dropped" claim above — i.e. a test that writes a
  `calendar_library` entry with a non-empty `clusters` array and confirms
  the read-back includes it (this specifically regression-tests the bug
  the old sync job had).
- Role enforcement: planner writes succeed; buyer/reviewer/approver writes
  return 403; all four roles can read; unauthenticated requests return
  401.
- The three data-lake scan endpoints return byte-identical output to
  today's `:7822` for the same query parameters, run against the same
  network parquet paths — same verification pattern used in Task 11's
  final audit for the AOP+SalesPlan merge (there, `division-aop-summary`
  was compared byte-for-byte between standalone and unified; same
  technique applies here).
- The migration script: run it against the real current JSON files, then
  assert row counts and a handful of spot-checked records match the
  source JSON exactly (e.g. all 223 stores in `store_cluster_map.json`
  land correctly, all 6 `festival_changelog` range keys are present).

## Error Handling

Following the existing platform's conventions (`auth/deps.py`,
`workflow/routes.py`): `HTTPException(401, ...)` for missing session,
`HTTPException(403, ...)` for wrong role, `HTTPException(404, ...)` for a
missing `calendar_library` id, `HTTPException(409, ...)` reserved for any
future concurrent-edit conflict (not needed for this sub-project — there's
no multi-step state machine here, unlike the workflow's plan-cycle
transitions).

## Open Risks

- **Interim staleness window** (see Migration Path #2): if sub-project B
  takes long enough that meaningful edits accumulate on the old system,
  the re-run-before-cutover import needs to be genuinely re-run, not
  forgotten. Worth a checklist item in sub-project B's own plan, not
  solved here.
- **`aliases` field**: currently always empty (`{}`) in real data across
  the whole `Local DB/` snapshot inspected this session. The
  `store_cluster_map_meta.aliases` column is being added on faith that the
  JSON schema's presence of the field means it's meant to be used
  eventually — if it turns out to be genuinely dead (like `period_log`
  was), it's cheap to drop later since it's just a JSONB column, not a
  whole table.
- **Network parquet paths** (`\\10.0.1.85\...`): the three data-lake scan
  endpoints depend on a UNC path being reachable from wherever the unified
  app runs. This was already true for the standalone Calendar Engine and
  is unchanged by this migration — noted here only because it's an
  existing operational dependency this sub-project doesn't remove.
