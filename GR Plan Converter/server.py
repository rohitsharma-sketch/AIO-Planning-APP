"""Growth vs LY - upload the final sales plan, get it against last year by the plan's hierarchy (Division -> Attribute
-> Department), on screen and as the GR % PLAN workbook (MAIN + PIVOT). LY comes from the data lake (gr_engine).
Run: python server.py  ->  http://127.0.0.1:8075  (on Landing: /growth/)."""
import json
import os
import pickle
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "AOP Realigner"))   # the suite's plan reader (xlsx / xlsb / csv, any header row)
import engine as ra_engine  # noqa: E402
import importer  # noqa: E402
import numpy as np  # noqa: E402

import gr_engine as ge  # noqa: E402

PORT = 8075
CACHE = os.path.join(HERE, ".cache")
LAST = os.path.join(CACHE, "last.pkl")
MAX_BODY = 400 * 1024 * 1024
# ponytail: one shared result for everyone (last plan built wins) - per-user workspaces if several planners use it at once
state = {"plan": None, "months": [], "ly": None, "main": None, "job": None}
lock = threading.Lock()


def _stamp():
    return time.strftime("%d %b %H:%M:%S")


def _job(data, name):
    def step(s):
        with lock:
            state["job"]["step"] = s
    try:
        step("Reading the plan")
        df, info, rep = importer.read_table(data, name, importer.NEED_ORIGINAL, "final sales plan")
        months = []
        if df is not None:
            step("Checking columns")
            df, months, info, rep = importer.prepare_original(df, info, rep)
        if not rep.ok:
            raise ValueError(" ".join(i["msg"] for i in rep.items if i["level"] == "error"))
        step("Loading last year from the data lake (first time ~2 min, then cached)")
        ly, ly_info = ge.load_ly(months, CACHE)
        step("Building growth vs LY")
        main = ge.build_main(df, months, ly)
        plan = {"name": name, "loaded_at": _stamp(), "rows": int(len(df)), "stores": int(df[ge.STORE].nunique()),
                "departments": int(df[ge.DEPT].nunique()), "notes": [i["msg"] for i in rep.items if i["level"] == "warning"][:5]}
        with lock:
            state.update(plan=plan, months=months, ly=ly_info, main=main)
            state["job"].update(status="done", step="Done", ended=_stamp())
        os.makedirs(CACHE, exist_ok=True)
        with open(LAST + ".tmp", "wb") as fh:
            pickle.dump({k: state[k] for k in ("plan", "months", "ly", "main")}, fh)
        os.replace(LAST + ".tmp", LAST)
    except Exception as e:  # noqa: BLE001 - shown on the page
        traceback.print_exc()
        with lock:
            state["job"].update(status="error", error=str(e) or e.__class__.__name__, ended=_stamp())


def _tags(q):
    t = q.get("tags", [None])[0]
    return [x for x in t.split("|") if x] if t else None


def _num(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 6)


def pivot_json(tags):
    months = state["months"]
    p = ge.pivot(state["main"], months, tags)
    lm = [ge.ly_label(m) for m in months]
    bl = [b for b, _ in ge.blocks(months)]
    rows = []
    for r in p.to_dict("records"):
        rows.append({"level": r["Level"], "div": r["Division"], "attr": r["ATTRIBUTE"], "dept": r["DEPARTMENT"],
                     "ty": [_num(r[m]) for m in months], "ly": [_num(r[m]) for m in lm],
                     "blocks": {b: [_num(r[f"TTL {b} Val TY"]), _num(r[f"TTL {b} Val LY"]), _num(r[f"{b} Growth %"])] for b in bl},
                     "ttl": [_num(r["TTL Val TY"]), _num(r["TTL Val LY"]), _num(r["TTL Growth %"])]})
    return {"months": months, "ly_months": lm, "blocks": bl, "rows": rows}


def workbook(tags):
    months, main = state["months"], state["main"]
    label = "PIVOT " + ("+".join(tags) if tags else "ALL")
    sheets = [("MAIN", main), (label[:31], ge.pivot(main, months, tags))]
    if tags:
        sheets.append(("PIVOT ALL", ge.pivot(main, months, None)))
    return ra_engine.write_xlsx(sheets)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        data = json.dumps(body).encode() if ctype == "application/json" else body
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
                with lock:
                    main = state["main"]
                    tags = main["SSG TAG"].replace("", "(blank)").value_counts().to_dict() if main is not None else {}
                    return self._send(200, {"job": state["job"], "plan": state["plan"], "ly": state["ly"], "months": state["months"],
                                            "blocks": [b for b, _ in ge.blocks(state["months"])] if state["months"] else [],
                                            "tags": {str(k): int(v) for k, v in tags.items()}})
            if path in ("/api/pivot", "/api/download"):
                with lock:
                    if state["main"] is None:
                        return self._send(400, {"error": "Upload the final sales plan first."})
                    if path == "/api/pivot":
                        return self._send(200, pivot_json(_tags(q)))
                    data, name = workbook(_tags(q)), f"GR % PLAN - {time.strftime('%d.%m.%y')}.xlsx"
                return self._send(200, data, ra_engine.XLSX_CTYPE, {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._send(404, {"error": "Not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "File too large (400 MB max)."})
        data = self.rfile.read(n) if n else b""
        if path != "/api/plan":
            return self._send(404, {"error": "Not found"})
        if not data:
            return self._send(400, {"error": "No file received."})
        with lock:
            if state["job"] and state["job"]["status"] == "running":
                return self._send(409, {"error": "A plan is already being built - wait for it to finish."})
            name = urllib.parse.unquote(self.headers.get("X-File-Name", "plan.xlsx"))
            state["job"] = {"status": "running", "step": "Starting", "name": name, "started": _stamp(), "error": None}
        threading.Thread(target=_job, args=(data, name), daemon=True).start()
        return self._send(202, {"ok": True})


def main():
    if os.path.exists(LAST):   # the last plan built survives a restart
        try:
            with open(LAST, "rb") as fh:
                state.update(pickle.load(fh))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    print(f"Growth vs LY on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
