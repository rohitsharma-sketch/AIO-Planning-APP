"""On/off switch per optional engine (user, 2026-10-14: "for optional engines give a toggle for the user so the user
can activate and deactive the engine if it is to be used"). Off = the step is hidden from the flow and its output is
ignored - the corrected plan file is kept on disk, so switching back on brings it back as it was. Default: all off
(user: "opted out is their default"). Stored in backend/engine_switches.json (git-ignored, like the other backend/*.json)."""
import json
import os

ENGINES = {
    "attr_correction": "Attr Correction",
    "base_correction": "Base Correction",
    "pww": "PW/W Deviation",
    "sor": "SOR Deviation",
}
PATH = os.path.join(os.path.dirname(__file__), "..", "engine_switches.json")
_PLAN_FILE = {"base_correction": "base_corrected_plan.json", "attr_correction": "attr_corrected_plan.json"}


def switches() -> dict:
    try:
        with open(PATH, encoding="utf-8") as fh:
            saved = json.load(fh)
    except (OSError, ValueError):
        saved = {}
    return {k: bool(saved.get(k, False)) for k in ENGINES}


def set_switch(key: str, on: bool) -> dict:
    if key not in ENGINES:
        raise KeyError(key)
    s = switches()
    s[key] = bool(on)
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=2)
    return s


def plan_files() -> list:
    """The department plan files in the order every engine reads them (most-corrected first), without the output of a
    correction engine that is switched off."""
    s = switches()
    return [f for k, f in _PLAN_FILE.items() if s[k]] + ["final_dept_plan.json"]


if __name__ == "__main__":   # self-check on a scratch file
    import tempfile
    PATH = os.path.join(tempfile.mkdtemp(), "s.json")
    assert plan_files() == ["final_dept_plan.json"] and switches()["pww"] is False   # opted out by default
    set_switch("base_correction", True)
    set_switch("attr_correction", True)
    assert plan_files() == ["base_corrected_plan.json", "attr_corrected_plan.json", "final_dept_plan.json"]
    set_switch("base_correction", False)
    assert plan_files() == ["attr_corrected_plan.json", "final_dept_plan.json"]
    print("ok")
