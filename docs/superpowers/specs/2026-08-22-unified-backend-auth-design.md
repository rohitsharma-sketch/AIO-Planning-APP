# Unified Backend + Auth + Approval Workflow — Design Spec

**Date:** 2026-08-22
**Status:** Draft, pending user review
**Phase:** 1 of 3 (backend + auth + approval workflow + audit trail). Frontend
unification and the Calendar Engine rewrite are separate, later specs — not
designed here.

## Context

Three independent applications currently run as separate processes:

| App | Port | Stack | Notes |
|---|---|---|---|
| Calendar Engine | 7822 | Vanilla HTML/JS + Python `http.server` | No build step, no FastAPI. Out of scope for Phase 1. |
| AOP Forecaster | 8000 | FastAPI + React (Vite) | Routes bound directly to `app = FastAPI()` via `@app.get/@app.post`. Postgres-backed (`rs_planning` DB). |
| SalesPlan | 8002 | FastAPI + React (Vite) | 11 engines, **already** structured as `APIRouter()` per engine, mounted via `app.include_router(...)` in `main.py`. File/Excel-backed, no Postgres today. |

They are stitched together today via HTTP calls (AOP Forecaster's
`/api/config/division-aop-summary` → SalesPlan's `/api/department-plan/sync-from-aop-forecaster`)
and a shared `rs_planning` Postgres instance that only AOP Forecaster currently
reads/writes.

**Goal of this phase:** one FastAPI process, one port, real login with four
named roles, and a real approval chain — a forecast run isn't just "computed,"
it's drafted, reviewed, and signed off before it's allowed to feed SalesPlan —
with a full audit trail of both the approval decisions and the underlying
number changes. AOP Forecaster's and SalesPlan's existing routers mount under
this one process; Calendar Engine and a unified frontend are explicitly out
of scope. Each app's internal engine logic (SalesPlan's file-based state,
AOP's Postgres-backed engine) is untouched.

**Non-goals (explicitly deferred):**
- Rewriting Calendar Engine into the FastAPI/React stack (Phase 3).
- Merging the three frontends into one React app (Phase 2) — the workflow and
  auth UI in this phase is minimal/functional (plain forms), not a polished
  experience; that comes with Phase 2's unified frontend.
- Migrating SalesPlan's 12 engines off file/Excel storage onto Postgres (a
  separate decision, not implied by this merge).
- Gating *edits* to Planning Inputs to only happen during a role's assigned
  workflow turn (see "Deliberately not doing" below) — the workflow governs
  when a *run* can be approved, not when Planner/Buyer are allowed to touch
  numbers.

## Architecture

New top-level project: `CLAUDE Projects/RS Planning Platform/backend/`
(sibling to the existing `Tentative AOP Forecaster` and `SalesPlan` folders,
which stay in place — their code is *imported*, not moved, in this phase).

```
RS Planning Platform/
  backend/
    app.py                  # the ONE FastAPI() instance, port 8010
    auth/
      models.py             # SQLAlchemy models: auth.users
      security.py           # password hashing (passlib/bcrypt), session cookie signing
      routes.py             # /api/auth/login, /logout, /me, /api/auth/admin/users
      deps.py               # require_login(), require_role(*roles), require_admin()
    workflow/
      models.py             # workflow.plan_cycles, workflow.plan_cycle_transitions
      routes.py             # /api/aop/plan-cycles/* (see below)
      service.py            # state machine: submit/approve/reject transitions
    audit/
      models.py             # audit.data_changes
      routes.py             # /api/audit/* (read-only log viewer)
      log.py                 # log_change(...) helper, called from db/editor.py
    requirements.txt        # union of AOP Forecaster's + SalesPlan's + passlib
  (no frontend/ yet — Phase 2)
```

`app.py` imports AOP Forecaster's and SalesPlan's existing route modules by
adding both folders to `sys.path` (they stay where they are; nothing moves).
This keeps the diff on each existing app small and reversible — if Phase 1
needs to be rolled back, both apps still run standalone exactly as they do
today, unchanged in their own folders.

### Route mounting

| Prefix | Source | Work required |
|---|---|---|
| `/api/auth/*` | New | Login/logout/me + admin user management |
| `/api/aop/plan-cycles/*` | New | The workflow state machine (create, submit, approve, reject, list, get) |
| `/api/audit/*` | New | Read-only audit log viewer (admin + approver, see below) |
| `/api/planning/*` | SalesPlan's 11 existing `APIRouter()` objects | **Re-import only** — `from engines.division_plan import router as division_plan_router` (with SalesPlan's `backend/` on `sys.path`), then `app.include_router(division_plan_router, prefix="/api/planning/division-plan", dependencies=[Depends(require_login)])`. Repeat per engine. Zero changes to SalesPlan's own files. |
| `/api/aop/*` | AOP Forecaster's `app.py` routes | **Refactor required**: extract every `@app.get/@app.post/@app.put/@app.delete` in `app.py` into a new `router = APIRouter()`, decorate with `@router.*` instead of `@app.*`, then `app.include_router(router, prefix="/api/aop", dependencies=[Depends(require_login)])` in the unified app. AOP Forecaster's own `app.py` keeps working standalone (the refactor is additive — `app.py` still creates its own `FastAPI()` and includes the same router directly, unprotected, for standalone use during the transition). |

Both existing frontends currently call bare `/api/...` paths. Each frontend's
API base path needs a one-line change (a `const API_BASE = '/api/aop'` /
`'/api/planning'` prepended to fetch calls, or a Vite dev-server proxy
rewrite) — unavoidable minimal frontend touch even though frontend
*unification* is Phase 2. The unified app serves each frontend's existing
`dist/` build as static files under `/aop/*` and `/planning/*` respectively
(still two separate bundles — just both served from one process/port).

## Auth design

**New Postgres schema `auth`** in the existing `rs_planning` database (same
instance, no new DB — consistent with keeping everything centralized there):

```sql
CREATE TABLE auth.users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username      text UNIQUE NOT NULL,
  password_hash text NOT NULL,          -- bcrypt via passlib
  role          text NOT NULL,          -- 'planner' | 'buyer' | 'reviewer' | 'approver'
  is_admin      boolean NOT NULL DEFAULT false,  -- orthogonal to role; user management access
  created_at    timestamptz NOT NULL DEFAULT now(),
  is_active     boolean NOT NULL DEFAULT true
);
```

`is_admin` is deliberately separate from `role` — "who can manage user
accounts" isn't a fifth point in the approval chain, and tying it to one
specific workflow role (e.g. only Approvers can be admins) would be an
arbitrary constraint with no stated reason. Any user can be `is_admin` in
addition to whichever of the four roles they hold.

**The four roles govern two things**: which module routes a user can hit at
all (all four roles get `/api/aop/*` and `/api/planning/*` — there's no
stated need to wall those off from each other), and which workflow
transitions they're allowed to perform (see Workflow below). `is_admin`
additionally unlocks `/api/auth/admin/*` (create/deactivate users) and
`/api/audit/*` (see Audit trail below).

**Session mechanism:** signed cookie session via Starlette's built-in
`SessionMiddleware` (itsdangerous — already a FastAPI/Starlette dependency,
no new package beyond `passlib[bcrypt]` for password hashing). No server-side
session table; the cookie carries `{user_id, role, is_admin}` signed with a
secret key (env var). Simple, stateless, adequate for an internal tool with
no compliance requirement driving anything heavier.

**Login flow:** `POST /api/auth/login {username, password}` → verifies
against `auth.users`, sets the session cookie, returns `{username, role,
is_admin}`. `GET /api/auth/me` returns the current session or 401.
`POST /api/auth/logout` clears the cookie. A minimal login page (plain HTML,
no framework — Phase 2's unified frontend replaces it) is served at `/login`
by the unified app; unauthenticated requests to any static frontend route
redirect there, unauthenticated API requests get a plain 401 JSON body.

**Seeding the first admin:** a one-time `backend/seed_admin.py` script
(prompts for username/password, hashes, inserts with `is_admin=true`) —
there's no bootstrap UI in Phase 1, matching the "no frontend unification
yet" scope.

## Workflow: Planner → Buyer → Reviewer → Approver

A **plan cycle** is the unit that moves through the chain — distinct from a
single `engine.forecast_runs` row, because Buyer can edit inputs and re-run
mid-review without starting over.

```sql
CREATE TABLE workflow.plan_cycles (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  status         text NOT NULL DEFAULT 'draft',
  -- 'draft' | 'pending_buyer' | 'pending_review' | 'pending_approval' | 'approved'
  current_run_id uuid REFERENCES engine.forecast_runs(run_id),
  created_by     uuid NOT NULL REFERENCES auth.users(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE workflow.plan_cycle_transitions (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  plan_cycle_id  uuid NOT NULL REFERENCES workflow.plan_cycles(id),
  from_status    text NOT NULL,
  to_status      text NOT NULL,
  actor_id       uuid NOT NULL REFERENCES auth.users(id),
  actor_role     text NOT NULL,       -- role held at the time of the action
  comment        text,
  run_id         uuid REFERENCES engine.forecast_runs(run_id),  -- run this transition applied to
  created_at     timestamptz NOT NULL DEFAULT now()
);
```

**State machine** (there is no `rejected` status — a rejection resets the
cycle to `draft`, per your call; the rejection itself, who did it, and why,
lives in `plan_cycle_transitions`, not in the cycle's current status):

```
                 submit (Planner)         submit (Buyer)        approve (Reviewer)      approve (Approver)
     draft ─────────────────────► pending_buyer ─────────► pending_review ─────────► pending_approval ─────────► approved
       ▲                                  │                        │                         │
       │                                  │   reject (Reviewer)    │    reject (Approver)     │
       └──────────────────────────────────┴────────────────────────┴─────────────────────────┘
                                              (always back to draft)
```

| Transition | Allowed role | Effect |
|---|---|---|
| Create cycle | Planner | New `plan_cycles` row, `status='draft'`, `current_run_id` = whatever run Planner just built via `session-from-db` + `run`. Planner can re-run freely while `draft` (each re-run just updates `current_run_id` — no transition logged for this, it's normal iteration, not a workflow event). |
| Submit to Buyer | Planner | `draft → pending_buyer` |
| Edit + re-run | Buyer | Buyer can edit AOP overrides (`PUT /api/aop/config/aop-overrides`, already built) and trigger a new run while `status='pending_buyer'`; `current_run_id` updates. Every edit is captured by the *data-change* audit log (see below), not a workflow transition. |
| Submit to Reviewer | Buyer | `pending_buyer → pending_review` |
| Approve (advance) | Reviewer | `pending_review → pending_approval` |
| Reject | Reviewer | `pending_review → draft` |
| Approve (final) | Approver | `pending_approval → approved`. Once approved, `current_run_id` becomes eligible for SalesPlan's sync (see below). An approved cycle is **not** further editable — Planner starting new work creates a **new** `plan_cycle`, it doesn't reopen an approved one. |
| Reject | Approver | `pending_approval → draft` |

Every transition (including rejections) writes one `plan_cycle_transitions`
row. `GET /api/aop/plan-cycles/{id}` returns the cycle plus its full
transition history — that *is* the workflow audit trail, no separate log
needed for this part.

**Consuming this from SalesPlan**: `division-aop-summary` currently reads
"the latest `engine.forecast_runs` row, period." It changes to: the
`current_run_id` of the most recently `approved` `plan_cycles` row. If none
exists yet, it 404s with a message saying so (same shape as today's "no run
persisted yet" 404, just a different condition). This is the actual point of
building the workflow — SalesPlan should never build a department plan off
an unapproved or since-rejected forecast.

**Deliberately not doing**: gating *edits* to Growth %/NSO/AOP overrides to
only happen while a cycle is at the editing role's stage. Planner and Buyer
can use the Planning Inputs editor built last turn at any time, regardless of
any cycle's status — the workflow controls when a *run* can become
`approved`, not when the underlying numbers can be touched. Adding turn-level
edit locks is real additional complexity (what happens to an edit made while
no cycle is active? do multiple concurrent cycles need to be preventable?)
with no stated need yet — flagged here so it's a conscious choice, not a gap
nobody noticed.

## Audit trail

Two logs, covering two different things:

1. **Workflow transitions** — `workflow.plan_cycle_transitions` (above);
   who submitted/approved/rejected each cycle, when, with what comment.
2. **Data changes** — every write to Growth %/NSO/AOP overrides, wherever it
   comes from (Planner or Buyer, in or out of an active workflow):

```sql
CREATE TABLE audit.data_changes (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  table_name    text NOT NULL,     -- e.g. 'planning_inputs.input_values', 'masterdata.nso_openings'
  record_key    jsonb NOT NULL,    -- e.g. {"lever_key":"aop_optional","store_id":"AAC","division_code":"GM","period_id":202704}
  old_value     text,
  new_value     text,
  actor_id      uuid NOT NULL REFERENCES auth.users(id),
  actor_role    text NOT NULL,
  plan_cycle_id uuid REFERENCES workflow.plan_cycles(id),  -- null if edited outside any active cycle
  changed_at    timestamptz NOT NULL DEFAULT now()
);
```

`db/editor.py`'s `put_growth`/`put_nso`/`put_aop_overrides` (built last turn)
need one change each: before upserting, read the current value, and if it
differs (or is new/deleted), insert a `data_changes` row. This requires actor
identity to reach `db/editor.py`, which it doesn't have today — the app.py
endpoints wrapping these functions need to pass the logged-in user (from the
new auth dependency) down into the editor calls.

**Viewing the audit trail**: `GET /api/audit/data-changes` and
`GET /api/audit/plan-cycles/{id}` — read-only, filterable by table/date/actor,
restricted to `is_admin` and `approver` role (an Approver signing off on a
plan is a reasonable reason to see what changed underneath it; Planner/Buyer/
Reviewer don't get a stated need for the full log beyond their own cycle's
transition history, which `GET /api/aop/plan-cycles/{id}` already exposes to
everyone with access to that cycle).

## Error handling

- Protected route, no/invalid session → `401 {"detail": "Not authenticated"}`.
- Protected route, valid session but wrong role (e.g. Buyer trying to
  Approve, or a non-admin hitting `/api/auth/admin/*`) → `403 {"detail": "Forbidden"}`.
- Workflow transition attempted from the wrong status (e.g. approving a
  cycle that's still `draft`) → `409 {"detail": "Cycle is in 'draft', expected 'pending_approval'"}`.
- Login with wrong username/password → `401 {"detail": "Invalid credentials"}`
  (deliberately not distinguishing "no such user" from "wrong password").
- `division-aop-summary` with no approved cycle → `404 {"detail": "No approved plan cycle yet"}`.
- Everything *inside* a mounted router (AOP's or SalesPlan's own error
  handling) is unchanged — this phase only adds an auth/workflow gate in
  front, it doesn't touch what happens once a request is authenticated and
  reaches the existing code.

## Testing

1. **Router-mount smoke test** — for every prefix, confirm the exact same
   request that works against the standalone app today (e.g.
   `POST /api/config/session-from-db` on :8000) still works at its new
   mounted path (`POST /api/aop/config/session-from-db` on :8010) with a
   valid session cookie, and returns 401 without one.
2. **Full pipeline re-run through the new prefixes** — the same chain
   exercised repeatedly this session (session-from-db → run →
   division-aop-summary → SalesPlan sync-from-aop-forecaster → calculate),
   now through `/api/aop/*` and `/api/planning/*` on the unified app, **plus
   the new gate**: confirm `division-aop-summary` 404s until a cycle is
   actually `approved`, then succeeds. AOP Forecaster's own internal call to
   SalesPlan's endpoint (`AOP_FORECASTER_URL` env var pattern) needs its
   target URL updated to the new unified port/prefix too.
3. **Auth tests** — login success/failure, session persists across requests,
   logout invalidates it, admin-only route rejects a non-admin session,
   protected static frontend routes redirect to `/login` when logged out.
4. **Workflow tests** — full happy path (Planner creates → submits → Buyer
   edits, re-runs, submits → Reviewer approves → Approver approves →
   `division-aop-summary` now serves this run); both rejection points (from
   Reviewer and from Approver) correctly reset to `draft` and log the
   transition; wrong-role transition attempts get 403; wrong-status
   transition attempts get 409.
5. **Audit tests** — editing Growth %/NSO/AOP overrides writes a
   `data_changes` row with correct old/new values and actor; a non-admin,
   non-approver hitting `/api/audit/*` gets 403.
6. **Standalone apps still work** — AOP Forecaster's `app.py` and SalesPlan's
   `main.py`, run standalone on their original ports, still function
   unchanged (proves the merge was additive, not destructive — matters for
   safe rollback during the transition).

## Rollout

Both existing standalone servers (`:8000`, `:8002`) keep running unchanged
during this phase — the unified app is additive, validated in parallel, not
a risky cutover. Once the unified app (`:8010`) is confirmed equivalent
(same tests, same results, for real usage, over some period the user
chooses), retiring the two standalone entrypoints is a separate, later
decision — not automatic, not part of this phase. Calendar Engine (`:7822`)
and the standalone Landing page (`:7800`) are untouched by this phase
entirely.

## Open risks / things to watch

- **Path collisions**: AOP Forecaster and SalesPlan don't currently share
  any route names, but both were built independently — worth a final grep
  for accidental overlaps before mounting (e.g. both could plausibly have
  had a generic `/api/upload`; AOP does, SalesPlan doesn't appear to — needs
  re-confirming when this is actually built, not assumed from memory here).
- **`sys.path` manipulation to import from sibling folders** is a bit
  fragile (relies on folder layout, not proper Python packaging). Acceptable
  for Phase 1 given both source folders aren't proper installable packages
  today either; worth revisiting if Phase 2/3 make the codebase feel messy.
- **AOP Forecaster's own `AOP_FORECASTER_URL`-based call to SalesPlan** is a
  loopback through HTTP even once both live in the same process — could
  become an in-process function call post-merge, but that's an optimization,
  not required for Phase 1 to work correctly.
- **Multiple concurrent `plan_cycles`**: nothing in this design stops two
  Planners from having two `draft` cycles open at once. Not prevented,
  because no stated need to prevent it yet — but worth knowing it's possible,
  since "which one is *the* current plan" isn't a question this design
  answers beyond "whichever was most recently approved."
- **Old `run_id`s orphaned by Buyer's re-runs** stay in `engine.forecast_runs`
  and `engine.forecast_results` forever (by design — runs are immutable/
  append-only) but only the cycle's final `current_run_id` is reachable from
  the workflow UI. That's intentional (full history preserved, nothing
  deleted) but means `engine.forecast_runs` will accumulate rows from
  abandoned mid-review edits, not just "real" plans — fine for Phase 1, worth
  a retention/archival thought later if the table grows large.
