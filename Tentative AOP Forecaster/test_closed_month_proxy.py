"""Closed-month decision + FY26 proxy base (2026-09-24 rules). No DB/network.
Run directly: python test_closed_month_proxy.py
"""
import datetime

from engine_v3 import FY27_M, _open_months, apply_proxy_base, build_growth_map, pass1_forecasts
from sync.common import closed_through_from_last_day, snapshot_last_day
from sync.store_actuals_sync import _closed_through, _complete_months
import pandas as pd

D = datetime.date

# ── closed month: only when the data includes the month's LAST day ──
assert snapshot_last_day("x_20260905T054337.parquet") == D(2026, 9, 4)
assert snapshot_last_day("no_stamp.parquet") is None
assert closed_through_from_last_day(D(2026, 9, 4)) == "2026-08"    # Sep not closed -> month-1
assert closed_through_from_last_day(D(2026, 8, 30)) == "2026-07"   # Aug's last day missing
assert closed_through_from_last_day(D(2026, 8, 31)) == "2026-08"
assert closed_through_from_last_day(D(2026, 12, 31)) == "2026-12"
assert _closed_through("x_20260905T054337.parquet", "2026-09") == "2026-08"
assert _closed_through("x_20260905T054337.parquet", "2026-07") == "2026-07"   # capped by data
assert _closed_through("no_stamp.parquet", "2026-09", today=D(2026, 9, 24)) == "2026-08"  # old rule
keep, skipped = _complete_months(["2026-07", "2026-08", "2026-09"], "2026-08")
assert keep == ["2026-07", "2026-08"] and skipped == ["2026-09"]

# engine: persisted value wins; date rule only as fallback
assert _open_months(closed_through="2026-08") == set(FY27_M[6:])          # Sep'26..Mar'27 open
assert _open_months(closed_through="2026-07") == set(FY27_M[5:])          # Aug'26 too
assert _open_months(as_of=D(2026, 9, 24)) == set(FY27_M[6:])

# ── proxy base: open month -> same month FY26 actual x (1+g) ──
store_info = {"LFL1": {"tag": "LFL"}, "RMP1": {"tag": "Ramp"}}
actuals = {"LFL1": {"MENS": {m: (10.0 if m not in FY27_M[6:] else 0.0) for m in FY27_M}}}
proxy = {"LFL1": {"MENS": {"Sep'26": 8.0, "Feb'27": 5.0}},        # keyed by the FY27 month it stands in for
         "RMP1": {"MENS": {"Sep'26": 99.0}}}
proxy["LFL1"]["MENS"]["Mar'27"] = 7.0                               # must be ignored (Mar'28 rule)
open_m = _open_months(closed_through="2026-08")
base, cells = apply_proxy_base(actuals, proxy, store_info, open_m)
growth = pd.DataFrame([["OVERALL"] + [10.0] * 12], columns=["Division"] + ["Apr'27", "May'27", "Jun'27", "Jul'27",
                      "Aug'27", "Sep'27", "Oct'27", "Nov'27", "Dec'27", "Jan'28", "Feb'28", "Mar'28"])
fc = pass1_forecasts(store_info, base, build_growth_map(growth))["LFL1"]["MENS"]
assert abs(fc["Sep'27"] - 8.8) < 1e-9          # proxy Sep'25 x 1.10 (was 0)
assert abs(fc["Feb'28"] - 5.5) < 1e-9
assert fc["Oct'27"] == 0.0                     # no FY26 value either -> stays 0
assert fc["Mar'28"] == 0.0                     # waits for a real closed Mar'27
assert abs(fc["Aug'27"] - 11.0) < 1e-9         # closed month untouched
assert cells == {("LFL1", "MENS", "Sep'27"), ("LFL1", "MENS", "Feb'28")}
assert "RMP1" not in base                      # Ramp own base never proxied
assert actuals["LFL1"]["MENS"]["Sep'26"] == 0.0  # input pivot not mutated
# once Sep'26 closes, the real actual replaces the proxy
base2, cells2 = apply_proxy_base(actuals, proxy, store_info, _open_months(closed_through="2026-09"))
assert ("LFL1", "MENS", "Sep'27") not in cells2 and base2["LFL1"]["MENS"]["Sep'26"] == 0.0

print("test_closed_month_proxy: all passed")
