"""python -m pytest tools/test_manual_parity.py - the manual's half-month inputs are read the same way every time
(user, 2026-10-15: "unless i add a rule or subtract a rule this should not be deviating on every iteration")."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import manual_parity as MP   # noqa: E402

MAN = {"source": "t.xlsx", "month_ref": {"NSO1": "REF1"},
       "cmp": [{"cluster": "C1", "division": "KIDS", "section": "S", "dept": "KB_BERMUDA", "attr": "A",   # a split parent
                "ly": {("Mar'26", "P1"): 3.0, ("Mar'26", "P2"): 1.0}, "plan": {}},
               {"cluster": "C1", "division": "LADIES", "section": "S", "dept": "L_EW_SAREE_SILK", "attr": "A",
                "ly": {("Mar'26", "P1"): 0.0, ("Mar'26", "P2"): 2.0, ("Apr'26", "P1"): 0.0, ("Apr'26", "P2"): 0.0}, "plan": {}}],
       "aop": [{"store": "REF1", "ref": "REF1", "cluster": "C1", "tag": "", "group": "SSG", "division": "KIDS",
                "half": {("Mar'27", "P1"): 6.0, ("Mar'27", "P2"): 4.0}},
               {"store": "REF1", "ref": "REF1", "cluster": "C1", "tag": "", "group": "SSG", "division": "GM",
                "half": {("Mar'27", "P1"): 9.0, ("Mar'27", "P2"): 0.0}}]}


def test_inputs():
    ly, ao = MP.build_inputs(MAN)
    c1 = ly["shares"]["C1"]
    assert c1["L_EW_SAREE_SILK"] == {"Mar'26": 0.0}                                   # all in P2: kept (was dropped)
    assert "Apr'26" not in c1["L_EW_SAREE_SILK"]                                     # no LY that month: nothing
    assert c1["KB_HSR BERMUDA"] == c1["KB_TXTL BERMUDA"] == {"Mar'26": 0.75}          # the parent's split to its parts
    assert ao["shares"]["REF1"] == {"Mar'27": 0.6}                                    # apparel only (GM left out)
    assert ao["div_shares"]["REF1"]["KIDS"] == {"Mar'27": 0.6} and "GM" not in ao["div_shares"]["REF1"]
    assert ao["month_ref"] == {"NSO1": "REF1"}
