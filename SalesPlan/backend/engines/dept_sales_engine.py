"""
Department Sales Plan Engine
=============================
Breaks store-division TY targets down to department level.

SSG stores  (= AOP's plan LfL, store_master.is_ssg - 148 stores on 28 Sep 2026):
    dept_TY = dept_LY × avg(P1_growth, P2_growth) / 100
    TY cont% re-derived from active dept values (sums to 100%)
    Inactive departments → TY = 0, excluded from total

Non-SSG stores (NSO, MAMJ-NSO, FY-tagged):
    TY cont% copied from their Ref Store (must be an SSG store)
    TY value = cont% × store_div_TY_total
    where store_div_TY_total = LY_div_total × avg_division_growth / 100
    LY_div_total: from "Store Actuals" sheet; falls back to summing dept actuals
    when absent/zero (fixes stores like AJL absent from the sheet).

Data required in inputs.xlsx:
    Sheet "Dept Actuals" — header row 1
    Columns: Store | Division | Department | Apr'26 | May'26 | … | Mar'27
"""

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
import io, json, os, threading, time
import pandas as pd
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from actuals_manager import (
    load_actuals, locked_ly_months, available_ty_months,
    load_store_div_actuals, actuals_source,
)
from store_master import load_store_master as _universal_store_master, is_ssg as _universal_is_ssg
from apportion import shares_pct, split
from plan_cache import save_json  # noqa: E402 - atomic JSON writes (audit 2026-10-06)

router = APIRouter()

# ── Paths ─────────────────────────────────────────────────────────────────────
_BASE     = os.path.dirname(__file__)
NEW_DEPT_MAP_PATH  = os.path.join(_BASE, "..", "new_dept_mapping.json")
FINAL_PLAN_PATH    = os.path.join(_BASE, "..", "final_dept_plan.json")


# ── Constants ─────────────────────────────────────────────────────────────────
# user, 2026-10-13: "remove divisions - gm and retail from sales plan engine" - the plan is built for these only
# (the BIS divisions); GM / RETAIL actuals still import (actuals_manager) but are no longer planned or shown
DIVISIONS = ["KIDS", "LADIES", "MENS"]

# Full plan range: Mar'27 → Mar'28 (13 months) with corresponding LY
TY_MONTHS  = ["Mar'27","Apr'27","May'27","Jun'27","Jul'27","Aug'27",
              "Sep'27","Oct'27","Nov'27","Dec'27","Jan'28","Feb'28","Mar'28"]
LY_MONTHS  = ["Mar'26","Apr'26","May'26","Jun'26","Jul'26","Aug'26",
              "Sep'26","Oct'26","Nov'26","Dec'26","Jan'27","Feb'27","Mar'27"]
MONTH_PAIR = list(zip(TY_MONTHS, LY_MONTHS))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_ssg(tag: str, store: str = "") -> bool:
    return _universal_is_ssg(tag, store)


# Store groups (user, 2026-10-14: "Clusters can have 3 sets - SSG/NSO/Others wherein NSO means stores which have names
# and are not genericly numbered. Others are the ones which will fall under the NSO-01 or MAMJ-01 category") - the AOP
# Forecaster's own placeholder prefixes (engine_v3 UNNAMED_PFX)
PLACEHOLDER_PFX = ("NS-", "AD-", "MAMJ")


def store_group(store: str, ssg: bool) -> str:
    return "SSG" if ssg else "Others" if str(store).strip().upper().startswith(PLACEHOLDER_PFX) else "NSO"


def _aop_store_plan() -> dict:
    """{STORE: {DIVISION: {TY month: Rs lakh}}} - the AOP Forecaster's store plan of the publish BIS plans on; {} if
    it can't be read (the non-SSG stores then keep the old rule: own LY x the division's average BIS growth)."""
    try:
        from engines.grain_view import _aop_by_store
        return _aop_by_store()[2] or {}
    except Exception:   # noqa: BLE001 - AOP / DB unreachable
        return {}



# ── Data Loaders ──────────────────────────────────────────────────────────────

def _load_store_master():
    """Returns [{Store, Ref Store, Cluster, Tag}] from the universal Store Master."""
    return list(_universal_store_master())


def _load_dept_actuals():
    """(store x dept LY actuals, usable LY months) - the Calendar app's reindexed department-level sales
    (actuals_manager; was actuals_store.json from a manual Excel import until 2026-09-28)."""
    return load_actuals(), locked_ly_months()


def _load_store_div_actuals():
    """Store x Division x LY month totals of the same reindexed Calendar sales (was the 'Store Actuals' sheet of
    AOP's inputs.xlsx). Returns {store: {division: {ly_month: Rs lakhs}}}."""
    return load_store_div_actuals()


def _load_new_dept_map() -> dict:
    """Returns {division: {new_dept: {ref_dept, alloc_pct}}}"""
    if os.path.exists(NEW_DEPT_MAP_PATH):
        with open(NEW_DEPT_MAP_PATH) as f:
            return json.load(f)
    return {}


def _save_new_dept_map(data: dict):
    save_json(NEW_DEPT_MAP_PATH, data, indent=2)


def apply_new_dept_adjustments(plan_result: dict, new_dept_map: dict) -> dict:
    """
    Post-calculation pass, per new dept entry {ref_dept, new_dept_pct, ref_reduction_pct}:
      new_dept_ty = ref_dept_ty x new_dept_pct / 100      (its plan IS this - its own plan is not added, 2026-10-13)
      ref_dept_ty = ref_dept_ty x (1 - ref_reduction_pct / 100)
    then every active department of the division x month is scaled by ONE factor, over all stores, back to the
    division's total before the carve (the BIS / AOP plan) - the mix is kept, and the new department stays exactly
    new_dept_pct of its reference everywhere (user, 2026-10-13: "Keep new dept cont % the same as fixed in the plan and
    reapportion on the mix and adjust the aop always it should happen automatically"; the carve used to be ADDED to
    the department's own BIS plan - 25.4% instead of 25% - and the division total moved by the carve).
    Backward-compat: old entries with only alloc_pct use it for both. Applied store-by-store, month-by-month.
    """
    if not new_dept_map:
        return plan_result

    # in place: every caller passes a fresh run_dept_plan() (a deep copy of the ~350 MB plan cost ~5 s, 2026-10-01)
    result = plan_result
    tot = lambda depts: sum(v.get("ty", 0.0) for v in depts.values() if v.get("active", True))   # noqa: E731
    # (div, month, LFL?) -> total before / after the carve. Like-for-like and other stores are put back on their own
    # totals, so the LFL stores stay exactly on the AOP plan (2026-10-13: over all stores together LADIES' LFL moved 2.4 L)
    pre, post = {}, {}

    # like-for-like stores together (they stay on the AOP division plan); every other store on its own, so it stays on
    # its own AOP store plan (2026-10-14: together, the carve moved Rs.30.85 L from the placeholder stores to the named ones)
    for store, sdata in result["stores"].items():
        grp = True if sdata.get("is_ssg") else store
        for div, entries in new_dept_map.items():
            div_data = sdata["divisions"].get(div, {})
            for ty_month, month_data in div_data.get("months", {}).items():
                depts = month_data["departments"]
                pre[(div, ty_month, grp)] = pre.get((div, ty_month, grp), 0.0) + tot(depts)
                for new_dept, cfg in entries.items():
                    ref_dept = cfg["ref_dept"]
                    # Support both old alloc_pct and new split fields
                    legacy = float(cfg.get("alloc_pct", 0))
                    new_dept_pct      = float(cfg.get("new_dept_pct",      legacy)) / 100.0
                    ref_reduction_pct = float(cfg.get("ref_reduction_pct", legacy)) / 100.0
                    if new_dept_pct == 0 and ref_reduction_pct == 0:
                        continue
                    ref_d = depts.get(ref_dept)
                    ref_ok = ref_d is not None and ref_d.get("active", True)
                    # full precision, and P1 / P2 move with TY so TY = P1 + P2 stays exact (2026-09-30)
                    ref_ty = ref_d.get("ty", 0.0) if ref_ok else 0.0
                    ref_p1 = ref_d.get("ty_p1", ref_ty / 2.0) if ref_ok else 0.0
                    ref_p2 = ref_ty - ref_p1
                    carve = {"ty": ref_ty * new_dept_pct, "ty_p1": ref_p1 * new_dept_pct, "ty_p2": ref_p2 * new_dept_pct}
                    if ref_ok:
                        keep = 1.0 - ref_reduction_pct   # ref dept loses ref_reduction_pct (independent of the carve)
                        depts[ref_dept].update(ty=ref_ty * keep, ty_p1=ref_p1 * keep, ty_p2=ref_p2 * keep)
                    if new_dept in depts:
                        depts[new_dept].update(carve)   # replaces its own plan (no reference here -> 0)
                        depts[new_dept]["active"] = True   # planned by the template, even if inactive in the master
                    elif ref_ok:
                        depts[new_dept] = {
                            "ly": 0.0, **carve, "growth_pct": None,
                            "cont_pct": 0.0, "active": True, "is_new": True,
                            "ref_dept": ref_dept,
                            "new_dept_pct": cfg.get("new_dept_pct", legacy),
                            "ref_reduction_pct": cfg.get("ref_reduction_pct", legacy),
                        }
                post[(div, ty_month, grp)] = post.get((div, ty_month, grp), 0.0) + tot(depts)

    # one factor per division x month for every store: back on the pre-carve total, mix (and new / ref) kept exactly
    f = {k: (pre[k] / post[k]) if post.get(k) else 1.0 for k in pre}
    for store, sdata in result["stores"].items():
        grp = True if sdata.get("is_ssg") else store
        for div in new_dept_map:
            for ty_month, month_data in sdata["divisions"].get(div, {}).get("months", {}).items():
                depts, k = month_data["departments"], f.get((div, ty_month, grp), 1.0)
                act = {d: v for d, v in depts.items() if v.get("active", True)}
                for v in act.values():
                    for fld in ("ty", "ty_p1", "ty_p2"):
                        if fld in v:
                            v[fld] *= k
                month_data["div_total_ty"] = sum(v["ty"] for v in act.values())
                month_data["div_total_p1"] = sum(v.get("ty_p1", 0.0) for v in act.values())
                month_data["div_total_p2"] = sum(v.get("ty_p2", 0.0) for v in act.values())
                pcts = shares_pct({d: v["ty"] for d, v in act.items()})   # adds to exactly 100
                for d, v in depts.items():
                    v["cont_pct"] = pcts.get(d, 0.0)

    return result


def _load_growth_matrix():
    """
    Returns {division: {dept: {period: float}}}: the saved matrix with BIS's live growth on top (see
    department_plan.live_growth_matrix).
    """
    from engines.department_plan import live_growth_matrix
    return live_growth_matrix()


def _load_dept_config():
    """
    Returns {division: [{name, active}]} merging master + custom + state.
    Imports _build_master from department_plan to avoid duplication.
    """
    from engines.department_plan import _build_master
    return _build_master()


def _growth_p1_p2(growth_matrix, div, dept, ty_month):
    dept_data = growth_matrix.get(div, {}).get(dept, {})
    g_p1 = float(dept_data.get(f"{ty_month} P1", 100.0))
    g_p2 = float(dept_data.get(f"{ty_month} P2", 100.0))
    return g_p1, g_p2


def _avg_division_growth(growth_matrix, div, ty_month):
    """
    Division-level average growth for a month — used for non-SSG stores.
    Averages growth across the division's departments for that month, leaving out the ones BIS delisted that month
    (index 0 = -100%): counting them pulled KIDS Apr'27 to 89.8 instead of 110 (audit 2026-10-06). Falls back to 100.0.
    """
    dept_growths = growth_matrix.get(div, {})
    if not dept_growths:
        return 100.0
    vals = []
    p1_key = f"{ty_month} P1"
    p2_key = f"{ty_month} P2"
    for dept_periods in dept_growths.values():
        p1 = float(dept_periods.get(p1_key, 100.0))
        p2 = float(dept_periods.get(p2_key, 100.0))
        if p1 + p2 > 0:
            vals.append((p1 + p2) / 2.0)
    return sum(vals) / len(vals) if vals else 100.0


def _aop_lfl_base():
    """(publish id, {STORE: {DIVISION: {TY month: L}}}) - the LY base of the AOP publish BIS plans on; (None, {}) when
    it can't be read (the plan then runs on today's Calendar LY, as before)."""
    try:
        from engines.grain_view import aop_base_by_store
        return aop_base_by_store()
    except Exception:   # noqa: BLE001 - AOP / DB unreachable
        return None, {}


def _aop_lfl_targets() -> dict:
    """{DIVISION: {TY month: L}} - the AOP plan BIS spreads each division onto (division_plan._bis_aop); {} if unread."""
    try:
        from engines.division_plan import _bis_aop, PLAN_MONTHS
        pid, _, totals, _, _ = _bis_aop()
        return {dv: {PLAN_MONTHS[int(p)]: float(v) for p, v in (pm or {}).items() if int(p) in PLAN_MONTHS and v}
                for dv, pm in (totals or {}).items() if dv in DIVISIONS} if pid else {}
    except Exception:   # noqa: BLE001 - AOP / DB unreachable: no hold
        return {}


def _base_scale(aop_base, store, div, ty_month, ly_month, store_dept_data) -> float:
    """The factor that puts a store x division x month's department LY (all departments) onto the AOP base."""
    b = (aop_base.get(str(store).strip().upper()) or {}).get(div, {}).get(ty_month)
    if not b:
        return 1.0
    snap = sum(v.get(ly_month, 0.0) for v in store_dept_data.values() if isinstance(v, dict))
    return b / snap if snap > 0 else 1.0


# ── Core Calculation ──────────────────────────────────────────────────────────

def run_dept_plan():
    """
    Returns:
      {
        "stores": {
          store_code: {
            "tag": str,
            "is_ssg": bool,
            "ref_store": str,
            "divisions": {
              div: {
                "months": {
                  ty_month: {
                    "div_total_ty": float,
                    "departments": {
                      dept: {
                        "ly": float,
                        "ty": float,
                        "growth_pct": float,   # effective monthly growth applied
                        "cont_pct": float,     # TY contribution % within div
                        "active": bool
                      }
                    }
                  }
                }
              }
            }
          }
        },
        "meta": {
          "ssg_count": int,
          "non_ssg_count": int,
          "dept_actuals_loaded": bool,
          "missing_ref_stores": [str]
        }
      }
    """
    store_master   = _load_store_master()
    dept_actuals, ly_locked = _load_dept_actuals()
    store_div_acts = _load_store_div_actuals()
    growth_matrix  = _load_growth_matrix()
    dept_config    = _load_dept_config()

    dept_actuals_loaded = bool(dept_actuals)

    # Only compute months where LY actuals are locked
    # ly_locked e.g. ["Mar'26","Apr'26","May'26","Jun'26"]
    # active_pairs = [(TY_month, LY_month)] filtered to locked LY months only
    active_pairs = [(ty, ly) for ty, ly in MONTH_PAIR if ly in ly_locked]
    active_ty_months = [ty for ty, _ in active_pairs]

    # Build active dept sets per division. The Department Master's inactive flag holds in the BIS divisions (user,
    # 2026-10-01: a department BIS doesn't plan, e.g. the new LW_U_CORD SETS, carried its stray LY at 0% growth, so the
    # base plan wasn't BIS's); a new one gets its plan from the New Department template instead. GM / RETAIL keep every
    # department: their flags came from the BIS sync, which doesn't cover them (95-99% of their plan is "inactive").
    # A department BIS gives growth to stays planned whatever the flag says - BIS is the plan (L_EW_BLOUSE: inactive in
    # the master, +10% in BIS); BIS's delisted ones come as -100% (index 0) and drop out either way.
    from engines.department_plan import BIS_DIVISIONS, _load_state
    state = _load_state()
    # ...except off season (user, 2026-10-14: "MAKE WINTER/PREWINTER INACTIVE FOR MAMJ"): BIS gives the winter / pre-winter
    # departments a growth, but one the master has inactive stays out for months its attribute is off season
    # (plan_checkup.season) - BIS can't switch it back on
    try:
        from engines.plan_checkup import season, _in
        from engines.final_results_engine import _load_dept_attr_map
        _ins, _ = season(active_ty_months)
        _attrs = _load_dept_attr_map()
    except Exception:   # noqa: BLE001 - no rule to hand: BIS decides, as before
        _ins, _attrs, _in = None, {}, (lambda a, i: True)
    active_depts = {}
    for div, rows in dept_config.items():
        bis = {d for d, p in growth_matrix.get(div, {}).items() if any(float(x) > 0 for x in p.values())}
        bis -= {d for d in bis if not _in((_attrs.get(div) or {}).get(d, "-"), _ins)}
        off = ({n for n, v in state.get(div, {}).items() if not v.get("active", True)} - bis) if div in BIS_DIVISIONS else set()
        active_depts[div] = {r["name"] for r in rows if r.get("active", True) and r["name"] not in off}

    # Build store lookup
    store_info = {}
    for s in store_master:
        store_info[s["Store"]] = s

    ssg_stores = {s for s, info in store_info.items() if _is_ssg(info.get("Tag", ""), s)}
    missing_ref = []
    # The like-for-like LY is the AOP publish's base (user, 2026-10-13: "this should match the AOP Forecaster's
    # projection for MAMJ which is 11.1% and then only it should be pushed to sales plan engine"): the Calendar snapshot
    # moved Mar'26 since Version 2 was published (V2 keeps its unshifted Mar base - user's choice, 26 Sep), so BIS's
    # growth on today's LY fell ~5.9 Cr short of the AOP plan. Each store x division x month is scaled onto that base;
    # the department mix inside it stays today's. A store / month the publish has no base for keeps today's LY.
    aop_pid, aop_base = _aop_lfl_base()

    results_ssg = {}

    # ── Step 1: SSG stores ────────────────────────────────────────────────────
    for store in ssg_stores:
        results_ssg[store] = {}
        for div in DIVISIONS:
            active = active_depts.get(div, set())
            months_out = {}

            for ty_month, ly_month in active_pairs:   # only locked months
                store_dept_data = dept_actuals.get(store, {}).get(div, {})
                dept_vals = {}
                k_base = _base_scale(aop_base, store, div, ty_month, ly_month, store_dept_data)

                for dept in active:
                    ly_val = store_dept_data.get(dept, {}).get(ly_month, 0.0) * k_base
                    g_p1, g_p2 = _growth_p1_p2(growth_matrix, div, dept, ty_month)
                    g = (g_p1 + g_p2) / 2.0
                    ly_half = ly_val / 2.0
                    # full precision - never rounded before summing (2026-09-30, "least apportioned difference")
                    ty_p1 = ly_half * g_p1 / 100.0
                    ty_p2 = ly_half * g_p2 / 100.0
                    ty_val = ty_p1 + ty_p2
                    dept_vals[dept] = {
                        "ly": ly_val, "ly_p1": ly_half, "ly_p2": ly_half,
                        "ty": ty_val, "ty_p1": ty_p1, "ty_p2": ty_p2,
                        "growth_pct": g, "g_p1": g_p1, "g_p2": g_p2,
                        "active": True,
                    }

                # Add inactive depts (zero, not in total)
                all_depts = {r["name"] for r in dept_config.get(div, [])}
                for dept in all_depts - active:
                    ly_val = store_dept_data.get(dept, {}).get(ly_month, 0.0) * k_base
                    dept_vals[dept] = {
                        "ly": ly_val, "ly_p1": ly_val / 2.0, "ly_p2": ly_val / 2.0,
                        "ty": 0.0, "ty_p1": 0.0, "ty_p2": 0.0,
                        "growth_pct": 0.0, "g_p1": 0.0, "g_p2": 0.0, "active": False,
                    }

                # TY divisional total from active depts only
                div_total_ty = sum(v["ty"] for v in dept_vals.values() if v["active"])
                div_total_p1 = sum(v.get("ty_p1", v["ty"] / 2.0) for v in dept_vals.values() if v["active"])
                div_total_p2 = sum(v.get("ty_p2", v["ty"] / 2.0) for v in dept_vals.values() if v["active"])

                # Contribution % - the active departments add to exactly 100
                pcts = shares_pct({d: v["ty"] for d, v in dept_vals.items() if v["active"]})
                for dept, v in dept_vals.items():
                    v["cont_pct"] = pcts.get(dept, 0.0)

                months_out[ty_month] = {
                    "div_total_ty": div_total_ty,
                    "div_total_p1": div_total_p1,
                    "div_total_p2": div_total_p2,
                    "departments": dept_vals,
                }

            results_ssg[store][div] = {"months": months_out}

    # ── Step 1b: like-for-like stores held on the AOP plan ─────────────────────
    # BIS holds every division x month exactly on its AOP plan over its own department mix; Sales Plan's mix (Calendar)
    # differs a little, so the same growth % landed ~10 L off (-0.024%, mostly Mar). One factor per division x month
    # over the LFL stores puts them back on it, the mix kept (2026-10-13, "should match the AOP ... 11.1%").
    hold = {}
    for div, months in _aop_lfl_targets().items():
        for ty_month, T in months.items():
            mds = [st[div]["months"][ty_month] for st in results_ssg.values() if ty_month in st.get(div, {}).get("months", {})]
            cur = sum(v["ty"] for md in mds for v in md["departments"].values() if v["active"])
            if not (T and cur > 0):
                continue
            f = hold.setdefault(div, {})[ty_month] = T / cur
            for md in mds:
                for v in md["departments"].values():
                    if v["active"]:
                        v["ty"], v["ty_p1"], v["ty_p2"] = v["ty"] * f, v["ty_p1"] * f, v["ty_p2"] * f
                act = [v for v in md["departments"].values() if v["active"]]
                md["div_total_ty"] = sum(v["ty"] for v in act)
                md["div_total_p1"] = sum(v["ty_p1"] for v in act)
                md["div_total_p2"] = sum(v["ty_p2"] for v in act)

    # ── Step 2: Non-SSG stores ────────────────────────────────────────────────
    # (user, 2026-10-14: "plan should come for the 309 stores or whatever count it is for the sales in the aop
    # forecaster ... For stores which are out of the SSG 148 stores - their respective ref stores plan cont % can be
    # taken and moved forward on every step"): TY = the AOP Forecaster's plan for the store x division x month, split
    # by its reference store's department cont % (and P1 / P2) - the MRP, display type and qty steps then follow that
    # reference too. A reference that is itself not like-for-like is followed to its own reference (up to 3 steps).
    results_non_ssg = {}
    aop_store = _aop_store_plan()
    ref_used = {}

    for s_info in store_master:
        store = s_info["Store"]
        if _is_ssg(s_info.get("Tag", ""), store):
            continue

        ref = s_info.get("Ref Store", "")
        for _ in range(3):
            if ref in results_ssg or ref not in store_info:
                break
            ref = store_info[ref].get("Ref Store", "")
        if ref not in results_ssg:
            missing_ref.append(store)
            ref_data = None
        else:
            ref_data = results_ssg[ref]
            ref_used[store] = ref

        results_non_ssg[store] = {}
        for div in DIVISIONS:
            active = active_depts.get(div, set())
            all_depts = {r["name"] for r in dept_config.get(div, [])}
            months_out = {}

            for ty_month, ly_month in active_pairs:   # only locked months
                # LY divisional total — prefer "Store Actuals" sheet; fall back to
                # summing dept-level actuals (fixes stores absent from that sheet).
                ly_div_total = store_div_acts.get(store, {}).get(div, {}).get(ly_month, 0.0)
                if ly_div_total == 0.0:
                    store_dept_acts = dept_actuals.get(store, {}).get(div, {})
                    ly_div_total = sum(
                        info.get(ly_month, 0.0)
                        for info in store_dept_acts.values()
                        if isinstance(info, dict)
                    )
                div_growth = _avg_division_growth(growth_matrix, div, ty_month)
                if aop_store:   # the AOP Forecaster's plan for it (0 when the AOP has none - untagged rows, an NSO with no opening month)
                    div_total_ty = float((aop_store.get(str(store).strip().upper(), {}).get(div) or {}).get(ty_month) or 0.0)
                else:
                    div_total_ty = ly_div_total * (div_growth / 100.0)

                dept_vals = {}

                ref_month = (ref_data or {}).get(div, {}).get("months", {}).get(ty_month, {})
                ref_depts  = ref_month.get("departments", {})
                # the division total split by the ref store's shares - the parts add back to it exactly. A store whose
                # ref store has no share in this division x month (or no ref store) splits by its OWN LY department mix
                # (audit 2026-10-06: it kept a division total with every department at 0, so division != sum of depts)
                cont = {d: ref_depts.get(d, {}).get("cont_pct", 0.0) for d in active}
                if sum(cont.values()) <= 0:
                    own = dept_actuals.get(store, {}).get(div, {})
                    cont = {d: (own.get(d) or {}).get(ly_month, 0.0) if isinstance(own.get(d), dict) else 0.0 for d in active}
                tys, lys, pcts = split(div_total_ty, cont), split(ly_div_total, cont), shares_pct(cont)
                for dept in active:
                    ref_dept = ref_depts.get(dept, {})
                    ty_val = tys[dept]
                    # its own growth on its own LY when it has one; a store new since LY carries its reference's
                    g        = (ty_val / lys[dept] * 100.0) if lys[dept] > 0 else ref_dept.get("growth_pct", div_growth)
                    ref_p1 = ref_dept.get("ty_p1", 0.0)
                    ref_ty = ref_dept.get("ty", 0.0)
                    ty_p1 = ty_val * ref_p1 / ref_ty if ref_ty > 0 else ty_val / 2.0
                    dept_vals[dept] = {
                        "ly": lys[dept], "ly_p1": lys[dept] / 2.0, "ly_p2": lys[dept] / 2.0,
                        "ty": ty_val, "ty_p1": ty_p1, "ty_p2": ty_val - ty_p1,
                        "growth_pct": g, "g_p1": ref_dept.get("g_p1", g), "g_p2": ref_dept.get("g_p2", g),
                        "cont_pct": pcts[dept],
                        "active": True,
                    }
                for dept in all_depts - active:
                    dept_vals[dept] = {"ly": 0.0, "ly_p1": 0.0, "ly_p2": 0.0,
                                       "ty": 0.0, "ty_p1": 0.0, "ty_p2": 0.0,
                                       "growth_pct": 0.0, "g_p1": 0.0, "g_p2": 0.0,
                                       "cont_pct": 0.0, "active": False}
                # nothing to split by at all (no ref share and no own LY by department): the division carries no plan
                div_total_ty = sum(v["ty"] for v in dept_vals.values() if v.get("active"))

                nsg_p1 = sum(v.get("ty_p1", v["ty"]/2.0) for v in dept_vals.values() if v.get("active"))
                nsg_p2 = sum(v.get("ty_p2", v["ty"]/2.0) for v in dept_vals.values() if v.get("active"))
                months_out[ty_month] = {
                    "div_total_ty": div_total_ty,
                    "div_total_p1": nsg_p1,
                    "div_total_p2": nsg_p2,
                    "departments": dept_vals,
                }

            results_non_ssg[store][div] = {"months": months_out}

    # Merge both
    all_results = {}
    for s, data in {**results_ssg, **results_non_ssg}.items():
        info = store_info.get(s, {})
        ssg = _is_ssg(info.get("Tag", ""), s)
        all_results[s] = {
            "tag": info.get("Tag", ""),
            "is_ssg": ssg,
            "group": store_group(s, ssg) if (ssg or info.get("Tag")) else "Untagged",   # untagged ERP rows: no AOP plan
            "ref_store": info.get("Ref Store", ""),
            "ref_used": ref_used.get(s, s if ssg else ""),   # the like-for-like store its split follows
            "cluster": info.get("Cluster", ""),
            "divisions": data,
        }

    return {
        "stores": all_results,
        "meta": {
            "ssg_count": len(results_ssg),
            "non_ssg_count": len(results_non_ssg),
            "dept_actuals_loaded": dept_actuals_loaded,
            "missing_ref_stores": list(set(missing_ref)),
            "non_ssg_ty_source": "AOP Forecaster store plan" if aop_store else "own LY x division average BIS growth (AOP store plan unreadable)",
            "ly_months_locked": ly_locked,
            "ty_months_active": active_ty_months,
            "lfl_ly_base": f"AOP publish {aop_pid}" if aop_base else "Calendar snapshot",
            "lfl_hold_on_aop": hold,
        },
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

# ── Actuals & Lock Endpoints ──────────────────────────────────────────────────

@router.get("/actuals/status")
def actuals_status():
    """Where Sales Plan's LY sales come from (the Calendar app's department-level snapshots, refreshed by the
    nightly data-lake sync) and which TY months they cover. No import / lock / unlock any more (2026-09-28)."""
    ly = locked_ly_months()
    return {
        "source": actuals_source(),
        "locked_ly_months": {m: {"locked": True, "source": "calendar"} for m in ly},   # kept for older callers
        "ly_months": ly,
        "available_ty_months": available_ty_months(),
    }


# ── Plan Endpoints ────────────────────────────────────────────────────────────

@router.get("/new-depts")
def get_new_depts():
    """Returns the new-dept mapping: {division: {new_dept: {ref_dept, alloc_pct}}}"""
    return _load_new_dept_map()


@router.post("/new-depts")
async def save_new_depts(request: Request):
    """
    Saves the new-dept mapping.
    Body: {division: {new_dept: {ref_dept, new_dept_pct, ref_reduction_pct}}}
    Both % fields are unlimited (>100 allowed). No upper cap.
    Backward-compat: accepts old alloc_pct field.
    """
    body = await request.json()
    for div, entries in body.items():
        if div not in DIVISIONS:
            raise HTTPException(status_code=422, detail=f"Unknown division: {div}")
        for new_dept, cfg in entries.items():
            if "ref_dept" not in cfg:
                raise HTTPException(status_code=422, detail=f"Entry {new_dept} missing ref_dept")
            has_pct = "new_dept_pct" in cfg or "ref_reduction_pct" in cfg or "alloc_pct" in cfg
            if not has_pct:
                raise HTTPException(status_code=422, detail=f"Entry {new_dept} missing % fields")
            # Negative % allowed — carve or boost logic handled in apply_new_dept_adjustments
            pass
    # save, regenerate and clear the stale corrected plans - the same as the template upload (audit 2026-10-06: this
    # path left attr/base-corrected plans in front of the new one and hid a failed regeneration behind ok: true)
    _apply_new_dept_map(body)
    finalized = True
    return {"ok": True, "saved": sum(len(v) for v in body.values()), "plan_finalized": finalized}


@router.delete("/new-depts")
def clear_new_depts():
    """
    Clears the new-dept mapping and deletes all downstream plan files
    (final_dept_plan, attr_corrected_plan, base_corrected_plan).
    """
    _BASE_DIR = os.path.join(_BASE, "..")
    removed = []
    # Clear mapping
    if os.path.exists(NEW_DEPT_MAP_PATH):
        save_json(NEW_DEPT_MAP_PATH, {})
        removed.append("new_dept_mapping.json")
    # Remove downstream plan files so Final Results reflects the cleared state
    for fname in ("final_dept_plan.json", "attr_corrected_plan.json", "base_corrected_plan.json"):
        p = os.path.join(_BASE_DIR, fname)
        if os.path.exists(p):
            os.remove(p)
            removed.append(fname)
    return {"ok": True, "cleared": removed}


# ── New departments: template + upload (user, 2026-10-01: "I want a template made for this instead of sync from
#    directory" - replaces the fixed-folder sync of NEW Departments.xlsx) ─────────────────────────────────────────
ND_COLS = ["DIVISION", "NEW DEPT", "REF DEPT", "NEW DEPT %", "REF REDUCTION %"]


def _dept_divisions() -> dict:
    """{DEPT (upper): division} for every department the plan knows."""
    return {r["name"].strip().upper(): div for div, rows in _load_dept_config().items() for r in rows}


def parse_new_dept_template(df: pd.DataFrame, dept_div: dict) -> tuple[dict, list]:
    """The filled template (or the old folder file: NEW MC | REF. MC | <Mon> P1 / P2 as fractions, averaged) ->
    ({division: {new_dept: {ref_dept, new_dept_pct, ref_reduction_pct}}}, problems). Any problem refuses the file."""
    import re as _re
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    up = {c.upper(): c for c in df.columns}
    problems, mapping, seen = [], {}, {}
    new_c = up.get("NEW DEPT") or next((c for c in df.columns if "new" in c.lower() and "mc" in c.lower()), None)
    ref_c = up.get("REF DEPT") or next((c for c in df.columns if "ref" in c.lower() and "mc" in c.lower()), None)
    if not new_c or not ref_c:
        return {}, [f"Columns NEW DEPT and REF DEPT not found - use the template. Got: {', '.join(df.columns)}"]
    legacy = [c for c in df.columns if _re.match(r"[A-Za-z]+\s+P[12]$", c)] if "NEW DEPT %" not in up else []
    if "NEW DEPT %" not in up and not legacy:
        return {}, ["Column NEW DEPT % not found - use the template."]
    for i, row in df.iterrows():
        r = i + 2   # the sheet's row number (header is row 1)
        new = str(row[new_c]).strip() if pd.notna(row[new_c]) else ""
        ref = str(row[ref_c]).strip() if pd.notna(row[ref_c]) else ""
        if not new and not ref:
            continue
        if not new or not ref:
            problems.append(f"Row {r}: give both NEW DEPT and REF DEPT.")
            continue
        if new.upper() == ref.upper():
            problems.append(f"Row {r} ({new}): NEW DEPT is its own REF DEPT - the row adds and takes the same share of one "
                            f"department, so it changes nothing. Name the existing department it is carved from.")
            continue
        if legacy:   # old folder file: month fractions (0.5 = 50%), averaged - both % the same
            vals = [float(row[c]) * 100 for c in legacy if pd.notna(row[c])]
            if not vals:
                problems.append(f"Row {r} ({new}): no allocation values.")
                continue
            new_pct = red_pct = sum(vals) / len(vals)
        else:
            try:
                new_pct = float(row[up["NEW DEPT %"]]) if pd.notna(row[up["NEW DEPT %"]]) else None
                red_c = up.get("REF REDUCTION %")
                red_pct = float(row[red_c]) if red_c and pd.notna(row[red_c]) else new_pct
            except (TypeError, ValueError):
                problems.append(f"Row {r} ({new}): NEW DEPT % and REF REDUCTION % must be numbers (50 = 50%).")
                continue
            if new_pct is None:
                problems.append(f"Row {r} ({new}): NEW DEPT % is blank.")
                continue
        if new_pct < 0:   # a new department may be bigger than its reference (e.g. 120 = 1.2x), never negative
            problems.append(f"Row {r} ({new}): NEW DEPT % {new_pct:g} is below 0 (enter 50 for 50%).")
            continue
        if not 0 <= red_pct <= 100:   # the reference can't lose more than it has
            problems.append(f"Row {r} ({new}): REF REDUCTION % {red_pct:g} is outside 0-100 - the reference can't lose more than it has.")
            continue
        div_c = up.get("DIVISION")
        div = str(row[div_c]).strip().upper() if div_c and pd.notna(row[div_c]) and str(row[div_c]).strip() else ""
        ref_div = dept_div.get(ref.upper())
        if ref_div is None:
            problems.append(f"Row {r} ({new}): REF DEPT {ref} is not a department in the plan - pick one from the Departments sheet.")
            continue
        div = div or ref_div
        if div != ref_div:
            problems.append(f"Row {r} ({new}): REF DEPT {ref} is in {ref_div}, not {div}.")
            continue
        if new.upper() in seen:
            problems.append(f"Row {r}: {new} is also on row {seen[new.upper()]} - one row per new department.")
            continue
        seen[new.upper()] = r
        mapping.setdefault(div, {})[new] = {"ref_dept": ref, "new_dept_pct": new_pct, "ref_reduction_pct": red_pct}
    if not mapping and not problems:
        problems.append("The file has no new departments - fill at least one row.")
    return mapping, problems


def _apply_new_dept_map(mapping: dict) -> dict:
    """Save the mapping and regenerate the plan with it (downstream corrected plans go stale, so they are cleared)."""
    _save_new_dept_map(mapping)
    base = run_dept_plan()
    final = apply_new_dept_adjustments(base, mapping)
    save_json(FINAL_PLAN_PATH, final)
    for fname in ("attr_corrected_plan.json", "base_corrected_plan.json"):
        p = os.path.join(_BASE, "..", fname)
        if os.path.exists(p):
            os.remove(p)
    return final


@router.get("/new-depts/template")
def new_depts_template():
    """The template, pre-filled with the current new departments, plus a Departments sheet to pick REF DEPT from."""
    cur = [{"DIVISION": div, "NEW DEPT": nd, "REF DEPT": c.get("ref_dept", ""),
            "NEW DEPT %": float(c.get("new_dept_pct", c.get("alloc_pct", 0))),
            "REF REDUCTION %": float(c.get("ref_reduction_pct", c.get("alloc_pct", 0)))}
           for div, entries in _load_new_dept_map().items() for nd, c in entries.items()]
    depts = sorted((div, r["name"], "active" if r.get("active", True) else "inactive")
                   for div, rows in _load_dept_config().items() for r in rows)
    how = pd.DataFrame({"How to fill": [
        "One row per new department (MC) introduced this year.",
        "DIVISION: KIDS / LADIES / MENS / GM / RETAIL - optional, taken from REF DEPT when blank.",
        "NEW DEPT: the new department's name.",
        "REF DEPT: the existing department it is carved from - exactly as on the Departments sheet.",
        "NEW DEPT %: the new department's plan = this % of the REF DEPT's plan, every store and month (50 = 50%; over 100 = bigger than the REF).",
        "REF REDUCTION %: how much the REF DEPT loses, 0-100 (independent of NEW DEPT %; blank = same as NEW DEPT %).",
        "NEW DEPT and REF DEPT must differ - a department can't be carved from itself.",
        "Upload replaces the whole list - delete a row to drop that new department. Any problem refuses the file.",
    ]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        pd.DataFrame(cur, columns=ND_COLS).to_excel(xw, sheet_name="New Departments", index=False)
        pd.DataFrame(depts, columns=["DIVISION", "DEPARTMENT", "STATUS"]).to_excel(xw, sheet_name="Departments", index=False)
        how.to_excel(xw, sheet_name="How to fill", index=False)
        ws = xw.sheets["New Departments"]
        ws.set_column(0, 0, 12)
        ws.set_column(1, 2, 32)
        ws.set_column(3, 4, 18)
        xw.sheets["Departments"].set_column(0, 2, 30)
        xw.sheets["How to fill"].set_column(0, 0, 110)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="New Departments - template.xlsx"'})


@router.post("/new-depts/upload")
async def upload_new_depts(file: UploadFile = File(...)):
    """The filled template -> checked, saved as the new-department mapping, plan regenerated (as Save & Apply)."""
    try:
        df = pd.read_excel(io.BytesIO(await file.read()), sheet_name=0, header=0)
    except Exception as e:  # noqa: BLE001 - not an Excel file
        raise HTTPException(422, f"Could not read {file.filename}: {e}")
    mapping, problems = parse_new_dept_template(df, _dept_divisions())
    if problems:
        raise HTTPException(422, {"message": f"{len(problems)} problem(s) - nothing was changed.", "problems": problems[:50]})
    final = _apply_new_dept_map(mapping)
    return {"ok": True, "divisions": sorted(mapping), "total_entries": sum(len(v) for v in mapping.values()),
            "plan_regenerated": True, "stores": len(final.get("stores", {}))}


@router.post("/generate-base")
def generate_base_plan():
    """
    Runs the base department plan (growth-matrix only, no new-dept adjustments)
    and writes final_dept_plan.json. Also clears any stale downstream files so
    Attr Correction and Base Correction know they need to re-run.
    """
    _BASE_DIR = os.path.join(_BASE, "..")
    key = _inputs_stamp()   # the inputs this plan is made from - before the run, so a change during it shows next time
    plan = run_dept_plan()
    # Apply new-dept mapping if one exists (empty mapping = no change)
    new_dept_map = _load_new_dept_map()
    final = apply_new_dept_adjustments(plan, new_dept_map)
    save_json(FINAL_PLAN_PATH, final)
    save_json(FINAL_STAMP_PATH, {"inputs": key, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    # Invalidate downstream optional engines
    stale_cleared = []
    for fname in ("attr_corrected_plan.json", "base_corrected_plan.json"):
        p = os.path.join(_BASE_DIR, fname)
        if os.path.exists(p):
            os.remove(p)
            stale_cleared.append(fname)
    store_count = len(final.get("stores", {}))
    return {"ok": True, "stores": store_count, "stale_cleared": stale_cleared}


@router.get("/run")
def run_plan():
    base = run_dept_plan()
    new_dept_map = _load_new_dept_map()
    return apply_new_dept_adjustments(base, new_dept_map)


@router.get("/export")
def export_plan():
    """
    Exports full plan as Excel:
    Sheet 1 — Summary: Store | Division | Department | Month1 TY | … | Month12 TY
    Sheet 2 — Contribution: Store | Division | Department | Month1 Cont% | …
    """
    result = run_dept_plan()

    rows_val  = []
    rows_cont = []

    for store, sdata in result["stores"].items():
        for div in DIVISIONS:
            div_data = sdata["divisions"].get(div, {})
            months_data = div_data.get("months", {})

            # Collect all depts that appear
            all_depts = set()
            for m_data in months_data.values():
                all_depts.update(m_data.get("departments", {}).keys())

            for dept in sorted(all_depts):
                row_val  = {"Store": store, "Division": div, "Department": dept,
                            "Type": "SSG" if sdata["is_ssg"] else "Non-SSG",
                            "Ref Store": sdata["ref_store"]}
                row_cont = {"Store": store, "Division": div, "Department": dept,
                            "Type": "SSG" if sdata["is_ssg"] else "Non-SSG",
                            "Ref Store": sdata["ref_store"]}

                for ty_month in available_ty_months():
                    m_data = months_data.get(ty_month, {})
                    dept_d = m_data.get("departments", {}).get(dept, {})
                    row_val[ty_month]  = round(dept_d.get("ty", 0.0), 8)   # 8 dp (was 2): rows add back to totals
                    row_cont[ty_month] = round(dept_d.get("cont_pct", 0.0), 8)

                rows_val.append(row_val)
                rows_cont.append(row_cont)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(rows_val).to_excel(writer, sheet_name="TY Values (Rs Lakhs)", index=False)
        pd.DataFrame(rows_cont).to_excel(writer, sheet_name="Contribution %", index=False)
        # Meta sheet
        meta_df = pd.DataFrame([result["meta"]])
        meta_df.to_excel(writer, sheet_name="Run Meta", index=False)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=dept_sales_plan.xlsx"},
    )


# user, 2026-10-13: "population latency for the every view in the planning engine". The live plan run (~5-10 s) ran
# once per view per request - Cluster View (4-5 s every open), the sidebar summary, the Store / Cluster panels each ran
# it. Now ONE run feeds every read-only view, and only when one of its inputs changes. The plan itself is not kept
# (~1.5 GB in memory) - only what the views need. warm_plan_views() re-checks the inputs every minute from 8010's
# start, so a page usually finds it ready. Callers that change the plan (Generate Base Plan, new-dept map, /run) still
# take their own fresh run_dept_plan().
_views = {"key": None}
_views_lock = threading.Lock()
VIEW_BUILDERS = {}   # name -> fn(plan) -> what that view needs; grain_view adds its cube


def plan_views() -> dict:
    """{key, summary, cluster, + each VIEW_BUILDERS entry} for the current plan inputs (built once per change)."""
    key = _plan_inputs_key()
    with _views_lock:
        if _views.get("key") != key or any(n not in _views for n in VIEW_BUILDERS):
            plan = run_dept_plan()
            v = {"key": key, "summary": _plan_summary(plan), "cluster": _cluster_plan(plan)}
            for n, fn in VIEW_BUILDERS.items():
                v[n] = fn(plan)
            del plan
            _views.clear()
            _views.update(v)
        return _views


FINAL_STAMP_PATH = os.path.join(_BASE, "..", "final_dept_plan.inputs.json")   # git-ignored (SalesPlan/backend/*.json)
_CORRECTED = ("attr_corrected_plan.json", "base_corrected_plan.json")


def _inputs_stamp() -> str:
    import hashlib
    return hashlib.sha1(_plan_inputs_key().encode()).hexdigest()


def refresh_saved_plan() -> bool:
    """Keep the saved base plan (final_dept_plan.json - what Final Results, MRP and every later engine read) on its
    current inputs (user, 2026-10-13: "still showing stale updates" - BIS saved at 14:46 but the saved plan was from
    before, so it only caught up on a manual Generate Base Plan). Regenerates when BIS's growth, the AOP publish, the
    Department Master, the plan months or the LY change - unless a correction step has been run on it, which a new
    base plan would wipe (that stays the user's Generate Base Plan). True when it regenerated."""
    if not os.path.exists(FINAL_PLAN_PATH):
        return False
    from engines.engine_switch import plan_files   # only a correction that is switched on holds the base plan back
    if any(os.path.exists(os.path.join(_BASE, "..", f)) for f in plan_files() if f in _CORRECTED):
        return False
    try:
        with open(FINAL_STAMP_PATH, encoding="utf-8") as fh:
            old = json.load(fh).get("inputs")
    except (OSError, ValueError):
        old = None
    if old == _inputs_stamp():
        return False
    generate_base_plan()
    return True


def warm_plan_views(every: int = 60):
    """Background: keep plan_views() current so no page waits for the plan run, and the saved base plan on its inputs
    (refresh_saved_plan) - 8010 starts this at boot."""
    while True:
        for job in (plan_views, refresh_saved_plan):
            try:
                job()
            except Exception:   # noqa: BLE001 - a bad input file must not kill the warmer; the page shows the error itself
                pass
        time.sleep(every)


def _plan_inputs_key() -> str:
    """Everything run_dept_plan reads, in one string - cheap (~0.3 s) next to the ~10 s plan run itself."""
    from actuals_manager import _snapshot
    from engines.department_plan import _load_state
    import datetime as _dt
    return json.dumps([_load_growth_matrix(), _load_dept_config(), _load_state(), locked_ly_months(),
                       _snapshot("reindexed")[0], _dt.date.today(), list(_load_store_master()), _aop_lfl_base()[0]],
                      sort_keys=True, default=str)


@router.get("/plan-summary")
def get_plan_summary():
    """
    Lightweight sidebar snapshot: Division → Month → {ty, ly, growth%}
    Also returns overall total and month list.
    Kept until one of the plan's inputs changes (user, 2026-10-07: the full plan run took ~10 s on every page load and
    held up every other request, e.g. Master Setup sat on "Loading department master...").
    """
    return plan_views()["summary"]


def _plan_summary(result):
    months = result["meta"]["ty_months_active"]
    divs: dict = {}

    for store, sdata in result["stores"].items():
        if not sdata.get("is_ssg"):
            continue
        for div, div_data in sdata.get("divisions", {}).items():
            if div not in divs:
                divs[div] = {m: {"ty": 0.0, "ly": 0.0} for m in months}
            for month, mdata in div_data.get("months", {}).items():
                if month not in divs[div]:
                    continue
                depts = mdata.get("departments", {})
                for dept_data in depts.values():
                    divs[div][month]["ty"] += dept_data.get("ty", 0.0)
                    divs[div][month]["ly"] += dept_data.get("ly", 0.0)

    # round and add growth
    summary = {}
    grand_ty = 0.0
    grand_ly = 0.0
    for div, month_data in divs.items():
        summary[div] = {}
        for m, vals in month_data.items():
            ty, ly = vals["ty"], vals["ly"]   # full precision - the grand total is the sum, not a sum of rounded parts
            growth = round((ty - ly) / ly * 100, 1) if ly > 0 else None
            summary[div][m] = {"ty": ty, "ly": ly, "growth": growth}
            grand_ty += ty
            grand_ly += ly

    grand_growth = round((grand_ty - grand_ly) / grand_ly * 100, 1) if grand_ly > 0 else None
    return {
        "months": months,
        "divisions": summary,
        "grand_ty": grand_ty,
        "grand_ly": grand_ly,
        "grand_growth": grand_growth,
    }


@router.get("/cluster-plan")
def get_cluster_plan():
    """
    Aggregate the final department plan by Cluster instead of Store.

    For each Cluster × Division × Month × Department:
      ty_total   = sum of store TY values within the cluster
      ly_total   = sum of store LY values within the cluster
      cont_pct   = dept_ty_total / div_ty_total × 100  (re-derived, sums to 100% within div/month)

    Returns:
      {clusters: [...], divisions: [...], months: [...],
       result: {cluster → {division → {month → {dept → {ty, ly, cont_pct}}}}}}
    """
    return plan_views()["cluster"]   # shared, rebuilt only when an input changes (2026-10-13)


def _cluster_plan(plan):
    from store_master import get_store_cluster_map

    cluster_map = get_store_cluster_map()

    # Accumulate: cluster → div → month → dept → {ty, ly}
    acc: dict = {}
    for store, sdata in plan["stores"].items():
        cluster = cluster_map.get(store)
        if not cluster:
            continue
        cl_acc = acc.setdefault(cluster, {})
        for div, div_data in sdata["divisions"].items():
            div_acc = cl_acc.setdefault(div, {})
            for month, m_data in div_data["months"].items():
                mo_acc = div_acc.setdefault(month, {})
                for dept, dd in m_data.get("departments", {}).items():
                    dp = mo_acc.setdefault(dept, {"ty": 0.0, "ly": 0.0})
                    dp["ty"] += dd.get("ty",  0.0) or 0.0
                    dp["ly"] += dd.get("ly",  0.0) or 0.0

    # Re-derive cont_pct within each cluster/div/month
    result: dict = {}
    for cluster, divs in acc.items():
        result[cluster] = {}
        for div, months in divs.items():
            result[cluster][div] = {}
            for month, depts in months.items():
                pcts = shares_pct({d: v["ty"] for d, v in depts.items()})   # adds to exactly 100
                result[cluster][div][month] = {
                    dept: {"ty": vals["ty"], "ly": vals["ly"], "cont_pct": pcts[dept]} for dept, vals in depts.items()}

    all_clusters = sorted(result.keys())
    all_divs     = sorted({d for cl in result.values() for d in cl.keys()})
    all_months   = available_ty_months()

    return {
        "clusters":  all_clusters,
        "divisions": all_divs,
        "months":    all_months,
        "result":    result,
    }


@router.get("/cluster-plan/export")
def export_cluster_plan():
    """Export cluster-aggregated plan as Excel."""
    data = get_cluster_plan()

    rows = []
    for cluster, divs in data["result"].items():
        for div, months in divs.items():
            all_depts = sorted({d for mo in months.values() for d in mo.keys()})
            for dept in all_depts:
                row = {"Cluster": cluster, "Division": div, "Department": dept}
                for month in data["months"]:
                    dd = months.get(month, {}).get(dept, {})
                    row[f"{month} TY"]      = round(dd.get("ty", 0.0), 8)
                    row[f"{month} Cont%"]   = round(dd.get("cont_pct", 0.0), 8)
                rows.append(row)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Cluster Plan", index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=cluster_dept_plan.xlsx"},
    )
