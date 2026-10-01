# SOR Deviation Engine
# Summer / Occasional / Regular deviation logic
#
# Phase 1: Sales Plan Cont% + Stock PPO Cont% (same wide template) synced from the SOR Deviation folder, as PW/W
#   does (user, 2026-09-29: "similar format for SOR deviation just like PW/W" + months auto-detected from the files).
#   Template columns: ATTRIBUTE-1 | DEPARTMENT | ARTICLE NAME | FINAL MRP | <TY month cols, e.g. Mar'27 ...>
#   Both files must carry the same months; the block is detected with PW/W's own detect_block.
#   Average = (plan_cont + ppo_cont) / 2 when both present
#            = max(plan_cont, ppo_cont) when one is absent/zero
# Phase 2 (reapportionment): within each DEPT x MONTH, normalise all article avg%
#   values to sum to 100%.

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import os, json, datetime, io
import pandas as pd
from engines.pww_deviation_engine import month_label, detect_block, _load_meta as _pww_meta
from apportion import shares_pct  # noqa: E402  (engines.pww_deviation_engine puts backend/ on the path)

router = APIRouter()

_BASE          = os.path.dirname(__file__)
SOR_DIR        = os.path.join(_BASE, "..")
SOR_PLAN_PATH  = os.path.join(SOR_DIR, "sor_sales_plan.json")
SOR_PPO_PATH   = os.path.join(SOR_DIR, "sor_stock_ppo.json")
SOR_AVG_PATH   = os.path.join(SOR_DIR, "sor_avg_result.json")
SOR_REAPP_PATH = os.path.join(SOR_DIR, "sor_reapp_result.json")

# Source files, synced from the folder like PW/W's PPO Cont %
SOR_SOURCE_DIR = r"C:\Users\A9820\Documents\CLaude - New Projects\SalesPlan\SOR Deviation"
SOR_SOURCES = {"plan": os.path.join(SOR_SOURCE_DIR, "Sales Plan Cont %.xlsx"),
               "ppo":  os.path.join(SOR_SOURCE_DIR, "Stock PPO Cont %.xlsx")}

_FIXED_COLS = {"ATTRIBUTE-1", "DEPARTMENT", "ARTICLE NAME", "FINAL MRP"}


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_file(contents: bytes, filename: str) -> dict:
    """
    Parse wide-format SOR Excel/CSV.
    Returns {months: [...], rows: [{attr, dept, article, mrp, month_vals:{m:v}}]}
    """
    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents))
    else:
        df = pd.read_excel(io.BytesIO(contents))

    # Month columns = headers that name a month, as "Mar'27" (the rest must be the 4 fixed cols)
    df.columns = [month_label(c) or str(c).strip() for c in df.columns]
    month_cols = [c for c in df.columns if c.upper() not in _FIXED_COLS]
    bad = [c for c in month_cols if month_label(c) is None]
    if bad:
        raise ValueError(f"Columns that are not months: {bad}")
    if not month_cols:
        raise ValueError("No month columns")

    # Normalise fixed cols (case-insensitive fallback)
    col_map = {}
    for c in df.columns:
        cu = c.upper().strip()
        if cu == "ATTRIBUTE-1":     col_map[c] = "ATTRIBUTE-1"
        elif cu == "DEPARTMENT":    col_map[c] = "DEPARTMENT"
        elif cu == "ARTICLE NAME":  col_map[c] = "ARTICLE NAME"
        elif cu == "FINAL MRP":     col_map[c] = "FINAL MRP"
    df = df.rename(columns=col_map)

    rows = []
    for _, r in df.iterrows():
        attr    = str(r.get("ATTRIBUTE-1", "")).strip()
        dept    = str(r.get("DEPARTMENT",  "")).strip()
        article = str(r.get("ARTICLE NAME","")).strip()
        mrp_val = str(r.get("FINAL MRP",  "")).strip()

        if not dept or dept == "nan":
            continue

        month_vals = {}
        for m in month_cols:
            raw = r.get(m, None)
            try:
                v = float(raw)
            except (TypeError, ValueError):
                v = 0.0
            month_vals[m] = round(v, 6)

        rows.append({
            "attr":    attr,
            "dept":    dept,
            "article": article,
            "mrp":     mrp_val,
            "months":  month_vals,
        })

    return {"months": month_cols, "rows": rows}


def _load_json(path: str):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── status ─────────────────────────────────────────────────────────────────────

def _file_info(path):
    if not os.path.exists(path):
        return {"file_found": False, "path": path}
    st = os.stat(path)
    return {"file_found": True, "path": path, "size_kb": round(st.st_size / 1024, 1),
            "file_date": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/sync-status")
def sor_sync_status():
    return {k: _file_info(p) for k, p in SOR_SOURCES.items()}


@router.post("/sync")
def sor_sync():
    """Read both files from the folder; their months must match - the block is detected from them."""
    parsed = {}
    for k, path in SOR_SOURCES.items():
        if not os.path.exists(path):
            raise HTTPException(404, f"File not found: {path}")
        try:
            with open(path, "rb") as f:
                parsed[k] = _parse_file(f.read(), path)
        except Exception as e:
            raise HTTPException(422, f"{os.path.basename(path)}: {e}")
    if parsed["plan"]["months"] != parsed["ppo"]["months"]:
        raise HTTPException(422, f"Months differ - Sales Plan {parsed['plan']['months']} vs Stock PPO {parsed['ppo']['months']}")
    try:
        block, _ = detect_block(parsed["plan"]["months"])
    except ValueError as e:
        raise HTTPException(422, str(e))
    for k, dest in (("plan", SOR_PLAN_PATH), ("ppo", SOR_PPO_PATH)):
        parsed[k].update(imported_at=_ts(), source_file=os.path.basename(SOR_SOURCES[k]), block=block)
        _save_json(dest, parsed[k])
    return {"ok": True, "block": block, "months": parsed["plan"]["months"],
            "plan_rows": len(parsed["plan"]["rows"]), "ppo_rows": len(parsed["ppo"]["rows"])}


@router.get("/status")
def sor_status():
    plan  = _load_json(SOR_PLAN_PATH)
    ppo   = _load_json(SOR_PPO_PATH)
    avg   = _load_json(SOR_AVG_PATH)
    reapp = _load_json(SOR_REAPP_PATH)
    return {
        "block":          plan.get("block") if plan else None,
        "pww_block":      _pww_meta().get("block"),   # sanctity check shown on the page
        "plan_imported":  plan  is not None,
        "plan_rows":      len(plan["rows"])   if plan  else 0,
        "plan_months":    plan["months"]       if plan  else [],
        "plan_date":      plan.get("imported_at","") if plan else "",
        "ppo_imported":   ppo   is not None,
        "ppo_rows":       len(ppo["rows"])    if ppo   else 0,
        "ppo_date":       ppo.get("imported_at","")  if ppo  else "",
        "avg_run":        avg   is not None,
        "avg_date":       avg.get("run_at","")        if avg  else "",
        "reapp_run":      reapp is not None,
        "reapp_date":     reapp.get("run_at","")      if reapp else "",
    }


# ── average engine ─────────────────────────────────────────────────────────────

@router.get("/run-avg")
def run_avg():
    plan = _load_json(SOR_PLAN_PATH)
    ppo  = _load_json(SOR_PPO_PATH)
    if not plan:
        raise HTTPException(400, "Sales Plan not imported yet")
    if not ppo:
        raise HTTPException(400, "Stock PPO not imported yet")

    # Build lookup: (dept, article, mrp) -> {month: val}
    def build_lookup(data):
        lkp = {}
        for r in data["rows"]:
            key = (r["dept"], r["article"], r["mrp"])
            lkp[key] = r
        return lkp

    plan_lkp = build_lookup(plan)
    ppo_lkp  = build_lookup(ppo)

    # Union of all months from both files
    all_months = list(dict.fromkeys(plan["months"] + [m for m in ppo["months"] if m not in plan["months"]]))

    # Union of all article keys
    all_keys = set(plan_lkp.keys()) | set(ppo_lkp.keys())

    result_rows = []
    for key in sorted(all_keys):
        dept, article, mrp = key
        plan_row = plan_lkp.get(key)
        ppo_row  = ppo_lkp.get(key)

        attr = (plan_row or ppo_row).get("attr", "")

        month_detail = {}
        for m in all_months:
            p_val = plan_row["months"].get(m, 0.0) if plan_row else 0.0
            o_val = ppo_row["months"].get(m,  0.0) if ppo_row  else 0.0

            p_present = p_val > 0
            o_present = o_val > 0

            if p_present and o_present:
                avg = round((p_val + o_val) / 2, 6)
                rule = "avg"
            elif p_present:
                avg = p_val
                rule = "plan_only"
            elif o_present:
                avg = o_val
                rule = "ppo_only"
            else:
                avg = 0.0
                rule = "zero"

            month_detail[m] = {
                "plan_cont": round(p_val, 4),
                "ppo_cont":  round(o_val, 4),
                "avg_cont":  avg,
                "rule":      rule,
            }

        result_rows.append({
            "attr":    attr,
            "dept":    dept,
            "article": article,
            "mrp":     mrp,
            "months":  month_detail,
        })

    out = {
        "run_at": _ts(),
        "months": all_months,
        "rows":   result_rows,
    }
    _save_json(SOR_AVG_PATH, out)
    return {"ok": True, "rows": len(result_rows), "months": all_months}


@router.get("/avg-result")
def avg_result():
    d = _load_json(SOR_AVG_PATH)
    if not d:
        raise HTTPException(404, "Average not run yet")
    return d


# ── reapportionment ────────────────────────────────────────────────────────────

@router.get("/reapportion")
def reapportion():
    avg = _load_json(SOR_AVG_PATH)
    if not avg:
        raise HTTPException(400, "Run average first")

    months = avg["months"]

    # each dept x month's articles re-apportioned to exactly 100 (was avg / total x 100, each rounded to 6 dp)
    by_dm: dict = {}
    for i, row in enumerate(avg["rows"]):
        for m, md in row["months"].items():
            by_dm.setdefault((row["dept"], m), {})[i] = md["avg_cont"]
    shares = {k: shares_pct(v) for k, v in by_dm.items()}

    reapp_rows = []
    for i, row in enumerate(avg["rows"]):
        dept = row["dept"]
        month_detail = {}
        for m, md in row["months"].items():
            reapp = shares[(dept, m)][i]
            month_detail[m] = {
                "plan_cont":  md["plan_cont"],
                "ppo_cont":   md["ppo_cont"],
                "avg_cont":   md["avg_cont"],
                "rule":       md["rule"],
                "reapp_cont": reapp,
            }
        reapp_rows.append({
            "attr":    row["attr"],
            "dept":    row["dept"],
            "article": row["article"],
            "mrp":     row["mrp"],
            "months":  month_detail,
        })

    out = {
        "run_at": _ts(),
        "months": months,
        "rows":   reapp_rows,
    }
    _save_json(SOR_REAPP_PATH, out)
    return {"ok": True, "rows": len(reapp_rows)}


@router.get("/reapp-result")
def reapp_result():
    d = _load_json(SOR_REAPP_PATH)
    if not d:
        raise HTTPException(404, "Reapportionment not run yet")
    return d


# ── export ─────────────────────────────────────────────────────────────────────

@router.get("/export")
def export_reapp():
    d = _load_json(SOR_REAPP_PATH)
    if not d:
        raise HTTPException(404, "Reapportionment not run yet")

    months = d["months"]
    records = []
    for row in d["rows"]:
        base = {
            "ATTRIBUTE-1":  row["attr"],
            "DEPARTMENT":   row["dept"],
            "ARTICLE NAME": row["article"],
            "FINAL MRP":    row["mrp"],
        }
        for m in months:
            md = row["months"].get(m, {})
            base[f"{m} - Plan%"]  = md.get("plan_cont",  0)
            base[f"{m} - PPO%"]   = md.get("ppo_cont",   0)
            base[f"{m} - Avg%"]   = md.get("avg_cont",   0)
            base[f"{m} - Reapp%"] = md.get("reapp_cont", 0)
        records.append(base)

    df = pd.DataFrame(records)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="SOR Reapportionment")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=sor_reapportionment.xlsx"},
    )
