"""Article split for the STR Forecaster - prepared ahead of the user's article sheet (user, 9 Oct: "I will give an Article
name Sheet too so you can break the fixture plan as per the sales plan imported and make the fixture plan as per the Cont %
of sales plan ... keep it handy as i will be needing it as on urgent basis").

    read_plan_detail(data, name)  the sales plan below department: store x department x MRP x ATTRIBUTE x ATTRIBUTE 2 x
                                  UDF06 (TABLE / NON_TABLE) x month, plan Rs + qty (the STR engine sums these away)
    read_articles(data)           the article sheet: DEPARTMENT + ARTICLE, plus whatever links it to the plan - any of
                                  MRP / ATTRIBUTE / ATTRIBUTE 2 / UDF06 - or its own CONT % / SHARE column
    split(fx, detail, arts, keys) each store x department x month fixture row -> one row per article with
                                  fixtures and MDQ x the article's cont % of the department's plan:
                                    1. the store's own plan that month (article plan / department plan),
                                    2. else the chain's plan for the department that month,
                                    3. else the sheet's own CONT %, else equal; plan rows no article claims -> "(other)"
                                  so a department's fixtures / MDQ always add back to the fixture plan.
Not wired into the page or the DB yet - the sheet's layout decides the join; run python str_article.py for the check."""
import io
import re

import numpy as np
import pandas as pd

KEYS = ("mrp", "attribute", "attribute2", "udf06")          # plan columns an article can be defined by
HEAD = {"MRP": "mrp", "ATTRIBUTE": "attribute", "ATTRIBUTE 2": "attribute2", "ATTRIBUTE2": "attribute2", "UDF06": "udf06",
        "UDF-06": "udf06", "UDF 06": "udf06"}
OTHER = "(other)"
FULL = ("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "SEPT", "OCTOBER",
        "NOVEMBER", "DECEMBER")


def _norm(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)                                            # MRP 299.0 -> "299"
    return " ".join(str(v).split()).upper()


def read_plan_detail(data, name=""):
    """sales plan workbook -> (frame month(file month) / store / division / department / mrp / attribute / attribute2 /
    udf06 / plan_rs / plan_qty, notes); same month columns as str_engine.read_sales_plan ("Mar'26 _V" Rs lakh, "_Q" pcs)"""
    import str_engine as se
    xl = pd.ExcelFile(io.BytesIO(data), engine="pyxlsb" if name.lower().endswith(".xlsb") else None)
    frames, notes = [], []
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        up = {str(c).strip().upper(): c for c in df.columns}
        sc = up.get("STORE_NAME", up.get("STORE"))
        if sc is None or "DEPARTMENT" not in up or "DIVISION" not in up:
            notes.append(f"{sh}: no STORE_NAME / DIVISION / DEPARTMENT - skipped")
            continue
        months = {}
        for c in df.columns:
            m = se.PLAN_COL.match(str(c))
            word = m.group(1).upper() if m else ""
            pm = se._sheet_month(f"{word[:3]} {m.group(2)}") if m and (len(word) == 3 or word in FULL) else None
            if pm is not None:
                months.setdefault(pm, {})[m.group(3).upper()] = c
        base = pd.DataFrame({"store": df[sc].map(_norm), "division": df[up["DIVISION"]].map(se.plan_division),
                             "department": df[up["DEPARTMENT"]].astype(str).str.strip()})
        for k in KEYS:
            h = next((h for h, kk in HEAD.items() if kk == k and h in up), None)
            base[k] = df[up[h]].map(_norm) if h else ""
        for pm, cols in sorted(months.items()):
            frames.append(base.assign(month=pm,
                                      plan_rs=pd.to_numeric(df[cols["V"]], errors="coerce").fillna(0.0) * se.LAKH if "V" in cols else 0.0,
                                      plan_qty=pd.to_numeric(df[cols["Q"]], errors="coerce").fillna(0.0) if "Q" in cols else 0.0))
    if not frames:
        raise ValueError("No usable sheet: needs STORE_NAME, DIVISION, DEPARTMENT and month columns like \"Mar'26 _V\". " + " ".join(notes))
    f = pd.concat(frames, ignore_index=True)
    f = f[f.division.isin(se.DIVS)]
    g = f.groupby(["month", "store", "division", "department", *KEYS], as_index=False)[["plan_rs", "plan_qty"]].sum()
    g = g[(g.plan_rs > 0) | (g.plan_qty > 0)].reset_index(drop=True)
    notes.append(f"{len(g):,} plan rows below department; " + ", ".join(f"{k} {g[k].nunique()}" for k in KEYS) + " distinct values")
    return g, notes


def read_articles(data):
    """article sheet -> (frame department / article / [link keys] / [share], keys used, notes). The ARTICLE column is the
    first header containing ARTICLE; a CONT % / SHARE / % column is the sheet's own share, used only where the plan
    gives no split."""
    xl = pd.ExcelFile(io.BytesIO(data))
    for sh in xl.sheet_names:
        head = xl.parse(sh, header=None, nrows=10)
        hdr = next((i for i in range(len(head)) if any(str(v).strip().upper() == "DEPARTMENT" for v in head.iloc[i])), None)
        if hdr is None:
            continue
        df = xl.parse(sh, header=hdr)
        up = {str(c).strip().upper(): c for c in df.columns}
        ac = next((c for k, c in up.items() if "ARTICLE" in k), None)
        if ac is None:
            continue
        out = pd.DataFrame({"department": df[up["DEPARTMENT"]].astype(str).str.strip(), "article": df[ac].map(_norm)})
        keys = []
        for h, k in HEAD.items():
            if h in up and k not in keys:
                out[k] = df[up[h]].map(_norm)
                keys.append(k)
        sc = next((c for k, c in up.items() if re.search(r"CONT|SHARE|%", k) and "ARTICLE" not in k), None)
        if sc is not None:
            v = pd.to_numeric(df[sc], errors="coerce")
            out["share"] = v / 100 if v.max() > 1.5 else v      # 25 or 0.25
        out = out[out.department.ne("") & out.article.ne("")]
        notes = [f"sheet {sh}: {len(out)} rows, {out.article.nunique()} articles in {out.department.nunique()} departments",
                 f"linked to the plan by {', '.join(keys)}" if keys else ("own CONT % column" if "share" in out else
                                                                           "no link to the plan and no CONT % - equal split")]
        return out.drop_duplicates(["department", *keys, "article"]).reset_index(drop=True), keys, notes
    raise ValueError("No sheet with a DEPARTMENT column and an ARTICLE column.")


def split(fx, detail, arts, keys, basis="plan_qty"):
    """fx: month / store / department / fixtures / mdq (forecast months); detail: read_plan_detail rows with month already on
    the forecast month; arts / keys: read_articles. -> fx rows x articles with cont, cont_from, fixtures, mdq."""
    k = ["month", "store", "department"]
    if keys:
        d = detail.merge(arts[["department", *keys, "article"]], on=["department", *keys], how="left")
        d["article"] = d.article.fillna(OTHER)
        a = d.groupby(k + ["article"])[basis].sum().rename("v").reset_index()
        a["cont"] = a.v / a.groupby(k).v.transform("sum")
        own = a[a.cont.notna()][k + ["article", "cont"]].assign(cont_from="store plan")
        c = d.groupby(["month", "department", "article"])[basis].sum().rename("v").reset_index()
        c["cont"] = c.v / c.groupby(["month", "department"]).v.transform("sum")
        chain = c[c.cont.notna()][["month", "department", "article", "cont"]].assign(cont_from="chain plan")
        has = fx[k].merge(own[k].drop_duplicates(), on=k, how="left", indicator=True)["_merge"].eq("both").values
        out = pd.concat([fx[has].merge(own, on=k), fx[~has].merge(chain, on=["month", "department"])], ignore_index=True)
        done = set(map(tuple, out[k].drop_duplicates().values))
        rest = fx[[tuple(r) not in done for r in fx[k].values]]
    else:
        out, rest = fx.iloc[0:0].assign(article="", cont=0.0, cont_from=""), fx
    if len(rest):   # no plan to split by: the sheet's own share, else equal
        sh = arts.groupby(["department", "article"], as_index=False)["share"].sum() if "share" in arts else \
            arts.drop_duplicates(["department", "article"])[["department", "article"]].assign(share=1.0)
        sh["cont"] = sh.share / sh.groupby("department").share.transform("sum")
        r = rest.merge(sh[["department", "article", "cont"]], on="department", how="left")
        r["cont_from"] = np.where(r.article.isna(), "no article for this department", "sheet CONT %" if "share" in arts else "equal")
        r["article"], r["cont"] = r.article.fillna(OTHER), r.cont.fillna(1.0)
        out = pd.concat([out, r], ignore_index=True)
    out["fixtures"], out["mdq"] = out.fixtures * out.cont, out.mdq * out.cont
    return out.reset_index(drop=True)


if __name__ == "__main__":   # self-check on tiny frames
    P = pd.Period("2027-03", freq="M")
    fx = pd.DataFrame({"month": [P] * 3, "store": ["S1", "S2", "S3"], "department": ["D", "D", "E"],
                       "fixtures": [10.0, 4.0, 6.0], "mdq": [1000.0, 400.0, 600.0]})
    det = pd.DataFrame({"month": [P] * 4, "store": ["S1", "S1", "S1", "S9"], "department": ["D"] * 4,
                        "mrp": ["299", "399", "499", "299"], "attribute": [""] * 4, "attribute2": [""] * 4, "udf06": [""] * 4,
                        "plan_rs": [0.0] * 4, "plan_qty": [60.0, 30.0, 10.0, 50.0]})
    arts = pd.DataFrame({"department": ["D", "D", "E", "E"], "mrp": ["299", "399", "", ""], "article": ["A1", "A2", "E1", "E2"]})
    o = split(fx, det, arts, ["mrp"]).set_index(["store", "article"])
    assert abs(o.mdq[("S1", "A1")] - 600) < 1e-9 and abs(o.mdq[("S1", "A2")] - 300) < 1e-9 and abs(o.mdq[("S1", OTHER)] - 100) < 1e-9
    assert abs(o.mdq[("S2", "A1")] - 400 * 110 / 150) < 1e-9 and o.loc[("S2", "A1"), "cont_from"] == "chain plan"   # S2: chain
    assert abs(o.mdq[("S3", "E1")] - 300) < 1e-9 and o.loc[("S3", "E1"), "cont_from"] == "equal"                    # E: no plan
    assert abs(o.mdq.sum() - fx.mdq.sum()) < 1e-6 and abs(o.fixtures.sum() - fx.fixtures.sum()) < 1e-6           # adds back
    print("str_article self-check: OK")
