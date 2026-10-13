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
            assert all(A.CAP_LO <= x[2] <= A.CAP_HI for x in r["info"].values())
        g = "C1" if grain == "cluster" else "A"
        jr = by[(g, "ML_JEANS")]
        assert jr["method"] == "deviation"
        if grain == "cluster":
            # cluster LY (netted over its stores) EPP 2 / ECO 2 = 50/50; buyer 90/10 -> 1.8 capped 1.5, 0.2 capped 0.5
            assert abs(jr["info"]["01-EPP [ML04]"][2] - 1.5) < 1e-12 and jr["info"]["02-ECO [ML04]"][2] == 0.5
            assert abs(jr["arts"]["01-EPP [ML04]"]["Mar'27"] - 30 * 3 / 4) < 1e-9   # new base 3 : 1 of 30
        pj = by[(g, "MSE_HSR PYJAMA")]   # split part: the old department's % by tier, no deviation
        assert pj["method"] == "buyer" and abs(pj["arts"]["01-EPP [MS21]"]["Mar'27"] - pj["aop"]["Mar'27"] * 0.25) < 1e-9
        assert by[(g, "MU_NEW")]["method"] == "buyer"
        assert by[(g, "MU_WIN")]["method"] == "ly"
    st = {(r["g"], r["dept"]): r["method"] for r in A.build("store", plan, cont, ly, {"pass": True}, M)["rows"]}
    assert st[("C", "ML_JEANS")] == "cluster" and st[("C", "MU_WIN")] == "cluster"   # no LY of its own
    assert A.tier("07-SUPER-PREMIUM [LW33]") == "SUPER-PREMIUM" and A.tier("01. EPP") == "EPP"
