# Universal Store Master
# Single source of truth for store -> cluster / tag / ref mapping.
# All engines import from here -- never read the file themselves.
# Source: the shared Postgres `stores` table (AOP Forecaster's db layer, schema
# `calendar`) — the same table AOP's Planning Inputs UI (incl. Ref Store Mapping)
# writes to. Previously read a standalone Excel file that could drift out of
# sync with Postgres edits; switched to the shared DB 2026-09-21 so a ref_store
# edit anywhere (UI or API) is visible to every app immediately.
# SSG rule = AOP's plan LfL (user, 2026-09-28): engine_v3.auto_tag - a trading store (SAME/NEW STORE)
# opened by 31 Dec before the LY window - so Sales Plan and AOP/BIS plan on the same 148 stores.
# Was: tag ends with "- Stores" + ANG override = 121, which missed the FY26 Q1-Q3 openings.

from functools import lru_cache

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
        from engine_v3 import auto_tag, LFL_TAGS

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
                    "SSG": auto_tag((r.tag or "").strip(), r.opening_date, r.store_current_status) in LFL_TAGS,
                }
                for r in rows if r.store_id
            )
    except Exception:
        return tuple()


def is_ssg(tag: str, store: str = "") -> bool:
    """AOP's LfL class for the store (tag kept for the callers' signature; the rule needs the opening date)."""
    return store in get_ssg_stores()


def get_clusters() -> list[str]:
    return sorted({r["Cluster"] for r in load_store_master() if r["SSG"]})


@lru_cache(maxsize=1)
def get_ssg_stores() -> frozenset[str]:
    return frozenset(r["Store"] for r in load_store_master() if r["SSG"])


def get_store_cluster_map() -> dict[str, str]:
    """Returns {store_code: cluster} for all stores."""
    return {r["Store"]: r["Cluster"] for r in load_store_master()}


def reload():
    """Force re-read from Postgres (clears lru_cache)."""
    load_store_master.cache_clear()
    get_ssg_stores.cache_clear()
