"""save_json under concurrent writers (2026-10-15: the server and a script saving the plan at once left invalid JSON)."""
import json
import os
import tempfile
import threading

from plan_cache import save_json


def test_concurrent_writers_leave_valid_json():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.json")
    errs = []

    def w(i):
        try:
            save_json(p, {"k": list(range(100000)), "w": i})
        except Exception as e:   # noqa: BLE001
            errs.append(e)

    ts = [threading.Thread(target=w, args=(i,)) for i in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs
    assert json.load(open(p))["w"] in range(6)
    assert not [f for f in os.listdir(d) if f.endswith(".tmp")]


if __name__ == "__main__":
    test_concurrent_writers_leave_valid_json()
    print("ok")
