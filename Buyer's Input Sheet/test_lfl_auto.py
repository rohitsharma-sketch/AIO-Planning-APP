"""Self-check for the auto LFL detector (run: python test_lfl_auto.py)."""
import pandas as pd
from sync_server import lfl_by_month, FY25_DATE_TO_MI, FY26_DATE_TO_MI

APR24, APR25, MAY24, MAY25 = (2024, 4), (2025, 4), (2024, 5), (2025, 5)
traded = {("OLD", APR24), ("OLD", APR25), ("OLD", MAY24), ("OLD", MAY25),
          ("NEW", APR25), ("NEW", MAY25),                      # opened in FY26
          ("MID", APR24), ("MID", APR25), ("MID", MAY24), ("MID", MAY25),
          ("SHUT", APR24), ("SHUT", MAY24), ("SHUT", MAY25)}   # dark Apr-25
opened = {"MID": pd.Timestamp(2024, 4, 20), "OLD": pd.NaT}     # part-month Apr-24
m = lfl_by_month(traded, opened, FY25_DATE_TO_MI, FY26_DATE_TO_MI)
assert m[0] == {"OLD"}, m[0]                  # Apr: MID part-month, SHUT dark
assert m[1] == {"OLD", "MID", "SHUT"}, m[1]   # May: all that traded both years
assert m[2] == set()
print("ok")
