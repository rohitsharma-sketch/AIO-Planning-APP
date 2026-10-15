"""The emailed 6-digit reset code (2026-10-15) - no database."""
from auth.security import CODE_WINDOW, check_reset_code, make_reset_code


def test_reset_code_window_and_single_use():
    t = 1_800_000_000.0
    c = make_reset_code("u1", "hashA", t)
    assert len(c) == 6 and c.isdigit()
    assert check_reset_code("u1", "hashA", c, t)
    assert check_reset_code("u1", "hashA", c[:3] + " " + c[3:], t)              # a space typed in the middle
    assert check_reset_code("u1", "hashA", c, t + CODE_WINDOW)                   # still good in the next window
    assert not check_reset_code("u1", "hashA", c, t + 2 * CODE_WINDOW + 1)       # expired
    assert not check_reset_code("u1", "hashB", c, t)                             # used: the password hash changed
    assert not check_reset_code("u2", "hashA", c, t)                             # another user
