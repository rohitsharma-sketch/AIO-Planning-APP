"""AOP Realigner engine - pure functions, no I/O.

Original plan: Store x Department x MRP x Display Type rows, "<Month> Plan" value + "<Month> Plan Qty".
Revised plan:  Store x Department values per month (only the departments the buyer changed).

Three ways to revise an existing plan, all ending in the same realign (a revised Store x Dept table):
  1. store listing changes  - listing_targets(): delisted -> 0, newly listed -> sized from same-cluster peers
  2. existing dept changes  - the buyer's revised values as uploaded
  3. new / split depts      - split_targets() (parent shared out by %), or new-dept values with a COPY FROM dept
  4. listing shift          - shift_targets(): a delisted dept moves into a chosen dept / section, a listed one comes
                              out of it - nothing else moves
  5. growth changes         - growth_targets(): the dept's plan scaled to its new growth over last year
Every method's output follows the original plan's display-type cont % (verify() checks it).

Per Store x Division x Month the original total is the target. Revised departments keep their new
value exactly (split to MRP x Display Type by the original cont %); every other department in that
bucket absorbs the difference pro-rata. If revised alone exceed a month's total, the excess comes out
of the same store-division's other live months instead. Jan/Feb are never touched. Qty = value /
the original ASP for that Department x MRP x Display Type x Month.
"""
import io
import threading

import numpy as np
import pandas as pd
import xlsxwriter

TOL = 1e-9
STORE, DIV, DEPT, MRP, DISP = "Store Name", "DIVISION", "DEPARTMENT", "MRP", "DISPLAY TYPE"
FROZEN = ("Jan", "Feb")  # default lock for a newly loaded plan: Jan & Feb stay exactly as the original
LOCKED = None  # month labels the user locked (server.py sets it per original plan); None = the FROZEN default


_TL = threading.local()   # the calling user's locked months (server.py sets it per request / job; 2026-09-30)


def locked(m):
    """Is plan month m locked - kept exactly as the original (value and qty)? The user picks this per month from
    the months found in the original plan (2026-09-29); until they do, Jan / Feb are the locked months."""
    L = getattr(_TL, "locks", None)
    L = L if L is not None else LOCKED
    return m in L if L is not None else m[:3] in FROZEN


XLSX_CTYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def parent_for(dept, depts):
    """Longest existing department name that `dept` starts with (LW_U_T-TOP F/S -> LW_U_T-TOP), or None."""
    return next((p for p in sorted(depts, key=len, reverse=True) if p != dept and dept.startswith(p)), None)


KEEP_ROW_COLS = {DIV, DEPT, MRP, DISP, "ATTRIBUTE", "Tag", "CONC - UDF", "CONC - MRP", "_basis"}


def add_new_departments(o, r, months, source=None):
    """A revised dept a store never had (e.g. LW_U_T-TOP F/S) gets rows cloned from another dept's rows: same
    MRP/display rows, zero original value. The rows come from source[(store, dept)] = (from_store, from_dept)
    when given (a split parent, a COPY FROM dept, or the same dept in a peer store for a new listing), else
    from the parent_for() dept in the same store. `_basis` = the row whose values give the MRP/display mix and
    ASP (itself, or the source row for a clone). A sourced store-dept whose rows are all zero is rebuilt too."""
    source = source or {}
    o = o.reset_index(drop=True)
    if source:
        V = [m + " Plan" for m in months]
        empty = o[V].abs().sum(axis=1).groupby([o[STORE], o[DEPT]]).transform("sum").to_numpy() <= TOL
        o = o[~(pd.MultiIndex.from_arrays([o[STORE], o[DEPT]]).isin(list(source)) & empty)].reset_index(drop=True)
    o["_basis"] = np.arange(len(o))
    have = set(zip(o[STORE], o[DEPT]))
    by_store = dict(tuple(o.groupby(STORE)))
    clones, unmatched = [], []
    for s, d in zip(r[STORE], r[DEPT]):
        if (s, d) in have:
            continue
        fs, fd = source.get((s, d), (s, None))
        g = by_store.get(fs)
        if fd is None:
            fd = parent_for(d, set(g[DEPT])) if g is not None else None
        c = g[g[DEPT] == fd].copy() if g is not None and fd else None
        if c is None or not len(c):
            unmatched.append(f"{s} / {d}")
            continue
        c[DEPT] = d
        if fs != s:  # rows borrowed from another store: take this store's own name, ref, cluster and tags
            t = by_store[s]
            for col in c.columns:
                if col not in KEEP_ROW_COLS and not pd.api.types.is_numeric_dtype(c[col]):
                    c[col] = t[col].mode().iat[0]
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


def _sd_totals(o, months, by=DEPT):
    """{(store, dept or division): per-month original values}."""
    g = o.groupby([STORE, by])[[m + " Plan" for m in months]].sum()
    return dict(zip(g.index, g.to_numpy(float)))


def listing_targets(o, changes, months):
    """Method 1 - store listing changes -> (revised Store x Dept values, source rows, counts).
    changes: [{store, dept, listing "Y"/"N", start (first month index it applies from), values (list or None)}].
    Delisted: the dept goes to 0 from `start`. Newly listed: from `start` it gets the share its department has of
    the division in same-cluster stores that plan it (pooled per month; all stores if no cluster peer) x this
    store's division total - or the given values. Its MRP/display rows come from the peer store that plans the
    most of it. Frozen months (Jan/Feb) and months before `start` keep the original."""
    n = len(months)
    fz = np.array([locked(m) for m in months])
    sd, dv = _sd_totals(o, months), _sd_totals(o, months, DIV)
    div_of = o.groupby(DEPT)[DIV].agg(lambda s: s.mode().iat[0]).to_dict()
    cluster = o.groupby(STORE)["CLUSTER"].first().to_dict() if "CLUSTER" in o else {}
    planners = {}
    for (s, d), v in sd.items():
        if np.abs(v).sum() > TOL:
            planners.setdefault(d, []).append(s)
    rows, source, counts, nopeer = [], {}, {"delisted": 0, "estimated": 0, "given": 0}, []
    for c in changes:
        s, d = c["store"], c["dept"]
        base = sd.get((s, d), np.zeros(n))
        apply = (np.arange(n) >= c["start"]) & ~fz
        if c["listing"] == "N":
            vec = np.where(apply, 0.0, base)
            counts["delisted"] += 1
        else:
            peers = [p for p in planners.get(d, []) if p != s]
            peers = [p for p in peers if cluster.get(p) == cluster.get(s)] or peers
            if not peers:
                nopeer.append(f"{s} / {d}")
                continue
            source[(s, d)] = (max(peers, key=lambda p: sd[(p, d)].sum()), d)
            if c.get("values") is not None:
                vec = np.asarray(c["values"], float)
                counts["given"] += 1
            else:
                num = np.sum([sd[(p, d)] for p in peers], axis=0)
                den = np.sum([dv.get((p, div_of[d]), np.zeros(n)) for p in peers], axis=0)
                vec = np.divide(num, den, out=np.zeros(n), where=np.abs(den) > TOL) * dv.get((s, div_of[d]), np.zeros(n))
                counts["estimated"] += 1
            vec = np.where(apply, vec, base)
        rows.append({STORE: s, DEPT: d, **dict(zip(months, vec))})
    if nopeer:
        raise ValueError("No store plans these departments, so there is nothing to size or copy a new listing from "
                         "(add them with Method 3 instead): " + ", ".join(nopeer[:10]) + (" ..." if len(nopeer) > 10 else ""))
    return pd.DataFrame(rows, columns=[STORE, DEPT, *months]), source, counts


def split_targets(o, splits, months):
    """Method 3 (split) -> (revised Store x Dept values, source rows).
    splits: [{parent, child, share (0..1), store (None = every store that has the parent)}]; a store-specific row
    replaces the all-store rows of that parent in that store. In live months the parent keeps (1 - sum of shares)
    of its original value and each child gets share x the parent (on top of its own original, if it already has
    one). A new child copies the parent's MRP/display rows, so its mix and ASPs are the parent's; nothing else
    moves. Jan/Feb stay on the parent (frozen rule)."""
    n = len(months)
    live = ~np.array([locked(m) for m in months])
    sd = _sd_totals(o, months)
    target, source, over = {}, {}, []
    get = lambda k: target.setdefault(k, sd.get(k, np.zeros(n)).copy())
    for p in dict.fromkeys(x["parent"] for x in splits):
        rows = [x for x in splits if x["parent"] == p]
        for s in [s for (s, d) in sd if d == p]:
            kids = [x for x in rows if x["store"] == s] or [x for x in rows if x["store"] is None]
            if not kids:
                continue
            tot = sum(x["share"] for x in kids)
            if tot > 1 + 1e-9:
                over.append(f"{s} / {p} ({tot:.0%})")
                continue
            pv = sd[(s, p)]
            get((s, p))[live] -= pv[live] * tot
            for x in kids:
                get((s, x["child"]))[live] += pv[live] * x["share"]
                if np.abs(sd.get((s, x["child"]), np.zeros(n))).sum() <= TOL:
                    source[(s, x["child"])] = (s, p)
    if over:
        raise ValueError("Shares add up to more than 100% of the parent: " + ", ".join(over[:10]) + (" ..." if len(over) > 10 else ""))
    r = pd.DataFrame([{STORE: s, DEPT: d, **dict(zip(months, v))} for (s, d), v in target.items()], columns=[STORE, DEPT, *months])
    return r, source


def shift_targets(o, changes, months, section_of=None):
    """Method 4 - listing / delisting shifted to a chosen target -> (revised Store x Dept values, source rows, notes).
    changes: [{store, dept, listing "Y"/"N", start, values (list or None), target}]; target = a department, or a
    section (every department of that section the store plans in the same division). Delisted: its value (from
    `start`, live months) moves into the target, split by the target departments' own value that month. Listed:
    its value (sized from same-cluster peers as Method 1, or given) comes out of the target only, capped at what
    the target has. Nothing else moves, so every store x division x month total is unchanged."""
    section_of = section_of or {}
    n = len(months)
    live = ~np.array([locked(m) for m in months])
    sd = _sd_totals(o, months)
    div_sd = o.groupby([STORE, DEPT])[DIV].first().to_dict()
    div_of = o.groupby(DEPT)[DIV].agg(lambda s: s.mode().iat[0]).to_dict()
    planned = {}
    for (s, d), v in sd.items():
        if np.abs(v).sum() > TOL:
            planned.setdefault(s, set()).add(d)
    ys = [c for c in changes if c["listing"] == "Y"]
    sized, source = {}, {}
    if ys:
        r1, source, _ = listing_targets(o, ys, months)
        sized = {(s, d): np.asarray(v, float) for s, d, *v in r1.itertuples(index=False)}
    target, capped, errors, moved = {}, [], [], 0.0
    get = lambda k: target.setdefault(k, sd.get(k, np.zeros(n)).copy())
    for c in changes:
        s, d, t = c["store"], c["dept"], c["target"]
        div = div_sd.get((s, d), div_of.get(d))
        have = planned.get(s, set())
        tg = [t] if t in have else sorted(x for x in have if section_of.get(x) == t and x != d and div_sd[(s, x)] == div)
        if not tg:
            errors.append(f"{s} / {d}: target {t} isn't planned in this store")
            continue
        if any(div_sd[(s, x)] != div for x in tg):
            errors.append(f"{s} / {d}: target {t} is in another division ({div_sd[(s, tg[0])]}) - a shift must stay inside {div}")
            continue
        apply = (np.arange(n) >= c["start"]) & live
        vec = get((s, d))
        if c["listing"] == "N":
            add = np.where(apply, vec, 0.0)
            vec[apply] = 0.0
        else:
            want = np.where(apply, sized[(s, d)], 0.0)
            take = np.minimum(want, np.maximum(sum(get((s, x)) for x in tg), 0.0))
            if (want - take > 1e-9).any():
                capped.append(f"{s} / {d}")
            vec[apply] = take[apply]
            add = -take
        cur = np.array([get((s, x)) for x in tg])
        tot, season = cur.sum(0), cur[:, live].sum(1)
        w = np.where(np.abs(tot) > TOL, cur / np.where(np.abs(tot) > TOL, tot, 1),
                     (season / season.sum())[:, None] if season.sum() > TOL else 1.0 / len(tg))
        for i, x in enumerate(tg):
            get((s, x))[:] += add * w[i]
        moved += float(np.abs(add).sum())
    if errors:
        raise ValueError("; ".join(errors[:10]) + (" ..." if len(errors) > 10 else ""))
    r = pd.DataFrame([{STORE: s, DEPT: d, **dict(zip(months, v))} for (s, d), v in target.items()], columns=[STORE, DEPT, *months])
    return r, source, {"capped": capped, "moved": moved}


def ly_label(m):
    """Plan month -> the same month last year ("Sep'26" -> "Sep'25"); frozen P1/P2 halves have none."""
    return None if " " in m else f"{m[:4]}{int(m[4:6]) - 1:02d}"


def growth_targets(o, rows, months, ly):
    """Method 5 - growth changes -> (revised Store x Dept values, per-row detail).
    rows: [{dept, growth (0.12 = 12%, or None), months ({month index: growth} - optional per-month growth, each
    month judged on its own plan vs its own last year), store (None = the department in every store)}]; months
    without their own value take `growth` (season-level, keeps the phasing) or stay as planned. A store's own row replaces
    the department row for that store. ly: {(store, dept): {"Sep'25": value in the plan's units}}.
    Current growth = plan / last year over the live months, on the stores that have both (store-level for a store
    row); the department's plan in scope is scaled by (1 + new) / (1 + current) in every live month, so its month
    phasing is kept. The rest of the store x division absorbs it in realign (capped at store x division x month)."""
    live = [j for j, m in enumerate(months) if not locked(m) and ly_label(m)]
    sd = _sd_totals(o, months)
    plan_live = {k: float(v[live].sum()) for k, v in sd.items()}
    ly_live = lambda s, d: sum(float(ly.get((s, d), {}).get(ly_label(months[j]), 0.0)) for j in live)
    own = {(x["store"], x["dept"]) for x in rows if x["store"]}
    out, detail, errors = {}, [], []
    for x in rows:
        d = x["dept"]
        scope = [x["store"]] if x["store"] else [s for (s, dd), v in plan_live.items() if dd == d and abs(v) > TOL and (s, d) not in own]
        comp = [s for s in scope if plan_live.get((s, d), 0) > TOL and ly_live(s, d) > TOL]
        p, l = sum(plan_live[(s, d)] for s in comp), sum(ly_live(s, d) for s in comp)
        if not comp or l <= TOL:
            errors.append(f"{x['store'] or 'all stores'} / {d}: no last-year sales to grow from")
            continue
        cur = p / l - 1
        f = (1 + x["growth"]) / (1 + cur) if x.get("growth") is not None else 1.0
        fm, per_month = {}, []                       # per-month growth: that month's own plan vs its own last year
        for j, g in sorted((x.get("months") or {}).items()):
            pj = sum(float(sd[(s, d)][j]) for s in comp)
            lj = sum(float(ly.get((s, d), {}).get(ly_label(months[j]), 0.0)) for s in comp)
            if lj <= TOL or pj <= TOL:
                errors.append(f"{x['store'] or 'all stores'} / {d} / {months[j]}: {'no last-year sales' if lj <= TOL else 'no plan'} that month")
                continue
            fm[j] = (1 + g) * lj / pj
            per_month.append({"month": months[j], "current": pj / lj - 1, "new": g, "factor": fm[j]})
        for s in scope:
            v = sd[(s, d)].copy()
            for j in live:
                v[j] *= fm.get(j, f)
            out[(s, d)] = v
        detail.append({"store": x["store"], "dept": d, "stores": len(scope), "comparable": len(comp), "ly": l, "plan": p,
                       "current": cur, "new": x.get("growth"), "factor": f, "months": per_month})
    if errors:
        raise ValueError("; ".join(errors[:10]) + (" ..." if len(errors) > 10 else ""))
    r = pd.DataFrame([{STORE: s, DEPT: d, **dict(zip(months, v))} for (s, d), v in out.items()], columns=[STORE, DEPT, *months])
    return r, detail


def realign(o, r, months, source=None, absorb=True):
    """o: original rows (numeric cols clean), r: revised Store x Dept values over `months`, source: where a new
    store-dept's rows come from (see add_new_departments). absorb=False (Method 2 option, 2026-09-29): the other
    departments stay exactly as they are and the store-division's month totals follow the revised departments -
    a month re-phase of one department (docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md).
    Returns (realigned rows in original layout, division x month summary, warnings,
    a long-format table of every cell that actually changed - for the comparison download)."""
    V = [m + " Plan" for m in months]
    Q = [m + " Plan Qty" for m in months]
    o, n_new_sd, n_new_rows = add_new_departments(o, r, months, source)
    b = o.pop("_basis").to_numpy()
    orig, qty = o[V].to_numpy(float), o[Q].to_numpy(float)
    basis = orig[b]

    keys = pd.MultiIndex.from_arrays([o[STORE], o[DEPT]])
    rev = r.set_index([STORE, DEPT]).reindex(columns=months)
    kept = keys.isin(rev.index)   # rows the revised file keeps (was `locked`, now the month-lock helper)
    R = np.nan_to_num(rev.reindex(keys).to_numpy(float))
    frozen = np.array([locked(m) for m in months])
    # a month absent from the revised file, or a locked month (Jan/Feb by default), is never touched
    lk = kept[:, None] & rev.notna().any().to_numpy()[None, :] & ~frozen[None, :]

    # 1. split revised Store x Dept value to MRP x Display rows by that month's original cont %;
    #    a month where the dept had no plan uses the row's average cont % across the REVISED (unlocked) months it
    #    did have - falling back to every month it had only if none of those had a plan. (2026-09-29: averaging in
    #    the locked Jan / Feb months put 2,896 LW_U_T-TOP Nov / Dec rows up to 0.075 L off the user's re-phase
    #    workbook; the revised-window average reproduces it exactly and still sums to 100% per store-dept.)
    sd = (o[STORE] + "||" + o[DEPT]).to_numpy()
    gsum = pd.DataFrame(basis).groupby(sd).transform("sum").to_numpy()
    has = np.abs(gsum) > TOL
    share = np.where(has, basis / np.where(has, gsum, 1), np.nan)
    in_rev = rev.notna().any().to_numpy() & ~frozen
    win = has & in_rev[None, :]
    use = np.where(win.any(1, keepdims=True), win, has)
    n = use.sum(axis=1)   # mean over `use` without numpy's "mean of empty slice" warning (a row with none -> 0)
    avg = np.divide(np.nansum(np.where(use, share, 0.0), axis=1), n, out=np.zeros(len(o)), where=n > 0) if share.size else np.zeros(len(o))
    cnt = pd.Series(avg).groupby(sd).transform("size").to_numpy()
    avg = np.where(has.any(1), avg, 1.0 / cnt)  # dept never planned in this store -> equal split
    mix = np.where(has, share, avg[:, None])
    new = np.where(lk, R * mix, orig)
    fb_cells = int((lk & ~has & (np.abs(R) > TOL)).sum())
    # a locked month the revised file actually gives, with a different value (a locked month the file leaves out
    # is not "different" - it used to read as 0 and flag every row: 6,864 false warnings on the T-TOP re-phase)
    ignored = int((kept[:, None] & (frozen & rev.notna().any().to_numpy())[None, :]
                   & (np.abs(R - pd.DataFrame(orig).groupby(sd).transform("sum").to_numpy()) > 1e-6)).any(1).sum())

    # 2. every other department in the Store x Division x Month absorbs the difference pro-rata. Revised
    #    values are never changed: if they alone exceed a month's total, the other departments go to 0 that
    #    month and the excess is taken from the same store-division's other live months (in proportion to
    #    their room), so the store x division season total - and the grand total - still match the original.
    grp = (o[STORE] + "||" + o[DIV]).to_numpy()
    if absorb:
        T = pd.DataFrame(orig).groupby(grp).transform("sum").to_numpy()
        L = pd.DataFrame(np.where(lk, new, 0.0)).groupby(grp).transform("sum").to_numpy()
        U = pd.DataFrame(np.where(lk, 0.0, orig)).groupby(grp).transform("sum").to_numpy()
        live = (rev.notna().any().to_numpy() & ~frozen)[None, :]
        has_u = np.abs(U) > TOL
        over = live & (L > T + TOL)
        excess = np.where(over, L - T, 0.0).sum(1, keepdims=True)
        room = np.where(live & ~over & has_u, np.clip(T - L, 0, None), 0.0)
        room_tot = room.sum(1, keepdims=True)
        take = np.where(room_tot > TOL, room * np.minimum(excess / np.where(room_tot > TOL, room_tot, 1), 1.0), 0.0)
        Tadj = T - take
        f = np.where(has_u & ~over, (Tadj - L) / np.where(has_u, U, 1), 0.0)
        new = np.where(lk, new, orig * f)
        spilled = over.any(1)
        unplaced = excess[:, 0] - take.sum(1)  # excess with no room left in any other month
        # nothing left to absorb into (bucket stays under target), or excess that couldn't be placed (stays over)
        short = ((~has_u) & live & (Tadj - L > 1e-6)).any(1) | (unplaced > 1e-6)
    else:
        # only the revised departments move; every other row is the original (f = 1, nothing spills or is short)
        f = np.ones_like(orig)
        new = np.where(lk, new, orig)
        excess = np.zeros((len(o), 1))
        spilled = short = np.zeros(len(o), bool)

    # 3. qty = new value / the original plan's ASP for that Department x MRP x Display Type x Month, pooled
    #    across stores (in the original it's identical across stores anyway). A new dept uses its parent's.
    #    No qty for that combo that month -> the combo's all-month ASP -> MRP. Unchanged cells keep their qty.
    key = (pd.Series(o[DEPT].to_numpy()[b]) + "||" + o[MRP].astype(str) + "||" + o[DISP]).to_numpy()
    qm = np.abs(qty) > TOL
    num = pd.DataFrame(np.where(qm, orig, 0.0)).groupby(key).transform("sum").to_numpy()
    den = pd.DataFrame(np.where(qm, qty, 0.0)).groupby(key).transform("sum").to_numpy()
    def _ratio(n, d):
        r = np.divide(n, d, out=np.zeros_like(n, dtype=float), where=np.abs(d) > TOL)
        return np.where(r > TOL, r, np.nan)
    asp_m, asp_all = _ratio(num, den), _ratio(num.sum(1), den.sum(1))
    asp_all = np.where(np.isnan(asp_all), pd.to_numeric(o[MRP], errors="coerce").fillna(0).to_numpy() / 1e5, asp_all)
    asp = np.where(np.isnan(asp_m), asp_all[:, None], asp_m)
    moved = np.abs(new - orig) > 1e-12
    new_qty = np.where(moved, np.divide(new, asp, out=np.zeros_like(new), where=asp > TOL), qty)
    asp_fb = int((moved & np.isnan(asp_m) & (np.abs(new) > TOL)).sum())

    # 4. comparison table: every cell that actually moved, tagged with why - the "did this come out
    #    okay" check against the original. "kept" = a revised row; "absorbed" = everything else that
    #    moved to make room (frozen months never change - f==1 there - so they're filtered out).
    status = np.where(lk, "kept", np.where(np.abs(f - 1) > TOL, "absorbed", "unchanged"))
    delta = new - orig
    changed = np.abs(delta) > 1e-6
    if changed.any():
        ri, ci = np.nonzero(changed)
        ov, nv = orig[ri, ci], new[ri, ci]
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = np.where(np.abs(ov) > TOL, (nv - ov) / np.abs(ov) * 100, np.nan)
        compare = pd.DataFrame({
            STORE: o[STORE].to_numpy()[ri], DIV: o[DIV].to_numpy()[ri], DEPT: o[DEPT].to_numpy()[ri],
            MRP: o[MRP].to_numpy()[ri], DISP: o[DISP].to_numpy()[ri], "Month": np.asarray(months)[ci],
            "Original": ov, "Realigned": nv, "Delta": nv - ov, "Delta %": pct, "Status": status[ri, ci],
        })
    else:
        compare = pd.DataFrame(columns=[STORE, DIV, DEPT, MRP, DISP, "Month", "Original", "Realigned", "Delta", "Delta %", "Status"])

    o[V], o[Q] = new, new_qty

    summ = []
    for d, g in o.groupby(DIV):
        i = g.index.to_numpy()
        for j, m in enumerate(months):
            summ.append({"division": d, "month": m, "original": float(orig[i, j].sum()), "final": float(new[i, j].sum()),
                         "revised_before": float(orig[i, j][kept[i]].sum()), "revised_after": float(new[i, j][kept[i]].sum())})
    spilled_sd = sorted({f"{s}/{d}" for s, d in zip(o[STORE][spilled], o[DIV][spilled])})
    spilled_amt = float(pd.Series(excess[:, 0]).groupby(grp).first().sum())
    short_sd = sorted({f"{s}/{d}" for s, d in zip(o[STORE][short], o[DIV][short])})
    warn = []
    if n_new_sd:
        warn.append(f"{n_new_sd} new store-departments created ({n_new_rows} MRP/display rows) from their parent department's rows.")
    if fb_cells:
        warn.append(f"{fb_cells} revised row-months had no original plan that month; split by the row's average cont % across the revised months that had a plan.")
    if ignored:
        warn.append(f"{ignored} revised rows had values in locked months different from the original - ignored, locked months stay as original.")
    if spilled_sd:
        warn.append(f"{len(spilled_sd)} store-division(s) had revised departments exceeding a month's original total - "
                    f"revised kept exactly, other departments set to 0 that month, and the excess ({spilled_amt:.4f}) taken "
                    f"from the same store-division's other live months, so its season total still matches: {', '.join(spilled_sd[:15])}")
    if asp_fb:
        warn.append(f"{asp_fb} changed row-months had no original qty for their Department x MRP x Display Type that month - "
                    f"qty uses that combination's all-month ASP instead.")
    if short_sd:
        warn.append(f"{len(short_sd)} store-division(s) couldn't fully land on the original total (no other department "
                    f"or month left to absorb into): {', '.join(short_sd[:15])}")
    return o, summ, warn, compare


def verify(o, r, out, months, absorb=True):
    """Independent after-the-fact checks of a realign result, plus a per-department table of
    original vs revised (file) vs realigned (output) - the numbers a planner would eyeball.
    absorb=False (other departments kept as they are): the store-division checks become information - the month
    totals are meant to follow the revised departments - and two checks take their place: every other department
    is untouched, and each revised store-department keeps its season total (a re-phase moves value between months)."""
    V = [m + " Plan" for m in months]
    rm = [m for m in months if m in r.columns]
    live = [m for m in rm if not locked(m)]
    fz = [m for m in months if locked(m)]
    checks = []
    add = lambda name, status, detail: checks.append({"name": name, "status": status, "detail": detail})

    keys = pd.MultiIndex.from_frame(r[[STORE, DEPT]])
    out_sd = out.groupby([STORE, DEPT])[V].sum().reindex(keys).fillna(0.0)
    orig_sd = o.groupby([STORE, DEPT])[V].sum().reindex(keys).fillna(0.0)
    if live and len(r):
        diff = float(np.abs(out_sd[[m + " Plan" for m in live]].to_numpy() - r[live].to_numpy()).max())
        add("Revised values kept exactly", "ok" if diff < 1e-6 else "fail", f"largest difference {diff:.2g}")
    a = o.groupby([STORE, DIV])[V].sum()
    d = (out.groupby([STORE, DIV])[V].sum().reindex(a.index).fillna(0.0) - a).to_numpy()
    season, cells = int((np.abs(d.sum(1)) > 1e-6).sum()), int((np.abs(d) > 1e-6).sum())
    g0, g1 = float(o[V].to_numpy().sum()), float(out[V].to_numpy().sum())
    if absorb:
        add("Store × Division totals match — whole season", "ok" if season == 0 else "fail",
            f"{season} of {len(a):,} store-divisions differ")
        add("Store × Division totals match — each month", "ok" if cells == 0 else "warn",
            f"{cells} of {d.size:,} store-division-months differ" +
            ("" if cells == 0 else " (where a revised department exceeded its month, the excess moved to other months)"))
        add("Grand total unchanged", "ok" if abs(g1 - g0) < 1e-6 else "fail", f"{g0:,.2f} → {g1:,.2f}")
    else:
        k = [STORE, DEPT, MRP, DISP]
        rev_sd = set(zip(r[STORE], r[DEPT]))
        mine = pd.Series([(s, dp) in rev_sd for s, dp in zip(o[STORE], o[DEPT])], index=o.index)
        a_rest = o[~mine].set_index(k)[V]
        b_rest = out.set_index(k)[V].reindex(a_rest.index).fillna(0.0)
        rd = float(np.abs(b_rest.to_numpy() - a_rest.to_numpy()).max()) if len(a_rest) else 0.0
        add("Other departments untouched", "ok" if rd < 1e-9 else "fail", f"{len(a_rest):,} rows · largest change {rd:.2g}")
        lv = [m + " Plan" for m in live]
        sd_moved = int((np.abs(out_sd[lv].sum(axis=1) - orig_sd[lv].sum(axis=1)) > 1e-6).sum()) if lv else 0
        add("Revised departments keep their season total", "ok" if sd_moved == 0 else "warn",
            f"{sd_moved} of {len(keys):,} revised store-departments changed their season total"
            + ("" if sd_moved == 0 else " - the revised file changes the total, not just the months"))
        add("Store × Division month totals", "info",
            f"{cells} of {d.size:,} store-division-months moved with the revised departments (other departments kept)")
        add("Grand total", "ok" if abs(g1 - g0) < 1e-6 else "info", f"{g0:,.2f} → {g1:,.2f}")
    if fz:
        cols = [m + " Plan" for m in fz] + [m + " Plan Qty" for m in fz]
        k = [STORE, DEPT, MRP, DISP]  # by key: a rebuilt empty store-dept can move rows around
        a = o.set_index(k)[cols]
        fd = float(np.abs(out.set_index(k)[cols].reindex(a.index).fillna(0.0).to_numpy() - a.to_numpy()).max())
        add("Locked months untouched (value and qty)", "ok" if fd < 1e-9 else "fail", f"largest change {fd:.2g}")
    # user rule for every method: the output follows the ORIGINAL plan's display-type cont % in each
    # store x department x month that has a plan both before and after
    k = [STORE, DEPT, DISP]
    a = o.groupby(k)[V].sum()
    b = out.groupby(k)[V].sum().reindex(a.index).fillna(0.0)
    at, bt = a.groupby(level=[0, 1]).transform("sum"), b.groupby(level=[0, 1]).transform("sum")
    both = (at.abs() > 1e-9) & (bt.abs() > 1e-9)
    dd = float(np.abs((a / at.where(both, 1) - b / bt.where(both, 1)).where(both, 0.0)).to_numpy().max()) if len(a) else 0.0
    n_sdm = int(((a.groupby(level=[0, 1]).sum().abs() > 1e-9) & (b.groupby(level=[0, 1]).sum().abs() > 1e-9)).to_numpy().sum())
    add("Display-type cont % kept as in the original", "ok" if dd < 1e-6 else "fail",
        f"{n_sdm:,} store-department-months checked · largest share difference {dd:.2g}")

    table = []
    rv = r.set_index([STORE, DEPT])
    for dept in dict.fromkeys(r[DEPT]):
        sel = keys.get_level_values(1) == dept
        table.append({"dept": dept, "stores": int(sel.sum()), "months": [
            {"month": m, "original": float(orig_sd[m + " Plan"].to_numpy()[sel].sum()),
             "revised": float(rv[m].to_numpy()[sel].sum()), "realigned": float(out_sd[m + " Plan"].to_numpy()[sel].sum())}
            for m in rm]})
    return checks, table


def _cell(v):
    """numpy scalar -> native Python, and NaN/Inf -> blank (xlsxwriter can't write either directly)."""
    if hasattr(v, "item"):
        v = v.item()
    return None if isinstance(v, float) and not np.isfinite(v) else v


def write_xlsx(sheets, on_progress=None):
    """sheets: [(name, df), ...]. Written row by row with xlsxwriter's own API (not pandas' .to_excel)
    so on_progress(done, total) can report real rows - the full plan is ~680k rows and takes minutes."""
    total = sum(len(df) for _, df in sheets)
    tick = on_progress or (lambda done, total: None)
    tick(0, total)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "constant_memory": True})
    done = 0
    for name, df in sheets:
        ws = wb.add_worksheet(name[:31])  # Excel's own sheet-name length limit
        for j, c in enumerate(df.columns):
            ws.write(0, j, str(c))
        for i, row in enumerate(df.itertuples(index=False, name=None)):
            ws.write_row(i + 1, 0, [_cell(v) for v in row])
            if i % 3000 == 0:
                tick(done + i, total)
        done += len(df)
        tick(done, total)
    wb.close()
    return buf.getvalue()


def export(df, fmt, on_progress=None):
    """csv ~9s; xlsx ~2.5 min for the full 680k-row plan."""
    if fmt == "csv":
        return df.round(6).to_csv(index=False).encode("utf-8-sig"), "text/csv", "csv"
    return write_xlsx([("Realigned Plan", df.round(6))], on_progress), XLSX_CTYPE, "xlsx"


def export_compare(summ, compare, fmt, on_progress=None):
    """The "did this come out okay" file: a Division x Month summary plus every cell that actually changed."""
    if fmt == "csv":
        return compare.round(4).to_csv(index=False).encode("utf-8-sig"), "text/csv", "csv"
    return write_xlsx([("Summary", pd.DataFrame(summ).round(4)), ("Changed Rows", compare.round(4))], on_progress), XLSX_CTYPE, "xlsx"
