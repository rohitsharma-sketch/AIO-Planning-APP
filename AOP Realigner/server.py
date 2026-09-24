"""AOP Realigner - pull a revised department plan back onto the original plan.

Original plan: Store x Department x MRP x Display Type rows, "<Month> Plan" value + "<Month> Plan Qty".
Revised plan:  Store x Department rows, "<Month> New" values (only the departments the buyer changed).

Per Store x Division x Attribute x Month the original total is the target. Revised departments keep
their new value exactly (split to MRP x Display Type by the original cont %); every other department
in that bucket absorbs the difference pro-rata. Jan/Feb are never touched.
Run: python server.py -> http://localhost:8070
"""
import io
import json
import os
import pickle
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pandas as pd

PORT = int(os.environ.get("REALIGNER_PORT", 8070))
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache", "original.pkl")  # gitignored: real plan data
MAX_BODY = 400 * 1024 * 1024
TOL = 1e-9
STORE, DIV, DEPT, MRP, DISP, ATTR = "Store Name", "DIVISION", "DEPARTMENT", "MRP", "DISPLAY TYPE", "ATTRIBUTE"
FROZEN = ("Jan", "Feb")  # user rule: Jan & Feb plans stay exactly as the original

state = {"orig": None, "months": None, "meta": None, "out": None}


def read_sheet(data, header_marker):
    """First sheet; header = first row containing header_marker (the original has a totals row on top)."""
    raw = pd.read_excel(io.BytesIO(data), header=None, engine="calamine")
    hits = [i for i in range(min(10, len(raw)))
            if header_marker in raw.iloc[i].astype(str).str.strip().str.upper().tolist()]
    if not hits:
        raise ValueError(f"Could not find a '{header_marker}' header in the first 10 rows.")
    df = raw.iloc[hits[0] + 1:].reset_index(drop=True)
    df.columns = [str(c).strip() for c in raw.iloc[hits[0]]]
    return df


def load_original(data):
    o = read_sheet(data, "STORE NAME")
    months = [c[:-5] for c in o.columns if c.endswith(" Plan")]
    num = [m + " Plan" for m in months] + [m + " Plan Qty" for m in months]
    missing = [c for c in [STORE, DIV, DEPT, MRP, DISP, ATTR] + num if c not in o.columns]
    if missing or not months:
        raise ValueError(f"Original plan is missing columns: {missing or '<Month> Plan'}")
    for c in num:
        o[c] = pd.to_numeric(o[c], errors="coerce").fillna(0.0)
    for c in (STORE, DIV, DEPT, DISP, ATTR):
        o[c] = o[c].astype(str).str.strip()
    if o.duplicated([STORE, DEPT, MRP, DISP]).any():
        raise ValueError("Original plan has duplicate Store x Department x MRP x Display Type rows.")
    return o, months


def load_revised(data, months):
    r = read_sheet(data, "DEPARTMENT")
    r.columns = [{"STORE NAME": STORE, "DEPARTMENT": DEPT}.get(c.upper(), c) for c in r.columns]
    cols = [m for m in months if m + " New" in r.columns]
    if STORE not in r.columns or DEPT not in r.columns or not cols:
        raise ValueError("Revised plan needs STORE NAME, DEPARTMENT and '<Month> New' columns matching the original months.")
    r = r.rename(columns={m + " New": m for m in cols})
    for c in (STORE, DEPT):
        r[c] = r[c].astype(str).str.strip()
    for m in cols:
        r[m] = pd.to_numeric(r[m], errors="coerce").fillna(0.0)
    if r.duplicated([STORE, DEPT]).any():
        raise ValueError("Revised plan has duplicate Store x Department rows.")
    return r[[STORE, DEPT] + cols], cols


def add_new_departments(o, r, months):
    """A revised dept a store never had (e.g. LW_U_T-TOP F/S) gets rows cloned from the longest original
    dept name it starts with in that store (LW_U_T-TOP): same MRP/display rows, zero original value.
    `_basis` = row whose values give the MRP/display mix and ASP (itself, or the parent row for a clone)."""
    o = o.reset_index(drop=True)
    o["_basis"] = np.arange(len(o))
    have = set(zip(o[STORE], o[DEPT]))
    by_store = dict(tuple(o.groupby(STORE)))
    clones, unmatched = [], []
    for s, d in zip(r[STORE], r[DEPT]):
        if (s, d) in have:
            continue
        g = by_store.get(s)
        parent = next((p for p in sorted(set(g[DEPT]), key=len, reverse=True) if d.startswith(p)), None) if g is not None else None
        if parent is None:
            unmatched.append(f"{s} / {d}")
            continue
        c = g[g[DEPT] == parent].copy()
        c[DEPT] = d
        c[[m + " Plan" for m in months] + [m + " Plan Qty" for m in months]] = 0.0
        if "CONC - UDF" in c:
            c["CONC - UDF"] = c[STORE] + d + c[MRP].astype(str) + c[DISP]
        if "CONC - MRP" in c:
            c["CONC - MRP"] = c[STORE] + d + c[MRP].astype(str)
        if "Tag" in c:
            c["Tag"] = "New Dept"
        clones.append(c)
    if unmatched:
        raise ValueError("Revised departments with no original department to borrow MRP/display rows from: "
                         + ", ".join(unmatched[:10]) + (" ..." if len(unmatched) > 10 else ""))
    n = sum(len(c) for c in clones)
    return (pd.concat([o, *clones], ignore_index=True) if clones else o), len(clones), n


def realign(o, r, months):
    """o: original rows (numeric cols clean), r: revised Store x Dept values over `months`.
    Returns (realigned rows in original layout, division x month summary, warnings)."""
    V = [m + " Plan" for m in months]
    Q = [m + " Plan Qty" for m in months]
    o, n_new_sd, n_new_rows = add_new_departments(o, r, months)
    b = o.pop("_basis").to_numpy()
    orig, qty = o[V].to_numpy(float), o[Q].to_numpy(float)
    basis = orig[b]

    keys = pd.MultiIndex.from_arrays([o[STORE], o[DEPT]])
    rev = r.set_index([STORE, DEPT]).reindex(columns=months)
    locked = keys.isin(rev.index)
    R = np.nan_to_num(rev.reindex(keys).to_numpy(float))
    frozen = np.array([m[:3] in FROZEN for m in months])
    # a month absent from the revised file, or a frozen month (Jan/Feb), is never touched
    lk = locked[:, None] & rev.notna().any().to_numpy()[None, :] & ~frozen[None, :]

    # 1. split revised Store x Dept value to MRP x Display rows by that month's original cont %;
    #    a month where the dept had no plan uses the row's average cont % across the months it did have
    sd = (o[STORE] + "||" + o[DEPT]).to_numpy()
    gsum = pd.DataFrame(basis).groupby(sd).transform("sum").to_numpy()
    has = np.abs(gsum) > TOL
    share = np.where(has, basis / np.where(has, gsum, 1), np.nan)
    avg = np.nan_to_num(np.nanmean(np.where(has.any(1, keepdims=True), share, 0.0), axis=1))
    cnt = pd.Series(avg).groupby(sd).transform("size").to_numpy()
    avg = np.where(has.any(1), avg, 1.0 / cnt)  # dept never planned in this store -> equal split
    mix = np.where(has, share, avg[:, None])
    new = np.where(lk, R * mix, orig)
    fb_cells = int((lk & ~has & (np.abs(R) > TOL)).sum())
    ignored = int((locked[:, None] & frozen[None, :] & (np.abs(R - pd.DataFrame(orig).groupby(sd).transform("sum").to_numpy()) > 1e-6)).any(1).sum())

    # 2. unlocked rows in each Store x Division x Attribute x Month absorb the difference pro-rata
    o[ATTR] = o[ATTR].astype(str).str.strip()
    grp = (o[STORE] + "||" + o[DIV] + "||" + o[ATTR]).to_numpy()
    T = pd.DataFrame(orig).groupby(grp).transform("sum").to_numpy()
    L = pd.DataFrame(np.where(lk, new, 0.0)).groupby(grp).transform("sum").to_numpy()
    U = pd.DataFrame(np.where(lk, 0.0, orig)).groupby(grp).transform("sum").to_numpy()
    ok = (np.abs(U) > TOL) & (T - L >= -TOL)
    # ponytail: revised depts alone overshoot (or nothing left to absorb) -> other depts 0, total stays over; flagged
    f = np.where(ok, (T - L) / np.where(ok, U, 1), 0.0)
    new = np.where(lk, new, orig * f)

    # 3. qty follows value at the row's ASP (a clone uses its parent's ASP; no qty history -> MRP)
    vs, qs = orig.sum(1)[b], qty.sum(1)[b]
    asp = np.divide(vs, qs, out=np.zeros(len(o)), where=np.abs(qs) > TOL)
    asp = np.where(asp > TOL, asp, pd.to_numeric(o[MRP], errors="coerce").fillna(0).to_numpy() / 1e5)
    has_o = np.abs(orig) > TOL
    new_qty = np.where(has_o, qty * np.divide(new, orig, out=np.zeros_like(new), where=has_o),
                       np.divide(new, asp[:, None], out=np.zeros_like(new), where=asp[:, None] > TOL))
    o[V], o[Q] = new, new_qty

    summ = []
    for d, g in o.groupby(DIV):
        i = g.index.to_numpy()
        for j, m in enumerate(months):
            summ.append({"division": d, "month": m, "original": float(orig[i, j].sum()), "final": float(new[i, j].sum()),
                         "revised_before": float(orig[i, j][locked[i]].sum()), "revised_after": float(new[i, j][locked[i]].sum())})
    miss = (~ok & (np.abs(T - L) > 1e-6)).any(1)  # group couldn't land on its original total
    over = sorted({f"{s}/{d}/{a}" for s, d, a in zip(o[STORE][miss], o[DIV][miss], o[ATTR][miss])})
    warn = []
    if n_new_sd:
        warn.append(f"{n_new_sd} new store-departments created ({n_new_rows} MRP/display rows) from their parent department's rows.")
    if fb_cells:
        warn.append(f"{fb_cells} revised row-months had no original plan that month; split by the row's average cont % across the other months.")
    if ignored:
        warn.append(f"{ignored} revised rows had Jan/Feb values different from the original - ignored, Jan/Feb stay as original.")
    if over:
        warn.append(f"{len(over)} store-division-attribute bucket(s) can't land on the original total in some month (revised departments alone "
                    f"exceed it, or no other department to absorb) - revised values kept as given: {', '.join(over[:15])}")
    return o, summ, warn


def export(df, fmt):
    """csv ~3s; xlsx ~2.5 min for the full 680k-row plan, so it's built only when asked."""
    if fmt == "csv":
        return df.round(6).to_csv(index=False).encode("utf-8-sig"), "text/csv", "csv"
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="xlsxwriter")
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"


def set_original(o, months, name):
    state.update(orig=o, months=months, meta={"name": name, "rows": len(o), "months": months,
                                               "loaded_at": time.strftime("%Y-%m-%d %H:%M")})
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "wb") as fh:
        pickle.dump((o, months, state["meta"]), fh)


if os.path.exists(CACHE):
    with open(CACHE, "rb") as fh:
        state["orig"], state["months"], state["meta"] = pickle.load(fh)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if p == "/api/original":
            return self._send(200, state["meta"] or {})
        if p == "/api/download" and state["out"] is not None:
            data, ctype, ext = export(state["out"], "xlsx" if "fmt=xlsx" in self.path else "csv")
            return self._send(200, data, ctype, {"Content-Disposition": f'attachment; filename="Realigned Plan.{ext}"'})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._send(413, {"error": "File too large (400 MB max)."})
        data = self.rfile.read(n)
        name = self.headers.get("X-File-Name", "upload.xlsx")
        try:
            if self.path == "/api/original":
                set_original(*load_original(data), name)
                return self._send(200, state["meta"])
            if self.path == "/api/realign":
                if state["orig"] is None:
                    raise ValueError("Upload the original plan first.")
                r, _ = load_revised(data, state["months"])
                out, summ, warn = realign(state["orig"], r, state["months"])
                state["out"] = out
                return self._send(200, {"summary": summ, "warnings": warn, "rows": len(out),
                                        "revised_departments": sorted(r[DEPT].unique().tolist())})
            self._send(404, {"error": "not found"})
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # bad/unsupported workbook -> tell the user, don't drop the connection
            self._send(400, {"error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    print(f"AOP Realigner on http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
