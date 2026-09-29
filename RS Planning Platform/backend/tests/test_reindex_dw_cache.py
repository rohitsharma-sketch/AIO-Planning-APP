"""Day-wise month cache: a closed month is cached / reused only when its day-wise data reaches the month's last day
(2026-09-30: Aug was cached from an export that stopped at 27 Aug and kept being served)."""
from calendar_engine import scans


def _month(ym, last_day):
    cols = [f"{ym}-{d:02d}" for d in range(1, last_day + 1)]
    return {"ok": True, "source": "dw", "rows": [], "actualRows": [], "columns": [], "actualColumns": cols,
            "rowsRead": 10, "rowsMapped": 10, "keyFields": ["store"], "actualKeyFields": ["store"], "grain": "store",
            "metric": "SL_V"}


def test_covers_month_end():
    assert scans._covers_month_end(_month("2026-08", 31), "2026-08")
    assert not scans._covers_month_end(_month("2026-08", 27), "2026-08")
    assert scans._covers_month_end(_month("2026-02", 28), "2026-02")
    assert not scans._covers_month_end(None, "2026-08")


def test_partial_cached_dw_month_is_recomputed_and_not_recached(monkeypatch):
    saved, computed = [], []
    monkeypatch.setattr(scans, "_is_month_closed", lambda m, today=None: True)
    monkeypatch.setattr(scans, "_cached_months_status", lambda src, months, fp, fk: {m: "x" for m in months})
    monkeypatch.setattr(scans, "_load_month_cache", lambda src, m, fp, fk: _month(m, 27 if m == "2026-08" else 31))
    monkeypatch.setattr(scans, "_save_month_cache", lambda src, m, fp, fk, r: saved.append(m))
    monkeypatch.setattr(scans, "_get_raw", lambda *a, **k: None)
    monkeypatch.setattr(scans, "_save_calendarised_sales_snapshot", lambda result, suffix="": None)

    def fresh(months, **k):
        computed.extend(months)
        return _month(months[0], 29)          # the export still stops before 31 Aug
    monkeypatch.setattr(scans, "reindex_daywise", fresh)

    r = scans.run_reindex({"source": "dw", "months": ["2026-07", "2026-08"], "dayMap": {"C": [["2026-01-01", "2027-01-01"]]}})
    assert r["ok"], r
    assert computed == ["2026-08"]            # July's full cache is reused, August's 27-day cache is not
    assert saved == []                        # a still-partial August isn't cached either
    monkeypatch.setattr(scans, "reindex_daywise", lambda months, **k: (computed.append(months[0]), _month(months[0], 31))[1])
    scans.run_reindex({"source": "dw", "months": ["2026-08"], "dayMap": {"C": [["2026-01-01", "2027-01-01"]]}})
    assert saved == ["2026-08"]               # once it reaches 31 Aug it is cached


def test_monthwise_cache_rule_unchanged(monkeypatch):
    got = []
    monkeypatch.setattr(scans, "_is_month_closed", lambda m, today=None: True)
    monkeypatch.setattr(scans, "_cached_months_status", lambda src, months, fp, fk: {m: "x" for m in months})
    monkeypatch.setattr(scans, "_load_month_cache", lambda src, m, fp, fk: dict(_month(m, 1), source="mw", actualColumns=[m]))
    monkeypatch.setattr(scans, "reindex_monthwise", lambda months, **k: got.append(months) or {"ok": False})
    monkeypatch.setattr(scans, "_save_calendarised_sales_snapshot", lambda result, suffix="": None)
    r = scans.run_reindex({"source": "mw", "months": ["2026-08"], "dayMap": {"C": [["2026-01-01", "2027-01-01"]]}})
    assert r["ok"] and got == []              # month-wise keeps serving its cache as before
