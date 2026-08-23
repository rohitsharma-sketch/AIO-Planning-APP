"""Sales Sync Engine
Watches a server folder for the latest sales parquet file, parses it on demand,
and caches the result locally. Always copies to scratch before reading.
"""

import os
import json
import shutil
import hashlib
import threading
import traceback
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CONFIG_FILE  = DATA_DIR / "sync_config.json"
STATUS_FILE  = DATA_DIR / "sync_status.json"
SALES_CACHE  = DATA_DIR / "sync_sales_cache.json"

SCRATCH = Path("data/sync_scratch")
SCRATCH.mkdir(exist_ok=True)

# ── config helpers ─────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {
        "sales_folder":  "",
        "sales_pattern": "*.parquet",
    }

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def load_status():
    if STATUS_FILE.exists():
        return json.loads(STATUS_FILE.read_text())
    return {
        "sales": {
            "last_sync": None,
            "rows": 0,
            "file": None,
            "error": None,
            "hash": None,
            "columns": [],
        }
    }

def save_status(st: dict):
    STATUS_FILE.write_text(json.dumps(st, indent=2))

# ── file discovery ─────────────────────────────────────────────────────────────

def latest_file(folder: str, pattern: str) -> Optional[Path]:
    """Return the most recently modified file matching pattern in folder."""
    try:
        p = Path(folder)
        if not p.exists():
            return None
        files = list(p.glob(pattern))
        if not files:
            return None
        return max(files, key=lambda f: f.stat().st_mtime)
    except Exception:
        return None

def file_hash(path: Path) -> str:
    h = hashlib.md5()
    h.update(str(path.stat().st_mtime).encode())
    h.update(str(path.stat().st_size).encode())
    return h.hexdigest()

# ── parser ─────────────────────────────────────────────────────────────────────

def parse_parquet(src_path: Path) -> dict:
    """
    Copy to scratch (avoids locking the server file), read with pandas,
    return {rows, columns, preview (first 500 rows), meta}.
    """
    import pandas as pd

    dst = SCRATCH / src_path.name
    shutil.copy2(src_path, dst)
    try:
        df = pd.read_parquet(dst)

        rows    = len(df)
        columns = list(df.columns)

        # Coerce non-serialisable types
        for col in df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
            df[col] = df[col].astype(str)

        preview = df.head(500).fillna("").astype(str).to_dict(orient="records")

        return {
            "rows":    rows,
            "columns": columns,
            "preview": preview,
            "meta": {
                "file":      src_path.name,
                "parsed_at": datetime.now().isoformat(),
            },
        }
    finally:
        try:
            dst.unlink()
        except Exception:
            pass

# ── sync worker ────────────────────────────────────────────────────────────────

_sync_lock = threading.Lock()

def _do_sync(folder: str, pattern: str):
    st    = load_status()
    entry = st.get("sales", {})
    entry["error"] = None

    try:
        src = latest_file(folder, pattern)
        if src is None:
            raise FileNotFoundError(
                f"No files matching '{pattern}' found in: {folder}"
            )

        h = file_hash(src)
        if h == entry.get("hash") and SALES_CACHE.exists():
            # File unchanged — just refresh timestamp
            entry["last_sync"] = datetime.now().isoformat()
            st["sales"] = entry
            save_status(st)
            return

        result = parse_parquet(src)
        SALES_CACHE.write_text(json.dumps(result, ensure_ascii=False))

        entry.update({
            "last_sync": datetime.now().isoformat(),
            "rows":      result["rows"],
            "file":      src.name,
            "hash":      h,
            "error":     None,
            "columns":   result["columns"],
        })

    except Exception as e:
        entry["error"]     = str(e)
        entry["last_sync"] = datetime.now().isoformat()
        traceback.print_exc()

    st["sales"] = entry
    save_status(st)

# ── endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
def sync_status():
    return {"config": load_config(), "status": load_status()}


class SyncConfig(BaseModel):
    sales_folder:  Optional[str] = None
    sales_pattern: Optional[str] = None


@router.post("/config")
def update_config(body: SyncConfig):
    cfg = load_config()
    if body.sales_folder  is not None: cfg["sales_folder"]  = body.sales_folder
    if body.sales_pattern is not None: cfg["sales_pattern"] = body.sales_pattern
    save_config(cfg)
    return {"ok": True, "config": cfg}


@router.post("/sync")
def sync_sales():
    cfg = load_config()
    if not cfg.get("sales_folder"):
        raise HTTPException(400, "Sales folder path not configured")
    with _sync_lock:
        _do_sync(cfg["sales_folder"], cfg.get("sales_pattern", "*.parquet"))
    st = load_status()
    if st["sales"].get("error"):
        raise HTTPException(500, st["sales"]["error"])
    return {"ok": True, "status": st["sales"]}


@router.get("/data")
def get_sales_data(limit: int = 500):
    if not SALES_CACHE.exists():
        raise HTTPException(404, "Sales data not synced yet")
    data = json.loads(SALES_CACHE.read_text())
    data["preview"] = data["preview"][:limit]
    return data


@router.get("/preview-folder")
def preview_folder(path: str, pattern: str = "*.parquet"):
    """List files in a folder so the user can verify the path is correct."""
    try:
        p = Path(path)
        if not p.exists():
            return {"exists": False, "files": []}
        files = sorted(p.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)[:20]
        return {
            "exists": True,
            "files": [
                {
                    "name":     f.name,
                    "size_kb":  round(f.stat().st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                }
                for f in files
            ],
        }
    except Exception as e:
        return {"exists": False, "error": str(e), "files": []}
