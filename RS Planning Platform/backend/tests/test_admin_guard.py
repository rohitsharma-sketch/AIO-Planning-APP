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


def test_rename_checks():
    from auth.routes import username_refusal
    assert username_refusal("", ["admin"]) and username_refusal("x" * 65, [])
    assert "already" in username_refusal("Admin", ["admin", "planning01"])     # case doesn't make it different
    assert username_refusal("Suraj Kumar", ["admin"]) is None


def test_sign_in_as_checks():
    from auth.routes import sign_in_as_refusal
    assert sign_in_as_refusal("a", "a", True, True)                     # yourself
    assert "another admin" in sign_in_as_refusal("a", "b", True, True)   # no admin-to-admin hops
    assert "switched off" in sign_in_as_refusal("a", "b", False, False)
    assert sign_in_as_refusal("a", "b", False, True) is None


def test_password_ok_ignores_spaces_at_the_ends():
    from auth.routes import password_ok
    from auth.security import hash_password
    h = hash_password("Temp-Pass-123")
    assert password_ok("Temp-Pass-123", h) and password_ok("Temp-Pass-123 ", h) and password_ok(" Temp-Pass-123\n", h)
    assert not password_ok("temp-pass-123", h) and not password_ok("Temp-Pass-12", h) and not password_ok("", h)
