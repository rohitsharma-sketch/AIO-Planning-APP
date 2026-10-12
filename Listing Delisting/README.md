# Listing / Delisting Analyser — CityKart

Store × department listing history against sales, with festival- and season-aware delist / relist / held
suggestions. An additional tool of the RS Planning suite.

- **Open it:** `http://10.0.1.131:7800/listing/` (Landing, behind the suite sign-in).
- **Server:** `serve.py` — static `app/` on 127.0.0.1:8123 with `Cache-Control: no-cache` (the daily rebuild
  rewrites the JSON files in place). Landing launches and watches it; run by hand with `python serve.py`.
- **Tabs:** Overview, Suggestions, By Department, By Store; under More: Change Events, Seasonality,
  Data & checks, Rules (rule version log in `app/rules.js`).

## Data build (daily)

`Tentative AOP Forecaster/sync/listing_delisting_sync.py` (part of the 05:00 data-lake sync) runs, in order:

| Script (`scripts/`) | Writes (`app/`) | From |
|---|---|---|
| `build_knowledge_base.py` | `kb.json` | yearly listing workbooks, `RS_planning/data/listing/Directories/` |
| `build_sales.py` | `sales.json` | data-lake month-wise sales (path from `sync.sources['data_lake_sales']`) |
| `build_seasonality.py`, `build_season_category.py` | `seasonality.json` | sales.json, kb.json |
| `build_stores.py` | `stores.json` | planning DB store master (AOP's LfL rule) |
| `build_daily.py` | `data/listing/cache/daily.parquet` | data-lake day-wise export (rebuilt only when a newer one lands) |
| `build_suggestions.py` | `windows.json`, `suggestions.json`, `festival_trend.json`, `festival_trend/` | all of the above |

All generated files are git-ignored. `scripts/_paths.py` holds the paths; `extract_one.py` is the one-off
`.xlsb` → CSV extractor for rebuilding a yearly workbook from `data/listing/RAW/` (see `HANDOVER.md`).

Other apps read these files: the Re-Aligner (`kb.json`, `sales.json`) and the STR Forecaster (`build_daily`'s cache).

## Docs

- [PRD_ARCHITECTURE.md](PRD_ARCHITECTURE.md) — layout and functioning (start at "Current state"), dated change log.
- [PRD_LOGIC.md](PRD_LOGIC.md) — data and rule logic, dated change log.
- [HANDOVER.md](HANDOVER.md) — how the yearly listing workbooks were first extracted from the raw reports.
