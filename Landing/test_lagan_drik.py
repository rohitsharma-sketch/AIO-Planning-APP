"""python test_lagan_drik.py - synthetic Drik page, no network."""
import lagan_drik as ld

row = lambda d, a: f'<a href="#" class="dpMuhurtaTitleLink">{d}, Monday</a> <img src="x.svg" alt="{a}" class="dpRowImage">'
days = [f"January {d}, 2026" for d in range(1, 32)] * 10            # 310 rows: enough to pass the layout check
html = "".join(row(d, "Inauspicious") for d in days) + row("February 5, 2026", "Auspicious") + row("February 6, 2026", "Auspicious")
out = ld.parse(html, 2026)
assert out[2] == [5, 6] and out[1] == [] and len(out) == 12, out
try:
    ld.parse(row("February 5, 2026", "Auspicious"), 2026)
    raise AssertionError("short page must be refused")
except ValueError:
    pass
print("lagan drik checks passed")
