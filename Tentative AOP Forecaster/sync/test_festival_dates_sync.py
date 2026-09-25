"""No-DB check: ICS parse + name mapping + derivations + overrides, the
re-date planner, and that a fetch failure is classed 'offline'.
Run: python sync/test_festival_dates_sync.py [path/to/basic.ics]
(defaults to the copy downloaded on 2026-09-24 into the audit scratchpad)."""
import datetime
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

import sync.festival_dates_sync as fds  # noqa: E402

ICS = sys.argv[1] if len(sys.argv) > 1 else (
    r"C:\Users\A9820\AppData\Local\Temp\claude\C--Users-A9820-Documents-CLaude---New-Projects-Buyer-s-Input-Sheet"
    r"\0918eae3-e799-439e-bcdc-0436bb46d685\scratchpad\cal_audit\india_holidays.ics")
D = datetime.date.fromisoformat

rows = fds.reference_rows(open(ICS, encoding="utf-8").read())
ref = {(r["festival"], r["year"]): r for r in rows}

assert ref[("Shraad", 2026)]["date"] == D("2026-09-26"), ref[("Shraad", 2026)]
assert ref[("Shraad", 2027)]["date"] == D("2027-09-15"), ref[("Shraad", 2027)]
assert ref[("Shraad", 2026)]["source"] == "derived"
assert ref[("Nuakhai", 2026)]["date"] == D("2026-09-15"), ref[("Nuakhai", 2026)]
assert ref[("Nuakhai", 2027)]["date"] == D("2027-09-05"), ref[("Nuakhai", 2027)]
# Indian dates, not global (India = global + 1 day for moon-sighted festivals)
for fest, iso in [("Eid al-Fitr", "2026-03-21"), ("Eid al-Adha", "2026-05-28"), ("Eid al-Fitr", "2025-03-31"), ("Milad-un-Nabi", "2025-09-05")]:
    assert ref[(fest, int(iso[:4]))]["date"] == D(iso) and ref[(fest, int(iso[:4]))]["source"] == "google", (fest, ref[(fest, int(iso[:4]))])
assert ref[("Chhath Puja", 2027)]["date"] == D("2027-11-05") and ref[("Chhath Puja", 2027)]["source"] == "override"
assert ref[("Diwali", 2027)]["date"] == D("2027-10-29") and ref[("Diwali", 2027)]["source"] == "google"
assert ref[("Kali Puja", 2027)]["date"] == D("2027-10-29")
assert ref[("Makar Sankranti", 2027)]["date"] == D("2027-01-14")
# Bohag Bihu: fixed 14 April every year (Google says 15 Apr in 2023/2025-2027)
bihu = {y: r for (f, y), r in ref.items() if f == "Bihu"}
assert bihu and all(r["date"] == datetime.date(y, 4, 14) and r["source"] == "override" for y, r in bihu.items()), bihu
assert all(f in {f for f, _ in ref} for f in list(fds.GOOGLE_NAMES) + list(fds.DERIVED)), "a mapped name found nothing"

# tentative suffix stripped; confirmed beats tentative regardless of order
ics = lambda *evs: "".join(f"BEGIN:VEVENT\nDTSTART;VALUE=DATE:{d}\nSUMMARY:{s}\nEND:VEVENT\n" for d, s in evs)
assert fds.parse_ics(ics(("20260101", "Holi (tentative)"), ("20260102", "Holi")))["Holi"][2026] == D("2026-01-02")
assert fds.parse_ics(ics(("20260102", "Holi"), ("20260101", "Holi (tentative)")))["Holi"][2026] == D("2026-01-02")
assert fds.parse_ics(ics(("20260101", "Holi (tentative)")))["Holi"][2026] == D("2026-01-01")

# re-date planner: only differing dates with a reference; each calendar uses its own years
row = lambda name, r, f: types.SimpleNamespace(name=name, ref_date=D(r), fut_date=D(f))
cal = types.SimpleNamespace(calendar_id=1, name="Old", ref_year=2025, fut_year=2026)
refmap = {("Holi", 2026): D("2026-03-04"), ("Holi", 2027): D("2027-03-22"), ("Holi", 2025): D("2025-03-14")}
changes = fds.plan_redate([(row("Holi", "2024-03-25", "2027-03-22"), "C1"), (row("Onam", "2024-09-15", "2025-09-05"), "C1")],
                          [(row("Holi", "2025-03-14", "2026-03-05"), "C1", cal)], refmap, "2026", "2027")
assert [(c["scope"], c["field"], c["new"]) for c in changes] == [
    ("Festival Master", "ref_date", "2026-03-04"), ("Calendar 1 Old", "fut_date", "2026-03-04")], changes

# fetch failure -> offline (sync_run records 'offline', table untouched)
from sync.common import _is_network_offline  # noqa: E402
import sync.common as common  # noqa: E402
fds._download = lambda: (_ for _ in ()).throw(OSError("getaddrinfo failed"))
common.call_with_timeout = lambda fn, **k: fn()  # skip the real retry delays
try:
    fds._fetch()
    raise AssertionError("expected ConnectionError")
except ConnectionError as e:
    assert _is_network_offline(e), e

print(f"test_festival_dates_sync: OK ({len(rows)} reference rows, years "
      f"{min(r['year'] for r in rows)}-{max(r['year'] for r in rows)})")
