"""
Rigorous 3-checkpoint verification for every saved Calendar Engine template.
Run after ANY calendar regeneration (whether via the app's own "Create
Calendar" + "Lock & Save" flow, or a direct script) - a naive check that only
looks at a festival's own anchor date (position 0) is not enough; see
docs/HANDOVER.md section 7 for the full story of why this exists.

Usage: python "Calendar Engine/scripts/verify_calendars.py"
Requires: psycopg, and DATABASE_URL reachable (reads from
"Tentative AOP Forecaster/.env" the same way the rest of the platform does).

Checkpoint 1 (structural): every cluster has exactly one row per calendar day
of the fut_year, and every future date is used exactly once (no duplicate
future dates - a hard invariant regardless of "sharedRef" reuse, which only
ever duplicates REFERENCE dates, never future ones).

Checkpoint 2 (full-window self-match): for EVERY position in EVERY festival's
pre/core/post window - not just the position-0 anchor - verify ref_date+pos
maps to fut_date+pos exactly. Checking only the anchor lets an off-window
position (e.g. Eid al-Fitr's pos -3 while pos 0 looks fine) silently mismatch
undetected - this happened for real, more than once, in the 2026-09-18
session that built this script.

Checkpoint 3 (cross-cluster consistency): for every festival shared across
multiple clusters, for EVERY position, verify every cluster produces the
identical (ref_date, fut_date) pair - "no two clusters may shift the same
festival by a different amount," extended to the whole window, not just
the anchor.

A finding from either checkpoint 2 or 3 is not automatically a bug: two
different real festivals can genuinely land on the same calendar day in a
given year (e.g. Eid al-Fitr vs Bihu in April 2024, Raksha Bandhan vs
Milad-un-Nabi in August 2026) - only one can "own" that day, resolved by
engine.js's buildFestMap priority rule (smaller |position| wins, then
smaller total window size). Cross-check any finding against the actual
festival dates before assuming it's a defect - see docs/HANDOVER.md §7 for
the full list of currently-accepted overlaps.
"""
import os
import re
import sys
from collections import defaultdict
from datetime import timedelta

import psycopg


def _load_database_url():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "Tentative AOP Forecaster", ".env")
    with open(env_path) as f:
        for line in f:
            m = re.match(r"DATABASE_URL=(.+)", line.strip())
            if m:
                # psycopg doesn't understand the "postgresql+psycopg://" SQLAlchemy dialect prefix
                return m.group(1).replace("postgresql+psycopg://", "postgresql://")
    raise RuntimeError(f"DATABASE_URL not found in {env_path}")


def main():
    conn = psycopg.connect(_load_database_url())
    cur = conn.cursor()

    cur.execute("SELECT calendar_id, name, ref_year, fut_year FROM calendar.calendars ORDER BY saved_at")
    calendars = cur.fetchall()

    grand_total_issues = 0
    for cal_id, label, ref_yr, fut_yr in calendars:
        print(f"\n{'='*70}\n{label} (id={cal_id})")
        issues = 0

        cur.execute("SELECT DISTINCT cluster_name FROM calendar.calendar_day_pairs WHERE calendar_id=%s", (cal_id,))
        clusters = [r[0] for r in cur.fetchall()]
        if not clusters:
            print("  (no day pairs saved for this calendar - skipping)")
            continue

        # --- Checkpoint 1: structural ---
        for cl in clusters:
            cur.execute(
                "SELECT COUNT(*), COUNT(DISTINCT fut_date) FROM calendar.calendar_day_pairs "
                "WHERE calendar_id=%s AND cluster_name=%s",
                (cal_id, cl),
            )
            n, n_distinct_fut = cur.fetchone()
            if n_distinct_fut != n:
                print(f"  [CP1 STRUCTURAL] {cl}: {n} rows but only {n_distinct_fut} distinct future dates (duplicate future date!)")
                issues += 1

        # --- Checkpoint 2 + 3: full-window self-match + cross-cluster consistency ---
        cur.execute(
            """
            SELECT cc.cluster_name, ccf.name, ccf.ref_date, ccf.fut_date, ccf.pre, ccf.core, ccf.post
            FROM calendar.calendar_clusters cc
            JOIN calendar.calendar_cluster_festivals ccf ON ccf.calendar_cluster_id = cc.id
            WHERE cc.calendar_id = %s
            """,
            (cal_id,),
        )
        rows = cur.fetchall()

        cur.execute("SELECT cluster_name, ref_date, fut_date FROM calendar.calendar_day_pairs WHERE calendar_id=%s", (cal_id,))
        pairs_by_cluster_ref = defaultdict(list)  # (cluster, ref_date) -> [fut_date, ...] (list: sharedRef can duplicate)
        for cl, rd, fd in cur.fetchall():
            pairs_by_cluster_ref[(cl, rd)].append(fd)

        cross_cluster = defaultdict(set)  # (festival_name, position) -> {(ref_date, fut_date), ...}

        for cluster, fname, ref_date, fut_date, pre, core, post in rows:
            for pos in range(-pre, post + core):
                rd = ref_date + timedelta(days=pos)
                fd = fut_date + timedelta(days=pos)
                if rd.year != ref_yr or fd.year != fut_yr:
                    continue  # position spills into an adjacent year - not this calendar's concern
                actual_futs = pairs_by_cluster_ref.get((cluster, rd), [])
                if fd not in actual_futs:
                    print(f"  [CP2 WINDOW] {cluster} / {fname} pos={pos:+d}: ref={rd} expected fut={fd}, got {actual_futs or 'NO PAIR'}")
                    issues += 1
                cross_cluster[(fname, pos)].add((rd, fd))

        for (fname, pos), pairset in cross_cluster.items():
            if len(pairset) > 1:
                print(f"  [CP3 CROSS-CLUSTER] {fname} pos={pos:+d}: clusters disagree: {sorted(pairset)}")
                issues += 1

        print(f"  -> {issues} issue(s) found")
        grand_total_issues += issues

    print(f"\n{'='*70}\nGRAND TOTAL ISSUES ACROSS ALL CALENDARS: {grand_total_issues}")
    conn.close()
    return grand_total_issues


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
