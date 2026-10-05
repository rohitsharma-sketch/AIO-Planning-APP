"""Lagan (marriage muhurat) dates straight from Drik Panchang (New Delhi), cached in lagan-drik.json.

The Landing page's own astronomical engine checks tithi, weekday, Holashtak, Chaturmas, Navratri and
Pitru Paksha only - it does not know nakshatra, Kharmas (Sun in Dhanu / Meena), Guru / Shukra asta,
Adhik maas or yoga / karana, so it shows far more dates than Drik (2026: 99 vs 59). Drik is the source
of truth; the engine is only the fallback for a year that has never been synced.
Run: python lagan_drik.py 2000 2030   (re-sync a range of years)
"""
import datetime
import json
import os
import re
import sys
import urllib.request

URL = "https://www.drikpanchang.com/shubh-dates/shubh-marriage-dates-with-muhurat.html?year={}"
FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lagan-drik.json")
_DAY = re.compile(r'class="dpMuhurtaTitleLink">([A-Za-z]+ \d+, (\d{4})), \w+</a>\s*<img[^>]*alt="(\w+)"')


def parse(html, year):
    """{month: [days]} of the days Drik marks Auspicious. Raises if the page doesn't look like Drik's list."""
    days = [(d, a) for d, y, a in _DAY.findall(html) if int(y) == year]
    if len(days) < 300:   # Drik lists every day of the year; fewer means the page layout changed
        raise ValueError(f"Drik page for {year} has {len(days)} day rows - layout changed?")
    out = {m: [] for m in range(1, 13)}
    for d, a in days:
        if a == "Auspicious":
            dt = datetime.datetime.strptime(d, "%B %d, %Y")
            out[dt.month].append(dt.day)
    return out


def fetch(year):
    req = urllib.request.Request(URL.format(year), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse(r.read().decode("utf-8", "ignore"), year)


def load():
    try:
        with open(FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"years": {}, "synced": {}}


def refresh(years):
    """Re-fetch the given years from Drik and save. Returns (data, {year: error}) - a failed year keeps its old dates."""
    data, errors = load(), {}
    for y in years:
        try:
            data["years"][str(y)] = fetch(y)
            data["synced"][str(y)] = datetime.datetime.now().isoformat(timespec="seconds")
        except Exception as e:  # noqa: BLE001 - offline / Drik down: report it, keep the last good copy
            errors[str(y)] = str(e)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, FILE)
    return data, errors


if __name__ == "__main__":
    a, b = int(sys.argv[1]), int(sys.argv[-1])
    _, err = refresh(range(a, b + 1))
    print("synced", a, "-", b, "errors:", err or "none")
