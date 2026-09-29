"""Reading plan workbooks robustly - and saying exactly what was read.

- .xlsx / .xlsb / .xls / .csv; the first sheet that has the header row is used (or a chosen one)
- the header row may sit anywhere in the first SCAN_ROWS rows (the original has a totals row on top)
- column names match loosely: case, extra spaces, curly quotes, "Sep '26" vs "Sep'26" vs "Sept 2026",
  STORE vs STORE NAME, DEPT vs DEPARTMENT
- one reader per revision method: prepare_listing (1 - store listing changes; 4 - the same shifted to a chosen
  target), prepare_revised (2 - existing departments; also 3 - new departments, with an optional COPY FROM column),
  prepare_split (3 - split), prepare_growth (5 - growth changes vs last year)
- nothing is coerced or dropped silently: blank rows, non-numeric cells, duplicate keys, unknown stores
  and departments all land in the report as an error (blocks the run), a warning, or a note - with rows
"""
import csv
import io
import os
import re

import numpy as np
import pandas as pd

from engine import (DEPT, DISP, DIV, MRP, STORE, locked, growth_targets, listing_targets, ly_label, parent_for,
                    shift_targets, split_targets)

LIST, FROMM, PARENT, NEWD, SHARE = "LISTING", "FROM MONTH", "PARENT DEPARTMENT", "NEW DEPARTMENT", "SHARE %"
TARGET, GROWTH = "TARGET", "NEW GROWTH %"

SCAN_ROWS = 15
XL_EXT = (".xlsx", ".xlsm", ".xlsb", ".xls")
ALIASES = {
    STORE: {"STORE NAME", "STORE", "STORE CODE", "STORENAME", "STORE_NAME"},
    DEPT: {"DEPARTMENT", "DEPT", "DEPARTMENT NAME", "DEPT NAME"},
    DIV: {"DIVISION", "DIV"},
    MRP: {"MRP"},
    DISP: {"DISPLAY TYPE", "DISPLAY", "DISPLAYTYPE", "DISPLAY_TYPE"},
    LIST: {"LISTING", "LISTING (Y/N)", "LISTED", "MC_LISTING", "MC LISTING", "MC_LISTING(REV)", "LISTING STATUS"},
    FROMM: {"FROM MONTH", "FROM", "EFFECTIVE FROM", "EFFECTIVE MONTH", "FROM (MONTH)"},
    PARENT: {"PARENT DEPARTMENT", "PARENT DEPT", "PARENT", "COPY FROM", "SPLIT FROM", "OLD DEPARTMENT", "FROM DEPARTMENT"},
    NEWD: {"NEW DEPARTMENT", "NEW DEPT", "CHILD DEPARTMENT", "SPLIT INTO"},
    SHARE: {"SHARE %", "SHARE", "SHARE%", "SPLIT %", "SPLIT%", "SHARE (%)"},
    TARGET: {"TARGET", "TARGET DEPARTMENT", "TARGET SECTION", "TARGET DEPT", "TARGET (DEPARTMENT / SECTION)", "SHIFT TO", "SHIFT FROM"},
    GROWTH: {"NEW GROWTH %", "NEW GROWTH", "GROWTH %", "GROWTH", "GROWTH%", "NEW GROWTH%"},
}
SHOWN = {STORE: "STORE NAME", DEPT: "DEPARTMENT", DIV: "DIVISION", MRP: "MRP", DISP: "DISPLAY TYPE",
         LIST: "LISTING", FROMM: "FROM MONTH", PARENT: "PARENT DEPARTMENT", NEWD: "NEW DEPARTMENT", SHARE: "SHARE %",
         TARGET: "TARGET", GROWTH: "NEW GROWTH %"}
NEED_ORIGINAL = {STORE, DEPT, DIV, MRP, DISP}
NEED_REVISED = {STORE, DEPT}
NEED_LISTING = {STORE, DEPT, LIST}
NEED_SPLIT = {PARENT, NEWD, SHARE}
NEED_SHIFT = {DEPT, LIST, TARGET}                  # STORE NAME optional: blank = every store it applies to
NEED_GROWTH = {DEPT, GROWTH}                       # STORE NAME optional: blank = the department in every store
YES = {"Y", "YES", "LISTED", "LIST", "RELIST", "RELISTED", "1"}
NO = {"N", "NO", "DELISTED", "DELIST", "-", "0"}
MONTH_ONLY = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[\s'\-]*(\d{4}|\d{2})(?:\s*-?\s*P\s*([12]))?$")
MONTH_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[\s'\-]*(\d{4}|\d{2})"
                      r"(?:\s*-?\s*P\s*([12]))?[\s\-_]+(PLAN\s*QTY|PLAN|NEW|QTY|GROWTH\s*%?)$")
CANON_MONTH = re.compile(r"^[A-Z][a-z]{2}'\d{2}(?: P[12])? (Plan|Plan Qty|New|Growth)$")  # what canon() produces


def month_cols(df, kind):
    """Months (in sheet order) that have a canonical '<Month> <kind>' column - "TTL SOND Val TY New" is not one."""
    return [c[:-len(kind) - 1] for c in df.columns if CANON_MONTH.match(c) and c.endswith(" " + kind)
            and not (kind == "Plan" and c.endswith("Plan Qty"))]


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, msg, examples=()):
        self.items.append({"level": level, "msg": msg, "examples": [str(e) for e in examples][:6]})

    error = lambda self, msg, ex=(): self.add("error", msg, ex)
    warn = lambda self, msg, ex=(): self.add("warning", msg, ex)
    info = lambda self, msg, ex=(): self.add("info", msg, ex)

    @property
    def ok(self):
        return not any(i["level"] == "error" for i in self.items)

    def first_error(self):
        return next((i["msg"] for i in self.items if i["level"] == "error"), "")


def norm(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    s = str(v).replace(" ", " ")
    for q in "’‘`´":
        s = s.replace(q, "'")
    return re.sub(r"\s+", " ", s).strip().upper()


def canon(v):
    """Header cell -> canonical column name (STORE, ... or "Sep'26 Plan" / "Sep'26 Plan Qty" / "Sep'26 New"), else None."""
    n = norm(v)
    for c, names in ALIASES.items():
        if n in names:
            return c
    m = MONTH_RE.match(n)
    if not m:
        return None
    mon, yy, p, kind = m.groups()
    label = f"{mon.title()}'{yy[-2:]}" + (f" P{p}" if p else "")
    kind = kind.replace(" ", "").rstrip("%")
    return label + {"NEW": " New", "PLAN": " Plan", "GROWTH": " Growth"}.get(kind, " Plan Qty")


def _blank(s):
    return s.isna() | s.astype(str).str.strip().isin(["", "nan", "None", "NaT"])


def _rows(idx):
    """Sheet row numbers (1-based) for a sheet-row index."""
    return [int(i) + 1 for i in idx]


def _sheets(data):
    """[(sheet_name, loader)]: loader() returns the whole sheet as a header-less DataFrame."""
    if data[:4] == b"PK\x03\x04" or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        xf = pd.ExcelFile(io.BytesIO(data), engine="calamine")
        # keep_default_na=False: pandas would otherwise silently blank out text like "n/a", "NA", "null"
        return [(n, lambda n=n: xf.parse(sheet_name=n, header=None, keep_default_na=False)) for n in xf.sheet_names]
    sample = data[:65536].decode("utf-8-sig", errors="replace")
    try:
        sep = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    return [("CSV", lambda: pd.read_csv(io.BytesIO(data), header=None, sep=sep, dtype=object,
                                         keep_default_na=False, encoding="utf-8-sig", encoding_errors="replace"))]


def read_table(data, filename, need, what, sheet=None):
    """Find the header row of `what` (a row holding every column in `need`) and return
    (DataFrame with canonical column names - index = 0-based sheet row, info, report)."""
    rep, info = Report(), {"file": filename, "bytes": len(data), "sheets": []}
    if not data:
        rep.error("The file is empty.")
        return None, info, rep
    try:
        sheets = _sheets(data)
    except Exception as e:
        rep.error(f"Couldn't open this file as a spreadsheet ({type(e).__name__}: {e}). Save it as .xlsx, .xlsb, .xls or .csv and try again.")
        return None, info, rep
    if os.path.splitext(filename.lower())[1] in XL_EXT and sheets[0][0] == "CSV":
        rep.error("The file is named like an Excel workbook but isn't one (it may be corrupted, or saved in another format).")
        return None, info, rep
    info["sheets"] = [n for n, _ in sheets]
    if sheet:
        sheets = [(n, f) for n, f in sheets if n == sheet]
        if not sheets:
            rep.error(f'There is no sheet named "{sheet}" - sheets in the file: {", ".join(info["sheets"])}.')
            return None, info, rep
    best, looks_revised = (0, None, None, need), False
    for name, load in sheets:
        try:
            raw = load()
        except Exception as e:
            rep.warn(f'Sheet "{name}" could not be read ({type(e).__name__}) - skipped.')
            continue
        for i in range(min(SCAN_ROWS, len(raw))):
            found = {canon(v) for v in raw.iloc[i].tolist()}
            if need <= found:
                return _frame(raw, i, name, info, rep)
            hits = len(need & found)
            if hits > best[0]:
                best = (hits, name, i + 1, need - found)
            looks_revised |= NEED_REVISED <= found and any(c and c.endswith(" New") for c in found)
    want = ", ".join(SHOWN[c] for c in sorted(need, key=list(SHOWN).index))
    closest = (f' Closest: sheet "{best[1]}" row {best[2]} is missing '
               f'{", ".join(SHOWN[c] for c in sorted(best[3], key=list(SHOWN).index))}.'
               if best[1] else "")
    hint = (" It has '<Month> New' columns - this looks like a revised plan; upload it in step 2."
            if looks_revised and need == NEED_ORIGINAL else "")
    rep.error(f"Couldn't find the {what}'s header row - no row in the first {SCAN_ROWS} rows of "
              f"{', '.join(repr(n) for n, _ in sheets)} has all of: {want}.{closest}{hint}")
    return None, info, rep


def _frame(raw, h, sheet, info, rep):
    cols, colmap = [], {}
    for j, hd in enumerate(raw.iloc[h].tolist()):
        c, text = canon(hd), (str(hd).strip() if norm(hd) else "")
        name = c or text or f"(blank {j + 1})"
        if name in colmap:
            if c:
                rep.error(f'Two columns both read as "{name}": "{colmap[name]}" and "{text}" (column {j + 1}). Rename or remove one.')
            name = f"{name} [{j + 1}]"
        colmap[name] = text or name
        cols.append(name)
    df = raw.iloc[h + 1:].copy()
    df.columns = cols
    for c in [c for c in cols if c.startswith("(blank ") and _blank(df[c]).all()]:
        df = df.drop(columns=c)
        colmap.pop(c)
    info.update(sheet=sheet, header_row=h + 1, colmap=colmap)
    where = f'sheet "{sheet}", ' if sheet != "CSV" else ""
    rep.info(f"Read {where}header on row {h + 1}" + (f" (the {h} row(s) above it were skipped)" if h else "") +
             (f'. Other sheets in the file: {", ".join(s for s in info["sheets"] if s != sheet)}' if len(info["sheets"]) > 1 else ""))
    return df, info, rep


def _keys(df, cols, rep, what):
    """Clean key columns (trim, collapse spaces, upper-case, 101.0 -> "101") and drop rows missing them."""
    for c in cols:
        s = df[c]
        num = pd.to_numeric(s, errors="coerce")
        whole = num.notna() & (num == num.round())
        s = s.where(~_blank(s), "").astype(object)
        s[whole] = num[whole].astype("int64").astype(str)
        df[c] = s.astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.upper()
    empty = (df[cols] == "").all(axis=1)
    partial = (df[cols] == "").any(axis=1) & ~empty
    if partial.any():
        rep.warn(f"{int(partial.sum())} {what} row(s) have values but no {' / '.join(SHOWN.get(c, c) for c in cols)} - skipped.",
                 [f"row {r}" for r in _rows(df.index[partial])])
    if empty.any():
        rep.info(f"{int(empty.sum())} empty row(s) skipped.")
    return df[~(empty | partial)]


def _numbers(df, cols, rep):
    """Numeric columns: "1,234" and "Rs 12" are read as numbers; anything else is 0 and reported."""
    bad, ex = 0, []
    for c in cols:
        s = df[c]
        num = pd.to_numeric(s, errors="coerce")
        miss = pd.Series(False, index=s.index)
        na = num.isna()
        if na.any():
            miss[na] = ~_blank(s[na]).to_numpy()  # only look at cells that failed to parse - fast on big files
        if miss.any():
            num[miss] = pd.to_numeric(s[miss].astype(str).str.replace(r"[,₹\s]|Rs\.?", "", regex=True), errors="coerce")
            still = miss & num.isna()
            bad += int(still.sum())
            ex += [f'{c}, row {i + 1}: "{s[i]}"' for i in s.index[still][:3]]
        df[c] = num.fillna(0.0).astype(float)
    if bad:
        rep.warn(f"{bad} cell(s) in value columns aren't numbers - treated as 0.", ex)
    return df


def _dups(df, key, rep, what):
    d = df[df.duplicated(key, keep=False)]
    if len(d):
        groups = d.groupby(key, sort=False).groups
        rep.error(f"{len(groups)} duplicate {what} key(s) ({' x '.join(SHOWN.get(k, k) for k in key)}) - each must appear once.",
                  [" / ".join(map(str, k)) + f"  (rows {', '.join(map(str, _rows(ix[:4])))})" for k, ix in list(groups.items())[:6]])


def prepare_original(df, info, rep):
    """-> (clean original rows, months, info, report)."""
    months = month_cols(df, "Plan")
    if not months:
        hint = (" This looks like a revised plan (it has '<Month> New' columns) - upload it in step 2."
                if month_cols(df, "New") else "")
        rep.error("No month value columns found - expected headers like \"Sep'26 Plan\" and \"Sep'26 Plan Qty\"." + hint)
        return None, [], info, rep
    noqty = [m for m in months if m + " Plan Qty" not in df.columns]
    if noqty:
        rep.warn(f"No qty column for {', '.join(noqty)} - qty is 0 there, so new qty can't be priced for those months.")
        for m in noqty:
            df[m + " Plan Qty"] = 0.0
            info["colmap"][m + " Plan Qty"] = m + " Plan Qty"
    df = _keys(df, [STORE, DEPT, DIV, DISP], rep, "original plan")
    mrp = pd.to_numeric(df[MRP], errors="coerce")
    if mrp.notna().all():
        df[MRP] = mrp.astype("int64") if (mrp == mrp.round()).all() else mrp
    else:
        df[MRP] = df[MRP].astype(str).str.strip()
        rep.info(f"{int(mrp.isna().sum())} MRP value(s) aren't numbers - kept as text.")
    num = [m + " Plan" for m in months] + [m + " Plan Qty" for m in months]
    df = _numbers(df, num, rep)
    _dups(df, [STORE, DEPT, MRP, DISP], rep, "original plan")
    neg = int((df[[m + " Plan" for m in months]] < 0).to_numpy().sum())
    if neg:
        rep.info(f"{neg:,} negative plan value(s) (kept as they are).")
    info.update(rows=len(df), stores=int(df[STORE].nunique()), departments=int(df[DEPT].nunique()),
                divisions=sorted(df[DIV].unique().tolist()), months=months)
    rep.info(f"{len(df):,} rows · {info['stores']} stores · {info['departments']} departments · "
             f"{len(info['divisions'])} divisions ({', '.join(info['divisions'])}) · {len(months)} months ({months[0]} to {months[-1]}).")
    return df.reset_index(drop=True), months, info, rep


def prepare_revised(df, info, rep, orig, months):
    """Methods 2 and 3 (new departments): validate a revised plan against the loaded original ->
    (revised Store x Dept rows, months used, source rows for new depts, info, report).
    An optional COPY FROM (PARENT DEPARTMENT) column names the department whose MRP / display rows and ASPs a new
    department takes; without it a new department must start with an existing one's name (LW_U_T-TOP F/S).
    info["preview"] compares original vs revised totals per department for the same stores."""
    new = month_cols(df, "New")
    if not new:
        if month_cols(df, "Plan"):
            rep.error("This file looks like a full plan ('<Month> Plan' columns - an original or a realigned output). "
                      "Step 2 needs the revised plan: Store x Department rows with '<Month> New' columns.")
        else:
            rep.error("No '<Month> New' columns found - expected headers like \"Sep'26 New\", \"Jan'27 P1 New\".")
        return None, [], {}, info, rep
    extra = [m for m in new if m not in months]
    if extra:
        rep.warn(f"{', '.join(extra)} aren't months in the original plan - ignored.")
    use = [m for m in months if m in new]
    if not use:
        rep.error(f"None of the file's months match the original's ({', '.join(months)}).")
        return None, [], {}, info, rep
    explicit = PARENT in df.columns
    df = _keys(df, [STORE, DEPT], rep, "revised plan")
    if explicit:
        df[PARENT] = _clean(df[PARENT])
    df = df.rename(columns={m + " New": m for m in use})
    df = _numbers(df, use, rep)
    _dups(df, [STORE, DEPT], rep, "revised plan")
    if not len(df):
        rep.error("The revised plan has no data rows.")
        return None, [], {}, info, rep

    depts_by_store = orig.groupby(STORE)[DEPT].agg(set).to_dict()
    unknown = sorted(set(df[STORE]) - set(depts_by_store))
    if unknown:
        rep.error(f"{len(unknown)} store(s) aren't in the original plan, so their values can't be placed.", unknown)
    parents, orphans, source = {}, [], {}
    for s, d, cp in zip(df[STORE], df[DEPT], df[PARENT] if explicit else [""] * len(df)):
        have = depts_by_store.get(s)
        if have is None or d in have:
            continue
        p = (cp if cp in have else None) if cp else parent_for(d, have)
        if p is None:
            orphans.append(f"{s} / {d}" + (f" (COPY FROM {cp} isn't planned in that store)" if cp else ""))
        else:
            parents.setdefault(d, [p, 0])[1] += 1
            source[(s, d)] = (s, p)
    if orphans:
        rep.error(f"{len(orphans)} store-department(s) don't exist in the original and have no department to copy "
                  f"MRP / display rows from - name one in a COPY FROM column, or start the new name with an "
                  f"existing department's (LW_U_T-TOP F/S).", orphans)
    for d, (p, n) in parents.items():
        rep.info(f"New department {d} will be created in {n} store(s), using {p}'s MRP / display rows and ASPs.")

    V = [m + " Plan" for m in use]
    orig_sd = orig.groupby([STORE, DEPT])[V].sum()
    base = orig_sd.reindex(pd.MultiIndex.from_frame(df[[STORE, DEPT]])).fillna(0.0).to_numpy()
    fz = [j for j, m in enumerate(use) if locked(m)]
    if fz:
        diff = (np.abs(df[use].to_numpy()[:, fz] - base[:, fz]) > 1e-6).any(axis=1)
        if diff.any():
            rep.warn(f"{int(diff.sum())} row(s) have values in locked months that differ from the original - they'll be ignored "
                     f"(locked months always stay as the original).", [f"row {r}" for r in _rows(df.index[diff])])
    missing = [m for m in months if m not in use]
    if missing:
        rep.info(f"Months not in the file stay as original for these departments: {', '.join(missing)}.")
    tot = orig_sd.sum(axis=1)
    for d in dict.fromkeys(df[DEPT]):
        planned = set(tot[(tot.index.get_level_values(1) == d) & (tot.abs() > 1e-9)].index.get_level_values(0))
        left_out = planned - set(df.loc[df[DEPT] == d, STORE])
        if left_out:
            rep.info(f"{len(left_out)} store(s) plan {d} in the original but aren't in this file - they stay as original.",
                     sorted(left_out))

    r = df[[STORE, DEPT] + use].reset_index(drop=True)
    info.update(rows=len(df), stores=int(df[STORE].nunique()), months=use,
                preview=_preview(r, orig, use, {d: f"new · copies {p}" for d, (p, _) in parents.items()}))
    info["departments"] = len(info["preview"]["rows"])
    rep.info(f"{len(df):,} store-department rows · {info['departments']} department(s) · {info['stores']} stores · "
             f"{len(use)} month(s) ({use[0]} to {use[-1]}).")
    return r, use, source, info, rep


def _clean(s):
    """A key-like text column where blank is allowed (COPY FROM, STORE NAME in a split file)."""
    return s.where(~_blank(s), "").astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.upper()


def _preview(r, orig, use, tags=None):
    """Original vs revised totals per department (same stores) - the table under step 2."""
    base = (orig.groupby([STORE, DEPT])[[m + " Plan" for m in use]].sum()
            .reindex(pd.MultiIndex.from_frame(r[[STORE, DEPT]])).fillna(0.0).to_numpy())
    vals = r[use].to_numpy(float)
    rows = [{"dept": d, "stores": len(ix), "tag": (tags or {}).get(d),
             "original": base[ix].sum(0).tolist(), "revised": vals[ix].sum(0).tolist()}
            for d, ix in r.groupby(DEPT, sort=False).indices.items()]
    return {"months": use, "frozen": [locked(m) for m in use], "rows": rows}


def _known(df, rep, checks):
    """Stores / departments that aren't in the original at all -> errors. checks: [(column, known set, (what, hint))]."""
    for col, have, what in checks:
        bad = sorted(set(df[col][df[col] != ""]) - have)
        if bad:
            rep.error(f"{len(bad)} {what[0]} aren't in the original plan{what[1]}.", bad)


def from_month(v, months):
    """FROM MONTH cell -> index into `months` (0 = from the first month when blank), None if it isn't one of them.
    "Oct'26", "October 2026", a date cell, "Jan'27" (= Jan'27 P1) all work."""
    n = v.strftime("%b'%y").upper() if hasattr(v, "strftime") else norm(v)
    if not n:
        return 0
    m = MONTH_ONLY.match(n)
    if not m:
        return None
    mon, yy, p = m.groups()
    label = f"{mon.title()}'{yy[-2:]}" + (f" P{p}" if p else "")
    return next((i for i, x in enumerate(months) if x == label or x.startswith(label + " ")), None)


def prepare_listing(df, info, rep, orig, months, shift=False, section_of=None):
    """Method 1 - store listing changes: STORE NAME, DEPARTMENT, LISTING (Y/N), optional FROM MONTH and optional
    '<Month> New' values for new listings -> (revised Store x Dept rows, months, source rows, info, report).
    shift=True is Method 4: every row also names a TARGET (a department, or a section of the Attribute Master) that
    the change is shifted into / out of, and STORE NAME may be blank (= every store the change applies to)."""
    section_of = section_of or {}
    raw_from = df[FROMM] if FROMM in df.columns else None
    if shift:
        df = _keys(df, [DEPT, LIST, TARGET], rep, "listing change")
        df[STORE] = _clean(df[STORE]) if STORE in df.columns else ""
    else:
        df = _keys(df, [STORE, DEPT, LIST], rep, "listing change")
    _dups(df, [STORE, DEPT], rep, "listing change")
    if not len(df):
        rep.error("The file has no listing changes.")
        return None, [], {}, info, rep
    bad = ~df[LIST].isin(YES | NO)
    if bad.any():
        rep.error(f"{int(bad.sum())} row(s) have a LISTING value that isn't Y or N.",
                  [f'row {i + 1}: "{v}"' for i, v in df[LIST][bad].head(6).items()])
    _known(df, rep, [(STORE, set(orig[STORE]), ("store(s)", "")),
                     (DEPT, set(orig[DEPT]), ("department(s)", " - a brand-new department is Method 3"))])
    if shift:
        _known(df, rep, [(TARGET, set(orig[DEPT]) | set(section_of.values()),
                          ("target(s)", " as a department or a section (Attribute Master)"))])
        same_t = df[df[TARGET] == df[DEPT]]
        if len(same_t):
            rep.error("A department can't be shifted into itself.", list(same_t[DEPT].unique()))
    starts = pd.Series(0, index=df.index)
    if raw_from is not None:
        starts = raw_from.reindex(df.index).map(lambda v: from_month(v, months))
        nf = starts.isna()
        if nf.any():
            rep.error(f"{int(nf.sum())} FROM MONTH value(s) aren't months of the plan ({months[0]} to {months[-1]}).",
                      [f'row {i + 1}: "{raw_from[i]}"' for i in df.index[nf][:6]])
    vcols = [m for m in months if m + " New" in df.columns and not locked(m)]
    given = pd.concat([~_blank(df[m + " New"]) for m in vcols], axis=1).any(axis=1) if vcols else pd.Series(False, index=df.index)
    df = _numbers(df, [m + " New" for m in vcols], rep)
    if not rep.ok:
        return None, [], {}, info, rep

    sd = orig.groupby([STORE, DEPT])[[m + " Plan" for m in months]].sum().abs().sum(axis=1)
    planned = set(sd[sd > 1e-9].index)
    changes, same = [], {"N": [], "Y": []}
    stores_of = {}
    for st, dep in planned:
        stores_of.setdefault(dep, set()).add(st)
    for i, s, d, ls in zip(df.index, df[STORE], df[DEPT], df[LIST]):
        y = "Y" if ls in YES else "N"
        t = df.at[i, TARGET] if shift else None
        if s:
            scope = [s]
        elif y == "N":                                   # blank store: every store planning the department ...
            scope = sorted(stores_of.get(d, ()))
        else:                                            # ... or, for a listing, every store planning the target
            tg = {t} | {x for x, sec in section_of.items() if sec == t}
            scope = sorted({st for x in tg for st in stores_of.get(x, ())} - stores_of.get(d, set()))
        for st in scope:
            if (y == "Y") == ((st, d) in planned):  # listed & already planned / delisted & not planned: nothing moves
                same[y].append(f"{st} / {d}")
                continue
            vals = [float(df.at[i, m + " New"]) if m in vcols else 0.0 for m in months] if given[i] else None
            changes.append({"store": st, "dept": d, "listing": y, "start": int(starts[i]), "values": vals, "target": t})
    if same["N"]:
        rep.info(f"{len(same['N'])} delisting(s) have no plan in the original anyway - nothing to move.", same["N"])
    if same["Y"]:
        rep.info(f"{len(same['Y'])} listing(s) are already planned - left as they are "
                 f"(to change their values use Method 2).", same["Y"])
    if not changes:
        rep.error("None of the rows changes the plan - every delisted department is already unplanned and every "
                  "listed one already planned.")
        return None, [], {}, info, rep
    if shift:
        try:
            r, source, notes = shift_targets(orig, changes, months, section_of)
        except ValueError as e:
            rep.error(str(e))
            return None, [], {}, info, rep
        n_del = sum(c["listing"] == "N" for c in changes)
        rep.info(f"{n_del} delisting(s) move their plan into the named target only; {len(changes) - n_del} listing(s) take "
                 f"theirs out of the target only (sized from same-cluster stores unless values are given). Nothing else "
                 f"moves - every store x division x month stays as in the original.")
        if notes["capped"]:
            rep.warn(f"{len(notes['capped'])} listing(s) wanted more than their target had in some month - capped at the "
                     f"target's value there (the target goes to 0 that month).", notes["capped"])
        tags = {}
        for c in changes:
            tags[c["dept"]] = f"{'delisted' if c['listing'] == 'N' else 'listed'} → {c['target']}"
            tags.setdefault(c["target"], "target")
        info.update(rows=len(df), stores=int(r[STORE].nunique()), months=months, preview=_preview(r, orig, months, tags))
        info["departments"] = len(info["preview"]["rows"])
        rep.info(f"{len(changes)} change(s) · {info['departments']} department(s) incl. targets · {info['stores']} stores.")
        return r, months, source, info, rep
    try:
        r, source, counts = listing_targets(orig, changes, months)
    except ValueError as e:
        rep.error(str(e))
        return None, [], {}, info, rep
    if counts["delisted"]:
        rep.info(f"{counts['delisted']} delisting(s): the department goes to 0 from its FROM MONTH (the first month if "
                 f"blank); the rest of that store x division absorbs it.")
    if counts["estimated"]:
        rep.info(f"{counts['estimated']} new listing(s) sized from same-cluster stores: the department's share of "
                 f"its division there x this store's division plan, month by month.")
    if counts["given"]:
        rep.info(f"{counts['given']} new listing(s) use the values given in the file.")
    ch = pd.DataFrame(changes)
    tags = {}
    for d, g in ch.groupby("dept", sort=False):
        n_del, n_add = int((g.listing == "N").sum()), int((g.listing == "Y").sum())
        tags[d] = " · ".join(x for x in (n_del and f"delisted in {n_del}", n_add and f"listed in {n_add}") if x)
    info.update(rows=len(df), stores=int(r[STORE].nunique()), months=months, preview=_preview(r, orig, months, tags))
    info["departments"] = len(info["preview"]["rows"])
    rep.info(f"{len(changes)} listing change(s) · {info['departments']} department(s) · {info['stores']} stores.")
    return r, months, source, info, rep


def _percent(raw, rep, what, allow_negative=False):
    """A % column -> fractions: "40" or "40%" = 40%; a file holding only values within +/-1 and no "%" (Excel
    %-formatted cells) = fractions already. The reading used is reported."""
    raw = raw.astype(str).str.strip()
    pct = raw.str.contains("%")
    num = pd.to_numeric(raw.str.replace(r"[%\s,]", "", regex=True), errors="coerce")
    bad = num.isna() | ((num <= -100) if allow_negative else (num <= 0))
    if bad.any():
        rep.error(f"{int(bad.sum())} {what} value(s) aren't valid numbers.", [f'row {i + 1}: "{raw[i]}"' for i in raw.index[bad][:6]])
    as_pct = pct | bool((num[~pct].abs() > 1).any())
    rep.info(f"{what} read as " + ("percentages (12 = 12%)." if bool(np.all(as_pct)) else "fractions (0.12 = 12%)."))
    return pd.Series(np.where(as_pct, num / 100, num), index=raw.index)


def prepare_growth(df, info, rep, orig, months, ly):
    """Method 5 - growth changes: DEPARTMENT, NEW GROWTH % (vs last year), optional STORE NAME (blank = every
    store; a store's own row overrides) -> (revised Store x Dept rows, months, {}, info, report).
    ly: {(store, dept): {"Sep'25": value}} from the month-wise data-lake export, in the plan's units."""
    gcols = [m for m in month_cols(df, "Growth") if m in months and not locked(m) and ly_label(m)]
    cols = [GROWTH] + [m + " Growth" for m in gcols]         # NEW GROWTH % (season) + optional '<Month> GROWTH %'
    raw = df[cols].copy()
    df = _keys(df, [DEPT], rep, "growth")
    raw = raw.reindex(df.index)
    filled = pd.concat([~_blank(raw[c]) for c in cols], axis=1)
    df, raw, filled = df[filled.any(axis=1)], raw[filled.any(axis=1)], filled[filled.any(axis=1)]  # nothing filled = unchanged
    df[STORE] = _clean(df[STORE]) if STORE in df.columns else ""
    if not len(df):
        rep.error("No growth filled in (NEW GROWTH % or a '<Month> GROWTH %' column) - nothing to change.")
        return None, [], {}, info, rep
    stacked = raw.stack()                                     # one % reading for every growth cell in the file
    stacked = stacked[filled.stack().reindex(stacked.index).fillna(False).astype(bool)]
    gv = _percent(stacked.reset_index(drop=True), rep, "Growth", allow_negative=True).to_numpy()
    vals = {k: v for k, v in zip(stacked.index, gv)}
    if gcols:
        rep.info(f"Per-month growth columns found ({', '.join(gcols)}) - a month with a value is judged on its own plan vs its own "
                 f"last-year month (a festival that moved month, e.g. Diwali, shows up there); other months use NEW GROWTH %.")
    _dups(df, [DEPT, STORE], rep, "growth")
    _known(df, rep, [(STORE, set(orig[STORE]), ("store(s)", "")), (DEPT, set(orig[DEPT]), ("department(s)", ""))])
    if not ly:
        rep.error("Last year's sales aren't available (the Listing / Delisting Analyser's sales.json) - can't measure growth.")
    if not rep.ok:
        return None, [], {}, info, rep
    jm = {m: j for j, m in enumerate(months)}
    rows = [{"dept": d, "store": s or None, "growth": vals.get((i, GROWTH)),
             "months": {jm[m]: vals[(i, m + " Growth")] for m in gcols if (i, m + " Growth") in vals}}
            for i, d, s in zip(df.index, df[DEPT], df[STORE])]
    try:
        r, detail = growth_targets(orig, rows, months, ly)
    except ValueError as e:
        rep.error(str(e))
        return None, [], {}, info, rep
    lm = [m for m in months if not locked(m) and ly_label(m)]
    for x in detail:
        mm = "".join(f"; {y['month']} {y['current']:+.1%} → {y['new']:+.1%}" for y in x["months"])
        season = (f"{x['current']:+.1%} now → {x['new']:+.1%} (plan × {x['factor']:.4f})" if x["new"] is not None
                  else f"{x['current']:+.1%} now, other months unchanged")
        rep.info(f"{x['dept']}{' / ' + x['store'] if x['store'] else ''}: {x['comparable']} of {x['stores']} store(s) with last year's "
                 f"sales - season plan {x['plan']:,.2f} vs last year {x['ly']:,.2f} = {season}{mm}.")
        if abs(x["current"]) > 2:
            rep.warn(f"{x['dept']}: current growth {x['current']:+.0%} looks like last year isn't comparable "
                     f"(renamed or split department?) - check before running.")
    info.update(rows=len(df), stores=int(r[STORE].nunique()), months=months,
                preview=_preview(r, orig, months, {x["dept"]: (f"{x['current']:+.0%} → {x['new']:+.0%}" if x["new"] is not None else "")
                                                   + (" · by month" if x["months"] else "") for x in detail}))
    info["departments"] = len(info["preview"]["rows"])
    rep.info(f"Months compared: {', '.join(lm)} vs {', '.join(ly_label(m) for m in lm)}. The rest of each store x division "
             f"absorbs the change (capped at store x division x month); other divisions are not touched.")
    return r, months, {}, info, rep


def prepare_split(df, info, rep, orig, months):
    """Method 3 - split: PARENT DEPARTMENT, NEW DEPARTMENT, SHARE %, optional STORE NAME (blank = every store)
    -> (revised Store x Dept rows, months, source rows, info, report)."""
    raw = df[SHARE].copy()
    df = _keys(df, [PARENT, NEWD], rep, "split")
    df[STORE] = _clean(df[STORE]) if STORE in df.columns else ""
    df["_share"] = _percent(raw.reindex(df.index), rep, "Shares")
    _dups(df, [PARENT, NEWD, STORE], rep, "split")
    _known(df, rep, [(STORE, set(orig[STORE]), ("store(s)", "")), (PARENT, set(orig[DEPT]), ("parent department(s)", ""))])
    same = df[df[PARENT] == df[NEWD]]
    if len(same):
        rep.error("A department can't be split into itself.", list(same[PARENT].unique()))
    if not len(df):
        rep.error("The file has no split rows.")
    if not rep.ok:
        return None, [], {}, info, rep
    has = set(zip(orig[STORE], orig[DEPT]))
    lone = [f"{s} / {p}" for s, p in zip(df[STORE], df[PARENT]) if s and (s, p) not in has]
    if lone:
        rep.warn(f"{len(lone)} store-specific row(s) name a store that doesn't have the parent department - skipped.", lone)
    splits = [{"parent": p, "child": c, "share": float(x), "store": s or None}
              for p, c, x, s in zip(df[PARENT], df[NEWD], df["_share"], df[STORE])]
    try:
        r, source = split_targets(orig, splits, months)
    except ValueError as e:
        rep.error(str(e))
        return None, [], {}, info, rep
    if not len(r):
        rep.error("No store plans any of the parent departments - nothing to split.")
        return None, [], {}, info, rep
    kids = df.groupby(PARENT, sort=False)[NEWD].agg(lambda x: ", ".join(dict.fromkeys(x))).to_dict()
    tags = {p: f"split into {k}" for p, k in kids.items()}
    tags.update({c: f"from {p}" for p, c in zip(df[PARENT], df[NEWD])})
    rep.info("Each parent keeps what isn't shared out; each new department takes its share of the parent in every live "
             "month, with the parent's MRP / display mix and ASPs. Locked months stay on the parent (never changed).")
    info.update(rows=len(df), stores=int(r[STORE].nunique()), months=months, preview=_preview(r, orig, months, tags))
    info["departments"] = len(info["preview"]["rows"])
    rep.info(f"{len(df)} split row(s) · {len(kids)} parent department(s) · {info['stores']} stores.")
    return r, months, source, info, rep




def template(orig, months, dept=None):
    """Revised-plan template: Store Name, DIVISION, DEPARTMENT, <Month> New - pre-filled with the
    original's values for `dept` (every store that has it), or empty headers if no dept is given."""
    cols = [STORE, DIV, DEPT] + [m + " New" for m in months]
    if not dept:
        return pd.DataFrame(columns=cols)
    g = orig[orig[DEPT] == dept].groupby([STORE, DIV, DEPT], sort=False)[[m + " Plan" for m in months]].sum().reset_index()
    return g.rename(columns={m + " Plan": m + " New" for m in months})[cols]


def live_months(months):
    return [m for m in months if not locked(m)]


def template_listing(orig, months, kb=None):
    """Method 1 template. With `kb` (the Listing / Delisting Analyser's kb.json) it is pre-filled with every difference
    between the plan and the latest listing month: planned departments now delisted (N) and listed departments
    with no plan (Y). Leave '<Month> New' blank to size a new listing from same-cluster stores.
    -> (template rows, skipped rows). A store x division whose EVERY planned department is delisted (a store
    closing or not open yet, e.g. an upcoming store flipped to N) is left out: nothing would be left there to
    absorb its plan. Those rows come back separately for the "Not included" sheet."""
    cols = [STORE, DIV, DEPT, LIST, FROMM, "NOTE"] + [m + " New" for m in live_months(months)]
    if not kb:
        return pd.DataFrame(columns=cols), pd.DataFrame()
    tot = orig.groupby([STORE, DEPT])[[m + " Plan" for m in months]].sum().abs().sum(axis=1)
    planned = set(tot[tot > 1e-9].index)
    season = orig.groupby([STORE, DEPT])[[m + " Plan" for m in live_months(months)]].sum().sum(axis=1)
    div_of = orig.groupby(DEPT)[DIV].agg(lambda s: s.mode().iat[0]).to_dict()
    li, last = len(kb["months"]) - 1, kb["months"][-1]
    flag = lambda s, d: (kb["data"].get(s, {}).get(d) or "")[li:li + 1]
    rows = [{STORE: s, DIV: div_of[d], DEPT: d, LIST: "N", FROMM: months[0],
             "NOTE": f"Listing app {last}: delisted - plan {season.get((s, d), 0):.2f} L in live months"}
            for s, d in sorted(planned) if flag(s, d) == "N"]
    per_sd = pd.Series(1, index=pd.MultiIndex.from_tuples(sorted(planned))).groupby(lambda k: (k[0], div_of[k[1]])).size()
    gone = pd.DataFrame(rows).groupby([STORE, DIV]).size() if rows else pd.Series(dtype=int)
    whole = {k for k, n in gone.items() if n == per_sd.get(k)}
    skipped = [dict(r, NOTE=f"not included - every planned {r[DIV]} department of {r[STORE]} is delisted (store closing / not open?)")
               for r in rows if (r[STORE], r[DIV]) in whole]
    rows = [r for r in rows if (r[STORE], r[DIV]) not in whole]
    rows += [{STORE: s, DIV: div_of[d], DEPT: d, LIST: "Y", FROMM: months[0], "NOTE": f"Listing app {last}: listed - not in the plan"}
             for s in sorted(set(orig[STORE]) & set(kb["data"])) for d, f in sorted(kb["data"][s].items())
             if f[li:li + 1] == "Y" and d in div_of and (s, d) not in planned]
    return pd.DataFrame(rows, columns=cols), pd.DataFrame(skipped, columns=cols[:6])


def template_split():
    return pd.DataFrame(columns=[PARENT, NEWD, SHARE, STORE])


def template_newdept(months):
    return pd.DataFrame(columns=[STORE, DIV, DEPT, "COPY FROM"] + [m + " New" for m in live_months(months)])


def template_shift(orig, months, kb=None):
    """Method 4 template: the Method 1 columns plus TARGET; with kb, pre-filled like Method 1 (TARGET left for the user)."""
    t, skipped = template_listing(orig, months, kb)
    t.insert(t.columns.get_loc(FROMM) + 1, TARGET, "")
    return t, skipped


def template_growth(orig, months, ly):
    """Method 5 template: every department with its plan and last year's sales over the live months (stores that have
    both) and the growth that gives today; fill NEW GROWTH % for the ones to change (blank = unchanged)."""
    lm = [m for m in months if not locked(m) and ly_label(m)]
    g = orig.groupby([STORE, DIV, DEPT])[[m + " Plan" for m in lm]].sum().sum(axis=1).rename("plan").reset_index()
    g["ly"] = [sum(float(ly.get((s, d), {}).get(ly_label(m), 0.0)) for m in lm) for s, d in zip(g[STORE], g[DEPT])]
    c = g[(g["plan"] > 1e-9) & (g["ly"] > 1e-9)].groupby([DIV, DEPT])[["plan", "ly"]].sum()
    a = g.groupby([DIV, DEPT]).agg(stores=(STORE, "size")).join(c).reset_index()
    span = f"{lm[0]}-{lm[-1]}" if lm else ""
    out = pd.DataFrame({DIV: a[DIV], DEPT: a[DEPT], STORE: "", "STORES": a["stores"],
                        f"PLAN {span} (comparable stores)": a["plan"].round(4),
                        f"LAST YEAR {ly_label(lm[0]) if lm else ''}-{ly_label(lm[-1]) if lm else ''}": a["ly"].round(4),
                        "CURRENT GROWTH %": ((a["plan"] / a["ly"] - 1) * 100).round(2), GROWTH: ""})
    # per month: that month's current growth (same comparable stores) and an empty column to set it
    comp = g[(g["plan"] > 1e-9) & (g["ly"] > 1e-9)][[STORE, DEPT]]
    for m in lm:
        pm = orig.groupby([STORE, DEPT])[m + " Plan"].sum().reindex(pd.MultiIndex.from_frame(comp)).fillna(0.0)
        lym = pd.Series([float(ly.get((s, d), {}).get(ly_label(m), 0.0)) for s, d in zip(comp[STORE], comp[DEPT])], index=pm.index)
        cur = (pm.groupby(level=1).sum() / lym.groupby(level=1).sum().replace(0, np.nan) - 1) * 100
        out[f"{m} CURRENT %"] = out[DEPT].map(cur).round(2)
    for m in lm:
        out[f"{m} GROWTH %"] = ""
    return out.sort_values([DIV, DEPT]).reset_index(drop=True)
