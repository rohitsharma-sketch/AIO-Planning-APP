"""AOP Realigner engine - pure functions, no I/O.

Original plan: Store x Department x MRP x Display Type rows, "<Month> Plan" value + "<Month> Plan Qty".
Revised plan:  Store x Department values per month (only the departments the buyer changed).

Per Store x Division x Month the original total is the target. Revised departments keep their new
value exactly (split to MRP x Display Type by the original cont %); every other department in that
bucket absorbs the difference pro-rata. If revised alone exceed a month's total, the excess comes out
of the same store-division's other live months instead. Jan/Feb are never touched. Qty = value /
the original ASP for that Department x MRP x Display Type x Month.
"""
import io

import numpy as np
import pandas as pd
import xlsxwriter

TOL = 1e-9
STORE, DIV, DEPT, MRP, DISP = "Store Name", "DIVISION", "DEPARTMENT", "MRP", "DISPLAY TYPE"
FROZEN = ("Jan", "Feb")  # user rule: Jan & Feb plans stay exactly as the original
XLSX_CTYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def parent_for(dept, depts):
    """Longest existing department name that `dept` starts with (LW_U_T-TOP F/S -> LW_U_T-TOP), or None."""
    return next((p for p in sorted(depts, key=len, reverse=True) if p != dept and dept.startswith(p)), None)


def add_new_departments(o, r, months):
    """A revised dept a store never had (e.g. LW_U_T-TOP F/S) gets rows cloned from its parent dept in that
    store (parent_for): same MRP/display rows, zero original value. `_basis` = the row whose values give the
    MRP/display mix and ASP (itself, or the parent row for a clone)."""
    o = o.reset_index(drop=True)
    o["_basis"] = np.arange(len(o))
    have = set(zip(o[STORE], o[DEPT]))
    by_store = dict(tuple(o.groupby(STORE)))
    clones, unmatched = [], []
    for s, d in zip(r[STORE], r[DEPT]):
        if (s, d) in have:
            continue
        g = by_store.get(s)
        parent = parent_for(d, set(g[DEPT])) if g is not None else None
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
    Returns (realigned rows in original layout, division x month summary, warnings,
    a long-format table of every cell that actually changed - for the comparison download)."""
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

    # 2. every other department in the Store x Division x Month absorbs the difference pro-rata. Revised
    #    values are never changed: if they alone exceed a month's total, the other departments go to 0 that
    #    month and the excess is taken from the same store-division's other live months (in proportion to
    #    their room), so the store x division season total - and the grand total - still match the original.
    grp = (o[STORE] + "||" + o[DIV]).to_numpy()
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
                         "revised_before": float(orig[i, j][locked[i]].sum()), "revised_after": float(new[i, j][locked[i]].sum())})
    spilled_sd = sorted({f"{s}/{d}" for s, d in zip(o[STORE][spilled], o[DIV][spilled])})
    spilled_amt = float(pd.Series(excess[:, 0]).groupby(grp).first().sum())
    short_sd = sorted({f"{s}/{d}" for s, d in zip(o[STORE][short], o[DIV][short])})
    warn = []
    if n_new_sd:
        warn.append(f"{n_new_sd} new store-departments created ({n_new_rows} MRP/display rows) from their parent department's rows.")
    if fb_cells:
        warn.append(f"{fb_cells} revised row-months had no original plan that month; split by the row's average cont % across the other months.")
    if ignored:
        warn.append(f"{ignored} revised rows had Jan/Feb values different from the original - ignored, Jan/Feb stay as original.")
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


def verify(o, r, out, months):
    """Independent after-the-fact checks of a realign result, plus a per-department table of
    original vs revised (file) vs realigned (output) - the numbers a planner would eyeball."""
    V = [m + " Plan" for m in months]
    rm = [m for m in months if m in r.columns]
    live = [m for m in rm if m[:3] not in FROZEN]
    fz = [m for m in months if m[:3] in FROZEN]
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
    add("Store × Division totals match — whole season", "ok" if season == 0 else "fail",
        f"{season} of {len(a):,} store-divisions differ")
    add("Store × Division totals match — each month", "ok" if cells == 0 else "warn",
        f"{cells} of {d.size:,} store-division-months differ" +
        ("" if cells == 0 else " (where a revised department exceeded its month, the excess moved to other months)"))
    g0, g1 = float(o[V].to_numpy().sum()), float(out[V].to_numpy().sum())
    add("Grand total unchanged", "ok" if abs(g1 - g0) < 1e-6 else "fail", f"{g0:,.2f} → {g1:,.2f}")
    if fz:
        cols = [m + " Plan" for m in fz] + [m + " Plan Qty" for m in fz]
        fd = float(np.abs(out.iloc[:len(o)][cols].to_numpy() - o[cols].to_numpy()).max())
        add("Jan / Feb untouched (value and qty)", "ok" if fd < 1e-9 else "fail", f"largest change {fd:.2g}")

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
