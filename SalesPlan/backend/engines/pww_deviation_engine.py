"""
PW/W Deviation Engine
======================
Phase 1: Compare PPO cont % (dept × MRP) vs LY SSG actuals for a cumulative month block (MAMJ, SOND, …).
The block is AUTO-DETECTED from the month columns of the imported PPO Cont % file (user, 2026-09-29: "instead of
the manual search bar ... auto detect from the file imported so that there is sanctity between modules") -
template DEPARTMENT | ARTICLE NAME | FINAL MRP | <TY month cols, e.g. Mar'27 Apr'27 May'27 Jun'27>. SOR
Deviation detects its months the same way (month_label / detect_block below).

Deviation formula:
  block_cont_pct = dept_block_ly_ssg / div_block_ly_ssg × 100
  if block_cont_pct < 2.5 → deviation = 0
  else → deviation = dept_block_ly_ssg / (ppo_dept_cont_pct / 100)
          where ppo_dept_cont_pct = dept's TY plan cont% (from final_dept_plan)
          averaged across the TY months that correspond to the LY block.

Block shorthands (LY month lists):
  MAMJ  → Mar'26 Apr'26 May'26 Jun'26
  AMJ   → Apr'26 May'26 Jun'26
  SOND  → Sep'26 Oct'26 Nov'26 Dec'26
  OND   → Oct'26 Nov'26 Dec'26
  JFM   → Jan'27 Feb'27 Mar'27
  (extend as needed)
"""

from fastapi import APIRouter, HTTPException, Query
import os, json, datetime
import pandas as pd
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from actuals_manager import load_actuals, locked_ly_months
from store_master import load_store_master as _universal_store_master, is_ssg as _universal_is_ssg

router = APIRouter()

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE            = os.path.dirname(__file__)
PWW_SOURCE_DIR   = r"C:\Users\A9820\Documents\CLaude - New Projects\SalesPlan\PW-W Deviation"
PWW_SOURCE_NAME  = "PPO Cont %.xlsx"
PWW_SOURCE_PATH  = os.path.join(PWW_SOURCE_DIR, PWW_SOURCE_NAME)
PWW_PPO_PATH     = os.path.join(_BASE, "..", "pww_ppo_data.json")
PWW_RESULT_PATH  = os.path.join(_BASE, "..", "pww_phase1_result.json")
PWW_P2_PATH      = os.path.join(_BASE, "..", "pww_phase2_result.json")
PWW_REAPP_PATH   = os.path.join(_BASE, "..", "pww_reapportion_result.json")
PWW_META_PATH    = os.path.join(_BASE, "..", "pww_ppo_meta.json")   # block / months detected at sync
FINAL_PLAN_PATH  = os.path.join(_BASE, "..", "final_dept_plan.json")

# ── Block definitions — all consecutive permutations ──────────────────────────
_LY_MONTHS = ["Mar'26","Apr'26","May'26","Jun'26","Jul'26","Aug'26",
               "Sep'26","Oct'26","Nov'26","Dec'26","Jan'27","Feb'27","Mar'27"]
_TY_MONTHS = ["Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
               "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"]

# First-letter initials for each LY month position
_INITIALS = ["M","A","M","J","J","A","S","O","N","D","J","F","M"]

def _build_blocks() -> dict:
    """
    Generate all 91 consecutive month permutations.
    Key = initials string; disambiguate duplicates by appending _2, _3 etc.
    """
    seen: dict[str, int] = {}
    blocks: dict[str, dict] = {}
    n = len(_LY_MONTHS)
    for start in range(n):
        for end in range(start, n):
            initials = "".join(_INITIALS[start:end + 1])
            count = seen.get(initials, 0) + 1
            seen[initials] = count
            key = initials if count == 1 else f"{initials}_{count}"
            ly_slice = _LY_MONTHS[start:end + 1]
            ty_slice = _TY_MONTHS[start:end + 1]
            blocks[key] = {
                "ly_months": ly_slice,
                "ty_months": ty_slice,
                "label": f"{initials}  {ly_slice[0].split(chr(39))[0]}–{ly_slice[-1]}",
                "months_count": end - start + 1,
            }
    # Also expose FULL as an alias
    blocks["FULL"] = {
        "ly_months": _LY_MONTHS,
        "ty_months": _TY_MONTHS,
        "label": f"FULL  Mar'26–Mar'27",
        "months_count": len(_LY_MONTHS),
    }
    return blocks

BLOCKS = _build_blocks()

_MON = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def month_label(header):
    """A file header naming a month -> "Mar'27" (Excel date, "Mar'27", "Mar-27", "Mar 2027", "2027-03", ...),
    else None. Shared with SOR Deviation so both modules read months the same way."""
    import re
    if isinstance(header, (datetime.date, datetime.datetime, pd.Timestamp)):
        y, m = header.year, header.month
    else:
        h = str(header).strip().upper().replace("’", "'")
        mt = re.fullmatch(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?(?: 00:00:00)?", h)
        if mt:
            y, m = int(mt[1]), int(mt[2])
        else:
            mt = re.fullmatch(r"([A-Z]{3})[A-Z]*[\s'\-_/]*(\d{2}|\d{4})", h)
            if not mt or mt[1] not in _MON:
                return None
            m, y = _MON[mt[1]], int(mt[2]) % 100 + 2000
    if not 1 <= m <= 12:
        return None
    return f"{datetime.date(2000, m, 1).strftime('%b')}'{y % 100:02d}"


def detect_block(ty_months: list) -> tuple:
    """TY month labels found in a file -> (block key, block def). They must be consecutive plan months."""
    idx = sorted(_TY_MONTHS.index(m) for m in set(ty_months) if m in _TY_MONTHS)
    if not idx or len(idx) != len(set(ty_months)):
        raise ValueError(f"Months {ty_months} are not all plan months ({_TY_MONTHS[0]}-{_TY_MONTHS[-1]})")
    if idx != list(range(idx[0], idx[-1] + 1)):
        raise ValueError(f"Months {ty_months} are not consecutive")
    want = _TY_MONTHS[idx[0]:idx[-1] + 1]
    key = next(k for k, v in BLOCKS.items() if v["ty_months"] == want)
    return key, BLOCKS[key]


def _load_meta() -> dict:
    if os.path.exists(PWW_META_PATH):
        with open(PWW_META_PATH) as f:
            return json.load(f)
    return {}

def _ly_to_ty(ly_month: str) -> str:
    idx = _LY_MONTHS.index(ly_month) if ly_month in _LY_MONTHS else -1
    return _TY_MONTHS[idx] if idx >= 0 else ly_month

DEVIATION_THRESHOLD = 2.5  # dept block cont% below this → deviation zeroed out

# Division prefix map (must match dept_sales_engine)
_PREFIX_DIV = [
    ("KBW_", "KIDS"), ("KGW_", "KIDS"), ("KIW_", "KIDS"),
    ("KB_",  "KIDS"), ("KG_",  "KIDS"), ("KI_",  "KIDS"),
    ("LWW_", "LADIES"), ("LW_", "LADIES"), ("L_",  "LADIES"), ("LY_", "LADIES"),
    ("MSE_", "MENS"), ("ME_",  "MENS"), ("MW_", "MENS"), ("M_", "MENS"),
    ("GM_",  "GM"),   ("RT_",  "RETAIL"),
]

def _infer_div(dept: str) -> str:
    u = dept.strip().upper()
    for prefix, div in _PREFIX_DIV:
        if u.startswith(prefix):
            return div
    return "UNKNOWN"

def _is_ssg(tag: str, store: str = "") -> bool:
    return _universal_is_ssg(tag, store)

def _load_store_master() -> list[dict]:
    return list(_universal_store_master())

def _load_ppo() -> dict:
    """Returns {dept: [{mrp, article_name, ppo_cont_pct}]}"""
    if os.path.exists(PWW_PPO_PATH):
        with open(PWW_PPO_PATH) as f:
            return json.load(f)
    return {}

def _save_ppo(data: dict):
    with open(PWW_PPO_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── Sync endpoint ──────────────────────────────────────────────────────────────

@router.get("/sync-status")
def get_sync_status():
    meta = _load_meta()
    if not os.path.exists(PWW_SOURCE_PATH):
        return {"file_found": False, "file_date": None, "size_kb": None, "path": PWW_SOURCE_PATH, "block": meta.get("block")}
    st = os.stat(PWW_SOURCE_PATH)
    return {
        "file_found": True,
        "file_date":  datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "size_kb":    round(st.st_size / 1024, 1),
        "path":       PWW_SOURCE_PATH,
        "block":      meta.get("block"),
        "ty_months":  meta.get("ty_months"),
        "ly_months":  meta.get("ly_months"),
    }


@router.post("/sync")
def sync_ppo():
    """Parse PPO Cont % file and save structured data."""
    if not os.path.exists(PWW_SOURCE_PATH):
        raise HTTPException(status_code=404, detail=f"File not found: {PWW_SOURCE_PATH}")

    try:
        df = pd.read_excel(PWW_SOURCE_PATH, header=0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read file: {e}")

    month_cols = {c: month_label(c) for c in df.columns if month_label(c)}   # original header -> "Mar'27"
    df.columns = [c if c in month_cols else str(c).strip().upper() for c in df.columns]

    dept_col    = next((c for c in df.columns if c not in month_cols and "DEPARTMENT" in c), None)
    article_col = next((c for c in df.columns if c not in month_cols and "ARTICLE" in c), None)
    mrp_col     = next((c for c in df.columns if c not in month_cols and "MRP" in c), None)

    if not all([dept_col, mrp_col]):
        raise HTTPException(status_code=422, detail=f"Missing DEPARTMENT / FINAL MRP columns. Found: {list(df.columns)}")
    if not month_cols:
        raise HTTPException(status_code=422, detail=(
            "No month columns - the block is read from the file. Use DEPARTMENT | ARTICLE NAME | FINAL MRP | "
            "one column per TY month (e.g. Mar'27, Apr'27, May'27, Jun'27) holding the PPO cont %."))
    try:
        block_key, block_def = detect_block(list(month_cols.values()))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    ppo: dict[str, list] = {}
    for _, row in df.iterrows():
        dept = str(row[dept_col]).strip() if pd.notna(row[dept_col]) else ""
        if not dept or dept.lower() == "nan":
            continue
        mrp  = row[mrp_col]
        art  = str(row[article_col]).strip() if article_col and pd.notna(row[article_col]) else ""
        by_month = {lbl: round(float(row[c]) * 100 if pd.notna(row[c]) else 0.0, 4)   # stored as %
                    for c, lbl in month_cols.items()}
        if dept not in ppo:
            ppo[dept] = []
        ppo[dept].append({
            "mrp":          float(mrp) if pd.notna(mrp) else 0.0,
            "article_name": art,
            "ppo_cont_pct": round(sum(by_month.values()) / len(by_month), 4),   # block average
            "months":       by_month,                                           # TY month -> % (Phase 2)
        })

    _save_ppo(ppo)
    st = os.stat(PWW_SOURCE_PATH)
    meta = {"block": block_key, "ty_months": block_def["ty_months"], "ly_months": block_def["ly_months"],
            "file_date": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")}
    with open(PWW_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
    return {
        "ok":        True,
        "file_date": meta["file_date"],
        "depts":     len(ppo),
        "rows":      sum(len(v) for v in ppo.values()),
        "block":     block_key,
        "ty_months": block_def["ty_months"],
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_ty_plan() -> dict:
    """Load final_dept_plan (or fall back to base plan) for PPO cont% reference."""
    for path in [
        FINAL_PLAN_PATH,
        os.path.join(_BASE, "..", "attr_corrected_plan.json"),
        os.path.join(_BASE, "..", "base_corrected_plan.json"),
    ]:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {}

def _ppo_dept_cont_pct(ty_plan: dict, dept: str, div: str, ty_months: list[str]) -> float:
    """
    Average TY cont_pct for a dept across the given TY months (SSG stores only).
    Falls back to 0 if plan is absent.
    """
    total_cont = 0.0
    count = 0
    for store_data in ty_plan.get("stores", {}).values():
        for m in ty_months:
            dept_data = (
                store_data.get("divisions", {})
                .get(div, {})
                .get("months", {})
                .get(m, {})
                .get("departments", {})
                .get(dept)
            )
            if dept_data:
                total_cont += dept_data.get("cont_pct", 0) or 0
                count += 1
    return round(total_cont / count, 4) if count else 0.0


# ── Phase 1 + Deviation ────────────────────────────────────────────────────────

@router.get("/run-phase1")
def run_phase1(block: str | None = Query(default=None, description="Omit: the block detected from the PPO file")):
    """
    Phase 1: LY SSG actuals vs PPO cont% for the specified block.

    Deviation formula:
      block_cont_pct = dept_block_ly / div_block_ly × 100
      if block_cont_pct < 2.5 → deviation = 0
      else → deviation = dept_block_ly / (ppo_dept_cont_pct / 100)
              where ppo_dept_cont_pct = dept TY plan cont% averaged over block TY months
    """
    ppo = _load_ppo()
    if not ppo:
        raise HTTPException(status_code=404, detail="No PPO data — run sync first")

    file_block = _load_meta().get("block")
    if not file_block:
        raise HTTPException(status_code=404, detail="No block detected yet - sync the PPO Cont % file first")
    block_key = (block or file_block).strip().upper()
    if block_key != file_block:   # the run always follows the imported file
        raise HTTPException(status_code=422, detail=f"The PPO file is for block {file_block}, not {block_key}")
    block_def = BLOCKS[block_key]
    ly_block_months = block_def["ly_months"]
    ty_block_months = block_def["ty_months"]

    # Filter to only locked months present in the block
    locked = set(locked_ly_months())
    active_ly_months = [m for m in ly_block_months if m in locked]
    if not active_ly_months:
        raise HTTPException(
            status_code=422,
            detail=f"No locked actuals for block '{block_key}'. Locked: {sorted(locked)}"
        )
    active_ty_months = [_ly_to_ty(m) for m in active_ly_months]

    # SSG stores
    store_master = _load_store_master()
    ssg_stores = {r["Store"] for r in store_master if _is_ssg(r["Tag"], r["Store"])}

    # LY actuals — SSG only, block months only
    actuals = load_actuals()
    div_dept_ly: dict[str, dict[str, float]] = {}
    for store, divs in actuals.items():
        if store not in ssg_stores:
            continue
        for div, depts in divs.items():
            if div not in div_dept_ly:
                div_dept_ly[div] = {}
            for dept, months in depts.items():
                val = sum(months.get(m, 0) or 0 for m in active_ly_months)
                div_dept_ly[div][dept] = div_dept_ly[div].get(dept, 0) + val

    div_block_total: dict[str, float] = {
        div: sum(d.values()) for div, d in div_dept_ly.items()
    }

    # TY plan for PPO cont% reference
    ty_plan = _load_ty_plan()

    # Build result
    divisions: dict[str, dict] = {}
    unmatched: list[str] = []

    for dept, mrp_rows in ppo.items():
        div         = _infer_div(dept)
        dept_ly     = div_dept_ly.get(div, {}).get(dept, 0.0)
        div_ly      = div_block_total.get(div, 0.0)
        block_cont  = round(dept_ly / div_ly * 100, 4) if div_ly else 0.0

        if dept_ly == 0:
            unmatched.append(dept)

        # Deviation
        ppo_cont = _ppo_dept_cont_pct(ty_plan, dept, div, active_ty_months)
        if block_cont < DEVIATION_THRESHOLD:
            deviation       = 0.0
            deviation_ratio = 0.0
            deviation_flag  = "below_threshold"
        else:
            if ppo_cont > 0:
                deviation       = round(dept_ly / (ppo_cont / 100), 2)
                deviation_ratio = round(block_cont / ppo_cont, 6)
            else:
                deviation       = 0.0
                deviation_ratio = 0.0
            deviation_flag = "computed" if ppo_cont > 0 else "no_plan"

        if div not in divisions:
            divisions[div] = {
                "ly_div_block_total": round(div_ly, 2),
                "depts": {},
            }

        divisions[div]["depts"][dept] = {
            "ly_block_sales":    round(dept_ly, 2),
            "block_cont_pct":    block_cont,
            "deviation":         deviation,
            "deviation_ratio":   deviation_ratio,
            "ppo_dept_cont_pct": round(ppo_cont, 4),
            "deviation_flag":    deviation_flag,
            "ppo_mrp_breakdown": sorted(mrp_rows, key=lambda r: r["mrp"]),
        }

    result = {
        "run_date":          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "block":             block_key,
        "ly_months_used":    active_ly_months,
        "ty_months_ref":     active_ty_months,
        "ssg_stores":        sorted(ssg_stores),
        "threshold_pct":     DEVIATION_THRESHOLD,
        "total_depts":       len(ppo),
        "unmatched_depts":   unmatched,
        "divisions":         divisions,
    }

    with open(PWW_RESULT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    return result


@router.get("/phase1-result")
def get_phase1_result():
    if os.path.exists(PWW_RESULT_PATH):
        with open(PWW_RESULT_PATH) as f:
            return json.load(f)
    return run_phase1()


@router.get("/status")
def get_status():
    ppo = _load_ppo()
    has_p1 = os.path.exists(PWW_RESULT_PATH)
    has_p2 = os.path.exists(PWW_P2_PATH)
    p1_run_date = None
    p2_run_date = None
    if has_p1:
        with open(PWW_RESULT_PATH) as f:
            p1_run_date = json.load(f).get("run_date")
    has_reapp = os.path.exists(PWW_REAPP_PATH)
    reapp_run_date = None
    if has_p2:
        with open(PWW_P2_PATH) as f:
            p2_run_date = json.load(f).get("run_date")
    if has_reapp:
        with open(PWW_REAPP_PATH) as f:
            reapp_run_date = json.load(f).get("run_date")
    meta = _load_meta()
    return {
        "ppo_loaded":      bool(ppo) and bool(meta.get("block")),
        "ppo_depts":       len(ppo),
        "block":           meta.get("block"),
        "ty_months":       meta.get("ty_months"),
        "ly_months":       meta.get("ly_months"),
        "phase1_run":      has_p1,
        "run_date":        p1_run_date,
        "phase2_run":      has_p2,
        "p2_run_date":     p2_run_date,
        "reapp_run":       has_reapp,
        "reapp_run_date":  reapp_run_date,
    }


# ── Phase 2 ────────────────────────────────────────────────────────────────────

@router.get("/run-phase2")
def run_phase2(block: str | None = Query(default=None)):
    """
    Phase 2: Cluster × Department × Merged MRP × Month final contribution %.

    For each Month × Cluster × Dept × MRP:
      LY_dept_cluster_month_cont% = cluster_dept_ly_month / cluster_div_ly_month × 100
      LY_mrp_cluster_month_cont%  = LY_dept_cluster_month_cont% × (PPO_mrp_pct / 100)
      Adjusted                    = LY_mrp_cluster_month_cont% × deviation_ratio

    Guardrails vs PPO_mrp_div_cont% = ppo_dept_cont_pct × (PPO_mrp_pct / 100):
      ≤ 0         → Final = PPO_mrp_div_cont%          rule = "ppo"
      < PPO × 50% → Final = PPO_mrp_div_cont% × 50%   rule = "floor_50"
      > PPO × 150%→ Final = PPO_mrp_div_cont% × 150%  rule = "cap_150"
      else        → Final = Adjusted                   rule = "adjusted"
    """
    if not os.path.exists(PWW_RESULT_PATH):
        raise HTTPException(status_code=404, detail="Phase 1 not run yet — run Phase 1 first")
    with open(PWW_RESULT_PATH) as f:
        p1 = json.load(f)
    block_key = (block or p1["block"]).strip().upper()

    if p1["block"] != block_key:
        raise HTTPException(
            status_code=422,
            detail=f"Phase 1 was run for block '{p1['block']}', not '{block_key}'. Re-run Phase 1 with this block first."
        )

    ppo = _load_ppo()
    if not ppo:
        raise HTTPException(status_code=404, detail="No PPO data — run sync first")

    # Store master with cluster
    store_master  = _load_store_master()
    ssg_cluster   = {r["Store"]: r["Cluster"] for r in store_master if _is_ssg(r["Tag"], r["Store"])}
    clusters      = sorted(set(ssg_cluster.values()))

    # LY actuals
    actuals         = load_actuals()
    active_ly_months = p1["ly_months_used"]

    # Phase 1 deviation data per dept
    p1_devs: dict[str, dict] = {}
    for div_data in p1["divisions"].values():
        for dept, dd in div_data["depts"].items():
            p1_devs[dept] = {
                "deviation_ratio":   dd.get("deviation_ratio", 0.0),
                "ppo_dept_cont_pct": dd.get("ppo_dept_cont_pct", 0.0),
                "deviation_flag":    dd.get("deviation_flag", "no_plan"),
            }

    # Aggregate: cluster → div → dept → month → LY sales (SSG only)
    cluster_sales: dict[str, dict] = {}
    for store, divs in actuals.items():
        cl = ssg_cluster.get(store)
        if not cl:
            continue
        cc = cluster_sales.setdefault(cl, {})
        for div, depts in divs.items():
            dd_map = cc.setdefault(div, {})
            for dept, months in depts.items():
                dm = dd_map.setdefault(dept, {})
                for m in active_ly_months:
                    dm[m] = dm.get(m, 0.0) + (months.get(m) or 0)

    # Div totals per cluster per month
    cluster_div_total: dict[str, dict] = {}
    for cl, divs in cluster_sales.items():
        cluster_div_total[cl] = {}
        for div, depts in divs.items():
            cluster_div_total[cl][div] = {}
            for m in active_ly_months:
                cluster_div_total[cl][div][m] = sum(depts[d].get(m, 0) for d in depts)

    # Build result: month → cluster → dept → {ly_dept_cont_pct, deviation_ratio, mrp_rows:{mrp_key→{…}}}
    result: dict = {}
    for m in active_ly_months:
        result[m] = {}
        for cl in clusters:
            result[m][cl] = {}
            for dept, mrp_rows in ppo.items():
                div = _infer_div(dept)

                cl_dept_ly  = cluster_sales.get(cl, {}).get(div, {}).get(dept, {}).get(m, 0.0)
                cl_div_ly   = cluster_div_total.get(cl, {}).get(div, {}).get(m, 0.0)
                ly_dept_cont = round(cl_dept_ly / cl_div_ly * 100, 6) if cl_div_ly > 0 else 0.0

                p1d = p1_devs.get(dept, {})
                dev_ratio       = p1d.get("deviation_ratio", 0.0)
                ppo_dept_cont   = p1d.get("ppo_dept_cont_pct", 0.0)
                dev_flag        = p1d.get("deviation_flag", "no_plan")

                mrp_detail: dict = {}
                for row in mrp_rows:
                    mrp        = row["mrp"]
                    mrp_key    = str(int(mrp)) if mrp == int(mrp) else str(mrp)
                    # within-dept MRP mix, already as % - the month's own column when the file has one
                    ppo_mrp_pct = (row.get("months") or {}).get(_ly_to_ty(m), row["ppo_cont_pct"])
                    art         = row.get("article_name", "")

                    # LY MRP cont% at div level for this cluster/month
                    ly_mrp_cont = round(ly_dept_cont * (ppo_mrp_pct / 100), 6)

                    # PPO MRP cont% at div level (guardrail reference)
                    ppo_mrp_div = round(ppo_dept_cont * (ppo_mrp_pct / 100), 6)

                    # Adjusted
                    adjusted = round(ly_mrp_cont * dev_ratio, 6)

                    # Guardrails
                    if adjusted <= 0 or dev_flag in ("below_threshold", "no_plan"):
                        final = ppo_mrp_div
                        rule  = f"ppo_{dev_flag}" if dev_flag != "computed" else "ppo"
                    elif ppo_mrp_div > 0 and adjusted < ppo_mrp_div * 0.5:
                        final = round(ppo_mrp_div * 0.5, 6)
                        rule  = "floor_50"
                    elif ppo_mrp_div > 0 and adjusted > ppo_mrp_div * 1.5:
                        final = round(ppo_mrp_div * 1.5, 6)
                        rule  = "cap_150"
                    else:
                        final = adjusted
                        rule  = "adjusted"

                    mrp_detail[mrp_key] = {
                        "article_name":     art,
                        "mrp":              mrp,
                        "ppo_mrp_pct":      round(ppo_mrp_pct, 4),
                        "ly_mrp_cont_pct":  round(ly_mrp_cont, 4),
                        "adjusted_cont_pct":round(adjusted, 4),
                        "ppo_div_cont_pct": round(ppo_mrp_div, 4),
                        "final_cont_pct":   round(final, 4),
                        "rule":             rule,
                    }

                result[m][cl][dept] = {
                    "div":             div,
                    "ly_dept_cont_pct":round(ly_dept_cont, 4),
                    "deviation_ratio": round(dev_ratio, 4),
                    "deviation_flag":  dev_flag,
                    "mrp_rows":        mrp_detail,
                }

    output = {
        "run_date":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "block":     block_key,
        "ly_months": active_ly_months,
        "clusters":  clusters,
        "result":    result,
    }
    with open(PWW_P2_PATH, "w") as f:
        json.dump(output, f, indent=2)

    return {
        "ok":       True,
        "block":    block_key,
        "clusters": clusters,
        "months":   active_ly_months,
        "total_depts": len(ppo),
    }


@router.get("/phase2-result")
def get_phase2_result():
    if not os.path.exists(PWW_P2_PATH):
        raise HTTPException(status_code=404, detail="Phase 2 not run yet")
    with open(PWW_P2_PATH) as f:
        return json.load(f)


# ── Reapportionment ────────────────────────────────────────────────────────────

@router.get("/reapportion")
def reapportion():
    """
    Reapportion Phase 2 Final Contribution % at Cluster × Department level.

    For each Cluster × Department:
      1. Sum Final% across all block months per MRP → block-level MRP total
      2. Sum across all MRPs → dept block total
      3. Normalise each MRP → reapportioned_pct = mrp_block_total / dept_block_total × 100

    Output: Cluster → Department → {div, dept_block_final_pct, mrp_rows: {mrp: {reapportioned_pct, …}}}
    reapportioned_pct values sum to 100.0 within each dept.
    """
    if not os.path.exists(PWW_P2_PATH):
        raise HTTPException(status_code=404, detail="Phase 2 not run yet — run Phase 2 first")
    with open(PWW_P2_PATH) as f:
        p2 = json.load(f)

    block      = p2["block"]
    ly_months  = p2["ly_months"]
    clusters   = p2["clusters"]
    p2_result  = p2["result"]

    # cluster → dept → mrp_key → sum of final_cont_pct across months
    # cluster → dept → metadata (div, deviation_ratio, deviation_flag)
    accum: dict[str, dict[str, dict]] = {}

    for m in ly_months:
        month_data = p2_result.get(m, {})
        for cl in clusters:
            cl_data = month_data.get(cl, {})
            cl_acc  = accum.setdefault(cl, {})
            for dept, dd in cl_data.items():
                dept_acc = cl_acc.setdefault(dept, {
                    "div":            dd["div"],
                    "deviation_ratio":dd["deviation_ratio"],
                    "deviation_flag": dd["deviation_flag"],
                    "_mrp_sums":      {},
                    "_mrp_meta":      {},
                })
                for mrp_key, mr in dd["mrp_rows"].items():
                    dept_acc["_mrp_sums"][mrp_key] = (
                        dept_acc["_mrp_sums"].get(mrp_key, 0.0) + mr["final_cont_pct"]
                    )
                    if mrp_key not in dept_acc["_mrp_meta"]:
                        dept_acc["_mrp_meta"][mrp_key] = {
                            "article_name": mr["article_name"],
                            "mrp":          mr["mrp"],
                            "ppo_mrp_pct":  mr["ppo_mrp_pct"],
                        }

    # Normalise and build final result
    result: dict[str, dict] = {}
    for cl, depts in accum.items():
        result[cl] = {}
        for dept, da in depts.items():
            mrp_sums = da["_mrp_sums"]
            dept_block_total = sum(mrp_sums.values())

            mrp_rows: dict[str, dict] = {}
            for mrp_key, mrp_sum in mrp_sums.items():
                meta = da["_mrp_meta"][mrp_key]
                reapp_pct = round(mrp_sum / dept_block_total * 100, 4) if dept_block_total > 0 else 0.0
                mrp_rows[mrp_key] = {
                    "article_name":      meta["article_name"],
                    "mrp":               meta["mrp"],
                    "ppo_mrp_pct":       meta["ppo_mrp_pct"],
                    "block_final_pct":   round(mrp_sum, 4),
                    "reapportioned_pct": reapp_pct,
                }

            result[cl][dept] = {
                "div":               da["div"],
                "deviation_ratio":   da["deviation_ratio"],
                "deviation_flag":    da["deviation_flag"],
                "dept_block_final_pct": round(dept_block_total, 4),
                "mrp_rows": dict(sorted(mrp_rows.items(), key=lambda x: x[1]["mrp"])),
            }

    output = {
        "run_date":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "block":     block,
        "ly_months": ly_months,
        "clusters":  clusters,
        "result":    result,
    }
    with open(PWW_REAPP_PATH, "w") as f:
        json.dump(output, f, indent=2)

    total_depts = sum(len(v) for v in result.values())
    return {
        "ok":           True,
        "block":        block,
        "clusters":     clusters,
        "total_depts":  total_depts // len(clusters) if clusters else 0,
    }


@router.get("/reapportion-result")
def get_reapportion_result():
    if not os.path.exists(PWW_REAPP_PATH):
        raise HTTPException(status_code=404, detail="Reapportionment not run yet")
    with open(PWW_REAPP_PATH) as f:
        return json.load(f)
