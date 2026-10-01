"""Apportioning that always adds back (user, 2026-09-30: "give me the least apportioned difference all time in all
models across apps wherever apportioning is present").

Parts are kept at full precision - never rounded before they are summed or saved - and the float remainder of a
split goes to its largest part, so the parts add back to the total exactly (a difference that shows at 8 decimals
never appears). Rounding is for display only. SHOWN is the 8-decimal line every reconciliation check uses."""

SHOWN = 5e-9   # a difference below this prints as 0.00000000


def plug(parts: dict, total: float) -> dict:
    """Make the parts add back to `total` exactly by moving the float remainder onto the largest part."""
    if not parts:
        return parts
    k = max(parts, key=lambda x: abs(parts[x]))
    parts[k] += total - sum(parts.values())
    return parts


def split(total: float, weights: dict) -> dict:
    """`total` shared out in proportion to `weights` (>= 0); the parts add back to `total` exactly.
    All-zero weights -> every part 0 (nothing to split by - the caller decides what that means)."""
    w = {k: max(float(v or 0.0), 0.0) for k, v in weights.items()}
    tw = sum(w.values())
    if tw <= 0:
        return {k: 0.0 for k in w}
    return plug({k: total * v / tw for k, v in w.items()}, total)


def shares_pct(values: dict) -> dict:
    """Each value's % of their total, adding to exactly 100 (all zero -> all 0)."""
    tot = sum(values.values())
    if tot <= 0:
        return {k: 0.0 for k in values}
    return plug({k: v / tot * 100.0 for k, v in values.items()}, 100.0)


if __name__ == "__main__":   # python apportion.py - the checks
    p = split(10.0, {"a": 1, "b": 1, "c": 1})
    assert abs(sum(p.values()) - 10.0) < 1e-12 and abs(p["a"] - 10 / 3) < 1e-12
    q = shares_pct({"a": 1.0, "b": 2.0, "c": 3.0})
    assert abs(sum(q.values()) - 100.0) < 1e-12 and abs(q["c"] - 50.0) < 1e-12
    assert split(5.0, {"a": 0, "b": 0}) == {"a": 0.0, "b": 0.0} and shares_pct({}) == {}
    r = split(0.1 + 0.2, {i: 0.37 * (i + 1) for i in range(97)})   # awkward floats: still adds back
    assert abs(sum(r.values()) - 0.30000000000000004) < 1e-15
    print("apportion checks passed")
