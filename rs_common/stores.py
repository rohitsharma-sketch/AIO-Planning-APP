"""The ONE store-code alias (user, 2026-10-15: "change the names of 2 stores in all databases - NLD to NEG, KGP to MKG";
"Same stores - merge", "Yes - permanent alias"). The lake and old uploads still send the old codes; every place a store
code enters the suite maps it here, so the database only ever holds the new code.

Add a row when a store is renamed again: OLD -> NEW (upper case).
"""
ALIAS = {"NLD": "NEG", "KGP": "MKG"}


def canon_store(code):
    """Trimmed, upper-case store code with old codes mapped to the new one. None / NaN pass through unchanged."""
    if code is None or code != code:   # None or NaN
        return code
    c = str(code).strip().upper()
    return ALIAS.get(c, c)


def canon_series(s):
    """A pandas Series of store codes with old codes mapped to the new one, everything else untouched - vectorised for
    the lake's millions of rows (its codes are already clean upper case)."""
    return s.replace(ALIAS)


if __name__ == "__main__":   # python rs_common/stores.py
    assert canon_store(" nld ") == "NEG" and canon_store("KGP") == "MKG" and canon_store("abc") == "ABC"
    assert canon_store(None) is None
    print("ok")
