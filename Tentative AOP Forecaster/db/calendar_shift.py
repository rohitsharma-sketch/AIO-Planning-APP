"""Festival-shift monthly sales totals onto a future year's festival calendar,
using the Calendar Engine's locked day maps (calendar.calendar_day_pairs).

Method = the Calendar Engine's own Month Wise Matrix split (see
ReindexOutputPanel.jsx / logic-base): month-level sales have no day field, so
each REFERENCE month's total is divided across future months in proportion to
how many future days that reference month's days feed, per the cluster's
locked day map. E.g. if 9 of Oct'25's Diwali-window days map into Nov'27, that
share of Oct'25's sales moves into Nov'27. Totals are conserved for every
reference month the map covers.

Used by engine_v3.apply_festival_shift for BOTH the real closed FY27 bases and
the option-(b) FY26 placeholder bases (user decision 2026-09-24).
"""
from collections import Counter, defaultdict


def month_shares(pairs):
    """{ref 'YYYY-MM': {fut 'YYYY-MM': share}} from [(ref_date, fut_date)] -
    each ref month's shares sum to 1."""
    n = Counter((r.strftime("%Y-%m"), f.strftime("%Y-%m")) for r, f in pairs)
    per_ref = Counter()
    for (r, _f), k in n.items():
        per_ref[r] += k
    out = defaultdict(dict)
    for (r, f), k in n.items():
        out[r][f] = k / per_ref[r]
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


def load_shift_maps(session, year_pairs=((2025, 2026), (2026, 2027))):
    """{'store_cluster': {store: cluster}, 'shares': {(ry, fy): {cluster: month_shares}},
    'calendars': {(ry, fy): name}} from the shared DB. Picks the calendar for
    each year pair the same way SalesPlan/AOP consumers do: latest saved_at."""
    from sqlalchemy import text

    store_cluster = dict(session.execute(text(
        "SELECT store_id, cluster_name FROM calendar.store_calendar_clusters")).all())
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
        shares[(ry, fy)] = {cl: month_shares(p) for cl, p in by_cluster.items()}
        calendars[(ry, fy)] = cal.name
    return {"store_cluster": store_cluster, "shares": shares, "calendars": calendars}
