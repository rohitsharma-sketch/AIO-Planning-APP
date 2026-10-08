"""The ONE roll-up from the data lake's DIVISION values to the five planning divisions (user, 2026-10-08: "add DND to
the retail division" and NON FOOD = GM everywhere). New code imports this; the older copies (AOP
sync/store_actuals_sync._norm_div, db/reindexed_base_sales, app.py dept_mix, Sales Plan actuals_manager, Calendar
ReindexOutputPanel PLAN_DIVISIONS) follow the same rule and move onto this module as each app switches to the
multi-year calendar sales (Phase 1+).

Not planned (None): NON-TRADING, FIXED ASSETS, CONSIGNMENT, CDIT, blanks.
"""
PLAN_DIVISIONS = ("MENS", "LADIES", "KIDS", "GM", "RETAIL")

_ROLLUP = {
    "MENS": "MENS", "LADIES": "LADIES", "KIDS": "KIDS", "GM": "GM",
    "RETAIL": "RETAIL", "DND": "RETAIL",
    "NON FOOD": "GM", "FOOTWEAR": "GM", "HOME FURNISHING": "GM", "HOUSEHOLD": "GM", "LIFESTYLE": "GM",
    "SPORTS & TOYS": "GM", "STATIONERY": "GM", "TRAVEL ACCESSORIES": "GM",
}


def norm(raw):
    """Upper-case, single spaces ('SPORTS  & TOYS' in the export -> 'SPORTS & TOYS')."""
    return " ".join(str(raw or "").upper().split())


def plan_division(raw):
    """'MENS' | 'LADIES' | 'KIDS' | 'GM' | 'RETAIL', or None when the division is not planned."""
    return _ROLLUP.get(norm(raw))


if __name__ == "__main__":   # python rs_common/divisions.py
    assert plan_division("SPORTS  & TOYS") == "GM" and plan_division("non food") == "GM"
    assert plan_division("DND") == "RETAIL" and plan_division("RETAIL") == "RETAIL"
    assert plan_division("NON-TRADING") is None and plan_division(None) is None and plan_division("CDIT") is None
    print("divisions: OK")
