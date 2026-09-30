"""Rights an admin can switch off (auth.rights) - pure, temp file, no database."""
import os
import tempfile

import pytest

from auth.rights import RIGHTS, effective, load_revoked, save_revoked


def test_effective_rights():
    assert effective(False, True, []) == list(RIGHTS)
    assert "servers" not in effective(False, True, ["servers"]) and "data_sync" in effective(False, True, ["servers"])
    assert effective(True, True, ["servers"]) == list(RIGHTS)          # admins always keep everything
    assert effective(False, False, []) == [] and effective(True, False, []) == []   # switched off: nothing


def test_save_and_restore():
    p = os.path.join(tempfile.mkdtemp(), "data", "r.json")
    assert save_revoked("u1", ["servers", "servers", "data_sync"], p) == ["data_sync", "servers"]
    assert load_revoked(p) == {"u1": ["data_sync", "servers"]}
    assert save_revoked("u1", [], p) == [] and load_revoked(p) == {}   # all given back -> entry gone
    with pytest.raises(ValueError):
        save_revoked("u1", ["delete_everything"], p)
