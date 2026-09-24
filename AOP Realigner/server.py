"""AOP Realigner — takes a revised department plan and pulls it back onto the original AOP.

Target = the original AOP total per Division x Month. Departments the buyer changed
(vs the AOP's own department value) keep their new number; the unchanged departments
absorb the difference pro-rata. Run:  python server.py   ->  http://localhost:8070
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("REALIGNER_PORT", 8070))
HERE = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 25 * 1024 * 1024
ID_COLS = ("division", "department")


def _num(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None  # non-numeric cell (a label column) -> not a value


def normalize(rows):
    """Sheet rows -> ({(div, dept, month): value}, [months in sheet order]).

    Long format: Division, Department, Month, Value.  Wide format: Division, Department,
    then one column per month.  Department may be missing (division-level AOP)."""
    out, months = {}, []
    for r in rows:
        cols = {str(c).strip(): v for c, v in r.items()}
        low = {c.lower(): v for c, v in cols.items()}
        div = str(low.get("division") or "").strip().upper()
        if not div:
            continue
        dept = str(low.get("department") or "").strip().upper()
        if "month" in low:
            cells = [(str(low["month"]).strip(), low.get("value"))]
        else:
            cells = [(c, v) for c, v in cols.items() if c.lower() not in ID_COLS]
        for m, v in cells:
            n = _num(v)
            if n is None or not m or m.startswith("__EMPTY"):
                continue
            if m not in months:
                months.append(m)
            out[(div, dept, m)] = out.get((div, dept, m), 0.0) + n
    return out, months


def realign(aop, plan, overrides=None, tol=0.005):
    """aop/plan: {(div, dept, month): value}. overrides: {"DIV|DEPT|MONTH": bool lock}."""
    overrides = overrides or {}
    has_dept = any(k[1] for k in aop)
    targets = {}
    for (d, _, m), v in aop.items():
        targets[(d, m)] = targets.get((d, m), 0.0) + v

    groups = {}
    for k in set(plan) | (set(aop) if has_dept else set()):
        groups.setdefault((k[0], k[2]), []).append(k)

    rows, summary = [], []
    for (d, m), keys in groups.items():
        cells = []
        for k in keys:
            a = aop.get(k, 0.0) if has_dept else None
            p = plan.get(k, 0.0)
            changed = has_dept and abs(p - a) > tol
            cid = "|".join(k)
            cells.append({"id": cid, "division": d, "department": k[1], "month": m,
                          "aop": a, "plan": p, "changed": changed,
                          "locked": overrides.get(cid, changed)})
        target = targets.get((d, m))
        L = sum(c["plan"] for c in cells if c["locked"])
        U = sum(c["plan"] for c in cells if not c["locked"])
        if target is None:
            for c in cells:
                c["final"], c["status"] = c["plan"], "no-target"
        elif U > tol and L <= target + tol:
            f = (target - L) / U
            for c in cells:
                c["final"], c["status"] = (c["plan"], "kept") if c["locked"] else (c["plan"] * f, "absorbed")
        elif L + U > tol:
            # ponytail: locked changes alone overshoot the AOP (or nothing is free to absorb) —
            # scale every department together; a smarter "shrink only the changes" rule can come later.
            f = target / (L + U)
            for c in cells:
                c["final"], c["status"] = c["plan"] * f, "compressed"
        else:
            for c in cells:
                c["final"], c["status"] = (c["aop"] or 0.0), "no-plan"
        rows += cells
        final = sum(c["final"] for c in cells)
        summary.append({"division": d, "month": m, "aop": target, "plan": L + U, "final": final,
                        "gap": None if target is None else round(final - target, 6),
                        "status": cells[0]["status"] if cells else "no-plan"})
    return rows, summary


def run(payload):
    aop, aop_months = normalize(payload.get("aop") or [])
    plan, plan_months = normalize(payload.get("plan") or [])
    if not aop:
        raise ValueError("Original AOP sheet has no Division/value rows.")
    if not plan:
        raise ValueError("Revised plan sheet has no Division/value rows.")
    months = aop_months + [m for m in plan_months if m not in aop_months]
    rows, summary = realign(aop, plan, payload.get("overrides"))
    mi = {m: i for i, m in enumerate(months)}
    rows.sort(key=lambda r: (r["division"], r["department"], mi[r["month"]]))
    summary.sort(key=lambda s: (s["division"], mi[s["month"]]))
    return {"months": months, "rows": rows, "summary": summary,
            "aop_has_departments": any(k[1] for k in aop)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/realign":
            return self._send(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "Upload too large (25 MB max)."})
        try:
            self._send(200, run(json.loads(self.rfile.read(n) or b"{}")))
        except (ValueError, TypeError, AttributeError) as e:
            self._send(400, {"error": str(e)})


if __name__ == "__main__":
    print(f"AOP Realigner on http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
