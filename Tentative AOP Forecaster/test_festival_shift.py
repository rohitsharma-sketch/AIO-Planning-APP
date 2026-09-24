"""No-DB check for the festival-shifted base (engine_v3.apply_festival_shift +
db/calendar_shift.py). Run: python test_festival_shift.py"""
import datetime as dt

from db.calendar_shift import month_shares, shift_month_totals
import engine_v3 as e

# Nov'27 days 1-9 fed by Oct'26 days 23-31 (a Diwali tail moving into Nov).
# Oct'26 then feeds 40 future days (31 in Oct'27 + 9 in Nov'27); Nov'26 days
# 1-9 are displaced, so Nov'26 feeds only Nov'27 days 10-30.
MOVES = [(dt.date(2027, 11, i), dt.date(2026, 10, 22 + i)) for i in range(1, 10)]


def year_map(ry, fy, moves=()):
    """Identity day map ref (ry, m, d) -> fut (fy, m, d), with `moves` =
    [(fut_date, ref_date)] overriding specific future days."""
    pairs = {}
    d = dt.date(fy, 1, 1)
    while d.year == fy:
        pairs[d] = d.replace(year=ry) if not (d.month == 2 and d.day == 29) else dt.date(ry, 2, 28)
        d += dt.timedelta(days=1)
    for fut, ref in moves:
        pairs[fut] = ref
    return [(r, f) for f, r in pairs.items()]


def test_shift_conserves_and_moves():
    sh = month_shares(year_map(2026, 2027, MOVES))
    assert abs(sum(sh["2026-10"].values()) - 1) < 1e-12
    out = shift_month_totals({"2026-10": 400.0, "2026-11": 300.0}, sh)
    assert abs(out["2027-10"] - 400 * 31 / 40) < 1e-9, out
    assert abs(out["2027-11"] - (400 * 9 / 40 + 300)) < 1e-9, out
    assert abs(sum(out.values()) - 700) < 1e-9, "totals must be conserved"


def test_apply_festival_shift():
    maps = {"store_cluster": {"LFL1": "X", "RAMP1": "X"},
            "shares": {(2025, 2026): {"X": month_shares(year_map(2025, 2026))},
                       (2026, 2027): {"X": month_shares(year_map(2026, 2027, MOVES))}},
            "calendars": {(2026, 2027): "2026 -> 2027 Calendar - All"}}
    lfl_tag = next(iter(e.LFL_TAGS))
    store_info = {"LFL1": {"tag": lfl_tag}, "LFL2": {"tag": lfl_tag}, "RAMP1": {"tag": next(iter(e.RAMP_TAGS))}}
    open_months = {m for m in e.FY27_M if e._lbl_ym(m) > "2026-08"}          # closed through Aug'26
    real = {m: (100.0 if m not in open_months else 0.0) for m in e.FY27_M}
    actuals = {s: {"MENS": dict(real)} for s in store_info}
    proxy = {s: {"MENS": {m: 50.0 for m in e.FY27_M[:-1]}} for s in store_info}  # FY26 = 50/month
    base, cells = e.apply_proxy_base(actuals, proxy, store_info, open_months)
    base2, cells2, shifted = e.apply_festival_shift(actuals, proxy, store_info, open_months, base, cells, maps)

    b = base2["LFL1"]["MENS"]
    assert abs(b["Jun'26"] - 100) < 1e-9                        # real closed month, identity map
    # Oct'26/Nov'26 are open -> FY26 placeholder 50 (identity 2025->2026), then
    # 9/40 of Oct'26 moves into Nov'27.
    assert abs(b["Oct'26"] - 50 * 31 / 40) < 1e-9, b["Oct'26"]  # = FY28 Oct'27 base
    assert abs(b["Nov'26"] - (50 * 9 / 40 + 50)) < 1e-9, b["Nov'26"]  # = FY28 Nov'27 base
    assert ("LFL1", "MENS", "Nov'27") in cells2 and ("LFL1", "MENS", "Jun'27") not in cells2
    assert shifted == {"LFL1": "2026 -> 2027 Calendar - All"}
    # Unmapped LfL store and the Ramp store keep the unshifted (proxy) base.
    assert base2["LFL2"]["MENS"] == base["LFL2"]["MENS"]
    assert base2["RAMP1"]["MENS"] == base["RAMP1"]["MENS"]
    # Jan'28..Mar'28 bases untouched (no 2027->2028 calendar).
    assert b["Jan'27"] == base["LFL1"]["MENS"]["Jan'27"] and b["Mar'27"] == base["LFL1"]["MENS"]["Mar'27"]
    # No 2026->2027 calendar (e.g. no DB) -> no-op.
    assert e.apply_festival_shift(actuals, proxy, store_info, open_months, base, cells,
                                  {"store_cluster": {}, "shares": {}, "calendars": {}})[0] is base


def test_missing_source_month_keeps_unshifted_base():
    """Regression (2026-09-24): FY26 actuals not synced yet, and the 2026->2027
    map feeds Mar'27 days 1-5 from Feb'26. Shifting counted Feb'26 as 0 and cut
    the Mar'27 LfL KLM base 114.4 -> 99.8 Cr; it must stay unshifted instead."""
    moves = [(dt.date(2027, 3, i), dt.date(2026, 2, 20 + i)) for i in range(1, 6)]
    maps = {"store_cluster": {"LFL1": "X"},
            "shares": {(2025, 2026): {"X": month_shares(year_map(2025, 2026))},
                       (2026, 2027): {"X": month_shares(year_map(2026, 2027, moves))}},
            "calendars": {(2026, 2027): "2026 -> 2027 Calendar - All"}}
    store_info = {"LFL1": {"tag": next(iter(e.LFL_TAGS))}}
    open_months = {m for m in e.FY27_M if e._lbl_ym(m) > "2026-08"}
    actuals = {"LFL1": {"MENS": {m: (100.0 if m not in open_months else 0.0) for m in e.FY27_M}}}
    base, cells = e.apply_proxy_base(actuals, {}, store_info, open_months)   # no FY26 data at all
    base2, _, _ = e.apply_festival_shift(actuals, {}, store_info, open_months, base, cells, maps)
    assert base2["LFL1"]["MENS"]["Mar'26"] == 100.0, base2["LFL1"]["MENS"]["Mar'26"]  # FY28 Mar'27 base untouched
    assert abs(base2["LFL1"]["MENS"]["Jun'26"] - 100.0) < 1e-9                       # complete months still shift


if __name__ == "__main__":
    test_shift_conserves_and_moves()
    test_apply_festival_shift()
    test_missing_source_month_keeps_unshifted_base()
    print("test_festival_shift: all passed")
