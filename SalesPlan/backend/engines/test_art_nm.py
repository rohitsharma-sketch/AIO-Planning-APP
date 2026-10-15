"""Article Name route (art_nm_engine): deviation caps, buyer % for new / split departments, fallbacks, articles = AOP.
python -m pytest engines/test_art_nm.py"""
import pandas as pd

from engines import art_nm_engine as A

M = ["Mar'27", "Apr'27"]


def _plan(depts):
    """stores A, B, C (C has no LY) all in cluster C1. depts = {dept: ty per store per month}."""
    mk = lambda: {"divisions": {"MENS": {"months": {m: {"departments": {d: {"ty": t, "active": True}
                                                                       for d, t in depts.items()}} for m in M}}}}   # noqa: E731
    return {"stores": {s: {"cluster": "C1", **mk()} for s in ("A", "B", "C")}}


def test_route():
    cont = A.parse_cont(pd.DataFrame({
        "DIVISION": ["MENS"] * 5, "DEPARTMENT": ["ML_JEANS", "ML_JEANS", "MSE_PYJAMA", "MSE_PYJAMA", "MU_NEW"],
        "NEW ARTICLE_NAME": ["01-EPP [ML04]", "02-ECO [ML04]", "01-EPP [MS07]", "02-ECO [MS07]", "02-ECO [MU01]"],
        "BUYERS INPUT\nAT MAMJ": [0.9, 0.1, 0.25, 0.75, 1.0],
        "MC TAG": ["EXISTING ACTIVE MC", "EXISTING ACTIVE MC", "NEW SPLIT MC", "NEW SPLIT MC", "NEW ACTIVE MC"]}))
    assert cont["block"] == "MAMJ" and abs(sum(cont["depts"]["ML_JEANS"]["arts"].values()) - 100) < 1e-9
    ly = {("A", "ML_JEANS"): {"01-EPP [ML04]": {m: 1.0 for m in M}, "02-ECO [ML04]": {m: 3.0 for m in M}},
          ("B", "ML_JEANS"): {"01-EPP [ML04]": {m: 1.0 for m in M}, "02-ECO [ML04]": {m: -1.0 for m in M}},
          ("A", "MSE_HSR PYJAMA"): {"01-EPP [MS21]": {m: 9.0 for m in M}, "02-ECO [MS21]": {m: 1.0 for m in M}},
          ("A", "MU_WIN"): {"01-EPP [MU09]": {m: 2.0 for m in M}}}
    plan = _plan({"ML_JEANS": 10.0, "MSE_HSR PYJAMA": 4.0, "MU_NEW": 2.0, "MU_WIN": 1.0, "MU_NEG": -0.01})
    for grain in ("cluster", "store"):
        b = A.build(grain, plan, cont, ly, {"pass": True}, M)
        by = {(r["g"], r["dept"]): r for r in b["rows"]}
        for r in b["rows"]:   # every group x department x month adds back to the department AOP (negative -> 0)
            for m in M:
                got = sum(v.get(m, 0.0) for v in r["arts"].values())
                assert abs(got - max(r["aop"][m], 0.0)) < 1e-9 and all(v.get(m, 0.0) >= 0 for v in r["arts"].values())
            assert all(A.CAP_LO <= x[4] <= A.CAP_HI for am in r["info"].values() for x in am.values() if x[4] is not None)
        g = "C1" if grain == "cluster" else "A"
        jr = by[(g, "ML_JEANS")]
        assert jr["method"] == "deviation"
        if grain == "cluster":
            # cluster LY (netted over its stores) EPP 2 / ECO 2 = 50/50; buyer 90/10 -> 1.8 capped 1.5, 0.2 capped 0.5
            w = jr["info"]["01-EPP [ML04]"]["Mar'27"]   # (LY, LY cont %, input %, deviation, capped, resultant)
            assert w[1] == 50.0 and abs(w[3] - 1.8) < 1e-12 and w[4] == 1.5 and w[5] == 75.0
            assert jr["info"]["02-ECO [ML04]"]["Mar'27"][4] == 0.5
            assert abs(jr["arts"]["01-EPP [ML04]"]["Mar'27"] - 30 * 3 / 4) < 1e-9   # new base 3 : 1 of 30
        pj = by[(g, "MSE_HSR PYJAMA")]   # split part: the old department's % by tier, no deviation
        assert pj["method"] == "buyer" and abs(pj["arts"]["01-EPP [MS21]"]["Mar'27"] - pj["aop"]["Mar'27"] * 0.25) < 1e-9
        assert by[(g, "MU_NEW")]["method"] == "buyer"
        assert by[(g, "MU_WIN")]["method"] == "ly"
    st = {(r["g"], r["dept"]): r["method"] for r in A.build("store", plan, cont, ly, {"pass": True}, M)["rows"]}
    assert st[("C", "ML_JEANS")] == "cluster" and st[("C", "MU_WIN")] == "cluster"   # no LY of its own
    assert A.tier("07-SUPER-PREMIUM [LW33]") == "SUPER-PREMIUM" and A.tier("01. EPP") == "EPP"


def test_promote_split():
    """Promote: each group x department x article plan over MRP bands by the group's LY article x MRP mix, then the
    chain's article mix, then the department's; the bands add back to the article plan."""
    b = {"rows": [{"g": "S1", "div": "MENS", "dept": "ML_JEANS", "arts": {"01-EPP [ML04]": {"Mar'27": 10.0}, "02-ECO [ML04]": {"Mar'27": 6.0}}},
                  {"g": "S2", "div": "MENS", "dept": "ML_JEANS", "arts": {"01-EPP [ML04]": {"Mar'27": 4.0}, "09-NEW [ML04]": {"Mar'27": 2.0}}}]}
    mix = {("S1", "ML_JEANS", "01-EPP [ML04]"): {"299": 3.0, "399": 1.0}, ("S1", "ML_JEANS", "02-ECO [ML04]"): {"499": 2.0}}
    out, how = A.promote_split(b, mix, {"S1": "C1", "S2": "C1"})
    j = out["MENS"]["ML_JEANS"]
    # S1 EPP 10 -> 7.5 / 2.5; S2 EPP 4 (no mix of its own) -> the chain's EPP mix 3 / 1; 09-NEW 2 -> the department's 3:1:2
    assert abs(j["299"]["Mar'27"] - (7.5 + 3.0 + 1.0)) < 1e-9 and abs(j["399"]["Mar'27"] - (2.5 + 1.0 + 2 / 6)) < 1e-9
    assert abs(sum(v["Mar'27"] for v in j.values()) - 22.0) < 1e-9   # 09-NEW: no mix of its own -> the department's
    assert how == {"own": 16.0, "chain article": 4.0, "chain department": 2.0}


def test_monthly_deviation_inactive_and_new_article():
    """The deviation is taken month by month; an IN-ACTIVE MC counts as 0%; a new article name takes its input %."""
    cont = A.parse_cont(pd.DataFrame({
        "DEPARTMENT": ["ML_JEANS", "ML_JEANS", "ML_JEANS", "MU_OFF", "MU_OFF"],
        "NEW ARTICLE_NAME": ["01-EPP [ML04]", "02-ECO [ML04]", "09-NEW [ML04]", "01-EPP [MU01]", "02-ECO [MU01]"],
        "MC STATUS": ["ACTIVE", "IN-ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE"],
        "BUYERS INPUT AT MAMJ": [0.6, 0.3, 0.1, 0.7, 0.3],
        "MC TAG": ["EXISTING ACTIVE MC"] * 3 + ["IN-ACTIVE MC"] * 2}))
    j, o = cont["depts"]["ML_JEANS"], cont["depts"]["MU_OFF"]
    assert j["arts"]["02-ECO [ML04]"] == 0.0 and j["given"]["02-ECO [ML04]"] == 30.0   # in-active article
    assert all(v == 0.0 for v in o["arts"].values())                                       # in-active MC
    ly = {("S1", "ML_JEANS"): {"01-EPP [ML04]": {"Mar'27": 1.0, "Apr'27": 3.0}, "02-ECO [ML04]": {"Mar'27": 3.0, "Apr'27": 1.0}},
          ("S1", "MU_OFF"): {"01-EPP [MU01]": {"Mar'27": 1.0, "Apr'27": 1.0}, "02-ECO [MU01]": {"Mar'27": 3.0, "Apr'27": 3.0}}}
    plan = {"stores": {"S1": {"cluster": "C1", "divisions": {"MENS": {"months": {m: {"departments": {
        "ML_JEANS": {"ty": 10.0, "active": True}, "MU_OFF": {"ty": 4.0, "active": True}}} for m in M}}}}}}
    b = A.build("store", plan, cont, ly, {"pass": True}, M)
    r = {x["dept"]: x for x in b["rows"]}
    jr = r["ML_JEANS"]
    # Mar: LY cont 25 / 75; EPP 60/25 = 2.4 -> 1.5 (res 37.5), ECO 0/75 -> 0.5 (res 37.5); Apr: 75 / 25 -> 0.8 (60) and
    # 0.5 (12.5). 09-NEW (never sold) takes its 10% as it is; the others share the other 90% by their resultants
    assert jr["info"]["01-EPP [ML04]"]["Mar'27"][4] == 1.5 and abs(jr["info"]["01-EPP [ML04]"]["Apr'27"][4] - 0.8) < 1e-12
    assert abs(jr["arts"]["09-NEW [ML04]"]["Mar'27"] - 1.0) < 1e-9
    assert abs(jr["arts"]["01-EPP [ML04]"]["Mar'27"] - 4.5) < 1e-9 and abs(jr["arts"]["01-EPP [ML04]"]["Apr'27"] - 9 * 60 / 72.5) < 1e-9
    # in-active MC: input 0% -> every deviation at the 50% floor -> the LY mix
    mo = r["MU_OFF"]
    assert mo["method"] == "inactive" and abs(mo["arts"]["01-EPP [MU01]"]["Mar'27"] - 1.0) < 1e-9


def test_post_check(monkeypatch):
    """Post-generation: article plan = department sales plan per department x month (a negative cluster/store plan
    counts as 0), and the like-for-like plan = the AOP per division x month - a moved plan is caught."""
    import engines.mrp_plan_engine as MP
    import engines.dept_sales_engine as DS
    plan = {"stores": {s: {"cluster": "C1", "is_ssg": s == "A", "divisions": {"MENS": {"months": {m: {"departments": {
        "ML_JEANS": {"ty": 10.0, "active": True}, "MU_NEG": {"ty": -0.01 if s == "B" else 0.0, "active": True}}}
        for m in M}}}} for s in ("A", "B")}}
    monkeypatch.setattr(MP, "_load_dept_plan", lambda: plan)
    monkeypatch.setattr(DS, "_aop_lfl_targets", lambda: {"MENS": {"Mar'27": 10.0, "Apr'27": 9.0}})
    ly = {("A", "ML_JEANS"): {"01-EPP [ML04]": {m: 1.0 for m in M}}, ("B", "ML_JEANS"): {"01-EPP [ML04]": {m: 2.0 for m in M}}}
    b = A.build("store", plan, None, ly, {"pass": True}, M)
    s = A.post_check(b)["summary"]
    assert s["dept_off"] == 0 and s["dept_neg"] == 2   # MU_NEG's -0.01 in B: articles 0, not a mismatch
    assert s["aop_cells"] == 2 and s["aop_off"] == 1   # Apr'27: like-for-like plan 10 vs AOP 9
    b["rows"][0]["arts"]["01-EPP [ML04]"]["Mar'27"] += 0.5
    assert A.post_check(b)["summary"]["dept_off"] == 1


def test_month_aop_unrounded():
    """The publish rounds each division x month to 2 decimals; within that rounding the store plan's own total wins."""
    from engines.dept_sales_engine import month_aop
    assert month_aop(12994.77, 12994.7705, 3) == 12994.7705   # Mar'27, publish 119 vs its store plan
    assert month_aop(100.0, 120.0, 3) == 100.0                # a real gap: the published AOP stays
    assert month_aop(0.0, 5.0, 3) == 0.0                      # nothing published: unchanged
