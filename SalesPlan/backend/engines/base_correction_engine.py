"""
Base Correction Engine
======================
Optional post-processing engine — runs after attribute correction (or directly
after New Dept if attribute correction is skipped).

Gap condition:
    active dept  AND  TY plan = 0
    (LY = 0 is explicitly allowed — new/recently-introduced departments are
    the primary use-case; the peer benchmark fills them correctly.)
    Division must have at least one planned dept (any_planned guard) to
    exclude stores where dept-level planning was never applied.

Fill formula (per store × div × dept × month):
    col1 = MAX(TY) across SSG peers with same zone × grade for that dept/month
    col2 = AVG(TY) across same peer set
    col3 = (col1 + col2) / 2          ← zone-grade benchmark
    col4 = (LY_this_store + col3) / 2 ← corrected TY

    If no peer data exists for the exact zone × grade combination,
    falls back to grade-only peers, then zone-only, then all-SSG.

Zone  = store's cluster field
Grade = numeric prefix of tag ("032 - Stores" → "032");
        for stores without a grade tag, inherits from their ref store.

Review sheet: every correction journaled with full audit trail.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import io, json, os, copy
import pandas as pd
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from actuals_manager import load_actuals, locked_ly_months

router = APIRouter()

_BASE            = os.path.dirname(__file__)
ATTR_PLAN_PATH   = os.path.join(_BASE, "..", "attr_corrected_plan.json")
FINAL_PLAN_PATH  = os.path.join(_BASE, "..", "final_dept_plan.json")
DEPT_GROWTH_PATH = os.path.join(_BASE, "..", "department_growth.json")
BASE_PLAN_PATH   = os.path.join(_BASE, "..", "base_corrected_plan.json")
REVIEW_PATH      = os.path.join(_BASE, "..", "base_correction_review.json")

TY_MONTHS = ["Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
             "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"]
LY_MONTHS = ["Mar'26","Apr'26","May'26","Jun'26","Jul'26","Aug'26",
             "Sep'26","Oct'26","Nov'26","Dec'26","Jan'27","Feb'27","Mar'27"]
MONTH_PAIR = dict(zip(TY_MONTHS, LY_MONTHS))


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load_source_plan() -> dict:
    """Use attr_corrected_plan if available, else final_dept_plan."""
    for path in (ATTR_PLAN_PATH, FINAL_PLAN_PATH):
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}


def _load_growth_matrix() -> dict:
    # Saved matrix + BIS's live growth, the same values the Growth Matrix screen shows (user, 2026-09-26).
    from engines.department_plan import live_growth_matrix
    return live_growth_matrix()


# ── Zone × Grade helpers ──────────────────────────────────────────────────────

def _extract_grade(tag: str) -> str:
    """'032 - Stores' → '032'; unrecognised tags return empty string."""
    t = str(tag).strip()
    if t.endswith("- Stores"):
        return t.split(" - Stores")[0].strip()
    return ""


def _store_zone_grade(store_meta: dict, all_store_meta: dict) -> tuple[str, str]:
    """Return (zone, grade) for a store, inheriting grade from ref store if needed."""
    zone  = store_meta.get("cluster", "")
    grade = _extract_grade(store_meta.get("tag", ""))
    if not grade:
        ref = store_meta.get("ref_store", "")
        grade = _extract_grade(all_store_meta.get(ref, {}).get("tag", ""))
    return zone, grade


def _build_peer_index(plan: dict) -> dict:
    """
    Pre-compute peer TY values for every SSG store × div × dept × month.
    Returns:
        {div: {dept: {ty_month: {(zone, grade): [ty_values]}}}}
    """
    idx: dict = {}
    stores = plan.get("stores", {})
    # Build metadata lookup first
    meta = {s: sd for s, sd in stores.items()}

    for store, sdata in stores.items():
        if not sdata.get("is_ssg"):
            continue
        zone, grade = _store_zone_grade(sdata, meta)
        for div, div_data in sdata.get("divisions", {}).items():
            for ty_month, month_data in div_data.get("months", {}).items():
                for dept, dinfo in month_data.get("departments", {}).items():
                    if not dinfo.get("active"):
                        continue
                    ty = dinfo.get("ty", 0.0)
                    if ty <= 0:
                        continue
                    (idx
                     .setdefault(div, {})
                     .setdefault(dept, {})
                     .setdefault(ty_month, {})
                     .setdefault((zone, grade), [])
                     .append(ty))
    return idx


def _peer_benchmark(idx: dict, div: str, dept: str, ty_month: str,
                    zone: str, grade: str) -> float | None:
    """
    col3 = (MAX + AVG) / 2 from the best-matching peer bucket.
    Falls back: zone+grade → grade-only → zone-only → all-SSG.
    Returns None if no peer data exists at all.
    """
    month_buckets: dict = idx.get(div, {}).get(dept, {}).get(ty_month, {})
    if not month_buckets:
        return None

    def _calc(vals: list) -> float:
        col1 = max(vals)
        col2 = sum(vals) / len(vals)
        return (col1 + col2) / 2.0

    # exact match
    if (zone, grade) in month_buckets:
        return _calc(month_buckets[(zone, grade)])

    # grade-only fallback
    grade_vals = [v for (z, g), vlist in month_buckets.items() if g == grade for v in vlist]
    if grade_vals:
        return _calc(grade_vals)

    # zone-only fallback
    zone_vals = [v for (z, g), vlist in month_buckets.items() if z == zone for v in vlist]
    if zone_vals:
        return _calc(zone_vals)

    # all-SSG fallback
    all_vals = [v for vlist in month_buckets.values() for v in vlist]
    return _calc(all_vals) if all_vals else None


# ── Core logic ────────────────────────────────────────────────────────────────

def run_check(plan: dict, ly_actuals: dict) -> list:
    """
    Scan for gaps: active dept AND TY = 0.
    LY = 0 is allowed — new/recently-introduced departments with no LY history
    are a primary use-case; the peer benchmark fills them correctly.

    Division must have at least one planned dept (any_planned guard) to exclude
    stores where dept-level planning was never applied entirely.

    Fill formula:
        col1 = MAX(TY) across SSG peers with same zone × grade, dept, month
        col2 = AVG(TY) across same peer set
        col3 = (col1 + col2) / 2
        corrected_TY = (LY_this_store + col3) / 2

    Returns list of gap records (one per store × div × dept × month).
    """
    gaps = []
    active_ty_months = plan.get("meta", {}).get("ty_months_active", [])
    peer_idx = _build_peer_index(plan)
    all_meta  = plan.get("stores", {})

    for store, sdata in plan.get("stores", {}).items():
        is_ssg = sdata.get("is_ssg", False)
        zone, grade = _store_zone_grade(sdata, all_meta)

        for div, div_data in sdata.get("divisions", {}).items():
            for ty_month, month_data in div_data.get("months", {}).items():
                if ty_month not in active_ty_months:
                    continue
                ly_month = MONTH_PAIR.get(ty_month)
                if not ly_month:
                    continue
                depts_plan = month_data.get("departments", {})
                active_depts = {d: info for d, info in depts_plan.items() if info.get("active")}

                # Skip stores/divisions where dept-level planning was never applied.
                any_planned = any(info.get("ty", 0.0) > 0 for info in active_depts.values())
                if not any_planned:
                    continue

                for dept, dinfo in active_depts.items():
                    ty = dinfo.get("ty", 0.0)
                    if ty > 0:
                        continue  # already planned

                    # LY actual for this specific store × dept × ly_month
                    ly = ly_actuals.get(store, {}).get(div, {}).get(dept, {}).get(ly_month, 0.0)

                    # Zone × grade benchmark
                    col3 = _peer_benchmark(peer_idx, div, dept, ty_month, zone, grade)
                    if col3 is None:
                        # No peer data at all — skip (can't compute a meaningful value)
                        continue

                    corrected_ty = round((ly + col3) / 2.0, 4)

                    # Determine which fallback tier was used for the method label
                    month_buckets = peer_idx.get(div, {}).get(dept, {}).get(ty_month, {})
                    if (zone, grade) in month_buckets:
                        method_label = f"Zone×Grade ({zone} / {grade})"
                    elif any(g == grade for (z, g) in month_buckets):
                        method_label = f"Grade fallback ({grade})"
                    elif any(z == zone for (z, g) in month_buckets):
                        method_label = f"Zone fallback ({zone})"
                    else:
                        method_label = "All-SSG fallback"

                    gaps.append({
                        "store":        store,
                        "is_ssg":       is_ssg,
                        "zone":         zone,
                        "grade":        grade,
                        "division":     div,
                        "department":   dept,
                        "ty_month":     ty_month,
                        "ly_month":     ly_month,
                        "ly":           round(ly, 4),
                        "original_ty":  0.0,
                        "corrected_ty": corrected_ty,
                        "col3_benchmark": round(col3, 4),
                        "method":       method_label,
                    })

    return gaps


def _avg_division_growth(growth_matrix: dict, div: str, ty_month: str) -> float:
    """Average growth % across all depts in a division for a month. Fallback 100.0."""
    dept_growths = growth_matrix.get(div, {})
    if not dept_growths:
        return 100.0
    p1_key = f"{ty_month} P1"
    p2_key = f"{ty_month} P2"
    vals = []
    for dg in dept_growths.values():
        p1 = float(dg.get(p1_key, 100.0))
        p2 = float(dg.get(p2_key, 100.0))
        vals.append((p1 + p2) / 2.0)
    return sum(vals) / len(vals) if vals else 100.0


def apply_corrections(plan: dict, gaps: list) -> dict:
    """Patches TY values in-place for all gap records. Recalculates cont_pct."""
    result = copy.deepcopy(plan)

    for gap in gaps:
        store = gap["store"]
        div   = gap["division"]
        dept  = gap["department"]
        month = gap["ty_month"]
        ty    = gap["corrected_ty"]

        try:
            depts = result["stores"][store]["divisions"][div]["months"][month]["departments"]
            if dept in depts:
                depts[dept]["ty"] = ty
                depts[dept]["ty_p1"] = round(ty / 2.0, 4)
                depts[dept]["ty_p2"] = round(ty / 2.0, 4)
        except (KeyError, TypeError):
            pass

    # Recalculate div_total_ty and cont_pct for ALL store × div × month combos
    # (not just affected ones — ensures cont_pct sums to 100% everywhere)
    for store, sdata in result.get("stores", {}).items():
        if not sdata.get("is_ssg"):
            continue
        for div, div_data in sdata.get("divisions", {}).items():
            for month, month_data in div_data.get("months", {}).items():
                depts = month_data.get("departments", {})
                total = sum(d.get("ty", 0.0) for d in depts.values() if d.get("active"))
                month_data["div_total_ty"] = round(total, 4)
                month_data["div_total_p1"] = round(sum(d.get("ty_p1", d.get("ty",0)/2) for d in depts.values() if d.get("active")), 4)
                month_data["div_total_p2"] = round(sum(d.get("ty_p2", d.get("ty",0)/2) for d in depts.values() if d.get("active")), 4)
                for dinfo in depts.values():
                    if dinfo.get("active"):
                        dinfo["cont_pct"] = round(dinfo.get("ty", 0.0) / total * 100, 4) if total > 0 else 0.0

    return result


def apply_nso_reapportionment(corrected_plan: dict, ly_actuals: dict,
                               growth_matrix: dict) -> tuple[dict, int]:
    """
    After SSG gaps are filled and SSG cont% is fully recalculated, propagate the
    updated cont% to every NSO store that references an SSG store.

    For each NSO store × div × month:
        1. div_total_ty from plan (or recomputed from dept actuals × div_growth if 0)
        2. Each active dept: ty = div_total_ty × ref_SSG_cont_pct
        3. Recalculate NSO div_total_ty and cont_pct

    Returns (updated_plan, nso_stores_updated_count).
    """
    result = corrected_plan  # already deep-copied in apply_corrections
    stores = result.get("stores", {})
    active_ty_months = result.get("meta", {}).get("ty_months_active", [])
    updated_stores = 0

    for store, sdata in stores.items():
        if sdata.get("is_ssg"):
            continue

        ref_code = sdata.get("ref_store", "")
        ref_data = stores.get(ref_code)
        if not ref_data or not ref_data.get("is_ssg"):
            continue

        store_touched = False
        for div, div_data in sdata.get("divisions", {}).items():
            ref_div = ref_data.get("divisions", {}).get(div, {})

            for ty_month, month_data in div_data.get("months", {}).items():
                if ty_month not in active_ty_months:
                    continue
                ly_month = MONTH_PAIR.get(ty_month)
                if not ly_month:
                    continue

                # Get div-level AOP for this NSO store
                div_total_ty = month_data.get("div_total_ty", 0.0)
                if div_total_ty <= 0:
                    # Recompute: sum LY dept actuals × avg div growth
                    store_div_acts = ly_actuals.get(store, {}).get(div, {})
                    ly_div_sum = sum(
                        v.get(ly_month, 0.0) for v in store_div_acts.values()
                        if isinstance(v, dict)
                    )
                    if ly_div_sum > 0:
                        div_growth = _avg_division_growth(growth_matrix, div, ty_month)
                        div_total_ty = round(ly_div_sum * div_growth / 100.0, 4)

                if div_total_ty <= 0:
                    continue

                ref_month = ref_div.get("months", {}).get(ty_month, {})
                ref_depts = ref_month.get("departments", {})
                depts = month_data.get("departments", {})

                new_total = 0.0
                for dept, dinfo in depts.items():
                    if not dinfo.get("active"):
                        continue
                    ref_dept = ref_depts.get(dept, {})
                    cont_pct = ref_dept.get("cont_pct", 0.0)
                    new_ty = round(div_total_ty * cont_pct / 100.0, 4)
                    dinfo["ty"]       = new_ty
                    dinfo["cont_pct"] = round(cont_pct, 4)
                    new_total        += new_ty

                month_data["div_total_ty"] = round(new_total, 4)
                store_touched = True

        if store_touched:
            updated_stores += 1

    return result, updated_stores


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/check")
def check_gaps():
    """
    Scans the current plan for active-dept zero-TY gaps.
    Returns gap list + summary statistics.
    """
    plan = _load_source_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan found. Complete New Depts → Save & Apply first.")

    ly_actuals = load_actuals()

    gaps = run_check(plan, ly_actuals)

    # Summary
    from collections import Counter
    div_counts = Counter(g["division"] for g in gaps)
    store_counts = len({g["store"] for g in gaps})

    return {
        "gap_count": len(gaps),
        "stores_affected": store_counts,
        "by_division": dict(div_counts),
        "total_ly_at_risk": round(sum(g["ly"] for g in gaps), 2),
        "total_corrected_ty": round(sum(g["corrected_ty"] for g in gaps), 2),
        "gaps": gaps,
    }


@router.post("/apply")
def apply_base_correction():
    """
    Runs the full check, applies all corrections, writes base_corrected_plan.json
    and base_correction_review.json.
    """
    plan = _load_source_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan found.")

    ly_actuals    = load_actuals()
    growth_matrix = _load_growth_matrix()

    # Step 1: fill SSG gaps, recalculate SSG cont%
    gaps = run_check(plan, ly_actuals)
    corrected_plan = apply_corrections(plan, gaps)

    # Step 2: propagate updated SSG cont% to NSO stores
    corrected_plan, nso_updated = apply_nso_reapportionment(
        corrected_plan, ly_actuals, growth_matrix
    )

    with open(BASE_PLAN_PATH, "w") as f:
        json.dump(corrected_plan, f)

    with open(REVIEW_PATH, "w") as f:
        json.dump({"gaps": gaps, "applied": True, "nso_stores_updated": nso_updated}, f, indent=2)

    from collections import Counter
    div_counts = Counter(g["division"] for g in gaps)

    return {
        "ok":                   True,
        "gap_count":            len(gaps),
        "stores_affected":      len({g["store"] for g in gaps}),
        "nso_stores_updated":   nso_updated,
        "by_division":          dict(div_counts),
        "total_ly_at_risk":     round(sum(g["ly"] for g in gaps), 2),
        "total_corrected_ty":   round(sum(g["corrected_ty"] for g in gaps), 2),
        "review":               gaps,
    }


@router.get("/review")
def get_review():
    """Returns the last applied correction review sheet."""
    if not os.path.exists(REVIEW_PATH):
        raise HTTPException(status_code=404, detail="No base correction has been applied yet.")
    with open(REVIEW_PATH) as f:
        data = json.load(f)
    return data


@router.get("/export")
def export_review():
    """Downloads the review sheet as Excel."""
    if not os.path.exists(REVIEW_PATH):
        raise HTTPException(status_code=404, detail="No review data. Run Apply first.")
    with open(REVIEW_PATH) as f:
        data = json.load(f)

    gaps = data.get("gaps", [])
    if not gaps:
        raise HTTPException(status_code=404, detail="No corrections were made.")

    df = pd.DataFrame(gaps)
    df = df.rename(columns={
        "store": "Store",
        "is_ssg": "Type",
        "zone": "Zone",
        "grade": "Grade",
        "division": "Division",
        "department": "Department",
        "ty_month": "TY Month",
        "ly_month": "LY Month",
        "ly": "LY Actuals (₹L)",
        "original_ty": "Original TY Plan",
        "col3_benchmark": "Zone×Grade Benchmark (₹L)",
        "corrected_ty": "Corrected TY Plan (₹L)",
        "method": "Peer Match Method",
    })
    df["Type"] = df["Type"].map({True: "SSG", False: "Non-SSG"})
    # Ensure column order
    col_order = ["Store","Type","Zone","Grade","Division","Department","TY Month","LY Month",
                 "LY Actuals (₹L)","Original TY Plan","Zone×Grade Benchmark (₹L)","Corrected TY Plan (₹L)","Peer Match Method"]
    df = df[[c for c in col_order if c in df.columns]]
    df = df.sort_values(["Division", "Store", "Department", "TY Month"])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Base Correction Review", index=False)
        # Summary sheet
        summary = pd.DataFrame([{
            "Total Gaps Fixed": len(gaps),
            "Stores Affected": len({g["store"] for g in gaps}),
            "Total LY at Risk (₹L)": round(sum(g["ly"] for g in gaps), 2),
            "Total Corrected TY (₹L)": round(sum(g["corrected_ty"] for g in gaps), 2),
        }])
        summary.to_excel(writer, sheet_name="Summary", index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=base_correction_review.xlsx"},
    )
