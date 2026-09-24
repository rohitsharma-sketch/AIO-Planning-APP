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


def test_versions_sharing_one_session_each_get_their_own_publish():
    """Real case 2026-09-24: Version 2 and Version 3 share AOP session S; the
    old one-per-session list showed only one of them. Timestamps are the real
    ones (IST): V2 saved 12 s AFTER its first publish, V3 17 s BEFORE its."""
    import datetime as dt
    from publish_aop_targets import pick_version_publishes
    IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
    t = lambda *a: dt.datetime(2026, 9, *a, tzinfo=IST)
    versions = [("Version 1", "A", "2026-09-11T11:22:05Z", None),
                ("Version 2", "S", "2026-09-15T05:49:38Z", None),   # 11:19:38 IST
                ("Version 3", "S", "2026-09-24T11:58:42Z", None)]   # 17:28:42 IST
    pubs = [(32, "A", t(15, 10, 20)), (40, "S", t(15, 11, 19, 26)), (90, "S", t(23, 17, 30)),
            (111, "S", t(24, 17, 28, 59))]
    got = {label: p[0] for label, _sid, p in pick_version_publishes(versions, pubs)}
    assert got == {"Version 3": 111, "Version 2": 90, "Version 1": 32}, got


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
