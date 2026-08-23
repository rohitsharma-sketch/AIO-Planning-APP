"""Cluster-name resolution, shared by every write path into
`calendar.store_calendar_clusters`.

The store/cluster template names its clusters loosely ("KASHMIR", "NE",
"NE-PUJA") while the calendar side (calendar.cluster_profiles.name, and hence
calendar.calendar_day_pairs.cluster_name) uses the display spellings
("Kashmir", "N. EAST", "N. EAST - PUJA"). Every downstream consumer looks the
cluster up by exact string (DateShiftPreviewPanel's
`detail.dayMap[store.cluster]`, scans.reindex_*'s `cluster_ref_fut`,
store_actuals_sync's `cluster_month_map`), so an unresolved variant silently
drops those stores' rows.

The old app resolved this at read time via normalized name variants
(`_scmNorm`/`_scmVariants`/`scmResolveCluster`,
Calendar Engine/calendar_engine.html lines 2985-3000). That logic is ported
here and applied on WRITE instead, so store_calendar_clusters.cluster_name
always matches a real cluster_profiles.name and no consumer has to duplicate
the normalization.

This module deliberately has no dependencies beyond `re`: it is imported both
by router.py (FastAPI request path) and by migrate_from_json.py (standalone
script), and the latter must not have to drag in fastapi/auth/scans just to
resolve a cluster name.
"""
import re


def _cluster_norm(x):
    """'N. EAST - PUJA' -> 'neastpuja' (lowercase, strip everything non-alphanumeric)."""
    return re.sub(r"[^a-z0-9]", "", str(x or "").lower())


def _cluster_variants(name):
    """Normalized form plus its compass-abbreviated form, e.g. 'N. EAST' -> {'neast', 'ne'}."""
    n = _cluster_norm(name)
    abbrev = n.replace("north", "n").replace("east", "e").replace("west", "w").replace("south", "s")
    return {n, abbrev}


def resolve_cluster_name(raw, profile_names, aliases=None):
    """Map a raw/imported cluster name onto the real cluster_profiles.name it means.

    Explicit alias wins (same precedence the old app used), then an exact match,
    then a normalized-variant match against the known profile names. Returns `raw`
    unchanged when nothing matches — never invent a cluster that doesn't exist.
    `profile_names` should be an ordered sequence so matching is deterministic.
    """
    if not raw:
        return raw
    if aliases and aliases.get(raw):
        return aliases[raw]
    if raw in profile_names:
        return raw
    raw_variants = _cluster_variants(raw)
    for name in profile_names:
        if _cluster_variants(name) & raw_variants:
            return name
    return raw
