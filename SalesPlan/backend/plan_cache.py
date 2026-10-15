"""The department plan files (final / attribute-corrected / base-corrected, ~350 MB of JSON, ~3.5 s to read) kept in
memory between page loads and re-read only when the file changes (user, 2026-10-01: "the population time to load the
data should be shortened up"). Readers must not change what they get back - copy first (the correction engines do).

ponytail: one slot - the plan is ~1.5 GB once loaded, so only the file read last is kept; give it more slots if the
server has the memory and pages flip between plan versions."""
import json
import os

_slot = {}


def load_json(path):
    """The parsed file, or None if it doesn't exist."""
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    if _slot.get("key") == (path, mt):
        return _slot["data"]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _slot.clear()
    _slot.update(key=(path, mt), data=data)
    return data


def save_json(path, obj, **kw):
    """Write JSON atomically: a .tmp file, then os.replace (audit 2026-10-06). The ~350 MB plan and the small state files
    were written in place, so a reader mid-write got a truncated file (500) and a crash mid-write left a corrupt plan."""
    # one .tmp per writer (2026-10-15: the server and a script regenerating at the same moment both wrote "<path>.tmp"
    # and the interleaved file became the saved plan - invalid JSON); the last os.replace still wins, but whole
    import threading
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, **kw)
    import time
    for i in range(40):   # Windows refuses the swap while another writer swaps or a reader holds the file (WinError 5 / 32)
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 39:
                os.remove(tmp)
                raise
            time.sleep(0.25)
