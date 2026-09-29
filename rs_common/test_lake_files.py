"""No-network check of the shared latest-file rule: newest wins; a truncated / column-short / unreadable newest file
is skipped for the last good export. Run: python rs_common/test_lake_files.py"""
import os
import sys
import tempfile
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lake_files import latest_path, pick_latest  # noqa: E402

d = tempfile.mkdtemp()


def put(name, rows, cols=("A", "B"), age=0):
    p = os.path.join(d, name)
    pd.DataFrame({c: range(rows) for c in cols}).to_parquet(p)
    t = time.time() - age
    os.utime(p, (t, t))
    return p


old = put("old.parquet", 1000, age=300)
full = put("full.parquet", 1010, age=200)
assert latest_path(d) == full                                 # newest complete export wins

cut = put("cut.parquet", 50, age=100)                          # the 50,000-row case, scaled down
p, notes = pick_latest(d)
assert p == full and "only 50 rows" in notes[0], notes

put("narrow.parquet", 1010, cols=("A",), age=50)               # a column went missing
p, notes = pick_latest(d)
assert p == full and any("missing columns ['B']" in n for n in notes), notes

with open(os.path.join(d, "writing.parquet"), "wb") as fh:     # half-copied file
    fh.write(b"PAR1 not finished")
p, notes = pick_latest(d)
assert p == full and any("unreadable" in n for n in notes), notes

for f in os.listdir(d):
    os.remove(os.path.join(d, f))
only = put("only.parquet", 5)
assert latest_path(d) == only                                  # a single file is simply used
print("lake file checks passed")
