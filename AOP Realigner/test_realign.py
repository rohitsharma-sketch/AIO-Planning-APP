"""python test_realign.py — no deps, no network."""
from server import run

AOP = [  # wide format, department-level AOP. MENS Mar total = 100
    {"Division": "MENS", "Department": "SHIRT", "Mar'27": 50, "Apr'27": 40},
    {"Division": "MENS", "Department": "JEANS", "Mar'27": 30, "Apr'27": 40},
    {"Division": "MENS", "Department": "TEE", "Mar'27": 20, "Apr'27": 20},
]
by = lambda res: {(r["department"], r["month"]): r for r in res["rows"]}

# 1. Buyer bumps SHIRT Mar 50->60: SHIRT kept, JEANS/TEE absorb -10 pro-rata (30:20)
plan = [dict(r) for r in AOP]
plan[0]["Mar'27"] = 60
res = run({"aop": AOP, "plan": plan})
r = by(res)
assert r[("SHIRT", "Mar'27")]["final"] == 60 and r[("SHIRT", "Mar'27")]["status"] == "kept"
assert abs(r[("JEANS", "Mar'27")]["final"] - 24) < 1e-9 and abs(r[("TEE", "Mar'27")]["final"] - 16) < 1e-9
assert all(abs(s["gap"]) < 1e-9 for s in res["summary"])
assert r[("SHIRT", "Apr'27")]["status"] == "absorbed" and r[("SHIRT", "Apr'27")]["final"] == 40  # untouched month

# 2. Long format + new dept not in AOP (locked as a change) + dropped dept (locked at 0)
plan = [{"Division": "mens", "Department": "shirt", "Month": "Mar'27", "Value": 50},
        {"Division": "MENS", "Department": "TEE", "Month": "Mar'27", "Value": 20},
        {"Division": "MENS", "Department": "POLO", "Month": "Mar'27", "Value": 10}]
r = by(run({"aop": AOP, "plan": plan}))
assert r[("POLO", "Mar'27")]["final"] == 10 and r[("JEANS", "Mar'27")]["final"] == 0
assert abs(r[("SHIRT", "Mar'27")]["final"] + r[("TEE", "Mar'27")]["final"] - 90) < 1e-9

# 3. Changes overshoot the AOP -> everything compressed proportionally, total still = AOP
plan = [{"Division": "MENS", "Department": d, "Mar'27": v} for d, v in (("SHIRT", 150), ("JEANS", 30), ("TEE", 20))]
res = run({"aop": AOP, "plan": plan})
assert {x["status"] for x in res["rows"] if x["month"] == "Mar'27"} == {"compressed"}
assert abs(res["summary"][0]["final"] - 100) < 1e-9

# 4. Manual override: unlock SHIRT's change -> whole plan scales to 100 by plan mix
plan = [dict(x) for x in AOP]; plan[0]["Mar'27"] = 60
r = by(run({"aop": AOP, "plan": plan, "overrides": {"MENS|SHIRT|Mar'27": False}}))
assert abs(r[("SHIRT", "Mar'27")]["final"] - 60 / 110 * 100) < 1e-9

# 5. Division-level AOP (no Department column): plan depts scale to the division total
res = run({"aop": [{"Division": "MENS", "Mar'27": 200}], "plan": plan})
assert abs(sum(x["final"] for x in res["rows"] if x["month"] == "Mar'27") - 200) < 1e-9
assert not res["aop_has_departments"]

print("all realign checks passed")
