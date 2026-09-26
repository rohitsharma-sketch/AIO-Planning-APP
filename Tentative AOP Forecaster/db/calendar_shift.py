"""Festival-shift monthly sales totals onto a future year's festival calendar,
using the Calendar Engine's locked day maps (calendar.calendar_day_pairs).

Method = the Calendar Engine's own Month Wise Matrix split (see
ReindexOutputPanel.jsx / logic-base): month-level sales have no day field, so
each REFERENCE month's total is divided across future months in proportion to
the SALES of the days that feed each future month (2026-09-25, option b:
cluster day sales from calendar.cluster_day_sales, see
sync/day_weights_sync.py), falling back to plain day COUNT for a cluster /
month without day data. Day count alone valued every moved day at its
month's average, which pulled the LfL KLM Mar'27 base 114.4 -> 109.8 Cr. E.g. if 9 of Oct'25's Diwali-window days map into Nov'27, that
share of Oct'25's sales moves into Nov'27. Totals are conserved for every
reference month the map covers.

Used by engine_v3.apply_festival_shift for BOTH the real closed FY27 bases and
the option-(b) FY26 placeholder bases (user decision 2026-09-24).
"""
from collections import Counter, defaultdict


def month_shares(pairs, weights=None):
    """{ref 'YYYY-MM': {fut 'YYYY-MM': share}} from [(ref_date, fut_date)] -
    each ref month's shares sum to 1. With `weights` ({date: day sales} for
    this cluster) a ref month is split by the sales of the days feeding each
    future month; a ref month with any day missing from `weights` (or zero
    total) keeps the day-count split."""
    n, w = Counter(), Counter()
    per_ref, per_ref_w, uncovered = Counter(), Counter(), set()
    for r, f in pairs:
        key = (r.strftime("%Y-%m"), f.strftime("%Y-%m"))
        n[key] += 1
        per_ref[key[0]] += 1
        if weights is not None:
            v = weights.get(r)
            if v is None:
                uncovered.add(key[0])
            else:
                w[key] += max(v, 0.0)
                per_ref_w[key[0]] += max(v, 0.0)
    out = defaultdict(dict)
    for (r, f), k in n.items():
        weighted = weights is not None and r not in uncovered and per_ref_w[r] > 0
        out[r][f] = w[(r, f)] / per_ref_w[r] if weighted else k / per_ref[r]
    return dict(out)


def load_day_weights(session):
    """{cluster: {date: day sales}} from calendar.cluster_day_sales, {} when
    the table doesn't exist yet (day-count fallback everywhere)."""
    from sqlalchemy import text
    exists = session.execute(text("SELECT to_regclass('calendar.cluster_day_sales')")).scalar()
    if not exists:
        return {}
    out = defaultdict(dict)
    for cl, d, v in session.execute(text("SELECT cluster_name, sale_date, value FROM calendar.cluster_day_sales")):
        out[cl][d] = float(v)
    return dict(out)


def shift_month_totals(monthly, shares):
    """{fut 'YYYY-MM': value} from {ref 'YYYY-MM': value} and month_shares().
    A ref month the map doesn't cover is dropped (it has no future days)."""
    out = defaultdict(float)
    for r, v in monthly.items():
        if not v:
            continue
        for f, s in shares.get(r, {}).items():
            out[f] += v * s
    return dict(out)


def incomplete_targets(monthly, shares):
    """Future months fed by at least one reference month that has NO data in
    `monthly` (key absent - e.g. FY26 actuals not synced yet). Their shifted
    value would silently count those days as 0 sales, so callers must keep
    the unshifted value for them instead. (Bug caught 2026-09-24: Feb'26
    missing -> Mar'27 LfL KLM base fell 114.4 -> 99.8 Cr.) A key present
    with value 0 is real data (a genuinely zero month), not missing."""
    return {f for r, fs in shares.items() if r not in monthly for f, s in fs.items() if s > 0}


def load_shift_maps(session, year_pairs=((2025, 2026), (2026, 2027))):
    """{'store_cluster': {store: cluster}, 'shares': {(ry, fy): {cluster: month_shares}},
    'calendars': {(ry, fy): name}} from the shared DB. Picks the calendar for
    each year pair the same way SalesPlan/AOP consumers do: latest saved_at."""
    from sqlalchemy import text

    store_cluster = dict(session.execute(text(
        "SELECT store_id, cluster_name FROM calendar.store_calendar_clusters")).all())
    day_weights = load_day_weights(session)
    shares, calendars = {}, {}
    for ry, fy in year_pairs:
        cal = session.execute(text(
            "SELECT calendar_id, name FROM calendar.calendars WHERE ref_year = :ry AND fut_year = :fy "
            "ORDER BY saved_at DESC LIMIT 1"), {"ry": str(ry), "fy": str(fy)}).first()
        if cal is None:
            continue
        by_cluster = defaultdict(list)
        for cl, r, f in session.execute(text(
                "SELECT cluster_name, ref_date, fut_date FROM calendar.calendar_day_pairs WHERE calendar_id = :id"),
                {"id": cal.calendar_id}):
            by_cluster[cl].append((r, f))
        shares[(ry, fy)] = {cl: month_shares(p, day_weights.get(cl)) for cl, p in by_cluster.items()}
        # A future day with no actual sales yet (e.g. Sep-Dec'26, whose base is
        # the 2025 placeholder shifted onto 2026) takes the weight of the ref
        # day this map lands on it, so the NEXT year pair's split still sees
        # where the festival value sits (Diwali'25 -> Nov'26 -> Oct'27).
        for cl, p in by_cluster.items():
            w = day_weights.setdefault(cl, {})
            for r, f in p:
                if f not in w and r in w:
                    w[f] = w[r]
        # The id, not just the name: a re-save keeps the name but gets a new id, so the name alone can't say
        # which day map a run used (audit 2026-09-26). This label is each store's "Base Calendar" in the run.
        calendars[(ry, fy)] = f"{cal.name} (id {cal.calendar_id})"
    return {"store_cluster": store_cluster, "shares": shares, "calendars": calendars}
