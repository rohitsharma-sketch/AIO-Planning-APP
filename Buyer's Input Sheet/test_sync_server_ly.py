"""No-network check: BIS's LY months are exactly AOP's plan months one year
earlier (the 2026-09-25 bug: Mar'26 + Apr-Jun'25 made LY 336.4 vs AOP 388.9).
Run: python test_sync_server_ly.py"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
sys.path.insert(0, os.path.join(here, "..", "Tentative AOP Forecaster"))
import sync_server as ss
from db.publish_aop_targets import MAMJ

plan = sorted(divmod(p, 100) for p in MAMJ.values())            # [(2027, 3) .. (2027, 6)]
ly = sorted(ss.AOP_LY_DATES.values())
assert ly == [(y - 1, m) for y, m in plan], (ly, plan)
assert len({y for y, _ in ly}) == 1, f"LY mixes years: {ly}"
assert ss.LY_DEF in ss._data_version() or ss._data_version() == "unknown"
# a finished sync is reused only while the export it read is still current (audit 2026-10-07)
done = {"status": "done", "data": {"data_version": "v1"}}
assert ss._job_fresh(done, "v1") and not ss._job_fresh(done, "v2")
assert not ss._job_fresh({"status": "running", "data": None}, "v1")
print(f"test_sync_server_ly: OK (plan {plan[0]}-{plan[-1]}, LY {ly[0]}-{ly[-1]})")
