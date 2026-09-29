"""No-DB check: PW/W and SOR read their block from the imported files' month columns (user, 2026-09-29).
Everything runs on temp copies - the real folders and saved results are untouched.
Run: python engines/test_deviation_blocks.py   (from SalesPlan/backend)"""
import os
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fastapi import HTTPException  # noqa: E402
from engines import pww_deviation_engine as pww, sor_deviation_engine as sor  # noqa: E402

tmp = tempfile.mkdtemp()
pww.PWW_SOURCE_PATH = os.path.join(tmp, "ppo.xlsx")
pww.PWW_PPO_PATH = os.path.join(tmp, "ppo.json")
pww.PWW_META_PATH = os.path.join(tmp, "meta.json")

# PW/W: the wide template -> block MAMJ, per-month mix kept, average = the single value Phase 1 uses
wide = pd.DataFrame({"DEPARTMENT": ["KBW_JACKET", "KBW_JACKET"], "ARTICLE NAME": ["01-EPP", "02-ECO"],
                     "FINAL MRP": [349, 599], "Mar'27": [0.25, 0.75], "Apr'27": [0.5, 0.5],
                     "May'27": [0.4, 0.6], "Jun'27": [0.1, 0.9]})
wide.to_excel(pww.PWW_SOURCE_PATH, index=False)
r = pww.sync_ppo()
assert r["block"] == "MAMJ" and r["ty_months"] == ["Mar'27", "Apr'27", "May'27", "Jun'27"], r
row = pww._load_ppo()["KBW_JACKET"][0]
assert row["months"] == {"Mar'27": 25.0, "Apr'27": 50.0, "May'27": 40.0, "Jun'27": 10.0} and row["ppo_cont_pct"] == 31.25, row
assert pww.get_status()["block"] == "MAMJ"

# the old single-column file is refused, with the template in the message
wide[["DEPARTMENT", "ARTICLE NAME", "FINAL MRP"]].assign(**{"TY PPO CONT %": 0.5}).to_excel(pww.PWW_SOURCE_PATH, index=False)
try:
    pww.sync_ppo()
    raise SystemExit("old format should be refused")
except HTTPException as e:
    assert e.status_code == 422 and "month" in e.detail.lower(), e.detail

# SOR: both files from the folder, months detected; files with different months are refused
sor.SOR_SOURCES = {"plan": os.path.join(tmp, "plan.xlsx"), "ppo": os.path.join(tmp, "stock.xlsx")}
sor.SOR_PLAN_PATH, sor.SOR_PPO_PATH = os.path.join(tmp, "p.json"), os.path.join(tmp, "o.json")
base = {"ATTRIBUTE-1": ["SUMMER"], "DEPARTMENT": ["KBW_JACKET"], "ARTICLE NAME": ["01-EPP"], "FINAL MRP": [349]}
pd.DataFrame({**base, "Mar-27": [0.2], "Apr-27": [0.3], "May-27": [0.3], "Jun-27": [0.2]}).to_excel(sor.SOR_SOURCES["plan"], index=False)
pd.DataFrame({**base, "Mar'27": [0.1], "Apr'27": [0.4], "May'27": [0.3], "Jun'27": [0.2]}).to_excel(sor.SOR_SOURCES["ppo"], index=False)
r = sor.sor_sync()
assert r["block"] == "MAMJ" and r["months"] == ["Mar'27", "Apr'27", "May'27", "Jun'27"], r
st = sor.sor_status()
assert st["block"] == "MAMJ" and st["pww_block"] == "MAMJ", st
pd.DataFrame({**base, "Apr'27": [0.4], "May'27": [0.3], "Jun'27": [0.2]}).to_excel(sor.SOR_SOURCES["ppo"], index=False)
try:
    sor.sor_sync()
    raise SystemExit("different months should be refused")
except HTTPException as e:
    assert e.status_code == 422 and "differ" in e.detail, e.detail
print("deviation block checks passed")
