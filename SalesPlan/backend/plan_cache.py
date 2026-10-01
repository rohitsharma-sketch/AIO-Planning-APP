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
