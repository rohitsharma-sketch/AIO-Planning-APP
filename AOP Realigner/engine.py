"""Sales Plan Re-Aligner engine - pure functions, no I/O.

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

Per Store x Division x Attribute x Month the original total is the target - the cap (user, 2026-10-01: a department
change stays inside its own attribute, no cross-attribute apportioning). Revised departments keep their new value
exactly (split to MRP x Display Type by the original cont %); every other department in that bucket absorbs the
difference pro-rata. If revised alone exceed a month's total, the excess comes out of the same bucket's other live
months instead. A plan without an ATTRIBUTE column falls back to Store x Division x Month. Jan/Feb are never touched. Qty = value /
the original ASP for that Department x MRP x Display Type x Month.
"""
import io
import threading

import numpy as np
import pandas as pd
import xlsxwriter

TOL = 1e-9
SHOWN = 5e-9   # the comparison shows 8 decimals: any difference that would show there counts (user, 2026-09-30)
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
ATTR = "ATTRIBUTE"


def has_attr(o):
    return ATTR in o.columns


def cap_label(o):
    """The cap level, as the checks and the comparison name it."""
    return "Store × Division × Attribute × Month" if has_attr(o) else "Store × Division × Month"


def cap_key(o, div_cap=None):
    """Per row, its cap bucket (less the month): store||division||attribute (user, 2026-10-01: "apportion and match at
    Store x Division x Attribute x Month ... so that the department changes made are contained within the attribute");
    store||division when the plan has no ATTRIBUTE column, and for the (store, division) pairs in `div_cap` - a store x
    division with a new listing, whose AOP is re-split over all its departments (user, 2026-10-01: "store x division aop
    will be multiplied on store's cont %")."""
    k = o[STORE].astype(str) + "||" + o[DIV].astype(str)
    if not has_attr(o):
        return k.to_numpy()
    ka = k + "||" + o[ATTR].fillna("").astype(str)
    if div_cap:
        at_div = pd.MultiIndex.from_arrays([o[STORE], o[DIV]]).isin([tuple(x) for x in div_cap])
        ka = ka.where(~at_div, k)
    return ka.to_numpy()


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


def listing_targets(o, changes, months, ref_of=None):
    """Method 1 - store listing changes -> (revised Store x Dept values, source rows, counts, how each listing was sized).
    changes: [{store, dept, listing "Y"/"N", start (first month index it applies from), values (list or None)}].
    Delisted: the dept goes to 0 from `start`. Newly listed (user, 2026-10-01: "first ... look for reference store cont
    % if not found then only cluster cont %"): from `start` it gets, month by month, the department's cont % of its
    division in the store's REF store (ref_of[store]) when that store plans it, else pooled over the same-cluster
    stores that plan it (all stores if none), x this store's division AOP - or the given values. Its MRP/display rows
    come from that REF store, else the peer that plans the most of it. Frozen months and months before `start` keep
    the original."""
    n = len(months)
    fz = np.array([locked(m) for m in months])
    sd, dv = _sd_totals(o, months), _sd_totals(o, months, DIV)
    div_of = o.groupby(DEPT)[DIV].agg(lambda s: s.mode().iat[0]).to_dict()
    cluster = o.groupby(STORE)["CLUSTER"].first().to_dict() if "CLUSTER" in o else {}
    planners = {}
    for (s, d), v in sd.items():
        if np.abs(v).sum() > TOL:
            planners.setdefault(d, []).append(s)
    ref_of = ref_of or {}
    rows, source, counts, nopeer, how = [], {}, {"delisted": 0, "estimated": 0, "given": 0, "ref": 0}, [], []
    for c in changes:
        s, d = c["store"], c["dept"]
        base = sd.get((s, d), np.zeros(n))
        apply = (np.arange(n) >= c["start"]) & ~fz
        if c["listing"] == "N":
            vec = np.where(apply, 0.0, base)
            counts["delisted"] += 1
        else:
            peers = [p for p in planners.get(d, []) if p != s]
            ref = ref_of.get(s)
            if ref and ref != s and ref in peers:
                peers, frm = [ref], "REF store"
            else:
                same = [p for p in peers if cluster.get(p) == cluster.get(s)]
                peers, frm = (same, "cluster") if same else (peers, "all stores planning it")
            if not peers:
                nopeer.append(f"{s} / {d}")
                continue
            source[(s, d)] = (max(peers, key=lambda p: sd[(p, d)].sum()), d)
            num = np.sum([sd[(p, d)] for p in peers], axis=0)
            den = np.sum([dv.get((p, div_of[d]), np.zeros(n)) for p in peers], axis=0)
            cont = np.divide(num, den, out=np.zeros(n), where=np.abs(den) > TOL)   # the department's cont % of the division
            aop = dv.get((s, div_of[d]), np.zeros(n))                              # this store's division AOP
            if c.get("values") is not None:
                vec = np.asarray(c["values"], float)
                counts["given"] += 1
            else:
                vec = cont * aop
                counts["estimated"] += 1
                counts["ref"] += frm == "REF store"
            vec = np.where(apply, vec, base)
            how.append({STORE: s, DIV: div_of[d], DEPT: d, "LISTED FROM": months[c["start"]],
                        "SIZED FROM": "your values" if c.get("values") is not None else frm,
                        "CONT % FROM": ", ".join(peers[:5]) + (f" +{len(peers) - 5} more" if len(peers) > 5 else ""),
                        **{f"{m} CONT %": cont[j] * 100 for j, m in enumerate(months) if apply[j]},
                        **{f"{m} DIVISION AOP": aop[j] for j, m in enumerate(months) if apply[j]},
                        **{f"{m} NEW": vec[j] for j, m in enumerate(months) if apply[j]}})
        rows.append({STORE: s, DEPT: d, **dict(zip(months, vec))})
    if nopeer:
        raise ValueError("No store plans these departments, so there is nothing to size or copy a new listing from "
                         "(add them with Method 3 instead): " + ", ".join(nopeer[:10]) + (" ..." if len(nopeer) > 10 else ""))
    return pd.DataFrame(rows, columns=[STORE, DEPT, *months]), source, counts, how


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
    the target has. Nothing else moves, so every store x division x attribute x month total is unchanged (the target
    must be in the same division and attribute)."""
    section_of = section_of or {}
    n = len(months)
    live = ~np.array([locked(m) for m in months])
    sd = _sd_totals(o, months)
    div_sd = o.groupby([STORE, DEPT])[DIV].first().to_dict()
    div_of = o.groupby(DEPT)[DIV].agg(lambda s: s.mode().iat[0]).to_dict()
    attr_of = o.groupby(DEPT)[ATTR].first().to_dict() if has_attr(o) else {}   # one attribute per department
    planned = {}
    for (s, d), v in sd.items():
        if np.abs(v).sum() > TOL:
            planned.setdefault(s, set()).add(d)
    ys = [c for c in changes if c["listing"] == "Y"]
    sized, source = {}, {}
    if ys:
        r1, source, _, _ = listing_targets(o, ys, months)
        sized = {(s, d): np.asarray(v, float) for s, d, *v in r1.itertuples(index=False)}
    target, capped, errors, moved = {}, [], [], 0.0
    get = lambda k: target.setdefault(k, sd.get(k, np.zeros(n)).copy())
    for c in changes:
        s, d, t = c["store"], c["dept"], c["target"]
        div = div_sd.get((s, d), div_of.get(d))
        have = planned.get(s, set())
        tg = [t] if t in have else sorted(x for x in have if section_of.get(x) == t and x != d and div_sd[(s, x)] == div
                                          and attr_of.get(x) == attr_of.get(d))
        if not tg:
            errors.append(f"{s} / {d}: target {t} isn't planned in this store")
            continue
        if any(div_sd[(s, x)] != div for x in tg):
            errors.append(f"{s} / {d}: target {t} is in another division ({div_sd[(s, tg[0])]}) - a shift must stay inside {div}")
            continue
        if any(attr_of.get(x) != attr_of.get(d) for x in tg):   # the cap is per attribute: no cross-attribute shift
            errors.append(f"{s} / {d}: target {t} is in another attribute ({attr_of.get(tg[0])}) - a shift must stay "
                          f"inside {attr_of.get(d)}")
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
    phasing is kept. The rest of its store x division x attribute absorbs it in realign (the cap)."""
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


def _take_back(new, add, pool, key):
    """Take `add` (per cell, >= 0) back out of the `pool` cells of the same key x month, pro-rata to their value.
    Returns (new, the part of `add` per cell that found no room)."""
    need = pd.DataFrame(add).groupby(key).transform("sum").to_numpy()
    room = np.where(pool, new, 0.0)
    rsum = pd.DataFrame(room).groupby(key).transform("sum").to_numpy()
    took = np.minimum(need, rsum)
    new = new - room * np.divide(took, rsum, out=np.zeros_like(rsum), where=rsum > TOL)
    return new, add * (1 - np.divide(took, need, out=np.zeros_like(need), where=need > TOL))


def realign(o, r, months, source=None, div_cap=None):
    """o: original rows (numeric cols clean), r: revised Store x Dept values over `months`, source: where a new
    store-dept's rows come from (see add_new_departments). Every store x division x attribute x month lands on the
    original - the cap (the "other departments stay as they are" option was removed, user 2026-09-30).
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

    # 2. every other department in the Store x Division x Attribute x Month absorbs the difference pro-rata, so each
    #    lands exactly on the original - the cap (user, 2026-09-30: "cap the target for the month x store x division";
    #    2026-10-01: at attribute level, so a change never spills into another attribute). If the revised departments
    #    alone exceed a month's cap, they are cut to it (the other departments go to 0 that month) and the cut moves
    #    to the same revised departments' other live months that still have room (other departments shrink there by
    #    the same amount) - so every month total AND the revised departments' season total still match. Only excess
    #    with no room anywhere stays over its month (flagged).
    grp = cap_key(o, div_cap)   # a store x division with a new listing (Method 1) is capped at division level
    T = pd.DataFrame(orig).groupby(grp).transform("sum").to_numpy()
    L = pd.DataFrame(np.where(lk, new, 0.0)).groupby(grp).transform("sum").to_numpy()
    U = pd.DataFrame(np.where(lk, 0.0, orig)).groupby(grp).transform("sum").to_numpy()
    live = (rev.notna().any().to_numpy() & ~frozen)[None, :]
    has_u = np.abs(U) > TOL
    over = live & (L > T + TOL)
    excess = np.where(over, L - T, 0.0).sum(1, keepdims=True)
    # room = months where the revised departments have a value to grow and other departments can give way
    room = np.where(live & ~over & has_u & (L > TOL), np.clip(T - L, 0, None), 0.0)
    room_tot = room.sum(1, keepdims=True)
    take = np.where(room_tot > TOL, room * np.minimum(excess / np.where(room_tot > TOL, room_tot, 1), 1.0), 0.0)
    placed = np.divide(take.sum(1, keepdims=True), excess, out=np.zeros_like(excess), where=excess > TOL)
    Lnew = np.where(over, L - (L - T) * placed, L + take)   # the revised departments' month total after the move
    scale = np.where(lk & (L > TOL), Lnew / np.where(L > TOL, L, 1), 1.0)   # 1 = a revised cell kept exactly
    new = np.where(lk, new * scale, new)
    f = np.where(has_u & ~over, (T - Lnew) / np.where(has_u, U, 1), 0.0)
    new = np.where(lk, new, orig * f)
    spilled = over.any(1)
    unplaced = excess[:, 0] - take.sum(1)  # excess with no room left in any other month
    # nothing left to absorb into (bucket stays under target), or excess that couldn't be placed (stays over)
    short = ((~has_u) & live & (T - Lnew > 1e-6)).any(1) | (unplaced > 1e-6)

    # 2b. no negative plan (user, 2026-10-01: "if there was a plan of -0.01 ... it should be covered to 0 and the balance
    #     should follow the rules set for apportion ... readjusting the value to its respective store x div x attribute x
    #     month after apportion"). In every unlocked month a negative cell becomes 0 and what that adds comes back out
    #     of the same bucket by the apportion rules: a revised department's row out of that department's own positive
    #     rows (its value stays as given), anything else - or what the department couldn't cover - out of the other
    #     departments' positive cells pro-rata, then the revised ones'; so the cap still holds. Locked months are never
    #     changed, negatives included.
    neg = (new < -TOL) & ~frozen[None, :]
    neg_amt, neg_left = float(-new[neg].sum()), 0.0
    if neg.any():
        add = np.where(neg, -new, 0.0)
        new = np.where(neg, 0.0, new)
        new, left = _take_back(new, np.where(lk, add, 0.0), lk & (new > TOL), sd)
        new, left = _take_back(new, np.where(lk, 0.0, add) + left, ~lk & (new > TOL) & ~frozen[None, :], grp)
        new, left = _take_back(new, left, lk & (new > TOL), grp)
        neg_left = float(left.sum())


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
    status = np.where(lk, np.where(np.abs(scale - 1) > TOL, "kept, moved to fit the cap", "kept"),
                      np.where(np.abs(new - orig) > TOL, "absorbed", "unchanged"))
    status = np.where(neg, "negative set to 0", status)
    delta = new - orig
    changed = np.abs(delta) > SHOWN
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
    lab = np.char.replace(grp.astype(str), "||", "/")
    spilled_sd = sorted(set(lab[spilled]))
    spilled_amt = float(pd.Series(excess[:, 0]).groupby(grp).first().sum())
    short_sd = sorted(set(lab[short]))
    bucket = "store-division-attribute(s)" if has_attr(o) else "store-division(s)"
    warn = []
    if n_new_sd:
        warn.append(f"{n_new_sd} new store-departments created ({n_new_rows} MRP/display rows) from their parent department's rows.")
    if fb_cells:
        warn.append(f"{fb_cells} revised row-months had no original plan that month; split by the row's average cont % across the revised months that had a plan.")
    if ignored:
        warn.append(f"{ignored} revised rows had values in locked months different from the original - ignored, locked months stay as original.")
    if spilled_sd:
        warn.append(f"{len(spilled_sd)} {bucket} had revised departments exceeding a month's cap (the original "
                    f"{cap_label(o).lower()} total) - cut to the cap, other departments 0 that month, and the excess "
                    f"({spilled_amt:.4f}) moved into the same revised departments' other months, so every month total and "
                    f"their season total still match: {', '.join(spilled_sd[:15])}")
    if neg.any():
        warn.append(f"{int(neg.sum()):,} negative plan cells (total {-neg_amt:.6f}) set to 0 in the unlocked months; the "
                    f"balance came back out of the same {cap_label(o).lower()} by the apportion rules"
                    + (f" - {neg_left:.6f} found no positive plan to come out of (flagged)" if neg_left > 1e-9 else "") + ".")
    if asp_fb:
        warn.append(f"{asp_fb} changed row-months had no original qty for their Department x MRP x Display Type that month - "
                    f"qty uses that combination's all-month ASP instead.")
    if short_sd:
        warn.append(f"{len(short_sd)} {bucket} couldn't fully land on the original total (no other department "
                    f"of the same attribute, or month, left to absorb into): {', '.join(short_sd[:15])}")
    return o, summ, warn, compare


def verify(o, r, out, months, div_cap=None):
    """Independent after-the-fact checks of a realign result, plus a per-department table of
    original vs revised (file) vs realigned (output) - the numbers a planner would eyeball."""
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
        lvp = [m + " Plan" for m in live]
        dm = np.abs(out_sd[lvp].to_numpy() - r[live].to_numpy())
        diff, moved = float(dm.max()), int((dm > 1e-6).sum())
        season_kept = float(np.abs(out_sd[lvp].to_numpy().sum(1) - r[live].to_numpy().sum(1)).max())
        if diff < 1e-6:
            add("Revised values kept exactly", "ok", f"largest difference {diff:.2g}")
        elif season_kept < 1e-6:   # moved between months only to fit the cap
            add("Revised values kept exactly", "warn", f"{moved} revised store-department-months moved to fit the "
                f"{cap_label(o).lower()} cap (largest {diff:.4f}); every revised store-department keeps its season total")
        else:
            add("Revised values kept exactly", "fail", f"largest difference {diff:.2g}")
    a = o.groupby([STORE, DIV])[V].sum()
    d = (out.groupby([STORE, DIV])[V].sum().reindex(a.index).fillna(0.0) - a).to_numpy()
    season, cells = int((np.abs(d.sum(1)) > SHOWN).sum()), int((np.abs(d) > SHOWN).sum())
    g0, g1 = float(o[V].to_numpy().sum()), float(out[V].to_numpy().sum())
    add("Store × Division totals match — whole season", "ok" if season == 0 else "fail",
        f"{season} of {len(a):,} store-divisions differ")
    if has_attr(o):   # the cap is per attribute; the division month total follows from it
        ka, kb = cap_key(o, div_cap), cap_key(out, div_cap)
        ca = o.groupby(ka)[V].sum()
        dc = (out.groupby(kb)[V].sum().reindex(ca.index).fillna(0.0) - ca).to_numpy()
        cc = int((np.abs(dc) > SHOWN).sum())
        add(f"{cap_label(o)} = original (the cap)", "ok" if cc == 0 else "fail",
            f"{cc} of {dc.size:,} store-division-attribute-months differ from the original file" +
            ("" if cc == 0 else f" (largest {float(np.abs(dc).max()):.4f}) - see the {CAP_SHEET} sheet of the comparison")
            + (f"; {len(div_cap)} store-division(s) with a new listing are capped at store x division" if div_cap else ""))
    add("Store × Division × Month = original" + ("" if has_attr(o) else " (the cap)"), "ok" if cells == 0 else "fail",
        f"{cells} of {d.size:,} store-division-months differ from the original file" +
        ("" if cells == 0 else f" (largest {float(np.abs(d).max()):.4f}) - see the comparison"))
    add("Grand total unchanged", "ok" if abs(g1 - g0) < 1e-6 else "fail", f"{g0:,.2f} → {g1:,.2f}")
    lv = [m + " Plan" for m in months if not locked(m)]
    nn = int((out[lv].to_numpy(float) < -TOL).sum()) if lv else 0
    add("No negative plan in the unlocked months", "ok" if nn == 0 else "fail", f"{nn} negative cells")
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
    # a store-dept-month whose original had a negative row is left out: that row is set to 0, so its mix moves by design
    had_neg = (o[V] < -TOL).groupby([o[STORE], o[DEPT]]).any().reindex(a.index.droplevel(2)).to_numpy()
    a, b = a.where(~had_neg, 0.0), b.where(~had_neg, 0.0)
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


def write_xlsx(sheets, on_progress=None, num_format=None):
    """sheets: [(name, df), ...]. Written row by row with xlsxwriter's own API (not pandas' .to_excel)
    so on_progress(done, total) can report real rows - the full plan is ~680k rows and takes minutes.
    num_format (e.g. "0.00000000") is applied to every float column, so Excel shows the figures in full."""
    total = sum(len(df) for _, df in sheets)
    tick = on_progress or (lambda done, total: None)
    tick(0, total)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "constant_memory": True})
    done = 0
    fmt = wb.add_format({"num_format": num_format}) if num_format else None
    for name, df in sheets:
        ws = wb.add_worksheet(name[:31])  # Excel's own sheet-name length limit
        if fmt:
            for j, c in enumerate(df.columns):
                if pd.api.types.is_float_dtype(df[c]):
                    ws.set_column(j, j, 14, fmt)
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


def compare_levels(o, out, months, div_cap=None):
    """Original plan vs the new plan at the two levels a planner checks (user, 2026-09-30: "a comparitive ... original
    plan v new revised plan ... to see where the difference is"):
      the cap level (Store x Division x Attribute x Month, or x Division x Month without attributes) - EVERY cell,
        with "Within cap" (the original file's total is the cap);
      Store x Dept x Month - the cells that moved."""
    V = [m + " Plan" for m in months]
    def long(df, by):
        g = df.groupby(by, dropna=False)[V].sum()
        g.columns = pd.Index(months, name="Month")
        return g.stack()
    def table(by, only_moved):
        a, b = long(o, by), long(out, by)
        idx = a.index.union(b.index)
        t = pd.DataFrame({"Original": a.reindex(idx).fillna(0.0), "New plan": b.reindex(idx).fillna(0.0)})
        t["Difference"] = t["New plan"] - t["Original"]
        t["Difference %"] = np.where(t["Original"].abs() > TOL, t["Difference"] / t["Original"].abs() * 100, np.nan)
        t = t.reset_index()
        t["Month"] = pd.Categorical(t["Month"], categories=months, ordered=True)
        t = t.sort_values(by + ["Month"]).reset_index(drop=True)
        t["Month"] = t["Month"].astype(str)
        t["Locked month"] = np.where([locked(m) for m in t["Month"]], "Yes", "")
        return t[t["Difference"].abs() > SHOWN].reset_index(drop=True) if only_moved else t
    sdm = table([STORE, DIV, ATTR] if has_attr(o) else [STORE, DIV], False)
    sdm["Within cap"] = np.where(sdm["Difference"].abs() <= SHOWN, "Yes",
                                 np.where(sdm["Difference"] > 0, "No - over the original", "No - under the original"))
    if div_cap and has_attr(o):   # a new listing re-splits the whole store x division: its attributes may move
        dl = pd.MultiIndex.from_arrays([sdm[STORE], sdm[DIV]]).isin([tuple(x) for x in div_cap])
        sdm.loc[dl & (sdm["Within cap"] != "Yes"), "Within cap"] = "n/a - new listing, capped at store x division"
    return sdm, table([STORE, DIV, DEPT], True)


CAP_SHEET = "Store x Div x Attribute x Month"   # 31 characters, Excel's sheet-name limit


def export_compare(summ, compare, fmt, on_progress=None, levels=None):
    """The "did this come out okay" file: a Division x Month summary, the Store x Division x Month cap check and the
    Store x Dept x Month moves (levels = compare_levels(...)), plus every cell that actually changed."""
    if fmt == "csv":
        return _r8(compare).to_csv(index=False, float_format="%.8f").encode("utf-8-sig"), "text/csv", "csv"
    sheets = [("Summary", _r8(pd.DataFrame(summ)))]
    if levels is not None:
        cap = CAP_SHEET if ATTR in levels[0].columns else "Store x Division x Month"
        sheets += [(cap, _r8(levels[0])), ("Store x Dept x Month", _r8(levels[1]))]
    return write_xlsx(sheets + [("Changed Rows", _r8(compare))], on_progress, "0.00000000"), XLSX_CTYPE, "xlsx"


def plan_to_plan(o, out, months):
    """The whole plan, original vs final, row for row (user, 2026-10-01: "a full plan to plan comparison not just the
    changes ... a full display type plan mapping original vs final so that i can easily point where the changes are
    made"): every Store x Dept x MRP x Display Type row of either plan, Changed / Months changed up front to filter on,
    then per month Original / Final / Difference and the season. A row only in the final plan (a new department) shows
    "new in final"."""
    V = [m + " Plan" for m in months]
    k = [STORE, DEPT, MRP, DISP]
    a, b = o.groupby(k, dropna=False)[V].sum(), out.groupby(k, dropna=False)[V].sum()
    idx = a.index.union(b.index)
    A, B = a.reindex(idx).fillna(0.0).to_numpy(), b.reindex(idx).fillna(0.0).to_numpy()
    lab = [c for c in (DIV, ATTR) if c in out.columns]
    t = pd.concat([out, o])[k + lab].drop_duplicates(k).set_index(k).reindex(idx).reset_index()[[STORE, *lab, DEPT, MRP, DISP]]
    d = np.abs(B - A) > SHOWN
    t["Changed"] = np.where(d.any(1), "Yes", "")
    t["Months changed"] = d.sum(1)
    t["Row"] = np.where(idx.isin(a.index), "", "new in final")
    cols = {}
    for j, m in enumerate(months):
        cols[f"{m} Original"], cols[f"{m} Final"], cols[f"{m} Difference"] = A[:, j], B[:, j], B[:, j] - A[:, j]
    cols["Season Original"], cols["Season Final"], cols["Season Difference"] = A.sum(1), B.sum(1), B.sum(1) - A.sum(1)
    t = pd.concat([t, pd.DataFrame(cols)], axis=1)
    return t.sort_values([STORE, *lab, DEPT, MRP, DISP], kind="stable").reset_index(drop=True)


def export_plan_to_plan(o, out, months, fmt, on_progress=None):
    t = _r8(plan_to_plan(o, out, months))
    if fmt == "csv":
        return t.to_csv(index=False, float_format="%.8f").encode("utf-8-sig"), "text/csv", "csv"
    return write_xlsx([("Plan to plan", t)], on_progress, "0.00000000"), XLSX_CTYPE, "xlsx"


def _r8(df):
    """8 decimals (user, 2026-09-30: "zero in difference to 0.00000000 instead of the full blown 0.0001"): a real
    difference shows in full and float noise (1e-13) becomes a clean 0, never -0."""
    df = df.copy()
    num = df.select_dtypes("float").columns
    df[num] = df[num].round(8) + 0.0
    return df
