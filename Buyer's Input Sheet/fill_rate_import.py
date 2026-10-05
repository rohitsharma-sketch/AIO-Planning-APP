"""Fill rate per department for the Planner's input (user, 5 Oct 2026: "PLAN vs FILL RATE.xlsb ... pivot has fill rates").

Reads the workbook's DIV - SUMMARY pivot (DIVISION | DEPARTMENT | ... | NEW FILL RATE % (W_CAP) | ...) and writes
fill_rate.json = {"source", "imported_at", "column", "departments": {DEPT NAME: rate 0-1}}. The rate drives the factor
table's fill-rate tag. Old department names in the pivot are copied onto both of their split departments (BIS
DEPT_SPLITS). A department the pivot doesn't list takes its reference department's rate in the page, else 1.00.
Run: python fill_rate_import.py "PLAN vs FILL RATE.xlsb"   (or upload it from BIS > Factors)
"""
import datetime
import json
import os
import sys

import pandas as pd

SHEET = "DIV - SUMMARY"
COLUMN = "NEW FILL RATE % (W_CAP)"   # user's choice, 5 Oct 2026 (not the MERGE / VISIBILITY rates)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fill_rate.json")
# old name in the buying data -> the departments BIS split it into (same as DEPT_SPLITS in otb-plan-app.html)
SPLITS = {
    "MSE_PYJAMA": ["MSE_HSR PYJAMA", "MSE_TXTL PYJAMA"], "L_IN_BRA": ["L_IN_BRA", "L_IN_SPRT BRA"],
    "LW_L_JEGGING": ["LW_L_DNM JOGGER", "LW_L_WVN JOGGER"], "LW_L_PALAZZO": ["LW_L_WES PALAZZO", "LW_L_ETH PALAZZO"],
    "KB_BERMUDA": ["KB_HSR BERMUDA", "KB_TXTL BERMUDA"], "KB_T-SHIRT H/S": ["KB_R/N T-SHIRT H/S", "KB_POLO T-SHIRT H/S"],
}


def _norm(v):
    return " ".join(str(v).split()).upper() if v is not None and v == v else ""


def parse(path):
    """{DEPT NAME: rate} from the pivot sheet. Raises ValueError if the sheet or its columns aren't there."""
    try:
        raw = pd.read_excel(path, sheet_name=SHEET, header=None, engine="pyxlsb" if path.lower().endswith(".xlsb") else None)
    except ValueError as e:
        raise ValueError(f"no '{SHEET}' sheet in the workbook") from e
    hdr = next((i for i, r in raw.iterrows() if {"DIVISION", "DEPARTMENT"} <= {_norm(v) for v in r}), None)
    if hdr is None:
        raise ValueError(f"'{SHEET}' has no DIVISION / DEPARTMENT header row")
    cols = {_norm(v): j for j, v in enumerate(raw.iloc[hdr])}
    if COLUMN not in cols:
        raise ValueError(f"'{SHEET}' has no '{COLUMN}' column")
    out = {}
    for _, r in raw.iloc[hdr + 1:].iterrows():
        div, dept, rate = _norm(r[cols["DIVISION"]]), _norm(r[cols["DEPARTMENT"]]), r[cols[COLUMN]]
        if not dept or "TOTAL" in div or "TOTAL" in dept or rate is None or rate != rate:
            continue
        out[dept] = float(rate)
    for old, parts in SPLITS.items():
        if old in out:
            for p in parts:
                out.setdefault(p, out[old])
    if not out:
        raise ValueError(f"'{SHEET}' has no department rows")
    return out


def save(path, source_name=None):
    depts = parse(path)
    data = {"source": source_name or os.path.basename(path), "column": COLUMN,
            "imported_at": datetime.datetime.now().isoformat(timespec="seconds"), "departments": depts}
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, OUT)
    return data


if __name__ == "__main__":
    d = save(sys.argv[1])
    print(f"{len(d['departments'])} departments -> {OUT}")
