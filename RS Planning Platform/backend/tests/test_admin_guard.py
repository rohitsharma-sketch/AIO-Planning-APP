"""Lock-out guards for the Users & access page (auth.routes.admin_change_refusal) - pure, no database."""
from auth.routes import admin_change_refusal


def test_cannot_remove_own_admin_or_switch_self_off():
    assert admin_change_refusal("a", "a", True, True, {"is_admin": False}, 3)
    assert admin_change_refusal("a", "a", True, True, {"is_active": False}, 3)
    assert admin_change_refusal("a", "a", True, True, {"email": "x@y.z", "role": "buyer"}, 1) is None


def test_last_active_admin_is_kept():
    assert "last active admin" in admin_change_refusal("a", "b", True, True, {"is_admin": False}, 1)
    assert "last active admin" in admin_change_refusal("a", "b", True, True, {"is_active": False}, 1)
    assert admin_change_refusal("a", "b", True, True, {"is_admin": False}, 2) is None     # another admin remains
    assert admin_change_refusal("a", "b", False, True, {"is_active": False}, 1) is None   # not an admin
    assert admin_change_refusal("a", "b", True, False, {"is_admin": False}, 1) is None    # already switched off
