# Buyer Review Workflow — Wiring Buyer's Input Into the Plan-Cycle Engine — Design Spec

**Date:** 2026-08-24
**Status:** Draft, pending user review
**Depends on:** 2026-08-22 unified backend + auth + approval workflow (the
`Planner → Buyer → Reviewer → Approver` state machine this spec wires a UI
onto already exists and is unchanged by this work).

## Context

The unified platform (`RS Planning Platform`, port 8010) already has a
complete `PlanCycle` state machine — `draft → pending_buyer → pending_review →
pending_approval → approved` — governing which AOP Forecaster run is allowed
to feed Sales Plan. AOP Forecaster's `GET /api/config/division-aop-summary`
(the endpoint Sales Plan's Department Plan syncs from) already refuses to
return anything until a cycle reaches `approved`, and the only path to
`approved` passes through `pending_buyer`.

**The problem: this workflow has zero UI.** The four `/api/aop/plan-cycles/*`
routes exist and are exercised by tests, but nothing in any of the three
frontends ever calls `POST /plan-cycles`, edits a run while `pending_buyer`,
or approves/rejects a cycle. The pipeline is real but dark — no one can
actually drive an AOP run from "computed" to "approved" today.

Separately, the standalone **Buyer's Input Sheet** app (port 5050, Flask +
vanilla HTML/JS, no auth) already embodies the *idea* of a buyer adjusting an
AOP-seeded plan — but at a much finer department/attribute-section grain
(`DVDATA`) than AOP Forecaster actually produces (AOP Forecaster's
`ForecastResult` is `store × division × period`, with no department
dimension at all). Reconciling those two grains is out of scope for this
pass (see Non-goals).

**Goal of this spec:** make the existing plan-cycle workflow actually
operable, end to end, at the grain AOP Forecaster already produces —
division-level annual totals — with the buyer's adjustment step living inside
the existing Buyer's Input Sheet app, and the other three roles (planner
submits, reviewer/approver approve) sharing one small new page in the
platform. Once a cycle reaches `approved`, Sales Plan's existing sync button
needs zero code changes to start reflecting the buyer's numbers — the gate
already lives in `division-aop-summary`.

**Non-goals (explicitly deferred):**
- Department/attribute-level buyer editing (Buyer's Input Sheet's existing
  `DVDATA` screen). This spec only wires the 3 division-level annual totals
  through the workflow; the existing rich section-level screen is untouched
  and unrelated to this pipeline.
- Mounting Buyer's Input Sheet as a platform module (`/buyers-input` under
  port 8010, matching AOP/Planning/Calendar). It stays standalone on port
  5050; only its JS gains authenticated cross-origin calls to the platform.
- Any change to the `PlanCycle` transition table itself (`workflow/service.py`)
  — it's already correct and tested.
- Editing/rerunning the AOP Forecaster engine from the buyer step (no new
  `ForecastRun` is created when a buyer adjusts totals — see Data model).
- Notifications, deadlines, or reminders for pending steps.

## Architecture

No new services. Three existing pieces change, two small new UI surfaces are
added:

```
RS Planning Platform/backend/
  db/models/workflow.py          # + PlanCycle.buyer_adjusted_totals (JSON)
  alembic/versions/               # + migration for the new column
  workflow/routes.py              # + PUT /plan-cycles/{id}/buyer-totals
  workflow/service.py             # + set_buyer_totals(...)
  static/
    plan-cycles.html              # NEW — shared planner/reviewer/approver page
  app.py                          # + GET /plan-cycles (serves the new page)

Tentative AOP Forecaster/
  app.py                          # division_aop_summary(): prefer
                                   # buyer_adjusted_totals when present on the
                                   # cycle whose run it's summarizing
                                   # + GET /api/config/recent-runs (new — see
                                   #   API changes; nothing today lists
                                   #   ForecastRuns, confirmed by inspection)

Buyer's Input Sheet/
  otb-plan-app.html               # + "AOP Review" tab
  sync_server.py                  # unchanged (no new backend needed here —
                                   # the tab talks directly to the platform's
                                   # existing/new APIs, cross-origin)
```

### Why a plain HTML page for Plan Cycles, not a React module

Planner/reviewer/approver each need exactly one action (submit / approve /
reject) on a short list of cycles. A full Vite/React module — build step,
`dist/` mount, its own `apiBase.js` dance — is disproportionate to that. The
existing `static/login.html` already establishes the pattern of a
plain-HTML, vanilla-JS page served directly by FastAPI for exactly this kind
of small, infrequently-touched screen; `plan-cycles.html` follows it.

### Why Buyer's Input Sheet stays standalone, calling the platform cross-origin

Rewriting Buyer's Input Sheet as a mounted platform module would touch its
entire existing (working, in daily use) section-level screen for no benefit
to this feature. Its new "AOP Review" tab instead makes `fetch(...,
{credentials: 'include'})` calls straight to `http://localhost:8010/api/...`.
This works today without any CORS change: `app.py`'s `CORSMiddleware` is
already configured `allow_origins=["*"], allow_credentials=True` — Starlette
echoes the specific request `Origin` back (rather than a literal `*`) when
credentials are involved, which is what makes a credentialed cross-origin
request legal at all. The one real constraint: **the browser must already
hold a platform session cookie** — i.e., the user must have logged into
`localhost:8010` at some point (directly, or via Landing/Calendar/AOP/
Planning) before the AOP Review tab's calls will succeed. If they haven't,
the tab shows "Sign in to the platform first" with a link to `/login`,
rather than a raw 401.

## Data model change

```python
# db/models/workflow.py — PlanCycle
buyer_adjusted_totals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

Shape: `{"mens": 1234.56, "ladies": 2345.67, "kids": 3456.78}` — Rs Lakhs,
same unit and same three division codes `division-aop-summary` already
returns. `None` until a buyer saves an edit; sits alongside `current_run_id`
on the same cycle row (no new table — one buyer edit per cycle, not a
history of edits).

One new Alembic migration, no data backfill needed (existing cycles simply
have `buyer_adjusted_totals = NULL`, meaning "no buyer override yet" — the
correct starting state).

## API changes

### New: `PUT /api/aop/plan-cycles/{id}/buyer-totals`

Body: `{"totals": {"mens": ..., "ladies": ..., "kids": ...}}`

- Requires `require_role("buyer")` and `cycle.status == "pending_buyer"` —
  same guard style as `set_current_run`.
- Sets `cycle.buyer_adjusted_totals`. Does **not** transition status — saving
  is a separate action from submitting, so a buyer can edit, leave, and come
  back before submitting (matches `set_current_run`'s existing "iteration,
  not a workflow event" pattern for the run-id field).
- The buyer's actual "submit" is the existing `POST /plan-cycles/{id}/submit`
  — unchanged, no new logic needed there. The AOP Review tab calls
  `PUT .../buyer-totals` then `POST .../submit` in sequence.
- All three totals must be present and numeric, or `422`. (Partial edits —
  e.g. only adjusting Mens — still require resubmitting the full
  three-value object; the tab always shows and submits all three together,
  so this isn't a real user-facing constraint.)

### Changed: `GET /api/config/division-aop-summary` (AOP Forecaster)

Currently: sums `ForecastResult` by division for `latest_approved_run_id`.

New: after finding the latest approved cycle, check
`cycle.buyer_adjusted_totals`. If set, return those three values directly
(still shaped as `{"division": ..., "annual_target": ...}` rows — the
response contract Sales Plan already consumes doesn't change). If `None`
(shouldn't happen once this ships and is used, but is the honest fallback for
any cycle approved before a buyer ever set totals, or a cycle that reached
`approved` with no buyer edit because the buyer submitted without changing
anything), fall back to the existing computed-sum behavior exactly as today.

This is the one and only change needed to make "Sales Plan's sync always
happens from Buyer's Input" true — `sync-from-aop-forecaster` in
`department_plan.py` is untouched; it already just calls this endpoint.

### New: `GET /api/config/recent-runs` (AOP Forecaster)

Checked by inspection — nothing today lists `ForecastRun`s (`/api/results/
{session_id}` requires already knowing the id; `db-sync/status` is a
different table entirely, data-lake sync jobs, not forecast runs). The
planner picker in `plan-cycles.html` needs one. Returns the last ~20 runs:
`[{"run_id", "created_at", "status", "division_totals": {...}}]` — the same
per-division sums `division-aop-summary` computes, so the planner sees what
they're actually submitting before doing so.

Implementation note: extract `division-aop-summary`'s per-division sum logic
into a shared `_division_totals_for_run(run_id)` helper, since both this
endpoint and the new single-run lookup below need it for an arbitrary
`run_id`, not just the latest approved one.

### New: `GET /api/config/runs/{run_id}/division-totals`

The buyer tab's totals source (see below) — a cycle's `current_run_id` isn't
guaranteed to still be within `recent-runs`' ~20-row window by the time a
buyer opens it, so the tab looks it up directly by id rather than filtering
the list. Same shared helper as `recent-runs`, `404` if the run doesn't
exist.

## New UI: `plan-cycles.html` (planner / reviewer / approver)

Served at `GET /plan-cycles` (login required, redirects to `/login` like
every other protected page). One page, two views based on the logged-in
user's role:

- **List**: `GET /api/aop/plan-cycles` — cycle id, status, created date.
  Clicking one loads its detail (`GET /plan-cycles/{id}` — already returns
  status + full transition history, used as-is).
- **Planner** (`role == "planner"`): a "Submit AOP run for buyer review"
  action — picks from `GET /api/config/recent-runs` (new, see API changes)
  and calls `POST /plan-cycles` then `POST /plan-cycles/{id}/submit` in
  sequence, so a freshly-created cycle lands directly in `pending_buyer`
  (matching "planner submits" as one user action, not two).
- **Reviewer** (`pending_review` cycles) / **Approver** (`pending_approval`
  cycles): Approve / Reject buttons calling `POST /plan-cycles/{id}/approve`
  or `.../reject` with an optional comment. Both roles reuse the identical
  markup; only which cycles are actionable differs, driven by `status` +
  the logged-in role (server already enforces the real permission check —
  the UI just hides buttons that would 403).

No new backend routes needed for reviewer/approver — `POST
/plan-cycles/{id}/{action}` already covers both.

## New UI: "AOP Review" tab in Buyer's Input Sheet

Added to the existing tab strip in `otb-plan-app.html`, alongside whatever
tabs exist today. Contents:

1. **Cycle picker** — `GET http://localhost:8010/api/aop/plan-cycles` cross-
   origin, filtered client-side to `status === "pending_buyer"`.
2. **The three division totals** — fetched via the cycle's `current_run_id`
   from the new `GET /api/config/runs/{run_id}/division-totals` (see API
   changes). Rendered as three editable number inputs (Mens / Ladies /
   Kids, Rs Lakhs), prefilled with the computed values.
3. **Calendarised LY reference** — alongside each division's input, the
   corresponding LY actual pulled from Calendar Engine's existing
   `POST /api/calendar/salesdata/reindex` (month-wise), shown as read-only
   context ("LY: ₹X Cr → AOP: ₹Y Cr, +Z%"). This is the "calendarised sales
   branches to the buyer's input module" requirement — informational only,
   not a new stored dependency; if the calendar data lake is unreachable
   (see the recent `KeyError('ym')` fix), this section just shows "LY
   reference unavailable" rather than blocking the rest of the tab.
4. **Save** → `PUT /plan-cycles/{id}/buyer-totals`. **Submit for Review** →
   the same save, then `POST /plan-cycles/{id}/submit`. Both disabled with a
   "Sign in to the platform first" message + `/login` link if the initial
   `GET /plan-cycles` call 401s.

## Error handling

- Every new cross-origin call in Buyer's Input Sheet treats a `401` as "not
  logged into the platform" (distinct message from a `403`, which means
  "logged in but wrong role" — a buyer-only tab a `planner` account opens
  should say so plainly rather than look broken).
- `division-aop-summary`'s existing `404` ("no approved run yet") behavior is
  unchanged — Sales Plan's sync button already handles that case today.
- The new `buyer-totals` endpoint's `409`/`403` cases (wrong status, wrong
  role) surface directly as the transition endpoints' errors already do —
  no new error-handling pattern needed, just the same one reused.

## Testing

- Backend: extend `test_workflow.py` / `test_full_pipeline.py` (existing
  patterns) to cover `set_buyer_totals` — role/status guards, and a full
  walk of draft → … → approved confirming `division-aop-summary` returns the
  buyer's numbers, not the raw computed sum.
- Manual end-to-end walk-through once built: run AOP → submit via
  `plan-cycles.html` → adjust + submit via the AOP Review tab → approve
  twice (reviewer, approver) → confirm Sales Plan's existing "Sync from AOP
  Forecaster" pulls the buyer's numbers.
