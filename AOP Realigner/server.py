"""Sales Plan Re-Aligner - web app.  python server.py  ->  http://localhost:8070

Every slow thing (reading a workbook, realigning, building an export) runs as a background job made of
timed steps; GET /api/state shows them live with an ETA learned from previous runs, and finished jobs go
to a persistent activity history. Requests never block on the work itself.
Business logic lives in engine.py, file reading/validation in importer.py.
"""
import contextlib
import json
import os
import pickle
import re
import shutil
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pandas as pd

import engine
import importer
from engine import DEPT, STORE

PORT = int(os.environ.get("REALIGNER_PORT", 8070))
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, ".cache")  # gitignored: real plan data
ORIG_PKL = os.path.join(CACHE_DIR, "original.pkl")
TIMINGS_JSON = os.path.join(CACHE_DIR, "timings.json")
HISTORY_JSON = os.path.join(CACHE_DIR, "history.json")
LOCKS_JSON = os.path.join(CACHE_DIR, "locks.json")
REPHASE_OV_JSON = os.path.join(CACHE_DIR, "rephase_overrides.json")   # Re-phase store overrides (REF OLD, fixed mix)
# Each signed-in user has their own workspace (user, 2026-09-30: "make it so each user gets their own copy"):
# .cache/users/<name>/ holds their original.pkl, locks.json, rephase_overrides.json and history.json. A new user's
# workspace starts as a copy of the files above (the setup at the time), then is theirs alone.
USERS_DIR = os.path.join(CACHE_DIR, "users")
AUTH_ME = "http://127.0.0.1:8010/api/auth/me"   # who a Landing session cookie belongs to
IDLE_UNLOAD = 2 * 3600   # an untouched workspace frees its plan from memory after this long (reloads on next visit)
MAX_BODY = 400 * 1024 * 1024
KB_JSON = os.path.join(HERE, "..", "Listing Delisting", "app", "kb.json")  # Listing / Delisting Analyser app's listing history
# the three ways to revise an existing plan (engine.py); each has its own step-2 file and template
METHODS = {"listing": "Store listing changes", "dept": "Existing department changes", "newdept": "New or split departments",
           "shift": "Listing / delisting shifted to a target", "growth": "Growth changes"}
SALES_JSON = os.path.join(HERE, "..", "Listing Delisting", "app", "sales.json")   # month-wise SL_V, rebuilt by the daily sync
ATT_MASTER = os.path.join(HERE, "..", "SalesPlan", "Attribute Master", "att master.xlsx")  # DEPARTMENT -> SECTION
_ref_cache = {}


def _cached(path, build):
    """Read a reference file once; read it again only when the file changes."""
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return {}
    hit = _ref_cache.get(path)
    if not hit or hit[0] != mt:
        hit = _ref_cache[path] = (mt, build(path))
    return hit[1]


def sections():
    """Attribute Master (the planning one): department -> section, names normalised like the importer."""
    def build(path):
        import pandas as pd
        am = pd.read_excel(path, engine="calamine")
        am.columns = [str(c).strip().upper() for c in am.columns]
        n = lambda x: " ".join(str(x).split()).upper()
        return {n(d): n(sc) for d, sc in zip(am["DEPARTMENT"], am["SECTION"]) if str(sc).strip() and str(d).strip()}
    return _cached(ATT_MASTER, build)


def last_year():
    """{(store, dept): {"Sep'25": value in lakhs}} from the Listing app's month-wise sales (SL_V in rupees)."""
    def build(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)["data"]
        return {(st, d): {m[:6]: v / 1e5 for m, v in mm.items()} for st, dd in data.items() for d, mm in dd.items()}
    return _cached(SALES_JSON, build)


def ly_partial():
    """Last-year months the sales export doesn't hold in full yet ("Sep'26(Till Date)" -> {"Sep'26"})."""
    try:
        mt = os.path.getmtime(SALES_JSON)
    except OSError:
        return set()
    hit = _ref_cache.get("ly_partial")
    if not hit or hit[0] != mt:
        with open(SALES_JSON, encoding="utf-8") as fh:
            hit = _ref_cache["ly_partial"] = (mt, {m[:6] for m in json.load(fh)["months"] if "(" in m})
    return hit[1]


def ly_departments():
    """Departments with last year's sales - the choices for Re-phase from LY's shape (a proxy such as LW_U_T-TOP F/S
    need not be in the plan). Rebuilt only when sales.json changes."""
    ly = last_year()
    hit = _ref_cache.get("ly_departments")
    if not hit or hit[0] is not ly:
        hit = _ref_cache["ly_departments"] = (ly, sorted({d for _, d in ly}))
    return hit[1]
os.makedirs(USERS_DIR, exist_ok=True)


class UserError(Exception):
    """A problem the user can fix - shown as-is in the UI."""


def stamp(t=None):
    return time.strftime("%d %b %H:%M:%S", time.localtime(t or time.time()))


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _save_json(path, obj):
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(path + ".tmp", path)


class Timings:
    """Last duration of each step (and the input size it had) -> ETA for the next run, scaled by size.
    Seeded from measured runs on the real 674k-row plan so the very first run already has an estimate."""
    SEED = {"read:original": [22.0, 126e6], "check:original": [6.0, 674478], "save:original": [3.0, 674478],
            "read:revised": [1.0, 75e3], "check:revised": [2.0, 674478], "realign": [15.0, 674478],
            "verify": [3.0, 674478], "export:full:xlsx": [150.0, 681732], "export:full:csv": [9.0, 681732],
            "export:compare:xlsx": [38.0, 278545], "export:compare:csv": [4.0, 278545]}

    def __init__(self):
        self.d = {**self.SEED, **_load_json(TIMINGS_JSON, {})}
        self.lock = threading.Lock()

    def estimate(self, key, size=None):
        secs, was = self.d.get(key, (None, None))
        if secs is None:
            return None
        return secs * size / was if size and was else secs

    def record(self, key, secs, size):
        with self.lock:
            self.d[key] = [secs, size]
            _save_json(TIMINGS_JSON, {k: v for k, v in self.d.items() if self.SEED.get(k) != v})


timings = Timings()


class Job:
    def __init__(self, group, kind, label):
        self.id, self.group, self.kind, self.label = uuid.uuid4().hex[:10], group, kind, label
        self.status, self.error, self.steps = "running", None, []
        self.started, self.ended = time.time(), None

    @contextlib.contextmanager
    def step(self, name, key=None, size=None):
        s = {"name": name, "status": "running", "started": time.time(), "ended": None,
             "eta": timings.estimate(key, size) if key else None, "done": None, "total": None}
        self.steps.append(s)
        try:
            yield s
            s["status"] = "done"
        except BaseException:
            s["status"] = "error"
            raise
        finally:
            s["ended"] = time.time()
            if key and s["status"] == "done":
                timings.record(key, s["ended"] - s["started"], size)

    def progress(self, done, total):
        if self.steps:
            self.steps[-1].update(done=done, total=total)

    def elapsed(self):
        return (self.ended or time.time()) - self.started

    def view(self):
        now, steps = time.time(), []
        for s in self.steps:
            secs = (s["ended"] or now) - s["started"]
            left = None
            if s["status"] == "running":
                if s["total"] and s["done"]:
                    left = secs / s["done"] * (s["total"] - s["done"])
                elif s["eta"] is not None:
                    left = max(s["eta"] - secs, 0.0)
            steps.append({"name": s["name"], "status": s["status"], "secs": round(secs, 1),
                          "left": None if left is None else round(left, 1), "eta": s["eta"] and round(s["eta"], 1),
                          "done": s["done"], "total": s["total"]})
        return {"id": self.id, "kind": self.kind, "label": self.label, "status": self.status, "error": self.error,
                "secs": round(self.elapsed(), 1), "started_at": stamp(self.started),
                "ended_at": self.ended and stamp(self.ended), "steps": steps}


jobs_lock = threading.Lock()
_tl = threading.local()   # the workspace of the request / job running on this thread


class _Mine:
    """Stands for the calling user's own dict / list in their workspace, so `state["orig"]`, `jobs.values()` and
    `history[:20]` below always mean *this* user's."""
    def __init__(self, attr):
        self._attr = attr

    def _o(self):
        return getattr(_tl.ws, self._attr)

    def __getattr__(self, n):
        return getattr(self._o(), n)

    def __getitem__(self, k):
        return self._o()[k]

    def __setitem__(self, k, v):
        self._o()[k] = v

    def __delitem__(self, k):
        del self._o()[k]

    def __contains__(self, k):
        return k in self._o()

    def __iter__(self):
        return iter(self._o())

    def __len__(self):
        return len(self._o())


jobs, history, state = _Mine("jobs"), _Mine("history"), _Mine("state")


def start_job(group, kind, label, fn, *args):
    """Run fn(job, *args) in the background. One running job per group ("data" = anything that changes
    the loaded plans or the result; each export has its own group)."""
    with jobs_lock:
        busy = next((j for j in jobs.values() if j.group == group and j.status == "running"), None)
        if busy:
            raise UserError(f"Please wait - {busy.label.lower()} is still running.")
        job = Job(group, kind, label)
        jobs[job.id] = job
        for old in sorted(jobs.values(), key=lambda j: j.started)[:-40]:
            if old.status != "running":
                jobs.pop(old.id)
    threading.Thread(target=_run, args=(job, fn, args, _tl.ws), daemon=True).start()
    return job


def _run(job, fn, args, w):
    _tl.ws, engine._TL.locks = w, w.locks   # the job works in its user's workspace
    try:
        fn(job, *args)
        job.status = "done"
    except UserError as e:
        job.status, job.error = "error", str(e)
    except Exception as e:
        job.status, job.error = "error", f"Unexpected error - {type(e).__name__}: {e}"
        traceback.print_exc()
    finally:
        job.ended = time.time()
        with jobs_lock:
            w.history.insert(0, job.view())
            del w.history[40:]
            _save_json(w.path("history.json"), w.history)


# ---------------------------------------------------------------- state

NO_RESULT = {"result": None, "out": None, "compare": None, "summary": None, "exports": {}}
def _new_state():
    return {"orig": None, "months": [], "orig_info": None, "orig_report": [], "orig_failed": None,
            "rev": None, "rev_months": [], "rev_info": None, "rev_report": [], "rev_upload": None, "orig_upload": None,
            "rev_source": {}, "method": "dept", "locks": [], "rephase_ov": None, **NO_RESULT}


lock = threading.RLock()


def _set_locks(months, chosen=None):
    """Locked months = kept exactly as the original (user, 2026-09-29: "make these locks dynamic for months ...
    auto detect the months as per the original plan upload"). Only months found in the original plan can be
    locked; a month without a choice yet is unlocked (user, 2026-10-02: "the month lock only can be configured
    if the user has set it" - was Jan / Feb). Saved so it survives a restart. Per user:
    the calling user's workspace and this thread's engine locks."""
    chosen = chosen or {}
    locks = [m for m in months if chosen.get(m, m[:3] in engine.FROZEN)]
    _tl.ws.locks = engine._TL.locks = set(locks)
    state["locks"] = locks
    _save_json(_tl.ws.path("locks.json"), {"months": months, "chosen": {m: m in locks for m in months}})
    return locks

def _safe(name):
    return re.sub(r"[^A-Za-z0-9._@-]", "_", name)[:80] or "local"


class Workspace:
    """One user's own Re-Aligner: plan, locks, overrides, revised file, result, exports, jobs and history."""

    def __init__(self, key, name=None):
        self.name, self.dir = name or key, os.path.join(USERS_DIR, _safe(key))
        old = os.path.join(USERS_DIR, _safe(self.name))   # folders were named by username before 30 Sep: keep that work
        if not os.path.isdir(self.dir) and old != self.dir and os.path.isdir(old):
            os.rename(old, self.dir)
        if not os.path.isdir(self.dir):          # first visit: start from a copy of the setup at the time
            os.makedirs(self.dir)
            for f in (ORIG_PKL, LOCKS_JSON, REPHASE_OV_JSON):
                if os.path.exists(f):
                    shutil.copy2(f, os.path.join(self.dir, os.path.basename(f)))
        self.jobs, self.history = {}, _load_json(self.path("history.json"), [])
        self.locks, self.touched = None, time.time()
        self.state = _new_state()
        self.load()

    def path(self, f):
        return os.path.join(self.dir, f)

    def load(self):
        """The saved plan, locks and overrides into memory (on first use, and again after an idle unload)."""
        prev, _tl.ws = getattr(_tl, "ws", None), self
        try:
            if os.path.exists(self.path("original.pkl")):
                try:
                    with open(self.path("original.pkl"), "rb") as fh:
                        saved = pickle.load(fh)
                    if isinstance(saved, tuple):  # cache written by the previous version: (df, months, meta)
                        df, months, meta = saved
                        for c in (STORE, DEPT, engine.DIV, engine.DISP):  # the old reader kept double spaces; today's importer collapses them
                            df[c] = df[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
                        saved = {"df": df, "months": months, "report": [], "info": {
                            "name": urllib.parse.unquote(meta.get("name", "original plan")), "loaded_at": meta.get("loaded_at"),
                            "rows": len(df), "stores": int(df[STORE].nunique()), "departments": int(df[DEPT].nunique()),
                            "divisions": sorted(df[engine.DIV].unique().tolist()), "months": months,
                            "colmap": {c: c for c in df.columns}, "sheets": [], "parse_secs": None}}
                    self.state.update(orig=saved["df"], months=saved["months"], orig_info=saved["info"], orig_report=saved["report"])
                except Exception:
                    traceback.print_exc()
            _set_locks(self.state["months"], _load_json(self.path("locks.json"), {}).get("chosen"))
            self.state["rephase_ov"] = _load_json(self.path("rephase_overrides.json"), None)   # kept until cleared
            self.loaded = True
        finally:
            _tl.ws = prev

    def unload(self):
        """Free the plan and any result from memory - the plan is on disk and reloads on the next visit."""
        with lock:
            self.state.update(_new_state())
            self.loaded = False


_spaces, _spaces_lock, _who = {}, threading.Lock(), {}


def who(cookie):
    """(account id, username) of the signed-in RS Planning user a request comes from (Landing forwards its session
    cookie), cached a minute. Keyed by id so a renamed user keeps their workspace.
    No cookie / not signed in (direct loopback use of :8070) -> the "local" workspace."""
    if not cookie:
        return "local", "local"
    now = time.time()
    hit = _who.get(cookie)
    if hit and now - hit[1] < 60:
        return hit[0]
    name = "local", "local"
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(urllib.request.Request(AUTH_ME, headers={"Cookie": cookie}), timeout=5) as r:
            me = json.load(r)
        if me.get("id"):
            name = me["id"], me.get("username") or me["id"]
    except Exception:  # noqa: BLE001 - 401 / platform down: no user
        pass
    if len(_who) > 500:
        _who.clear()
    _who[cookie] = (name, now)
    return name


def workspace(key, name=None):
    """This user's workspace (created on first visit); frees other idle workspaces' memory.
    ponytail: one lock around creation - a first visit (loading a ~200 MB plan) briefly holds up other users' polls."""
    with _spaces_lock:
        w = _spaces.get(key)
        if w is None:
            w = _spaces[key] = Workspace(key, name)
        w.name = name or w.name                  # a rename shows up on the next visit
        now = time.time()
        for o in _spaces.values():
            if o is not w and o.loaded and now - o.touched > IDLE_UNLOAD and not any(j.status == "running" for j in o.jobs.values()):
                o.unload()
    if not w.loaded:
        w.load()
    w.touched = time.time()
    return w


def _overrides():
    """The uploaded Re-phase store overrides ({store: {ref_old, mix}}), or None."""
    return (state.get("rephase_ov") or {}).get("stores")


def _fail(report, what):
    errs = [i["msg"] for i in report.items if i["level"] == "error"]
    raise UserError(f"{what}: {errs[0]}" + (f" (+{len(errs) - 1} more problem(s) - see the card)" if len(errs) > 1 else ""))


def job_original(job, data, name, sheet=None):
    with job.step("Read workbook", "read:original", len(data)):
        df, info, rep = importer.read_table(data, name, importer.NEED_ORIGINAL, "original plan", sheet)
    months = []
    if df is not None:
        with job.step("Check columns and values", "check:original", len(df)):
            df, months, info, rep = importer.prepare_original(df, info, rep)
    info.update(name=name, loaded_at=stamp(), parse_secs=round(job.elapsed(), 1))
    if not rep.ok:
        with lock:
            state["orig_failed"] = {"name": name, "at": stamp(), "report": rep.items, "sheets": info.get("sheets", [])}
            state["orig_upload"] = (data, name) if len(info.get("sheets", [])) > 1 else None
        _fail(rep, name)
    with job.step("Save for next session", "save:original", len(df)):
        pkl = _tl.ws.path("original.pkl")
        with open(pkl + ".tmp", "wb") as fh:
            pickle.dump({"df": df, "months": months, "info": info, "report": rep.items}, fh)
        os.replace(pkl + ".tmp", pkl)
    with lock:
        # a month the previous plan also had keeps the user's lock choice; a new month starts on the default
        _set_locks(months, _load_json(_tl.ws.path("locks.json"), {}).get("chosen"))
        state.update(orig=df, months=months, orig_info=info, orig_report=rep.items, orig_failed=None,
                     orig_upload=(data, name) if len(info["sheets"]) > 1 else None, **NO_RESULT)
        rev = state["rev_upload"]
    if rev:  # the revised plan was checked against the old original - check it again
        with contextlib.suppress(UserError):  # its problems show on its own card; the original itself loaded fine
            _check_revised(job, *rev)


def job_revised(job, data, name, sheet=None, method="dept"):
    _check_revised(job, data, name, sheet, method)


def _check_revised(job, data, name, sheet=None, method="dept"):
    with lock:
        orig, months = state["orig"], state["months"]
    if orig is None:
        raise UserError("Load the original plan first (step 1).")
    with job.step("Read the file", "read:revised", len(data)):
        if method == "listing":
            df, info, rep = importer.read_table(data, name, importer.NEED_LISTING, "listing changes", sheet)
            prep = importer.prepare_listing
        elif method == "shift":
            df, info, rep = importer.read_table(data, name, importer.NEED_SHIFT, "listing / delisting shift", sheet)
            sec = sections()
            prep = lambda df, info, rep, orig, months: importer.prepare_listing(df, info, rep, orig, months, True, sec)
        elif method == "growth":
            df, info, rep = importer.read_table(data, name, importer.NEED_GROWTH, "growth changes", sheet)
            ly = last_year()
            prep = lambda df, info, rep, orig, months: importer.prepare_growth(df, info, rep, orig, months, ly)
        elif method == "newdept":  # either a split file or a new-department values file
            df, info, rep = importer.read_table(data, name, importer.NEED_SPLIT, "split file", sheet)
            prep = importer.prepare_split
            if df is None:
                df, info, rep2 = importer.read_table(data, name, importer.NEED_REVISED, "new-department file", sheet)
                prep = importer.prepare_revised
                if df is None:
                    rep.error("Method 3 takes a split file (PARENT DEPARTMENT, NEW DEPARTMENT, SHARE %) or a new-department "
                              "file (STORE NAME, DEPARTMENT, COPY FROM, '<Month> New') - this is neither.")
                else:
                    rep = rep2
        else:
            df, info, rep = importer.read_table(data, name, importer.NEED_REVISED, "revised plan", sheet)
            prep = importer.prepare_revised
    r, use, source = None, [], {}
    if df is not None:
        with job.step("Check against the original", "check:revised", len(orig)):
            r, use, source, info, rep = prep(df, info, rep, orig, months)
    how = info.pop("_how", None)   # Method 1: how each new listing was sized - for the check file only
    info.update(name=name, loaded_at=stamp(), method=method)
    with lock:
        state.update(rev_how=how)
        state.update(rev=r if rep.ok else None, rev_months=use if rep.ok else [], rev_info=info, rev_source=source if rep.ok else {},
                     rev_report=rep.items, rev_upload=(data, name, sheet, method), **NO_RESULT)
    if not rep.ok:
        _fail(rep, name)


def job_run(job):
    with lock:
        o, r, months, source = state["orig"], state["rev"], state["months"], state["rev_source"]
        method = (state["rev_info"] or {}).get("method", "dept")
        div_cap = (state["rev_info"] or {}).get("div_cap")   # Method 1 new listings: capped at store x division
        names = (state["orig_info"] or {}).get("name"), (state["rev_info"] or {}).get("name")
    if o is None or r is None:
        raise UserError("Load a valid original plan (step 1) and revised plan (step 2) first.")
    with job.step("Realign", "realign", len(o)):
        try:
            out, summ, warn, compare = engine.realign(o, r, months, source, div_cap)
        except ValueError as e:
            raise UserError(str(e))
    with job.step("Verify totals", "verify", len(o)):
        checks, dept_table = engine.verify(o, r, out, months, div_cap)
    # the recheck (user, 2026-10-01: "if the check fails at any level then it should auto run till it passes"): a rerun
    # of the same inputs gives the same output, so each round REPAIRS the output (no negatives, every store x division x
    # month on the original) and verifies again - until all pass, a round fixes nothing more, or 5 rounds
    rechecks = 0
    while any(c["status"] == "fail" for c in checks) and rechecks < 5:
        with job.step(f"Recheck {rechecks + 1}: repair and verify again", "recheck", len(o)):
            out, fixed = engine.repair(o, out, months)
            if not len(fixed):
                break
            rechecks += 1
            compare = engine.merge_compare(compare, fixed)
            checks, dept_table = engine.verify(o, r, out, months, div_cap)
    if rechecks:
        left = [c["name"] for c in checks if c["status"] == "fail"]
        warn.append(f"Recheck: {rechecks} round(s) repaired the output and re-ran every check - "
                    + (f"still failing (nothing more it can fix): {', '.join(left)}" if left else "all checks now pass") + ".")
    res = {"id": job.id, "method": method, "finished_at": stamp(), "secs": round(job.elapsed(), 1), "original": names[0], "revised": names[1],
           "rows": len(out), "changed_rows": len(compare), "summary": summ, "warnings": warn, "rechecks": rechecks,
           "checks": checks, "dept_table": dept_table,
           "status_counts": compare["Status"].value_counts().to_dict() if len(compare) else {}}
    with lock:
        state.update(out=out, compare=compare, summary=summ, result=res, exports={})


EXPORTS = {"compare": "Comparison vs original", "full": "Full realigned plan", "plan": "Plan-to-plan mapping"}


def job_rephase(job, dept, mix=None):
    """Method 2 in one go (user, 2026-09-30: "i just select the department ... take it to the final plan"): build the
    re-phase from last year, load it as the revised plan and realign with the other departments kept as they are -
    exactly the Re-phase file download -> step-2 upload -> Run, with the same checks at every step."""
    with lock:
        o, months = state["orig"], state["months"]
    if o is None:
        raise UserError("Load the original plan first (step 1).")
    ly = last_year()
    if not ly:
        raise UserError("Last year's sales (the Listing / Delisting Analyser's sales.json) aren't built yet.")
    with job.step("Build the re-phase from last year", "rephase", len(o)):
        try:
            df, how, notes = importer.template_rephase(o, months, ly, dept, mix, _overrides(), ly_partial())
        except ValueError as e:
            raise UserError(str(e))
        data = engine.write_xlsx([("Revised plan", df), ("How it was built", how), ("Summary", pd.DataFrame({"NOTE": notes}))])
    with lock:   # the other departments absorb it, so every store x division x attribute x month stays on the original (the cap)
        state.update(method="dept")
    _check_revised(job, data, f"Re-phase from LY - {dept}.xlsx", None, "dept")
    with lock:
        if state["rev_info"] is not None:
            state["rev_info"]["generated"] = True   # built here, not uploaded - the page shows no Replace drop zone for it
            state["rev_report"] = [{"level": "info", "msg": n, "examples": []} for n in notes] + state["rev_report"]
    job_run(job)


def job_export(job, kind, fmt):
    with lock:
        res, out, compare, summ = state["result"], state["out"], state["compare"], state["summary"]
        orig, months = state["orig"], state["months"]
        colmap = (state["orig_info"] or {}).get("colmap") or {}
    if not res:
        raise UserError("Run the realignment first.")
    size = len(out) if kind in ("full", "plan") else len(compare) + len(summ)
    with job.step(f"Build {EXPORTS[kind].lower()} ({fmt.upper()})", f"export:{kind}:{fmt}", size):
        if kind == "plan":   # every row, original vs final (user, 2026-10-01)
            data, ctype, ext = engine.export_plan_to_plan(orig, out, months, fmt, job.progress)
        elif kind == "full":
            data, ctype, ext = engine.export(engine.round6(out).rename(columns={k: v for k, v in colmap.items() if k in out.columns}),
                                             fmt, job.progress)
        else:
            levels = engine.compare_levels(orig, out, months, (state["rev_info"] or {}).get("div_cap")) if fmt == "xlsx" else None
            data, ctype, ext = engine.export_compare(summ, compare, fmt, job.progress, levels)
    name = "Realigned Plan" + {"compare": " - Comparison", "plan": " - Plan to Plan"}.get(kind, "") + f".{ext}"
    with lock:
        if state["result"] and state["result"]["id"] == res["id"]:  # a newer run makes this build stale
            state["exports"][f"{kind}-{fmt}"] = {"data": data, "ctype": ctype, "filename": name, "size": len(data),
                                                 "built_at": stamp(), "secs": round(job.elapsed(), 1)}


def public_state():
    with lock:
        s = dict(state)
        exports = {k: {kk: vv for kk, vv in v.items() if kk != "data"} for k, v in s["exports"].items()}
    now = time.time()
    with jobs_lock:
        live = [j.view() for j in sorted(jobs.values(), key=lambda j: j.started)
                if j.status == "running" or now - (j.ended or now) < 8]
        hist = history[:20]
    o, res = s["orig"], s["result"]
    est = {}
    if o is not None:
        est["realign"] = (timings.estimate("realign", len(o)) or 0) + (timings.estimate("verify", len(o)) or 0)
    if res:
        for kind in EXPORTS:
            for fmt in ("xlsx", "csv"):
                size = res["rows"] if kind in ("full", "plan") else res["changed_rows"] + len(res["summary"])
                est[f"{kind}-{fmt}"] = timings.estimate(f"export:{kind}:{fmt}", size)
    return {
        "original": s["orig_info"] and {**{k: v for k, v in s["orig_info"].items() if k != "colmap"}, "report": s["orig_report"]},
        "original_failed": s["orig_failed"],
        "revised": s["rev_info"] and {**{k: v for k, v in s["rev_info"].items() if k != "colmap"},
                                      "report": s["rev_report"], "ok": s["rev"] is not None},
        "result": res, "exports": exports, "jobs": live, "history": hist, "estimates": est,
        "departments": sorted(o[DEPT].unique().tolist()) if o is not None else [],
        "method": s["method"], "listing_app": os.path.exists(KB_JSON), "locks": s["locks"],
        "ly_departments": ly_departments() if o is not None and s["method"] == "dept" else [],
        "user": _tl.ws.name,   # whose workspace this is
        "rephase_overrides": (lambda v: v and {"name": v["name"], "loaded_at": v["loaded_at"], "stores": len(v["stores"]),
                                               "ref_old": sum("ref_old" in x for x in v["stores"].values()),
                                               "mix": sum(len(x.get("mix") or {}) if all(isinstance(y, dict) for y in (x.get("mix") or {}).values()) else 0
                                                          for x in v["stores"].values())})(s.get("rephase_ov")),
    }


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the console quiet; /api/state is polled every second
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _route(self):
        u = urllib.parse.urlsplit(self.path)
        return u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}

    def _enter(self):
        """Every request works in its own user's workspace."""
        _tl.ws = workspace(*who(self.headers.get("Cookie")))
        engine._TL.locks = _tl.ws.locks

    def do_GET(self):
        self._enter()
        path, q = self._route()
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if path == "/rules.js":  # rules in force + version log, shown by the page's Rules button
            with open(os.path.join(HERE, "rules.js"), "rb") as fh:
                return self._send(200, fh.read(), "text/javascript; charset=utf-8")
        if path == "/api/state":
            return self._send(200, public_state())
        if path == "/api/download":
            with lock:
                e = state["exports"].get(f"{q.get('type')}-{q.get('fmt')}")
            if not e:
                return self._send(404, {"error": "That file hasn't been built yet - use the Build button first."})
            return self._send(200, e["data"], e["ctype"], {"Content-Disposition": f'attachment; filename="{e["filename"]}"'})
        if path == "/api/template":
            with lock:
                o, months = state["orig"], state["months"]
            if o is None:
                return self._send(400, {"error": "Load the original plan first."})
            method, kind, dept = q.get("method") or "dept", q.get("kind"), q.get("dept") or None
            sheets = None
            if method == "listing" and kind == "check":   # Method 1 check file: the realigned result, before Run
                with lock:
                    r, src, how = state["rev"], state["rev_source"], state.get("rev_how") or []
                    info = state["rev_info"] or {}
                if r is None or info.get("method") != "listing":
                    return self._send(400, {"error": "Upload a valid listing changes file first (step 2)."})
                try:
                    out = engine.realign(o, r, months, src, info.get("div_cap"))[0]
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, engine.write_xlsx(importer.listing_check(o, out, months, how), None, "0.00000000"),
                                  engine.XLSX_CTYPE, {"Content-Disposition": 'attachment; filename="Listing check file.xlsx"'})
            if method in ("listing", "shift"):
                kb = None
                if kind == "kb":
                    if not os.path.exists(KB_JSON):
                        return self._send(404, {"error": "The Listing / Delisting Analyser's data isn't built yet."})
                    with open(KB_JSON, encoding="utf-8") as fh:
                        kb = json.load(fh)
                df, skipped = (importer.template_shift if method == "shift" else importer.template_listing)(o, months, kb)
                what = "Listing shifts" if method == "shift" else "Listing changes"
                name = f"{what} - from Listing app.xlsx" if kb else f"{what} template.xlsx"
                if len(skipped):
                    sheets = [("Listing changes", df), ("Not included", skipped)]
            elif method == "growth":
                ly = last_year()
                if not ly:
                    return self._send(404, {"error": "Last year's sales (the Listing / Delisting Analyser's sales.json) aren't built yet."})
                df, name = importer.template_growth(o, months, ly), "Growth changes template.xlsx"
            elif method == "newdept":
                df, name = ((importer.template_split(), "Department split template.xlsx") if kind == "split"
                            else (importer.template_newdept(months), "New department template.xlsx"))
            elif kind in ("rephase", "rephase-overrides"):   # Method 2 file from last year's month shape (docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md)
                ly = last_year()
                if not ly:
                    return self._send(404, {"error": "Last year's sales (the Listing / Delisting Analyser's sales.json) aren't built yet."})
                if not dept:
                    return self._send(400, {"error": "Pick the department to re-phase first."})
                try:
                    if kind == "rephase-overrides":   # the stores of this re-phase, the ones needing REF OLD / a mix first
                        sheets = [("Store overrides", importer.template_rephase_overrides(o, months, ly, dept, q.get("mix") or None,
                                                                                           _overrides()))]
                        name = f"Re-phase store overrides - {dept}.xlsx"
                    else:
                        df, how, notes = importer.template_rephase(o, months, ly, dept, q.get("mix") or None, _overrides(), ly_partial())
                        sheets = [("Revised plan", df), ("How it was built", how), ("Summary", pd.DataFrame({"NOTE": notes}))]
                        name = f"Re-phase from LY - {dept}.xlsx"
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
            else:
                df = importer.template(o, months, dept)
                name = f"Revised plan template - {dept}.xlsx" if dept else "Revised plan template.xlsx"
            return self._send(200, engine.write_xlsx(sheets or [("Revised plan", df)]), engine.XLSX_CTYPE,
                              {"Content-Disposition": f'attachment; filename="{name.replace("/", "-")}"'})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        self._enter()
        path, q = self._route()
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "File too large (400 MB max)."})
        data = self.rfile.read(n) if n else b""
        name = urllib.parse.unquote(self.headers.get("X-File-Name", "upload.xlsx"))
        try:
            method = q.get("method") or state["method"]
            if method not in METHODS:
                raise UserError("Unknown revision method.")
            if path == "/api/original":
                job = start_job("data", "original", "Loading original plan", job_original, data, name)
            elif path == "/api/revised":
                job = start_job("data", "revised", f"Checking {METHODS[method].lower()}", job_revised, data, name, None, method)
            elif path == "/api/sheet":  # re-read the last upload of a slot from a different sheet
                with lock:
                    up = state["orig_upload" if q.get("slot") == "original" else "rev_upload"]
                if not up:
                    raise UserError("Upload the file again to choose a sheet.")
                if q.get("slot") == "original":
                    job = start_job("data", "original", "Loading original plan", job_original, up[0], up[1], q.get("sheet"))
                else:
                    job = start_job("data", "revised", f"Checking {METHODS[up[3]].lower()}", job_revised, up[0], up[1], q.get("sheet"), up[3])
            elif path == "/api/original/dismiss":  # hide a failed-upload notice
                with lock:
                    state.update(orig_failed=None, orig_upload=None)
                return self._send(200, {"ok": True})
            elif path in ("/api/revised/clear", "/api/method"):  # switching method drops the other method's file
                with jobs_lock:
                    if any(j.group == "data" and j.status == "running" for j in jobs.values()):
                        raise UserError("Please wait for the current step to finish.")
                with lock:
                    if path == "/api/method":
                        state["method"] = method
                    state.update(rev=None, rev_months=[], rev_info=None, rev_report=[], rev_upload=None, rev_source={}, **NO_RESULT)
                return self._send(200, {"ok": True})
            elif path == "/api/locks":   # ?months=Jan'27 P1|Feb'27 P1 - the full set of locked months
                with jobs_lock:
                    if any(j.group == "data" and j.status == "running" for j in jobs.values()):
                        raise UserError("Please wait for the current step to finish.")
                with lock:
                    months = state["months"]
                    want = [m for m in (q.get("months") or "").split("|") if m]
                    bad = [m for m in want if m not in months]
                    if bad:
                        raise UserError(f"Not a month of the original plan: {', '.join(bad)}")
                    locks = _set_locks(months, {m: m in want for m in months})
                    state.update(**NO_RESULT)   # an earlier result was realigned with the old locks
                    rev = state["rev_upload"]
                if rev:   # its checks depend on which months are locked
                    job = start_job("data", "revised", "Re-checking with the new locked months", _check_revised, *rev)
                    return self._send(202, {"job": job.id, "locks": locks})
                return self._send(200, {"ok": True, "locks": locks})
            elif path == "/api/rephase-overrides":   # upload: STORE NAME + REF OLD and/or '<Month> %'
                with lock:
                    o, months = state["orig"], state["months"]
                if o is None:
                    raise UserError("Load the original plan first (step 1).")
                ov, rep = importer.read_rephase_overrides(data, name, o, months)
                if ov is None:
                    raise UserError(f"{name}: {rep.first_error()}")
                saved = {"name": name, "loaded_at": stamp(), "stores": ov}
                _save_json(_tl.ws.path("rephase_overrides.json"), saved)
                with lock:
                    state["rephase_ov"] = saved
                return self._send(200, {"ok": True, "report": rep.items})
            elif path == "/api/rephase-overrides/clear":
                with lock:
                    state["rephase_ov"] = None
                if os.path.exists(_tl.ws.path("rephase_overrides.json")):
                    os.remove(_tl.ws.path("rephase_overrides.json"))
                return self._send(200, {"ok": True})
            elif path == "/api/rephase":   # ?dept=&mix= - re-phase from LY, load it as step 2 and run (Method 2)
                if not q.get("dept"):
                    raise UserError("Pick the department to re-phase first.")
                job = start_job("data", "rephase", f"Re-phasing {q['dept']} from last year", job_rephase,
                                q["dept"], q.get("mix") or None)
            elif path == "/api/run":
                job = start_job("data", "run", f"Realigning · {METHODS[method].lower()}", job_run)
            elif path == "/api/export":
                kind, fmt = q.get("type"), q.get("fmt")
                if kind not in EXPORTS or fmt not in ("xlsx", "csv"):
                    raise UserError("Unknown export.")
                with lock:
                    if f"{kind}-{fmt}" in state["exports"]:
                        return self._send(200, {"ready": True})
                job = start_job(f"export:{kind}:{fmt}", "export", f"Building {EXPORTS[kind].lower()} ({fmt.upper()})",
                                job_export, kind, fmt)
            else:
                return self._send(404, {"error": "not found"})
            return self._send(202, {"job": job.id})
        except UserError as e:
            return self._send(409, {"error": str(e)})


if __name__ == "__main__":
    print(f"Sales Plan Re-Aligner on http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()   # loopback only - via Landing /realigner/
