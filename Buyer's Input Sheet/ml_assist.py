"""History check for the planner's factor (user, 2026-10-09: "i want the ml concepts to aid in the factor tuning").

Advisory only - nothing here changes a factor. Built from the 9 Oct offline study (ml_study/BIS_ML_factor_study.md):
past planning cycles are rebuilt from calendar.sales_fact (actual sales, MENS / LADIES / KIDS, like-for-like stores)
with the BIS timing - target = a 4-month block starting Mar / Jul / Nov, LY = the same block a year earlier, plan made
5 months before the block with data to the month before - and every factor is scored the BIS way:
    plan[d] = A_div x LY[d] x f[d] / sum_div(LY x f),   WAPE = sum|plan - actual| / sum actual   (divisions pooled)
Only cycles whose target had ended by a test cycle's plan date are used to predict it (no look-ahead).

Writes ml_assist.json with:
  walk_*      the honest test: the 25V26-growth (and a recent-momentum) strength picked on earlier cycles only, then
              scored on the next test cycle, vs plain share; pick_* = the strength all completed cycles would pick now
  curve_*     every strength on the test cycles - descriptive only (a minimum read off it was picked after seeing them)
  bands       how departments in each growth / recent-momentum band did next year (actual share / plain share)
  ridge       a linear model (numpy, exact additive reasons) of next-year relative performance, its walk-forward
              track record, and for the coming MAMJ plan each department's predicted multiplier + top reasons
  departments the coming MAMJ plan's inputs per department (growth vs division, recent momentum, bands)
Within its division only (user, 2026-10-12: "make sure the performance is measured in their respective division and
no cross division referencing is there in the ml concept"): every clue compares a department with its own division,
one ridge model is learnt per division from that division's departments only, the bands are per division, and the
error is scored division by division (summed only to report one number).
Sell-thru and fill rate (user, 2026-10-12: "add sell-thru and fill rate as clues in the ml"; chose the hybrid): they have
no history before 2026, so they are learnt on the one window that has them - the BIS Mar-Jun'26 sell-thru (same
definition as the BIS) and the fill-rate file against the months after it (Jul'26 to the last closed month), per
division, on top of the history model (its own view of those months taken out first), strength picked by leave-one-
department-out. Weak evidence on one window; shrinks to no effect when it does not help.

Run: python ml_assist.py            (rebuild + self-check); the BIS server runs build() on a planner's Refresh.
"""
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(_HERE, "ml_assist.json")
_ENV = os.path.join(_HERE, "..", "Tentative AOP Forecaster", ".env")
COVID = set(pd.period_range("2020-03", "2021-06", freq="M"))   # lockdown months: no input or target may touch them
SMALL = 1e5                       # a growth needs at least Rs 1 lakh in the earlier block
K_DAMP, CLAMP = 0.05, (0.8, 1.2)  # BIS guardrails (Rs Cr a month, factor limits) - same as _fmLimit
SEASON = {3: "MAMJ", 7: "JASO", 11: "NDJF"}
G_GRID = [round(x, 2) for x in np.arange(-0.5, 1.001, 0.05)]
R_GRID = [round(x, 2) for x in np.arange(-0.25, 0.751, 0.05)]
LAMBDA = 30.0                     # ridge penalty when there is no earlier cycle to choose it on
LAMS = [0.3, 3.0, 30.0, 300.0]    # chosen on the last training cycle, as in the study
FEATS = ["rel_g1", "rel_g2", "rel_gr", "rel_g1_div", "accel", "rel_size", "share_ly",
         "miss_g1", "miss_g2", "miss_gr", "season_MAMJ", "season_JASO"]   # no division labels: one model per division
LABEL = {"rel_g1": "25V26 growth vs division", "rel_g2": "2-year growth vs division", "rel_gr": "recent momentum",
         "rel_g1_div": "growth vs division total", "accel": "growth speeding up / slowing", "rel_size": "department size",
         "share_ly": "department size", "miss_g1": "no 25V26 history", "miss_g2": "no 2-year history",
         "miss_gr": "no recent history", "season_MAMJ": "season", "season_JASO": "season"}
DIVS = ("MENS", "LADIES", "KIDS")
LAMS_SF = [1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1e9]   # sell-thru / fill-rate penalty; 1e9 = no effect


def _db_url():
    for line in open(_ENV, encoding="utf-8"):
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
            for p in ("postgresql://", "postgres://"):
                if url.startswith(p):
                    return "postgresql+psycopg://" + url[len(p):]
            return url
    raise RuntimeError("DATABASE_URL not found")


def load_sales():
    from sqlalchemy import create_engine, text
    eng = create_engine(_db_url())
    try:
        with eng.connect() as c:
            return pd.read_sql(text("""
                SELECT to_char(month,'YYYY-MM') AS month, store, plan_division AS division, department, sum(sl_v) AS sl_v
                FROM calendar.sales_fact
                WHERE kind='actual' AND calendar_id=0 AND plan_division IN ('MENS','LADIES','KIDS')
                GROUP BY 1,2,3,4"""), c)
    finally:
        eng.dispose()


class Cube:
    """dept x store x month sales, with the window helpers the cycles need"""

    def __init__(self, raw):
        p = pd.PeriodIndex(raw["month"], freq="M")
        self.last = p.max()
        months = pd.period_range(p.min(), self.last, freq="M")
        self.mi = {m: i for i, m in enumerate(months)}
        self.keys = raw[["division", "department"]].drop_duplicates().sort_values(["division", "department"]).reset_index(drop=True)
        ki = {(d, n): i for i, (d, n) in enumerate(zip(self.keys.division, self.keys.department))}
        stores = sorted(raw["store"].unique())
        si = {s: i for i, s in enumerate(stores)}
        self.cube = np.zeros((len(self.keys), len(stores), len(months)))
        np.add.at(self.cube, (np.array([ki[(a, b)] for a, b in zip(raw["division"], raw["department"])]),
                              raw["store"].map(si).to_numpy(), p.map(self.mi).to_numpy()), raw["sl_v"].to_numpy())
        self.store_month = self.cube.sum(0)
        self.div = self.keys["division"].to_numpy()

    def ok(self, ms):
        return all(m not in COVID and m in self.mi for m in ms)

    def trading(self, ms):
        return np.all(self.store_month[:, [self.mi[m] for m in ms]] > 0, axis=1)

    def sales(self, ms, smask):
        return self.cube[:, smask, :][:, :, [self.mi[m] for m in ms]].sum(axis=(1, 2))

    def growth(self, cur, prev):
        n = len(self.keys)
        if not cur or not self.ok(cur + prev):
            return np.full(n, np.nan), {}
        s = self.trading(cur + prev)
        x, y = self.sales(cur, s), self.sales(prev, s)
        g = np.where(y >= SMALL, x / np.where(y > 0, y, 1) - 1, np.nan)
        tot = {d: x[self.div == d].sum() / y[self.div == d].sum() - 1 for d in np.unique(self.div) if y[self.div == d].sum() > 0}
        return g, tot


def _rows(cube, S, with_target=True):
    """one row per active department of the cycle whose target block starts at S"""
    T = [S + i for i in range(4)]
    L, L2, L3 = [m - 12 for m in T], [m - 24 for m in T], [m - 36 for m in T]
    R = [m for m in (S - 8, S - 7, S - 6) if m <= cube.last]      # the months before the plan date that exist
    if with_target and (T[-1] > cube.last or not cube.ok(T + L)):
        return []
    if not with_target and not cube.ok(L):
        return []
    st = cube.trading(T + L) if with_target else cube.trading(L)
    b = cube.sales(L, st)
    a = cube.sales(T, st) if with_target else np.full(len(b), np.nan)
    g1, gd1 = cube.growth(L, L2)
    g2, _ = cube.growth(L, L3)
    gr, _ = cube.growth(R, [m - 12 for m in R])
    out = []
    for k in np.where(b > 0)[0]:
        out.append(dict(cycle=str(S), season=SEASON[S.month], target_end=T[-1], plan_date=S - 5, division=cube.div[k],
                        department=cube.keys.department[k], b=b[k], a=a[k], g1=g1[k], g2=g2[k], gr=gr[k],
                        g1_div=gd1.get(cube.div[k], np.nan), recent=",".join(str(m) for m in R)))
    return out


def _features(df):
    df = df.copy()
    grp = [df.cycle, df.division]
    df["B"] = df.groupby(grp)["b"].transform("sum")
    df["share_ly"] = df.b / df.B
    df["lypm_cr"] = df.b / 4 / 1e7
    for g in ("g1", "g2", "gr"):
        med = df.groupby(grp)[g].transform("median")
        raw = np.log((1 + df[g]) / (1 + med))   # log of (1+g)/(1+division median) - as the BIS's _contFactor
        df[f"raw_{g}"] = raw.where(np.isfinite(raw))   # -100% growth (ratio 0) = no data, 1.00 in the BIS (review 9 Oct)
        df[f"rel_{g}"] = df[f"raw_{g}"].clip(-1.5, 1.5)        # clipped copy for the model only
        df[f"miss_{g}"] = df[f"rel_{g}"].isna().astype(float)
    df["rel_g1_div"] = np.log((1 + df.g1) / (1 + df.g1_div)).clip(-1.5, 1.5)
    df["accel"] = (np.log1p(df.g1.clip(lower=-0.95)) - 0.5 * np.log1p(df.g2.clip(lower=-0.95))).clip(-1.5, 1.5)
    size = np.log(df.lypm_cr.clip(lower=1e-4))
    df["rel_size"] = size - size.groupby(grp).transform("median")   # vs its own division's middle department
    for s in ("MAMJ", "JASO"):
        df[f"season_{s}"] = (df.season == s).astype(float)
    return df


def guard(f, lypm):
    """BIS small-department damping then limits (_fmLimit without rules - no fill history)"""
    return np.clip(1 + (f - 1) * lypm / (lypm + K_DAMP), *CLAMP)


def wape_parts(sub, f):
    """{division: (abs error, actual)} - each division's own plan split (its actual total x its departments' LY x f)"""
    out = {}
    for d in sub.division.unique():
        m = (sub.division == d).to_numpy()
        b, a, ff = sub.b.to_numpy()[m], sub.a.to_numpy()[m], f[m]
        A = a.sum()
        out[d] = (float(np.abs(A * b * ff / (b * ff).sum() - a).sum()), float(A))
    return out


def wape(sub, f, div=None):
    """BIS back-test WAPE for one cycle: one division, or the divisions' errors summed (each scored within itself)"""
    p = wape_parts(sub, f)
    if div is not None:
        return p[div][0] / p[div][1] if div in p and p[div][1] else float("nan")
    return sum(e for e, _ in p.values()) / sum(a for _, a in p.values())


class RidgeNP:
    """weighted ridge, unpenalised intercept, standardised inputs; contributions are exact (linear)"""

    def fit(self, x, y, w, lam=LAMBDA):
        self.mu = np.average(x, axis=0, weights=w)
        self.sd = np.sqrt(np.average((x - self.mu) ** 2, axis=0, weights=w)) + 1e-9
        z = (x - self.mu) / self.sd
        ym = np.average(y, weights=w)
        W = w[:, None]
        self.beta = np.linalg.solve(z.T @ (W * z) + lam * np.eye(z.shape[1]), z.T @ (w * (y - ym)))
        self.b0 = ym
        return self

    def contrib(self, x):
        return ((x - self.mu) / self.sd) * self.beta

    def predict(self, x):
        return self.b0 + self.contrib(x).sum(1)


def _xy(df):
    x = np.nan_to_num(df[FEATS].to_numpy(dtype=float), nan=0.0)   # missing = division median (rel 0); miss_* flag it
    y = np.log(((df.a / df.groupby([df.cycle, df.division]).a.transform("sum")) / df.share_ly).clip(0.1, 10).to_numpy())
    w = (df.b / df.groupby(df.cycle).b.transform("sum")).to_numpy()   # each cycle weighs the same; within it, by LY
    assert df.division.nunique() <= 1, "one division at a time - no cross-division learning"
    return x, y, w * len(w) / w.sum()


def zs_raw(st, r):
    v = st.get(f"{r.division}|{str(r.department).upper()}")
    return None if v is None else float(v)


def _sf_inputs(rows, st, fill):
    """log(sell-thru / its division's middle department), log(fill / division middle); missing = 0 (neutral)"""
    s = np.array([np.nan if (v := zs_raw(st, r)) is None or v <= 0 else v for r in rows.itertuples()], dtype=float)
    f = np.array([np.nan if (v := fill.get(str(r.department).upper())) is None or v <= 0 else v for r in rows.itertuples()], dtype=float)
    out = []
    for x in (s, f):
        z = np.zeros(len(rows))
        for dn in rows.division.unique():
            k = (rows.division == dn).to_numpy() & np.isfinite(x)
            if k.sum() >= 3:
                z[k] = np.log(x[k] / np.median(x[k]))
        out.append(z)
    return out[0], out[1]


def _st_fill_terms(cube, models, ridge_pred, st, fill):
    """learn, per division, how much sell-thru and fill rate add to the history model on the months after Mar-Jun'26:
    y = log(Jul'26.. actual share / Jul'25.. share) - the history model's own centred view for the Jul cycle;
    weighted ridge on the two inputs, penalty by leave-one-department-out (1e9 = no effect)"""
    res = {"window": "", "by_division": {}}
    if not st and not fill:
        return res
    y0 = 2026
    W = [m for m in pd.period_range(f"{y0}-07", f"{y0}-10", freq="M") if m <= cube.last]
    if not W or not cube.ok(W + [m - 12 for m in W]):
        return res
    res["window"] = f"{W[0]}..{W[-1]}"
    rows = _features(pd.DataFrame(_rows(cube, pd.Period(f"{y0}-07", freq="M"), with_target=False)))
    if not len(rows):
        return res
    smask = cube.trading(W + [m - 12 for m in W])
    a_all, b_all = cube.sales(W, smask), cube.sales([m - 12 for m in W], smask)
    key = {(dv, dp): i for i, (dv, dp) in enumerate(zip(cube.keys.division, cube.keys.department))}
    idx = np.array([key[(r.division, r.department)] for r in rows.itertuples()])
    rows = rows.assign(a=a_all[idx], b=b_all[idx])
    rows = rows[(rows.b > 0) & (rows.a >= 0)].reset_index(drop=True)
    off = ridge_pred(models, rows)                       # the history model's view, centred in each division
    zs, zf = _sf_inputs(rows, st, fill)
    for dn in DIVS:
        k = (rows.division == dn).to_numpy()
        n = int(k.sum())
        if n < 10:
            res["by_division"][dn] = {"n": n, "on": False, "why": "too few departments"}
            continue
        sub = rows[k]
        A, bb, aa = sub.a.sum(), sub.b.to_numpy(), sub.a.to_numpy()
        y = np.log(((aa / A) / (bb / bb.sum())).clip(0.1, 10)) - off[k]
        w = bb / bb.sum() * n
        x = np.column_stack([zs[k], zf[k]])

        def loo(lam):   # leave one department out: its term from the others only
            p = np.zeros(n)
            for i in range(n):
                o = np.ones(n, bool)
                o[i] = False
                m = RidgeNP().fit(x[o], y[o], w[o], lam)
                p[i] = m.predict(x[i:i + 1])[0] - m.b0
            return p

        def err(p):     # the BIS split error on the window: history factor alone vs with the term
            f = np.exp(off[k] + p)
            return float(np.abs(A * bb * f / (bb * f).sum() - aa).sum() / A)
        best = min(LAMS_SF, key=lambda lam: err(loo(lam)))
        e0, e1 = err(np.zeros(n)), err(loo(best))
        m = RidgeNP().fit(x, y, w, best)
        on = best < 1e8 and e1 < e0
        res["by_division"][dn] = {"n": n, "lam": best, "on": bool(on), "err_without": e0, "err_with": e1,
                                  "beta_st": float(m.beta[0] / m.sd[0]) if on else 0.0,     # per unit of log(ST / division middle)
                                  "beta_fill": float(m.beta[1] / m.sd[1]) if on else 0.0,
                                  "typ_st": float(np.exp(m.beta[0])) if on else 1.0,         # one typical difference
                                  "typ_fill": float(np.exp(m.beta[1])) if on else 1.0,
                                  "n_st": int((zs[k] != 0).sum()), "n_fill": int((zf[k] != 0).sum())}
    return res


def load_st(src, week_to_mi):
    """{DIVISION|DEPARTMENT: Mar-Jun'26 sell-thru (0-1)} the BIS way (sync_server monthly_st_dept -> _plannerInputs):
    store rows, season '26, active stores, weeks 9-26; per week sum qty -> ST%; per month the mean of the non-zero weeks;
    the department's input = the mean over the months with data"""
    import pyarrow.parquet as pq
    d = pq.read_table(src, columns=["DIVISION", "DEPARTMENT", "WEEK", "SL_Q", "CLS_STK_Q", "LOCATION", "SEASON", "STORE_STATUS"]).to_pandas()
    d = d[(d.LOCATION.astype(str).str.upper() == "STORE") & d.SEASON.astype(str).str.contains("26", na=False)
          & (d.STORE_STATUS.astype(str).str.upper() == "ACTIVE") & d.WEEK.isin(set(week_to_mi))]
    d["k"] = d.DIVISION.astype(str).str.strip().str.upper() + "|" + d.DEPARTMENT.astype(str).str.strip().str.upper()
    w = d.groupby(["k", "WEEK"])[["SL_Q", "CLS_STK_Q"]].sum().reset_index()
    w["mi"] = w.WEEK.map(week_to_mi)
    den = w.SL_Q + w.CLS_STK_Q
    w["p"] = np.where(den > 0, w.SL_Q / den.where(den > 0, 1), 0.0)
    m = w[w.p > 0].groupby(["k", "mi"]).p.mean()
    return m.groupby(level=0).mean().to_dict()


def load_fill():
    """{DEPARTMENT: fill rate 0-1} from fill_rate.json (the BIS's PLAN vs FILL RATE import)"""
    p = os.path.join(_HERE, "fill_rate.json")
    j = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    return {" ".join(str(k).split()).upper(): float(v) for k, v in (j.get("departments") or {}).items() if v is not None}


def build(out_path=OUT_JSON, raw=None, st=None, fill=None):
    """st = (sell-thru parquet path, {"WK-09": mi, ...}) or a ready {DIV|DEPT: 0-1} dict; None = no sell-thru term"""
    raw = load_sales() if raw is None else raw
    if isinstance(st, tuple):
        st = load_st(*st)
    st = st or {}
    fill = load_fill() if fill is None else fill
    # calendar.sales_fact should hold closed months only; never let the running month in even if it does (review 9 Oct)
    raw = raw[raw["month"] < datetime.now().strftime("%Y-%m")]
    cube = Cube(raw)
    rows = []
    for S in pd.period_range("2021-03", cube.last, freq="M"):
        if S.month in SEASON:
            rows += _rows(cube, S)
    df = _features(pd.DataFrame(rows)).reset_index(drop=True)
    cyc = df.drop_duplicates("cycle")[["cycle", "target_end", "plan_date"]].reset_index(drop=True)
    allc = list(cyc.cycle)
    by = {c: df[df.cycle == c] for c in allc}

    def eligible(c):
        """cycles known at c's plan date: their target ended BEFORE the plan month (the plan has data to the month before)"""
        p = cyc.loc[cyc.cycle == c, "plan_date"].iloc[0]
        return [x for x, e in zip(cyc.cycle, cyc.target_end) if e < p]
    tests = [c for c in allc if len(eligible(c)) >= 4]

    def cont(sub, s_g, s_r):   # the Continuous growth / recent-momentum terms alone, BIS damping + limits
        x = s_g * np.nan_to_num(sub.raw_g1.to_numpy()) + s_r * np.nan_to_num(sub.raw_gr.to_numpy())
        return guard(np.exp(x), sub.lypm_cr.to_numpy())

    plain = {c: wape(by[c], np.ones(len(by[c]))) for c in allc}
    SC = {"g": {s: {c: wape(by[c], cont(by[c], s, 0.0)) for c in allc} for s in G_GRID},
          "r": {s: {c: wape(by[c], cont(by[c], 0.0, s)) for c in allc} for s in R_GRID}}

    def pick(T, cs):
        return min(T, key=lambda s: np.mean([T[s][c] for c in cs]))

    def summary(T):
        """curve = each strength on the test cycles (descriptive: a minimum read off it is picked after seeing them);
        walk = the honest score: for every test cycle the strength is picked on earlier cycles only, then scored"""
        curve = [{"s": s, "mean": float(np.mean([T[s][c] for c in tests])), "wins": int(sum(T[s][c] < plain[c] - 1e-12 for c in tests))}
                 for s in T]
        picks = {c: pick(T, eligible(c)) for c in tests}
        wf = {c: T[picks[c]][c] for c in tests}
        return curve, {"mean": float(np.mean(list(wf.values()))), "wins": int(sum(wf[c] < plain[c] - 1e-12 for c in tests)),
                       "picks": picks, "by_cycle": wf}, pick(T, allc)

    cg, wfg, now_g = summary(SC["g"])
    cr, wfr, now_r = summary(SC["r"])

    # Ridge, one model per division learnt from that division's departments only; the same centred, guarded factor in
    # its track record and in its advice; each division's lambda picked on its own earlier cycle
    def ridge_pred(models, sub):
        pred = np.zeros(len(sub))
        for dname in sub.division.unique():
            k = (sub.division == dname).to_numpy()
            if dname in models:
                pred[k] = models[dname].predict(np.nan_to_num(sub[k][FEATS].to_numpy(dtype=float)))
            pred[k] -= np.average(pred[k], weights=sub.b.to_numpy()[k])   # vs the division's average department
        return pred

    def ridge_factor(models, sub):
        pred = ridge_pred(models, sub)
        return pred, guard(np.exp(pred), sub.lypm_cr.to_numpy())

    def fit1(cs, lam, dname):
        sub = df[df.cycle.isin(cs) & (df.division == dname)]
        if len(sub) < len(FEATS) + 5:
            return None
        x, y, w = _xy(sub)
        return RidgeNP().fit(x, y, w, lam)

    def choose_lam(cs, dname):
        val, inner = cs[-1], eligible(cs[-1])
        if not inner:
            return LAMBDA

        def err(lam):
            m = fit1(inner, lam, dname)
            return wape(by[val], ridge_factor({dname: m} if m else {}, by[val])[1], dname)
        return min(LAMS, key=err)

    def fit_all(cs):
        lams = {dn: choose_lam(cs, dn) for dn in DIVS}
        return {dn: m for dn in DIVS if (m := fit1(cs, lams[dn], dn)) is not None}, lams

    wf, wf_div = {}, {dn: {} for dn in DIVS}
    plain_div = {dn: {c: wape(by[c], np.ones(len(by[c])), dn) for c in tests} for dn in DIVS}
    for c in tests:
        models_c, _ = fit_all(eligible(c))
        f_c = ridge_factor(models_c, by[c])[1]
        wf[c] = float(wape(by[c], f_c))
        for dn in DIVS:
            wf_div[dn][c] = float(wape(by[c], f_c, dn))
    models, lam_now = fit_all(allc)

    # bands (descriptive, all cycles; a department counts once per cycle): next-year actual share / plain share
    df["rel_perf"] = (df.a / df.groupby([df.cycle, df.division]).a.transform("sum")) / df.share_ly

    def bands(col, q, dname):
        d = df[df.division == dname].dropna(subset=[col])   # departments of the same division only
        edges = np.unique(np.quantile(d[col], np.linspace(0, 1, q + 1)))
        d = d.assign(bin=np.clip(np.searchsorted(edges, d[col], side="right") - 1, 0, len(edges) - 2))
        return [{"from": float(np.exp(edges[i])), "to": float(np.exp(edges[i + 1])),
                 "rel_perf": float(np.average(g.rel_perf.clip(0, 5), weights=g.b)), "n": int(len(g))}
                for i, g in d.groupby("bin")], edges

    BG = {dn: bands("rel_g1", 6, dn) for dn in DIVS}   # fewer bands than pooled: each division has a third of the rows
    BR = {dn: bands("rel_gr", 4, dn) for dn in DIVS}

    def band(v, e):
        return None if v != v else int(np.clip(np.searchsorted(e, v, side="right") - 1, 0, len(e) - 2))

    # the coming MAMJ plan (the BIS plans MAMJ): inputs + the model's view per department
    nxt = pd.Period(f"{cube.last.year + (1 if cube.last.month >= 3 else 0)}-03", freq="M")
    cur = _features(pd.DataFrame(_rows(cube, nxt, with_target=False)))
    sf = _st_fill_terms(cube, models, ridge_pred, st, fill)
    deps = {}
    if len(cur):
        pred_h = ridge_pred(models, cur)
        dv_ = cur.division.to_numpy()
        bw = cur.b.to_numpy()
        zs, zf = _sf_inputs(cur, st, fill)
        t_st, t_fi = np.zeros(len(cur)), np.zeros(len(cur))
        for dn, o in sf["by_division"].items():
            k = dv_ == dn
            if o.get("on") and k.any():
                t_st[k], t_fi[k] = o["beta_st"] * zs[k], o["beta_fill"] * zf[k]
                t_st[k] -= np.average(t_st[k], weights=bw[k])     # each term vs the division's average department
                t_fi[k] -= np.average(t_fi[k], weights=bw[k])
        pred = pred_h + t_st + t_fi
        f_g = guard(np.exp(pred), cur.lypm_cr.to_numpy())
        xc = np.nan_to_num(cur[FEATS].to_numpy(dtype=float))
        con = np.zeros((len(cur), len(FEATS)))
        for dn, m in models.items():
            k = dv_ == dn
            if k.any():
                con[k] = m.contrib(xc[k])
                con[k] -= np.average(con[k], axis=0, weights=bw[k])   # each reason vs the division's average department too
        nan_of = {"rel_g1": "g1", "rel_g1_div": "g1", "accel": "g1", "rel_g2": "g2", "rel_gr": "gr"}
        for i, r in enumerate(cur.itertuples()):
            agg = {}
            for j, ft in enumerate(FEATS):
                if LABEL[ft] in ("season", "division"):          # the same for every department compared
                    continue
                if ft.startswith("miss_") and not xc[i, j]:     # "no history" only when the history is missing
                    continue
                if ft in nan_of and getattr(r, nan_of[ft]) != getattr(r, nan_of[ft]):   # no reason from an imputed value
                    continue
                if ft == "accel" and r.g2 != r.g2:
                    continue
                agg[LABEL[ft]] = agg.get(LABEL[ft], 0.0) + con[i, j]
            if t_st[i]:
                agg["sell-thru vs division"] = t_st[i]
            if t_fi[i]:
                agg["fill rate vs division"] = t_fi[i]
            top = sorted(agg.items(), key=lambda kv: -abs(kv[1]))[:3]
            bgd, brd = BG.get(r.division), BR.get(r.division)
            deps[f"{r.division}|{r.department}"] = {
                "g1": None if r.g1 != r.g1 else float(r.g1), "rel_g1": None if r.raw_g1 != r.raw_g1 else float(np.exp(r.raw_g1)),
                "rel_gr": None if r.raw_gr != r.raw_gr else float(np.exp(r.raw_gr)),
                "band_g": band(r.rel_g1, bgd[1]) if bgd else None, "band_r": band(r.rel_gr, brd[1]) if brd else None,
                "ml": float(np.exp(pred[i])), "ml_guarded": float(f_g[i]),
                "parts": {"history": float(np.exp(pred_h[i])), "st": float(np.exp(t_st[i])), "fill": float(np.exp(t_fi[i]))},
                "st": zs_raw(st, r), "fill": fill.get(str(r.department).upper()),
                "why": [{"label": k, "mult": float(np.exp(v))} for k, v in top]}
    ptest = float(np.mean([plain[c] for c in tests]))
    out = {"built_at": datetime.now().isoformat(timespec="seconds"), "data_to": str(cube.last),
           "cycles": allc, "tests": tests, "plain": {"by_cycle": {c: plain[c] for c in tests}, "mean": ptest},
           "curve_growth": cg, "walk_growth": wfg, "pick_growth": now_g,
           "curve_recent": cr, "walk_recent": wfr, "pick_recent": now_r,
           "ridge": {"walk_forward": wf, "mean": float(np.mean(list(wf.values()))), "lambda": lam_now,
                     "wins": int(sum(wf[c] < plain[c] - 1e-12 for c in tests)), "per_division": True,
                     "coef": {dn: {f: float(b) for f, b in zip(FEATS, m.beta)} for dn, m in models.items()},
                     "by_division": {dn: {"walk_forward": wf_div[dn], "mean": float(np.mean(list(wf_div[dn].values()))),
                                          "plain": float(np.mean(list(plain_div[dn].values()))),
                                          "wins": int(sum(wf_div[dn][c] < plain_div[dn][c] - 1e-12 for c in tests))} for dn in DIVS}},
           "st_fill": sf,
           "bands_growth": {dn: v[0] for dn, v in BG.items()}, "bands_recent": {dn: v[0] for dn, v in BR.items()},
           "plan": {"cycle": str(nxt), "ly": f"{nxt - 12}..{nxt - 9}", "recent": cur.recent.iloc[0] if len(cur) else "",
                    "ready": bool(len(cur))},
           "departments": deps}
    with open(out_path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    os.replace(out_path + ".tmp", out_path)
    return out


if __name__ == "__main__":   # rebuild + self-check
    import sys
    sys.path.insert(0, _HERE)
    import sync_server as _ss   # the BIS server's own sell-thru source and week -> month map
    _src = _ss.get_latest_file(_ss.SELLTHRU_DIR, ("*.parquet",))
    ST_ARGS = load_st(_src, _ss.WEEK_STR_TO_MI) if _src else {}
    o = build(st=ST_ARGS)
    g20 = next(c for c in o["curve_growth"] if abs(c["s"] - 0.2) < 1e-9)
    print("cycles", o["cycles"], "tests", o["tests"])
    print(f"plain {o['plain']['mean']*100:.2f} | growth 0.20 {g20['mean']*100:.2f} | growth walk-forward {o['walk_growth']['mean']*100:.2f} "
          f"({o['walk_growth']['wins']}/{len(o['tests'])}) picks {o['walk_growth']['picks']} now {o['pick_growth']} | "
          f"recent walk-forward {o['walk_recent']['mean']*100:.2f} ({o['walk_recent']['wins']}/{len(o['tests'])}) picks "
          f"{o['walk_recent']['picks']} now {o['pick_recent']} | ridge {o['ridge']['mean']*100:.2f} ({o['ridge']['wins']}) lam {o['ridge']['lambda']}")
    print("plan", o["plan"], "departments", len(o["departments"]))
    # consistency: a department's reasons never cite growth it does not have; the factor stays inside the limits
    bad = [k for k, v in o["departments"].items() for w in v["why"]
           if (w["label"] == "no 25V26 history" and v["g1"] is not None) or (w["label"] == "25V26 growth vs division" and v["g1"] is None)]
    assert not bad, bad[:5]
    assert all(0.8 - 1e-9 <= v["ml_guarded"] <= 1.2 + 1e-9 for v in o["departments"].values())
    for k, v in o["departments"].items():   # the parts multiply to the model factor
        p = v["parts"]
        assert abs(p["history"] * p["st"] * p["fill"] - v["ml"]) < 1e-6 * v["ml"], k
    print("st_fill", {dn: {x: o["st_fill"]["by_division"][dn].get(x) for x in ("n", "lam", "on", "err_without", "err_with", "typ_st", "typ_fill")}
                      for dn in o["st_fill"]["by_division"]}, o["st_fill"]["window"])
    print("ridge by division", {dn: (round(v["mean"] * 100, 2), round(v["plain"] * 100, 2), v["wins"]) for dn, v in o["ridge"]["by_division"].items()})
    print("self-check: OK")
    if "--isolation" in sys.argv:   # no cross-division learning: change LADIES' sales, MENS / KIDS must not move
        raw = load_sales()
        raw2 = raw.copy()
        lad = raw2.division == "LADIES"
        raw2.loc[lad, "sl_v"] = raw2.loc[lad, "sl_v"] * np.random.default_rng(1).uniform(0.5, 1.5, lad.sum())
        a = build(out_path=OUT_JSON + ".iso_a", raw=raw, st=ST_ARGS, fill=load_fill())
        b = build(out_path=OUT_JSON + ".iso_b", raw=raw2, st=ST_ARGS, fill=load_fill())
        moved = [k for k in a["departments"] if not k.startswith("LADIES|") and k in b["departments"]
                 and abs(a["departments"][k]["ml_guarded"] - b["departments"][k]["ml_guarded"]) > 1e-9]
        changed = sum(1 for k in a["departments"] if k.startswith("LADIES|") and k in b["departments"]
                      and abs(a["departments"][k]["ml_guarded"] - b["departments"][k]["ml_guarded"]) > 1e-9)
        for f in (OUT_JSON + ".iso_a", OUT_JSON + ".iso_b"):
            os.remove(f)
        assert not moved, moved[:5]
        print(f"isolation: OK (LADIES changed {changed} departments, MENS / KIDS moved 0)")
