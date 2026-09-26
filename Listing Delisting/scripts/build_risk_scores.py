"""
Builds app/risk.json: a delisting-risk score for every store x department combo that is
currently Listed ('Y' in the latest month that has any listing record).

Rule (see PRD_LOGIC.md for full writeup, including before/after examples) -- REWORK
2026-09-21, replaces the earlier continuous-seasonal-index method entirely:
  - Only score combos whose latest recorded month is 'Y' (currently Listed).
  - The KB's last month (e.g. "Sep'26(Till Date)") is a partial, in-progress month -- its sales
    are only a few days' worth, not comparable to a full month. It still counts for the
    "currently Listed?" check, but the trend window is anchored to the last *complete* month
    instead, so a partial month never fakes a decline.
  - FIXED CALENDAR-MONTH SEASONAL WINDOWS (business rule, not derived): each department's
    season_category (from app/seasonality.json, itself from build_season_category.py) maps to a
    fixed set of in-season calendar months -- see IN_SEASON_WINDOWS below. regular/occasional/
    missing category = always in-season (no restriction).
  - recent_idxs = the 3 complete months ending at the anchor. Only the ones whose calendar
    month falls in the department's in-season window count as recent_in_season_idxs. If NONE
    of the 3 recent months are in-season for this department, skip -- not flagged. This is the
    core fix: an off-season dip for a seasonal department produces no signal at all, by
    construction (no more "expected" math trying to compensate for it).
  - history_in_season_idxs = every month before the recent window whose calendar month is
    in-season, most-recent-first, capped at 6. Need at least 3 such months, else skip as
    insufficient history (same "skip, don't assume low-risk" precedent as before).
  - baseline_avg = mean actual SL_V over history_in_season_idxs, floored at MIN_BASELINE (2000
    rupees) -- below that, skip as noise.
  - recent_avg = mean actual SL_V over recent_in_season_idxs only (1, 2, or 3 months).
  - shortfall = clamp((baseline_avg - recent_avg) / baseline_avg, 0, 1). Flagged if >= 0.5.

Usage: python build_risk_scores.py
"""
import json
import os
import re
import statistics

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RECENT_N = 3
BASELINE_CAP = 6       # cap on how many in-season history months feed the baseline
MIN_BASELINE_HISTORY = 3  # need at least this many in-season history months to proceed
MIN_BASELINE = 2000.0   # rupees; below this a % shortfall is noise, not signal
RISK_THRESHOLD = 0.5
PARTIAL_SUFFIX = '(Till Date)'  # in-progress month label suffix, see PRD_LOGIC.md
MONTH_RE = re.compile(r"^([A-Za-z]{3})'(\d{2})(\(Till Date\))?$")
MONTH_ORDER = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Fixed in-season calendar-month windows per season_category -- a business rule, not derived
# from data. A category NOT in this dict (regular, occasional, or a missing/null category) is
# always in-season -- no restriction (see PRD_LOGIC.md for why: occasional/regular have no
# natural calendar window, and null-category departments default to the same "always in-season"
# treatment as regular). October deliberately overlaps summer and both winter categories --
# confirmed intentional (a realistic shoulder month), not a bug.
IN_SEASON_WINDOWS = {
    'summer': {'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct'},
    'prewinter': {'Aug', 'Sep', 'Oct'},
    'lt_winter': {'Oct', 'Nov', 'Dec', 'Jan', 'Feb'},
    'hvy_winter': {'Oct', 'Nov', 'Dec', 'Jan', 'Feb'},  # same window as lt_winter, by design
}


def cal_month(label):
    m = MONTH_RE.match(label)
    if not m:
        raise ValueError(f"Unparseable month label: {label}")
    return m.group(1)


def in_season_window(season_category):
    """The fixed set of in-season calendar months for a category, or None meaning
    'always in-season' (regular, occasional, or a missing/null category)."""
    return IN_SEASON_WINDOWS.get(season_category)


def is_in_season(season_category, cal):
    window = in_season_window(season_category)
    return window is None or cal in window


def score_combo(history, months, sale_for_month, season_category):
    """Returns a dict (flagged combo) or None (not listed / no in-season signal / insufficient
    in-season history / below the noise floor / shortfall under threshold)."""
    last_idx = None
    for i in range(len(history) - 1, -1, -1):
        if history[i] != '.':
            last_idx = i
            break
    if last_idx is None or history[last_idx] != 'Y':
        return None  # no data at all, or not currently Listed

    # Anchor the trend window on the last *complete* month -- a partial "till date" month
    # would otherwise look like a fake sales collapse purely from having fewer days billed.
    anchor_idx = last_idx - 1 if PARTIAL_SUFFIX in months[last_idx] else last_idx
    if anchor_idx < RECENT_N - 1:
        return None  # not even 3 complete months of history to anchor a recent window on

    recent_idxs = list(range(anchor_idx - RECENT_N + 1, anchor_idx + 1))

    recent_in_season_idxs = [i for i in recent_idxs if is_in_season(season_category, cal_month(months[i]))]
    if not recent_in_season_idxs:
        return None  # THE CORE FIX: off-season dip for this department -- no signal, by construction

    # In-season history months before the recent window, most-recent-first, capped.
    history_in_season_idxs = [
        i for i in range(recent_idxs[0] - 1, -1, -1)
        if is_in_season(season_category, cal_month(months[i]))
    ][:BASELINE_CAP]
    if len(history_in_season_idxs) < MIN_BASELINE_HISTORY:
        return None  # insufficient in-season history -- skip, don't assume low-risk

    baseline_avg = sum(sale_for_month(months[i]) for i in history_in_season_idxs) / len(history_in_season_idxs)
    if baseline_avg < MIN_BASELINE:
        return None  # base too small for a % shortfall to be meaningful

    recent_avg = sum(sale_for_month(months[i]) for i in recent_in_season_idxs) / len(recent_in_season_idxs)

    shortfall = max(0.0, min(1.0, (baseline_avg - recent_avg) / baseline_avg))
    if shortfall < RISK_THRESHOLD:
        return None

    m_recent = len(recent_in_season_idxs)
    pct = round(shortfall * 100)
    reason = (
        "Zero sales in the in-season portion of the last 3 months despite still Listed"
        if recent_avg == 0 else
        f"Sales down {pct}% vs this department's own prior in-season average "
        f"({m_recent} of 3 recent months were in-season)"
    )

    return {
        'risk_score': round(shortfall, 3),
        'recent_avg': round(recent_avg, 2),
        'baseline_avg': round(baseline_avg, 2),  # prior in-season baseline average
        'last_month': months[last_idx],
        'trend_through_month': months[anchor_idx],
        'history_months_used': len(history_in_season_idxs),
        'recent_in_season_count': m_recent,
        'reason': reason,
    }


def tertile_cutoffs(scores):
    """(low_max, medium_max) tertile cutoffs of a score list, or (None, None) if too few to mean
    anything (fewer than 3 flagged combos)."""
    if len(scores) < 3:
        return None, None
    t1, t2 = statistics.quantiles(scores, n=3)
    return t1, t2


def assign_tier(score, t1, t2):
    if t1 is None:
        return 'High'  # degenerate case: too few flagged combos for tertiles, all notable
    if score <= t1:
        return 'Low'
    if score <= t2:
        return 'Medium'
    return 'High'


def build():
    with open(os.path.join(BASE, 'app', 'kb.json'), encoding='utf-8') as f:
        kb = json.load(f)
    with open(os.path.join(BASE, 'app', 'sales.json'), encoding='utf-8') as f:
        sales = json.load(f)
    with open(os.path.join(BASE, 'app', 'seasonality.json'), encoding='utf-8') as f:
        seasonality = json.load(f)
    months = kb['months']

    season_category_by_dept = {
        dept: entry.get('season_category') for dept, entry in seasonality['departments'].items()
    }

    flagged = []
    scored_count = 0
    for store, depts in kb['data'].items():
        store_sales = sales['data'].get(store, {})
        for dept, history in depts.items():
            dept_sales = store_sales.get(dept, {})
            if not any(ch != '.' for ch in history):
                continue
            scored_count += 1
            season_category = season_category_by_dept.get(dept)  # None = always in-season
            result = score_combo(
                history, months, lambda m, ds=dept_sales: ds.get(m, 0.0), season_category)
            if result:
                flagged.append({'store': store, 'dept': dept, **result})

    flagged.sort(key=lambda r: r['risk_score'], reverse=True)

    # Low/Medium/High severity badge: tertiles of the FLAGGED score distribution itself (not
    # the full 0-1 range), so the three tiers always split the actually-flagged combos into
    # roughly even thirds -- data-driven, not arbitrary round numbers like "50/75%".
    t1, t2 = tertile_cutoffs([r['risk_score'] for r in flagged])
    for r in flagged:
        r['risk_tier'] = assign_tier(r['risk_score'], t1, t2)

    out = {
        'generated_at': None,
        'params': {
            'recent_months': RECENT_N,
            'baseline_cap_months': BASELINE_CAP,
            'min_baseline_history_months': MIN_BASELINE_HISTORY,
            'min_baseline_sales': MIN_BASELINE,
            'risk_threshold': RISK_THRESHOLD,
            'method': 'fixed in-season calendar-month windows (see PRD_LOGIC.md)',
            'risk_tier_cutoffs': {'low_max': t1, 'medium_max': t2} if t1 is not None else None,
        },
        'scored_count': scored_count,
        'flagged_count': len(flagged),
        'flagged': flagged,
    }
    import datetime
    out['generated_at'] = datetime.date.today().isoformat()

    out_path = os.path.join(BASE, 'app', 'risk.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))

    print(f"OK: {scored_count} currently-Listed combos evaluated, {len(flagged)} flagged "
          f"(risk >= {RISK_THRESHOLD}) -> {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")


def demo():
    """Smallest runnable check: score_combo's fixed-window in-season math and its skip
    conditions. Adapted from the previous seasonal-index-based demo() -- same test shapes,
    now driven by season_category instead of a continuous index."""
    months = [f"{mon}'24" for mon in MONTH_ORDER] + ["Sep'25(Till Date)"]  # 13 labels, idx 0..12

    # --- Off-season dip that should NOT flag (mirrors the old KGW_JACKET-in-summer case) -----
    # hvy_winter combo, recent window = Jun/Jul/Aug (all off-season) with a real dip -- but since
    # none of the 3 recent months are in-season, there's nothing to compare, so no flag at all.
    history = 'Y' * 13
    # Recent window is idx 5,6,7 = Jun,Jul,Aug -- all off-season for hvy_winter.
    off_season_sales = {months[i]: 9000.0 for i in range(8)}
    off_season_sales.update({months[i]: 0.0 for i in range(5, 8)})  # Jun/Jul/Aug dip
    r = score_combo(history[:8], months[:8], lambda m: off_season_sales.get(m, 0.0), 'hvy_winter')
    assert r is None, f"expected no flag for an off-season dip, got {r}"

    # --- Genuine in-season decline that SHOULD still flag ------------------------------------
    # hvy_winter combo anchored so recent window = Dec'23/Jan'24/Feb'24 (in-season). 7 prior
    # in-season months (Oct'22-Feb'23, Oct'23-Nov'23, capped at 6) sold well; recent in-season
    # months collapsed to near-zero.
    winter_months = ["Oct'22", "Nov'22", "Dec'22", "Jan'23", "Feb'23", "Oct'23", "Nov'23",
                      "Dec'23", "Jan'24", "Feb'24"]
    winter_sales = {m: 9000.0 for m in winter_months[:7]}
    winter_sales.update({"Dec'23": 100.0, "Jan'24": 50.0, "Feb'24": 0.0})
    r2 = score_combo('Y' * 10, winter_months, lambda m: winter_sales.get(m, 0.0), 'hvy_winter')
    assert r2 is not None and r2['risk_score'] >= 0.5, f"expected genuine in-season decline to flag, got {r2}"
    assert r2['recent_in_season_count'] == 3  # Dec/Jan/Feb all in-season for hvy_winter
    assert r2['history_months_used'] == 6  # capped at BASELINE_CAP even though 7 were available

    # --- regular/occasional combo: always in-season, behaves like a flat trailing comparison -
    flat_months = [f"{mon}'24" for mon in MONTH_ORDER[:9]]  # Jan-Sep'24, 9 months
    flat_sales = {**{flat_months[i]: 9000.0 for i in range(6)}, **{flat_months[i]: 0.0 for i in range(6, 9)}}
    r3 = score_combo('Y' * 9, flat_months, lambda m: flat_sales.get(m, 0.0), 'regular')
    assert r3 is not None and r3['risk_score'] == 1.0 and r3['recent_in_season_count'] == 3
    r3b = score_combo('Y' * 9, flat_months, lambda m: flat_sales.get(m, 0.0), None)  # missing category
    assert r3b is not None and r3b['risk_score'] == 1.0  # null category defaults like regular
    r3c = score_combo('Y' * 9, flat_months, lambda m: flat_sales.get(m, 0.0), 'occasional')
    assert r3c is not None and r3c['risk_score'] == 1.0  # occasional also always in-season

    # --- Insufficient in-season-history skip case ---------------------------------------------
    # summer combo with only 2 in-season months of history behind the recent window (need >= 3).
    short_months = ["May'24", "Jun'24", "Jul'24", "Aug'24", "Sep'24"]  # all summer-in-season
    short_sales = {m: 5000.0 for m in short_months}
    # recent window = Jul/Aug/Sep (idx 2,3,4); history before it = May, Jun only (2 months, < 3).
    r4 = score_combo('Y' * 5, short_months, lambda m: short_sales.get(m, 0.0), 'summer')
    assert r4 is None, f"expected insufficient in-season history to skip, got {r4}"

    # --- Not currently listed -> skipped regardless of trend ----------------------------------
    assert score_combo('Y' * 4 + 'N', flat_months[:5], lambda m: 0.0, 'regular') is None

    # --- Baseline too small -> skipped as noise ------------------------------------------------
    tiny_sales = {**{flat_months[i]: 10.0 for i in range(6)}, **{flat_months[i]: 0.0 for i in range(6, 9)}}
    r5 = score_combo('Y' * 9, flat_months, lambda m: tiny_sales.get(m, 0.0), 'regular')
    assert r5 is None, f"expected tiny baseline to be skipped as noise, got {r5}"

    # --- Risk-tier tertiles: data-driven cutoffs over the flagged scores themselves -----------
    t1, t2 = tertile_cutoffs([0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    assert assign_tier(0.5, t1, t2) == 'Low'
    assert assign_tier(1.0, t1, t2) == 'High'
    assert tertile_cutoffs([0.9]) == (None, None)  # too few flagged combos
    assert assign_tier(0.9, None, None) == 'High'  # degenerate fallback

    print("demo OK")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        demo()
    else:
        build()
