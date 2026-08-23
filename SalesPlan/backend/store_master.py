# Universal Store Master
# Single source of truth for store -> cluster / tag / ref mapping.
# All engines import from here -- never read the file themselves.
# Source: Store Master\Store Master.xlsx
# Columns: Store Name | Ref Name - Merch | CLUSTER | STORE TAG
# SSG rule: STORE TAG ends with "- Stores" (e.g. "032 - Stores", "080 - Stores")

import os
import pandas as pd
from functools import lru_cache

STORE_MASTER_PATH = r"C:\Users\A9820\Documents\CLaude - New Projects\Store Master\Store Master.xlsx"

SSG_OVERRIDE_STORES: set[str] = {"ANG"}


@lru_cache(maxsize=1)
def load_store_master() -> tuple[dict, ...]:
    """
    Returns a tuple of store-record dicts (immutable so lru_cache works).
    Each record: {Store, Ref Store, Cluster, Tag}
    Call list(load_store_master()) to get a plain list.
    """
    try:
        df = pd.read_excel(STORE_MASTER_PATH, header=0)
        df.columns = [str(c).strip() for c in df.columns]
        col_map = {
            "Store Name":       "Store",
            "Ref Name - Merch": "Ref Store",
            "CLUSTER":          "Cluster",
            "STORE TAG":        "Tag",
        }
        df = df.rename(columns=col_map)
        for col in ["Store", "Ref Store", "Cluster", "Tag"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        df = df[df["Store"].notna() & (df["Store"] != "") & (df["Store"] != "nan")]
        return tuple(df[["Store", "Ref Store", "Cluster", "Tag"]].to_dict(orient="records"))
    except Exception:
        return tuple()


def is_ssg(tag: str, store: str = "") -> bool:
    if store and store in SSG_OVERRIDE_STORES:
        return True
    return str(tag).strip().endswith("- Stores")


def get_clusters() -> list[str]:
    return sorted({r["Cluster"] for r in load_store_master() if is_ssg(r["Tag"], r["Store"])})


def get_ssg_stores() -> set[str]:
    return {r["Store"] for r in load_store_master() if is_ssg(r["Tag"], r["Store"])}


def get_store_cluster_map() -> dict[str, str]:
    """Returns {store_code: cluster} for all stores."""
    return {r["Store"]: r["Cluster"] for r in load_store_master()}


def reload():
    """Force re-read of the file (clears lru_cache)."""
    load_store_master.cache_clear()
