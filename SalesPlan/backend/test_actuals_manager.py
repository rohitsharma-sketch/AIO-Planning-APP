"""No-DB check: Calendar snapshot months/divisions map onto Sales Plan's LY labels.
Run: python test_actuals_manager.py   (from SalesPlan/backend)"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import actuals_manager as am  # noqa: E402

# Reindexed columns are the TY (plan) month; the engines look them up by the LY label one year earlier.
assert am._ly_label("2027-04", "reindexed") == ("Apr'26", (2026, 4))
assert am._ly_label("2026-04", "actual") == ("Apr'26", (2026, 4))
# Raw divisions roll up to the plan divisions (the export has a double space in SPORTS  & TOYS).
assert am._plan_div("SPORTS  & TOYS") == "GM" and am._plan_div("KIDS") == "KIDS" and am._plan_div("DND") == "RETAIL"
assert am._plan_div("NON FOOD") == "GM" and am._plan_div("NON-TRADING") is None   # 2026-10-08: DND -> RETAIL, NON FOOD -> GM
# A month is usable only once it has fully elapsed.
today = datetime.date(2026, 9, 28)
assert am._closed(2026, 8, today) and not am._closed(2026, 9, today)
assert am.ly_to_ty_month("Mar'26") == "Mar'27"
print("actuals manager checks passed")
