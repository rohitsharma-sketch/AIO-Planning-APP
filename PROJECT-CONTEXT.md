# Project Context — RS Planning Suite

## Name and purpose
RS Planning Suite (Citykart retail): internal planning tools that run the planning
chain Calendar Engine -> AOP Forecaster -> Buyer's Input Sheet (BIS) -> Sales Plan,
plus side tools (NSO Distributor, AOP Re-Aligner, Growth vs LY, Listing / Delisting
Analyser), all opened from one Landing page on the office network.

## Tech stack
- Front ends: React + Vite (Calendar, AOP, Sales Plan; built dist/ is committed and
  served) and single-file HTML / plain JS (BIS, Landing, NSO, Re-Aligner, Growth vs LY,
  Listing).
- Back ends: Python (FastAPI unified platform on 8010, Flask / http.server app servers),
  PostgreSQL, data-lake parquet files on a network share.
- Landing (7800) is the only port shared on the network; it proxies every app and
  enforces sign-in and per-person rights.

## Current phase
Live internal use with stakeholder demos. Live AOP = Version 2 (locked). Ongoing work:
UI declutter across the suite; planner factor models (Matrix / Weighted / Continuous)
with back-test.

## Key constraints
- No change to calculations or numbers unless explicitly asked; division plans must
  always equal AOP.
- Keep e2e-tested texts, rights-guarded labels and element ids unchanged.
- Never overwrite users' plan files; database writes need confirmation and a backup.
- Every change: tests, commit + push (origin and aio), CHANGELOG entry.
- Values only (no quantity) in BIS.

## What "done" looks like
The change is visible in the app, every existing action is still reachable with the
same safeguards, tests pass, numbers are unchanged unless that was the ask, and it is
committed, pushed and logged in CHANGELOG.md.
