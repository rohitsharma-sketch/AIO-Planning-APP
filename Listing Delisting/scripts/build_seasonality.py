"""
Builds app/seasonality.json: per-department calendar-month seasonality, aggregated across all
available years (Jan across 2024/2025/2026, etc.) rather than the absolute Apr'23-Sep'26
timeline the rest of the app uses. Backs two business questions (see PRD_LOGIC.md):
  1. Listing/delisting timing -- which calendar months are historically weak for a department
     (candidate delist/relist windows).
  2. Best growth periods -- which month-to-month transitions historically grow the most, if
     you were to bank on (invest heavily in) a department.

Dept-level = summed across all stores (this is department seasonality, not store-specific).
The trailing "(Till Date)" month is a partial month (a few days' billing) -- excluded from
every calendar-month average and from any growth transition touching it, same reasoning as
build_risk_scores.py's anchor logic.

Usage: python build_seasonality.py
"""
import json
import os
import re
import statistics

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONTH_ORDER = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MONTH_RE = re.compile(r"^([A-Za-z]{3})'(\d{2})(\(Till Date\))?$")
MIN_TRANSITION_BASE = 2000.0  # rupees; same floor as build_risk_scores.py's MIN_BASELINE
MIN_TRANSITION_YEARS = 2      # need at least this many qualifying years to report a month


def parse_months(months):
    """Returns list of (index, mon_abbr) for every FULL (non-partial) month, in order."""
    parsed = []
    for i, m in enumerate(months):
        match = MONTH_RE.match(m)
        if not match:
            raise ValueError(f"Unparseable month label: {m}")
        mon, _yy, partial = match.groups()
        if partial:
            continue
        parsed.append((i, mon))
    return parsed


def dept_seasonality(dept, totals, months, parsed):
    """totals: {month_label: summed SL_V across all stores for this dept}."""
    by_cal = {mon: [] for mon in MONTH_ORDER}
    for i, mon in parsed:
        by_cal[mon].append(totals.get(months[i], 0.0))

    avg_by_month = {mon: round(sum(v) / len(v), 2) if v else 0.0 for mon, v in by_cal.items()}
    years_count = {mon: len(v) for mon, v in by_cal.items()}

    covered = [mon for mon in MONTH_ORDER if years_count[mon] > 0]
    overall_avg = round(sum(avg_by_month[m] for m in covered) / len(covered), 2) if covered else 0.0

    weak_months = []
    if overall_avg > 0:
        for mon in covered:
            pct = (avg_by_month[mon] - overall_avg) / overall_avg * 100
            weak_months.append({
                'month': mon, 'avg_sales': avg_by_month[mon],
                'pct_vs_annual_avg': round(pct, 1), 'years': years_count[mon],
            })
        weak_months.sort(key=lambda r: r['pct_vs_annual_avg'])

    # Growth "into" each calendar month (Feb->Mar's growth is attributed to Mar) -- one row per
    # calendar month, same grain as weak_months, instead of a Mon1->Mon2 pair. Two robustness
    # guards, both needed (see PRD_LOGIC.md for real examples of each failure mode):
    #   1. MIN_TRANSITION_BASE: skip a year's growth entirely if the FROM month's sales are
    #      below this floor -- a near-zero base (e.g. Rs 159) turns an ordinary seasonal ramp-up
    #      into a meaningless six-digit "% growth" figure, just from dividing by almost nothing.
    #   2. MEDIAN, not MEAN, across the qualifying years -- even above the floor, a single
    #      unusually extreme year can dominate a 2-4 year average; the median is what most years
    #      actually look like.
    #   3. A destination month below the department's OWN annual average never qualifies, even
    #      with strong relative growth -- it's still one of this department's weaker months in
    #      absolute terms, and calling it "best growth" while it also shows up in weak_months is
    #      self-contradictory. See NOT AMBIGUOUS below.
    idx_total = {i: totals.get(months[i], 0.0) for i, _ in parsed}
    transitions = {}
    for pos in range(len(parsed) - 1):
        i, mon_from = parsed[pos]
        j, mon_to = parsed[pos + 1]
        if j != i + 1:
            continue  # a gap in the full-month sequence (shouldn't happen mid-series, defensive)
        from_val = idx_total[i]
        if from_val < MIN_TRANSITION_BASE:
            continue  # base too small for a % change to mean anything (also catches <= 0)
        growth_pct = (idx_total[j] - from_val) / from_val * 100
        transitions.setdefault(mon_to, []).append(growth_pct)

    growth_summary = []
    for mon_to, vals in transitions.items():
        if len(vals) < MIN_TRANSITION_YEARS:
            continue  # not enough qualifying years for a reliable figure -- skip, don't report a noisy one
        median_growth = statistics.median(vals)
        if median_growth <= 0:
            continue  # a "best growth period" showing an actual decline is misleading, not useful
        # NOT AMBIGUOUS: a month that's itself below this department's own annual average is
        # still, in absolute terms, one of its underperforming months -- even if it grew off an
        # even-worse prior month. Calling that a "best growth period" contradicts the same
        # month's entry in weak_months. Only a month that's genuinely above its own department's
        # average earns the growth label -- unambiguously good by both measures, not just
        # "less bad than last month."
        if avg_by_month[mon_to] < overall_avg:
            continue
        mon_from = MONTH_ORDER[(MONTH_ORDER.index(mon_to) - 1) % 12]
        growth_summary.append({
            'month': mon_to, 'from_month': mon_from,
            'avg_growth_pct': round(median_growth, 1), 'years': len(vals),
        })
    growth_summary.sort(key=lambda r: r['avg_growth_pct'], reverse=True)

    # Seasonality-intensity index = coefficient of variation (population stdev / mean) across
    # the covered calendar-month averages. Flat department -> CV ~0; hard-seasonal -> large CV.
    # Needs >=2 covered months and a positive mean, else undefined -> 0.0 (see limitations).
    covered_vals = [avg_by_month[m] for m in covered]
    seasonality_index = (
        round(statistics.pstdev(covered_vals) / overall_avg, 4)
        if len(covered_vals) >= 2 and overall_avg > 0 else 0.0
    )

    return {
        'avg_sales_by_month': avg_by_month,
        'years_count_by_month': years_count,
        'overall_avg_monthly_sales': overall_avg,
        'weak_months': weak_months,
        'growth_transitions': growth_summary,
        'seasonality_index': seasonality_index,
    }


def build():
    with open(os.path.join(BASE, 'app', 'kb.json'), encoding='utf-8') as f:
        kb = json.load(f)
    with open(os.path.join(BASE, 'app', 'sales.json'), encoding='utf-8') as f:
        sales = json.load(f)
    months = kb['months']
    parsed = parse_months(months)

    dept_month_total = {}
    for depts in sales['data'].values():
        for dept, by_month in depts.items():
            acc = dept_month_total.setdefault(dept, {})
            for month_label, val in by_month.items():
                acc[month_label] = acc.get(month_label, 0.0) + val

    departments = {
        dept: dept_seasonality(dept, dept_month_total.get(dept, {}), months, parsed)
        for dept in kb['departments']
    }

    # Tier the seasonality_index into Low/Medium/High/Very High using quartiles of the ACTUAL
    # CV distribution across all departments -- not hardcoded round numbers (see PRD_LOGIC.md).
    cvs = sorted(d['seasonality_index'] for d in departments.values())
    q1, q2, q3 = statistics.quantiles(cvs, n=4)
    for d in departments.values():
        idx = d['seasonality_index']
        d['seasonality_tier'] = (
            'Low' if idx <= q1 else 'Medium' if idx <= q2 else 'High' if idx <= q3 else 'Very High'
        )

    out = {
        'calendar_months': MONTH_ORDER,
        'method': (
            'Per department, SL_V summed across all stores per month, then grouped by calendar '
            'month across all years present (e.g. Jan pools Jan\'24/25/26; 2023 Q1 has no '
            'listing/sales data at all, and the trailing "(Till Date)" month is excluded as '
            'partial). avg_sales_by_month/years_count_by_month give the mean and the sample '
            'size (years) behind it -- typically 3-4, sometimes fewer near the 2023 Q1 gap or '
            'the 2026 partial tail. weak_months ranks calendar months by % below the '
            'department\'s own overall_avg_monthly_sales (delist/relist candidates). '
            'growth_transitions gives, per calendar month, the median month-over-month % '
            'growth arriving into it from the previous month (e.g. the "Mar" row is Feb->Mar '
            'growth -- from_month says which prior month), ranked descending (best growth '
            'periods). Median rather than mean so one extreme year cannot dominate a 2-4 year '
            'average; a year only counts if its starting month\'s sales were >= Rs 2,000 (a '
            'near-zero base turns an ordinary ramp-up into a meaningless six-digit % figure); a '
            'month needs >= 2 qualifying years to be reported at all. seasonality_index is the coefficient of variation '
            '(population stdev / mean of the covered avg_sales_by_month values) -- a flat '
            'department is near 0, a hard-seasonal one (e.g. RAINCOAT) is large. '
            'seasonality_tier buckets it into Low/Medium/High/Very High using quartiles of the '
            'seasonality_index distribution across all departments in this file (see '
            'seasonality_index_quartiles below) -- not fixed thresholds.'
        ),
        'seasonality_index_quartiles': {'q1': round(q1, 4), 'q2': round(q2, 4), 'q3': round(q3, 4)},
        'departments': departments,
    }
    out_path = os.path.join(BASE, 'app', 'seasonality.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f"OK: {len(departments)} departments -> {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")


def demo():
    """Smallest runnable check: calendar-month pooling + growth math, including the zero-base skip."""
    months = ["Jan'24", "Feb'24", "Mar'24", "Jan'25", "Feb'25", "Mar'25(Till Date)"]
    parsed = parse_months(months)
    assert [mon for _, mon in parsed] == ['Jan', 'Feb', 'Mar', 'Jan', 'Feb'], parsed
    totals = {"Jan'24": 3000.0, "Feb'24": 6000.0, "Mar'24": 9000.0, "Jan'25": 4000.0, "Feb'25": 8000.0}
    r = dept_seasonality('X', totals, months, parsed)
    assert r['years_count_by_month']['Jan'] == 2 and r['years_count_by_month']['Mar'] == 1
    assert r['avg_sales_by_month']['Jan'] == 3500.0
    growth_by_month = {g['month']: g for g in r['growth_transitions']}
    # Jan->Feb: 2024 (3000->6000, +100%) and 2025 (4000->8000, +100%) -- both bases clear the
    # Rs 2,000 floor, so both years count; the "Feb" row's from_month should say "Jan".
    assert growth_by_month['Feb']['from_month'] == 'Jan'
    assert growth_by_month['Feb']['years'] == 2
    assert abs(growth_by_month['Feb']['avg_growth_pct'] - 100.0) < 0.01
    # Feb->Mar: 2025's Mar is a Till Date month, excluded upstream by parse_months(), so only
    # 2024 could even be a candidate -- that's a single year, below MIN_TRANSITION_YEARS (2).
    assert 'Mar' not in growth_by_month, "Feb->Mar should have < 2 qualifying years (only 2024 has a full Mar)"

    # MIN_TRANSITION_BASE floor: a from-month below Rs 2,000 doesn't get counted for that year,
    # even though it's a "real" positive number, not exactly zero.
    tiny_totals = {"Jan'24": 500.0, "Feb'24": 50000.0}  # from_val=500 < floor -> this year excluded
    tiny = dept_seasonality('TINY', tiny_totals, ["Jan'24", "Feb'24"], parse_months(["Jan'24", "Feb'24"]))
    assert 'Feb' not in {g['month'] for g in tiny['growth_transitions']}

    # MIN_TRANSITION_YEARS: even with a qualifying base, a single year isn't enough to report.
    one_year_totals = {"Jan'24": 3000.0, "Feb'24": 6000.0}
    one_year = dept_seasonality('ONEYR', one_year_totals,
                                 ["Jan'24", "Feb'24"], parse_months(["Jan'24", "Feb'24"]))
    assert 'Feb' not in {g['month'] for g in one_year['growth_transitions']}

    # THE OUTLIER-ROBUSTNESS FIX: 3 years of Jan->Feb growth where one year is a wild outlier
    # (mirrors the real KBW_THERMAL UPPER case) -- the reported figure must be the MEDIAN of the
    # three, not the mean (which the outlier would drag far away from what a typical year looks like).
    outlier_months = ["Jan'23", "Feb'23", "Jan'24", "Feb'24", "Jan'25", "Feb'25"]
    outlier_totals = {
        "Jan'23": 2000.0, "Feb'23": 122000.0,   # +6000% (the outlier year)
        "Jan'24": 2000.0, "Feb'24": 3000.0,     # +50%
        "Jan'25": 2000.0, "Feb'25": 3200.0,     # +60%
    }
    outlier = dept_seasonality('OUTLIER', outlier_totals, outlier_months, parse_months(outlier_months))
    feb_row = next(g for g in outlier['growth_transitions'] if g['month'] == 'Feb')
    assert feb_row['years'] == 3
    assert feb_row['avg_growth_pct'] == 60.0, feb_row  # median(6000, 50, 60) == 60, not the ~2037 mean

    # NOT AMBIGUOUS: Feb grows a clean +100% off Jan every year, but Mar is this department's
    # real peak (way above its own annual average) -- Feb itself stays below that average, so it
    # must NOT appear in "best growth periods" even with perfectly good, floor-clearing growth
    # numbers. Only Mar (genuinely above average) should qualify.
    peak_months = ["Jan'24", "Feb'24", "Mar'24", "Jan'25", "Feb'25", "Mar'25"]
    peak_totals = {
        "Jan'24": 3000.0, "Feb'24": 6000.0, "Mar'24": 50000.0,
        "Jan'25": 3000.0, "Feb'25": 6000.0, "Mar'25": 50000.0,
    }
    peak = dept_seasonality('PEAK', peak_totals, peak_months, parse_months(peak_months))
    growth_months = {g['month'] for g in peak['growth_transitions']}
    assert 'Feb' not in growth_months, "Feb is below its own department's annual average -- must not show as 'best growth' despite +100% MoM"
    assert 'Mar' in growth_months, "Mar is genuinely above average -- should still qualify"

    # A DECLINE never appears in "best growth periods" -- a negative median growth is excluded
    # entirely, not shown as the least-bad option (a real issue found in KBW_THERMAL UPPER,
    # where most of the year is decline off a single in-season peak).
    decline_months = ["Jan'24", "Feb'24", "Jan'25", "Feb'25"]
    decline_totals = {"Jan'24": 9000.0, "Feb'24": 3000.0, "Jan'25": 8000.0, "Feb'25": 2000.0}
    decline = dept_seasonality('DECLINE', decline_totals, decline_months, parse_months(decline_months))
    assert 'Feb' not in {g['month'] for g in decline['growth_transitions']}

    # seasonality_index: a flat department (same value every month) has CV == 0; a spiky one
    # (all sales in one month) has a large CV.
    flat_totals = {"Jan'24": 100.0, "Feb'24": 100.0, "Mar'24": 100.0}
    flat_parsed = parse_months(["Jan'24", "Feb'24", "Mar'24"])
    flat = dept_seasonality('FLAT', flat_totals, ["Jan'24", "Feb'24", "Mar'24"], flat_parsed)
    assert flat['seasonality_index'] == 0.0, flat['seasonality_index']

    spiky_totals = {"Jan'24": 0.0, "Feb'24": 0.0, "Mar'24": 900.0}
    spiky_parsed = parse_months(["Jan'24", "Feb'24", "Mar'24"])
    spiky = dept_seasonality('SPIKY', spiky_totals, ["Jan'24", "Feb'24", "Mar'24"], spiky_parsed)
    assert spiky['seasonality_index'] > flat['seasonality_index'], spiky['seasonality_index']
    print("demo OK")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        demo()
    else:
        build()
