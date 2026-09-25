"""Reading plan workbooks robustly - and saying exactly what was read.

- .xlsx / .xlsb / .xls / .csv; the first sheet that has the header row is used (or a chosen one)
- the header row may sit anywhere in the first SCAN_ROWS rows (the original has a totals row on top)
- column names match loosely: case, extra spaces, curly quotes, "Sep '26" vs "Sep'26" vs "Sept 2026",
  STORE vs STORE NAME, DEPT vs DEPARTMENT
- nothing is coerced or dropped silently: blank rows, non-numeric cells, duplicate keys, unknown stores
  and departments all land in the report as an error (blocks the run), a warning, or a note - with rows
"""
import csv
import io
import os
import re

import numpy as np
import pandas as pd

from engine import DEPT, DISP, DIV, FROZEN, MRP, STORE, parent_for

SCAN_ROWS = 15
XL_EXT = (".xlsx", ".xlsm", ".xlsb", ".xls")
ALIASES = {
    STORE: {"STORE NAME", "STORE", "STORE CODE", "STORENAME", "STORE_NAME"},
    DEPT: {"DEPARTMENT", "DEPT", "DEPARTMENT NAME", "DEPT NAME"},
    DIV: {"DIVISION", "DIV"},
    MRP: {"MRP"},
    DISP: {"DISPLAY TYPE", "DISPLAY", "DISPLAYTYPE", "DISPLAY_TYPE"},
}
SHOWN = {STORE: "STORE NAME", DEPT: "DEPARTMENT", DIV: "DIVISION", MRP: "MRP", DISP: "DISPLAY TYPE"}
NEED_ORIGINAL = {STORE, DEPT, DIV, MRP, DISP}
NEED_REVISED = {STORE, DEPT}
MONTH_RE = re.compile(r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*[\s'\-]*(\d{4}|\d{2})"
                      r"(?:\s*-?\s*P\s*([12]))?[\s\-_]+(PLAN\s*QTY|PLAN|NEW|QTY)$")
CANON_MONTH = re.compile(r"^[A-Z][a-z]{2}'\d{2}(?: P[12])? (Plan|Plan Qty|New)$")  # what canon() produces


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
    kind = kind.replace(" ", "")
    return label + {"NEW": " New", "PLAN": " Plan"}.get(kind, " Plan Qty")


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
    """Validate a revised plan against the loaded original -> (revised Store x Dept rows, months used, info, report).
    info["preview"] compares original vs revised totals per department for the same stores."""
    new = month_cols(df, "New")
    if not new:
        if month_cols(df, "Plan"):
            rep.error("This file looks like a full plan ('<Month> Plan' columns - an original or a realigned output). "
                      "Step 2 needs the revised plan: Store x Department rows with '<Month> New' columns.")
        else:
            rep.error("No '<Month> New' columns found - expected headers like \"Sep'26 New\", \"Jan'27 P1 New\".")
        return None, [], info, rep
    extra = [m for m in new if m not in months]
    if extra:
        rep.warn(f"{', '.join(extra)} aren't months in the original plan - ignored.")
    use = [m for m in months if m in new]
    if not use:
        rep.error(f"None of the file's months match the original's ({', '.join(months)}).")
        return None, [], info, rep
    df = _keys(df, [STORE, DEPT], rep, "revised plan")
    df = df.rename(columns={m + " New": m for m in use})
    df = _numbers(df, use, rep)
    _dups(df, [STORE, DEPT], rep, "revised plan")
    if not len(df):
        rep.error("The revised plan has no data rows.")
        return None, [], info, rep

    depts_by_store = orig.groupby(STORE)[DEPT].agg(set).to_dict()
    unknown = sorted(set(df[STORE]) - set(depts_by_store))
    if unknown:
        rep.error(f"{len(unknown)} store(s) aren't in the original plan, so their values can't be placed.", unknown)
    parents, orphans = {}, []
    for s, d in zip(df[STORE], df[DEPT]):
        have = depts_by_store.get(s)
        if have is None or d in have:
            continue
        p = parent_for(d, have)
        if p is None:
            orphans.append(f"{s} / {d}")
        else:
            parents.setdefault(d, [p, 0])[1] += 1
    if orphans:
        rep.error(f"{len(orphans)} store-department(s) don't exist in the original and have no parent department to copy "
                  f"MRP / display rows from (a new department must start with an existing one's name).", orphans)
    for d, (p, n) in parents.items():
        rep.info(f"New department {d} will be created in {n} store(s), using {p}'s MRP / display rows and ASPs.")

    V = [m + " Plan" for m in use]
    orig_sd = orig.groupby([STORE, DEPT])[V].sum()
    base = orig_sd.reindex(pd.MultiIndex.from_frame(df[[STORE, DEPT]])).fillna(0.0).to_numpy()
    fz = [j for j, m in enumerate(use) if m[:3] in FROZEN]
    if fz:
        diff = (np.abs(df[use].to_numpy()[:, fz] - base[:, fz]) > 1e-6).any(axis=1)
        if diff.any():
            rep.warn(f"{int(diff.sum())} row(s) have Jan/Feb values that differ from the original - they'll be ignored "
                     f"(Jan & Feb always stay as the original).", [f"row {r}" for r in _rows(df.index[diff])])
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

    rows = []
    for d, g in df.assign(**{f"_o{j}": base[:, j] for j in range(len(use))}).groupby(DEPT, sort=False):
        rows.append({"dept": d, "stores": len(g), "parent": parents.get(d, [None])[0],
                     "original": [float(g[f"_o{j}"].sum()) for j in range(len(use))],
                     "revised": [float(g[m].sum()) for m in use]})
    info.update(rows=len(df), stores=int(df[STORE].nunique()), departments=len(rows), months=use,
                preview={"months": use, "frozen": [m[:3] in FROZEN for m in use], "rows": rows})
    rep.info(f"{len(df):,} store-department rows · {len(rows)} department(s) · {info['stores']} stores · "
             f"{len(use)} month(s) ({use[0]} to {use[-1]}).")
    return df[[STORE, DEPT] + use].reset_index(drop=True), use, info, rep


def template(orig, months, dept=None):
    """Revised-plan template: Store Name, DIVISION, DEPARTMENT, <Month> New - pre-filled with the
    original's values for `dept` (every store that has it), or empty headers if no dept is given."""
    cols = [STORE, DIV, DEPT] + [m + " New" for m in months]
    if not dept:
        return pd.DataFrame(columns=cols)
    g = orig[orig[DEPT] == dept].groupby([STORE, DIV, DEPT], sort=False)[[m + " Plan" for m in months]].sum().reset_index()
    return g.rename(columns={m + " Plan": m + " New" for m in months})[cols]
