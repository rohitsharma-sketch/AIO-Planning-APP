"""No-DB check: the BIS growth push replaces the whole lever and stamps the AOP publish.
Run: python db/test_buyer_department_growth.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from db.buyer_department_growth import upsert_buyer_growth  # noqa: E402


class _Session:
    def __init__(self):
        self.sql, self.commits = [], 0

    def execute(self, stmt, params=None):
        self.sql.append((str(stmt), params or {}))

    def commit(self):
        self.commits += 1


s = _Session()
n = upsert_buyer_growth(s, [{"division": "mens", "department": "m_jeans", "mi": 11, "growth_pct": 12.3456789},
                            {"division": "MENS", "department": "X", "mi": 99, "growth_pct": 1}], aop_publish_id=112)
body = [q for q, _ in s.sql]
assert n == 1, n
assert any(q.strip().startswith("DELETE") for q in body), "a push must replace the lever"
ins = [p for q, p in s.sql if "INSERT INTO planning_inputs.input_values" in q]
assert ins == [{"lk": "buyer_department_growth", "pid": 202703, "rk": "MENS|M_JEANS", "val": 12.3456789,
                "src": "buyer_input|aop:112"}], ins
assert s.commits == 1

# Nothing valid -> nothing deleted (a bad push must never wipe the buyer's growth).
s = _Session()
assert upsert_buyer_growth(s, [{"division": "MENS", "department": "X", "mi": 99, "growth_pct": 1}]) == 0
assert not any("DELETE" in q for q, _ in s.sql)
print("buyer growth push checks passed")
