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
    # (label, session, createdAt, savedAt) - V2 last saved 15 Sep 11:37 IST at 10% flat
    versions = [("Version 1", "A", "2026-09-11T11:22:05Z", "2026-09-15T04:50:00Z"),
                ("Version 2", "S", "2026-09-15T05:49:38Z", "2026-09-15T06:07:00Z"),
                ("Version 3", "S", "2026-09-24T11:58:42Z", "2026-09-24T11:58:42Z")]
    pubs = [(32, "A", t(15, 10, 20)), (40, "S", t(15, 11, 19, 26)), (41, "S", t(15, 11, 37, 30)),
            (90, "S", t(23, 17, 30)),       # unsaved what-if run (MENS 15 / LADIES 12 / KIDS 9)
            (111, "S", t(24, 17, 28, 59))]  # published 17 s AFTER V3 was saved
    got = {label: p[0] for label, _sid, p in pick_version_publishes(versions, pubs)}
    assert got == {"Version 3": 111, "Version 2": 41, "Version 1": 32}, got
    # Deleting V3 must not hand its run (or the unsaved 23 Sep run) to V2.
    got = {label: p[0] for label, _sid, p in pick_version_publishes(versions[:2], pubs)}
    assert got == {"Version 2": 41, "Version 1": 32}, got


def test_lfl_growth_matches_bis_growth_vs_ly():
    """25 Sep publish, MAMJ LfL KLM: base 388.82 -> target 431.85 = +11.1%, AOP
    Summary's Overall Growth and BIS's Growth vs LY. The engine totals (423.14,
    +8.8%) must NOT be the numerator. RETAIL/GM never count; no base -> None."""
    from publish_aop_targets import lfl_growth_pct
    base = {"MENS": {"m": 15310.31}, "LADIES": {"m": 11484.96}, "KIDS": {"m": 12087.27}, "RETAIL": {"m": 999.0}}
    target = {"MENS": {"m": 16730.08}, "LADIES": {"m": 12815.76}, "KIDS": {"m": 13642.03}, "RETAIL": {"m": 5.0}}
    assert lfl_growth_pct(base, target) == 11.1, lfl_growth_pct(base, target)
    assert lfl_growth_pct(None, target) is None


def test_live_version_is_a_saved_version():
    """One live AOP (2026-09-25): the latest SAVED version's publish, or the
    version of the session on screen - never an unsaved/deleted-version run
    (list_aop_history already only returns saved versions' publishes)."""
    import publish_aop_targets as m
    orig = m.list_aop_history
    try:
        m.list_aop_history = lambda s, limit=50: [{"id": 112, "session_id": "v2"}, {"id": 32, "session_id": "v1"}]
        assert m.live_version(None)["id"] == 112
        assert m.live_version(None, "v1")["id"] == 32          # lock the version on screen
        assert m.live_version(None, "deleted-v3") is None       # unsaved/deleted session -> nothing to lock
        m.list_aop_history = lambda s, limit=50: []
        assert m.live_version(None) is None
    finally:
        m.list_aop_history = orig


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)} passed")
