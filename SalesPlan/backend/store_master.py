# Universal Store Master
# Single source of truth for store -> cluster / tag / ref mapping.
# All engines import from here -- never read the file themselves.
# Source: the shared Postgres `stores` table (AOP Forecaster's db layer, schema
# `calendar`) — the same table AOP's Planning Inputs UI (incl. Ref Store Mapping)
# writes to. Previously read a standalone Excel file that could drift out of
# sync with Postgres edits; switched to the shared DB 2026-09-21 so a ref_store
# edit anywhere (UI or API) is visible to every app immediately.
# SSG rule: STORE TAG ends with "- Stores" (e.g. "032 - Stores", "080 - Stores")

from functools import lru_cache

SSG_OVERRIDE_STORES: set[str] = {"ANG"}


@lru_cache(maxsize=1)
def load_store_master() -> tuple[dict, ...]:
    """
    Returns a tuple of store-record dicts (immutable so lru_cache works).
    Each record: {Store, Ref Store, Cluster, Tag}
    Call list(load_store_master()) to get a plain list.
    """
    try:
        from sqlalchemy import select
        from db.base import SessionLocal
        from db.models.masterdata import Store as StoreRow

        with SessionLocal() as session:
            rows = session.execute(
                select(StoreRow).where(StoreRow.valid_to.is_(None))
            ).scalars().all()
            return tuple(
                {
                    "Store": (r.store_id or "").strip(),
                    "Ref Store": (r.ref_store or "").strip(),
                    "Cluster": (r.cluster_key or "").strip(),
                    "Tag": (r.tag or "").strip(),
                }
                for r in rows if r.store_id
            )
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
    """Force re-read from Postgres (clears lru_cache)."""
    load_store_master.cache_clear()
