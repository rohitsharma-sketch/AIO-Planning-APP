# Dockerize the RS_planning Web Stack — Design

## Goal

Move Landing (7800), AOP Forecaster standalone (8000), RS Planning Platform
(8010), and Buyer's Input Sheet (5050) into Docker containers, orchestrated
by `docker-compose`, while preserving Landing's one-click Master Switch
(launch/stop every other app) and without disrupting anything that currently
depends on the native Postgres instance or the native sync jobs.

## Context

Today, `Landing/landing_server.py` is a plain Python HTTP server that also
acts as a process manager: its Master Switch spawns and kills the other
three apps as native Windows processes (`subprocess.Popen` with
`DETACHED_PROCESS`/`CREATE_NEW_PROCESS_GROUP`, PID lookup via `psutil`).
That mechanism cannot reach into a Docker container from outside it, so
containerizing any of these apps requires rebuilding how Landing controls
them.

Three decisions were confirmed with the user before this design was
written, each closing off an alternative this doc does not pursue:

1. **Postgres stays external**, reached via `host.docker.internal:5432`.
   The `.env.example` describes it as "the shared local instance," implying
   other things on this machine may depend on it — no migration, no new
   Postgres container.
2. **Sync jobs stay native.** AOP Forecaster's and Calendar Engine's sync
   jobs read from `\\10.0.1.85\...\INVENTORY AUTOMATION\data_lake`, a
   Windows UNC path Linux containers can't resolve natively. Rather than
   mount that share via CIFS into containers, the sync logic keeps running
   as a native host process, and the containerized apps proxy to it.
3. **Landing's container gets the Docker socket mounted** (accepted
   trade-off: that container gains root-equivalent control over the whole
   Docker daemon, not just this stack). The alternative (a narrower native
   helper) was declined in favor of the standard approach.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Windows host                                                      │
│                                                                     │
│  Postgres (native, 127.0.0.1:5432)  ◄───────────────────┐         │
│  Sync Helper (native, new FastAPI service, :8999)◄────────┐       │
│       - has real UNC-share access                          │       │
│       - runs store_actuals_sync / calendar_reindex / etc   │       │
│                                                               │       │
│  ┌──────────────────── Docker Desktop ─────────────────┐    │       │
│  │  landing (7800) ── /var/run/docker.sock mounted ─────┼────┘       │
│  │  aop-forecaster (8000)  ────────────────────────────┼────────┐   │
│  │  rs-planning-platform (8010) ────────────────────────┼────────┤   │
│  │  buyers-input (5050)                                 │        │   │
│  │       all reach Postgres via host.docker.internal:5432        │   │
│  │       sync-triggering routes proxy to                          │   │
│  │       host.docker.internal:8999                                │   │
│  └───────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

One `docker-compose.yml` at the repo root defines four services (Landing,
AOP Forecaster, RS Planning Platform, Buyer's Input) on one bridge network.
Postgres and the new Sync Helper are not compose services — they stay
native processes on the host, reached via `host.docker.internal`. All four
containers bind `0.0.0.0` inside the container; compose maps that to the
host's LAN-reachable ports, so another user's machine hitting this server's
exposed URL reaches the same containers, whose sync-triggering calls still
land on the native Sync Helper on this host — sync execution is always
server-side, regardless of which machine's browser initiated the request.

## Components

| Container | Base image | What it builds/runs | Depends on |
|---|---|---|---|
| `landing` | python:3.11-slim + `docker` SDK (pip package) | `landing_server.py`, serves `index.html` | Docker socket (mounted) |
| `aop-forecaster` | node:20 (build stage) → python:3.11-slim | `npm run build` for the React frontend, then `uvicorn app:app` serving `dist/` + API | Postgres (external), Sync Helper (external) |
| `rs-planning-platform` | node:20 (build stage, x3) → python:3.11-slim | Builds AOP/Planning/Calendar frontends into their respective `dist/` folders, then `uvicorn app:app` | Postgres (external), Sync Helper (external) |
| `buyers-input` | python:3.11-slim | `sync_server.py` (Flask) | none |

Each app's Dockerfile is a standard multi-stage build where a frontend
exists: build in a `node:20` stage, copy only the built `dist/` output into
the final slim Python stage, so the shipped image doesn't carry
`node_modules`.

`buyers-input` has no `requirements.txt` today (confirmed by inspection —
none exists in `Buyer's Input Sheet/`). One will be written from its actual
imports (`flask`, `flask-cors`, `pandas`) as part of building its
Dockerfile — a small, contained addition needed to build the image at all,
not a design change.

`DATABASE_URL` (already environment-variable-driven in every app — see
`Tentative AOP Forecaster/db/base.py`) gets overridden per-container in
compose to point at `host.docker.internal` instead of `127.0.0.1`; no
application code needs to change for this.

## Native Sync Helper

A new small FastAPI service, `sync_helper/app.py`, running natively on the
host (not in Docker), listening on port 8999. It owns exactly the sync
logic currently embedded in `Tentative AOP Forecaster/app.py`'s
`/api/config/db-sync*` routes:

- `POST /db-sync` — runs every job in `DB_SYNC_JOBS` (site_master,
  store_actuals, calendar_reindex, etc.), same loop-and-catch-per-job
  behavior `db_sync_all()` has today, just relocated here.
- `GET /db-sync/status` — same as today's status endpoint (reads
  `sync.sync_runs`).

The containerized apps' existing `/api/config/db-sync*` routes become thin
HTTP proxies: instead of `importlib.import_module(...).run()` executing
in-process, they call `http://host.docker.internal:8999/db-sync` and
forward the response verbatim. No frontend code changes — same URLs, same
response shape, only what answers behind them changes.

Any other endpoint that currently imports and calls sync/reindex logic
in-process (e.g. Calendar Engine's day-wise/month-wise reindex trigger)
follows the same pattern: identify it, move its execution into the Sync
Helper, replace the in-process call with an HTTP proxy call. The initial
implementation plan should enumerate every such endpoint explicitly rather
than assume `/api/config/db-sync*` is the only one.

## Landing's Master Switch rework

`docker-compose.yml`'s service names match `landing_server.py`'s existing
`APPS` list identifiers (`aop-forecaster`, `rs-planning-platform`,
`buyers-input`) so Landing's container can look them up by name. Landing's
container gets `/var/run/docker.sock` bind-mounted, plus the `docker`
Python package added to its image.

Rework of the three functions that currently drive the Master Switch:

- `_is_online(port)` → replaced by a container-name lookup:
  `docker.from_env().containers.get(name).status == "running"`.
- `_launch(app)` → `container.start()`.
- `_shutdown_many(ports_and_names)` → `container.stop()` per container,
  keeping the existing concurrent-wait pattern (`psutil.wait_procs`'s
  role played by iterating `container.wait(timeout=...)` calls
  concurrently, or the SDK's equivalent) so total wall time is still bounded
  by the single slowest container, not their sum.

Landing itself is never in this list — same as today, since if this
endpoint is being hit at all, Landing is already running.

## Error handling

- **Sync Helper unreachable** (native process not running): the proxy call
  fails with a clear error message surfaced to the UI the same way a 500
  from the in-process call is surfaced today — no silent hang, no generic
  "something went wrong."
- **Docker socket unavailable or permission denied**: Master Switch buttons
  show an explicit error instead of failing silently (today's psutil path
  has no real failure mode here since it's native process control; this is
  a genuinely new failure surface the rework introduces and must handle
  explicitly).
- **A container fails to start** (bad image, missing env var, Postgres
  unreachable at container startup): surfaced through the existing
  `already_online`/`launched` response shape in `_launch_all`, extended to
  report a `failed` bucket rather than silently reporting a container as
  "launched" when it immediately exited.

## Testing & rollout

Docker Desktop is **not installed on this machine** (confirmed via
PowerShell — no `docker` CLI, no Docker service) as of this design being
written. Nothing here can be run or verified until it's installed.

Rollout order, once Docker is available:

1. Build and run each of the four containers standalone (`docker run`, not
   compose) and confirm each one starts, reaches Postgres via
   `host.docker.internal`, and (for AOP Forecaster / RS Planning Platform)
   reaches the Sync Helper — before touching Landing's Master Switch
   rework. This isolates "does the container work" from "does Landing's
   orchestration of it work."
2. Bring the four up together via `docker-compose up` and confirm they
   reach each other and Postgres/Sync Helper correctly on the shared
   network.
3. Only then rework Landing's `_is_online`/`_launch`/`_shutdown_many` and
   verify the Master Switch against the running compose stack.
4. Verify the "another user's machine" scenario explicitly: from a second
   machine on the LAN, hit this host's exposed port and confirm both the
   app loads and a sync-triggering action correctly executes on this host
   (not silently fail, not attempt to run on the second machine).

Build success is not sufficient to call any step done — each step needs an
actual running verification before moving to the next, per this session's
standing verification discipline.

## Out of scope

- Containerizing Postgres.
- Containerizing or otherwise changing how sync jobs reach the
  `\\10.0.1.85\...` network share.
- `SalesPlan/backend` (has its own `requirements.txt` but was not named as
  part of "the web apps" in this request — not touched by this design).
- Production deployment concerns (TLS, restart policies beyond Docker's
  defaults, secrets management beyond environment variables) — this design
  covers local/LAN operation matching how the stack runs today, not a
  hardened production posture.
