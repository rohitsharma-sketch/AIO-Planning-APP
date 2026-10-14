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
        df, info, art, disp = se.build(articles=True)
        with lock:
            state.update(df=df, info=info, art=art, disp=disp, af=None, dfd=None, dirty=False, ver=ver)
        return df, info


def display_df():
    """the frame split to display types (TABLE / NON_TABLE; built on first use, kept until the next rebuild)"""
    frame()
    with lock:
        if state.get("dfd") is None:
            state["dfd"] = se.display_frame(state["df"], *state["disp"])
        return state["dfd"]


def article_df():
    """the display-type frame split to articles by their cont % of the sales plan (built on first use)"""
    dfd = display_df()
    with lock:
        if state.get("af") is None:
            state["af"] = se.article_frame(dfd, state["art"])
        return state["af"]


def _base(df, q, keys=()):
    """the frame a request needs: split to articles / display types when one is a layer or a filter; tags added when used"""
    d = (article_df() if "article" in keys or q.get("article") else
         display_df() if "display" in keys or q.get("display") else df)
    return _with_tags(d) if any(k in keys or q.get(k) for k in TAG_KEYS) else d


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
        if "tag" not in r:   # a Tag / Attribute layer already grouped the row - keep its value (it is the row's path)
            r["tag"] = own.get("tag")
        if "attribute" not in r:
            r["attribute"] = own.get("attribute") or master.get(str(r["department"]).upper())
        r["attribute_from"] = "tag master" if own.get("attribute") else "attribute master" if master.get(str(r["department"]).upper()) else ""
    return rows


TAG_KEYS = ("tag", "attribute")


def _with_tags(df):
    """Tag and Attribute as row layers (user, 9 Oct: "add Tag and Attribute as draggable layers too"): each department's
    Core / Seasonal tag ("(untagged)") and attribute (own, else the suite attribute master; "(no attribute)")"""
    t, master = se.tags()
    deps = df.department.unique()
    own = {d: t.get(str(d).upper(), {}) for d in deps}
    return df.assign(tag=df.department.map({d: own[d].get("tag") or "(untagged)" for d in deps}),
                     attribute=df.department.map({d: own[d].get("attribute") or master.get(str(d).upper()) or "(no attribute)" for d in deps}))


def _filter(df, q):
    for k in ("division", "cluster", "department", "store", "season", "display", "article") + TAG_KEYS:
        v = [x for x in q.get(k, []) if x]   # one or several values (repeated params) - the per-layer search filters
        if v:
            df = df[df[k].isin(v)]
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


LAYER_KEYS = ("division", "department", "cluster", "store", "tag", "attribute", "season", "display", "article")
LAYER_LABEL = {"division": "Division", "department": "Department", "cluster": "Cluster", "store": "Store", "tag": "Tag",
               "attribute": "Attribute", "season": "Season", "display": "Display type", "article": "Article"}


_ADD = ("qty", "mdq", "ly_qty", "ly_mdq", "plan_rs")


def _avg_cell(r):
    """the 4-month figures as the page shows them (user, 2026-10-13: "put the same averages in the excel export too"):
    plan qty, MDQ, LY qty / MDQ, plan Rs and fixtures as the average month (over the months that have one); the store
    count is already the average month; STR %, days and bands are unchanged (they were the average month already)"""
    t = dict(r["total"])
    for f in _ADD:
        v = [c[f] for c in r["months"] if c.get(f)]
        t[f] = sum(v) / len(v) if v else 0.0
    t["fixtures"] = t.get("fixtures_avg", t["fixtures"])
    return t


def _cells_wide(c, pre):
    """one period's figures as Excel columns"""
    return {f"{pre} season": c["season"], f"{pre} season index (vs window)": c["season_idx"], f"{pre} year index": c.get("season_year"),
            f"{pre} share of plan in festival months": c.get("fest_share"), f"{pre} STR band": c["band"],
            f"{pre} base band (60-120)": c["base_band"], f"{pre} STR days": c["days"], f"{pre} LY days": c["ly_days"],
            f"{pre} plan qty": c["qty"], f"{pre} MDQ": c["mdq"], f"{pre} LY qty": c["ly_qty"], f"{pre} plan Rs": c["plan_rs"],
            f"{pre} fixtures": c["fixtures"], f"{pre} stores": c.get("stores"),
            f"{pre} max STR %": c["str"], f"{pre} LY STR %": c["ly_str"]}


def workbook(df, months, has_plan, layers, info, filters):
    """the full working, not the screen (user, 9 Oct: "make sure the excel gives me a detailed version not just a summary
    excerpt"): Read me, every store x department x month with every input and step, the drill-down of the page's layers
    fully opened (every level, 4-month and each month), and the long by-month roll-ups"""
    out = io.BytesIO()
    df = _with_tags(df)
    has_plan = bool(has_plan)
    dim = df.month.map(lambda m: m.days_in_month).astype(float)
    dly = df.month.map(lambda m: (m - 12).days_in_month).astype(float)
    ok = (df.mdq > 0) & (df.plan_qty > 0) & has_plan
    lyok = df.ly_known & (df.ly_q > 0)
    # STR days by forward cover (2026-10-14): each month's MDQ sold down by its own and the later months' sales
    fk = [c for c in ("store", "department", "display", "article") if c in df]
    days = np.where(ok, se.forward_days(df, "plan_qty", "mdq", fk), np.nan) if has_plan else np.full(len(df), np.nan)
    ly_days = np.where(lyok, se.forward_days(df.assign(_lq=df.ly_q.where(lyok, 0.0)), "_lq", "mdq_base", fk,
                                             dim_of=lambda m: (m - 12).days_in_month), np.nan)
    d = pd.DataFrame({
        "division": df.division, "cluster": df.cluster, "store": df.store, "department": df.department, **({"display type": df.display} if "display" in df else {}), **({"article": df.article, "article cont % of the department's plan": df.cont,
                                         "cont % from": df.cont_from, "article cont % in its cluster": df.cont_cluster,
                                         "stock share = min(store, cluster cont %)": df.stock_cont} if "article" in df else {}), "tag": df.tag,
        "attribute": df.attribute, "month": df.month.astype(str), "days in month": dim,
        "fixtures (file)": df.fixtures_file, "fixtures": df.fixtures, "qty per fixture": df.density, "MDQ (file)": df.mdq_base,
        "MDQ = fixtures x qty per fixture": df.mdq, "edited": df.edited,
        "plan Rs": df.plan_rs, "plan qty": df.plan_qty, "plan qty from": df.qty_from, "LY avg selling price": df.asp,
        "price from": df.asp_from, "LY month": (df.month - 12).astype(str), "LY qty": df.ly_q, "LY Rs": df.ly_v,
        "plan qty per day": np.where(ok, df.plan_qty / dim, np.nan),
        "STR days = MDQ sold down by this and the next months' plan": days,
        "LY days = MDQ (file) sold down by this and the next months' LY sales": ly_days,
        "season base index (festival-free, cluster)": df.season_base, "festival days (store calendar)": df.fest_days,
        "festivals": df.festivals, "festival days x lift (per festival, learnt from every store that has it)": df.fest_detail,
        "festival lift (effective)": df.fest_lift,
        "year index = base x (1 + sum of festival days / days x (lift - 1))": df.season_year_idx,
        "season index = year index / cluster x dept window average": df.season_idx, "season": df.season,
        "peak reason (festival / high sales vs the year)": df.peak_why})
    d["STR band (season)"] = [se.str_band(x, sea) for x, sea in zip(days, df.season)]
    d["base band (60-120)"] = [se.str_band(x) for x in days]
    d["LY band (season)"] = [se.str_band(x, sea) for x, sea in zip(ly_days, df.season)]
    d["max STR % = qty / (qty + MDQ)"] = np.where(ok, se.str_of(df.plan_qty, df.mdq), np.nan)
    d["LY STR %"] = np.where(lyok, se.str_of(df.ly_q, df.mdq_base), np.nan)
    for c in ("store", "department", "division", "cluster", "attribute"):
        d[c] = d[c].map(_safe)
    bands = ", ".join(f"{k} {lo}-{hi}" for k, (lo, hi) in se.SEASON_BANDS.items())
    readme = [("What", "STR Forecaster - full working behind the page"), ("Built", time.strftime("%d %b %Y %H:%M")),
              ("Filters", filters or "none"), ("Months", ", ".join(str(m) for m in months)),
              ("Stores", f"{df.store.nunique()} (every month in both the fixture plan and the sales plan)"),
              ("STR days", "forward cover: a month's MDQ sold down by that month's planned qty, then the next months', till none is left (past the last plan month at its selling rate); the all-months figure = the months' STR days weighted by their MDQ; only rows with both a plan and fixtures"),
              ("LY days", "the file MDQ / (last year's qty / days in that month), store-months that sold last year"),
              ("Season", f"year index = the cluster's festival-free sales curve (day-wise sales 2022-25: the month vs the department's average month of the year) raised by the month's festival days at the cluster x department festival lift; season index = that month vs the same cluster x department's average month of the plan window ({', '.join(str(m) for m in months)}), so a tag shows which months stand out for that cluster; peak >= {se.SEASON_CUT[0]}, off <= {se.SEASON_CUT[1]}; built {info.get('season_built')}"),
              ("Band", f"STR days rounded to the nearest {se.BAND_STEP}, kept inside the season's limits ({bands}); never under {se.BAND_MIN} or over {se.BAND_MAX}"),
              ("Roll-ups", "plan qty and MDQ are summed first, then the days; a group's season = its departments' season index weighted by plan qty"),
              ("Articles", "with Article as a layer or filter: fixtures, MDQ and last year's sales of a store x department x month are split by each article's share of the department's planned qty in that store and month (Rs where the plan has no qty) - the store's own plan, else the chain's; planned Rs / qty are the article's own"),
              ("Sheets", "STR detail = every store x department x month; Pivot = the page's row layers as a classic pivot (one row per combination, every label repeated), all months and each month; By month = long format per level"),
              ("N-month avg", "as on the page (N = the months loaded): plan qty, MDQ, LY qty / MDQ, plan Rs, fixtures and store count are the average month (the months' figures over the months that have one), not totals; STR days = the months' forward-cover days weighted by their MDQ")]
    # rows straight to xlsxwriter in streaming mode (user, 2026-10-14: "decrease the latency for extracting output in STR
    # forecaster in excel" - pandas' cell-by-cell formatter took ~230 s of the 5 million cells); same sheets, same values
    import xlsxwriter
    wb = xlsxwriter.Workbook(out, {"constant_memory": True, "strings_to_formulas": False, "strings_to_urls": False,
                                   "in_memory": True})
    head = wb.add_format({"bold": True, "bg_color": "#E8EEE9", "border": 1, "text_wrap": True, "valign": "top"})

    class _XW:   # what the sheets below need of pandas' ExcelWriter
        def sheet(self, frame, name):
            _write_sheet(wb, head, frame, name)
    xw = _XW()
    try:
        xw.sheet(pd.DataFrame(readme, columns=["", "How it is worked out"]), "Read me")
        xw.sheet(d.sort_values(["cluster", "division", "department", "store", "month"]), "STR detail")
        # the page's layers in the classic pivot layout (user, 2026-10-14: "make the download happen in classic pivot table
        # formats rather than straight drill downs as it increases rows and blank space"): one row per combination of
        # the layers (their deepest level), every layer in its own column with its label on every row - no parent rows
        by = list(layers)
        if "department" in by and "division" not in by:
            by.insert(by.index("department"), "division")
        rows = []
        for r in se.rollup(df, by, months, has_plan):
            row = {LAYER_LABEL.get(x, x.title()): _safe(str(r.get(x, ""))) for x in by}
            row.update(_cells_wide(_avg_cell(r), f"{len(months)}-month avg"))
            for m, c in zip(months, r["months"]):
                row.update(_cells_wide(c, m.strftime("%b %y")))
            rows.append(row)
        dr = pd.DataFrame(rows)
        lab = [LAYER_LABEL.get(x, x.title()) for x in by]
        dr = dr.sort_values(lab, kind="stable")
        xw.sheet(dr[lab + [c for c in dr.columns if c not in lab]], "Pivot")
        long = []
        for by, nm in ((["cluster"], "cluster"), (["division"], "division"), (["division", "department"], "department"),
                       (["cluster", "division", "department"], "cluster x department"), (["cluster", "store"], "store")):
            for r in se.rollup(df, by, months, has_plan):
                base = {"level": nm, **{k: _safe(r[k]) for k in by}}
                for m, c in [(f"{len(months)}-month avg", _avg_cell(r))] + [(str(m), c) for m, c in zip(months, r["months"])]:
                    long.append({**base, "month": m, **{k.split(" ", 1)[1]: v for k, v in _cells_wide(c, "x").items()}})
        xw.sheet(pd.DataFrame(long), "By month")
    finally:
        wb.close()
    return out.getvalue()


# The detailed Excel, kept per inputs version x layers x filters (user, 2026-10-14: "decrease the latency for extracting
# output in STR forecaster in excel"): the same file is served again at once while nothing changed; the default one
# (the page's layers, no filters) is built in the background at start and after every change. ponytail: last 4 kept.
_wb_cache: dict = {}
_wb_lock = threading.Lock()
DL_FILTERS = ("division", "cluster", "department", "store", "season", "display", "article", "tag", "attribute")


def _download(q):
    df, info = frame()
    months = sorted(df.month.unique())
    lay = [k for k in q.get("layers", ["cluster,department,store"])[0].split(",") if k in LAYER_KEYS] or ["cluster", "department", "store"]
    key = (state.get("ver"), tuple(lay), tuple((k, tuple(sorted(q[k]))) for k in DL_FILTERS if q.get(k)))
    with _wb_lock:
        if key in _wb_cache:
            return _wb_cache[key]
        fl = "; ".join(f"{k} = {', '.join(q[k])}" for k in DL_FILTERS if q.get(k))
        x = workbook(_filter(_base(df, q, lay), q), months, bool(info.get("sales_plan")), lay, info, fl)
        while len(_wb_cache) >= 4:
            _wb_cache.pop(next(iter(_wb_cache)))
        _wb_cache[key] = x
        return x


def _warm_download():
    """build the default Excel in the background (start, and after a change)"""
    try:
        _download({})
    except Exception:  # noqa: BLE001 - the button builds it itself and shows any error
        traceback.print_exc()


def _write_sheet(wb, head, df, name):
    """one DataFrame as a sheet, header + rows, column by column to plain Python values (blank for NaN / inf)."""
    ws = wb.add_worksheet(name[:31])
    cols = [str(c) for c in df.columns]
    ws.write_row(0, 0, cols, head)
    data = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            data.append(s.astype(object).where(s.notna(), None).tolist())
        elif pd.api.types.is_numeric_dtype(s):
            v = s.astype(float).to_numpy()
            data.append(np.where(np.isfinite(v), v, np.nan).astype(object).tolist())
            data[-1] = [None if x != x else x for x in data[-1]]
        else:
            data.append([None if x is None or (isinstance(x, float) and x != x) else
                         x if isinstance(x, (int, float, bool, str)) else str(x) for x in s.astype(object).tolist()])
    for r, row in enumerate(zip(*data), 1):
        ws.write_row(r, 0, row)
    ws.freeze_panes(1, 0)
    ws.set_column(0, max(len(cols) - 1, 0), 14)


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
                # any layer path, e.g. "division,department,cluster" (user, 9 Oct: "drag and drop function which drills to
                # any level for STR similar to AOP forecaster output model"); a department carries its one division along
                by = [k for k in q.get("by", ["division"])[0].split(",") if k in LAYER_KEYS] or ["division"]
                if "department" in by and "division" not in by:
                    by.insert(by.index("department"), "division")
                d = _base(df, q, by)
                d, hp = _filter(d, q), bool(info.get("sales_plan"))
                rows = se.rollup(d, by, months, hp)
                if len(rows) > 6000:
                    return self._send(413, {"error": f"{len(rows):,} rows at that level - open rows one at a time instead."})
                if "department" in by:
                    _tag_cols(rows)
                # distinct stores with fixtures per month, for the All row (a store under many rows counts once)
                st = [int(d.loc[(d.month == m) & (d.fixtures > 0), "store"].nunique()) for m in months]
                return self._send(200, {"months": [str(m) for m in months], "rows": rows, "by": by, "has_plan": hp,
                                        "all_stores": st})
            if path == "/api/cells":
                dept = q.get("department", [""])[0]
                d = df[df.department == dept]
                if d.empty:
                    return self._send(404, {"error": "No such department in the fixture plan."})
                mi = {m: i for i, m in enumerate(months)}
                # STR days by forward cover (2026-10-14), per store (and per display type for the display rows)
                hp_ = bool(info.get("sales_plan"))
                d = d.assign(fwd_days=se.forward_days(d, "plan_qty", "mdq", ["store"]) if hp_ else np.nan,
                             fwd_ly_days=se.forward_days(d.assign(_lq=d.ly_q.where(d.ly_known, 0.0)), "_lq", "mdq_base", ["store"],
                                                  dim_of=lambda m: (m - 12).days_in_month))

                def cell(r, src=None, by_disp=False):
                    dim, ldim = r.month.days_in_month, (r.month - 12).days_in_month
                    c = {"fixtures": r.fixtures, "fixtures_file": r.fixtures_file, "density": r.density, "mdq": r.mdq,
                         "mdq_base": r.mdq_base, "plan_rs": r.plan_rs, "plan_qty": r.plan_qty, "qty_from": r.qty_from,
                         "asp": r.asp, "asp_from": r.asp_from, "ly_q": r.ly_q, "n_days": dim, "ly_n_days": ldim,
                         "str": float(se.str_of(r.plan_qty, r.mdq)) if info.get("sales_plan") and r.mdq > 0 and r.plan_qty > 0 else None,
                         "ly_str": float(se.str_of(r.ly_q, r.mdq_base)) if r.ly_known and r.ly_q > 0 else None,
                         "days": (None if r.fwd_days != r.fwd_days else float(r.fwd_days)) if info.get("sales_plan") and r.mdq > 0 else None,
                         "ly_days": (None if r.fwd_ly_days != r.fwd_ly_days else float(r.fwd_ly_days)) if r.ly_known else None, "edited": r.edited}
                    if c["days"] is not None and src is not None:   # the forward-cover working for the pop-up (2026-10-14)
                        nx = src[(src.store == r.store) & (src.month >= r.month)]
                        if by_disp:
                            nx = nx[nx.display == r.display]
                        nx = nx.sort_values("month")
                        c["cover"] = se.cover_walk(r.mdq, nx.plan_qty.astype(float).tolist(),
                                                   [m.days_in_month for m in nx.month], [str(m) for m in nx.month])
                    sea = r.season
                    c.update(season=sea, season_idx=r.season_idx, band=se.str_band(c["days"], sea), base_band=se.str_band(c["days"]),
                             season_base=r.season_base, fest_days=r.fest_days, festivals=r.festivals, fest_lift=r.fest_lift, fest_detail=r.fest_detail,
                             season_year=r.season_year_idx, fest_share=1.0 if r.fest_days > 0 else 0.0, peak_why=r.peak_why,
                             pk=r.plan_qty if r.peak_ok else 0.0)
                    return c

                # user, 9 Oct: "add display type to the department editor table too": a store with one display type = one
                # row (that type, editable); with both = an editable "All" row (fixture edits are per store x department)
                # and a read-only row per display type with its own STR
                dv = display_df()
                dv = dv[dv.department == dept]
                dv = dv.assign(fwd_days=se.forward_days(dv, "plan_qty", "mdq", ["store", "display"]) if hp_ else np.nan,
                               fwd_ly_days=se.forward_days(dv.assign(_lq=dv.ly_q.where(dv.ly_known, 0.0)), "_lq", "mdq_base",
                                                    ["store", "display"], dim_of=lambda m: (m - 12).days_in_month))
                kinds = dv.groupby("store").display.unique()
                by = {}
                for r in d.itertuples():
                    if r.month in mi:
                        ks = kinds.get(r.store, [se.NO_DISP])
                        key = (r.store, ks[0] if len(ks) == 1 else "All")
                        by.setdefault(key, [None] * len(months))[mi[r.month]] = cell(r, d)
                for r in dv.itertuples():
                    if r.month in mi and len(kinds.get(r.store, [])) > 1:
                        by.setdefault((r.store, r.display), [None] * len(months))[mi[r.month]] = cell(r, dv, True)
                cl = dict(zip(d.store, d.cluster))
                order = {"All": 0, "TABLE": 1, "NON_TABLE": 2}
                rows = [{"store": st, "display": k, "edit": k == "All" or len(kinds.get(st, [])) <= 1, "cluster": cl.get(st),
                         "months": by[(st, k)]} for st, k in sorted(by, key=lambda x: (x[0], order.get(x[1], 3)))]
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
            if path == "/api/values":   # every value of one hierarchy, for its search filter
                k = q.get("key", [""])[0]
                if k not in LAYER_KEYS:
                    return self._send(400, {"error": "unknown key"})
                d = _base(df, {}, (k,))
                return self._send(200, {"key": k, "values": sorted(str(x) for x in d[k].dropna().unique())})
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
            if path == "/api/stores/download":   # the Store mapping tab as Excel
                sm = pd.DataFrame((info.get("common") or {}).get("store_map") or [])
                if len(sm):
                    sm = sm.rename(columns={"store": "Store", "status": "Status", "cluster": "Cluster (AOP)", "fixture_months": "Fixture plan months",
                                            "plan_months": "Sales plan months", "missing": "Missing", "mdq": "MDQ (all months)", "plan_rs": "Plan Rs (all months)"})
                    for c in ("Store", "Cluster (AOP)"):
                        sm[c] = sm[c].map(_safe)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_formulas": False}}) as xw:
                    sm.to_excel(xw, sheet_name="Store mapping", index=False)
                return self._send(200, out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f'attachment; filename="STR Store mapping - {time.strftime("%d.%m.%y")}.xlsx"'})
            if path == "/api/download":
                name = f"STR Forecast - {time.strftime('%d.%m.%y')}.xlsx"
                return self._send(200, _download(q),
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._send(404, {"error": "Not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/")
        try:
            return self._post(u, path)
        finally:   # any change: the cached Excel files are old - drop them and build the default one again
            with _wb_lock:
                _wb_cache.clear()
            threading.Thread(target=_warm_download, daemon=True).start()

    def _post(self, u, path):
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
    threading.Thread(target=lambda: (frame(), _warm_download()), daemon=True).start()   # the frame, then the default Excel
    threading.Thread(target=_season_watch, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
