"""python test_workspaces.py - each user's Re-Aligner is their own (2026-09-30). Temp folders only, no network."""
import os
import tempfile
import threading

import engine
import server

tmp = tempfile.mkdtemp()
server.USERS_DIR = os.path.join(tmp, "users")
server.ORIG_PKL, server.LOCKS_JSON, server.REPHASE_OV_JSON = (os.path.join(tmp, f) for f in ("o.pkl", "l.json", "r.json"))
server._save_json(server.LOCKS_JSON, {"months": ["Sep'26", "Oct'26"], "chosen": {"Oct'26": True}})   # the setup to copy

a, b = server.workspace("alice"), server.workspace("bob")
assert a is not b and a.dir != b.dir and a is server.workspace("alice")
assert a.state["locks"] == b.state["locks"] == []          # no plan loaded yet -> no months, no locks
assert os.path.exists(a.path("locks.json"))                 # started from a copy of the setup at the time

M = ["Sep'26", "Oct'26", "Nov'26"]
server._tl.ws = a
server._set_locks(M, {"Sep'26": True})
server.state["method"] = "growth"
server._tl.ws = b
server._set_locks(M, {"Nov'26": True})
assert server.state["method"] == "dept"                     # alice's change isn't bob's
assert a.locks == {"Sep'26"} and b.locks == {"Nov'26"}
assert server._load_json(a.path("locks.json"), {})["chosen"]["Sep'26"] and not server._load_json(b.path("locks.json"), {})["chosen"]["Sep'26"]


def locks_in_thread(w):  # a job thread sees its own user's locks
    engine._TL.locks = w.locks
    return [m for m in M if engine.locked(m)]


seen = {}
ts = [threading.Thread(target=lambda: seen.update(a=locks_in_thread(a))),
      threading.Thread(target=lambda: seen.update(b=locks_in_thread(b)))]
for t in ts:
    t.start()
for t in ts:
    t.join()
assert seen == {"a": ["Sep'26"], "b": ["Nov'26"]}, seen
assert server.who(None) == "local" and server.who("") == "local"
assert server._safe("../../x") == ".._.._x" and server._safe("rohit.sharma@citykart.org") == "rohit.sharma@citykart.org"
a.touched -= server.IDLE_UNLOAD + 1
a.state["method"] = "shift"
server.workspace("bob")                                     # another user's visit frees an idle workspace
assert not a.loaded and a.state["method"] == "dept"
server.workspace("alice")                                   # ... and it reloads on its next visit
assert a.loaded
print("all workspace checks passed")
