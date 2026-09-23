"""Regression check for the 2026-09-23 Engine-Forecast-vs-Forecast growth% fix.
Run directly: python test_publish_aop_targets.py
No DB/network needed - _aggregate_lfl_totals() is pure.
"""
from publish_aop_targets import _aggregate_lfl_totals, LFL_TAGS, PUBLISH_DIVS

MONTH = "Mar'27"
PERIOD = 202703


def _rec(tag, div, base, forecast, engine=None):
    r = {"Tag": tag, "Division": div, f"{MONTH} | Base": base, f"{MONTH} | Forecast": forecast}
    if engine is not None:
        r[f"{MONTH} | Engine Forecast"] = engine
    return r


def test_lfl_tag_filter_excludes_ramp_and_nso():
    records = [
        _rec("080 - Stores", "MENS", 100.0, 110.0, 110.0),  # LFL - counted
        _rec("Ramp", "MENS", 999.0, 999.0, 999.0),          # excluded
        _rec("NSO", "MENS", 999.0, 999.0, 999.0),           # excluded
    ]
    totals, base_totals, engine_totals = _aggregate_lfl_totals(records)
    key = ("MENS", PERIOD)
    assert totals[key] == 110.0
    assert base_totals[key] == 100.0
    assert engine_totals[key] == 110.0


def test_engine_forecast_differs_from_deviation_inclusive_forecast():
    """The whole point of the fix: when a ref-store-mix deviation exists,
    engine_totals must track "Engine Forecast", NOT the inflated "Forecast"."""
    records = [_rec("080 - Stores", "MENS", base=100.0, forecast=118.4, engine=110.0)]
    totals, base_totals, engine_totals = _aggregate_lfl_totals(records)
    key = ("MENS", PERIOD)
    assert totals[key] == 118.4          # deviation-inclusive target, unchanged behaviour
    assert engine_totals[key] == 110.0    # pure engine figure - what BIS's growth% must use
    growth_from_forecast = (totals[key] / base_totals[key] - 1) * 100
    growth_from_engine = (engine_totals[key] / base_totals[key] - 1) * 100
    assert round(growth_from_forecast, 1) == 18.4   # the WRONG number BIS used to show
    assert round(growth_from_engine, 1) == 10.0      # the CORRECT number, matches AOP's own display


def test_engine_forecast_falls_back_to_forecast_when_column_absent():
    """Older sessions run before 'Engine Forecast' existed as its own column
    have no deviation layer anyway - Forecast IS the engine figure then."""
    records = [_rec("080 - Stores", "MENS", base=100.0, forecast=110.0)]  # no engine kwarg
    _, _, engine_totals = _aggregate_lfl_totals(records)
    assert engine_totals[("MENS", PERIOD)] == 110.0


def test_non_publish_division_excluded():
    records = [_rec("080 - Stores", "RETAIL", 50.0, 55.0, 55.0)]
    totals, _, _ = _aggregate_lfl_totals(records)
    assert ("RETAIL", PERIOD) not in totals
    assert "RETAIL" not in PUBLISH_DIVS


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
