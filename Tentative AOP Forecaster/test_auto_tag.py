"""Self-check for the plan LfL cut-off (run: python test_auto_tag.py)."""
import datetime as dt
from engine_v3 import auto_tag, LFL_CUTOFF

assert LFL_CUTOFF == dt.date(2025, 12, 31)
assert auto_tag("032 - Stores", dt.date(2018, 5, 1), "SAME STORE") == "032 - Stores"   # agrees: kept
assert auto_tag("FY26 - Q3", dt.date(2025, 12, 31), "NEW STORE") == "FY26 - Q3"        # Dec opening = LfL
assert auto_tag("FY26 - Q4", dt.date(2025, 12, 20), "NEW STORE") == "LFL"              # mis-tagged: promoted
assert auto_tag("FY26 - Q1", dt.date(2026, 1, 5), "NEW STORE") == "Ramp"               # Jan opening: ambiguous
assert auto_tag("080 - Stores", dt.date(2019, 3, 1), "CLOSED STORE") == "Ramp"         # not trading
assert auto_tag("FY27 - Q2", dt.date(2000, 1, 1), "UPCOMING_STORE") == "FY27 - Q2"     # placeholder date
assert auto_tag("NSO", dt.date(2020, 1, 1), "SAME STORE") == "NSO"
print("ok")
