"""STR Forecaster engine (user, 2026-10-09: "I want to make a STR Forecaster, the components will be - Total Fixture Plan
on Store Wise x Month Wise, Minimum Density Qty, Sales Plan Month Wise").

Per store x department x month (MENS / LADIES / KIDS - GM has no Capacity / MDQ in the fixture file, left out for now):
    MDQ            = fixtures x qty per fixture (the file's Capacity; its MDQ column = MC_FIX x Capacity exactly)
    planned qty    = planned sales (Rs) / LY average selling price (LY sl_v / sl_q, same store x dept x month a year
                     earlier, from calendar.sales_fact; falls back to the department's month, then its whole LY)
    forecast STR   = planned qty / (planned qty + MDQ)
    LY STR (bench) = LY sales qty / (LY sales qty + the file's MDQ, no edits) - the same formula on last year's months
Roll-ups sum qty and MDQ first, then take the ratio. Uploads, rows and edits live in planning_inputs.str_* (migration
c7e2a4f9b1d3); the newest active upload of each kind is used; edits (append-only) override it, latest wins.
"""
import io
import json
import os
import re
import sys
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import text

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
for p in (ROOT, os.path.join(ROOT, "Tentative AOP Forecaster")):
    if p not in sys.path:
        sys.path.insert(0, p)
from db.base import SessionLocal  # noqa: E402 - the suite's planning DB session (.env in the AOP folder)
from rs_common.divisions import plan_division  # noqa: E402 - the one division roll-up

DIVS = ("MENS", "LADIES", "KIDS")
FIX_COLS = ("MC_FIX", "FINAL FIXTURE", "FIXTURES", "FIXTURE")
MON3 = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
KEY = ["month", "store", "department"]


def _sheet_month(name):
    """ "Jun'26" / "Jun-2026" / "JUNE 26" -> Period('2026-06') or None"""
    m = re.match(r"\s*([A-Za-z]{3})[A-Za-z]*\W*(\d{4}|\d{2})\b", str(name))
    if not m or m.group(1).upper() not in MON3:
        return None
    y = int(m.group(2))
    return pd.Period(year=y + 2000 if y < 100 else y, month=MON3.index(m.group(1).upper()) + 1, freq="M")


def read_fixture(data):
    """Fixture workbook (one sheet per month) -> (frame month/store/division/department/fixtures/mdq, notes).
    The header row is found by its STORE cell (Jun'26 has a blank first row); the month comes from a MONTH column or
    else the sheet name. The display type (UDF-06: TABLE / NON_TABLE) is kept per row ('' when the file has none)."""
    xl = pd.ExcelFile(io.BytesIO(data))
    frames, notes = [], []
    for sh in xl.sheet_names:
        head = xl.parse(sh, header=None, nrows=10)
        hdr = next((i for i in range(len(head)) if any(str(v).strip().upper() == "STORE" for v in head.iloc[i])), None)
        if hdr is None:
            notes.append(f"{sh}: no STORE header row - skipped")
            continue
        df = xl.parse(sh, header=hdr)
        df.columns = [str(c).strip().upper() for c in df.columns]
        fix = next((c for c in FIX_COLS if c in df.columns), None)
        missing = [c for c in ("STORE", "DIVISION", "DEPARTMENT", "MDQ") if c not in df.columns] + ([] if fix else ["fixture column"])
        if missing:
            notes.append(f"{sh}: missing {', '.join(missing)} - skipped")
            continue
        df = df[df["STORE"].notna() & df["DEPARTMENT"].notna()]
        if "MONTH" in df.columns and df["MONTH"].notna().all():
            month = pd.to_datetime(df["MONTH"]).dt.to_period("M")
        else:
            pm = _sheet_month(sh)
            if pm is None:
                notes.append(f"{sh}: no MONTH column and the sheet name is not a month - skipped")
                continue
            month = pd.Series([pm] * len(df), index=df.index)
        frames.append(pd.DataFrame({
            "month": month, "store": df["STORE"].astype(str).str.strip().str.upper(),
            "division": df["DIVISION"].map(plan_division), "department": df["DEPARTMENT"].astype(str).str.strip(),
            "fixtures": pd.to_numeric(df[fix], errors="coerce").fillna(0.0),
            "mdq": pd.to_numeric(df["MDQ"], errors="coerce").fillna(0.0),
            "display": _display(df[next(c for c in ("UDF-06", "UDF06", "DISPLAY TYPE") if c in df.columns)])
            if any(c in df.columns for c in ("UDF-06", "UDF06", "DISPLAY TYPE")) else ""}))
    if not frames:
        raise ValueError("No usable sheet: each month needs STORE, DIVISION, DEPARTMENT, a fixture column and MDQ. " + " ".join(notes))
    f = pd.concat(frames, ignore_index=True)
    left_out = f[~f.division.isin(DIVS)]
    if len(left_out):
        notes.append(f"{left_out.department.nunique()} GM / other departments left out (no Capacity / MDQ) - MENS, LADIES, KIDS only")
    f = f[f.division.isin(DIVS)]
    g = f.groupby(["month", "store", "division", "department", "display"], as_index=False)[["fixtures", "mdq"]].sum()
    return g[(g.fixtures > 0) | (g.mdq > 0)].reset_index(drop=True), notes


PLAN_COL = re.compile(r"^\s*([A-Za-z]{3,9})\W*(\d{2}|\d{4})\s*_\s*([VQ])\s*$")   # "Mar'26 _V", "June'26 _Q"
LAKH = 1e5


def read_sales_plan(data, name=""):
    """Store-level sales plan (user, 9 Oct: "MAMJ'26 - Sales Plan.xlsx") -> (frame month/store/division/department/
    plan_rs/plan_qty, notes). Columns STORE_NAME (or STORE), DIVISION, DEPARTMENT and one "<Mon>'<yy> _V" (Rs lakh) and
    "<Mon>'<yy> _Q" (pieces) pair per month; MRP / ATTRIBUTE rows of a store x department x article x display type (UDF06) are summed;
    totals such as "MAMJ'26_V" are not months and are ignored."""
    xl = pd.ExcelFile(io.BytesIO(data), engine="pyxlsb" if name.lower().endswith(".xlsb") else None)
    frames, notes = [], []
    for sh in xl.sheet_names:
        head = xl.parse(sh, header=None, nrows=10)
        hdr = next((i for i in range(len(head)) if any(str(v).strip().upper() in ("STORE_NAME", "STORE") for v in head.iloc[i])), None)
        if hdr is None:
            notes.append(f"{sh}: no STORE_NAME header row - skipped")
            continue
        df = xl.parse(sh, header=hdr)
        up = {str(c).strip().upper(): c for c in df.columns}
        sc = up.get("STORE_NAME", up.get("STORE"))
        if "DIVISION" not in up or "DEPARTMENT" not in up:
            notes.append(f"{sh}: missing DIVISION / DEPARTMENT - skipped")
            continue
        months = {}
        for c in df.columns:
            m = PLAN_COL.match(str(c))
            word = m.group(1).upper() if m else ""
            ok = len(word) == 3 or word in ('JANUARY','FEBRUARY','MARCH','APRIL','MAY','JUNE','JULY','AUGUST','SEPTEMBER','SEPT','OCTOBER','NOVEMBER','DECEMBER')   # a "MARAPR'26_V" total is not March
            pm = _sheet_month(f"{word[:3]} {m.group(2)}") if m and ok else None
            if pm is not None:
                months.setdefault(pm, {})[m.group(3).upper()] = c
        if not months:
            notes.append(f"{sh}: no month value / qty columns (like \"Mar'26 _V\") - skipped")
            continue
        base = pd.DataFrame({"store": df[sc].astype(str).str.strip().str.upper(), "division": df[up["DIVISION"]].map(plan_division),
                             "department": df[up["DEPARTMENT"]].astype(str).str.strip()})
        ac = next((c for k, c in up.items() if "ARTICLE" in k), None)
        if ac is not None:   # ARTICLE NAME, e.g. "02-ECO [KB02]"
            base["article"] = df[ac].map(lambda v: "" if v is None or v != v else " ".join(str(v).split()))
        dc = next((c for k, c in up.items() if k in ("UDF06", "UDF-06", "DISPLAY TYPE")), None)
        base["display"] = _display(df[dc]) if dc is not None else ""
        for pm, cols in sorted(months.items()):
            v = pd.to_numeric(df[cols["V"]], errors="coerce").fillna(0.0) * LAKH if "V" in cols else 0.0
            q = pd.to_numeric(df[cols["Q"]], errors="coerce").fillna(0.0) if "Q" in cols else np.nan
            frames.append(base.assign(month=pm, plan_rs=v, plan_qty=q))
    if not frames:
        raise ValueError("No usable sheet: needs STORE_NAME, DIVISION, DEPARTMENT and month columns like \"Mar'26 _V\" / \"Mar'26 _Q\". " + " ".join(notes))
    f = pd.concat(frames, ignore_index=True)
    out = f[~f.division.isin(DIVS)]
    if len(out):
        notes.append(f"{out.department.nunique()} departments outside MENS / LADIES / KIDS left out")
    f = f[f.division.isin(DIVS) & f.department.ne("") & f.store.ne("")]
    g = f.groupby(["month", "store", "division", "department", "display"] + (["article"] if "article" in f else []), as_index=False)[["plan_rs", "plan_qty"]].sum(min_count=1)
    g = g[(g.plan_rs > 0) | (g.plan_qty > 0)].reset_index(drop=True)
    notes.append(f"value read as Rs lakh: Rs {g.plan_rs.sum() / 1e7:,.1f} Cr, {g.plan_qty.sum():,.0f} pcs over {g.store.nunique()} stores")
    return g, notes


def default_shift(months):
    """The pre-selected choice on the upload card (the planner picks): a file whose months are all past is the plan for
    the same months next year (MAMJ'26 file -> MAMJ'27); otherwise as is."""
    return 12 if max(months) < pd.Period(date.today(), freq="M") else 0


def _copy(session, table, cols, frame):
    raw = session.connection().connection.dbapi_connection   # psycopg 3
    buf = io.StringIO()
    frame[cols].to_csv(buf, index=False, header=False)
    with raw.cursor() as cur:
        with cur.copy(f"COPY {table} ({','.join(cols)}) FROM STDIN WITH (FORMAT csv)") as cp:
            cp.write(buf.getvalue())


def save_upload(kind, file_name, frame, shift, user):
    """store one upload (forecast month = file month + shift); returns the upload id"""
    table = {"fixture": "planning_inputs.str_fixture_rows", "sales_plan": "planning_inputs.str_plan_rows"}[kind]
    vals = {"fixture": ["fixtures", "mdq"], "sales_plan": ["plan_rs", "plan_qty"] + (["article"] if "article" in frame else [])}[kind]
    vals += ["display"] if "display" in frame else []
    fr = frame.copy()
    fr["month"] = [(m + shift).to_timestamp().date() for m in fr["month"]]
    months = ",".join(sorted({str(m)[:7] for m in fr["month"]}))
    with SessionLocal() as s:
        uid = s.execute(text("""INSERT INTO planning_inputs.str_uploads (kind, file_name, months, month_shift, rows, uploaded_by)
                                VALUES (:k, :f, :m, :sh, :n, :u) RETURNING id"""),
                        {"k": kind, "f": file_name, "m": months, "sh": int(shift), "n": int(len(fr)), "u": user}).scalar()
        fr.insert(0, "upload_id", uid)
        _copy(s, table, ["upload_id", "month", "store", "division", "department"] + vals, fr)
        s.commit()
    return uid


def active_upload(s, kind):
    r = s.execute(text("""SELECT id, file_name, months, month_shift, rows, uploaded_by, uploaded_at FROM planning_inputs.str_uploads
                          WHERE kind = :k AND active ORDER BY uploaded_at DESC, id DESC LIMIT 1"""), {"k": kind}).mappings().first()
    return dict(r) if r else None


def rollback(kind):
    """switch the newest active upload of a kind off - the one before it (if any) is used again"""
    with SessionLocal() as s:
        u = active_upload(s, kind)
        if not u:
            return None
        s.execute(text("UPDATE planning_inputs.str_uploads SET active = false WHERE id = :i"), {"i": u["id"]})
        s.commit()
        return u


def add_edit(field, department, value, user, month=None, store=None):
    if field not in ("fixtures", "density"):
        raise ValueError("field must be fixtures or density")
    v = float(value)
    if not np.isfinite(v) or v < 0 or (field == "fixtures" and v > 1000) or (field == "density" and v > 100000):
        raise ValueError("value out of range")
    if field == "fixtures" and not (month and store):
        raise ValueError("a fixture edit needs a store and a month")
    with SessionLocal() as s:
        s.execute(text("""INSERT INTO planning_inputs.str_edits (month, store, department, field, value, edited_by)
                          VALUES (:m, :s, :d, :f, :v, :u)"""),
                  {"m": month, "s": store, "d": department, "f": field, "v": v, "u": user})
        s.commit()


def reset_department(department, user):
    """back to the file for one department: a -1 edit for every key it has edited (history kept, latest wins)"""
    with SessionLocal() as s:
        keys = s.execute(text("""SELECT DISTINCT ON (field, month, store) field, month, store, value FROM planning_inputs.str_edits
                                 WHERE department = :d ORDER BY field, month, store, edited_at DESC, id DESC"""), {"d": department}).all()
        live = [k for k in keys if k.value >= 0]
        for k in live:
            s.execute(text("""INSERT INTO planning_inputs.str_edits (month, store, department, field, value, edited_by)
                              VALUES (:m, :s, :d, :f, -1, :u)"""), {"m": k.month, "s": k.store, "d": department, "f": k.field, "u": user})
        s.commit()
        return len(live)


def version():
    """a cheap stamp of the stored inputs - any upload, rollback or edit (from any process) changes it; so does a save
    of the AOP Forecaster's store master (clusters)"""
    with SessionLocal() as s:
        v = tuple(s.execute(text("""SELECT (SELECT coalesce(max(id), 0) FROM planning_inputs.str_uploads),
                                            (SELECT count(*) FROM planning_inputs.str_uploads WHERE active),
                                            (SELECT coalesce(max(id), 0) FROM planning_inputs.str_edits)""")).one())
    for f in ("cfg", SEASON_FILE):   # AOP store master (clusters) and the cluster season curves
        try:
            if f == "cfg":
                import config_store
                f = config_store.CONFIG_FILE
            v += (os.path.getmtime(f),)
        except Exception:  # noqa: BLE001 - a missing optional input just leaves its part out
            v += (None,)
    return v


def store_clusters():
    """store -> cluster from the AOP Forecaster's Store Master (user, 9 Oct: "Add Clusters to Stores from AOP forecaster")"""
    try:
        import config_store   # Tentative AOP Forecaster/config_store.py (on sys.path above)
        return {str(s["store"]).strip().upper(): s["cluster"] for s in config_store.get_stores()["stores"] if s.get("cluster")}
    except Exception:  # noqa: BLE001 - the AOP config is optional here
        return {}


# user, 9 Oct: "split these departments in the new departments as mentioned in the core apps ... split the plan equally
# in the new departments" - the data-lake department split (5 Sep export, used suite-wide: BIS DEPT_SPLITS, Listing
# build_knowledge_base.DEPT_SPLITS, fill_rate_import.SPLITS). L_IN_BRA keeps its name there, so it is not split here.
DEPT_SPLITS = {
    "MSE_PYJAMA": ["MSE_HSR PYJAMA", "MSE_TXTL PYJAMA"], "KB_T-SHIRT H/S": ["KB_R/N T-SHIRT H/S", "KB_POLO T-SHIRT H/S"],
    "KB_BERMUDA": ["KB_HSR BERMUDA", "KB_TXTL BERMUDA"], "LW_L_PALAZZO": ["LW_L_WES PALAZZO", "LW_L_ETH PALAZZO"],
    "LW_L_JEGGING": ["LW_L_DNM JOGGER", "LW_L_WVN JOGGER"],
}


def split_depts(f, cols, ly=None):
    """an old department's row -> one row per new department; a store that already has the new name gets its part added.
    cols = {column: "sl_q" | "sl_v"}: each part's share of last year's sales (user, 9 Oct: "split the plan by LY share
    instead of 50/50") - pieces for qty / fixtures / MDQ, value for Rs - the same store and month a year earlier, else the
    chain's that month, else equal. `ly` = LY sales with month already +12; none -> equal shares."""
    old = f.department.isin(DEPT_SPLITS)
    if not old.any():
        return f
    parts = f[old].assign(old=f.department[old], department=f.department[old].map(DEPT_SPLITS)).explode("department").reset_index(drop=True)
    equal = 1.0 / parts.old.map(lambda d: len(DEPT_SPLITS[d]))
    l = None
    if ly is not None and len(ly):
        back = {n: o for o, ns in DEPT_SPLITS.items() for n in ns}
        l = ly[ly.department.isin(back)].assign(old=lambda x: x.department.map(back))
        l = l.astype({"sl_q": float, "sl_v": float})
    for c, w in cols.items():
        sh = pd.Series(np.nan, index=parts.index)
        if l is not None and len(l):
            for keys in (["month", "store"], ["month"]):   # first level with LY sales of the old department wins
                part = l.groupby(keys + ["old", "department"])[w].sum().clip(lower=0)
                tot = part.groupby(level=list(range(len(keys) + 1))).sum()
                num = part.reindex(pd.MultiIndex.from_frame(parts[keys + ["old", "department"]])).fillna(0).values
                den = tot.reindex(pd.MultiIndex.from_frame(parts[keys + ["old"]])).values
                sh = sh.fillna(pd.Series(np.where(den > 0, num / np.where(den > 0, den, 1), np.nan), index=parts.index))
        parts[c] = parts[c] * sh.fillna(equal)
    parts = parts[(parts[list(cols)].fillna(0) != 0).any(axis=1)]   # a part with no share in this store-month: no row
    f = pd.concat([f[~old], parts.drop(columns="old")], ignore_index=True)
    cols = list(cols)
    return f.groupby(["month", "store", "division", "department"] + [c for c in ("article", "display") if c in f], as_index=False)[cols].sum(min_count=1)


def _period(col):
    return pd.to_datetime(col).dt.to_period("M")


_CACHE = {}   # an upload's rows never change and LY months are closed: fetched once (user, 9 Oct: "reduce ... population time")


def _frame(s, sql, params=None, key=None):
    """query -> DataFrame built from row tuples (dict rows took ~1 s of a rebuild); `key` caches a result that cannot change"""
    if key is not None and key in _CACHE:
        return _CACHE[key].copy()
    r = s.execute(text(sql), params or {})
    df = pd.DataFrame(r.all(), columns=list(r.keys()))
    if key is not None:
        if len(_CACHE) > 20:
            _CACHE.clear()
        _CACHE[key] = df
    return df.copy()


# ---- department tags (user, 9 Oct: "Add a tab to add Core or Seasonal Tag to the department and Add Attribute to them.
# I will give the master") - planning_inputs.str_dept_tags (migration e5b9d2f1a7c3); attribute falls back to the
# suite's attribute master (masterdata.attribute_master.attribute1)
TAGS = ("CORE", "SEASONAL")
TAG_LABEL = {"CORE": "Core", "SEASONAL": "Seasonal"}


def _tag(v):
    v = str(v or "").strip().upper()
    return "CORE" if v.startswith("CORE") else "SEASONAL" if v.startswith("SEASON") else None


def read_tags(data):
    """tag master workbook -> (frame department/tag/attribute, notes). First sheet with a DEPARTMENT header; the tag
    column is the first header containing CORE, SEASON, TAG or TYPE; the attribute column the first starting ATTRIBUTE."""
    xl = pd.ExcelFile(io.BytesIO(data))
    for sh in xl.sheet_names:
        head = xl.parse(sh, header=None, nrows=10)
        hdr = next((i for i in range(len(head)) if any(str(v).strip().upper() == "DEPARTMENT" for v in head.iloc[i])), None)
        if hdr is None:
            continue
        df = xl.parse(sh, header=hdr)
        up = {str(c).strip().upper(): c for c in df.columns}
        tc = next((c for k, c in up.items() if any(w in k for w in ("CORE", "SEASON", "TAG", "TYPE"))), None)
        ac = next((c for k, c in up.items() if k.startswith("ATTRIBUTE")), None)
        if tc is None and ac is None:
            continue
        f = pd.DataFrame({"department": df[up["DEPARTMENT"]].astype(str).str.strip(),
                          "tag": df[tc].map(_tag) if tc is not None else None,
                          "attribute": df[ac].map(lambda v: str(v).strip().upper() if pd.notna(v) and str(v).strip() else None) if ac is not None else None})
        f = f[f.department.ne("") & f.department.str.upper().ne("NAN")]
        bad = int((df[tc].notna() & f.tag.isna()).sum()) if tc is not None else 0
        notes = [f"sheet {sh}: {len(f)} departments", f"tag from \"{tc}\"" if tc is not None else "no tag column",
                 f"attribute from \"{ac}\"" if ac is not None else "no attribute column"] + ([f"{bad} tag values not Core / Seasonal - left blank"] if bad else [])
        return f.drop_duplicates("department", keep="last").reset_index(drop=True), notes
    raise ValueError("No sheet with a DEPARTMENT column and a Core / Seasonal (TAG) or ATTRIBUTE column.")


def save_tags(frame, user, source):
    """upsert department tags; a blank tag / attribute in an upload keeps the stored one, an edit sets exactly what is sent"""
    keep = source != "edit"
    with SessionLocal() as s:
        for r in frame.itertuples():
            tag = r.tag if isinstance(r.tag, str) and r.tag in TAGS else None
            att = r.attribute if isinstance(r.attribute, str) and r.attribute.strip() else None
            s.execute(text(f"""INSERT INTO planning_inputs.str_dept_tags (department, tag, attribute, source, updated_by)
                               VALUES (:d, :t, :a, :s, :u)
                               ON CONFLICT (department) DO UPDATE SET
                                 tag = {"coalesce(EXCLUDED.tag, str_dept_tags.tag)" if keep else "EXCLUDED.tag"},
                                 attribute = {"coalesce(EXCLUDED.attribute, str_dept_tags.attribute)" if keep else "EXCLUDED.attribute"},
                                 source = EXCLUDED.source, updated_by = EXCLUDED.updated_by, updated_at = now()"""),
                      {"d": str(r.department).strip().upper(), "t": tag, "a": att, "s": source[:200], "u": user})
        s.commit()
    return len(frame)


def tags():
    """department -> {tag, attribute, attribute_master, source, updated_by, updated_at}; attribute = own else the master's"""
    with SessionLocal() as s:
        t = _frame(s, "SELECT department, tag, attribute, source, updated_by, updated_at FROM planning_inputs.str_dept_tags")
        try:
            am = _frame(s, "SELECT upper(trim(department)) AS d, attribute1 FROM masterdata.attribute_master WHERE attribute1 IS NOT NULL")
        except Exception:  # noqa: BLE001 - the shared master is optional
            s.rollback()
            am = pd.DataFrame(columns=["d", "attribute1"])
    master = dict(zip(am.d, am.attribute1))
    t = t.astype(object).where(t.notna(), None)   # an empty tag / attribute is None, not a truthy NaN
    out = {str(r.department).upper(): {"tag": r.tag, "attribute": r.attribute, "source": r.source, "updated_by": r.updated_by,
                          "updated_at": r.updated_at} for r in t.itertuples()}
    return out, master


def apply_inputs(df, edits):
    """fixtures / qty per fixture / MDQ after edits. Qty per fixture = the file's MDQ / fixtures; where the file has no
    MDQ, the department's median; a department density edit replaces it for every store and month."""
    df = df.copy()
    df["fixtures_file"], df["mdq_file"] = df.fixtures, df.mdq
    dens = (df.mdq / df.fixtures.where(df.fixtures > 0)).where(df.mdq > 0)
    df["density"] = dens.fillna(df.department.map(dens.groupby(df.department).median()))
    gap = (df.fixtures > 0) & (df.mdq <= 0)                       # the file has fixtures but no MDQ for it
    df["mdq_base"] = np.where(gap, df.fixtures * df.density.fillna(0.0), df.mdq)   # the file as given, gaps filled - LY bench
    changed = pd.Series(False, index=df.index)
    df["edited"] = ""
    if len(edits):
        edits = edits[edits.value >= 0]   # a -1 edit = reset to the file
    if len(edits):
        de = edits[(edits.field == "density") & edits.store.isna() & edits.month.isna()].set_index("department").value
        hit = df.department.isin(de.index)
        df.loc[hit, "density"] = df.loc[hit, "department"].map(de)
        df.loc[hit, "edited"] = "qty per fixture"
        changed |= hit
        fe = edits[(edits.field == "fixtures") & edits.store.notna() & edits.month.notna()]
        if len(fe):
            fe = fe.assign(month=_period(fe.month)).set_index(KEY).value
            v = pd.Series([fe.get(k, np.nan) for k in zip(df.month, df.store, df.department)], index=df.index)
            got = v.notna()
            df.loc[got, "fixtures"] = v[got]
            df.loc[got, "edited"] = (df.loc[got, "edited"] + ", fixtures").str.strip(", ")
            changed |= got
    df["mdq"] = np.where(changed, df.fixtures * df.density.fillna(0.0), df.mdq_base)
    return df


MIN_PCS = 10   # a store's own LY price needs at least this many pieces (thin sales give a shaky price - review 9 Oct)


def add_ly(df, lys):
    """LY qty and the average selling price; lys months already +12. Price: the store's own (>= MIN_PCS pieces and
    within 0.5-2x its department-month price) -> department x month -> department -> division x month (new / renamed
    departments; flagged)."""
    if len(lys):
        lys = lys.assign(sl_v=lys.sl_v.astype(float), sl_q=lys.sl_q.astype(float).clip(lower=0))   # returns: no negative qty
        df = df.merge(lys[KEY + ["sl_v", "sl_q"]].rename(columns={"sl_v": "ly_v", "sl_q": "ly_q"}), on=KEY, how="left")

        def price(by, name):
            g = lys.groupby(by)[["sl_v", "sl_q"]].sum()
            return (g.sl_v / g.sl_q.where(g.sl_q > 0)).rename(name)
        df = df.merge(price(["month", "department"], "asp_dm"), left_on=["month", "department"], right_index=True, how="left")
        df = df.merge(price(["department"], "asp_d"), left_on="department", right_index=True, how="left")
        df = df.merge(price(["month", "division"], "asp_vm"), left_on=["month", "division"], right_index=True, how="left")
    else:
        df = df.assign(ly_v=np.nan, ly_q=np.nan, asp_dm=np.nan, asp_d=np.nan, asp_vm=np.nan)
    df[["ly_v", "ly_q"]] = df[["ly_v", "ly_q"]].fillna(0.0)
    # a department with no LY sales under this name at all (new / renamed) has no LY STR - not a false 0%
    df["ly_known"] = df.department.isin(set(lys.department)) if len(lys) else False
    own = df.ly_v / df.ly_q.where(df.ly_q >= MIN_PCS)
    own = own.where(((own >= 0.5 * df.asp_dm) & (own <= 2 * df.asp_dm)) | df.asp_dm.isna())
    df["asp"], df["asp_from"] = np.nan, ""
    for v, name in ((own, "store"), (df.asp_dm, "department month"), (df.asp_d, "department"),
                    (df.asp_vm, "division month (no department price)")):
        take = df.asp.isna() & (v > 0)
        df.loc[take, "asp"] = v[take]
        df.loc[take, "asp_from"] = name
    by_price = (df.plan_rs / df.asp).where(df.asp > 0, 0.0).fillna(0.0)
    own_q = df["plan_qty_file"] if "plan_qty_file" in df else pd.Series(np.nan, index=df.index)
    use_own = own_q.notna() & ((own_q > 0) | (df.plan_rs <= 0))       # the plan's own qty wherever it gives one
    df["plan_qty"] = np.where(use_own, own_q.fillna(0.0), by_price)
    df["qty_from"] = np.where(use_own, "plan", np.where(by_price > 0, "Rs / LY price", ""))
    return df.drop(columns=["asp_dm", "asp_d", "asp_vm"])


def build(articles=False):
    """the full store x department x month frame (None when no fixture plan yet) + info for the page"""
    with SessionLocal() as s:
        fu, pu = active_upload(s, "fixture"), active_upload(s, "sales_plan")
        if not fu:
            return None, {"fixture": None, "sales_plan": pu}
        fx = _frame(s, "SELECT month, store, division, department, fixtures, mdq, display FROM planning_inputs.str_fixture_rows WHERE upload_id = :i",
                    {"i": fu["id"]}, key=("fx", fu["id"]))
        pl = _frame(s, "SELECT month, store, division, department, plan_rs, plan_qty AS plan_qty_file, coalesce(article, '') AS article, display FROM planning_inputs.str_plan_rows WHERE upload_id = :i",
                    {"i": pu["id"]}, key=("pl", pu["id"])) if pu else pd.DataFrame()
        ed = _frame(s, """SELECT DISTINCT ON (field, department, month, store) field, department, month, store, value
                          FROM planning_inputs.str_edits ORDER BY field, department, month, store, edited_at DESC, id DESC""")
        fx["month"] = _period(fx.month)
        months = sorted(fx.month.unique())
        lys = _frame(s, """SELECT month, store, department, plan_division AS division, sum(sl_v) AS sl_v,
                                  sum(sl_q) AS sl_q FROM calendar.sales_fact
                           WHERE kind = 'actual' AND calendar_id = 0 AND month = ANY(CAST(:m AS date[]))
                             AND plan_division = ANY(:d) GROUP BY 1, 2, 3, 4""",
                     {"m": [f"{m - 12}-01" for m in months], "d": list(DIVS)}, key=("ly", tuple(map(str, months)), date.today()))
    common = {}
    split = sorted((set(fx.department) | (set(pl.department) if len(pl) else set())) & set(DEPT_SPLITS))
    ly_sh = lys.assign(month=_period(lys.month) + 12) if len(lys) else None   # LY sales on their forecast month
    fx = split_depts(fx.astype({"fixtures": float, "mdq": float}), {"fixtures": "sl_q", "mdq": "sl_q"}, ly_sh)
    fxd = fx   # by display type (display_frame); the department frame sums it
    fx = fx.groupby(["month", "store", "division", "department"], as_index=False)[["fixtures", "mdq"]].sum()
    pld = pd.DataFrame()
    if len(pl):
        pl["month"] = _period(pl.month)
        pl = pl[pl.month.isin(months)]
        pl = split_depts(pl.astype({"plan_rs": float, "plan_qty_file": float}), {"plan_rs": "sl_v", "plan_qty_file": "sl_q"}, ly_sh)
    if len(pl) == 0 and pu:
        common = {"month_mismatch": True}   # the plan's months miss the fixture months: show the fixture view and say why
    if len(pl):
        # user, 9 Oct: "map and match the stores ... so that the comparison is apple to apple" and "the stores which have
        # their plan and fixtures only qualify those. All months should be present in both sales and fixtures" - a store
        # is compared only when every forecast month is in the fixture plan AND in the sales plan
        fs, ps = set(fx.store), set(pl.store)
        nf, np_ = fx.groupby("store").month.nunique(), pl.groupby("store").month.nunique()
        both_ = set(nf[nf == len(months)].index) & set(np_[np_ == len(months)].index)

        def gaps(f, st):
            have = set(f.month[f.store == st])
            return ", ".join(m.strftime("%b'%y") for m in months if m not in have)
        part = []
        for st in sorted((fs & ps) - both_):
            a, b = gaps(fx, st), gaps(pl, st)
            part.append(f"{st} (" + "; ".join(x for x in ((a and "no fixtures " + a), (b and "no plan " + b)) if x) + ")")
        # every store of either file with its status (user, 9 Oct: "add the mapped and unmapped store list tab")
        fmo, pmo, clm = fx.groupby("store").month.apply(set), pl.groupby("store").month.apply(set), store_clusters()
        fxm, plr = fx.groupby("store").mdq.sum(), pl.groupby("store").plan_rs.sum()
        lab = lambda ms: ", ".join(m.strftime("%b'%y") for m in months if m in ms)   # noqa: E731
        smap = []
        for st in sorted(fs | ps):
            a, b = fmo.get(st, set()), pmo.get(st, set())
            status = ("Mapped - compared" if st in both_ else "Fixture plan only" if not b else "Sales plan only" if not a
                      else "Month missing")
            miss = "; ".join(x for x in ((len(a) < len(months) and a and "no fixtures " + lab(set(months) - a)) or "",
                                          (len(b) < len(months) and b and "no plan " + lab(set(months) - b)) or "") if x)
            smap.append({"store": st, "status": status, "cluster": clm.get(st, "(no AOP cluster)"), "fixture_months": lab(a),
                         "plan_months": lab(b), "missing": miss, "mdq": float(fxm.get(st, 0.0)), "plan_rs": float(plr.get(st, 0.0))})
        common = {"stores_both": len(both_), "fixture_only": sorted(fs - ps), "plan_only": sorted(ps - fs), "part_months": part,
                  "store_map": smap,
                  "left_out_mdq": float(fx.loc[~fx.store.isin(both_), "mdq"].sum()),
                  "left_out_rs": float(pl.loc[~pl.store.isin(both_), "plan_rs"].sum())}
        fx, pl = fx[fx.store.isin(both_)], pl[pl.store.isin(both_)]
        art = pl[pl.article.ne("")] if "article" in pl else pl.iloc[0:0]
        pld = pl.groupby(KEY + ["display"], as_index=False)[["plan_rs", "plan_qty_file"]].sum(min_count=1) if "display" in pl else pd.DataFrame()
        pl = pl.groupby(KEY + ["division"], as_index=False)[["plan_rs", "plan_qty_file"]].sum(min_count=1)   # department total
        df = fx.merge(pl, on=KEY, how="outer", suffixes=("", "_p"))
        df["division"] = df["division"].fillna(df.pop("division_p"))
    else:
        df, art = fx.assign(plan_rs=0.0), pd.DataFrame()
    df[["fixtures", "mdq", "plan_rs"]] = df[["fixtures", "mdq", "plan_rs"]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    df = df[df.month.isin(months)]          # a plan month with no fixture month cannot get an STR
    df = apply_inputs(df, ed)
    df["cluster"] = df.store.map(store_clusters()).fillna("(no AOP cluster)")
    look = season_index()
    dep = df.department.str.upper()
    df["season_base"] = np.array([look.base(c, d, p.month) for c, d, p in zip(df.cluster, dep, df.month)], dtype=float)
    fd = {k: look.fest(*k) for k in set(zip(df.store, df.month))}
    sk = list(zip(df.store, df.month))
    df["fest_days"] = [sum(fd[k].values()) for k in sk]
    df["festivals"] = [", ".join(fd[k]) for k in sk]
    up, det = [], []
    for k, dd in zip(sk, dep):
        fx = fd[k]
        up.append(sum(n * (look.lift(f, dd) - 1) for f, n in fx.items()) / k[1].days_in_month if fx else 0.0)
        det.append(", ".join(f"{f} {n} days x{look.lift(f, dd):.2f}" for f, n in fx.items()))
    df["fest_uplift"], df["fest_detail"] = up, det
    df["fest_lift"] = np.where(df.fest_days > 0, 1 + df.fest_uplift * df.month.dt.days_in_month / df.fest_days.where(df.fest_days > 0, 1), 1.0)
    # the festival-free curve raised by each festival in the month: its days / the month's days x (its lift - 1)
    df["season_idx"] = df.season_base * (1 + df.fest_uplift)
    no_season = sorted(df.loc[df.season_base.isna(), "department"].unique().tolist())
    df["season_idx"] = df.season_idx.fillna(1.0)   # no season history under this name: treated as a normal month
    # user, 9 Oct: "I see generic peak tags ... I want the tags to be dynamic which ... point to the cluster's performance and
    # their respective festive period": against the whole year every summer department is peak in Mar-Jun, so the tag
    # compares a month with the same cluster x department's average month of the plan window (festivals included) -
    # peak = it stands out inside the window, off = it lags. The whole-year index stays as season_year_idx.
    df["season_year_idx"] = df.season_idx
    wm = df.groupby(["cluster", "department"]).season_year_idx.transform("mean")
    df["season_idx"] = (df.season_year_idx / wm.where(wm > 0)).fillna(1.0)   # no sales history in the window: normal
    # user, 9 Oct: "differentiate peak only if the festival is there or high sales is recorded as per the yoy avg": a month
    # high inside the window is peak only with a reason - festival days in it (with a sales lift) or its festival-free
    # history at >= 1.15x the department's average month of the year (2022-25 average); otherwise normal
    fest = (df.fest_days > 0) & (df.fest_lift > 1)
    high = df.season_base >= SEASON_CUT[0]
    df["peak_ok"] = fest | high
    df["peak_why"] = np.select([fest & high, fest, high], ["festival + high sales", "festival", "high sales"], "")
    sea = df.season_idx.map(season_of)
    df["season"] = sea.where(~(sea.eq("peak") & ~df.peak_ok), "normal")
    fests = {}
    for (c, m), g in df.loc[df.fest_days > 0, ["cluster", "month", "festivals"]].drop_duplicates().groupby(["cluster", "month"]):
        fests.setdefault(c, {})[str(m)] = sorted({x for v in g.festivals for x in v.split(", ") if x})
    if len(lys):
        lys["month"] = _period(lys.month) + 12   # LY aligned to its forecast month
    df = add_ly(df, lys)
    info = {"fixture": fu, "sales_plan": pu, "months": [str(m) for m in months], "ly_months": [str(m - 12) for m in months],
            "common": common, "split_departments": {d: DEPT_SPLITS[d] for d in split}, "qty_by_price_rows": int((df.qty_from == "Rs / LY price").sum()),
            "edits": int(len(ed)), "stores": int(df.store.nunique()), "departments": int(df.department.nunique()),
            "no_asp_rows": int(((df.plan_rs > 0) & ~(df.asp > 0)).sum()),
            "plan_without_fixtures": int(((df.plan_rs > 0) & (df.mdq <= 0)).sum()),
            "plan_rs_without_fixtures": float(df.loc[(df.plan_rs > 0) & (df.mdq <= 0), "plan_rs"].sum()),
            "mdq_without_plan": float(df.loc[(df.mdq > 0) & (df.plan_qty <= 0), "mdq"].sum()) if pu else 0.0,
            "price_from_division": sorted(df.loc[df.asp_from.str.startswith("division"), "department"].unique().tolist()),
            "no_ly_departments": sorted(df.loc[~df.ly_known, "department"].unique().tolist()),
            "no_season_departments": no_season, "season_built": look.built_at, "festivals": fests,
            "clusters": sorted(df.cluster.unique().tolist()), "season_cut": list(SEASON_CUT), "season_bands": SEASON_BANDS,
            "base_band": [BAND_MIN, BAND_MAX]}
    info["articles"] = int(art.article.nunique()) if len(art) else 0
    info["displays"] = sorted(set(fxd.display) - {""})
    return (df.reset_index(drop=True), info, art, (fxd, pld)) if articles else (df.reset_index(drop=True), info)


ART_STOCK, ART_LY = ("fixtures", "fixtures_file", "mdq", "mdq_base"), ("ly_q", "ly_v")

# user, 9 Oct: "Break it further into table and non-tbale" ... "display type": both files carry the display type (fixture
# UDF-06, sales plan UDF06: TABLE / NON_TABLE); it is kept per row and the department frame splits into it
DISPLAYS = ("TABLE", "NON_TABLE")
NO_DISP = "(no display type)"


def _display(col):
    v = col.astype(str).str.strip().str.upper().str.replace(r"[\s-]+", "_", regex=True)
    return v.where(v.isin(DISPLAYS), "")


def display_frame(df, fxd, pld):
    """the store x department x month frame split to display types: fixtures and MDQ by the display type's share in the
    fixture plan (its own rows), planned Rs / qty and last year's sales by its share of the sales plan (qty; Rs where
    the store-month has no qty). A display type with fixtures but no plan (or the reverse) gets a row with that side 0.
    Department totals unchanged; dept_mdq / dept_q keep the department's figures for the article cap."""
    base = df.assign(dept_mdq=df.mdq, dept_q=df.plan_qty)
    if fxd is None or not len(fxd) or fxd.display.eq("").all():
        return base.assign(display=NO_DISP)
    f = fxd.groupby(KEY + ["display"])[["fixtures", "mdq"]].sum()
    p = pld.groupby(KEY + ["display"])[["plan_rs", "plan_qty_file"]].sum() if len(pld) else None
    j = (f.join(p, how="outer") if p is not None else f).fillna(0.0).reset_index()
    for c in ("plan_rs", "plan_qty_file"):
        if c not in j:
            j[c] = 0.0
    t = j.groupby(KEY)
    sh = lambda c: (j[c] / t[c].transform("sum")).where(t[c].transform("sum") > 0)   # noqa: E731
    j["sh_fx"], j["sh_md"] = sh("fixtures"), sh("mdq")
    j["sh_pl"] = sh("plan_qty_file").where(t.plan_qty_file.transform("sum") > 0, sh("plan_rs"))
    j["display"] = j.display.replace("", NO_DISP)
    out = base.merge(j[KEY + ["display", "sh_fx", "sh_md", "sh_pl"]], on=KEY, how="left")
    one = out.display.isna()   # no display rows for this store-month: the department as a whole
    out["display"] = out.display.fillna(NO_DISP)
    for c, s_ in (("fixtures", "sh_fx"), ("fixtures_file", "sh_fx"), ("mdq", "sh_md"), ("mdq_base", "sh_md"),
                  ("plan_rs", "sh_pl"), ("plan_qty", "sh_pl"), ("ly_q", "sh_pl"), ("ly_v", "sh_pl")):
        if c in out:
            out[c] = out[c] * out[s_].where(~one, 1.0).fillna(0.0)
    keep = (out[["fixtures", "mdq", "plan_rs", "plan_qty"]].abs().sum(axis=1) > 0) | one
    return out[keep].drop(columns=["sh_fx", "sh_md", "sh_pl"]).reset_index(drop=True)

NO_ART = "(no article plan)"


def article_frame(df, art):
    """the store x department x month frame split to articles (user, 9 Oct: "break the fixture plan as per the sales plan
    imported and make the fixture plan as per the Cont % of sales plan"; 9 Oct: "Bifurcate each stores' plan cont % on
    month and take that cont % to divide the MDQ and Fixtures as per their store x month x dept x art name share"): each
    article's cont % = its planned QTY / the department's in that store and month (Rs share only where the store-month
    plan has no qty - the value share gave cheap articles too little MDQ); fixtures, MDQ and last year's sales
    x cont % (no article-level history - last year is apportioned the same way); the article's own planned Rs / qty.
    A store with no article plan that month takes the chain's cont % for the department; no plan at all -> NO_ART.
    Stock (user, 9 Oct: "there can be variation in STR days in Article name ... on the basis of its own performance in a
    cluster or store ... but it should be capping to the original STR decided on Department"): fixtures and MDQ follow
    the article's cont % in its AOP cluster that month, its selling rate its own store plan, so its days = the
    department's days x cluster cont / store cont - an article planned to sell faster in this store than across its
    cluster holds fewer days, never more than the department: stock share = min(store cont, cluster cont)."""
    if not len(art):
        return df.assign(article=NO_ART, cont=1.0, cont_from="no article plan")
    # inside a display type when the frame is split to them (an article's plan rows carry their display type)
    dk = ["display"] if "display" in df and "display" in art else []
    K = KEY + dk
    if dk:
        art = art.assign(display=art.display.replace("", NO_DISP))
    a = art.groupby(K + ["article"], as_index=False)[["plan_rs", "plan_qty_file"]].sum(min_count=1)
    a["w"] = a.plan_qty_file.fillna(0.0).where(a.groupby(K).plan_qty_file.transform("sum") > 0, a.plan_rs)
    a["cont"] = a.w / a.groupby(K).w.transform("sum")
    a = a[a.cont > 0]
    cl = a.store.map(df.drop_duplicates("store").set_index("store").cluster) if "cluster" in df else a.store
    gd = [cl, a.month, a.department] + [a[c] for c in dk]
    g = gd + [a.article]
    cq = a.plan_qty_file.fillna(0.0)
    cw = cq.where(cq.groupby(gd).transform("sum") > 0, a.plan_rs.fillna(0.0))   # qty share, Rs where the cluster has no qty
    a["cont_cluster"] = (cw.groupby(g).transform("sum") / cw.groupby(gd).transform("sum")).where(cl.ne("(no AOP cluster)"), a.cont)
    ch = a.groupby(["month", "department"] + dk + ["article"], as_index=False).w.sum()
    ch["cont"] = ch.w / ch.groupby(["month", "department"] + dk).w.transform("sum")
    own = df.merge(a[K + ["article", "cont", "cont_cluster", "plan_rs", "plan_qty_file"]].rename(columns={"plan_rs": "a_rs", "plan_qty_file": "a_q"}), on=K)
    own["cont_from"] = "store plan"
    rest = df[~df.set_index(K).index.isin(a.set_index(K).index.unique())]
    rest = rest.merge(ch[["month", "department"] + dk + ["article", "cont"]], on=["month", "department"] + dk, how="left")
    rest["cont_from"] = np.where(rest.article.isna(), "no article plan", "chain plan")
    rest["article"], rest["cont"] = rest.article.fillna(NO_ART), rest.cont.fillna(1.0)
    out = pd.concat([own, rest], ignore_index=True)
    out["cont_cluster"] = out.cont_cluster.fillna(out.cont) if "cont_cluster" in out else out.cont
    out["stock_cont"] = np.minimum(out.cont, out.cont_cluster)
    for c in ART_STOCK + ART_LY:
        if c in out:
            out[c] = out[c] * (out.stock_cont if c in ART_STOCK else out.cont)
    out["plan_rs"] = out.a_rs.where(out.a_rs.notna(), out.plan_rs * out.cont) if "a_rs" in out else out.plan_rs * out.cont
    out["plan_qty"] = out.a_q.where(out.a_q.notna(), out.plan_qty * out.cont) if "a_q" in out else out.plan_qty * out.cont
    if "dept_mdq" in out:   # never more days than the department in that store and month (a display type can run slower)
        cap = (out.dept_mdq * out.plan_qty / out.dept_q.where(out.dept_q > 0)).where(out.plan_qty > 0)
        r = (cap / out.mdq.where(out.mdq > 0)).clip(upper=1.0).fillna(1.0)
        for c in ART_STOCK:
            if c in out:
                out[c] = out[c] * r
    return out.drop(columns=[c for c in ("a_rs", "a_q") if c in out]).reset_index(drop=True)


def str_of(qty, mdq):
    qty, mdq = np.asarray(qty, float), np.asarray(mdq, float)
    den = qty + mdq
    return np.where(den > 0, qty / np.where(den > 0, den, 1), np.nan)


def days_of(qty, mdq, n_days, n_months=1):
    """STR in days (user, 9 Oct: "STR should be in days like 60 Days, 30 Days"): how many days the minimum display stock
    lasts at the planned selling rate = average MDQ / (qty per day). = days in month x (1 / STR - 1) for one month."""
    if not qty or qty <= 0 or not n_days:
        return None
    return float((mdq / n_months) / (qty / n_days))


# user, 9 Oct: "give me STR days according to the nearest round ranging from a store base minimum to 60 till 180 max
# after the actual STR is calculated" - actual days rounded to the nearest 30, kept between 60 and 180
BAND_STEP, BAND_MIN, BAND_MAX = 30, 60, 180


# user, 9 Oct: "incorporate the seasonality trends from the Listing - Delisting Analyser App where peak seasons can be
# differentiated from the normal ones and STR can differ according to it". Season of a department x month = its
# festival-free sales rate that month / its 12-month average, 2022-25, per AOP cluster (str_season.py; was the chain curve of
# the Listing app windows.json until the user asked for cluster curves), peak / off at the
# Listing app's own in / off season index (1.15 / 0.85). The band keeps the nearest-30 rounding; only its limits move:
# every season = the base rule 60-180 (user, 9 Oct: "range for all tags seasonality is 60 -180 remove 90 - 180 range"; off
# was 90-180 before). The user's
# 60-day minimum and 180-day maximum hold for every season (user, 9 Oct: "why is 30 days STR being suggested where min
# 60 Days - max 180 days is capping" - peak was 30-90 by my default).
SEASON_FILE = os.path.join(HERE, "season_cluster.json")   # str_season.py (user, 9 Oct: "use each cluster's own season curve")
SEASON_BANDS = {"peak": (BAND_MIN, BAND_MAX), "normal": (BAND_MIN, BAND_MAX), "off": (BAND_MIN, BAND_MAX)}
SEASON_CUT = [1.15, 0.85]


class _Season:
    """season inputs from str_season.py: base(cluster, DEPT, month) = the cluster's festival-free curve (chain where the
    cluster has few stores), fest(store, period) = (festival days, names) of the store's own calendar cluster that month,
    lift(cluster, DEPT) = sales lift on its Mar-Jun festival days (user, 9 Oct: "Take festivals falling in MAMJ into account")"""
    def __init__(self, w):
        self.w, self.built_at = w, w.get("built_at")
        self.ch, self.cl = w.get("chain", {}), w.get("cluster", {})
        self.lf, self.lh = w.get("fest_lift_by_festival", {}), w.get("fest_lift_chain", {})
        self.fd, self.sc = w.get("fest_days", {}), w.get("store_cal", {})

    def base(self, c, d, m):
        v = self.cl.get(c, {}).get(d) or self.ch.get(d)
        return v[m - 1] if v else None

    def fest(self, s, p):
        """{festival: its days} in the store's own calendar cluster that month"""
        v = self.fd.get(self.sc.get(s, "ALL"), {}).get(f"{p.year}-{p.month:02d}", {})
        return v if isinstance(v, dict) else {}

    def lift(self, f, d):
        """the department's sales lift on festival f (learnt from every store that celebrates it)"""
        return self.lf.get(f, {}).get(d) or self.lh.get(d) or 1.0


def season_index():
    """the season inputs (empty when str_season.py has not run: every month normal); sets SEASON_CUT"""
    try:
        with open(SEASON_FILE, encoding="utf-8") as fh:
            w = json.load(fh)
    except Exception:  # noqa: BLE001 - not built yet
        w = {}
    SEASON_CUT[:] = [float(x) for x in w.get("cut", SEASON_CUT)]
    return _Season(w)


def season_of(idx):
    if idx is None or idx != idx:
        return None
    return "peak" if idx >= SEASON_CUT[0] else "off" if idx <= SEASON_CUT[1] else "normal"


def str_band(days, season=None):
    """54 -> 60, 75 -> 90 (half rounds up), 104 -> 90, 105 -> 120, 250 -> 180; None stays None. With a season the
    limits are that season's (all 60-180 today), never outside BAND_MIN-BAND_MAX"""
    if days is None or days != days:
        return None
    lo, hi = SEASON_BANDS.get(season, (BAND_MIN, BAND_MAX))
    lo, hi = max(lo, BAND_MIN), min(hi, BAND_MAX)
    return int(min(max(np.floor(days / BAND_STEP + 0.5) * BAND_STEP, lo), hi))


def rollup(df, by, months, has_plan=True):
    """rows grouped by `by`, each with per-month and total qty / MDQ / STR / LY STR (sum first, then the ratio);
    no sales plan loaded -> forecast STR None (never a false 0%). Biggest MDQ first within the first key."""
    # summed per group x month in one groupby, the ratios after (user, 9 Oct: "reduce toggle delay") - same figures as
    # a per-group loop. Forecast: rows with both a plan and fixtures (plan with no fixtures = 100%, fixtures with no plan
    # = 0% - both reported apart in info, never inside a total); no plan loaded -> MDQ shown, STR None (never a false 0%).
    # LY: store-months that sold last year, in departments with LY sales under their name (else not open / renamed).
    both = ((df.mdq > 0) & (df.plan_qty > 0)) if has_plan else pd.Series(False, index=df.index)
    lyv = df.ly_known.astype(bool) & (df.ly_q > 0)
    a = pd.DataFrame({k: df[k].values for k in by})
    a["mi"] = pd.Index(months).get_indexer(df.month)
    a["q"], a["md"] = np.where(both, df.plan_qty, 0.0), (np.where(both, df.mdq, 0.0) if has_plan else df.mdq.values)
    a["nb"], a["lq"], a["lmd"], a["nl"] = both.values.astype(int), np.where(lyv, df.ly_q, 0.0), np.where(lyv, df.mdq_base, 0.0), lyv.values.astype(int)
    a["fixtures"], a["plan_rs"], a["ed"] = df.fixtures.values, df.plan_rs.values, (df.edited != "").values.astype(int)
    # season of a group = its departments' season index weighted by planned qty
    a["sq"] = np.where(both, df.plan_qty * (df["season_idx"] if "season_idx" in df else 1.0), 0.0)
    a["sy"] = np.where(both, df.plan_qty * (df["season_year_idx"] if "season_year_idx" in df else 1.0), 0.0)
    a["fq"] = np.where(both & (df["fest_days"] > 0 if "fest_days" in df else False), df.plan_qty, 0.0)   # planned qty in festival months
    a["pk"] = np.where(both & (df["peak_ok"] if "peak_ok" in df else True), df.plan_qty, 0.0)   # planned qty with a peak reason
    a = a[a.mi >= 0]
    V = ["q", "md", "nb", "lq", "lmd", "nl", "fixtures", "plan_rs", "ed", "sq", "sy", "fq", "pk"]
    g = a.groupby(by + ["mi"], dropna=False, sort=True)[V].sum()
    dim = [m.days_in_month for m in months]
    ldim = [(m - 12).days_in_month for m in months]

    def cell(s, nd, nm, lnd, lnm):
        # days: over the months that have matched rows (days in those months; LY = the same months a year earlier)
        days = days_of(s[0], s[1], nd, nm) if nm else None
        ly_days = days_of(s[3], s[4], lnd, lnm) if lnm else None
        sidx = s[9] / s[0] if s[2] and s[0] > 0 else None
        sea = season_of(sidx)
        if sea == "peak" and s[12] < 0.5 * s[0]:   # most of its plan has no festival / high-sales reason
            sea = "normal"
        return {"qty": float(s[0]), "mdq": float(s[1]), "str": float(str_of(s[0], s[1])) if s[2] else None,
                "days": days, "ly_days": ly_days, "band": str_band(days, sea), "ly_band": str_band(ly_days, sea),
                "base_band": str_band(days), "ly_base_band": str_band(ly_days), "season": sea, "season_idx": sidx, "sq": float(s[9]), "sy": float(s[10]), "fq": float(s[11]), "pk": float(s[12]),
                "season_year": s[10] / s[0] if sidx is not None else None, "fest_share": s[11] / s[0] if sidx is not None else None,
                "ly_qty": float(s[3]), "ly_mdq": float(s[4]), "ly_str": float(str_of(s[3], s[4])) if s[5] else None,
                "fixtures": float(s[6]), "plan_rs": float(s[7]), "rows": int(s[2]), "ly_rows": int(s[5]),
                "n_days": nd if nm else 0, "n_months": nm, "ly_n_days": lnd if lnm else 0, "ly_n_months": lnm}
    acc = {}
    for t in g.itertuples():
        keys, mi = t[0][:-1], t[0][-1]
        acc.setdefault(keys, [[0.0] * len(V) for _ in months])[mi] = list(t[1:])
    out = []
    for keys, ms in acc.items():
        row = dict(zip(by, keys))
        cells = [cell(s, dim[i], 1 if s[2] else 0, ldim[i], 1 if s[5] else 0) for i, s in enumerate(ms)]
        tot = [sum(s[j] for s in ms) for j in range(len(V))]
        pm, lm = [i for i, s in enumerate(ms) if s[2]], [i for i, s in enumerate(ms) if s[5]]
        row.update(months=cells, total=cell(tot, sum(dim[i] for i in pm), len(pm), sum(ldim[i] for i in lm), len(lm)),
                   edited=bool(tot[8]))
        out.append(row)
    if len(by) > 1:   # department view: divisions together, biggest departments first
        out.sort(key=lambda r: (str(r[by[0]]), -r["total"]["mdq"]))
    elif by[0] == "store":
        out.sort(key=lambda r: -r["total"]["mdq"])
    return out


if __name__ == "__main__":   # self-check of the maths on tiny frames (no DB)
    P = lambda s: pd.Period(s, freq="M")   # noqa: E731
    assert np.allclose(str_of([30, 0, 10], [70, 0, 0]), [0.3, np.nan, 1.0], equal_nan=True)
    assert _sheet_month("Jun'26") == P("2026-06") and _sheet_month("JUNE 2026") == P("2026-06") and _sheet_month("Total") is None
    base = pd.DataFrame({"month": [P("2027-03")] * 3, "store": ["S1", "S2", "S3"], "division": ["MENS"] * 3,
                         "department": ["A"] * 3, "fixtures": [2.0, 1.0, 1.0], "mdq": [200.0, 100.0, 0.0], "plan_rs": [3000.0, 0.0, 0.0]})
    d = apply_inputs(base, pd.DataFrame())
    assert list(d.mdq) == [200.0, 100.0, 100.0]          # S3 had no MDQ: fixtures x the department's median 100
    ed = pd.DataFrame({"field": ["fixtures", "density"], "department": ["A", "A"], "month": [pd.Timestamp("2027-03-01"), None],
                       "store": ["S1", None], "value": [3.0, 50.0]})
    d = apply_inputs(base, ed)
    assert list(d.fixtures) == [3.0, 1.0, 1.0] and list(d.mdq) == [150.0, 50.0, 50.0]   # edits: 3 fixtures; 50 per fixture
    lys = pd.DataFrame({"month": [P("2027-03")], "store": ["S1"], "department": ["A"], "division": ["MENS"], "sl_v": [1000.0], "sl_q": [10.0]})
    d = add_ly(d, lys)
    assert d.plan_qty.iloc[0] == 30.0 and d.asp_from.iloc[0] == "store"   # 3000 / (1000 / 10)
    d3 = add_ly(apply_inputs(base, ed).assign(plan_qty_file=[45.0, np.nan, np.nan]), lys)
    assert d3.plan_qty.iloc[0] == 45.0 and d3.qty_from.iloc[0] == "plan"   # the plan's own qty, not 3000 / 100
    assert PLAN_COL.match("June'26 _Q") and PLAN_COL.match("Mar'26 _V") and _sheet_month("MAM 26") is None   # MAMJ total ignored
    r = rollup(d, ["division"], [P("2027-03")])[0]
    assert abs(r["total"]["str"] - 30 / (30 + 150)) < 1e-12        # forecast: only S1 has both a plan and fixtures
    assert abs(r["total"]["ly_str"] - 10 / (10 + 200)) < 1e-12     # LY: only S1 sold LY; its file MDQ (no edits)
    d2 = add_ly(apply_inputs(base, pd.DataFrame()), lys.assign(sl_q=[5.0]))   # 5 pieces < MIN_PCS: department-month price
    assert d2.asp_from.iloc[0] == "department month"
    ed2 = pd.concat([ed, pd.DataFrame({"field": ["density"], "department": ["A"], "month": [None], "store": [None], "value": [-1.0]})])
    ed2 = ed2.drop_duplicates(["field", "department", "month", "store"], keep="last")
    assert list(apply_inputs(base, ed2).mdq) == [300.0, 100.0, 100.0]   # density reset to the file (100); S1 fixture edit 3 stays
    assert abs(days_of(30, 150, 31) - 155.0) < 1e-9 and days_of(0, 150, 31) is None   # 150 pcs at 30 a month of 31 days
    t = r["months"][0]
    assert abs(t["days"] - 150 / (30 / 31)) < 1e-9 and abs(t["ly_days"] - 200 / (10 / 31)) < 1e-9   # Mar'27 / Mar'26: 31 days
    assert [str_band(x) for x in (20, 54, 75, 104, 105, 250, None)] == [60, 60, 90, 90, 120, 180, None]
    assert t["band"] == 150 and t["ly_band"] == 180          # 155 days -> 150; 620 days -> capped at 180
    assert (str_band(45, "peak"), str_band(150, "peak"), str_band(40, "off"), str_band(40, "normal")) == (60, 150, 60, 60)
    assert min(str_band(d, s) for d in (1, 20, 44, 400) for s in ("peak", "normal", "off", None)) >= BAND_MIN   # never under 60
    assert (season_of(1.2), season_of(1.0), season_of(0.8), season_of(None)) == ("peak", "normal", "off", None)
    rs = rollup(d.assign(season_idx=1.3), ["division"], [P("2027-03")])[0]["months"][0]
    assert rs["season"] == "peak" and rs["band"] == 150 and rs["base_band"] == 150   # 155 days: peak keeps the 180 max
    assert (_tag(" core"), _tag("Seasonal"), _tag("x"), _tag(None)) == ("CORE", "SEASONAL", None, None)
    sp = split_depts(pd.DataFrame({"month": [P("2027-03")] * 2, "store": ["S1"] * 2, "division": ["MENS"] * 2,
                                   "department": ["MSE_PYJAMA", "MSE_TXTL PYJAMA"], "plan_rs": [100.0, 10.0], "q": [np.nan, 4.0]}), {"plan_rs": "sl_v", "q": "sl_q"})
    assert sp.set_index("department").plan_rs.to_dict() == {"MSE_HSR PYJAMA": 50.0, "MSE_TXTL PYJAMA": 60.0}   # half each, added
    assert np.isnan(sp.set_index("department").q["MSE_HSR PYJAMA"])                                         # no qty stays no qty
    lyx = pd.DataFrame({"month": [P("2027-03")] * 3, "store": ["S1", "S1", "S2"], "department": ["MSE_HSR PYJAMA", "MSE_TXTL PYJAMA", "MSE_TXTL PYJAMA"],
                        "sl_q": [30.0, 10.0, 5.0], "sl_v": [600.0, 400.0, 100.0]})
    f3 = pd.DataFrame({"month": [P("2027-03")] * 3, "store": ["S1", "S2", "S3"], "division": ["MENS"] * 3, "department": ["MSE_PYJAMA"] * 3,
                       "mdq": [100.0] * 3, "plan_rs": [100.0] * 3})
    sp = split_depts(f3, {"mdq": "sl_q", "plan_rs": "sl_v"}, lyx).set_index(["store", "department"])
    assert sp.mdq[("S1", "MSE_HSR PYJAMA")] == 75.0 and sp.plan_rs[("S1", "MSE_HSR PYJAMA")] == 60.0   # S1's own LY: 30 of 40 pcs, 600 of 1000 Rs
    assert ("S2", "MSE_HSR PYJAMA") not in sp.index and sp.mdq[("S2", "MSE_TXTL PYJAMA")] == 100.0   # S2 sold only TXTL: no HSR row
    assert abs(sp.mdq[("S3", "MSE_HSR PYJAMA")] - 100 * 30 / 45) < 1e-9                         # S3 no LY: chain month share
    fr = pd.DataFrame({"month": [P("2027-03")] * 2, "store": ["S1", "S2"], "department": ["A", "A"], "division": ["MENS"] * 2,
                       "fixtures": [4.0, 2.0], "fixtures_file": [4.0, 2.0], "mdq": [400.0, 200.0], "mdq_base": [400.0, 200.0],
                       "ly_q": [10.0, 0.0], "ly_v": [100.0, 0.0], "plan_rs": [1000.0, 50.0], "plan_qty": [10.0, 1.0]})
    ar = pd.DataFrame({"month": [P("2027-03")] * 2, "store": ["S1", "S1"], "department": ["A", "A"], "division": ["MENS"] * 2,
                       "article": ["ECO", "PREM"], "plan_rs": [600.0, 400.0], "plan_qty_file": [8.0, 2.0]})
    af = article_frame(fr, ar).set_index(["store", "article"])
    assert af.mdq[("S1", "ECO")] == 320.0 and af.plan_qty[("S1", "PREM")] == 2.0     # 80% of the qty -> 80% of MDQ; own qty
    assert af.mdq[("S2", "ECO")] == 160.0 and af.cont_from[("S2", "ECO")] == "chain plan"   # S2 has no article plan: chain
    assert abs(af.mdq.sum() - fr.mdq.sum()) < 1e-9 and abs(af.fixtures.sum() - fr.fixtures.sum()) < 1e-9   # adds back
    # two stores of one cluster: S1 sells ECO 80%, S3 20% -> cluster ECO 50%; S1 ECO stock 50% (fewer days), PREM capped
    f2 = fr.assign(store=["S1", "S3"], cluster=["C1", "C1"], mdq=[400.0, 400.0], plan_qty=[10.0, 10.0])
    a2 = pd.concat([ar, ar.assign(store="S3", plan_qty_file=[2.0, 8.0])], ignore_index=True)
    a2 = article_frame(f2, a2).set_index(["store", "article"])
    assert a2.mdq[("S1", "ECO")] == 200.0 and a2.mdq[("S1", "PREM")] == 80.0   # 25 days (x .5/.8) and 40 = the department's
    dd = a2.mdq / a2.plan_qty
    assert (dd <= 400.0 / 10.0 + 1e-9).all() and dd[("S1", "ECO")] < 40.0      # never above the department, some below
    # display types: S1 dept A = TABLE 1 fixture / 100 MDQ + NON_TABLE 3 / 300; plan TABLE 2 pcs, NON_TABLE 8
    fd = pd.DataFrame({"month": [P("2027-03")] * 2, "store": ["S1"] * 2, "department": ["A"] * 2, "display": ["TABLE", "NON_TABLE"],
                       "fixtures": [1.0, 3.0], "mdq": [100.0, 300.0]})
    pd_ = pd.DataFrame({"month": [P("2027-03")] * 2, "store": ["S1"] * 2, "department": ["A"] * 2, "display": ["TABLE", "NON_TABLE"],
                        "plan_rs": [100.0, 900.0], "plan_qty_file": [2.0, 8.0]})
    dv = display_frame(fr, fd, pd_).set_index(["store", "display"])
    assert dv.mdq[("S1", "TABLE")] == 100.0 and dv.plan_qty[("S1", "TABLE")] == 2.0 and dv.fixtures[("S1", "NON_TABLE")] == 3.0
    assert dv.mdq[("S2", NO_DISP)] == 200.0                                     # no display rows: the department whole
    assert abs(dv.mdq.sum() - fr.mdq.sum()) < 1e-9 and abs(dv.plan_qty.sum() - fr.plan_qty.sum()) < 1e-9
    # articles inside TABLE (50 days vs the department's 40): capped at the department
    ad = article_frame(dv.reset_index(), ar.assign(display="TABLE", plan_qty_file=[1.0, 1.0])).set_index(["store", "display", "article"])
    t = ad.sort_index().loc[("S1", "TABLE")]
    assert ((t.mdq / t.plan_qty) <= 400.0 / 10.0 + 1e-9).all()
    print("str_engine self-check: OK")
