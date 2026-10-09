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
    else the sheet name. TABLE + NON_TABLE rows of a store x department are summed."""
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
            "mdq": pd.to_numeric(df["MDQ"], errors="coerce").fillna(0.0)}))
    if not frames:
        raise ValueError("No usable sheet: each month needs STORE, DIVISION, DEPARTMENT, a fixture column and MDQ. " + " ".join(notes))
    f = pd.concat(frames, ignore_index=True)
    left_out = f[~f.division.isin(DIVS)]
    if len(left_out):
        notes.append(f"{left_out.department.nunique()} GM / other departments left out (no Capacity / MDQ) - MENS, LADIES, KIDS only")
    f = f[f.division.isin(DIVS)]
    g = f.groupby(["month", "store", "division", "department"], as_index=False)[["fixtures", "mdq"]].sum()
    return g[(g.fixtures > 0) | (g.mdq > 0)].reset_index(drop=True), notes


PLAN_COL = re.compile(r"^\s*([A-Za-z]{3,9})\W*(\d{2}|\d{4})\s*_\s*([VQ])\s*$")   # "Mar'26 _V", "June'26 _Q"
LAKH = 1e5


def read_sales_plan(data, name=""):
    """Store-level sales plan (user, 9 Oct: "MAMJ'26 - Sales Plan.xlsx") -> (frame month/store/division/department/
    plan_rs/plan_qty, notes). Columns STORE_NAME (or STORE), DIVISION, DEPARTMENT and one "<Mon>'<yy> _V" (Rs lakh) and
    "<Mon>'<yy> _Q" (pieces) pair per month; MRP / ATTRIBUTE / TABLE-NON_TABLE rows of a store x department are summed;
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
    g = f.groupby(["month", "store", "division", "department"], as_index=False)[["plan_rs", "plan_qty"]].sum(min_count=1)
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
    vals = {"fixture": ["fixtures", "mdq"], "sales_plan": ["plan_rs", "plan_qty"]}[kind]
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
    try:
        import config_store
        return v + (os.path.getmtime(config_store.CONFIG_FILE),)
    except Exception:  # noqa: BLE001 - no AOP config: clusters just stay empty
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


def split_depts(f, cols):
    """an old department's row -> one row per new department, each with an equal share of `cols` (fixtures, MDQ, plan);
    a store that already has the new name gets the share added to it"""
    old = f.department.isin(DEPT_SPLITS)
    if not old.any():
        return f
    parts = f[old].assign(department=f.department[old].map(DEPT_SPLITS)).explode("department")
    parts[cols] = parts[cols].div(f.department[old].map(lambda d: len(DEPT_SPLITS[d])).reindex(parts.index), axis=0)
    f = pd.concat([f[~old], parts], ignore_index=True)
    return f.groupby(["month", "store", "division", "department"], as_index=False)[cols].sum(min_count=1)


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


def build():
    """the full store x department x month frame (None when no fixture plan yet) + info for the page"""
    with SessionLocal() as s:
        fu, pu = active_upload(s, "fixture"), active_upload(s, "sales_plan")
        if not fu:
            return None, {"fixture": None, "sales_plan": pu}
        fx = _frame(s, "SELECT month, store, division, department, fixtures, mdq FROM planning_inputs.str_fixture_rows WHERE upload_id = :i",
                    {"i": fu["id"]}, key=("fx", fu["id"]))
        pl = _frame(s, "SELECT month, store, division, department, plan_rs, plan_qty AS plan_qty_file FROM planning_inputs.str_plan_rows WHERE upload_id = :i",
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
    fx = split_depts(fx.astype({"fixtures": float, "mdq": float}), ["fixtures", "mdq"])
    if len(pl):
        pl["month"] = _period(pl.month)
        pl = pl[pl.month.isin(months)]
        pl = split_depts(pl.astype({"plan_rs": float, "plan_qty_file": float}), ["plan_rs", "plan_qty_file"])
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
        common = {"stores_both": len(both_), "fixture_only": sorted(fs - ps), "plan_only": sorted(ps - fs), "part_months": part,
                  "left_out_mdq": float(fx.loc[~fx.store.isin(both_), "mdq"].sum()),
                  "left_out_rs": float(pl.loc[~pl.store.isin(both_), "plan_rs"].sum())}
        fx, pl = fx[fx.store.isin(both_)], pl[pl.store.isin(both_)]
        df = fx.merge(pl, on=KEY, how="outer", suffixes=("", "_p"))
        df["division"] = df["division"].fillna(df.pop("division_p"))
    else:
        df = fx.assign(plan_rs=0.0)
    df[["fixtures", "mdq", "plan_rs"]] = df[["fixtures", "mdq", "plan_rs"]].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    df = df[df.month.isin(months)]          # a plan month with no fixture month cannot get an STR
    df = apply_inputs(df, ed)
    df["cluster"] = df.store.map(store_clusters()).fillna("(no AOP cluster)")
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
            "no_ly_departments": sorted(df.loc[~df.ly_known, "department"].unique().tolist())}
    return df.reset_index(drop=True), info


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


def str_band(days):
    """54 -> 60, 75 -> 90 (half rounds up), 104 -> 90, 105 -> 120, 250 -> 180; None stays None"""
    if days is None or days != days:
        return None
    return int(min(max(np.floor(days / BAND_STEP + 0.5) * BAND_STEP, BAND_MIN), BAND_MAX))


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
    a = a[a.mi >= 0]
    V = ["q", "md", "nb", "lq", "lmd", "nl", "fixtures", "plan_rs", "ed"]
    g = a.groupby(by + ["mi"], dropna=False, sort=True)[V].sum()
    dim = [m.days_in_month for m in months]
    ldim = [(m - 12).days_in_month for m in months]

    def cell(s, nd, nm, lnd, lnm):
        # days: over the months that have matched rows (days in those months; LY = the same months a year earlier)
        days = days_of(s[0], s[1], nd, nm) if nm else None
        ly_days = days_of(s[3], s[4], lnd, lnm) if lnm else None
        return {"qty": float(s[0]), "mdq": float(s[1]), "str": float(str_of(s[0], s[1])) if s[2] else None,
                "days": days, "ly_days": ly_days, "band": str_band(days), "ly_band": str_band(ly_days),
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
    assert (_tag(" core"), _tag("Seasonal"), _tag("x"), _tag(None)) == ("CORE", "SEASONAL", None, None)
    sp = split_depts(pd.DataFrame({"month": [P("2027-03")] * 2, "store": ["S1"] * 2, "division": ["MENS"] * 2,
                                   "department": ["MSE_PYJAMA", "MSE_TXTL PYJAMA"], "plan_rs": [100.0, 10.0], "q": [np.nan, 4.0]}), ["plan_rs", "q"])
    assert sp.set_index("department").plan_rs.to_dict() == {"MSE_HSR PYJAMA": 50.0, "MSE_TXTL PYJAMA": 60.0}   # half each, added
    assert np.isnan(sp.set_index("department").q["MSE_HSR PYJAMA"])                                         # no qty stays no qty
    print("str_engine self-check: OK")
