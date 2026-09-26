"""Every suite theme must define every colour role (a missing role would fall
back to the Sage hex and leave that part of an app half-themed)."""
import json
import os
import re

THEMES = os.path.join(os.path.dirname(__file__), "..", "static", "suite-themes.json")


def test_every_theme_defines_every_role():
    cfg = json.load(open(THEMES, encoding="utf-8"))
    themes = cfg["themes"]
    assert cfg["default"] in themes
    roles = set(themes["sage"])
    for tid, t in themes.items():
        assert set(t) == roles, (tid, roles ^ set(t))
        for k, v in t.items():
            if k.endswith("_rgb"):
                assert re.fullmatch(r"\d{1,3},\d{1,3},\d{1,3}", v), (tid, k, v)
            elif k not in ("name", "desc"):
                assert re.fullmatch(r"#[0-9A-F]{6}", v), (tid, k, v)


if __name__ == "__main__":
    test_every_theme_defines_every_role()
    print("ok")
