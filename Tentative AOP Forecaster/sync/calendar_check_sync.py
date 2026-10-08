"""
Nightly accuracy check of the calendarised (reindexed) sales - runs right after calendar_reindex_sync in
sync/run_all.py (user, 2026-09-28: "how can i be sure that the calendarised sales is 100% accurate" -> "yes,
build the nightly check"). Read-only: it recomputes everything independently and compares cell by cell at
0.01 L; only its own sync.sync_runs row is written. Any failure marks the run 'failed' with the reason, which
the Sales Sync page shows next to the last sync.

Checks (month-wise snapshots, the ones the nightly sync rebuilds):
  1. saved actuals       = a fresh read of the raw month-wise export (store x division x month)
  2. saved reindexed     = the actuals moved by an independent rebuild of each cluster's month map
                           (db.calendar_shift.month_plan - each LY month spread by its days' sales, whole month
                           next to a not-yet-closed month - the same rule as scans.reindex_monthwise since 8 Oct 2026)
  3. conservation        = reindexed total = actual total per store x division (nothing created or lost)
  4. department tables   = the main tables (actual and reindexed, store x division x month)
  5. day maps            = each cluster of the calendar used covers every plan-year day once, no LY day reused
  6. clusters            = every TRADING store (SAME / NEW STORE) with sales has a calendar cluster; sales of the
                           rest (closed stores, HO, warehouses, sites - 316 L on 28 Sep 2026) are reported, not shifted
  7. calendar alignment  = EVERY saved calendar (not only the one used): no day moved 3+ months (year-end wrap) and
                           "same weekday last year" is the most common shift (no weekly drift) - db.calendar_shift.
                           alignment_issues; the engine checks unsaved calendars and the save refuses a failing one
  8. multi-year sales    = calendar.sales_fact (2026-10-08): 8a every stored actual month (2019+) = the export,
                           store x division x month (pyarrow group_by - independent of the loader); 8b every calendar's
                           reindexed months add back to their actuals; 8c the live calendar's months = the saved
                           reindexed snapshot. A restated old month fails 8a (stored months are frozen).
  plus a self-test: a planted 0.02 L error must fail checks 1 and 2, or the check itself is broken.

Not covered: that the data lake equals the finance / MIS books (needs an external report), festival dates
(festival_dates_sync), the day-wise snapshot (rebuilt only by a manual Run Reindex).

Run manually: python sync/calendar_check_sync.py   (--test: no-DB self-check)
"""
import calendar as _cal
import datetime
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
from sqlalchemy import text

from sync.common import call_with_timeout, sync_run

SOURCE_KEY = "calendar_check"
TOL_L = 0.01
LAKH = 1e5
KEYS = ["store", "division", "col"]


def compare(name, a, b, keys=KEYS):
    """a, b: DataFrames with keys + 'v' (rupees). -> check dict; ok when every cell agrees within TOL_L."""
    m = a.groupby(keys)["v"].sum().to_frame("a").join(b.groupby(keys)["v"].sum().to_frame("b"), how="outer").fillna(0)
    d = (m["a"] - m["b"]).abs() / LAKH
    worst = d.idxmax() if len(d) else None
    return {"name": name, "ok": bool((d <= TOL_L).all()), "cells": int(len(m)), "max_diff_L": round(float(d.max()) if len(d) else 0.0, 6),
            "fails": int((d > TOL_L).sum()), "worst": list(map(str, worst)) if isinstance(worst, tuple) else str(worst),
            "total_a_L": round(float(m["a"].sum()) / LAKH, 2), "total_b_L": round(float(m["b"].sum()) / LAKH, 2)}


def snapshot(session, kind):
    rows = session.execute(text("SELECT rows FROM calendar.sales_snapshots WHERE source_type = 'mw' AND kind = :k"), {"k": kind}).scalar() or []
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f"month-wise snapshot '{kind}' is empty")
    return df.rename(columns={"value": "v"})[KEYS + ["v"]]


def cluster_month_map(pairs):
    """{cluster: {ref 'YYYY-MM': fut 'YYYY-MM'}} - each LY month goes to the plan month most of its days map to."""
    buckets = {}
    for cl, ref, fut in pairs:
        buckets.setdefault(cl, {}).setdefault(ref.strftime("%Y-%m"), Counter())[fut.strftime("%Y-%m")] += 1
    return {cl: {rm: c.most_common(1)[0][0] for rm, c in b.items()} for cl, b in buckets.items()}


def shift(actual, store_cluster, cmap):
    """Actual cells moved to their plan month; returns (shifted, unmapped actual cells)."""
    df = actual.copy()
    df["cluster"] = df["store"].map(store_cluster)
    df["col"] = [cmap.get(c, {}).get(m) if isinstance(c, str) else None for c, m in zip(df["cluster"], df["col"])]
    return df.dropna(subset=["col"])[KEYS + ["v"]], df[df["col"].isna()]


def shift_shares(actual, store_cluster, plan):
    """Actual cells spread over plan months by db.calendar_shift.month_plan's shares - the rule the month-wise reindex
    uses since 2026-10-08 (proportional; whole month next to a not-yet-closed month). -> (shifted, unmapped cells)."""
    df = actual.copy()
    df["cluster"] = df["store"].map(store_cluster)
    have = {(cl, rm) for cl, p in plan.items() for rm in p}
    miss = [(c, m) not in have for c, m in zip(df["cluster"], df["col"])]
    sh = pd.DataFrame([(cl, rm, fm, s) for cl, p in plan.items() for rm, fs in p.items() for fm, s in fs.items() if s > 0],
                      columns=["cluster", "col", "fut", "share"])
    m = df[[not x for x in miss]].merge(sh, on=["cluster", "col"])
    m = m.assign(v=m["v"] * m["share"], col=m["fut"])
    return m.groupby(KEYS, as_index=False)["v"].sum(), df[miss]


def day_map_issues(pairs, fut_year):
    """Clusters whose map does not cover each plan-year day exactly once, or reuses an LY day."""
    days = 366 if _cal.isleap(fut_year) else 365
    by = {}
    for cl, ref, fut in pairs:
        by.setdefault(cl, ([], []))[0].append(ref)
        by[cl][1].append(fut)
    bad = {}
    for cl, (refs, futs) in by.items():
        fy = [f for f in futs if f.year == fut_year]
        if len(set(fy)) != days or len(fy) != len(set(fy)) or len(refs) != len(set(refs)):
            bad[cl] = {"plan_days": len(set(fy)), "dup_plan_days": len(fy) - len(set(fy)), "reused_ly_days": len(refs) - len(set(refs))}
    return bad


def alignment_check(session):
    """Check 7 over every saved calendar (user, 2026-10-08: "for all calendars - saved or unsaved")."""
    from db.calendar_shift import alignment_issues
    by_cal = {}
    for name, cl, r, f in session.execute(text(
            "SELECT c.name, p.cluster_name, p.ref_date, p.fut_date FROM calendar.calendar_day_pairs p "
            "JOIN calendar.calendars c ON c.calendar_id = p.calendar_id")):
        by_cal.setdefault(name, {}).setdefault(cl, []).append((r, f))
    bad = {name: issues for name, maps in by_cal.items() if (issues := alignment_issues(maps))}
    return {"name": "7 every saved calendar in line with the year (no year-end wrap, no weekly drift)",
            "ok": not bad, "calendars": len(by_cal), "bad": bad}


def raw_monthwise(session, months):
    """store x division x month SL_V from the newest month-wise export (same file the reindex reads)."""
    import pyarrow.parquet as pq
    folder = session.execute(text("SELECT config->>'path' FROM sync.sources WHERE source_key = 'data_lake_sales'")).scalar()
    from sync.common import latest_file
    src = latest_file(folder)   # the same file the reindex read (rs_common.lake_files) - not the newest name stamp
    lo = datetime.datetime.strptime(min(months), "%Y-%m")
    t = call_with_timeout(pq.read_table, src, columns=["BILLMONTH", "STORE_NAME", "DIVISION", "SL_V"],
                          filters=[("BILLMONTH", ">=", lo)]).to_pandas()
    t["col"] = pd.to_datetime(t["BILLMONTH"]).dt.strftime("%Y-%m")
    t = t[t["col"].isin(months) & t["STORE_NAME"].notna()]
    t["DIVISION"] = t["DIVISION"].fillna("(none)")
    return t.rename(columns={"STORE_NAME": "store", "DIVISION": "division", "SL_V": "v"})[KEYS + ["v"]], os.path.basename(src)


def raw_monthwise_all(session, lo, hi):
    """store x division x month SL_V for lo..hi from the newest month-wise export, summed with pyarrow's own group_by -
    a different code path from the loader (calendar_sales_fact_sync.read_monthwise, pandas), so check 8a is
    independent of it."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    folder = session.execute(text("SELECT config->>'path' FROM sync.sources WHERE source_key = 'data_lake_sales'")).scalar()
    from sync.common import latest_file
    src = latest_file(folder)
    parts = []
    with open(src, "rb") as fh:
        for b in pq.ParquetFile(fh).iter_batches(columns=["BILLMONTH", "STORE_NAME", "DIVISION", "SL_V"], batch_size=4_000_000):
            t = pa.table({"col": pc.strftime(b.column("BILLMONTH"), format="%Y-%m"), "store": b.column("STORE_NAME"),
                          "division": pc.fill_null(b.column("DIVISION"), "(none)"), "v": b.column("SL_V")})
            t = t.filter(pc.and_(pc.and_(pc.greater_equal(t["col"], lo), pc.less_equal(t["col"], hi)), pc.is_valid(t["store"])))
            parts.append(t.group_by(["store", "division", "col"]).aggregate([("v", "sum")]).to_pandas())
    df = pd.concat(parts).rename(columns={"v_sum": "v"})
    df.loc[df["division"].astype(str).str.strip() == "", "division"] = "(none)"
    return df.groupby(KEYS, as_index=False)["v"].sum(), os.path.basename(src)


def fact_checks(session, rx_calendar_id, shifted_snapshot):
    """Check 8 - the multi-year calendar sales (calendar.sales_fact, Phase 0, 2026-10-08)."""
    if not session.execute(text("SELECT to_regclass('calendar.sales_fact')")).scalar():
        return [{"name": "8 multi-year calendar sales", "ok": True, "note": "table not created yet"}], None
    q = lambda sql, **p: pd.DataFrame(session.execute(text(sql), p).mappings().all())
    act = q("SELECT store, division, to_char(month, 'YYYY-MM') AS col, sum(sl_v) AS v FROM calendar.sales_fact "
            "WHERE kind = 'actual' GROUP BY 1, 2, 3")
    if act.empty:
        return [{"name": "8 multi-year calendar sales", "ok": False, "note": "calendar.sales_fact holds no actual months"}], None
    raw, _ = raw_monthwise_all(session, act["col"].min(), act["col"].max())
    out = [compare(f"8a multi-year actuals = raw export ({act['col'].min()}..{act['col'].max()}, store x division x month)", act, raw)]
    # 8b conservation per calendar: each reindexed reference month adds back to its actuals (mapped stores)
    rx = q("SELECT calendar_id, store, division, to_char(ref_month, 'YYYY-MM') AS col, sum(sl_v) AS v FROM calendar.sales_fact "
           "WHERE kind = 'reindexed' GROUP BY 1, 2, 3, 4")
    act_ref = q("SELECT store, division, to_char(ref_month, 'YYYY-MM') AS col, sum(sl_v) AS v FROM calendar.sales_fact "
                "WHERE kind = 'actual' GROUP BY 1, 2, 3")
    store_cluster = dict(session.execute(text("SELECT store_id, cluster_name FROM calendar.store_calendar_clusters")).all())
    worst = {"name": "8b multi-year reindexed adds back to actuals (every calendar, store x division x reference month)",
             "ok": True, "calendars": 0, "cells": 0, "max_diff_L": 0.0, "fails": 0}
    for cal_id, g in (rx.groupby("calendar_id") if len(rx) else []):
        clusters = {c for (c,) in session.execute(text("SELECT DISTINCT cluster_name FROM calendar.calendar_day_pairs WHERE calendar_id = :c"),
                                                   {"c": int(cal_id)})}
        a = act_ref[act_ref["col"].isin(set(g["col"])) & act_ref["store"].map(store_cluster).isin(clusters)]
        c = compare("", g[KEYS + ["v"]], a)
        worst["calendars"] += 1; worst["cells"] += c["cells"]; worst["fails"] += c["fails"]
        worst["max_diff_L"] = max(worst["max_diff_L"], c["max_diff_L"]); worst["ok"] = worst["ok"] and c["ok"]
    out.append(worst)
    # 8c the live calendar's TY months = the Calendar's saved reindexed sales (TY months the next, still-open reference
    # month cannot feed yet)
    live = q("SELECT store, division, to_char(month, 'YYYY-MM') AS col, sum(sl_v) AS v FROM calendar.sales_fact "
             "WHERE kind = 'reindexed' AND calendar_id = :c GROUP BY 1, 2, 3", c=int(rx_calendar_id))
    if len(live):
        last_ref = q("SELECT to_char(max(ref_month), 'YYYY-MM') AS m FROM calendar.sales_fact WHERE kind = 'reindexed' AND calendar_id = :c",
                     c=int(rx_calendar_id))["m"][0]
        y, mth = int(last_ref[:4]) + 1, int(last_ref[5:])
        upto = f"{y if mth > 1 else y - 1}-{(mth - 1) or 12:02d}"
        cols = sorted(c for c in set(live["col"]) & set(shifted_snapshot["col"]) if c <= upto)
        out.append(compare(f"8c multi-year reindexed = Calendar's saved reindexed ({cols[0] if cols else '-'}..{upto})",
                           live[live["col"].isin(cols)], shifted_snapshot[shifted_snapshot["col"].isin(cols)]))
    return out, (act, raw)


def planted(df):
    out = df.copy()
    out.iloc[0, out.columns.get_loc("v")] += 0.02 * LAKH
    return out


def run_checks(session):
    rx = session.execute(text("SELECT detail FROM sync.sync_runs WHERE source_key = 'calendar_reindex' AND status = 'success' "
                              "ORDER BY sync_run_id DESC LIMIT 1")).scalar()
    if not rx:
        raise LookupError("no successful calendar_reindex run to check")
    cal_id = rx["calendar_id"]
    pairs = session.execute(text("SELECT cluster_name, ref_date, fut_date FROM calendar.calendar_day_pairs WHERE calendar_id = :c"),
                            {"c": cal_id}).all()
    fut_year = session.execute(text("SELECT fut_year FROM calendar.calendars WHERE calendar_id = :c"), {"c": cal_id}).scalar()
    store_cluster = dict(session.execute(text("SELECT store_id, cluster_name FROM calendar.store_calendar_clusters")).all())
    actual, shifted = snapshot(session, "actual"), snapshot(session, "trend_shifted")
    months = sorted(actual["col"].unique())
    raw, raw_file = raw_monthwise(session, months)
    from db.calendar_shift import load_day_weights, month_plan
    by_cluster = {}
    for cl, ref, fut in pairs:
        by_cluster.setdefault(cl, []).append((ref, fut))
    # same rule and the same "closed" test as the reindex (scans._is_month_closed: through sync closed_through)
    from sync.common import get_closed_through
    ct = get_closed_through()
    plan, _ = month_plan(by_cluster, load_day_weights(session), {m for m in months if not ct or m <= ct})
    recomputed, unmapped = shift_shares(actual, store_cluster, plan)

    checks = [compare("1 saved actuals = raw export", actual, raw),
              compare("2 saved reindexed = independent recompute", shifted, recomputed),
              compare("3 conservation: reindexed total = actual total (store x division)",
                      shifted.assign(col="all"), actual.drop(index=unmapped.index).assign(col="all")),
              compare("4a department actuals = main actuals", snapshot(session, "actual_dept"), actual),
              compare("4b department reindexed = main reindexed", snapshot(session, "trend_shifted_dept"), shifted)]
    bad_maps = day_map_issues(pairs, fut_year)
    checks.append({"name": "5 day maps: every plan day once, no LY day reused", "ok": not bad_maps,
                   "clusters": len({p[0] for p in pairs}), "bad": bad_maps})
    unmapped_names = sorted(unmapped["store"].unique().tolist())
    status = dict(session.execute(text("SELECT store_id, store_current_status FROM masterdata.stores "
                                       "WHERE valid_to IS NULL AND store_id = ANY(:s)"), {"s": unmapped_names}).all())
    trading = [st for st in unmapped_names if str(status.get(st) or "").upper() in ("SAME STORE", "NEW STORE")]
    checks.append({"name": "6 every trading store with sales has a calendar cluster", "ok": not trading, "trading_without_cluster": trading,
                   "others": {st: status.get(st) for st in unmapped_names if st not in trading}})
    checks.append(alignment_check(session))
    fchecks, fact_pair = fact_checks(session, cal_id, shifted)
    checks.extend(fchecks)
    selftest = not compare("", planted(actual), raw)["ok"] and not compare("", planted(shifted), recomputed)["ok"]
    if fact_pair:
        selftest = selftest and not compare("", planted(fact_pair[0]), fact_pair[1])["ok"]
    checks.append({"name": "self-test: a planted 0.02 L error is caught", "ok": selftest})
    return {"calendar_id": cal_id, "calendar_name": rx.get("calendar_name"), "raw_file": raw_file, "months": months,
            "tolerance_L": TOL_L, "unmapped_store_cells": int(len(unmapped)),
            "unmapped_L": round(float(unmapped["v"].sum()) / LAKH, 2), "unmapped_stores": unmapped_names[:20],
            "checks": checks}


def ensure_source():
    """Idempotent sync.sources row (SyncRun has an FK to it)."""
    from db.base import SessionLocal
    with SessionLocal() as db:
        db.execute(text("INSERT INTO sync.sources (source_key, config, enabled, ttl_minutes) "
                        "VALUES (:k, CAST(:cfg AS JSON), true, 1440) ON CONFLICT (source_key) DO NOTHING"),
                   {"k": SOURCE_KEY, "cfg": json.dumps({"note": "Read-only accuracy check of the calendarised sales"})})
        db.commit()


def run():
    ensure_source()
    with sync_run(SOURCE_KEY) as (session, result):
        detail = run_checks(session)
        result["detail"] = detail
        result["rows_read"] = sum(c.get("cells", 0) for c in detail["checks"])
        failed = [c["name"] for c in detail["checks"] if not c["ok"]]
        if failed:
            raise RuntimeError("Calendarised sales check FAILED: " + "; ".join(failed))


def demo():
    """No-DB check of the comparison, month map, shift and day-map rules."""
    a = pd.DataFrame({"store": ["S1", "S1"], "division": ["KIDS"] * 2, "col": ["2026-03", "2026-04"], "v": [100.0, 200.0]})
    assert compare("x", a, a)["ok"] and not compare("x", planted(a), a)["ok"]
    d = datetime.date
    pairs = [("C", d(2026, 3, 30), d(2027, 3, 29)), ("C", d(2026, 3, 31), d(2027, 4, 1)), ("C", d(2026, 3, 29), d(2027, 3, 28)),
             ("C", d(2026, 4, 1), d(2027, 4, 2))]
    cm = cluster_month_map(pairs)
    assert cm == {"C": {"2026-03": "2027-03", "2026-04": "2027-04"}}, cm
    s, un = shift(a.assign(store=["S1", "S2"]), {"S1": "C"}, cm)
    assert s["col"].tolist() == ["2027-03"] and un["store"].tolist() == ["S2"]
    assert day_map_issues(pairs, 2027)["C"]["plan_days"] == 4
    from db.calendar_shift import alignment_issues
    good = [(d(2025, 1, 10) + datetime.timedelta(i), d(2025, 1, 10) + datetime.timedelta(i + 364)) for i in range(60)]
    late = [(r, f + datetime.timedelta(7)) for r, f in good]                    # a week late all along
    wrap = good[:-1] + [(d(2025, 12, 27), d(2026, 1, 3))]                       # ref December on TY January
    assert alignment_issues({"C": good}) == {}
    assert alignment_issues({"C": late})["C"]["most_common_shift"] == 371
    assert alignment_issues({"C": wrap})["C"]["far_moves"] == 1
    print("calendar_check demo OK")


if __name__ == "__main__":
    if "--test" in sys.argv:
        demo()
    else:
        run()
        print("calendar_check: all checks passed")
