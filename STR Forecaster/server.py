"""STR Forecaster - forecast sell-thru per store x department x month from the fixture plan (fixtures x qty per fixture
= minimum display stock, MDQ) and the sales plan (Rs -> qty at LY selling price): STR = qty / (qty + MDQ).
Engine: str_engine.py; data: planning_inputs.str_* (Postgres). Uploads and edits need an admin or a planner.
Run: python server.py  ->  http://127.0.0.1:8085  (on Landing: /str/)."""
import io
import json
import os
import threading
import time
import traceback
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd

import str_engine as se

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8085
AUTH_ME = "http://127.0.0.1:8010/api/auth/me"
MAX_BODY = 200 * 1024 * 1024
state = {"df": None, "info": None, "dirty": True, "job": None}
lock = threading.Lock()          # guards state
build_lock = threading.Lock()    # one rebuild at a time
_who = {}


def _stamp():
    return time.strftime("%d %b %H:%M:%S")


def who(cookie):
    """the signed-in RS Planning user (Landing forwards the session cookie), cached a minute; None if not signed in"""
    if not cookie:
        return None
    hit = _who.get(cookie)
    if hit and time.time() - hit[1] < 60:
        return hit[0]
    me = None
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(urllib.request.Request(AUTH_ME, headers={"Cookie": cookie}), timeout=5) as r:
            me = json.load(r)
    except Exception:  # noqa: BLE001 - 401 / platform down
        me = None
    if me:
        if len(_who) > 500:
            _who.clear()
        _who[cookie] = (me, time.time())
    return me


def can_edit(me):
    return bool(me and (me.get("is_admin") or me.get("role") in ("admin", "planner")))


def frame():
    """the computed frame, rebuilt after any upload / edit / rollback - here or from any other process (version stamp)"""
    with build_lock:
        ver = se.version()
        with lock:
            if not state["dirty"] and state.get("ver") == ver:
                return state["df"], state["info"]
        df, info = se.build()
        with lock:
            state.update(df=df, info=info, dirty=False, ver=ver)
        return df, info


def _dirty():
    with lock:
        state["dirty"] = True


def _num(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 6)


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return _num(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return o


def _tag_cols(rows):
    """department rows get their Core / Seasonal tag and attribute (own, else the suite attribute master)"""
    t, master = se.tags()
    for r in rows:
        own = t.get(str(r["department"]).upper(), {})
        r["tag"] = own.get("tag")
        r["attribute"] = own.get("attribute") or master.get(str(r["department"]).upper())
        r["attribute_from"] = "tag master" if own.get("attribute") else "attribute master" if r["attribute"] else ""
    return rows


def _filter(df, q):
    for k in ("division", "cluster", "department", "store"):
        v = q.get(k, [""])[0]
        if v:
            df = df[df[k] == v]
    return df


def _job(kind, data, name, user, shift=None):
    try:
        with lock:
            state["job"]["step"] = "Reading the file"
        g, notes = se.read_fixture(data) if kind == "fixture" else se.read_sales_plan(data, name)
        shift = se.default_shift(list(g.month.unique())) if shift is None else shift
        with lock:
            state["job"]["step"] = f"Saving {len(g):,} rows"
        uid = se.save_upload(kind, name, g, shift, user)
        _dirty()
        with lock:
            state["job"].update(status="done", step="Done", ended=_stamp(), upload_id=uid, notes=notes,
                                shift=shift, rows=int(len(g)))
    except Exception as e:  # noqa: BLE001 - shown on the page
        traceback.print_exc()
        with lock:
            state["job"].update(status="error", error=str(e) or e.__class__.__name__, ended=_stamp())


def _safe(v):
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def workbook(df, months, has_plan):
    out = io.BytesIO()
    cols = ["division", "department", "cluster", "store", "month", "fixtures_file", "fixtures", "density", "mdq", "plan_rs", "asp",
            "asp_from", "plan_qty", "ly_q", "mdq_base", "edited"]
    d = df[cols].copy()
    d["month"] = d.month.astype(str)
    for c in ("store", "department", "division", "cluster"):
        d[c] = d[c].map(_safe)
    ok = (d.mdq > 0) & (d.plan_qty > 0)
    dim = df.month.map(lambda m: m.days_in_month).astype(float)
    dly = df.month.map(lambda m: (m - 12).days_in_month).astype(float)
    lyok = df.ly_known & (df.ly_q > 0)
    d["days of cover (plan)"] = np.where(ok, d.mdq / (d.plan_qty.where(d.plan_qty > 0) / dim), np.nan) if has_plan else np.nan
    d["LY days of cover"] = np.where(lyok, d.mdq_base / (d.ly_q.where(d.ly_q > 0) / dly), np.nan)
    d["season index"] = df.season_idx
    d["season"] = df.season_idx.map(se.season_of)
    d["STR band (days)"] = [se.str_band(x, sea) for x, sea in zip(d["days of cover (plan)"], d["season"])]
    d["base band (60-180)"] = d["days of cover (plan)"].map(se.str_band)
    d["max STR at MDQ"] = np.where(ok, se.str_of(d.plan_qty, d.mdq), np.nan) if has_plan else np.nan
    d["LY STR (same formula)"] = np.where(lyok, se.str_of(d.ly_q, d.mdq_base), np.nan)
    d = d.rename(columns={"fixtures_file": "fixtures (file)", "density": "qty per fixture", "mdq": "MDQ", "plan_rs": "plan (Rs)",
                          "asp": "LY avg selling price", "asp_from": "price from", "plan_qty": "plan qty", "ly_q": "LY qty",
                          "mdq_base": "MDQ (file)"})
    tg = {r["department"]: r for r in _tag_cols([{"department": x} for x in df.department.unique()])}
    d.insert(2, "tag", df.department.map(lambda x: tg[x]["tag"]))
    d.insert(3, "attribute", df.department.map(lambda x: tg[x]["attribute"]))
    # xlsxwriter (installed): ~1.7M cells far faster than openpyxl (~45 s); text is never read as a formula
    with pd.ExcelWriter(out, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_formulas": False}}) as xw:
        d.sort_values(["division", "department", "store", "month"]).to_excel(xw, sheet_name="STR detail", index=False)
        for by, nm in ((["division"], "By division"), (["division", "department"], "By department"),
                        (["cluster"], "By cluster"), (["cluster", "store"], "By store")):
            rows = []
            for r in se.rollup(df, by, months, has_plan):
                base = {k: r[k] for k in by}
                if "department" in by:
                    base.update(tag=tg[r["department"]]["tag"], attribute=tg[r["department"]]["attribute"])
                for m, c in zip(months, r["months"]):
                    rows.append({**base, "month": str(m), "plan qty": c["qty"], "MDQ": c["mdq"], "season": c["season"], "STR band": c["band"],
                                 "base band": c["base_band"], "days of cover": c["days"],
                                 "LY days of cover": c["ly_days"], "max STR at MDQ": c["str"], "LY STR": c["ly_str"]})
                rows.append({**base, "month": "4-month avg", "plan qty": r["total"]["qty"], "MDQ": r["total"]["mdq"],
                             "season": r["total"]["season"], "STR band": r["total"]["band"], "base band": r["total"]["base_band"], "days of cover": r["total"]["days"], "LY days of cover": r["total"]["ly_days"],
                             "max STR at MDQ": r["total"]["str"], "LY STR": r["total"]["ly_str"]})
            out_df = pd.DataFrame(rows)
            for k in by:
                out_df[k] = out_df[k].map(_safe)
            out_df.to_excel(xw, sheet_name=nm, index=False)
    return out.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        data = json.dumps(_clean(body)).encode() if ctype == "application/json" else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        path = u.path.rstrip("/") or "/"
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as fh:
                    return self._send(200, fh.read(), "text/html; charset=utf-8")
            if path == "/api/state":
                me = who(self.headers.get("Cookie"))
                df, info = frame()
                with lock:
                    job = dict(state["job"]) if state["job"] else None
                return self._send(200, {"info": info, "job": job, "can_edit": can_edit(me), "user": (me or {}).get("username")})
            df, info = frame()
            if df is None:
                return self._send(400, {"error": "Upload the fixture plan first."})
            months = sorted(df.month.unique())
            if path == "/api/rollup":
                by = {"division": ["division"], "department": ["division", "department"], "cluster": ["cluster"],
                      "store": ["cluster", "store"]}.get(q.get("by", ["division"])[0], ["division"])
                d, hp = _filter(df, q), bool(info.get("sales_plan"))
                rows = se.rollup(d, by, months, hp)
                if "department" in by:
                    _tag_cols(rows)
                return self._send(200, {"months": [str(m) for m in months], "rows": rows, "by": by, "has_plan": hp})
            if path == "/api/cells":
                dept = q.get("department", [""])[0]
                d = df[df.department == dept]
                if d.empty:
                    return self._send(404, {"error": "No such department in the fixture plan."})
                mi = {m: i for i, m in enumerate(months)}
                by_store = {}
                for r in d.itertuples():
                    if r.month not in mi:
                        continue
                    dim, ldim = r.month.days_in_month, (r.month - 12).days_in_month
                    c = {"fixtures": r.fixtures, "fixtures_file": r.fixtures_file, "density": r.density, "mdq": r.mdq,
                         "mdq_base": r.mdq_base, "plan_rs": r.plan_rs, "plan_qty": r.plan_qty, "qty_from": r.qty_from,
                         "asp": r.asp, "asp_from": r.asp_from, "ly_q": r.ly_q, "n_days": dim, "ly_n_days": ldim,
                         "str": float(se.str_of(r.plan_qty, r.mdq)) if info.get("sales_plan") and r.mdq > 0 and r.plan_qty > 0 else None,
                         "ly_str": float(se.str_of(r.ly_q, r.mdq_base)) if r.ly_known and r.ly_q > 0 else None,
                         "days": se.days_of(r.plan_qty, r.mdq, dim) if info.get("sales_plan") and r.mdq > 0 else None,
                         "ly_days": se.days_of(r.ly_q, r.mdq_base, ldim) if r.ly_known else None, "edited": r.edited}
                    sea = se.season_of(r.season_idx)
                    c.update(season=sea, season_idx=r.season_idx, band=se.str_band(c["days"], sea), base_band=se.str_band(c["days"]))
                    by_store.setdefault(r.store, [None] * len(months))[mi[r.month]] = c
                cl = dict(zip(d.store, d.cluster))
                rows = [{"store": st, "cluster": cl.get(st), "months": by_store[st]} for st in sorted(by_store)]
                dens = d.drop_duplicates("store").density
                return self._send(200, {"department": dept, "division": d.division.iloc[0], "months": [str(m) for m in months],
                                        "density": float(dens.median()) if len(dens) else None,
                                        "density_edited": bool(d.edited.str.contains("qty per fixture").any()), "rows": rows})
            if path == "/api/tags":
                t, master = se.tags()
                g = df.groupby(["division", "department"], as_index=False)[["mdq", "plan_rs"]].sum()
                rows = []
                for r in g.itertuples():
                    own = t.get(str(r.department).upper(), {})
                    rows.append({"division": r.division, "department": r.department, "mdq": r.mdq, "plan_rs": r.plan_rs,
                                 "tag": own.get("tag"), "attribute": own.get("attribute"),
                                 "attribute_master": master.get(str(r.department).upper()), "source": own.get("source"),
                                 "updated_by": own.get("updated_by"), "updated_at": own.get("updated_at")})
                return self._send(200, {"rows": rows, "attributes": sorted(set(master.values()) | {v["attribute"] for v in t.values() if v.get("attribute")}),
                                        "not_in_plan": sorted(set(t) - {str(x).upper() for x in g.department})})
            if path == "/api/tags/download":
                t, master = se.tags()
                g = df.drop_duplicates(["division", "department"])[["division", "department"]].sort_values(["division", "department"])
                known = {str(x).upper() for x in g.department}
                rows = [{"DIVISION": r.division, "DEPARTMENT": r.department,
                         "CORE / SEASONAL": se.TAG_LABEL.get(t.get(str(r.department).upper(), {}).get("tag"), ""),
                         "ATTRIBUTE": t.get(str(r.department).upper(), {}).get("attribute") or "",
                         "SUITE ATTRIBUTE MASTER (info)": master.get(str(r.department).upper(), "")} for r in g.itertuples()]
                rows += [{"DIVISION": "", "DEPARTMENT": k, "CORE / SEASONAL": se.TAG_LABEL.get(v.get("tag"), ""),
                          "ATTRIBUTE": v.get("attribute") or "", "SUITE ATTRIBUTE MASTER (info)": master.get(k, "")}
                         for k, v in sorted(t.items()) if k not in known]   # tagged, not in this fixture plan
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_formulas": False}}) as xw:
                    pd.DataFrame(rows).to_excel(xw, sheet_name="Department tags", index=False)
                    pd.DataFrame({"How to use": [
                        "Fill CORE / SEASONAL with Core or Seasonal and ATTRIBUTE with the attribute, then upload this file on the Department tags tab.",
                        "A blank cell keeps the value already saved; clear a value in the app.",
                        "SUITE ATTRIBUTE MASTER (info) is the suite's attribute master - shown when ATTRIBUTE is blank; it is not read on upload."]}
                    ).to_excel(xw, sheet_name="Read me", index=False)
                name = f"STR Department tags - {time.strftime('%d.%m.%y')}.xlsx"
                return self._send(200, out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            if path == "/api/download":
                name = f"STR Forecast - {time.strftime('%d.%m.%y')}.xlsx"
                return self._send(200, workbook(_filter(df, q), months, bool(info.get("sales_plan"))),
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._send(404, {"error": "Not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/")
        me = who(self.headers.get("Cookie"))
        if not can_edit(me):
            return self._send(403, {"error": "Only an admin or a planner can change the STR inputs."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            return self._send(400, {"error": "Bad Content-Length."})
        if n > MAX_BODY:
            return self._send(413, {"error": "File too large (200 MB max)."})
        data = self.rfile.read(n) if n else b""
        user = me.get("username")
        try:
            if path == "/api/upload":
                qs = urllib.parse.parse_qs(u.query)
                kind = qs.get("kind", ["fixture"])[0]
                shift = qs.get("shift", [None])[0]
                if shift not in (None, "0", "12"):
                    return self._send(400, {"error": "shift must be 0 or 12"})
                if kind == "tags":   # a small master: read and saved at once
                    if not data:
                        return self._send(400, {"error": "No file received."})
                    f, notes = se.read_tags(data)
                    n_ = se.save_tags(f, user, "upload: " + urllib.parse.unquote(self.headers.get("X-File-Name", "tags.xlsx")))
                    return self._send(200, {"ok": True, "rows": n_, "notes": notes})
                if kind not in ("fixture", "sales_plan"):
                    return self._send(400, {"error": "kind must be fixture or sales_plan"})
                if not data:
                    return self._send(400, {"error": "No file received."})
                name = urllib.parse.unquote(self.headers.get("X-File-Name", "upload.xlsx"))
                with lock:
                    if state["job"] and state["job"]["status"] == "running":
                        return self._send(409, {"error": "An upload is already running - wait for it to finish."})
                    state["job"] = {"status": "running", "step": "Starting", "kind": kind, "name": name, "started": _stamp(), "error": None}
                threading.Thread(target=_job, args=(kind, data, name, user, None if shift is None else int(shift)), daemon=True).start()
                return self._send(202, {"ok": True})
            body = json.loads(data or b"{}")
            if path == "/api/edit":
                se.add_edit(body.get("field"), str(body.get("department") or ""), body.get("value"), user,
                            month=(body.get("month") + "-01") if body.get("month") else None, store=body.get("store") or None)
                _dirty()
                return self._send(200, {"ok": True})
            if path == "/api/tags":
                dep = str(body.get("department") or "").strip()
                if not dep:
                    return self._send(400, {"error": "department is required"})
                tag = (body.get("tag") or "").strip().upper() or None
                if tag not in (None,) + se.TAGS:
                    return self._send(400, {"error": "tag must be Core or Seasonal"})
                att = (body.get("attribute") or "").strip().upper()[:60] or None
                se.save_tags(pd.DataFrame([{"department": dep, "tag": tag, "attribute": att}]), user, "edit")
                return self._send(200, {"ok": True})
            if path == "/api/reset":
                n_ = se.reset_department(str(body.get("department") or ""), user)
                _dirty()
                return self._send(200, {"ok": True, "reset": n_})
            if path == "/api/rollback":
                u_ = se.rollback(body.get("kind"))
                _dirty()
                return self._send(200, {"ok": True, "rolled_back": u_})
            return self._send(404, {"error": "Not found"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": str(e)})


def _season_watch():
    """cluster season curves (str_season.py) rebuilt when the Listing day-wise cache or the AOP store master is newer -
    checked hourly; the version stamp then rebuilds the frame"""
    import str_season
    while True:
        try:
            if str_season.stale():
                str_season.build()
        except Exception:  # noqa: BLE001 - keep serving with the curves we have
            traceback.print_exc()
        time.sleep(3600)


def main():
    print(f"STR Forecaster on http://127.0.0.1:{PORT}")
    threading.Thread(target=lambda: frame(), daemon=True).start()   # warm the frame so the first page load is quick
    threading.Thread(target=_season_watch, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
