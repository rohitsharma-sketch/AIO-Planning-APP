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
# weighted factor model (factor builder, 2026-10-07): the page's default passes, broken ones are refused
import copy, json, re
html = open(os.path.join(here, "otb-plan-app.html"), encoding="utf-8").read()
js = re.search(r"const FM_DEFAULT=(\{.*?\});\n", html, re.S).group(1)
good = json.loads(re.sub(r"([{,]\s*)(\w+):", r'\1"\2":', js).replace("'", '"'))   # JS object literal -> JSON
assert ss._model_error(good) is None, ss._model_error(good)
for path, val in ((["drivers", 0, "weight"], 101), (["drivers", 0, "slabs", 2, "from"], 0.01), (["clamp", 0], 1.3),
                  (["rules", 0, "f"], float("nan")), (["drivers", 1, "slabs", 0, "mult"], 0)):
    m = copy.deepcopy(good)
    tgt = m
    for k in path[:-1]:
        tgt = tgt[k]
    tgt[path[-1]] = val
    assert ss._model_error(m), (path, val)
pm = copy.deepcopy(good)                       # percentile slabs: rising 1-99 accepted, 100 refused
pm["drivers"][0].update(by="pct")
for j, sl in enumerate(pm["drivers"][0]["slabs"][1:], 1):
    sl["pct"] = 25 * j
assert ss._model_error(pm) is None, ss._model_error(pm)
pm["drivers"][0]["slabs"][-1]["pct"] = 100
assert ss._model_error(pm)
# continuous strengths (2026-10-07): the page's default passes; missing key, NaN or out of range refused
cd = json.loads(re.sub(r"(\w+):", r'"\1":', re.search(r"const FM_CONT_DEFAULT=(\{.*?\});", html).group(1)))
assert ss._cont_error(cd) is None, ss._cont_error(cd)
for bad in ({"st": 0.25, "growth": 0.2}, {**cd, "st": float("nan")}, {**cd, "growth": 4}, None):
    assert ss._cont_error(bad), bad
print(f"test_sync_server_ly: OK (plan {plan[0]}-{plan[-1]}, LY {ly[0]}-{ly[-1]})")
