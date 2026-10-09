# RS Planning Suite — Changelog

Suite-wide changes across Calendar → AOP Forecaster → Buyer's Input Sheet (BIS) → Sales Plan.
Newest first. Each entry names its commit.

---

## 2026-10-09

### STR Forecaster: 4-month average first, months fold away
- **Asked (user):** "Give the months a collapsable ticker on the header so that i can view the 4 month avg in the first place and if i want then only i will see monthly changes"
- The forecast table opens on the 4-month average (Band, STR days, LY days, Plan qty, MDQ) only; the toggle on its header ("> Mar'27-Jun'27" / "< hide months") adds the month columns after it. The choice is remembered per browser. The department fixture editor keeps its months.

### STR Forecaster: Tag and Attribute as row layers
- **Asked (user):** "add Tag and Attribute as draggable layers too"
- "+ Tag" and "+ Attribute" chips in the Rows bar: drag them into any position (e.g. Attribute > Division > Department > Cluster > Store). Tag = the department's Core / Seasonal tag ("(untagged)" until set); Attribute = its own attribute, else the suite attribute master ("(no attribute)" if neither). Read live from the Department tags tab, so a tag change shows on the next load. Server: /api/rollup and its filters accept tag / attribute.

### STR Forecaster: drag-and-drop row layers that drill to any level
- **Asked (user):** "instead of the sepearate tab why dont you give a similar drag and drop function which drills to any level for STR similar to AOP forecaster ouput model"
- The Division / Department / Cluster / Store view buttons are replaced by a "Rows" layer bar like the AOP Output pivot: drag the chips to change the order, x drops a layer, "+ Layer" adds it back (or drag it into place). Each row opens (triangle) into the next layer, e.g. Division > Department > Cluster > Store; "Open to" opens every row down to a layer in one request per layer (guarded at 6,000 rows). Children load on demand and are cached; sorting applies at every level, header filters to the top layer; the All row adds up the top-layer rows shown. A pencil on any department row opens its store-level fixture editor. The band table click puts Department on top for that division and band; Revert restores the layers, open rows, filters and sort.
- /api/rollup takes any layer path (by=division,department,cluster); a department always carries its division.

### STR Forecaster: each cluster's own season curve, cluster filter, simpler notes
- **Asked (user):** "i like this suggestion - Store-level seasonality: use each cluster's own season curve from the day-wise sales, rather than one for the whole chain. Club it with their respective cluster and amalgamate the already present structure for a deeper meaning but simplified version of the app"
- New str_season.py: the Listing - Delisting Analyser's season method (day-wise data-lake cache, each store's calendar-cluster festival days left out, sales per festival-free open store-day, month vs that year's average, 2022-25 averaged) run per AOP cluster x department and chain-wide; a cluster leans on the chain curve where few of its stores sell the department (w = stores / (stores + 3)). Output season_cluster.json (gitignored), rebuilt by the server when the day-wise cache or the AOP store master is newer (hourly check); 11 s. Every store x department x month now takes its own cluster's season; roll-ups weight by plan qty. Replaces the chain-wide windows.json rates (e.g. KI_AP_JEANS Mar = normal 1.05, Apr-Jun off; NE - (P) R/N T-shirts dip in May).
- Cluster filter beside the division one: the table, the All row, the Division x band table, Revert and the Excel all follow it. Popup says which curve the season came from. The long note under the table folds into "Data notes".

### STR Forecaster: split departments by LY share instead of 50/50
- **Asked (user):** "split the plan by LY share instead of 50/50"
- The five old department names are now divided by each new part's share of last year's sales: the same store and month a year earlier, else the chain's that month, else equal. Pieces for plan qty, fixtures and MDQ; value for plan Rs. A store that sold only one part LY gives it the whole row. Old-department totals and the All figures are unchanged (All 54.5 days); e.g. MSE_PYJAMA 75% HSR / 25% TXTL, KB_T-SHIRT H/S 77% R/N / 23% POLO, KB_BERMUDA 42% HSR / 58% TXTL, LW_L_PALAZZO 58% WES / 42% ETH, LW_L_JEGGING 48% DNM / 52% WVN (4-month plan qty). Each pair's forecast and LY days now agree with each other.

### STR Forecaster: season-aware STR band (Listing - Delisting Analyser seasonality)
- **Asked (user):** "incorporate the seasonality trends from the Listing - Delisting Analyser App where peak seasons can be differentiated from the normal ones and STR can differ according to it"
- Season per department x month = its festival-free sales rate that month / its 12-month average (Listing app windows.json, 2022-25, refreshed nightly); peak >= 1.15, off <= 0.85 (the Listing app's own thresholds). Roll-ups take the plan-qty-weighted index. Mar-Jun'27: 366 peak, 58 normal, 28 off department-months.
- Band keeps the nearest-30 rounding; its limits follow the season: peak 30-90, normal 60-180 (base rule), off 90-180 (str_engine.SEASON_BANDS). "Season-aware band" toggle (on by default) switches back to the base 60-180 rule; Peak / Off badges on band cells; the calculation popup shows the season index and limits; the band count table follows the toggle; Excel adds season, season index and base band. Departments with no Listing history (KI_AP_BABA SUIT TXTL H/S, L_EW_SAREE_JAIPURI) count as normal.

### STR Forecaster: tag master import / export, AOP clusters, Division x band counts
- **Asked (user):** "1.)give me an import master and export master for department tags 2.) Add Clusters to Stores from AOP forecaster 3.) I need a small table indicating the Division and final STR Band ... when i click on the count of departments falling under that band the list automatically should filter out the specific departments and there should be a revert button"
- Department tags tab: "Export master" (GET /api/tags/download) = every department with Core / Seasonal, own attribute and the suite attribute master (info), plus a Read me sheet; the same layout imports back ("Import master" drop zone).
- Clusters from the AOP Forecaster's Store Master (config_store.get_stores, levers.json; all 180 stores have one): new Cluster view; Store view = Cluster + Store; Cluster column in the department detail and Excel (+ By cluster sheet). A save of the AOP store master refreshes it (version stamp includes levers.json).
- Division x final (4-month) band table above the forecast: counts of departments per band; clicking a count switches to the Department view filtered to that division and band (sorted by STR days); "Revert to previous view" restores the view, division, filters and sort you had before. "Clear sort & filters" also still clears.

### STR Forecaster: old department names split into the core apps' new departments
- **Asked (user):** "split these departments in the new departments as mentioned in the core apps, check it and reference back, split the plan equally in the new departments"
- The five names with no LY sales are split as in the suite's data-lake department split (same list as BIS DEPT_SPLITS / Listing / fill rate): KB_T-SHIRT H/S -> KB_R/N + KB_POLO T-SHIRT H/S; KB_BERMUDA -> KB_HSR + KB_TXTL BERMUDA; LW_L_PALAZZO -> LW_L_WES + LW_L_ETH PALAZZO; LW_L_JEGGING -> LW_L_DNM + LW_L_WVN JOGGER; MSE_PYJAMA -> MSE_HSR + MSE_TXTL PYJAMA. Fixtures, MDQ, plan Rs and plan qty are halved into each (at read time - stored uploads unchanged). Each new department now has its own LY sales, so all departments have LY days; plan qty / MDQ / forecast days unchanged in total (All 54.5 days), LY 54.5 -> 53.1 days. L_IN_BRA keeps its name (core apps carve L_IN_SPRT BRA out of it) and is not split.

### STR Forecaster: faster views, calculation popups, header sort / filter, full-month stores, department tags
- **Asked (user):** "1.) reduce toggle delay time and population time. 2.) It will be helpful if every department tile will have the calculation popup once clicked on it 3.)add filters and sort functions on headers remove the find bar 4.) Most likely the stores which have their plan and fixtures only qualify those. All months should be present in both sales and fixtures. 5.) Add a tab to add Core or Seasonal Tag to the department and Add Attribute to them. I will give the master so that you can tag each department with it"
- Speed: views 0.06-0.2 s (were 3-8 s) - rollup is one groupby (same figures, checked against the old code), upload rows and LY sales cached, the page keeps every view and loads the others in the background; department detail 0.15 s (was 2.4 s); Excel ~11 s (was ~66 s, xlsxwriter).
- Click any figure (main table, All row, department detail) for its calculation: plan qty, MDQ, average MDQ, days, qty per day, STR days, band, %, LY.
- Headers sort (click) and filter (value list, Band included); the find bar is gone; the All row adds up the rows shown.
- Only stores with every forecast month in both the fixture plan and the sales plan are compared (180 today; 9 with a missing month listed in the note).
- New "Department tags" tab: Core / Seasonal and attribute per department (planning_inputs.str_dept_tags, migration e5b9d2f1a7c3), from a tag master upload or edited in place; attribute defaults to the suite attribute master. Tag and attribute show (sortable, filterable) in the Department view and the Excel.

### AOP Forecaster: department split on Actual Sales Cont %
- **Asked (user):** "In the AOP Forecaster : change the cont% to break AOP into Department to Actual Sales Cont % instead of RE-indexed Cont %".
- Output's Department layer / filter now splits each store x division's Base and Forecast by the department's share of its ACTUAL LY sales in the same month last year (`/api/config/dept-mix?sale_type=actual`, calendar.sales_snapshots actual_dept), instead of the re-indexed share. Fallbacks unchanged (store mix over closed months; new stores = division network mix). Eff Sales / Eff Cont% / Eff Gr% and the "= Calendar total" rows stay calendarised (re-indexed) so they still match the Calendar. Division totals unchanged (checked: split adds back to 100%; e.g. AMG MENS R/N T-shirt Mar 16.8% actual vs 16.4% re-indexed). OutputTab.jsx splitByDept(leaves, mix, shareMix); dist rebuilt.

### STR Forecaster: STR band (60-180 days)
- **Asked (user):** "give me STR days according to the nearest round ranging from a store base minimum to 60 till 180 max after the actual STR is calculated."
- After the actual STR days are worked out, Band = the days rounded to the nearest 30 (half rounds up), kept between 60 and 180 (54 -> 60, 75 -> 90, 104 -> 90, 250 -> 180); per store x department x month and for every roll-up from its own actual days. New Band column (main table and department detail, actual and LY days alongside); Excel "STR band (days)" / "STR band". Step and limits = BAND_STEP / BAND_MIN / BAND_MAX in str_engine.py.
- Today: every division and month bands at 60 (actual 43-67 days); stores over Mar-Jun: 173 at 60, 15 at 90, 1 at 120.

### STR Forecaster: STR shown in days
- **Asked (user):** "STR should be in days like 60 Days, 30 Days etc."
- STR days = MDQ / (planned qty per day) - how long the minimum display stock lasts at the plan's selling rate (fewer days = faster sell-through; = days in month x (1 / STR - 1)). 4-month figure = average MDQ / planned qty per day over the months with data; LY days the same with LY sales qty (LY month lengths). Shown in the division / department / store table and the department detail; the % stays in the hover; Excel gains "days of cover (plan)" / "LY days of cover".
- Today (189 matched stores, Mar-Jun): MENS 45 days (LY 43), LADIES 58 (LY 61), KIDS 62 (LY 62), all 54 (LY 55).

### STR Forecaster: store-level sales plan, stores matched across both files (reviewed)
- **Asked (user):** "@MAMJ'26 - Sales Plan.xlsx use this" and "also map and match the stores which are availble in the fixture sheet too so that the comparison is apple to apple".
- New reader for the store-level plan (STORE_NAME, DIVISION, DEPARTMENT, "<Mon>'yy _V" Rs lakh / "_Q" pieces per month; MRP / ATTRIBUTE / TABLE-NON_TABLE rows summed; totals like "MAMJ'26_V" ignored); planned qty comes from the plan itself (Rs / LY price only where a row has no qty). Migration `d4a8c1e7f2b9` adds plan_qty to planning_inputs.str_plan_rows.
- Apples to apples: STR only over stores present in both the fixture plan and the sales plan; fixture-only / plan-only stores are listed with their MDQ / Rs. A plan whose months miss the fixture months now falls back to the fixture view with a clear message.
- Loaded the user's plan (upload 2, Mar-Jun'26 used as Mar-Jun'27 like the fixture file): 80,751 rows, Rs 508.6 Cr, 1.54 crore pcs; 189 stores in both (fixture only: BSC, GCG, GPG, LSR, MAR, RSG; plan only: BGP, BNP, DMH, GWL, LPA, RSN, SCL). Max STR vs LY STR (actual MAMJ'26, same stores and fixtures): MENS 40.6 / 41.5, LADIES 34.5 / 33.2, KIDS 33.0 / 33.0, all 35.9 / 35.9.
- Reviewed (approve): fixed the month-mismatch empty page and a combined-month total column being read as a month.

### STR Forecaster - new additional app (Landing > Additional tools, /str/, port 8085)
- **Asked (user):** "I want to make a STR Forecaster, the components will be - Total Fixture Plan on Store Wise x Month Wise, Minimum Density Qty, Sales Plan Month Wise. Add it in the additional APP section" (+ "this is the month wise fixture file"; "for the time being i will give you a sales plan tentative").
- Choices (user): STR = sales qty / (sales qty + fixture stock); store x department x month; Excel upload + edit in app; sales qty = plan Rs / LY avg selling price; forecast MAMJ'27 using the MAMJ'26 fixture file; GM left out (no Capacity / MDQ); storage = new DB tables.
- `STR Forecaster/` (str_engine.py, server.py, index.html; stdlib server like Growth vs LY): MDQ = fixtures x qty per fixture (the file's MDQ = MC_FIX x Capacity exactly; TABLE + NON_TABLE summed; missing MDQ = fixtures x the department's median); planned qty at LY price (store price needs >= 10 pcs and 0.5-2x the department-month price, then department-month, department, division-month); Max STR = qty / (qty + MDQ) over rows with both a plan and fixtures - labelled as the highest sell-thru the plan allows (stores at exactly MDQ), monthly, not comparable to the BIS weekly ST%; LY STR on the same formula and fixture plan over store-months that sold LY, departments with LY sales under their name.
- Views by division / department / store with per-month and 4-month-average columns, Excel export; department detail: store x month fixtures editable (planner / admin), one qty per fixture for a department (confirm), Reset to file; uploads choose "same months next year" or "as is"; roll back an upload. Edits are append-only (planning_inputs.str_edits, -1 = reset).
- Migration `c7e2a4f9b1d3`: planning_inputs.str_uploads, str_fixture_rows, str_plan_rows, str_edits (new tables only). Landing: APPS watchdog entry, /str proxy, card.
- Loaded the user's MAMJ'26 Fixture Allocation.xlsx as Mar-Jun'27: 71,570 rows, 195 stores, 120 departments; LY STR (same formula) MENS 41.1%, LADIES 32.7%, KIDS 31.4%, all 35.0%. Five fixture departments have no LY sales under their name (KB_BERMUDA, KB_T-SHIRT H/S, LW_L_JEGGING, LW_L_PALAZZO, MSE_PYJAMA) - shown, priced from the division until mapped. Sales-plan reader waits for the tentative file.
- Reviewed: code review (approve; fixed body-length check, failed-auth caching, Excel formula cells, explicit month shift, edit reset) and calculation review (fixed: STR labelled as a ceiling, 4-month avg label, LY excludes non-trading store-months and returns, price guards, plan/fixture leftovers kept out of totals, density Apply confirm).

### BIS: factor table - department preview, plain-language reasons, history check (reviewed)
- **Asked (user, 8-9 Oct):** "i want a preview pane to see if i choose matrix, weight builder or Continuous what will be my result before selecting the default factor matrix, simplify the picker as possible"; "i needed the pop up department on which factor does what and how ill it affect the department"; "add a proper reason in simple terms to aid the user to select the right model"; "i want the ml concepts to aid in the factor tuning and i also want a reviewed work"; "if you can embed something in the front end - factor table".
- Factor table top: pick a department; one table, factors as rows x Matrix / Weighted builder / Continuous as columns - the multiplier each factor applies and its Rs lakh effect on the department's Mar-Jun plan (log-share split, adds up to plan - plain share), "For this department" and "How it works" rows, a Suggested box (lowest back-test error) and Use this / Settings per column (replaces the old view tabs + Planner uses select).
- History check (advisory, never changes a factor): new `Buyer's Input Sheet/ml_assist.py` rebuilds 12 past planning cycles from calendar.sales_fact (like-for-like stores, BIS timing, COVID excluded) into ml_assist.json (gitignored); BIS server GET /api/planner/ml-assist + planner-only POST .../rebuild. In the factor table: "What sales history says" for the chosen department (growth / recent-momentum bands, a weak-evidence note when the method in use points the other way, a Ridge second opinion labelled not-for-decisions), "History check - all departments" (method factor vs history, flagged first, row click previews; 26 flagged under Matrix today), and in Continuous settings an honest walk-forward check of the growth strength (18.57% vs 18.62% no factor - within noise, so no change suggested; recent momentum 18.54%, also within noise).
- Reviewed: independent code review (no critical/high; fixed refresh-after-error and polling) and statistics review (fixed a one-month look-ahead, best-strength picked on its own test cycles, ridge record vs advice mismatch, reasons from imputed values, -100% growth, partial month, overclaiming wording); re-verified. Offline study report (Buyer's Input Sheet/ml_study, outside the repo) corrected to 6 unseen cycles: Continuous 0.20 18.47%, plain 18.62%, Ridge / RF / XGBoost 18.91-19.02%.

## 2026-10-08

### Suite: Undo / Redo in every app
- **Asked (user):** "Add an undo button feature in all apps, Forward and Backward."
- New `RS Planning Platform/backend/static/suite-undo.js`, served inside `GET /api/suite-theme.js` (which every app page already loads), so Calendar, AOP, Sales Plan, BIS, Listing, Re-Aligner, GR Plan Converter and the platform pages all get it with no per-app change.
- A small Undo | Redo pill (bottom-left) on any page with editable fields; Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z) when the cursor is not in a text box. Hover shows what it will undo; a toast says what was undone.
- Records every committed field edit (input / select / textarea / checkbox / slider) and puts values back as a normal edit (React and plain-HTML handlers both recompute). Undo does not save - each app's own Save still applies. Fields re-drawn by the app are found again by id / data-key / name / aria-label.
- Not covered yet: app actions that are not a field edit (Clear all, drag-and-drop, Re-seed, custom dropdowns such as the Ref Store picker).

### BIS: factor table - preview a department under each method, one simple picker
- **Asked (user):** "i want a preview pane to see if i choose matrix, weight builder or Continuous what will be my result before selecting the default factor matrix, simplify the picker as possible"
- Top of the factor table: pick a department (grouped by division); three cards - Matrix / Weighted builder / Continuous - each with the department's factor, its Phase 1 plan for Mar-Jun (Rs Cr and vs LY, every department of the division scored the same way and re-balanced to the AOP, as the planner does), the change vs plain AOP share, the back-test error and the reason. Draft edits show immediately.
- "Use this" replaces the old Planner uses dropdown (Save applies it); "Settings" replaces the view tabs. Checked: the Matrix card for MSE_R/N T-SHIRT H/S = Rs 29.39 Cr +12.4%, identical to the planner's own value.

### AOP Forecaster: Ref Store Mapping - readable % pop-up, visible scrollbar
- **Asked (user):** "it is difficult to see when i click on % and make the side slider stay visible and tangible"
- The % (division mix) pop-up is now pinned to the window beside the button (opens upward near the bottom), so the table's scroll box no longer clips it; larger text, right-aligned numbers, bigger close button, % button stays highlighted while open. Closes on outside click, scroll or resize.
- Planning Inputs tables get a wide (14 px), always-visible scrollbar with a solid thumb. Layout only.

### AOP Forecaster: Planning Inputs uses the full window
- **Asked (user):** "improve scaling on this" (Ref Store Mapping tab screenshot).
- Page width 1140 px -> 1560 px; the store tables (all Planning Inputs tabs) now grow with the window height (`max(440px, 100vh - 320px)`) instead of a fixed 440 px box. Layout only, no data or logic change.

### Listing / Delisting: festival trend - store-by-store table, links to the store history
- **Asked (user):** "instead of the dropping the graph in daily trend, i want to have some detailed tabular format to understand where can i see store wise change or make a hyperlink for a similar tab already existing in the module."
- Under the Daily trend chart: **Store by store** for the year picked (year chips): festival-day rate vs the days around it (each store's own cluster window), lift, last year's lift, change, festival-window sales, trading days and whether it is listed now; sortable; total row = the year table. Each store opens the module's existing store x department pop-up (listing history, monthly sales, why delist / relist) with "‹ Back to ... trend".
- Data: `app/festival_trend.json` is now an index (62 KB) + one file per department `app/festival_trend/dN.json` (238 files, <= 70 KB, loaded only when that department's trend is opened). Nightly Listing build +~2.5 min.
- ML_JEANS Dussehra 2025: 144 stores, all 1.93x (= year table); e.g. PNA 5.08x vs 6.04x in 2024, GWT 8.44x vs 5.26x.

### Listing / Delisting: Festival lift -> "Daily trend" for the department
- **Asked (user):** "if i were to see festival lift in detail can i get a link for the sales trend in the department".
- Seasonality tab, Festival lift table: every festival row has a **Daily trend ›** link. It opens the department's day-by-day sales from 14 days before to 14 days after the festival date, one line per year (2022 onwards, incl. 2026 where closed), per trading store-day, in the stores whose calendar cluster keeps that festival; festival days and build-up / after-days shaded (Festival Master windows). Below: per year the festival date and window, festival-day rate vs the days around it, the local lift and festival-window sales. Hover a point for its date, sales and stores.
- New nightly output `app/festival_trend.json` (build_suggestions.py; 238 departments, 46 festival-years, 1.2 MB, loaded only when a trend is opened).
- ML_JEANS Dussehra: 1.87x / 2.00x / 1.96x / 1.93x (2022-25) against the surrounding days (pooled table: 2.22x vs the same months' normal days).

### AOP base now read from the Calendar's multi-year sales (Phase 1)
- **Asked (user):** "once done, go ahead with phase 1".
- `sync/store_actuals_sync.py` (the AOP base: levers `store_actuals` and `store_actuals_fy26`) reads `calendar.sales_fact` instead of re-reading the parquet and repeating the reindex (14 s instead of a file read + reindex). Nightly order now: day weights -> multi-year sales -> AOP base -> Calendar reindex -> check (the multi-year loader works out "closed" itself, by the same rule on the same export).
- Tie-out before switching, cell by cell: FY26 placeholder (Mar'25-Feb'26) identical on 8,839 cells; base Apr'26-Aug'26 identical. Only Mar'26 label (TY Mar'27) moves, 15,482.1 -> 14,750.4 L = the Calendar's own Mar'27: the old sync kept all of Mar'26 there because it did not count Jan / Feb'26 as closed, so the 731.7 L of Holi days that land in Feb'27 (and Feb'26 days that land in Mar'27) were ignored. GM 2,305.3 -> 2,309.1, KIDS 4,272.5 -> 4,015.5, LADIES 3,509.8 -> 3,334.6, MENS 5,100.3 -> 4,825.3, RETAIL 294.3 -> 265.9.
- Saved AOP versions are unchanged (they keep their own inputs); a new session / re-run picks this up. Full nightly sync ran end to end on the new order - every check passed, including check 8.

### Calendar: multi-year calendar sales table (Phase 0 of "flow all sales ... from calendarised app")
- **Asked (user):** "flow all sales for actual and reindexed in all other apps from calendarised app"; "go ahead and plan the multi-year calendar sales switch"; "go ahead with phase 0".
- New table `calendar.sales_fact` (+ `calendar.sales_fact_load`, migration `b5d1e8f2a9c4`): every closed month as plain rows - **actual** Jan 2019 - Aug 2026 (91 months; Apr 2020 had no sales) and **reindexed** per saved calendar (2021 -> 22, 2024 -> 25, 2025 -> 26 all 12 months, 2026 -> 27 Jan-Aug) by the Calendar's own proportional split - at store x division x department x ATTRIBUTE1, value and quantity, plus the planning division. 2,825,818 actual cells, 518,515.77 L.
- Filled by `sync/calendar_sales_fact_sync.py`, now in the nightly sync before the check (first fill 8 min; past months frozen, only new / open months rewritten). Shared helpers `rs_common/divisions.py` (the one division roll-up) and `rs_common/calendar_sales.py` (the one reader apps will use).
- Nightly check 8 (all pass, exact): 8a every stored actual month = the export (109,536 store x division x month cells, 518,515.77 L both sides); 8b every calendar's reindexed months add back to their actuals (64,379 cells); 8c the live calendar's months = the Calendar's saved reindexed sales (15,721 cells, 85,301.74 L both). A restated old month now fails 8a instead of changing silently. No app reads the table yet (Phase 1 = AOP base).

### Divisions: DND -> RETAIL and NON FOOD -> GM everywhere; Version 2 fixed in place (DND + GM 10%)
- **Asked (user):** "Fix this issue of GM at 6% instead of 10% input"; "if you can add DND to the retail division and make the plan adjustments". Choices: NON FOOD = **GM** everywhere; **fix Version 2 in place**.
- One roll-up now in every app: DND (DND FASHION ITEM / DND GM ITEM) -> RETAIL; NON FOOD -> GM (was RETAIL in Sales Plan, the Calendar toggle and the AOP Eff columns; GM in the AOP base). Changed: AOP `sync/store_actuals_sync._norm_div` (+ store actuals re-synced), AOP `db/reindexed_base_sales`, AOP `dept-mix` (Eff Sales), Sales Plan `actuals_manager`, Sales Plan department master (29 NF_ departments RETAIL -> GM in `department_custom.json` / `department_state.json`, settings kept), Calendar "Planning divisions only" (now includes DND). Still not planned: NON-TRADING, FIXED ASSETS, CONSIGNMENT, CDIT. BIS (MENS / LADIES / KIDS only) unaffected.
- **Version 2** (live, locked): its own inputs got each store's LY DND sales in RETAIL (Mar-Aug'26, +2.6 to +9.7 L a month, 161 new RETAIL rows) and it was re-run with GM Apr-Jun'27 at 10% (was 6%), rest of its growth unchanged; re-saved as Version 2. LfL GM Apr'27 2,127.6 -> 2,207.8 L (+10% on 2,007.1), RETAIL base +DND; KIDS / LADIES / MENS unchanged to the decimal, so the published MAMJ (43,186.79 L) and Lock to Planning (KIDS / LADIES / MENS) are unchanged. Backups: `Backups\aop_v2_session_before_dnd_gm_*`, `aop_v2_state_before_dnd_gm_*`, `salesplan_department_*_before_nonfood_*`.
- AOP base vs Eff Sales now agree for GM and RETAIL Apr-Aug'27 (within 0.1 L; Mar'27 differs only because Version 2's base predates today's proportional split).

### AOP Output: reconciliation rows to the Calendar ("+ Not in plan" / "= Calendar total")
- **Asked (user):** "How will i know about DND and such cases where there will be a slight difference either make such a provision in the output tab too to know why is there a slight difference in sales from the calendarised app."
- Under Grand total (Eff Sales columns, every month + Total): **+ Not in plan (DND, NON-TRADING, FIXED ASSETS ...)** = calendarised sales of the divisions planning leaves out, for the stores in view (hover = by division), and **= Calendar total** = Grand total + those = the Calendar's Month Wise Matrix with "Planning divisions only" off. Shown when no Division / Department filter is on. `dept-mix` now also returns those divisions (`other`) and keeps plan-division rows with no department as "(NO DEPARTMENT)".
- ALC Mar'27: Eff 169.76 + DND 0.43 = 170.19 L = Calendar. All 1,449 store-months tie within Rs 180.

### Calendar: Month Wise Matrix "Planning divisions only" toggle
- **Asked (user):** "where to see 169.8 March sales in ALC in calendar ?" then "add the planning divisions only toggle".
- A checkbox next to Download XLSX: on = only the five planning divisions (MENS, LADIES, KIDS, GM's Footwear / Household / Lifestyle / Home Furnishing / Sports & Toys / Stationery / Travel Accessories, RETAIL incl. Non Food); DND, non-trading, fixed assets etc. left out - the figures AOP (Eff Sales), BIS and Sales Plan use. Remembered per browser; the store heading and the XLSX file name say when it is on.
- ALC TY Mar'27: 170.19 L (all) -> 169.76 L (planning divisions) = AOP Output Eff Sales.

### AOP re-run on the new base - Version 3 (live; Lock to Planning still on Version 2)
- **Asked (user):** "rerun the AOP forecast with the new base"; "go ahead and rerun the AOP forecast".
- Fresh session from the DB (today's store actuals = proportional calendarised split, data to 28 Sep month-wise / 7 Oct day-wise; closed through Aug'26), run with Version 2's own growth settings, saved as **Version 3 — 08 Oct 2026** (now the live AOP BIS reads). Lock to Planning untouched (Version 2, MAMJ 43,184.66 L). Backup: `Backups\aop_before_rerun_20261008_145928.json`.
- LfL (Rs L): Mar'27 base 13,694.3 -> 13,201.3 (Holi days of Mar'26 now land in Feb'27, outside the plan year); Mar'27 forecast unchanged 15,624.2 (the March override); Apr-Aug unchanged within 1 L; Sep'27 base 0 -> 8,701.2 / forecast 9,223.2 (Sep'26 now in the base - month-wise file stops at 28 Sep, so about 4.8% short until the next export). Live MAMJ 43,185.67 L, LfL growth 12.5%.
- NSO (97 stores): each store's 750 L ramp is now spread over its whole first year in the reference store's (LAM) shape - Version 2 had no LAM forecast after Aug'27, so it was packed into Mar-Aug. Apr-Aug NSO 24,888 -> 17,571 L; full-year NSO 29,481 -> 46,667 L. Ramp FY27 - Q1 stores +161 L Apr-Aug.

### AOP Output: Eff Sales / Eff Cont % / Eff Gr% columns + Department filter (Departments tab and sale-type switch removed)
- **Asked (user):** "instead of reindexed and actual sales switch, add 2 columns named Eff Sales, Eff Cont % and Eff Gr% in Output. Month Wise and Total Both"; "Remove the separate departments tab and add the department filter field in the output tab only"; "All sales should match with calendarised sales on month level make sure of that".
- Output now has three more values (on by default, every month + Total): **Eff Sales** = the Calendar's calendarised (reindexed) LY sales of the row, **Eff Cont %** = its share of the row above, **Eff Gr%** = Fcst vs Eff Sales. '—' where the LY month has not closed yet.
- **Department** is a filter field in the bar (dashed, like Tag / Cluster) - drag it onto the header to add the layer. With it on, each store-division's Base and Fcst are split by the department's share of its Eff Sales in that month (totals kept exactly). The separate Departments tab and the Reindexed | Actual switch are gone.
- Tie-out vs the Calendar (store x month, Mar'27-Sep'27, 2,233 checks): largest gap Rs 180; network within Rs 7,000 a month (e.g. Mar'27 14,741.20 L both). Only the non-planning divisions (DND etc., 2.8-9.8 L a month) are left out, as everywhere in planning - e.g. ALC Mar'27 Eff 169.76 L = Calendar 170.19 L - DND 0.43 L.

### Landing: "Sync all data" in the account (admin) menu
- **Asked (user):** "give me a sync button to start refresh all syncs in the admin button on the landing page - so that i can manage the console better."
- Admins only (like Users & access; greyed out for anyone whose "data sync" right is off). One click starts the database sync (`sync/run_all.py`: site / store master, store actuals, day weights, Calendar month-wise reindex + check, day-wise reindex, festivals, Listing / Delisting) and Buyer's Input's sales, sell-through and history syncs, all from the newest data-lake files, then opens the Data sync panel to follow each source. The label shows when it started, or which part could not start.

### AOP Forecaster: Results "Departments" tab - division forecast split by LY department contribution
- **Asked (user):** "i want a similar tab where the aop forecast decided on division will be bifurcated on reindexed cont % and will be multiplied by the aop forecasted"; "give me a similar tab filter for sale type - reindexed or actual sales"; "yes go ahead and build it".
- New tab next to Output, same pivot (Month / Type / Division / Tag / Cluster / Store filters, quarter bands, ₹ L / Cr) plus a **Department** layer, a **Sale type** switch (Reindexed / Actual) and a **Cont%** value (share of the row above).
- Department Fcst = each store's division forecast × the department's share of that store-division's LY sales in the same month: Reindexed = the Calendar's festival-aligned department sales on the TY month, Actual = the same month last year on its own dates (`GET /api/config/dept-mix`). LY column = those sales. Months without closed LY sales use the store's mix over the months that have it; new stores (no LY) use the division's network mix.
- Checked on the live session: 1,595 store-division rows -> 140,416 department rows (539 departments); every store x division x month forecast kept exactly (132,172.72 L in = out) for both sale types. ALC MENS Mar'27 78.19 L -> ML_JEANS 11.67 L reindexed (MSE_R/N T-SHIRT H/S 12.65 L on actual).

### Calendar: 2025 -> 2026 calendar approved and backed up
- **Asked (user):** "make sure the calendar version is saved now. This calendar is perfect."
- Confirmed saved: "2025 -> 2026 Calendar - All" (id 1791441518950, saved 8 Oct 12:08) is the only 2025 calendar, so it is what the Calendar, AOP and Sales Plan read. 10 clusters x 365 days, no LY day used twice, year-alignment check PASS, day-map fingerprint `f4dafc4c1aaf36cc`. Dated copy: `Backups\calendar_2025_2026_APPROVED_20261008_141544.json`.

### Calendar: every pop-up is a whole month, day 1 to the last day
- **Asked (user):** "pop up okay i want the whole month from 1 - 30 days of the month , 1- 28/29 day detail for frb"; "make it for all months wherever shift is there and colored cells are there".
- Clicking any cell (every tinted / shifted cell, any month) now opens its **whole TY month**, every day from the 1st to the last, with the clicked cell's days outlined and a "clicked cell" line (its days, rupees, share). Two buttons flip to the cell's **whole LY month**. Ref Month labels open the whole LY month; TY headers / totals open the whole TY month.
- Checked on the 2025 -> 26 calendar (UP + NCR): all 12 TY months and all 12 LY months list day 1 to the last day (Feb = 28) and every cell ties; Mar'25 -> Feb'26 opens Feb'26 with 28 days (18 from Feb'25, 10 from Mar'25 highlighted). Commit `0b10198`.
- **All calendars (user: "build for all calendars not just 25-26, make the features which have been changed for all calendars - new or old"):** nothing is calendar-specific - pop-ups, the proportional split, saved runs and the alignment check work on whichever calendar is picked. Checked every saved calendar (2021 -> 22, 2024 -> 25, 2025 -> 26, 2026 -> 27) x 10 clusters x 24 month views = 960 pop-ups: all list day 1 to the last day and tie. A day with no partner now gets its own row instead of being skipped: in 2024 -> 25 (2024 has 366 days) 1 Feb 2024 has no TY day, listed as "No TY day takes this day; its sales stay in the month total". 2021 and 2024 have no daily sales, so their pop-ups split by day count (said in the pop-up).

### Calendar: day table is a pop-up, and whole months open too
- **Asked (user):** "instead of the down bar - i need it as a pop up when i click also i need it for the whole month mapping like the whole of Feb, the whole of whichever month is there which is clicked so that the month detail can be made visible for view".
- The day-by-day table now opens as a pop-up (Esc, ✕ or a click outside closes). Three ways in: a tinted **cell** (as before); a **Ref Month** label (every day of that LY month and the TY month each one went to); a **TY month** header or its total (every day landing in that TY month and the LY month it came from). Whole-month views add a "Cell" column, a "why ordinary days moved" line per moved cell and a subtotal per cell.
- Checked (LAD, 2025 -> 26): all of Feb'25 = 28 days -> Feb'26 18 + Mar'26 10, Rs 1,00,23,118 ✓; everything landing in Mar'26 = 31 days <- Feb'25 10 + Mar'25 19 + Apr'25 2, Rs 1,53,44,425 ✓.

### Calendar: saved runs open without Run Reindex; past calendars have no Re-index
- **Asked (user):** "also cache the previous ran versions so that all previews ready to view instead of running re-index evertime the calendar is loaded. For current template like 26-27 or related to future you can perhaps ask for re-index push button but not for all the templates which belong to the past".
- Picking a calendar on Calendarised Sales now loads its last run straight from the month cache (new `POST /salesdata/reindex/saved`, no data-lake read - 2025 -> 26: 12 months in 0.7 s). A **past** calendar (every reference month closed) shows "Past calendar - saved run shown" and no button; the current / future one (2026 -> 27) shows **Re-index**. Saved runs were filled for every calendar with the page's fields (Sales Value, no extra fields): 2021 -> 22, 2024 -> 25, 2025 -> 26 all 12 months (past, 0.3-0.6 s to open); 2026 -> 27 Jan-Aug (Sep-Dec not closed - Re-index fills them). Commit `2270d08` (all three entries above).
- **Day-wise too (user: "also save the dw runs for past calendars"):** saved for 2021 -> 22, 2024 -> 25 and 2025 -> 26, all 12 months each (a fresh day-wise run took 4.5 / 12 / 16 min; the saved one opens in 1.4 / 2.3 / 2.9 s, 18,520 / 37,563 / 49,021 rows - well under the 300,000-row cap). 2025 -> 26 day-wise totals 113,812.31 L vs month-wise 113,814.88 L. 2026 -> 27 (current) is not saved for day-wise - Re-index as before.
- A one-month run now splits that month exactly as a full-year run does (the "closed months" for the split are the calendar's, not just the run's).

### Month-wise reindex: proportional split (AOP's rule) instead of whole-month
- **Asked (user):** "yes go ahead with the split switch" (option chosen: switch to AOP's rule; also AOP's store actuals sync and the nightly check; regenerate the snapshots).
- Each reference month's sales now spread over TY months by the actual sales of its days landing in each (day count where a month has no daily data) - the same split as the Month Wise Matrix and AOP's festival shift. Was: the whole month to the TY month most of its days fall in. A month not closed yet (and a closed month feeding the same TY month) keeps the whole-month rule until it closes (`db/calendar_shift.month_plan`).
- Snapshots regenerated, live 2026 -> 27 calendar (lakh): Feb'27 9,270.54 -> 10,002.22 (+731.69), Mar'27 15,482.22 -> 14,750.54 (-731.69), Jun'27 -0.92, Jul'27 +0.92, every other month unchanged (Sep'27 9,540.27), total 108,358.06 unchanged; actuals unchanged (108,679.61). Nightly calendar check: all passed. store_actuals_sync re-run with the same split. Backups: `Backups\sales_snapshots_mw_before_split_20261008_122146.json`, `Backups\input_values_store_actuals_before_split_20261008_122146.json`.

### Calendar: click a Month Wise Matrix cell for the day-by-day table
- **Asked (user):** "when i click on the colored cell i want a day wise breakup for the store which is live, and is more detailed than the hover comment. Keep the hover comment on for summarised version but when the user clicks on it then it should give a detailed date wise tabular format so that they can navigate to the reasoning with numbers".
- Hover keeps the summary. Clicking (or Enter on) any non-zero cell opens a panel under that store's table: every day of the ref month that landed in the TY month - LY date / day, TY date / day (weekday change in amber), shift in days (+364 = same weekday last year), why (festival build-up / festival days / after-days with both years' festival dates, or ordinary day re-placed + the chain of festival moves behind it), the cluster's day sales the split is weighted by, the day's share and the store's rupees. Total row adds up to the cell (tick). Esc or Close shuts it; clicking the same cell again closes it.
- Checked on real data (LAD, fixed 2025 -> 26 calendar, UP + NCR daily sales): Mar'25 -> Feb'26 10 days Rs 59,27,653, -> Mar'26 19 days Rs 1,13,79,162, -> Apr'26 2 days Rs 9,67,262 - rows add up to each cell. (lib/moveReasons.js dayBreakup; the matrix now gets the full day map + day sales.)

### Calendar engine: year-end wrap fixed + a year-alignment check for every calendar (saved or unsaved)
- **Asked (user):** "check if the rule mentioned in this matrix is right or is it reversed"; "why is it the holi shift needs apr days ?"; "yes fix the calendar and show me before/after"; "make a check for this issue in the system"; "for all calendars - saved or unsaved".
- Finding: the matrix direction is right (LY day -> TY day). Holi is right too (ref 1-10 Mar 2025 -> TY 19-28 Feb 2026, offset 355, as the user's reference calendar). The real fault was in the **2025 -> 2026 calendar**: TY 1-5 Jan 2026 were filled from ref 26-31 Dec 2025, so almost every day ran a week late (+371 instead of +364, 1,287 vs 747 days) and each month's last week spilled into the next (e.g. ref 17-26 Mar -> TY 1-8 Apr). The 2024 -> 25 and 2026 -> 27 calendars were fine.
- Cause (engine V2): the one-to-one assignment measured month and day distance with a wrap (December counted as the month before January, 26 Dec as 7 days from 2 Jan). In 2025 -> 26 the big festivals move ~19 days later, the September shortage was borrowed month by month back to January, and January took the reference year's December. Fix: distances inside the year, no wrap (`engine.js` _v2Remap cost).
- Before / after, 2025 -> 2026, all 10 clusters (3,650 days): same date as the user's reference 1,055 -> 2,210; same month 2,404 -> 2,779 (66% -> 76%); same weekday 2,834 -> 2,854; reused LY days 0 -> 0; most common shift +371 -> +364. LAD (UP + NCR): Jan, May-Aug and Dec 2025 now stay whole in their own TY month; only Holi and the Sep-Nov festival season move. The 2024 and 2026 calendars rebuild identically.
- **Check, everywhere:** two rules - no day moved 3+ months (year-end wrap) and "same weekday last year" (364 days per year) is the most common shift (no weekly drift).
  - Unsaved: the engine's Validation shows them as errors, and Generate checks all clusters at once ("OUT OF LINE with the year in: ...").
  - Save: POST /calendar-library refuses a failing calendar (422 with the clusters and reasons) from any screen - tested with the saved 2025 calendar (refused, nothing written).
  - Saved: nightly calendar_check check 7 scans every saved calendar - today it flags only "2025 -> 2026 Calendar - All" (9 clusters) until it is replaced with the fixed version.
- Tests: engine.test.mjs test11 (real 2025 -> 26 festivals clean; planted wrap and week drift caught), calendar_check_sync --test (alignment cases). **Replaced (user: "Replace it"):** the old calendar (3,650 pairs, 10 clusters, 62 festivals) is backed up to Documents/CLaude - New Projects/Backups/calendar_2025_2026_before_fix_20261008_120838.json; the fixed rebuild was saved through the normal save path (passes the check) as calendar 1791441518950, same name, and the old one deleted. Verified: check 7 PASS for all 4 saved calendars; the saved 2025 -> 26 calendar = 2,210 days equal to the reference, 76.1% same month, +364 most common; LAD TY 1-3 Jan <- ref 2, 3, 1 Jan 2025.

### Calendar: Month Wise Matrix totals row
- **Asked (user):** "need a total of months in the bottom row". Bottom Total row per store: Ref Actual Sales, every TY month, Split Total (tick when it equals Ref Actual Sales); a Total row per store in the XLSX download too. Display only.

### Calendar: Month Wise Matrix rows now tally (Split Total column)
- **Reported (user, LAD screenshot):** "the split shows waywardness - check how the total is not tallying up. It should tally up".
- Cause: the matrix showed only the TY months of the run's own output, but a reference month's sales are split over every TY month its days land in. A share landing in a month the run didn't output (here 2026-02) was worked out but had no column, so e.g. 2025-01 (Rs 1,18,09,539) showed only Rs 1,01,07,891.
- Fix: columns = every TY month any split lands in; new **Split Total** column with a check mark when it equals Ref Actual Sales (red cross + the difference on hover otherwise). Same in the XLSX download. Numbers unchanged - nothing was lost, it just wasn't shown.

### MRP Re-apportionment: audit fixes, progress bar, output check indicator, lighter output colours
- **Asked (user):** "audit the mrp re-apportionment module"; then "NO PROGRESS BAR, NO output check indicator, install it"; "give better colors in the output file"; and confirmed the master can be imported as a 4-column list (Department, Display Type, Current MRP, Listed MRP - already supported).
- Audit (3 reviewers: engine, security, page; criticals none). Fixed:
  - **Sales silently dropped (found while testing):** pandas' str dtype keeps blanks through astype(str), so the pivot dropped every row with a blank DISPLAY_TYPE / ATTRIBUTE1 - Rs 181.13 L of sales never reached the run, while the tie (checked on the raw rows) passed. Blanks are now "(BLANK)" (they land in Unmapped), and the tie runs on the table the run actually uses (now 245,872 cells, 56,646.33 L = Calendar, max diff 0.0). The master's departments were not affected (41,062.26 L before and after).
  - Sales tie cached on the sales file alone: a later Calendar snapshot never re-ran it (red until restart). The cache key now includes the snapshot time.
  - Red pre-run checks were enforced only by the page: /run now refuses them itself (409 with the fix). One run or master import at a time (409 "in progress"). A master whose departments have no sales is refused (400) instead of saving a FAILED run.
  - Import: unsafe file names made safe (CON.xlsx, ".xlsx", ':' or '<'); the new file is placed before the old one is archived and the old one is put back if placing fails; archive names carry microseconds; 50 MB cap; negative MRPs refused; a blank current MRP row is dropped (was MRP 0).
  - Checks: store x dept totals in lakh (rupees at 8 dp is below float noise); month totals per store x dept x month (was one total per month); new **split** check re-derives every discontinued MRP's split a second way (merge_asof) - 30,569 rows, a swapped 40/60 turns it red.
  - Page: Import is a real button (keyboard / screen reader); errors read as one line whatever comes back (HTML 502, FastAPI 422 list); every reload starts fresh and only the newest answer lands; a refused run reloads the checks; Import and Run can't overlap; download links stay on the page if a file is missing.
  - Stand-alone Sales Plan scripts (start.bat, watchdog.ps1, install_service.ps1, port 8002, no sign-in) bound to 127.0.0.1 - not running today, but would have been open to the LAN.
- **Progress bar + output check indicator:** GET /progress (step, %, elapsed, output checks); the page polls it while a run goes - Pre-run checks, Reading master and sales, Re-apportioning, Output checks, Writing the Excel file (with its own %), Saving, Done. The five output checks show with a tick / cross as soon as they're done (while the Excel is still being written); after the run "Output checks 5/5 passed - see results". A run started from another tab shows too.
- **Output file colours:** light "ink and paper" like the app instead of dark rows: deep-green header, old MRP red, new MRP bold green, split shares amber (e.g. 40%), sales 2 decimals with "-" for zero (values still full precision), wider columns (headers no longer wrap), Validation PASS green / FAIL red, readable Engine Log, coloured tabs.
- Tests: module test (incl. the real tie catching a planted Rs 2,000, import, post-checks) and end-to-end on temp folders (busy 409, red-check 409, unsafe names, rollback, 413, negative MRP, empty sales, progress feed) pass. Not done (low): error texts still show server paths (behind sign-in); output folder never pruned.

### MRP Re-apportionment: keep last good run + run history
- **Asked (user):** "add keep last good run and run history".
- Every run is logged in `Output\_run_history.json` (time, MRP master, sales file, checks, totals, output file; newest first). A run whose checks fail is saved as `MRP Reapportioned <time> - FAILED.xlsx` and never becomes the default download: `GET /download` gives the newest run that passed (`?file=` any run from the history; names outside the output pattern refused). New `GET /runs`. File names now carry seconds (two runs in one minute overwrote each other).
- Page: last-run banner says when the last run failed and that Download gives the last good run; results' download is marked "FAILED - not for use" for a failed run; Run history panel (★ = what Download gives, per-run download).
- Fixed on the way: `/status` never returned `has_result`, so MRP Plan Output always showed Re-apportionment as Pending; it now means "a run has passed its checks".
- Checked through the real endpoints on a temp output folder: good run, then a planted failed run -> saved as FAILED, history lists both, default download = the good one, `?file=` gives the failed one, `../` names refused, `has_result` true. Page checked in the built app with stub data.

### MRP Re-apportionment: checks built in (red stops Run, each says how to fix and re-run)
- **Asked (user):** "how can checks be embedded in this - and how can we rerun if the checks are not passed ?" -> chose the checks strip + blocking.
- Before a run (`GET /checks`, shown above Run): MRP master readable (red if not), LY sales tie to the Calendar department sales (red if not), share of LY sales on MRPs in the master (amber), Dept x Display with nothing listed (amber). Red disables Run (the endpoints refuse it too); every non-green item says what to fix, then Refresh -> Run again.
- After a run: store x dept totals and month totals (before = after + Unmapped, to 8 decimals in lakh), each old MRP's shares add to 100%, every new MRP is a listed MRP of its Dept x Display. Any red = run marked FAILED - not for use (CHECKS card, last-run banner, Engine Log sheet).
- Today's data: master ok, tie ok (212,813 cells, 0.0 L); amber - 45.43 L on old MRPs not in the master, 149 of 284 groups with nothing listed (192.47 L) -> Unmapped. Run: all four post-run checks green. Planted faults turn each post-run check red; no master -> red with the fix. The first live run caught a false alarm (Rs 0.00000024 float noise on a ~Rs 1,000 Cr month compared in rupees) - month totals now compared in lakh like the suite's other ties.

### MRP Re-apportionment: Groups list showed empty strips
- Reported (user, screenshot): 284 blank lines in MRP Groups. The cards sat in a fixed-height (520 px) flex column and were shrunk to their borders; `flexShrink: 0` on each card. Checked in the built page with 284 stub groups: every card 113-171 px with its content, list scrolls.

### Right: "Import a new MRP master"
- **Asked (user):** "yes add the right for mrp master import".
- New right `mrp_master` (auth/rights.py) - an admin can switch it off per person in Users & access. Landing GUARDED blocks `POST …/mrp-reapportionment/mapping/upload` without it (403 with the reason); Export and Run stay open. The MRP page reads `/api/auth/rights` and shows Import switched off (with the reason on hover) when the right is off.
- Tests: Landing `test_rights_guard.py` (upload guarded, download / run not), platform `tests/test_rights.py` pass. Landing + 8010 restarted; unauthenticated upload via 7800 -> 401.

### Sales Plan › MRP Re-apportionment: import / export the MRP master
- **Asked (user):** "what if i have a new version for mrp mapping master ? Importing and exporting feature - add it".
- MRP Mapping Master card: **⇪ Import new version** (.xlsx, confirm before replacing) and **↓ Export current**. `POST /mapping/upload` reads the file with the same reader a run uses (wide "MRP Adj" grid or plain list) before it goes live - an unusable file changes nothing; the replaced version moves to `MRP Mapping\Archive\<YYYY-MM-DD HHMMSS> <name>` (kept, never overwritten). The reply says what changed vs the previous version (old MRPs added / removed / given a different new MRP) and how many Dept x Display have nothing listed. `GET /mapping/download` returns the active master exactly as uploaded.
- Checked through the real endpoints on a temp folder (bad file 400 + folder unchanged; v1 5,837 rows; v2 2 added / 1 removed / 2 changed, v1 archived; export byte-identical); repo test `engines/test_mrp_reapportionment.py` covers it. The live mapping folder was not touched.
- Answered: the LY Actual Sales here are the sales engine's data-lake file (Calendar reader), tied cell by cell to the Calendar `actual_dept` snapshot before every run - actual bill-month sales, not the reindexed LY the department plan uses.

### Sales Plan › MRP Re-apportionment: faster Excel export
- **Asked (user):** "yes speed up the excel export" (a run took ~7 min, nearly all of it writing the workbook).
- `_build_excel` now writes with xlsxwriter (already used by the Sales Plan engines): one format per column, row banding as a single conditional format, instead of openpyxl styling ~3.4 M cells one by one. Same five sheets, columns, number formats and colours.
- Real LY run: export 590.5 s -> 42.1 s; every sheet read back identical to the old export (Reapportioned Sales 140,409 rows, Unmapped 9,539, Original Sales 136,589, Validation, Engine Log).

### Sales Plan › MRP Re-apportionment: the planners' MRP master rule
- **Asked (user):** the MRP master design ("MRP MASTER - 27-04-2026 - New(Shubham).xlsx") that suggests the new MRP by Department x old MRP x Display, built into the existing Sales Plan module (not a new app). Decisions: replace the old method; PreWinter / Winter split like Regular; a Department x Display with nothing listed -> Unmapped; LY Mar-Jun 2026 sales from the sales engine.
- Rule: a listed old MRP moves to its new MRP; a discontinued one splits to the nearest listed MRP below / above (old MRPs in value order within Department x Display): 40/60 (Regular, Occasional, all Winter), 60/40 (Summer); one side only -> 100%. Was: spread over every listed MRP of Department x Display x Attribute, equal or typed %s (the %-editor is gone; the Groups tab shows where each discontinued MRP goes).
- Loader reads the workbook's wide "MRP Adj" grid as is (or a plain DEPARTMENT / DISPLAY / MRP_CURRENT / MRP_LISTED list); placed in `MRP Merging Engine\Sales Reapportionment\MRP Mapping\` (was empty). Output gains SHARE_PCT. Validation: store x dept before = after + Unmapped.
- Checked: the engine's below / above targets equal the workbook's Final1 / Final2 for all 5,233 discontinued MRPs; full run on LY Mar-Jun 2026: Rs 41,062.26 L in -> 40,824.36 L re-apportioned + 237.90 L Unmapped (7,070 rows no listed MRP, 2,469 MRP not in master), diff Rs 0.000001, validation passed; split step 0.4 s (was a per-row loop). Test `engines/test_mrp_reapportionment.py` adds a hand-made rule case.
- Workbook notes for the planners: FABRIC-SUITING / NON_TABLE is out of MRP order in the grid (the app sorts); the Working sheet's after-split total is half the before total.

## 2026-10-07

### Core apps: loading-time check + gzip on 8010
- **Asked (user):** "check loading times in the other core apps too".
- Timed every page-load request in-process (cold / warm). Calendar: all < 0.25 s except the Calendarised Sales snapshot summary (0.9 s, 8.4 MB) and the data-source scans `salesdata/link` / `link-daywise` (9-16 s once after a restart, only on a refresh click). AOP: all < 0.35 s except `config/recent-runs` (~10.7 s every call). BIS (5050): every load call < 0.2 s, the three sync jobs ready in < 1 s.
- Fixed: 8010 now gzips responses over 2 KB (Calendar's 8.4 MB summary -> 0.8 MB, ~50 ms to pack); checked live through Landing (Content-Encoding passes through; clients without gzip get plain bytes) and that CSV / Excel downloads still come through.
- Commit `08fc468`.
- `engine.forecast_results` (10.8 M rows) had no index on `run_id`, so every per-run total scanned the whole table - `recent-runs` (Plan Cycles) 20 times, `runs/{id}/division-totals` (BIS AOP Review) and `division-aop-summary` (Sales Plan "Load AOP division targets") once each. User approved the index: migration `a7c4e9b2d1f3` adds `ix_forecast_results_run_metric (run_id, metric_key)`, built CONCURRENTLY on the live DB (24 s, 79 MB, valid; no data change). recent-runs 10.7 s -> 0.28 s; one run's totals 14 ms.

### Sales Plan: page loading times
- **Asked (user):** "fix the loading times in the planning engine" (Master Setup stuck on "Loading department master…").
- Cause: the sidebar's Plan Snapshot (collapsed by default) ran the whole department plan (`run_dept_plan`, ~10-13 s of pure Python) on every page load, and while it ran it held up the page's own requests - Master Setup's data takes 25 ms on its own.
- Sidebar: the snapshot is fetched only when it is opened. Server: `/dept-sales/plan-summary` is kept until one of the plan's inputs changes (growth matrix incl. live BIS, department master/state, Calendar snapshot stamp, LY months, store master, date) - 12.8 s first time, then 0.2 s; same numbers as a fresh run.
- Sales Sync status no longer loads the six snapshots' full sales rows it never shows: 4.5 s -> 0.02 s, same output.
- Commit `513336b`.
- MRP Re-apportionment warm-up (user: "yes warm the mrp re-apportionment at startup"): 8010 reads the sales engine file in a background thread at start (`warm_sales`, ~35-85 s) instead of on the first page open; a lock makes an open during the warm-up wait for it rather than read the file a second time. Tested: Master Setup stayed < 0.2 s during the warm-up; sales-status 65 ms afterwards, Calendar tie-out still passes.

### Handover doc updated with 7 Oct
- **Asked (user):** "update the handover doc with today's changes".
- `docs/HANDOVER.md`: new §11 (live AOP publish 116 and the BIS -> Sales Plan push; BIS numbers, layout and audit fixes; the three planner factor models with back-test results; the suite declutter commit by commit; the buyer_push right; today's gotchas). Header date updated; the stale "Sales Plan dist untracked" notes (§3.5, §9 item 3) corrected.

### Post-declutter audit: HTML apps
- HTML-apps review (Landing, NSO, Re-Aligner, Growth vs LY, Listing): no critical / high issue; rights ids, menus, handlers and confirms verified. Fixes:
  - Growth vs LY and Listing: collapsible headings showed a literal "B8" / "BE" instead of ▸ / ▾ - the CSS escapes `\25B8` / `\25BE` had been written as a control byte (0x15) + "B8"; restored (checked live: ▸ renders). Listing cache-buster -> v=20261007b.
  - Landing: a Drik Panchang sync started from the "Export / Sync ▾" menu now shows "Syncing N years…" on the menu button itself (the item's own label was hidden by the closed menu).

### Post-declutter audit: Calendar minor fixes
- Calendar review: no critical / high issue. Two minor fixes: the Calendarised Sales "More views" menu no longer shows empty (a day-wise run with no actuals has no extra views since Run Details went); Date Shift falls back to sorting by Store when the context columns are hidden while sorted by Ref Day / Fut Day. dist rebuilt; engine tests pass; both tabs render with no errors.

### Post-declutter audit: Sales Plan running-status line
- **Asked (user):** "audit the suite once again after the declutter" / "fix whatever the audit finds and commit". Four read-only reviewers (Calendar, AOP, Sales Plan, the five HTML apps) on the declutter diffs; AOP and Sales Plan: no critical / high issue.
- Fix (minor finding): actions started from a menu close the menu, so their "Syncing…" / "Running…" labels were never seen. Growth Matrix now shows "Syncing from Buyer's Input Sheet…" beside Saving / Saved, and PW/W shows "Running Phase 1… / Running Phase 2… / Reapportioning…" while a run from the ⋯ menu is going (role=status). dist rebuilt; pages render with no errors.

### Sales Plan: confirm before Reset to 100 and Revert to Original
- **Asked (user):** "add confirm to both and keep the titles removed".
- Growth Matrix "Reset to 100" asks "Reset every <division> department's growth to 100 (LY)? …" and Attribute Correction "Revert to Original" asks before discarding the division's edits; Cancel does nothing (checked: no request sent). The 13 duplicate page titles stay removed. dist rebuilt.

### Sales Plan: decluttered (suite declutter 8 of 8)
- **Asked (user):** suite declutter ("check sales plan too in this process").
- **Moved (handlers / labels unchanged; menus are native details, always in the DOM, Esc returns focus):** Growth Matrix - ↑ Buyer Input, Sync from Buyer's Input Sheet, ↺ Reset to 100 [danger] -> "Matrix tools ▾", legend -> ⓘ, ▶ Generate Base Plan primary; Department Master - Load AOP division targets + ↓ Export -> "Data ▾", AOP tiles one line, attribute chips folded; New Depts - Clear [danger, confirm kept] moved away from Save & Apply into "⋯"; Attribute Correction - Compare AOP + Revert to Original [danger] -> "More ▾"; PW/W - Refresh -> "Data ▾", only the next-step run button shows (others in "⋯"); SOR - Refresh -> "Data ▾"; MRP Output - Deviations + Export CSV -> "More ▾"; Division Plan - Refresh -> "Data ▾", charts folded.
- **Quieter:** 13 duplicate in-page titles removed (the header already titles every page; subtitles kept), Reconciliation got its missing header title; Final Results pipeline card -> breadcrumb, tiles -> one line, Department View filters -> "Filters" with chips, Cluster KPI row keeps TY / LY / Growth / Depts; Base Correction 12 -> 7 default columns + "+ Context columns" (`sp.baseCorr.ctxCols`); MRP help column -> ⓘ; sidebar Plan Snapshot collapsed by default (`sp.snapshotOpen`). Dead code removed (grep-proven): ContribBar, PipelineNode / Arrow, unused Link import.
- Note: "Reset to 100" and "Revert to Original" had no confirm before and still have none (re-parenting only).
- **Checks:** build OK; built page walked through all 16 sidebar pages - every page renders, no script errors (only empty-API responses without a backend), menus present as planned.

### AOP Forecaster: decluttered (suite declutter 7 of 8)
- **Asked (user):** suite declutter.
- **Moved:** Results - store-type / division / month chips -> "Filters ▾" with removable chips on one line; Base source + Data labels -> "View ▾"; Unlock [confirm kept] + Download Excel -> "Plan ▾" (Promote / Locked to Planning stay visible). Review - "Include flat detail sheet" -> "Run options ▾"; month chips -> "Months · N of 13 ▾"; per-month AOP override paragraphs -> one expandable line; store tiles -> one line; help texts -> tooltips. Store Master / AOP Overrides - Template + Import -> "File ▾"; Tag / Cluster / Region / Grade filters behind "Filters" with chips; read-only columns behind "+ Context columns" (`aop.storeMaster.contextCols`); Ref Store Mapping Change Log -> "⋯". Landing rows: Rename / ✕ on hover or keyboard focus (Continue latest kept). Configure: one "Continue from database" + "Edit Growth % / NSO / AOP" link.
- **Removed:** duplicate "← Review inputs", dash-sub line, top and bottom Review navs (the header stepper does the same), duplicate reset link, "Step 1 of 3"; dead code (each proven by grep): GrowthTab + ROW_KEYS, ExcelPalettePicker.jsx/.css, lib/gridsort.jsx, an empty effect, unused isMajor.
- **Checks:** build OK; live on :8000 - landing, Open Version 2 (read-only), Results menus, no page errors, totals unchanged.

### Calendar: Run Details removed
- **Asked (user):** "remove run detail in the calendar app".
- The Calendarised Sales "Run Details" view (source / rows read / cached vs computed months / frozen sync / unmapped stores, dates and clusters) is gone from "More views"; the empty-result warning no longer points to it. The run itself is unchanged. dist rebuilt.
- **Checks:** engine.test passes; Calendarised Sales renders with no errors and keeps its Day-wise / Month-wise select (e2e).

### Landing: big "Planning Suite" title back
- **Asked (user):** "i liked this better earlier" (about the intro after the declutter).
- Restored the original intro: the "FY 2027–28 · Planning suite" eyebrow, the big "Planning Suite" title and both its styles. The rest of the Landing declutter (Account menu, sync strip, Lagan Export / Sync menu) stays.

### Calendar Engine: decluttered (suite declutter 6 of 8)
- **Asked (user):** suite declutter.
- **Moved:** Festival Master toolbar (Import, Download template, Sync dates (Google), Sync structure to all templates [confirm kept], Remove from all clusters + its input [confirm kept]) -> "Festival tools ▾", which also opens the Change Log (was an always-on side card). Cluster rename / region / copy-from [confirm kept] -> "Cluster settings ▾". Calendarised Sales: Month Wise Matrix, DW Comparison, P1/P2 Comparison, Run Details -> "More views ▾" (Monthly Summary stays a tab); month chips -> "Months: … ▾". Store Mapping: Download template, Change Log, Download change log -> "Data ▾", help -> ⓘ, cluster counts in one strip. Library cards: duplicate "Load & Preview" removed (card click / Enter loads), Rename [prompt kept] / Delete [confirm kept] -> "⋯", badges -> one status dot.
- **Quieter:** Day-by-Day 6 tiles -> one line (validation errors as a red count on its tab); 4 of 6 filters behind "Filters" with removable chips; 17 -> 8 default columns + "+ Context columns" (`cal.dayMap.contextCols`); Date Shift filters / Ref Day / Fut Day likewise (`cal.dateShift.contextCols`); Version Setting legend + priority order in one "How mapping works"; compact engine select. Shared `ui.jsx` (Menu on native details - always in the DOM, Esc returns focus; useStoredFlag).
- Found in the live check: the festival-name input inside the menu lost its styling (it used to sit in `.field`; the global input rule skips type=text) - menu text inputs now styled.
- **Checks:** engine.test passes; build OK; built page renders with no errors; "Festival Master", the Calendarised Sales tab, Monthly Summary and the Day-wise / Month-wise select still visible (e2e); menus open / close.

### Landing: decluttered (suite declutter 5 of 8)
- **Asked (user):** suite declutter.
- **Top bar:** brand + status + one "Account ▾" menu holding Theme (theme-btn), Users (admin only, admin-link), Servers start / stop all (launch-all-btn, rights greying kept) and Sign out (signout-btn / signout-label). Items stay in the page (rights script and e2e unaffected).
- Intro to one line (duplicate "Planning Suite" heading and "opens in a new tab" sentence removed), footer's repeated Servers line removed, sync strip one line (detail as tooltip, "View details" span removed), Lagan card meta "Look up". Lagan modal: Monthly Summary / All Dates / Sync with Drik Panchang -> "Export / Sync ▾" (same ids), method note -> ⓘ, year chips capped at 5 + "+N more", shorter subtitle.
- **Checks:** scripts parse; every rights / admin id present; 8 per-card status labels visible (e2e needs 3); test_rights_guard and test_lagan_drik pass; static preview on :5179.

### NSO Distributor: decluttered (suite declutter 4 of 8)
- **Asked (user):** suite declutter.
- File status shown once: tiles -> one summary line ("Required n/n · Optional n/n") that expands the tile grid (opens by itself when a required file is missing); duplicate Generate summary removed; folder message only for warnings. Duplicate h2 title dropped; one "Reset" next to Scan (resetAll, confirm kept) instead of two; AOP table wider with borderless inputs until hover / focus; current stage name next to the bar, stage pills in a collapsed details; Download XLSX as a text link (same handler). Removed unused SheetJS CDN script, clean(), MONTH_MAP, MONTHS, clearFolder(), updateSummary().
- Fix found in the live check: a global `[hidden]{display:none!important}` - the summary button showed as an empty pill before any scan because its display rule beat the hidden attribute.
- **Checks:** scripts parse, ids exist, confirm prompts kept; live on :8060.

### Listing / Delisting Analyser: decluttered (suite declutter 3 of 8)
- **Asked (user):** suite declutter.
- **Moved:** Change Events / Seasonality / Data & checks / Rules tabs -> "More ▾" (shows the open view's name; same tab-btn / data-mode). Suggestions: Division / Season category / Cluster / Severity -> Filters panel with removable chips; rule paragraph -> one line + "Full rules →"; row sub-lines removed (same facts are in the Why panel); funnel text -> tooltip. Change Events: Window + zero-sales flip -> Filters. By Department / By Store: Order + Cells -> "View ▾", one-line legend. Overview: 5 tiles -> clickable strip, top tables first, "Season windows now" and "By division" collapsed.
- Removed dead `ACTIONS['open-dept']` (no data-act="open-dept" anywhere). Cache-buster -> v=20261007a.
- **Checks:** app.js passes node --check; live on :8123 - tabs, More menu, Filters chips, Export, Full rules.

### Growth vs LY: decluttered (suite declutter 2 of 8)
- **Asked (user):** suite declutter ("remove extra buttons which can be readjusted. De-cramp the core and additional apps").
- Once a plan is loaded, card 1 is just the plan line + "Replace plan" (same #file input; keyboard opens it); description and drop zone only before a plan is loaded. Group-header "TY … plan vs LY … sales" and "Click a row…" -> tooltips; shorter card-2 text; Expand all a small ghost button, Download stays primary. Chart card collapsed by default - a row click opens it (checked live: KIDS row opens the chart).
- **Checks:** script parses, ids exist, test_gr passes, live on :8075.

### Re-Aligner: decluttered (suite declutter 1 of 8)
- **Asked (user):** "revamp core apps and remove extra buttons which can be readjusted. De-cramp the core and additional apps" (reviewed with the ECC dev-team skill: layout only, every action reachable with the same handler / confirm / label).
- **Moved:** Step 2 header's 8 controls -> a "Re-phase from LY" row (department, LY shape, Re-phase & run) + one "Files ▾" menu per method (M1/M4 Blank template + From Listing / Delisting Analyser; M2 Template, Re-phase file, Store overrides upload, Overrides template, Clear store overrides [red, confirm kept]; M3 Split + New-department templates; M5 Growth template). Listing check file stays visible. Replace the original plan -> "Replace…" beside the file name (drag-drop for a replacement removed).
- **Quieter:** method cards one line (descriptions as tooltips); "How to fill the file" collapsible (open until a file is loaded); results 4 tiles -> one line (duplicate Run time dropped); passing checks folded; downloads as compact rows with tooltips; Run card one line; Activity "Recent" collapsed; topbar subtitle -> tooltip, connection badge only when offline.
- **Checks:** scripts parse, all ids exist, confirm prompts 3/3, guarded labels kept ("Re-phase & run", "Run"), test_realign / test_workspaces pass; live on :8070 - each method's Files menu correct, Esc closes and returns focus.

### PROJECT-CONTEXT.md added
- **Asked (user):** "yes create the PROJECT-CONTEXT.md" (from the ECC dev-team review).
- Repo-root summary of the suite: purpose, tech stack, current phase, key constraints and what "done" means - the shared baseline the dev-team / review sessions read (as untrusted declarative data). No code change.

### BIS Continuous factor: 19V26 comparable beside 25V26 + agreement check
- **Asked (user):** "the continuous should add another layer - except for 1 year comparable we want 19 V 26 and 25 V 26 comparable to make sure this factor works".
- **Built:** a fourth driver, Base growth 19V26 (31 stores), compared as (1 + growth) / (1 + division median) with its own strength (department's own, else its reference department's - `_plannerInputs` `gb`), and an optional switch "Trust growth only when 25V26 and 19V26 agree" - when the two sit on opposite sides of their division medians, neither moves that department's factor (one comparable only -> kept). The tab shows how many departments disagree (45 of 144 today). Tune searches the 19V26 strength and the switch too (~3,000 settings, 0.8 s). Hover explains "not used (the two comparables disagree)". Server validates `base` (-2..3) and `agree` (bool).
- **What the back-test says (error, short / long / weighted; plain share 14.83 / 14.35 / 14.51):** 25V26 + sell-thru (tuned) 11.13 / 13.54 / 12.74; adding 19V26 at 0.25 12.06 / 15.69 / 14.48; with the agreement check 11.71 / 14.56 / 13.61; agreement on 25V26 alone 11.66 / 13.76 / 13.06; 19V26 alone at best 13.74 / 14.71 / 14.39. So the 19V26 comparable did not improve the prediction - Tune leaves it at 0 with the switch off. Defaults unchanged (base 0, agree off).
- **Checks:** `test_factor_model.js` (both comparables, agree kept / ignored, one comparable, agreement checked at strength 0), `test_sync_server_ly.py` (base / agree validation).

### BIS factor window: Continuous option with Tune
- **Asked (user):** "yes add the continuous option with tune button" (after "suggest me 2 - 3 approaches to derive planner's input using the given factors").
- **Continuous (`_contFactor`):** no slabs - factor = (sell-thru / division median)^s x ((1 + LY growth) / (1 + division median))^s x (fill / division median)^s with a signed strength per driver (0 = off; negative = lower value, higher factor), then the shared rules / small-department damping / limits (`_fmLimit`, also used by the weighted builder), then the re-balance to AOP. "Planner uses" now offers Continuous / Weighted builder / Matrix; saved table still Matrix until a planner switches + saves. Server validates the strengths (`_cont_error`, -2..3, finite).
- **Back-test now has two windows** for every method: short (Mar-Apr 2026 inputs -> May-Jun 2026) and long (Jul-Oct 2025 -> Mar-Jun 2026, closer to the year-ahead step), with their average vs plain share (`_fmEval`, `_fmBacktest(spec, IN, OUT)`).
- **Tune** searches ~400 strength settings (0.3 s, cached inputs) with the long test counting double - an equal weighting chased 2-month momentum (growth 0.5) and lost on the long test. Result today: sell-thru 0.375, LY growth 0.375, fill off -> short 11.13% / long 13.54% vs plain 14.83% / 14.35% (better by 2.25 pts on average); the saved matrix is worse than plain (15.04%). Live: every division x month stays on AOP (0.00 L off).
- **Checks:** `test_factor_model.js` (continuous product, median = 1.00, strength 0 / missing / negative, shared clamp), `test_sync_server_ly.py` (strength validation).

### BIS factor builder: percentile slabs + back-test
- **Asked (user):** "yes go ahead with percentile slabs and back-test".
- **Percentile slabs:** each driver card has "Slabs by: Value | Percentile in division". In percentile mode a slab starts at a percentile (P1-P99) of its division's active departments for the same months (`_fmQuant` / `_fmCut` / `_fmResolve`), so cut-offs move with every data refresh and "High" means high for that division (sell-thru now: MENS 8.4 / 11.2 / 12.9%, LADIES 7.8 / 10.1 / 12.9%, KIDS 9.2 / 11.3 / 12.3%). Departments spread evenly (sell-thru 32 / 30 / 30 / 32 vs 8 / 38 / 65 / 13 on fixed values). Server validates (`by`, rising 1-99).
- **Back-test (`_fmBacktest`):** the planner step one year earlier with no look-ahead - inputs Mar-Apr 2026 (sell-thru, LY growth 25V26) + current fill rate; each department's May-Jun 2026 share of its division predicted from its May-Jun 2025 share (same stores), re-balanced like the planner; error = WAPE, per division too. Shown live in the builder for plain share, the saved matrix and the draft.
- **First results (151 departments):** plain share 14.83%; saved matrix 15.72% (worse by 0.90 pts); builder default 14.44% (better 0.38), with percentile slabs 14.08% (better 0.74); sell-thru alone 13.72% (better 1.11); LY growth alone 15.75% (worse 0.92) - high-growth departments kept growing, so cutting them lost accuracy.
- **Checks:** `test_factor_model.js` (percentiles, resolved starts), `test_sync_server_ly.py` (percentile validation).

### BIS: weighted factor builder (step 1 + builder) beside the 36-row matrix
- **Asked (user):** dynamic factor table instead of the hand-set one; drag-and-drop slabs and weightage for a single or multi-factor system; a definitive coefficient. Then: "yes start with step 1 and the builder".
- **Formula (`_weightedFactor`):** each driver that is on puts the department in one of its slabs (a multiplier); drivers combine as a weighted geometric mean (one driver = its multiplier; 1.10 and 0.91 cancel; a driver with no data is left out and the rest re-weighted) -> floor / cap rules in card (priority) order, a later rule never undoing an earlier one -> small departments damped toward 1.00 (f' = 1 + (f-1) x LY / (LY + k), LY per month) -> clamp. The re-balance to each division's AOP is unchanged.
- **Builder (Factor matrix window, "Weighted builder" tab):** driver cards dragged by the grip (or ↑ / ↓) to set priority; Use switch and weight slider per driver ("% of the factor"); slab bar with draggable boundaries and department counts per slab, plus a slab table (start %, name, multiplier, add / remove); rules; damping and factor limits; live preview (low / median / high factor, top and bottom 5 vs the matrix).
- **Safe switch:** "Planner uses: Weighted builder / Matrix (36 rows)" - saved factor table stays on Matrix (today's numbers unchanged) until a planner switches and saves. Admin / planner only; the server validates the model (`_model_error`: each driver once, weights 0-100, rising slab starts, multipliers in (0, 3], NaN refused, clamp lo <= 1 <= hi).
- **Checks:** `test_factor_model.js` (single / weighted / re-weighting / rule priority / damping / clamp), `test_sync_server_ly.py` (model validation); live: weighted mode keeps every division x month on AOP (0.00 L off), matrix mode unchanged (M_IN_BRIEF 1.08).

### BIS audit: plan rules, data refresh and the Sales Plan push
- **Asked (user):** "audit the app once done", then "fix whatever the audit finds and commit". Three read-only reviewers (planning rules, today's UI + security, server + sync); every finding re-checked in code or live before fixing.
- **Plan rules (otb-plan-app.html):**
  1. Revert (attribute / division) and "Reset" put the start values back without re-balancing - an attribute revert left MENS ~6% under AOP, and hide-then-reset left a division off AOP. They now re-balance (`_divReapp` / `_divRescale`) and clear the buyer's own entries they undo.
  2. A locked division was overwritten by Re-apportion by LY Cont%, Reset, Re-seed, Revert and Clear all inputs. It is now left exactly as it is (Revert says "unlock it first").
  3. A big entry (e.g. 2000% on ML_JEANS, or a typo) drove the other departments below -100% - negative sales, sent to Sales Plan. Re-balancing now stops at -100% (`_divReapp`, `_divRescale`); the AOP check line shows the overshoot in red.
  4. Clear all inputs left locks (frozen at 0%) and old buyer entries (kept at the next re-seed). It now clears them too (`clearAllInputs`), locked divisions kept.
  5. Lock All stuck on "Unlock All" while a division was locked. Label fixed: "Reset to Planner's input" -> "Reset to AOP share" (it restores the plain AOP share).
- **Data refresh (sync_server.py):** a sync job, once done, was reused until 5050 restarted, so Refresh data never picked up a new lake export (LY, history, sell-thru went stale silently). A finished job is now reused only while the data version it STARTED from is current; the check-and-start is locked. `test_sync_server_ly.py` covers it.
- **Sales Plan push:** one POST replaces every division's buyer growth and any signed-in person could send it. New right "Send the Buyer's plan to Sales Plan" (`buyer_push`, Landing GUARDED; Users & access can switch it off per person, e.g. reviewers / approvers). 5050 no longer allows cross-origin calls (CORS removed) and caps request bodies at 25 MB. The page now checks how many rows the server stored and says so if it is short, and shows the reason for a 403.
- **Factor matrix button (user: "i want matrix table also can i have a button similar to context button to view the table"):** "▦ Factor matrix" beside "+ Context columns" on the Buyer's Plan and Attribute Summary opens the sell-thru x LY growth x fill rate table that sets the planner's factor (moved out of Plan tools).
- **UI:** the grid is inert behind the department drawer; the drawer's factor label reads the number directly; the totals line is no longer a live region read out on every keystroke.

### BIS: Avg ST% hover shows the months behind the block figure
- **Asked (user):** "avg sell thru on months should be according to the months and probably a hover can make things easier in the block panel so that the block sell thru can be justified".
- Avg ST% (Buyer's Plan, Attribute, Division and Department Summary, and the drawer) is the selected months' ST%, simple average over the months with data; hovering lists each month, e.g. M_IN_BRIEF Mar 10.1 / Apr 9.4 / May 10.6 / Jun 11.1 -> 10.3%. Picking other months re-averages (Apr+May -> 10.0%). Attributes note that each month weights its departments by LY.
- Division, attribute and department now share one month source (`_stMon`); the unused `_attrPeriodAvg` is gone.

### BIS: Division and Department Summary use the same lean layout
- **Asked (user):** "apply the same layout to division and department summary".
- **Division Summary:** Avg ST% | 25 V 26 | LY Actual Sales | Plan Total | vs LY%. **Department Summary:** Avg ST% | 25 V 26 | LY Actual Sales | Plan Total | Growth%; a department's name opens the same details drawer.
- Month-by-month columns (and Contrib% in Department Summary) come back with "+ Context columns" or the header's "Show months" - one switch for every report (`_monCols` / `_togMonCols`), remembered per browser. Column names match the Buyer's Plan ("LY Actual Sales", "Plan Total").

### BIS: calmer layout - lean grid, department drawer, live AOP check, one Data menu
- **Asked (user):** "is there anyway we can keep the app less cramped, more informative and true to the rules set and still easy to function? BIS"; chose all four options; then "keep avg st% and 25 v 26 in the main grid".
- **Lean grid (default):** Avg ST% | 25 V 26 | LY Actual Sales | Planner Gr% (+Use) | Block Growth% | Plan Total | vs LY%. "+ Context columns" brings back monthly ST%, 19 V 26, Contrib%, Factor and Planner Value (remembered per browser). Phase 2 keeps its planner / buyer month columns.
- **Department drawer:** click a department's name: LY, plan, buyer vs planner growth, month by month (LY, buyer Gr%, plan, planner Gr%, locks), how the planner's growth is built, sell-thru by month, 19 V 26 / 25 V 26, Contrib %; "Edit month by month" opens the existing month window. Read-only, so every edit still goes through the same rules. Esc closes, focus returns to the name.
- **Live AOP check:** the four KPI tiles (one was a hard-coded "Avg ST 8.4%") and the bottom grand-total bar became one line beside the division tabs: LY, Plan, growth, then "MENS = AOP / LADIES = AOP / KIDS = AOP" - red with the month and gap in lakhs if any division x AOP month is off - and how many departments are locked / buyer-set.
- **Top bar:** Factors moved into Plan tools; Refresh data (with its status), Plan history and Export into one Data menu. Filters start closed; active filters show as removable chips.
- **Quieter rows:** padlocks show on hover or once locked (keyboard focus still shows them), sell-thru in plain figures (red / green only for growth), Use as a light pill, no padlock emoji on every planner cell.
- **Bug fixed:** the filter panel's "Clear all" set the department filter to "show none" (empty grid) and switched all 38 inactive departments back on. It now clears filters only.

### BIS: division growth matches AOP to the decimal (KIDS 12.8% -> 12.9%)
- **Asked (user):** "kids growth is 12.9% in aop forecaster but it shows 12.8% in the bis".
- **Cause:** BIS took LY from the departments' own synced actuals, which add up ~1 L higher for Jun'26 than the base AOP's growth is on (MENS +1.02 L, LADIES +1.04 L, KIDS +0.84 L). Same plan money (136.41 Cr), different LY: 12.847% vs 12.854%, either side of the rounding line.
- **Fix:** each department's actual is scaled so the division adds up to AOP's base for that month (`_secActScale`); the mix between departments is still their own actual. Every screen now reads LY from `_secMonLY` (the row builder and magnifier had their own copies). Seed tag z3 re-balances each browser once; buyers' own entries and locks stay.
- **Checked live:** MENS +9.3%, LADIES +11.6%, KIDS +12.9% = AOP; plan total = AOP to 0.0001 Cr in every division; BIS tests pass.

### BIS: Block Growth% hover shows the month-wise growth
- **Asked (user):** "show the month wise growth in the hover".
- Hovering a department's or attribute's Block Growth% (and Phase 2's Phase 1 column) lists Mar/Apr/May/Jun growth with each month's share of the block's LY, e.g. Mar +7.5% (29%), Apr-Jun +10.0% -> block +9.3%. The block is the LY-weighted average of the months, which is why departments differ under the same division AOP (`_blockWhy`).

## 2026-10-06

### Suite audit: 26 high-severity issues fixed across core and additional apps
- **Asked (user):** "check and run a quick audit if there are any issues - fix them in the whole module -core or additionals".
- **How:** six read-only reviewers (BIS, Calendar, AOP, Sales Plan, Re-Aligner / NSO / Growth vs LY, Landing / auth), critical/high only. Every finding was re-checked in code or on live data before fixing.
- **Sales Plan:**
  1. Non-SSG stores were planned 13–25% low. The division average counted BIS-delisted departments (index 0): KIDS Apr'27 used 89.8 instead of 110, MENS 85.3. Delisted departments now stay out (`_avg_division_growth`; one copy shared with Base Correction).
  2. 39 inactive departments were switched back on and planned at LY from Jul'27, because the growth matrix filled every unsent period with 100. `live_growth_matrix` now returns only the periods BIS or a saved value supplies.
  3. A non-SSG division whose ref store had no share kept a total with every department at 0. It now splits by the store's own LY department mix, and the division total is always the sum of its departments. Full run, in memory only: 0 mismatches.
  4. Save & Apply on New Depts kept stale corrected plans and hid failures. It now runs `_apply_new_dept_map`.
  5. A one-off Postgres error cached an empty store master. It now raises, which isn't cached.
  6. All 21 JSON plan / state writes are atomic (`plan_cache.save_json`: .tmp + os.replace).
- **BIS:**
  1. A re-seed with every department buyer-set could leave a division off AOP; `_divRescale` now runs after it.
  2. Attribute Block / Use / lock overwrote individually locked departments; they now use `_divReapp` with the attribute as anchor and skip locked cells. `_divReappAttr` is removed.
  3. Stored script injection in the Factors dialog: reasons, labels and the upload file name are now escaped.
  4. Unlocking a division left all its cells locked. Only the locks it added are removed, and `divLocked` is now saved.
- **AOP:**
  1. The auto-rebuild re-ran the OLD session at engine-default growth and silently made it the live AOP. It no longer runs automatically: a "Rebuild from database" notice lands on Review for the planner to check and Run.
  2. A major change ran on the saved version's own session (two versions shared it; Lock could pick the wrong one). It now forks the session first (`POST /api/session/{id}/fork`).
  3. A re-run after a later sync closed a month zeroed that month's base. Sessions record `closed_through`, and a re-run uses the session's own.
  4. Version ownership used the browser clock; it now uses the DB clock.
- **Calendar:**
  1. Sync Now / Lock & Save / Save-to-template deleted the old calendar before saving the new one. They now save first.
  2. Save-to-template deleted by name and could hit a same-named calendar; it now deletes by id.
  3. A partial what-if Run Reindex replaced the shared snapshot AOP / Sales Plan read. Only the nightly sync jobs save it now (`persistSnapshot`).
- **Re-Aligner (fast-xlsx follow-ups):**
  1. A sheet over 1,048,575 rows made the file unopenable; it now continues on "(2)" sheets.
  2. An empty `<cols/>` made a sheet unopenable.
  3. Duplicate column names crashed the export.
  4. Download names keep printable ASCII only (no header injection, no crash on ’ –); an unknown template department returns 400.
- **NSO:** the read-file / parse / start routes served any file on the host to any signed-in user. They now accept only a bare spreadsheet file name in an existing folder.
- **Growth vs LY:** the "(blank)" SSG tag matched nothing; it now selects the untagged stores.
- **Landing / auth:**
  1. Per-person rights could be bypassed with percent-encoded or "//" paths. Landing now matches the decoded path and refuses "//".
  2. `login?next=` could run `javascript:` or send users off-site; it now accepts same-site paths only.
  3. A switched-off or demoted user kept access through their old cookie. Every request now re-checks the user (sign-in-as keeps its flags).
  4. "Launch all" could start a second copy of an app. One locked, grace-aware `_launch` now serves the watchdog, start-up and Launch all, and a failed start no longer kills the watchdog.
- **Left as designed:** with no saved AOP version, the latest run stays live (an existing rule).
- **Checks:** every app's tests pass. The 5 failing platform tests are the known stale ones and fail the same way without these changes. Restarted Landing, 8010, 8000, 8060, 8070 and 8075, one listener each. Live checks: "//" → 400, unauthenticated encoded guard → 401, NSO traversal → 404, the fork route is present, AOP live = Version 2 (43,184.66 L).

### Re-Aligner: every download is named after its method
- **Asked (user):** "give rename to the download files according to the method numbers or the listing like - if the output is for the Dept Re-aligner then it should say that, if it is listing re-alignment then it should say that".
- Each file now starts with the method: "Method 1 - Listing Re-alignment", "Method 2 - Dept Re-alignment", "Method 3 - New Dept Re-alignment", "Method 4 - Listing Shift Re-alignment", "Method 5 - Growth Re-alignment". Examples:
  - "Method 2 - Dept Re-alignment - Realigned Plan - Plan to Plan.xlsx" (outputs take the method of the run);
  - "Method 1 - Listing Re-alignment - Check file.xlsx";
  - "Method 2 - Dept Re-alignment - Re-phase from LY - <dept>.xlsx";
  - templates likewise.
- One helper (`server.file_name`) also swaps characters Windows can't hold in a filename (e.g. "H/S" → "H-S"). The re-phase download takes the server's name. Re-Aligner restarted.

### Re-Aligner: final Excel outputs in seconds instead of minutes
- **Asked (user):** "re-aligner is delaying the final output process check it and try to reduce it".
- **Cause:** the xlsx exports wrote the ~675k-row plan cell by cell in Python (xlsxwriter). The server's last timings were 650 s for Plan-to-plan and 260 s for the Full realigned plan (93 s / 78 s on an idle machine; slower in the server alongside other work).
- **Fix (`engine.write_xlsx`, same interface for every caller):** the sheet XML is now built column-wise in polars (already installed, so no new dependency) and zipped straight into the .xlsx. Measured on the 674,478-row plan: Plan-to-plan 10.4 s, Full plan 8.0 s, about the same file size (deflate level 6). The files are standard SpreadsheetML: every cell keeps its address, text is inline, the 8-decimal number format is kept, booleans stay true/false, and characters XML can't hold are stripped.
- **Checked:** read back, every value and text cell equals the source (max difference 0.0); multi-sheet / categorical / boolean / mixed columns round-trip; `test_realign.py` and `test_workspaces.py` pass. Re-Aligner restarted (8070); a result on screen needs one more Run.

### BIS: Attribute Summary = read-only summary, with an "Edit by attribute" pane carrying every Buyer's Plan tool
- **Asked (user):** "i want similar to the buyer's input sheet in this module also … attribute is optional but in case if the user wants to work on to change it then only open a similar pane with all BIS components intact as the main sheet. otherwise just highlight it as a summary of the BIS output derivative".
- **Default:** a bar reads "Summary of the Buyer's Plan - every figure here is the departments added up by attribute (read-only)". There are no inputs, locks or Use buttons. The Factor column now shows each attribute's factor (its departments' factors weighted by AOP share, e.g. MENS REGULAR 1.07, OCCASIONAL 0.98). The Planner Gr% hover message explains the attribute's build-up.
- **✎ Edit by attribute** opens the editing pane: an outlined table, a header bar naming the phase and its rules, and a Done button. It has the Buyer's Plan tools per division × attribute:
  - Phase 1: Block Growth% with lock, and "Use" (every department of the attribute takes the planner's Gr %; the other attributes re-balance to AOP).
  - Phase 2: month growth per attribute with its own lock, balanced like a department edit (`_phase2Edit` now takes a group), so each department's block total and each month's AOP both hold.
- **Checked live (MENS):** Use on SUMMER → buyer +11.89% = planner +11.89%, AOP exact every month. Phase 2: REGULAR May → +5%; AOP exact, largest block-total drift 0.00000000003 Cr. `test_phase2.js` gained a group-edit case.

## 2026-10-05

### Docs: handover calendar table updated
- **Asked (user):** "update the handover doc with the new calendar names". `docs/HANDOVER.md` §7.13 "Current saved calendars" now lists the four live V2 calendars (ids, `<ref> -> <fut> Calendar - All` names, what each feeds, lagan re-sync on 2026-10-05). The 2026-09 audit's set is kept as a superseded note.

### Calendar: 2021 and 2024 calendars renamed (data)
- **Asked (user):** "yes rename the 2021 calendar". "2021-> 2022 Calendar - All" → "2021 -> 2022 Calendar - All" (name only; id 1791178013513, saved_at and day map unchanged).
- **Asked (user):** "yes add - All to the 2024 calendar". "2024 -> 2025 Calendar" → "2024 -> 2025 Calendar - All" (id 1790655101158, name only). All four now read "<ref> -> <fut> Calendar - All". The old name survives only in the legacy `Calendar Engine/Local DB/calendar_library.json` and `docs/HANDOVER.md` (an older calendar id); nothing live looks calendars up by name.

### Pre-demo re-check of Calendar / AOP / BIS + BIS warm-up on start
- **Asked (user):** "now re-check all 3 apps again as i am going to show it to the stakeholders tomorrow".
- **Green:**
  - one process per port, and the hostname link answers;
  - every test passes except the known-stale `test_lfl_auto.py`;
  - all 10 syncs succeeded today;
  - AOP Version 2 is live and locked (MAMJ Rs.431.85 Cr, +11.1%), and opening it only reads (no re-run or publish);
  - a first-time BIS browser lands exactly on AOP for every division (KIDS 136.41 / LADIES 128.15 / MENS 167.29) in Phase 1, with 125 fill rates loaded and no console errors;
  - all four V2 calendars match today's engine (0 changed pairs, 0 reuse);
  - the Calendar dist is current.
- **Fixed (`sync_server.py`):** BIS's three data pulls (sales, history, sell-thru) run once per server process and are then served instantly. After a restart, the first visitor waited minutes with empty sell-thru / LY-growth columns and neutral planner factors. The server now starts all three itself 3 s after launch.

### BIS: the "use" control is now an accessible button
- **Asked (user):** "make the use button a bit more accessible".
- It's a real `<button>` labelled "Use" instead of tiny underlined text, so it can be reached with Tab and pressed with Enter / Space. It's 40×24 px with the suite's pale-fill style (contrast 8.4:1) and a visible focus ring.
- Screen readers hear e.g. "Use the planner's Gr % +8.4% for M_IN_BRIEF, buyer now +9.3%", and the hover text says the same.
- After it's pressed, focus moves to that department's own growth input (the button disappears once the two match). The confirmation message names the department and is announced (`role="status"`).

### BIS: hover message on every Planner Gr% cell explains the number
- **Asked (user):** "how is the planner's growth coming on each cell i want a small message".
- Hovering a Planner Gr% cell (Phase 1 block, or each Phase 2 month) shows four lines:
  1. the factor and its reason;
  2. the three inputs with their bands (sell-thru, LY growth, fill rate, plus the reference department if borrowed);
  3. AOP share by LY cont % × factor → re-balanced ×scale to the division AOP;
  4. the result vs LY.

  Example: "Mar: factor 1.08 - Strong ST → scale / Sell-thru 10.1% (High) · LY growth 19.2% (Low) · Fill rate 85.7% (Good) / AOP share Rs.0.27 Cr × 1.08 = Rs.0.30 Cr → re-balanced ×0.919 = Rs.0.27 Cr / vs LY Rs.0.26 Cr = +6.7%". Division, attribute and grand-total rows say they are the sum of their departments. `_plannerCalc` now keeps each cell's plain share and re-balance scale.

### BIS: the buyer's Gr % starts from the plain AOP share; the gap to the planner's is the factor
- **Asked (user):** "how can buyer's input and planner's input be the same in all departments there must be a difference on the basis of factor"; chose "Plain AOP share".
- Before, the buyer's Gr % was seeded with a copy of the Planner's Gr %. Now it's seeded with the department's share of the division AOP by LY contribution (factor 1.00, i.e. the division's growth that month). The Planner's Gr % keeps the factor and the re-balance to AOP. Example, MENS: M_IN_BRIEF factor 1.08 → planner +8.44% vs buyer +9.28%; ME_BLAZER factor 1.00 → +0.31% vs +8.94% (the factor-above-1 departments take share, so a 1.00 department loses some in the re-balance).
- Buyer-side re-balancing weights are back to LY (they had been the planner's values). "use" now shows wherever the two columns differ; taking it counts as the buyer's choice and survives a re-seed. The seed fingerprint is bumped (`z2`), so every browser re-seeds once; buyers' own entries and locks stay. Removed the now-unused `_plannerVal` / `_plannerSig`.

### Sales Plan: department_state.json committed
- **Asked (user):** "commit department_state.json too". This is the live Department Master state (contribution % and active flag per department, synced from BIS), committed as it stands; it had been left out of commits until now.

### Builds: Sales Plan and AOP Forecaster dist folders committed in full
- **Asked (user):** "commit the dist folders too".
- Both frontends rebuilt from the current source and force-added in full (`git add -A -f`; their `assets/` are git-ignored, so before this only `index.html` was tracked and the committed index pointed at asset files that weren't in the repo). A fresh clone now serves both apps without a build step.

### AOP: calendar-only re-run checked - Version 2 kept (no publish)
- **Asked (user):** "re-run AOP with the new calendars", then "keep version 2".
- I copied Version 2's session (`193eea12`) into the scratchpad and ran it with the same inputs and growth, once on the old (pre-lagan) calendars and once on the new ones. MAMJ (all stores): 954.59 → 954.57 Cr; Jun'27 −0.019 / Jul'27 +0.019 Cr; Mar'27 (override), Apr and May unchanged; Mar'27–Mar'28 total unchanged at 1,337.58 Cr. Nothing was published, saved or locked. Version 2 stays the live, locked AOP.

### Landing: the shared link works every time (one server owns 7800) + 2021→22 calendar re-synced
- **Asked (user):** "sync the 2021 calendar too ... i had shared the ip to other machines too, link is not seeming to work ... make sure that the link works everytime".
- **Cause:** two Landing servers were both listening on 0.0.0.0:7800: the 11:09 one (old code) and a later restart. Python's server sets SO_REUSEADDR, which on Windows lets a second process bind the same port, so each visitor reached one of them at random. Each copy also ran its own watchdog, which is why there were two BIS servers.
- **Fix (`landing_server.py`):** `_ExclusiveServer` binds with SO_EXCLUSIVEADDRUSE and no reuse, and it binds BEFORE launching any app or watchdog. A second copy (scheduled task, Keep Alive, start.bat) now prints "already running" and exits. I cleared the duplicates and restarted from the "RS Planning - Landing Server 7800" task: one Landing, one BIS.
- Checked from this machine: `http://10.0.1.50:7800`, `http://CKHO-L-A9820:7800` and `http://CKHO-L-A9820.citykr.com:7800` all answer (→ sign-in). Firewall allows 7800 on every profile, and sleep is off. The IP comes from DHCP, so share the hostname link.
- 2021 → 2022 Calendar - All re-synced with the lagan rule in place (670 of 3,650 pairs changed, lagan-only; lagan mismatches 792 → 356; 0 reuse). No reindex was needed: snapshots use 2026 → 2027.

### Calendar: three V2 calendars re-synced with the lagan rule + reindexed (data, no code)
- **Asked (user):** "sync now the three V2 calendars and reindex".
- Backed up first (scratchpad `calendar_backup_before_lagan.json`). Day maps were regenerated in place with today's engine and the Drik lagan dates, keeping the same calendar ids and saved_at:
  - 2024→25: 860 of 3,650 pairs changed;
  - 2025→26 All: 1,289 changed;
  - 2026→27 All: 751 changed.
- Without the lagan rule the engine reproduces every stored map exactly, so these changes come only from lagan. Lagan mismatches fell from 922 to 480, 920 to 328 and 1,026 to 474. No LY day is reused.
- Day-count month shares are unchanged. Sales-weighted shares move a little: for 2026→27 only N. EAST / N. EAST - PUJA, where Mar'26 now splits about 72–77% to Mar'27 and 23–28% to Feb'27 (was 77–80%). AOP was not re-run, and the Mar'27 AOP override stays as given.
- Reindex against "2026 -> 2027 Calendar - All": `calendar_reindex_sync` (mw + mw_dept, 4.13M rows read) and `calendar_reindex_dw_sync` (dw, 17.99M rows) both succeeded; `calendar_check_sync` passed all checks.
- The 2021→22 V2 calendar saved this morning was not touched.

### BIS: Phase 1 / Phase 2 + fill rates from the PLAN vs FILL RATE pivot
- **Asked (user):** "transform the model into 2 phases remove the prompt banner keep the model button on topbar, and rename Block wise to phase 1 and the month wise to phase 2 ... Phase 2 changes will be taken to the sales plan ... Pivot has fillrates now configure it accordingly". Choices: Phase 2 keeps BOTH each department's Phase 1 block total and each division-month AOP; fill rate = NEW FILL RATE % (W_CAP).
- The login prompt is gone. The top-bar button reads **Phase 1 · Block** / **Phase 2 · Month** and switches with one click.
- **Phase 1** is unchanged: one Block Growth % per department, flat across the months, re-balanced to each month's AOP.
- **Phase 2** shows a read-only Phase 1 Block Gr% column, then Planner Gr% / Buyer Gr% per month, each with a lock. Editing a month no longer auto-locks it, the same as Phase 1. The edited cell and the locked cells stay; every other cell in the division re-balances (iterative proportional fit), so each department's block total and each month's AOP both hold. If a department has no other unlocked month, AOP wins and the page says how far its block total moved. The magnified monthly editor follows the same rule in Phase 2. Check: `node "Buyer's Input Sheet/test_phase2.js"`.
- Sales Plan: unchanged path. On Save, each department × month growth goes to Sales Plan, which applies it to that month's P1 and P2.
- **Fill rates:** `fill_rate_import.py` reads the DIV - SUMMARY pivot into `fill_rate.json`: 114 departments, plus 11 split departments that take their old name's rate, so 125 in all (78 Good, 35 Avg, 12 Low). Factors → Refresh fill rates re-uploads the workbook (`POST /api/planner/fill-rate`, admin / planner). A department missing from the pivot uses its reference department's rate, else a neutral 1.00 ("not in the fill-rate pivot").

### Calendar Engine: lagan days match lagan days (Drik Panchang dates)
- **Asked (user):** "use the drik lagan dates in the calendar engine too"; chose "match lagan to lagan".
- When the engine picks an LY day for an ordinary TY day, a Drik marriage-muhurat day now pairs with an LY muhurat day and a non-lagan day with a non-lagan day. This is weighed after month, before weekday (`getWeights().lagan = 196`), in both V1 and V2. Festival anchors are unchanged.
- The rule only runs when both years were synced from Drik (`GET /api/calendar/lagan-dates`, read from `Landing/lagan-drik.json`); otherwise the engine behaves exactly as before.
- BIHAR 2026→27 test: lagan mismatches 91→32 (V1), 93→33 (V2). The rest are months where the two years have different lagan counts (e.g. Jan 2026 has 0, Jan 2027 has 9). Same-weekday pairs drop by about 20 days, as that rule now comes second. Month placement, no-reuse (V2) and month adjacency are unchanged (`engine.test.mjs` test10).
- **Locked calendars are not regenerated.** Their Calendar Library cards will show "Out of sync" until Sync Now (or Create Calendar → Lock & Save), followed by a reindex.

### Landing: Lagan Calendar = Drik Panchang's own list + "Sync with Drik Panchang" button
- **Asked (user):** "check why is there a difference with drik panchang in lagan dates and give me a proper refresh button to sync it".
- **Why it differed:** the page computed dates itself from tithi, weekday, Holashtak, Chaturmas, Navratri and Pitru Paksha only. Drik also rules out Kharmas (Sun in Dhanu / Meena), Guru / Shukra asta, Adhik maas, days without an auspicious nakshatra and bad yoga / karana, so 2026 showed 99 dates against Drik's 59 (e.g. Jan 2026: 13 vs 0, Shukra asta).
- Now: `Landing/lagan_drik.py` reads Drik's marriage-muhurat page (New Delhi) per year into `Landing/lagan-drik.json` (2000-2030 seeded today). The calendar shows those dates, with "Drik Panchang · synced <date>" per year; an unsynced year falls back to the computed list, marked "Approximate".
- **↻ Sync with Drik Panchang** re-fetches the selected years (`POST /api/lagan/refresh`, sign-in needed). A year Drik can't be reached for keeps its last synced dates and the error is shown. Check: `python Landing/test_lagan_drik.py`.

### BIS: Planner Value shows "Cr" on every row
- **Asked (user):** "missing the Cr in the end of each value" (Planner's input -> Planner Value). Only the grand total had it; department/attribute rows now read e.g. Rs.1.0 Cr.

### Calendar: MW Comparison tab removed (month-wise too)
- **Asked (user):** "remove mw comparison" (on a month-wise result).
- Tab, its store-month table and its CSV export deleted. Month-wise tabs: Reindexed Sales, Monthly Summary, By Cluster, Month Wise Matrix, P1 / P2 Comparison, Run Details.

### Calendar: Monthly Summary and MW Comparison only for month-wise reindex — `e9433ca`
- **Asked (user):** "remove monthly and mw comparison from date wise indexing citing no relevance, keep them in the month wise indexing".
- Day-wise results: Reindexed Sales, By Cluster, DW Comparison, P1 / P2 Comparison, Run Details. Month-wise keeps Monthly Summary and MW Comparison.

### Cleanup: unused data files removed, 30 GB of old reindex jobs pruned — `eb00a6a`
- **Asked (user):** "yes, prune the old reindex folders, remove the unused data files."
- **Reindex jobs:** 146 folders (24 Aug – 26 Sep, 30.0 GB) under the platform's `calendar_engine/Local DB/reindex_jobs` deleted (untracked; regenerable by re-running a reindex); the 8 newest kept.
- **Removed from git (recoverable from history):** Sales Plan old Actual Sales workbook, old parquet-sync caches, a duplicate MRP Cont % copy, Attribute Master outputs, NEW Departments.xlsx, start.bat.bak, watchdog.log; AOP inputs_from_config.xlsx, output/AOP_Forecast.xlsx, backend.log, diff_archive; BIS AOP/ reference workbooks + the stale `/buyer/demo` page; Calendar legacy `local_server.py` + `calendar_engine.html`, backup JSONs, Default Template.xlsx, an old CSV export. Kept: Sales Plan MRP Cont % / PPO Cont % (the only versioned backups of files the engines read from outside the repo).
- Test sweep 39/43 (baseline 38/43) — the same 4 stale tests fail. Listing/delisting sync re-run after the 11:01 MemoryError: ok — all 10 syncs green.

### Calendar: Download Festival Dates (festivals × years, no clusters) — `0a27f8e`
- **Asked (user):** "download the festival list with their bulk year dates ... ranging from year to year as per the selection. No clusters nothing just festivals".
- **Moved to the Version Setting tab** (`8d517ed`, user: "give me the festival bulk year feature here"): a **Festival Dates** card under Calendar Years — From Year → To Year + **Download Festival Dates (CSV)**; the Festival Master toolbar copy was removed. One row per festival (calendar order), one column per year (DD-Mon-YYYY): Google reference first, then the built-in table, blank if neither (no estimate). Defaults to the Version Setting years; up to 21 years.

### BIS: Planner's input beside the buyer's growth — `1b7d384`
- **Asked (user):** a planner's input from a fill-rate / factor grid, in parallel with the buyer's input — "Planner's input to be parallel to the final Value ... both the growth % will be in parallel and both values will be in parallel for the buyer to choose"; factor table revised 5 Oct; SSG = the 25V26 cohort; reference departments = Sales Plan's mapping; "do not hardcode the prompt banner to block MAMJ".
- **Planner's value** = factor × (division AOP × department LY cont %), re-balanced so each division × month equals AOP; **Planner Gr %** = value ÷ LY − 1, locked. Columns: Factor | Planner Gr% | Planner Value | Block Growth% (buyer) | Plan Total / vs LY% (final); Month wise shows Planner Gr% + Buyer Gr% per month.
- **Factor table** (`factor_table.json`, shared): Avg Weekly Sell-Thru % × LY Growth (25V26, MAMJ'26 vs '25, value) × Fill Rate → 0.80–1.20. **No fill-rate file yet → every factor 1.00 ("fill rate pending")**, so numbers are unchanged today (verified: planner Gr % = current growth to 1e-13, planner sums = AOP). Only an admin / planner can save it (server checks the platform session; 403 otherwise).
- Buyer's Gr % defaults to the planner's; a buyer's own entry supersedes and survives re-seeds; **use** restores the planner's. Re-balance weights by planner value. **Block wise / Month wise** prompt once per session + Mode button. Value only — no quantity.

### Calendar: Lock & Save name defaults to "LY -> TY Calendar - All" — `8cc5ea2`
- **Asked (user):** "when i lock and save the default field should be LY -> TY Calendar - All always, where LY & TY is to be taken from version setting".
- The prompt pre-fills `<Reference year> -> <Future year> Calendar - All` from Version Setting (was `<cluster> Calendar`); still editable, and an existing name still overwrites that template. Calendar `dist` rebuilt and committed in full.

### BIS: buyer growth reaches Sales Plan only on Save — `103de79`
- **Asked (user):** "yes, push only on Save" (readiness review CRITICAL: opening BIS in a fresh browser silently overwrote the live buyer plan in Sales Plan with plain AOP seeds).
- `saveState()` pushes only from the **Save** button; seeding, version loads, department moves and visibility changes save in the browser only. Verified: a fresh load seeds 944 cells and sends nothing; Save sends one POST (944 rows).

### Readiness review (Calendar, AOP Forecaster, BIS) — security fixes — `ccd94d4`
- **Asked (user):** "deploy agents to check the whole 3 core apps till BIS so that its made to be ready for deployment post review to the stakeholders"
- **AOP Forecaster — CRITICAL fixed:** `_session_dir` took any session id, so `GET /api/session/..` (also `%2e%2e`, `..%5C`) returned 200 from the app folder and `DELETE /api/sessions/{id}` (no login on 8000) could `rmtree` the app folder or above. Session ids must now be UUIDs (all 132 real ones are) — else 404. Verified live.
- **AOP Forecaster — a run no longer freezes the server:** `/api/run` was `async def` around the CPU-bound engine, blocking 8000 and, when mounted, Calendar / Sales Plan on 8010 for every user. Now a worker thread; runs stay one at a time (shared engine files).
- **Calendar — path fix:** `_recover_reindex_job` joined any job id into a path (`..\..\Users`, `C:\Windows`); non-UUID ids are now ignored; real jobs still recover.
- **Ops:** a second Landing server was bound to 7800 again (Windows lets two processes share the port); the duplicate was stopped, 8000/8010 relaunched by the real Landing's watchdog.
- AOP + platform tests identical to the baseline.

### Cleanup — dead code and stale files, no behaviour change — `9e85e6d`, `4c1726c`
- **Asked (user):** "analyse the whole app and the functionality, delete extra lines of code, duplicate codes or extra trash stores without hampering the rules and code in the app"
- Five read-only reviewers mapped proven-unused code per app; only items referenced at their own definition (git grep + AST) were removed: Sales Plan 96 lines (dead loaders / constants, unused imports); Re-Aligner 3 lines; Listing scripts / CSS 15 lines; `Landing/lagan-dates.json`. Each app's tests match the baseline.

## 2026-10-02

### Growth vs LY: the source plan's tags group the stores, as they are — `ce49347` (reverts `55de313`)
- **Asked (user):** "this rule is to be changed - follow tags from source plan as that will guide you to group you just have to plot ly numbers accordingly without fail according to the tag, and the new tags will follow without ly numbers"
- The comparable-store rule (SSG only with LY in every month) is removed: every store is grouped by its own SSG TAG in the source plan; a store with no LY (e.g. BRN, SAH, SBW, tagged SSG in main.xlsx) shows LY 0 under its tag. No "SSG TAG (plan)" column any more.
- main.xlsx, SSG stores: OND +23.1%, JF +9.9%, TTL +18.9% (KIDS 20.0%, LADIES 18.2%, MENS 18.5%). `test_gr.py`: an SSG-tagged store with no LY stays SSG with LY 0.

### Growth vs LY: an SSG store needs last year's sales in every month — `55de313`
- **Asked (user):** "i have uploaded the main source plan with correct tags now implement the fix" (main.xlsx: one tag per store now; BRN / SAH / SBW are SSG, "032 - Stores" / "125 - Stores").
- **Rule:** a store tagged SSG counts as like-for-like only with LY sales in **every** LY month (Oct'25 … Feb'26 P2) — the Re-Aligner's comparable-store rule; otherwise it counts as OTHERS. The plan's tag is kept in the workbook's new "SSG TAG (plan)" column and the page names those stores.
- **main.xlsx:** BRN, SAH, SBW have no LY in the data lake at all (under any store name; the lake's unplanned stores NBR, BDN, ABT, VSM, GPB, TZP are closed ones) → OTHERS here. SSG growth: OND **+20.1%** (was 23.1%), JF **+7.6%** (was 9.9%), TTL **+16.1%** — the same 120 stores as the 3.9.26 file.
- `test_gr.py`: an SSG-tagged store with no LY counts as OTHERS, its TY stays out of the SSG pivot.

### Growth vs LY: block headers name their TY and LY months — `995ea29`
- **Asked (user):** "LY should be 2025 OND and 2026 JF, and TY should be 2026 OND Plan and 2027 JF Plan" — already the pairing (each plan month vs the same month a year earlier); the headers only said OND / JF.
- Headers now read "OND · TY Oct'26–Dec'26 plan vs LY Oct'25–Dec'25 sales", "JF · TY Jan'27–Feb'27 plan vs LY Jan'26–Feb'26 sales", "TTL · TY Oct'26–Feb'27 plan vs LY Oct'25–Feb'26 sales" (worked out from the plan's own months).

### Growth vs LY: LY covers every department of the plan's divisions; lake names normalised — `ae89c5f`
- **Asked (user):** "This is my LY figures check why is there big difference in between mine and yours" — theirs (GR % PLAN 3.9.26, all stores) Oct'25 9,623.45 … Feb'26 P2 4,439.56 = 43,221.84; the app's screen showed 35,033.40.
- **Why:** (1) the screen had the **SSG** filter on (SSG stores only); all stores was 42,671.84. (2) **133 L**: the lake spells KI_AP_BABA SUIT NEW BORN  F/S with two spaces, the plan with one — no match. (3) **~416 L**: departments that sold last year but have no line in the final plan (LW_U_T-TOP F/S 214, KB_BABA SUIT DNM F/S 156, KI_AP_CASUAL SHIRT F/S 24, KI_AP_TOP F/S 19, MU_CORD SETS 3) weren't counted. Renamed / split departments (MSE_PYJAMA = MSE_HSR + TXTL PYJAMA, LW_L_JEGGING / PALAZZO → JOGGER / PALAZZO splits, KB_T-SHIRT H/S = POLO + R/N …) net to 0.
- **Fix:** LY = every lake department of the plan's divisions (KIDS / LADIES / MENS) in the plan's stores, a department the plan doesn't have shown with TY 0 under the lake's division / attribute; names collapsed to one space.
- **Now:** all stores LY 43,336.15 (vs 43,221.84). The 114 L left = departments with LY in neither the final plan nor the 3.9.26 file (ME_BLAZER SUIT 43.9, LW_L_CULOTTES 25.8, KB_BLAZER SUIT 24.0, LW_U_CROP TEES 6.4, KG_CAPRI SET 6.0, MU_SHACKET 3.6 …) — that file's department list came from the plan as it was on 3 Sep. SSG stores: LY 35,589.74, growth +18.9%.
- `test_gr.py`: a double-spaced lake name lands on the plan's name; a KIDS department the plan dropped keeps its LY (TY 0, lake attribute); a FOOTWEAR department is left out.

### Sales Plan Re-Aligner: the final plan keeps the original rows in their order; new row-order check — `54a615b`
- **Asked (user):** "Check this - why is the output changing in method 1 after re-allignment, put a check in mehtod 1 that the store x division x month should be the same after re-allignment" (a pivot of Original / Method 2 / Method 1 by store, Oct'26: Method 1 gave MAR 51.94 vs 55.34, AD-NS-04 20.56 vs 0, NS-41 190.41 vs 0 …).
- **Cause:** the plan was right — every store × division × month of "Realigned Plan Post Listing" equals the original (the run's check: 0 of 6,384 off; per store Oct'26 MAR 55.34 = 55.34). But its **rows were in a different order**: a department rebuilt for a new listing (all-zero rows in the original) was dropped and re-added at the end, so only 0.34% of rows stayed in place. Taking the Method 1 values row by row against the original's rows reproduces the pivot exactly.
- **Fix:** every original row now keeps its place. A rebuilt store-dept reuses its own rows where MRP × display match the source store and only adds the source's other rows, after all original rows. On your file: 676,704 of 676,704 rows in place; values identical to before (1e-14); a row-by-row pivot now equals the original per store (max difference 0.0).
- **Checks:** "Store × Division × Month = original" already runs on every method; new **"Original rows kept in the file's order"** fails if rows ever move again. All five methods re-run on the real plan: every check ok.
- `test_realign.py`: a rebuilt department keeps its row in place and adds the missing MRP row at the end, with the source's 3 : 1 mix.

### Growth vs LY — new app on Landing (`/growth/`, port 8075) — `156a0ac`
- **Asked (user):** "check this format and design a convertor for me so that whenever i want to input old data and the final sales plan it can plot the data against ly according to the hierarchy given in the sale splan" (format: GR % PLAN - 3.9.26.xlsb). Chose: LY "Auto from data lake"; "New app on Landing".
- **Input:** the final sales plan (xlsx / xlsb / csv, any header row — the Re-Aligner's importer).
- **LY, by itself:** the data lake's day-wise sales (latest complete export via `rs_common.lake_files`), the same months a year earlier, value ₹ ÷ 1e5 = lakhs and qty. A P1 / P2 month is split last year at the middle day: **P1 = 1st–15th, Feb 1st–14th**. Checked against the 3.9.26 workbook: full months match the month-wise lake exactly; Jan P1/P2 match 98% of rows at the 15th, Feb 98–99% at the 14th. The rest are departments renamed or split in the lake since then (MSE_PYJAMA, KB_BERMUDA, LW_L_JEGGING …), which the final plan's names now follow. Stores with no LY (new stores) show LY 0, as in that workbook. The first read takes ~2 min, then it's cached per lake export.
- **Screen:** Division › Attribute › Department (the plan's hierarchy) with each block (e.g. OND / JF — months grouped by calendar year) and the season: TY, LY, growth % (TY ÷ LY − 1, same stores). There's an SSG TAG filter (SSG by default, or All stores) and a month-by-month TY vs LY chart for any row.
- **Download — GR % PLAN workbook:** MAIN (one row per Store × Department in the 3.9.26 layout: Div Conc, Dep Conc, Division, STORE NAME, DEPARTMENT, ST TAG, ATTRIBUTE, SSG TAG, TY value / qty, LY value / qty by month with block and season totals, plus growth % per block and season) + PIVOT for the chosen tags + PIVOT ALL. "TTL Qty LY" is the season total (the 3.9.26 file repeated SOND there).
- **On your plan (NEW FINAL):** SSG stores: KIDS +23.4%, LADIES +20.6%, MENS +18.9%, total +20.8% (42,314.79 vs 35,033.40 L). All stores: +72.7% (new stores have no LY).
- **Landing:** watchdog entry, `/growth` proxy route + slash redirect, card. Landing restarted once (4 stale duplicate processes cleared).
- `test_gr.py`: P1/P2 cut (Jan 15th, Feb 14th), rupees → lakhs, blocks, MAIN totals, LY-only rows kept, pivot growth.

### Sales Plan Re-Aligner: engine delays cut — Method 1 run 100 s → 10 s — `cda7b06`
- **Asked (user):** "cut the delays in all the method engines"
- **Timed on your plan** (676k rows; check → realign → verify), old → new:
  - Method 1 (your 53,504-row listing file): 7.9 + 90.6 + 2.0 s → **3.0 + 5.9 + 1.4 s**
  - Method 2 re-phase LW_U_T-TOP: 0.6 + 5.2 + 1.2 → 0.6 + 4.9 + 1.2 s
  - Method 3 split, Method 4 shift, Method 5 growth: ~9 s → ~8 s each
- **Causes:** `add_new_departments` copied rows once per new listing and rebuilt a set inside its loop (37 s); `np.isin` on string keys is quadratic (53 s, two calls); `listing_targets` recomputed the same peers' cont % 1.7M times. Now: one merge, hash-based `isin`, memoised cont % / cluster averages.
- **Same results:** every method's output compared old vs new engine on the real plan — identical rows, max difference 0.0.
- **Not changed:** the xlsx downloads (full plan ~75 s, plan-to-plan longer) are xlsxwriter's own speed; CSV takes ~9 s.

### Sales Plan Re-Aligner: Method 1 new listings stay inside their attribute; exact 6-decimal download — `d8d1888`
- **Asked (user):** "check pdh its original plan differs from the final output … new final is the source … fix the method 1" (files: Realigned Plan NEW FINAL = original, Realigned Plan Post Listing = the Method 1 output).
- **What PDH showed:** PDH plans about 173 of its 176 Y listings already in NEW FINAL, so they were correctly left as they are (the file's L_EW_DRESS FABRIC / L_EW_SAREE_TANT are N, and already 0). PDH's one truly new listing, MSE_JAMAICAN (SUMMER), was re-split over the **whole** MENS division (`div_cap`), so every MENS attribute (HVY WINTER, REGULAR …) gave a little.
- **Fix 1 — attribute cap for listings:** `prepare_listing` no longer sets `div_cap`. A new listing comes out of its own store × division × attribute; a month the attribute can't carry moves to the listing's other months, and only an attribute with no room at all spills to the store × division (29 on your file, flagged). PDH's attributes are now untouched; MSE_JAMAICAN keeps its season 0.0514 (Jan P1 moves to later months: SUMMER is 0 there).
- **Fix 2 — each listing keeps its own season:** when several revised departments overflow one bucket, the move kept only their combined season (ANG KIDS SUMMER listings up to 0.026 L off each). An iterative proportional fit (month totals and each store-dept's season both fixed; whole store-depts scaled, so MRP × display mix is kept) now keeps each one's own. The check reads "warn: moved to fit the cap; every revised store-department keeps its season total".
- **Fix 3 — exact download:** the final plan was rounded to 6 dp cell by cell, which put 227 store × divisions up to 1e-5 off and the grand total +0.0008. `engine.round6` rounds with largest remainder inside each store × division × attribute × month (division for spilled ones): every total now matches to 1e-15, grand 73,685.195573 = original; no cell moves more than 1e-6.
- Re-run on your files: every hard check ok (cap 0 of 37,289 off, store × division × month 0 of 6,384, grand total, no negatives, display-type mix).
- `test_realign.py`: two revised departments overflowing one attribute keep their own seasons, the other attribute untouched; `round6` lands thirds on their exact total.

### Sales Plan Re-Aligner: Method 4 template fixed, Method 5 grows P1 / P2 months, no default month lock — `227f2f2`
- **Asked (user):** "method 4 is broken check it, and check why method 5 has a lock in it for JF as it is not there. the month lock only can be configured if the user has set it"
- **Method 4 — blank template crashed:** `template_shift` added TARGET after FROM MONTH, which the Method 1 blank template (`Department | Store | Listing (Y/N)`) no longer has. It is now `Department | Store | Listing (Y/N) | Target`; the Listing-app pre-filled one is unchanged.
  - Checked on your plan: a delisting into a section and the checks all pass (cap, store × division × month, grand total 73,685.20 → 73,685.20).
  - A section target with no department of the listed one's attribute in that store (e.g. LW_U_TEES F/S is PREWINTER; AD-NS-08's L_WESTERN_UPPER has none) now says that instead of "target isn't planned".
- **Method 5 — Jan / Feb looked locked:** growth needs a last-year month, and a P1 / P2 half-month has none, so Jan'27 P1/P2 and Feb'27 P1/P2 were dropped. `engine.ly_groups` now pairs the halves and compares them with last year's whole month (Jan'27 P1 + P2 vs Jan'26). One `Jan'27 GROWTH %` column sets both halves. A month with a locked half is left out.
- **No default lock:** `engine.FROZEN` was Jan / Feb, so every newly loaded plan had them locked. It is now empty: a month is locked only when the user clicks it. Five older workspaces whose saved locks were exactly that default were reset (backups `locks.json.bak`); your main workspace had none.
- `test_realign.py`: no default lock; fixtures lock Jan / Feb explicitly; P1 grown vs last year's Jan; one locked half drops the month; Method 4 blank template columns.

## 2026-10-01

### Sales Plan Re-Aligner: step-2 warning for new listings in stores with no plan — `e6a89c5`
- **Asked (user):** "yes, add the warning in step 2", after PDH (an FY27 Q3 opening store, 0 in the whole original) got no plan for KB_BABA SUIT TXTL H/S though its REF NGC plans it.
- **`importer.prepare_listing` (Methods 1 and 4):** every Y listing (no own values) whose store × division has **no plan in the original for the months it applies** is counted.
  - The warning names every store, and the store × division examples with listing counts.
  - It says why the listings stay 0 (Store × Division × Month always matches the original) and the fix: give the store its plan (AOP / NSO opening plan) in the original file and reload it.
- **Your file:** "7129 new listing(s) in 123 store x division(s) … Stores (41): AD-NS-04 … NS-90, PDH".
- `test_realign.py`: S3 with no LADIES plan lists B → named; S2 / C has a plan → not named.

### Sales Plan Re-Aligner: recheck — a failed check repairs the output and verifies again until it passes
- **Asked (user):** "also install a rechecker if the check fails at any level then it should auto run till it passes through"
- **Why not a plain rerun:** the realign is deterministic, so the same inputs give the same output and the same failure. Each recheck round therefore **repairs** the output instead.
- **One repair round** (`engine.repair`):
  - negative cells in unlocked months go to 0, the amount out of the rest of that store × division × month;
  - every store × division × month is put back exactly on the original (positive cells scaled; one with nothing left gets its original rows back);
  - qty is rescaled for the cells it moved, and locked months are never touched.
- **The loop** (`server.job_run`): repair → verify, until every check passes, a round fixes nothing more, or **5 rounds** (never endless).
  - The repaired store × divisions are checked at division level.
  - The cells it moved show in the comparison as "rechecked - fixed to fit the original" (`engine.merge_compare`).
  - A note says how many rounds ran and anything still failing that it can't fix, e.g. a revised value that conflicts with the original totals.
  - The Results line shows "rechecked n×".
- `test_realign.py`: a good output is broken on purpose (S9 Sep +5 over the original and one negative cell). The repair loop brings every hard check back to ok, leaves the locked month untouched, and a further round finds nothing to fix.
- On your current listing run every check already passes, so the recheck doesn't trigger; it's a safety net.

### Sales Plan Re-Aligner: new listings fall back, month by month, to the cluster's non-zero average cont % — `461ca9b`
- **Asked (user):** pasted ~7,800 store × department listings that came out at 0: "Check these cases, even though plan is present in their respective refernce stores, so either it should check the sales of store's respective cluster average without 0% cont % and appportioning should be there within the same store xdivision".
- **Found** (replaying "Listing changes template (4).xlsx"): 7,841 of 7,991 new listings were 0.
  - **7,129**: the store has **no division plan** in the unlocked months (40 stores not trading yet: AD-NS-04…09, NS-40…90, CND, KRB), and x% × 0 = 0.
  - **712**: the REF store plans the department, but **not in the months the store trades**. E.g. AD-NS-10 opens Feb'27, and its REF LAM plans KB_T-SHIRT F/S Oct–Jan only.
- **Rule** (`engine.listing_targets`, Methods 1 and 4):
  - Per month: the REF store's cont %.
  - Where that is 0% (or there is no REF store): the **average cont % of the same-cluster stores above 0% that month**, with 0% stores left out.
  - Else the same over every store planning it.
  - × the store's division AOP. The store × division gives way as before.
  - The cluster fallback is now this non-zero average (was a pooled share).
  - The "How it was built" sheet gains a per-month "<m> CONT FROM".
- **Your file replayed:**
  - **418 listings get a plan (was 150)**. Still 0: 7,129 with no division AOP and 444 that no store plans in those months; nothing to size from.
  - All checks ok: Store × Division × Month 0 / 6,384 off, grand total 73,459.07 → 73,459.07.
  - The upload check takes 8.3 s.
- **Tests:** a REF store at 0% in Nov now takes all stores' non-zero average (20/80 × 8 = 2), and Sep stays REF 0.5 × 8 = 4. The no-REF cases now expect the non-zero average.

### Sales Plan Re-Aligner: Store × Division × Month always equals the original file
- **Asked (user):** "how to reload the checks if they fail" (screenshot: 4 failed checks, grand total 73,459.07 → 73,422.05). Chose "Rest of the store × division" for the cause. Then: "the store x division x month wise data should match with the sales plan i nthe original file always. Also, make sure that the plan is intact not incremental or decremental against the sales plan in the original file".
- **Cause:** 11 delistings (all OCCASIONAL) of a department that was the only one of its attribute in that store × division. The attribute cap left nothing to absorb them, so 37.02 L of AOP was lost.
  - Stores: AKN, BKR, BWR, CNW, PBS, SBA in LADIES; BRP, DMB, DTG, GPG, KGT in MENS.
  - Re-running can't fix it: the checks are recomputed from the output.
- **Step 2a (fallback):** a bucket still off its original after the attribute-level apportioning hands its balance to the other departments of its store × division, pro-rata. Revised departments keep their values.
  - Those store × divisions are checked at division level (`out.attrs["spill_div"]`, merged into `verify` / `compare_levels`).
- **Step 2c (guarantee):** after all the rules and the negative pass, a store × division × month that is still off has every positive cell scaled onto the original. Revised ones are included; this is flagged and recorded in `out.attrs["forced_div"]`, and "Revised values kept exactly" is a warn there.
  - One with nothing left to carry its plan (every department 0) keeps its **original** plan that month, flagged as "kept exactly as the original file there, the change not applied".
  - So the plan is never up or down against the original.
- **Your run replayed** (your original + "Listing changes template (4).xlsx", in memory): every check is ok. Store × Division × Month 0 / 6,384 off, grand total 73,459.07 → 73,459.07, attribute cap 0 / 26,964 off (324 store × divisions at division level).
- **Tests:** a new fallback case (a lone OCCASIONAL delisting absorbed by REGULAR, S1 stays 70). The old "sole department revised down stays short" cases now expect it held on the original.

### Sales Plan Re-Aligner Method 4: new listings sized by the REF store rule too
- **Asked (user):** "yes, apply the REF store rule in method 4 too"
- **Change:** `engine.shift_targets(..., ref_of)` passes the plan's REF Name column to `listing_targets`.
  - A Y listing shifted out of a target is sized like Method 1: the REF store's cont % first, then the same-cluster stores, then all stores, × the store's division AOP.
  - It still comes **only out of its target** (capped at what the target has); nothing else moves.
  - The step-2 note says how many listings used the REF store.
- **Real plan check (in memory):** NAH + L_EW_SAREE_TANT out of L_EW_SAREE_FNCY. Oct 0.281636 (same as Method 1, from BGI); L_EW_SAREE_FNCY 1.931350 → 1.649714. All checks are ok.
- `test_realign.py`: S3 lists B out of A, pooled 15/80 × 8 = 1.5 vs REF S2 0.5 × 8 = 4.
- **Restart:** stopped every 8070 listener, and confirmed the new process post-dates the edit.

### Sales Plan Re-Aligner Method 1: new listings sized from the REF store's cont %, the whole store × division gives way, and a Listing check file
- **Asked (user):** "first the store if found in such a case should look for refernce store cont % if not found then only cluster cont % will be taken will be apportioned on the respective store's cont % scale and then store x divsion aop will be multiplied on store's cont % on display so that the final plan can get adjusted according to the new listing. Also, give me a comparitive plan just like mehtod 2 in method 1". The user chose "Whole store × division" and "Check-file before running".
- **Sizing** (`engine.listing_targets`, new `ref_of`): a Y listing with no plan in the store takes, month by month, the department's **cont % of its division in the store's REF store** (the plan's REF Name column) when that store plans it.
  - Fallbacks: pooled over same-cluster stores that plan it, then every store that does.
  - Value = that cont % × **this store's division AOP**.
  - Its MRP × display rows come from the REF store, otherwise the biggest peer.
  - Returns a `how` list with, per month: cont %, division AOP and new value.
- **Giving way** (`cap_key`, `realign`, `verify` and `compare_levels` take `div_cap`):
  - A store × division with a new listing is capped at **store × division**, so all its other departments scale by (1 − cont %) and the division AOP stays exact.
  - Every other bucket keeps the attribute cap, and delistings stay inside their attribute.
  - The comparison marks those attribute rows "n/a - new listing, capped at store x division".
- **Listing check file:** a step-2 button once a valid Method 1 file is uploaded; `GET /api/template?method=listing&kind=check` → `importer.listing_check`. It runs the realignment in memory and gives three sheets:
  - **Comparison**: every department of the touched store × divisions, Original / New / Change per unlocked month and season, marked newly listed / delisted / gives way.
  - **How it was built**: REF store or cluster, cont %, division AOP, new value.
  - **Store x Division**: season totals.
- **Real plan check ("Realigned Plan (Final).xlsx", in memory):**
  - NAH lists L_EW_SAREE_TANT and takes REF store BGI's cont % (Oct 1.4787%) × NAH LADIES AOP 19.0462 = 0.281636.
  - The other 51 NAH LADIES departments scale by exactly 0.98521305, and NAH LADIES stays at 58.888313. All checks are ok.
  - 174 of 304 stores have a REF store in the plan.
- **Ops:** a stale Re-Aligner process (16:58) was still answering on 8070 next to the restarted one, since Windows lets two servers bind the same port. It was stopped; the live process now post-dates every edit.
- `test_realign.py` covers: REF-first sizing (S3 with REF S2 → 0.5 × 8 = 4, vs 15/80 pooled), the division-level giving way even when the attribute isn't planned in the store, the cap checks, the "n/a" label, and the check file's labels.

### Sales Plan Re-Aligner: Method 1 blank template is Department | Store | Listing (Y/N) — `2730379`, renamed in the next commit
- **Asked (user):** "i want this as blank template headers instead of the current one" (screenshot: Department | Store | Value); Value = the Y / N listing flag (user's choice). Then "rename Value to Listing (y/n)".
- **Rename:** the third column is now **Listing (Y/N)**, which was already a LISTING alias. A file with a "Value" header still reads; the test covers both.
- **Template:** `importer.template_listing` (blank, without the Listing app) returns just **Department, Store, Value**. It used to be STORE NAME, DIVISION, DEPARTMENT, LISTING, FROM MONTH, NOTE and "<Month> New".
- **Reading:** "VALUE" is a new name for the LISTING column (Y = newly listed, N = delisted). An optional FROM MONTH and "<Month> New" values are still read if added.
- **Unchanged:** the "From Listing / Delisting Analyser" pre-filled template keeps its columns.
- **Text:** the Method 1 how-to and rules text are updated.
- **Verified:**
  - `test_realign.py` checks the blank columns, and that a Department,Store,Value file delists correctly.
  - The live download ("Listing changes template.xlsx") has exactly Department | Store | Value.

### Sales Plan Re-Aligner: results laid out tighter, tables first
- **Asked (user):** "can we squeeze the layout a bit - and move the results up so it can look less calutrophobic as of now"
- **New order in Results:** summary stats → **Revised departments / Division × Month** tables → checks → notes → downloads. The tables used to sit below all the checks.
- **Compact checks:**
  - a grid, two to a row on desktop and one on a phone, with smaller padding and type;
  - a warning or failed check sorts first, spans the full width and gets a tinted border.
  - At desktop width the eight checks take ~300 px (was ~600).
- **Checked in the browser** at desktop and phone width.

### Sales Plan Re-Aligner: no negative plan — negatives set to 0, balance re-apportioned in the bucket
- **Asked (user):** "if there was a plan of -0.01 and in the apportion it should be covered to 0 and the balance should follow the rules set for apportion. this rule is just for redacting the negative plan to 0 and readjusting the value to its respective store x div x attribute x month after apportion."
- **Rule** (`engine.realign` step 2b, helper `_take_back`): after apportioning, every negative cell in an **unlocked** month becomes 0. What that adds comes back out of the same Store × Division × Attribute × Month:
  - from a revised department's own positive rows, for its negative row, so its value stays as given;
  - otherwise from the other departments' positive cells, pro-rata;
  - then from the revised ones;
  - anything still uncovered is flagged.
  - Locked months are never changed, negatives included.
- **Shown in:**
  - Status "negative set to 0" in the comparison.
  - A note with the count and total.
  - A new check, "No negative plan in the unlocked months".
- **Display-type check:** the cont % check skips store-dept-months that had a negative row, since its mix moves by design.
- **Real plan (in memory, LW_U_T-TOP re-phase):**
  - The original has 1,720 negative cells (−4.92 L); 113 are in the locked Jan/Feb months and stay.
  - All 1,607 in unlocked months (−4.75 L) went to 0, and every check is ok: cap 0/43,632 and 0/7,272 off, revised values exact, grand total 83,848.99 unchanged, display-type mix kept.
  - Each balance is spread pro-rata over its bucket, so many more cells move by tiny amounts (≈244k "absorbed").
- `test_realign.py`: a revised department's negative row and another department's negative both go to 0. The revised value stays exact, the balance comes pro-rata out of the others, and a locked-month negative is kept.

### Sales Plan Re-Aligner: downloads in two groups with one XLSX ⇄ CSV slider
- **Asked (user):** "compile the downloaded options in 2 categories - comparison and final plan and give a slider for the user to download in xlsx or csv"
- **Groups:**
  - **Comparison**: Comparison vs original, Plan to plan.
  - **Final plan**: Full realigned plan.
- **Slider:** one **XLSX ⇄ CSV** slider in the Downloads header switches every card, its description and its Build & download button.
  - The choice is remembered in the browser (localStorage, falling back to XLSX).
  - The six cards became three.
- **"about —" removed:** a download with no timing yet shows no estimate.
- **Checked in the browser:** groups and cards render, the slider flips all three cards to CSV and back, and the Downloads block doesn't overflow at phone width.

### Sales Plan base plan = BIS: inactive departments in KIDS / LADIES / MENS are no longer planned
- **Asked (user):** "base plan will be the same as generated by bis", then "cord sets is a new department", then chose "Respect inactive in KLM".
- **Found:** `run_dept_plan` takes its departments from `_build_master()`, which ignores the Department Master's active flags, so every department was planned. LW_U_CORD SETS (new, inactive) carried its stray LY at 0% growth, which put LADIES 0.02–0.03 L a month over BIS.
- **Rule:**
  - In KIDS / LADIES / MENS, a department the master marks inactive gets 0, **unless BIS gives it growth**. BIS is the plan: L_EW_BLOUSE is inactive in the master but +10% in BIS, so it stays. BIS's delisted departments come as −100% and drop out either way.
  - GM / RETAIL are untouched: their flags come from the BIS sync, which doesn't cover them, and 95–99% of their plan is flagged inactive.
- **New departments:** a department the New Department template plans (carved from its reference) is switched active, so its carve counts in the division total.
  - CORD SETS now gets its plan only from a template row (reference department + %).
- **Verified (in memory, nothing saved):** SSG base plan vs BIS publish 112, Mar–Jun'27. KIDS / LADIES / MENS are within 0.0004 L of BIS every month (was LADIES +0.03). The remainder is the known LY-base gap.
- `test_new_dept_template.py` covers an inactive department turning active from the template. The other engine tests pass.

### Sales Plan Re-Aligner: "Plan to plan" download — the whole plan, original vs final, row for row
- **Asked (user):** "i want a full plan to plan comparison not just the changes which have happened, the comparison should be covering a full display type plan mapping original vs final so that i can easily point where the changes are made"
- **New download (XLSX and CSV):** `engine.plan_to_plan` / `export_plan_to_plan`, export kind `plan`.
  - **Rows:** one per Store × Department × MRP × Display Type of either plan, with Division and Attribute.
  - **Up-front columns:** **Changed** (Yes), **Months changed** and **Row** ("new in final" for a new department's rows).
  - **Values:** per month, Original / Final / Difference, then the season, all at 8 dp.
- **Real plan (LW_U_T-TOP re-phase):** 674,478 rows. 48,710 changed, all LADIES REGULAR departments. Season Final = plan total. Built in 3.4 s; CSV ~50 s (235 MB), XLSX ~4 min (84 MB).
- `test_realign.py` checks every row is present, new rows are flagged, Original / Final / Difference are right, and unchanged rows have 0 difference.

### Sales Plan Re-Aligner: the cap is now Store × Division × Attribute × Month (no cross-attribute apportioning) — `8287980`
- **Asked (user):** "change the rule to apportion and match at Store x Division x Attribute x Month instead of Store x Division x Month so that the department changes made are contained with in the attribute and no cross apportioning is there."
- **Engine:**
  - `engine.cap_key` groups by store || division || ATTRIBUTE, and `realign` uses it for the cap and the absorbing.
  - A revised department is absorbed only by the other departments of its own attribute in that store × division. Store × division × month still lands on the original, since it is the sum of its attributes.
  - A plan without an ATTRIBUTE column falls back to Store × Division × Month.
- **Departments alone in their attribute:** in the loaded plan, 539 of 4,621 store × division × attribute buckets hold one planned department (e.g. LW_U_TEES F/S, LADIES PREWINTER). A change to such a department has nothing to absorb it, so it is flagged ("couldn't fully land") and not spread to another attribute.
- **Method 4 (shift):** the target must be in the same division **and attribute**. A section target takes only its departments of that attribute.
- **Checks:** "Store × Division × Attribute × Month = original (the cap)" plus "Store × Division × Month = original".
- **Comparison download:** the cap sheet is now **Store x Div x Attribute x Month**, with ATTRIBUTE and "Within cap" columns.
- **Rules panel, method texts and REPHASE_DEPARTMENT_MONTHS.md (G3a):** updated.
- **Verified:**
  - `test_realign.py` gains an attribute case: A (REGULAR) Sep 10→15 moves only B (REGULAR), C and D (SUMMER) don't move, and a cross-attribute shift is refused.
  - Real plan, in memory, an LW_U_T-TOP re-phase (674k rows, 5.8 s): only REGULAR departments moved. 0 of 43,632 store-division-attribute-months and 0 of 7,272 store-division-months differ, and revised values are kept exactly.

### Sales Plan: AOP-by-attribute window (capped), pick the attributes to work on, a clear "what next" prompt, plan generation ~7x faster
- **Asked (user):**
  - "i need a window for what is the current AOP as per the attributes selected and it will give me a column for every attribute and re-apportion according to the changes made against it. It should always be capped to the division AOP."
  - "what if i want to only work on only some attributes and its departments and the others even if they have ly sales i still want them filtered out somehow"
  - "post growth matrix there should be a prompt redirecting me if i want to select the optional engines or i want to opt out and see the final results, also the population time to load the data should be shortened up. I can select multiple optional engines in department or perhaps an individual too."
- **Attribute Correction → "AOP by attribute" window:**
  - Rows are months plus Season. Columns are Division AOP (cap), one per attribute (₹ L, editable, with "was" and %), Σ attributes, and Σ − cap to 8 dp.
  - Typing an attribute's new AOP re-apportions the other unlocked attributes pro-rata at once (`reapportionToCap`). The month always adds back to the division AOP exactly, so an attribute can't exceed what's left.
  - It edits the same correction % as the grid, so Save & Apply uses the exact, total-keeping apply from Phase 1.
- **"Work on" chips:** pick the attributes to work on. The others are **held out**: they and their departments keep their AOP, even with LY sales, shown in one "Held" column. They are locked for Auto Balance, and greyed and locked in the % grid. The selected attributes share what's left of the cap.
- **Empty page:** when the saved plan has no months (today's, from 23 Sep), the page says so and offers **▶ Generate the department plan**, run by the user.
- **Prompt after Growth Matrix:**
  - **▶ Generate Base Plan & continue** opens "Base plan ready — N stores. What next?".
  - Tick one or more optional engines (they run in order) and **Run n selected →**, or **Only this →** on any one, or **Opt out — see Final Results**.
  - Nothing is pre-ticked (Base Correction used to be).
- **Faster:**
  - LY sales are built once per snapshot and day and shared (they were built twice per run and on every page load), and the month labels are cached (`actuals_manager`).
  - The new-department pass no longer deep-copies the ~350 MB plan.
  - Plan generation went from **~36 s → 5.3 s** (3.4 s warm), with an identical plan: all 1,410,912 department-months match. The only differences are that Sep'27 is now included because September closed on 1 Oct, and the order of the missing-ref store list.
  - Pages that read the plan file (Final Results ×2, Reconciliation, MRP plan, Display Type, Base Correction) keep the last one read in memory (`plan_cache.py`, one slot), instead of 3.5 s per read.

### Sales Plan New Departments: template download + upload (replaces "Sync from Folder")
- **Asked (user):** "I want a template made for this instead of sync from directory".
- **Template** (`GET /api/planning/dept-sales/new-depts/template`), pre-filled with today's list:
  - **New Departments** sheet: DIVISION | NEW DEPT | REF DEPT | NEW DEPT % | REF REDUCTION %.
  - **Departments** sheet: every department with its division and status, to pick a REF DEPT from.
  - **How to fill** sheet.
- **Upload** (`POST /api/planning/dept-sales/new-depts/upload`): every row is checked (`parse_new_dept_template`), then the mapping is saved and the plan regenerated, as the sync did. Any problem refuses the whole file and nothing changes. The checks:
  - REF DEPT must be a department in the plan, in the row's division (DIVISION is optional and taken from REF DEPT when blank).
  - NEW DEPT % ≥ 0, and may be over 100 (bigger than the REF).
  - REF REDUCTION % 0–100 (blank = NEW DEPT %).
  - One row per new department.
  - **NEW DEPT ≠ REF DEPT.**
  - The old folder file layout (NEW MC / REF. MC / month fractions) is still read.
- **Removed:** the Sync from Folder panel, `/new-depts/sync-status`, `/new-depts/sync` (404 now) and the fixed folder path.
- **Found:** 7 of today's 15 entries (KG_HIPSTER SET F/S, KI_AP_HIPSTER SET F/S, KGW_JACKET, KGW_PYJAMA, KB_T-SHIRT F/S, LWW_WINTER TOP, LWW_KURTI SET) name themselves as their own REF DEPT. With the same department on both sides the row adds and removes the same share, so these rows have never changed the plan. The template refuses them until a real reference is given.
- **Checked live:** the template downloads (17 KB, 3 sheets); uploading it back is refused with those 7 rows listed; the saved list is unchanged. Tests: `engines/test_new_dept_template.py`.

### Least apportioned difference, Phase 1: Sales Plan (every split adds back exactly) + Reconciliation page
- **Asked (user):** "embed the matrix to give me the least apportioned difference all time in all models across apps wherever apportioning is present". Chosen: phase by app, Sales Plan first; AOP targets to be kept at full precision in their phase.
- **Rule (`SalesPlan/backend/apportion.py`):** parts are kept at full precision, never rounded before being summed or saved. A split's float remainder goes to its largest part (`split`, `shares_pct`, `plug`), so totals equal the sum of their parts at 8 decimals (`SHOWN = 5e-9`). Rounding is display only.
- **Fixed, engine by engine:**
  - `dept_sales_engine`:
    - SSG P1 / P2 / TY were rounded to 4 dp before summing. Non-SSG departments are now split exactly from the division total; P2 = TY − P1.
    - **Bug:** the new-department adjustment changed TY but not P1 / P2, so TY ≠ P1 + P2 by up to **3.06 L** (BHR KIDS KB_BABA SUIT DNM H/S). It also left the division total stale. P1 / P2 now move with TY, and the division total and contribution % are re-derived.
    - Summary and exports are at full precision / 8 dp.
  - `department_plan`: equal default shares add to exactly 100 (was round(100/n, 4) = 99.9999). `/calculate` splits the target exactly by the shares and reports `allocated` / `difference` (was 2 dp per department).
  - `attribute_correction_engine`: the corrected attributes share out exactly what they had, by their new % (which are shares of the attributed departments), so the store × division × month total never moves. Before, the % were applied to the whole division, values were rounded to 4 dp, and the drifted sum overwrote the total. Aggregates are no longer rounded on every addition.
  - `base_correction_engine`: the gap fill uses exact halves. **Bug:** the NSO re-apportionment rounded to 4 dp, never updated P1 / P2, and a ref store with no plan wiped the NSO's division total to 0. It now splits exactly, moves P1 / P2 with TY, and keeps the plan when there is nothing to split by.
  - `mrp_plan_engine`: bands are split exactly (were 2 dp) and add back even when the shares total 99.6 / 100.4; reports `allocated_ty` / `difference`; the CSV is at 8 dp. **Bug:** it looked for the plan in `engines/`, so it never found it and every band was 0. It now reads backend/, like every other engine.
  - `display_type_engine`: **bug:** it looped over the division's keys instead of its months, so it made **0 rows**. It now makes rows; on the live plan with 60/40 test shares, 967,032 rows. MRP and Table / Non-Table splits are exact. It reads the corrected plan first like the other engines, its validate uses the 8-dp line, and its messages name the missing MRP shares.
  - `mrp_reapportionment_engine`: the exact split (was 6 dp + plug), the Excel at 8 dp (was re-rounded to 2 after the plug), validation at 8 dp (was 0.01), and equal default shares exact. Test tightened: 190 store × dept totals exact on real data.
  - `pww_deviation_engine` / `sor_deviation_engine`: re-apportioned shares add to exactly 100 (were 4 / 6 dp, no plug).
  - `division_plan` growth structure: months add back exactly to each division base (were 2 dp each).
  - `final_results_engine`: values at full precision (the page formats them).
- **Reconciliation page** (Sales Plan → Reconciliation; `engines/reconciliation.py`, `GET /api/planning/reconciliation`, `/export` xlsx with 0.00000000 format). On the plan the pages use, every store × division × month: division total = Σ departments, P1 / P2 likewise, TY = P1 + P2, Σ contribution % = 100; and department = Σ MRP bands. What the MRP file has no shares for is listed apart as "not covered" (not a rounding difference). It shows which plan file it checked and when that file was generated.
- **Before → after on the live plan** (426 stores, Mar–Aug'27, 1,410,912 department-months): division total vs departments 847 → **0** off (largest 0.0015 L); TY = P1 + P2 43,532 → **0** (3.06 L); contribution % 4,284 → **0**. The plan total moves 84,183.8482 → **84,183.7397 L** (now = Σ departments; before, total and departments disagreed). Not covered by MRP shares: **34,043 L** (Jul–Aug'27, plus 348 of 518 departments not in the MRP file).
- **To act on:** the saved `final_dept_plan.json` is from 23 Sep and has no months. Generate it again (Department Plan → Growth Matrix → ▶ Generate Base Plan) so the saved plan uses the exact maths. Next phases: NSO, AOP publish (full precision), Calendar download, Re-Aligner export.

## 2026-09-30

### Sales Plan Re-Aligner comparison: 8 decimals (0.00000000)
- **Asked (user):** "can you zero in difference to 0.00000000 ? instead of the full blown 0.0001 ?" (on the comparison download).
- **Before:** every figure was rounded to 4 decimals, so a real difference below 0.00005 showed as 0.0000 and the smallest as 0.0001 (in the user's file, 38,596 Changed Rows read exactly 0.0001).
- **Now:** every number in the comparison (xlsx and CSV) is rounded to 8 decimals, float noise is written as a clean 0 (never -0), and the xlsx number format is `0.00000000` (`engine._r8`, `write_xlsx(num_format=)`). The "changed", "moved", "Within cap" and cap check use the same 8-decimal line (`engine.SHOWN = 5e-9`), so any difference the file shows is counted.
- **Checked:** LW_U_T-TOP Store x Division x Month has 7,272 rows, all exactly 0; the smallest real difference is 0.00000004 (Store x Dept x Month) and 0.00000001 (Changed Rows); the cap still passes at 0 of 7,272. The file grew from 11.9 to 15.1 MB (about 40 s to build).

### Sales Plan Re-Aligner: "stay as they are" option removed
- **Asked (user):** "remove the stay as they are option".
- **Removed everywhere:** the Run card radio buttons and `setAbsorb`; `POST /api/option` (now 404) and `state.absorb`; the `absorb` parameter and its branch in `engine.realign` / `engine.verify`, with their "other departments untouched" / "season total" checks; and the Rules panel and page text that described it. Every run now keeps each Store × Division × Month on the original file (the cap).
- **Tests:** the absorb=False cases are replaced by a capped pure re-phase (D 40/40 → 20/60, kept exactly, S1 months stay 70 / 80) and a capped read-back of the Re-phase file (stores with another department sit exactly on the cap; single-department stores are flagged). `test_realign.py` and `test_workspaces.py` pass.
- **Checked live** (Admin workspace, LW_U_T-TOP Re-phase & run after the 8070 restart): the cap passes at 0 of 7,272, same counts as before (104 moved to fit), no option on the page.

### Sales Plan Re-Aligner: Store × Division × Month is a hard cap; original-vs-new comparison download
- **Asked (user):** "cap the target for the month x store x division should be matching as per the original file imported. validate the same. Also, make sure that there is a comparitive drawn between 2 iterations - original plan v new revised plan and is downloadable to see where the difference is there." (after checking a Method 2 output).
- **Found:** Re-phase & run ran with "other departments stay as they are", so month totals followed the re-phased department. Replaying Planning01's LW_U_T-TOP run: **750 of 7,272** store × division × months were off the original (up to 2.39 L), with season totals kept. Even with "absorb", 8 were off: BRN and DLT LADIES, where T-TOP's re-phase alone was bigger than the whole division's month, and the old overflow rule lowered other months' targets.
- **Now (`engine.realign`):**
  - Re-phase & run uses **absorb**.
  - A revised department that exceeds a month's cap is **cut to the cap**, and the excess moves into the same department's other live months that have room, where the other departments shrink by the same amount. So every Store × Division × Month, the season, the grand total and the revised department's own season total all match.
  - Only excess with no room anywhere stays over its month, and it is flagged.
  - Such cells are labelled "kept, moved to fit the cap".
- **Checks (`engine.verify`):** "Store × Division × Month = original (the cap)" is now pass / fail (it was a warning). "Revised values kept exactly" reads **warn** when values only moved between months to fit the cap and every revised store-department kept its season total.
- **Comparison download** ("Comparison vs original", xlsx; `engine.compare_levels`): **Summary**, **Store x Division x Month** (every one: Original, New plan, Difference, %, Locked month, **Within cap**), **Store x Dept x Month** (every department-month that moved), **Changed Rows** (every MRP × display cell, with why). The CSV is still the changed cells.
- **Validated:**
  - LW_U_T-TOP replayed on Planning01's plan and then run live in the Admin workspace: 0 of 7,272 off the cap, grand total 83,848.99 → 83,848.99, locked months and display-type cont % unchanged, 104 cells moved to fit the cap. Comparison 11.9 MB, all 7,272 "Within cap = Yes".
  - ML_JEANS, MW_JACKET, MW_WINTER T-SHIRT, MW_PULLOVER and LWW_CARDIGAN: all 0 of 7,272, no failed check.
  - `test_realign.py` updated: the overflow case S2 is now cut to its cap with A's season kept; the lock-swap case is capped at 70.
- **Also:** the Rules panel, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md` (G3a), and the Run card wording. The manual "stay as they are" option remains, now labelled "store × division × month totals will NOT match the original". Restarting 8070 cleared in-memory results.

### Sign-in fix: capitals in usernames and spaces around passwords
- **Bug (user):** "except for admin others cannot login through their email id and it is not accepting temp password set by admin".
- **Found:**
  - The email lookup worked for all 4 accounts. But usernames matched capitals exactly, and the accounts had been renamed Planning01 / Planning02 / SK-Planning, so anyone typing "planning01" got "Invalid credentials" even with the right temporary password.
  - A temporary password copied from the Users page's green message can pick up a trailing space, and the password check counted that space.
- **Fix (`auth/routes.py`):**
  - `find_login_user`: the username exactly, else ignoring capitals, else the email, ignoring capitals. Each only counts when exactly one active account matches.
  - `password_ok`: accepts the password as typed, or with the spaces at either end removed. Used at sign-in and at change-password.
  - Admin-set passwords (Add a person, Set password) are trimmed before saving, and must still be at least 8 characters.
- **Checked live through Landing** (a deliberately wrong password, timed): every account is found by its email, by its email in capitals, by its lowercase username, and by its username with a trailing space; an unknown name is not. Test: `tests/test_admin_guard.py::test_password_ok_ignores_spaces_at_the_ends`.

### Sales Plan Division Plan: shown in ₹ Cr
- **Asked (user):** "Can we have this in Cr ?" (the LY Base / Plan MAMJ cards).
- The cards now read ₹ 388.83 Cr and ₹ 431.85 Cr (1 Cr = 100 L, 2 decimals); hovering shows the exact lakhs.
- **Then (user):** "yes, show the tables in Cr too". The Division Plan table, the comparison card, the chart cards, the chart axes and the tooltips are now in ₹ Cr, and hovering a cell still shows the exact lakhs. The CSV export stays in lakhs, so its figures stay exact.

### Sales Plan Division Plan: "Compare with" another AOP version
- **Asked (user):** "where is the version selector here ?" then "yes, add the comparison dropdown". The old selector was removed on 29 Sep (`de37c48`) when the page was set to follow the BIS plan.
- **What:** a **Compare with** dropdown lists every other saved AOP version (its latest publish). Picking one adds a card showing that version's Mar'27–Jun'27 plan per division and month, the difference from the BIS plan (₹ L and %), and its growth on this page's LY base. It is view only and changes nothing; the plan still comes from BIS.
- **Server:** `division_plan.py` `_versions()` (added to `/config` as `versions`), `GET /api/planning/division-plan/compare/{publish_id}`, which reuses `_plan_rows`. The LY base is the page's own: Version 1's publish (32) came before publishes stored their base.
- **Checked live:** Version 1 (publish 32) vs the BIS plan (Version 2, publish 112) is ₹42,089.98 L vs ₹43,184.66 L = −1,094.68 L (−2.5%); KIDS −330.23, LADIES −334.53, MENS −429.92; Mar'27 is identical. Growth on the LY base: +8.2% vs +11.1%.

### Sign in with your username or your email
- **Asked (user):** "can we enable an option for either using an email sign in or the username sign in, like you can sign in either with your email or username ?".
- **Login** (`auth/routes.py login`): tries the username first. If there's no match and the entry contains "@", it tries the email on file, ignoring capitals, but only when exactly one active account has that email. The login page label now says "Username or email".
- **One email per person:** adding a person, changing an email on the Users page, and setting your own email at change-password now refuse an email another account already has (`email_taken`, 409). Checked on 30 Sep: 4 accounts, 4 emails, none shared.
- **Checked live:** the admin's email in capitals with a wrong password reached the password check (0.39 s, bcrypt ran); an unknown email was refused at once (0.005 s). No real password was used.

### AOP Re-Aligner is now "Sales Plan Re-Aligner"
- **Asked (user):** "Rename AOP Re-Aligner to Sales Plan Re-Aligner everywhere".
- **Renamed:** the Landing card and launcher name, the app's page title and heading, the Rules panel, code headers and the re-phase rule document.
- **Kept, so nothing breaks:** the folder `AOP Realigner/` (the launcher, sync jobs and docs point at it) and the web address `/realigner/`, so bookmarks still work. Older entries below keep the name they had at the time.

### Users & access: admins can "Sign in as" someone
- **Asked (user):** "yes, build the sign in as option". Showing people's permanent passwords isn't possible: only a bcrypt hash is stored, and it can't be reversed. Storing passwords readably was declined for security.
- **What:** a **Sign in as** link next to Rename, for active non-admin accounts other than yourself. It opens the suite as that person without their password. `POST /api/auth/admin/sign-in-as/{id}` (admin only) swaps the session to that person with `signed_in_by` {admin id, current name} and `must_change_password` off, so the admin isn't forced to choose the person's password.
- **Banner:** while signed in as someone else, every page shows "Signed in as <name>" with a **Back to admin** button. It is in `static/suite-theme.js`, which every app loads. `POST /api/auth/stop-sign-in-as` re-checks that the admin is still an active admin (otherwise it signs out) and restores their session.
- **While signed in as them:** you have their role and their action rights, you work in their Re-Aligner workspace, and the admin pages are closed. Anything done is recorded as that person.
- **Log:** `backend/data/sign_in_as.log` (JSON lines {at, event start|stop, admin, as}, gitignored). The newest 50 are shown in a "Sign in as - history" card (`GET /api/auth/admin/sign-in-as-log`).
- **Checks:** no signing in as yourself, as another admin, or as a switched-off account (`sign_in_as_refusal`, tests in `tests/test_admin_guard.py`). Checked live: admin → Planning02 (banner shown, Users hidden, admin API 403, Planning02's rights) → Back to admin, with both events logged.

### Switched-off actions are hidden in Calendar and AOP; Landing gets Sign out / switch user
- **Asked (user):** "yes, hide the buttons in calendar and aop too" and "also add a log off or change user button in the landing page to switch profiles".
- **Calendar:** Run Reindex is hidden for a person whose `calendar_reindex` is switched off. `lib/api.js getRights`, and `App.jsx` passes `rights` to the tabs (`CalendarisedSalesTab`).
- **AOP Forecaster:** Sync into database (`DbSyncPanel`) and Promote to Planning / Unlock (`ResultsDashboard`) are hidden when `data_sync` / `aop_publish` is switched off. They use a new `lib/rights.js useCan(right)`, which asks `/api/auth/rights` once per page load. Standalone :8000, or no answer, means show the button; Landing still refuses the action.
- **Landing:** a "<name> · Sign out" button next to Users. It calls `POST /api/auth/logout`, which clears the session and the remember-me cookie, then goes to `/login?next=/` so someone else can sign in. On phones the top bar drops the brand name, username and "Theme" text, so it fits (it had already been 47 px too wide at 412 px).
- **Build:** both frontends rebuilt. `dist/` is not committed; 8010 serves the local build.

### Users & access: switch off important actions per person
- **Asked (user):** "give me a revoke access panel for admin for different rights like server action button and other important features".
- **Panel:** a new "Access to important actions" card on `/auth/users`, with one tick box per action for each person. Unticking switches the action off at once. Everyone has every action until an admin unticks it, admins always keep all of them, and switched-off accounts have none.
- **The six actions:** start / stop all servers (Master Switch); sync the data lake (Landing Sync now, AOP Sync into database); promote AOP to Planning or unlock it; Calendar Run Reindex; Re-Aligner Run and Re-phase & run; change the suite colour theme.
- **Enforced in Landing** (`landing_server.py` `GUARDED`), the one door to every app. Before a guarded request, Landing asks 8010 `GET /api/auth/rights`, which reads admin and active status fresh from the database, not the session, and returns 403 "An admin has switched off your access to: …" when the right is gone. If the check can't be made, the action is refused. Landing also greys out the Master Switch and Sync now for people without them.
- **Storage:** `RS Planning Platform/backend/data/user_rights.json`, shaped {user id: [revoked rights]}. It is local and git-ignored, and no database change was needed. API: `GET /api/auth/admin/rights`, `PUT /api/auth/admin/rights/{id}` {revoked}.
- **Left out on purpose:** the BIS sales / sell-through / history syncs. BIS calls them itself when it loads, so blocking them would break BIS for that person.
- **Tests:** `tests/test_rights.py`, `Landing/test_rights_guard.py`. Checked live: switching one action off for Planning01 applied at once (5 of 6); the admin's guarded request passed Landing; it was given back.

### Users & access: rename a username
- **Asked (user):** "i need a username rename option here".
- **What:** a **Rename** link under each name in the USER column of `/auth/users` (kept there so it stays visible when the table scrolls sideways on a narrow screen) changes the name the person signs in with. The server refuses a blank name, one over 64 characters, or one another account already has (ignoring case, so "Admin" and "admin" can't both exist). Renaming yourself updates your own session at once; anyone else sees the new name the next time they sign in.
- **Re-Aligner:** workspaces are now kept by account id, not username, so a renamed person keeps their plan, locks, overrides and history. Folders named by username before this change move to the id folder on that person's next visit.
- **Files:** `RS Planning Platform/backend/auth/routes.py` (`username_refusal`, PATCH accepts `username`), `static/admin-users.html`, `tests/test_admin_guard.py`; `AOP Realigner/server.py` (`who` returns (id, username), `Workspace(key, name)`), `test_workspaces.py`.

### AOP Re-Aligner: every signed-in user has their own copy
- **Asked (user):** "make it so each user gets their own copy".
- **How it works:** each request is tied to the RS Planning user signed in through Landing. The Re-Aligner asks the platform (`/api/auth/me`) who the forwarded session cookie belongs to, and caches the answer for a minute.
- **What each user gets:** their own **workspace** in `.cache/users/<name>/`, holding:
  - the plan, month locks and store overrides;
  - the revised file, result and exports;
  - running jobs and activity history.
- **Isolation:** one user's loads, locks, Re-phase & run and exports never touch another's. Jobs run with their own user's locks, and each user can run their own job at the same time as others.
- **Starting point:** a user's first visit starts from a **copy of the setup at that time**: the loaded plan, locks and overrides. After that it's theirs.
- **Local use:** direct use of `:8070` on this PC, with no sign-in, gets a separate "local" workspace.
- **Memory:** a workspace untouched for 2 hours frees its plan from memory, and it reloads on the next visit. An unexported result is dropped then. The Re-Aligner's top bar shows "Your workspace: <name>".
- **No Landing change or restart:** Landing already forwards the session cookie.
- **Checked:**
  - Your own browser tab was put in the `admin` workspace automatically, seeded with the 674,478-row plan, 4 locked months and 303 overrides.
  - `test_workspaces.py`: two users' locks and settings stay apart, job threads see their own locks, and idle unload and reload work.
  - `test_realign.py` still passes.
- Files: `AOP Realigner/server.py` (Workspace, `who()`, per-user `state` / `jobs` / `history`), `engine.py` (`locked()` per thread, `engine.LOCKED` still the fallback), `index.html`, `test_workspaces.py`.

### Users & access admin page; password reset accepts an email
- **Asked (user):** "email not sent - email should be there" and "give me an admin layout for setting user control up".
- **Why no reset email came:**
  - The value typed (an email) isn't a username, and the form only looked up usernames.
  - None of the 3 accounts (admin, planning01, planning02) has an email on file.
  - The server has no SMTP (email-sending) settings, so it can't send any email yet.
- **Fixes:**
  - **Forgot password** now also accepts the email on file. It still answers the same way whether or not the account exists.
  - **New Users & access page** at `/auth/users`, reached through a Users button on Landing that only admins see. On it an admin can:
    - see every account;
    - change email, role (planner / buyer / reviewer / approver), admin rights, and sign-in on/off, each saved immediately;
    - **set a temporary password**, generated or typed, which forces the person to pick their own at next sign-in;
    - add a person.
  - It also shows how many admins there are and whether reset email is set up, and explains the roles.
  - **Lock-out guards** (server side): an admin can't remove their own admin rights or switch themselves off, and the last active admin can't be removed.
  - **Email status:** an admin-only `GET /api/auth/admin/email-status` reports whether email is set up, never the settings themselves.
- **Checked:**
  - The admin endpoints return 401 without a sign-in, and the page sends anonymous visitors to sign-in.
  - Guard tests pass (`tests/test_admin_guard.py`).
  - A cookie forged with the public development key is still rejected after the 8010 restart.
- **Still needed for email resets:** SMTP settings on the server (SMTP_HOST / SMTP_USER / SMTP_PASSWORD / SMTP_FROM), and each person's email on the page. Until then, use **Set password**.
- Files: `RS Planning Platform/backend/auth/routes.py`, `app.py`, `static/admin-users.html`, `tests/test_admin_guard.py`; `Landing/index.html`.

### Re-phase: a comparable store needs both the SSG tag and a full last year
- **Asked (user):** "yes, require both the tag and a full last year".
- **Rule:** a store may lend its month shape only if it sold in the department's division in **every** re-phased month last year **and**, when the plan has an SSG TAG column, it is tagged SSG. Tagged stores left out are named in the summary.
- **Live plan:** 124 SSG-tagged stores become 121 comparable. The 3 left out are **BRN, SAH and SBW**: they're tagged SSG but have no last-year sales in the data at all, so they never had a shape to lend.
- **Results unchanged:** every department and all six test set-ups give the same numbers. LW_U_T-TOP still reproduces the workbook (304.07 / 316.26 / 96.73 / 55.71).
- Tests: a tagged store with a part-year history is left out.
- Files: `AOP Realigner/importer.py`, `rules.js`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md` (G6).

### Re-Aligner Re-phase rebuilt as a generic planning rule, and tested across plan set-ups
- **Asked (user):** "i want it to be a generic planning tool and not a biased working ... made for one time purpose ... reverify and rebuild ... the logic base should be clear, try to test on different models".
- **Rebuilt:** these rules are in the rule-set doc §0 (G1–G10), the Rules page and the Summary shown with every run.
  - **Comparable stores:** with an SSG TAG column, a store counts as comparable if its tag starts with "SSG" (it used to be an exact match on "SSG"/"SSG-ANG"). Without that column, it's decided from the data: the store must have sold in the division in every window month last year. Before this, every store could lend its shape, even one that opened mid-year.
  - **Last-year months:** a month missing from the data, or only till date, is refused rather than used silently.
  - **Unlocked half-months:** reported instead of skipped silently.
  - **Summary:** every run comes with a Summary sheet, and its lines also show in step 2.
  - **Wording:** SSG-specific labels are now "comparable stores", and the workbook examples are gone from the help text.
- **A bias the tests caught:** a fixed mix typed for LW_U_T-TOP in JHM was also applied to ML_JEANS. A fixed mix is now keyed by store × department: an overrides row needs a DEPARTMENT, and one without it is refused. REF OLD stays a store-wide attribute. The workbook's overrides file was rebuilt with JHM's mix set for LW_U_T-TOP and re-uploaded.
- **Tested:**
  - **Every department in the live plan:** 176 departments; 175 run and 1 is correctly refused because it has no last year. All invariants hold: shares 100% (worst 4e-16), store totals kept, non-trading months 0, only comparable stores lend a shape.
  - **Independent cross-check:** a different model wrote its own implementation from the rules only, without the code. On 6 set-ups (a proxy shape, KIDS, MENS, a 3-month window, a plan without SSG TAG, a plan without SSG TAG/REF/CLUSTER) it matched **5,362/5,362 store-months** (max 5e-15 L).
  - **Full Method 2 path:** all six end to end with every check ok, and the other departments moved 0.
  - **Workbook regression:** still exact (303/303 stores).
  - **Unit tests added:** no-tag comparable rule, partial and missing month refusal, half-month note, and mix per department.
- Files: `AOP Realigner/importer.py`, `server.py` (`ly_partial`, notes into step 2 + Summary sheet), `index.html`, `rules.js`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md` (§0).

### Re-Aligner: no "Replace this file" box after Re-phase & run
- **Asked (user):** "shouldn't this replace the file option be removed … now that the plan is remade accordingly".
- **Change:** when the step-2 file was built by Re-phase & run, the big drop box is replaced by one line: "Built by Re-phase & run – nothing to upload. To use your own edits, download Re-phase file, change it and upload it here", where "upload it here" is a small link.
- **Unchanged:**
  - An uploaded file still shows the drop box.
  - The edit-and-upload route stays: download the Re-phase file, change it (e.g. a hand-set store) and upload.
  - The upload route for other departments' hand-made revised plans stays.
- **How:** `server.job_rephase` marks the revised info `generated`, and `index.html renderRev` reads it.

### Re-Aligner Rules page: Method 2 written out in full
- **Asked (user):** "have you made sure that the rules are set for method 2". The Rules page was checked line by line against `importer.template_rephase` and `engine.verify`.
- **What was wrong:**
  - "What is kept" said the other departments always absorb, but Method 2 can keep them as they are.
  - "Checks" didn't describe the stay-as-they-are checks.
  - The re-phase details the code applies were missing:
    - The window is only the unlocked full months; P1/P2 halves have no last-year month.
    - Last year comes from the data-lake sales, a year earlier.
    - Only SSG stores lend a shape, and negative last-year values count as 0.
    - A month is "not trading" when the store has no plan in that division.
    - REF / SSG TAG / CLUSTER are read from the plan's own columns.
    - A fixed mix is rescaled to 100%.
    - Each re-phase comes with a "How it was built" sheet.
- **Now:**
  - "Method 2 – existing department changes" covers the file format and the absorb / stay-as-they-are option.
  - A new "Method 2 – Re-phase from last year" section covers Re-phase & run, the window, the shape cascade, non-trading months, store overrides and the audit sheet.
  - "Checks on every run" now includes the stay-as-they-are checks.
- File: `AOP Realigner/rules.js`.

### Re-Aligner Re-phase: store overrides make it match the hand-built plan exactly
- **Asked (user):** "Check why is there a slight difference between mine and your iteration and fine tune it". The app gave 304.10 / 316.09 / 96.28 / 56.30; the user's pivot is 304.07 / 316.26 / 96.73 / 55.71.
- **Why:** 286 of 303 stores already matched exactly. The gap came from two causes only:
  - **16 stores** take REF OLD's shape in the workbook. REF OLD isn't in the plan, the DB store master or Store Master.xlsx (1/16 in each), so the app used the cluster's SSG stores.
  - **JHM** is hand-typed, with Oct = 0 although it trades in Oct.
- **Fix, "Store overrides":** in Method 2 step 2, upload once (kept until cleared) a sheet with STORE NAME, REF OLD and optionally `<Month> %`.
  - REF OLD from the sheet is used before the cluster fallback.
  - A month % mix replaces that store's last-year shape, as given.
  - **Overrides template** lists the re-phase's stores, with the ones that need REF OLD first.
- **Result, in the app on the live plan:** with the workbook's REF OLD and JHM's typed mix, **Re-phase & run gives 304.07 / 316.26 / 96.73 / 55.71**, all 303 stores exact (max 2e-8 L), and all checks ok.
- Files: `AOP Realigner/importer.py` (`read_rephase_overrides`, `template_rephase_overrides`, `template_rephase(..., overrides)`), `server.py`, `index.html`, `rules.js`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md`.

### AOP Re-Aligner: "Re-phase & run" takes a department to the final plan in one click
- **Asked (user):** "i just select the department to be executed and you do it on the second step by yourself and take it to the final plan".
- **How it works:** in Method 2's step 2, pick the department (and optionally the LY shape), then click **Re-phase & run**. The server does, as one job, what used to be three steps:
  1. Builds the re-phase from last year.
  2. Loads it as the step-2 revised plan, with the usual checks.
  3. Sets "other departments: stay as they are" and runs the realignment. The result, checks and downloads appear as after a normal run.
- **Re-phase file** still downloads the same file, for checking or editing it first.
- **Tested on the live plan** (LW_U_T-TOP with the LW_U_T-TOP F/S shape): 25 s, all checks passed.
  - LADIES moves only by LW_U_T-TOP's own change: Sep 550.21 → 304.10, Oct 222.56 → 316.09, Nov 0 → 96.28, Dec 0 → 56.30 L; 229 stores.
  - KIDS, MENS and Jan/Feb are unchanged.
- Files: `AOP Realigner/server.py` (`job_rephase`, `POST /api/rephase?dept=&mix=`), `index.html`, `rules.js`.

### Nightly sync now rebuilds the Calendar's day-wise sales too
- **Asked (user):** "yes, add day-wise to the nightly sync".
- **Before:** only the month-wise calendarised sales were rebuilt nightly. The day-wise ones changed only when someone ran Run Reindex → Day-wise by hand, and still sat on 26 Sep's data, which stopped at **27 Aug 2026**.
- **New job `calendar_reindex_dw`** (`sync/calendar_reindex_dw_sync.py`) runs in `sync/run_all.py`, after `calendar_reindex` and `calendar_check`. So it's part of the 05:00 task and of Sync now / Sync into database.
  - It uses the same calendar, stores and months as the month-wise job, and the Calendar's own day-wise output (store level, default metric).
  - It has its own sync-status row, so a day-wise failure never marks the month-wise rebuild failed. The shared calendar loading moved into `calendar_reindex_sync.calendar_inputs()`.
- **Bug fixed on the way (month cache):** a closed month is cached for good. August had been cached on 26 Sep from a day-wise file that ended on 27 Aug, because "closed" comes from the month-wise data. Every later day-wise run, nightly included, would have kept serving that 27-day August.
  - Day-wise months are now cached, or reused, only when their data reaches the month's last day (`scans._covers_month_end`). The month-wise rule is unchanged.
  - Tests: `RS Planning Platform/backend/tests/test_reindex_dw_cache.py` (3).

### Calendar: "Last synced" shows when the data was actually pulled
- **Bug (user, screenshot):** the Link Sales Data Source table showed Month-wise last synced "25 Sept, 10:40 am", although the data had been re-synced since (29 Sep, 13:09).
- **Cause:** the column showed when the list of linked months was last saved. Month-wise already had every month linked, so the daily syncs that rebuild its data never moved it.
- **Fix:** `GET /api/calendar/salesdata-link-selection/{mw|dw}` now also returns `dataSyncedAt`. That's the source's last snapshot rebuild, plus the last day-weights sync for day-wise. The column shows the later of the two.
- Month-wise now reads 29 Sep, 01:09 pm; day-wise is unchanged (29 Sep, 01:58 pm).
- Files: `RS Planning Platform/backend/calendar_engine/router.py`, `Calendar Engine/frontend/src/components/CalendarisedSalesTab/LinkStatusPanel.jsx` (+ rebuilt `dist/`).

### AOP Re-Aligner: "Re-phase from LY" builds the Method 2 file
- **Asked (user):** "yes, build the re-phase from LY generator".
- **Where:** Method 2, step 2. Pick the department and optionally the LY-shape department (any department with last-year sales, e.g. LW_U_T-TOP F/S), then click **Re-phase from LY**.
- **What it builds:** a Method 2 file where each store keeps its total for the unlocked months, re-split by last year's same months.
  - **Shape source:** the first SSG store of (the store itself, REF, REF OLD), else the cluster's SSG stores, else the store's planned phasing.
  - **Non-trading months** get 0 and the rest is rescaled.
  - **Audit sheet:** "How it was built" shows each store's source, LY, mix % and old/new values.
  - **Then:** upload it and run with "other departments: stay as they are".
- **New rule found in the workbook:** only SSG stores lend a shape. The workbook's LY pivot is filtered to SSG, so a non-SSG REF falls through to REF OLD.
- **Tested on `LW_U_T-TOP Working.xlsx`:**
  - With the workbook's LY and REF OLD: 286/286 formula stores exact, 16/17 exceptions (JHM is manual); 7,865/7,878 final rows exact, all 13 misses are JHM.
  - With live `sales.json` and no REF OLD column: 271/286 exact. The 15 REF-OLD stores use the cluster fallback, within 0.71 L.
  - Live plan: 772.77 L kept exactly.
  - Adding a REF OLD column to the plan makes every store exact.
- **Also:** Method 2's fallback mix no longer prints numpy's "mean of empty slice" warning (same maths). The Rules page has been updated.
- Files: `AOP Realigner/importer.py` (`template_rephase`), `server.py` (template route, `ly_departments` in state), `index.html`, `rules.js`, `engine.py`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md` (R4, §8).

## 2026-09-29

### AOP Re-Aligner Method 2: tested against the re-phase rule set, and improved
- **Asked (user):** "compare it with the method 2 and improve the logic base through intense training and checking." The user chose "Test, then improve Method 2".
- **Test:** the new LW_U_T-TOP store months from `LW_U_T-TOP Working.xlsx` were fed to Method 2 against the file's 8th Aug LADIES plan (220,584 rows).
- **Fixes and additions:**
  - **Fallback mix:** a month the department had no plan in (Nov/Dec) now uses the average over the *revised* months that had one. Locked Jan/Feb no longer count. It was 2,896 row-months off by up to 0.075 L; now 0.
  - **New Run-card option "Other departments: stay as they are":** only the revised departments move, which suits a month re-phase. The default ("absorb") is unchanged. In this mode the checks confirm the other departments are untouched and the revised departments kept their season total; the store × division months show as info.
  - **Warning fix:** the "locked month ignored" warning now fires only for locked months the revised file contains. It had fired 6,864 times falsely.
- **Result:** with "stay as they are", all 7,878 LW_U_T-TOP rows match the workbook exactly in every month, the other 51 LADIES departments are untouched, and all checks are ok. Rule-set doc R8 was corrected (zeros counted, window months only), and §7 was added.
- Files: `AOP Realigner/engine.py`, `server.py` (`/api/option?absorb=`), `index.html`, `test_realign.py`, `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md`.

### Rule set: re-phase a department's plan across months (from LW_U_T-TOP Working.xlsx)
- **Asked (user):** "analyse this file thoroughly and build a generic rule set." The 554 MB workbook was read by streaming its XML, without opening it in Excel or loading whole sheets. Every step was checked against its saved values.
- **Written up:** `docs/business-rules/REPHASE_DEPARTMENT_MONTHS.md`. The method:
  - Keep each store's window total (Sep–Dec) for one department.
  - Re-split it by a store-level LY month mix: own mix for SSG / SSG-ANG stores, else REF → REF OLD → 0. The mix may come from a proxy department (here LW_U_T-TOP F/S).
  - Drop non-trading months and rescale the rest.
  - Split down to MRP × display by the old plan's month mix (the average of the planned months for months that had none, renormalised).
  - Re-price qty from the old ASP. Jan/Feb and every other department stay untouched.
  - The doc also lists the checks each run must pass.
- **Verified in the file:**
  - 303 stores; the window total is kept exactly (772.77 L); every mix is 100%.
  - MRP × display rows equal the store months exactly; Jan/Feb and the other departments are unchanged.
  - 16 of the 17 hand-typed "Exception" rows follow the non-trading-month rule exactly.
- **Open points:**
  - JHM's typed mix doesn't follow the rule.
  - F/S is used as the curve but has no plan of its own.
  - The workbook's final value + qty (Post) step is unfinished.
- No app code changed.

### BIS: the department filter search picks what you click
- **Bug (user):** "filter search not working properly, I cannot single out my selection." With no filter set, typing a search showed the matches ticked, and clicking one **hid** it (search "dupatta" → click → 235 other departments shown, dupatta gone).
- **Fix (Excel-style):** while searching with nothing picked yet, the matches start unticked. Clicking one **shows only that department**, and more clicks add or remove others. "(Select All Search Results)" shows only the matches. Without a search, unticking still hides just that one.
- **Check (sandbox):** "dupatta" → click → only L_EW_DUPATTA · then "kurti set" → click → DUPATTA + KURTI SET · Select All → all 198 · "kurti" + Select All Search Results → the 5 kurti departments · no search, untick DUPATTA → only it hidden.

### BIS sends inactive departments to Sales Plan as plan 0
- **Problem (from the post-sync check):** Sales Plan's LADIES TY ran +0.05 … +0.12 L a month over AOP. L_EW_BLOUSE is inactive in BIS, so BIS left it out of the push, and its share went to the other LADIES departments. But Sales Plan still planned it: a department with no BIS row falls back to the saved matrix value (or index 100), and Sales Plan's Department Master only follows BIS when someone presses its "Sync from Buyer's Input" button. So the share was counted twice.
- **Fix (user's choice: "BIS sends it as plan 0"):** BIS now pushes every inactive department with **−100% for each recorded month**. Sales Plan turns that into growth index 0, so TY = 0, with no change to the Sales Plan engine. Sales Plan's `sync-from-buyer` treats a department BIS sends only at −100% as **inactive**, so it stays greyed there instead of flipping to "active".
- **Check (BIS sandbox, push intercepted):** L_EW_BLOUSE is sent as −100% for Mar–Jun. 39 inactive departments = 156 rows at −100%, 944 rows in all. Sales Plan's live figures update at the next **Save** in BIS.

### Sales sync run on the new files, and the data checked through every app
- **Bug fixed on the way (BIS):** the sales job reused whatever local copy already existed, so it would have kept reading the old 5 Sep copy after the source moved to `master.parquet`. It also read a half-written copy while the history job was re-copying it ("File too short"). Both jobs now share one `_local_copy()`: refreshed only when the network file changes, written to a temp file and swapped in under a lock.
- **Sync:** the full data-lake sync ran (`run_all`: site master, store master, day shift, store actuals, day weights — cluster-days now to **28 Sep 2026**, calendar reindex, nightly accuracy check, festival dates, Listing / Delisting), all ok. BIS sales, history and sell-through re-synced from `master.parquet` / the complete 2 Sep sell-through.
- **What changed in the data:** Mar–Jun 2026 (the plan LY) and every month Sep 2025–Jul 2026 are **identical** to the 5 Sep file for KIDS / LADIES / MENS. Aug 2026 has tiny restatements (−0.01 … −0.07 L). Sep 2026 grows from ~5 to 28 days. So the AOP base, BIS LY and the plans are unchanged.
- **Every app ties to the raw file** (0.01 L tolerance, planted 0.02 L caught each time): Calendar department snapshot 398,433 store × dept × month cells (Mar–Sep 2026, ₹90,034.01 L) exact · Listing `sales.json` 170,394 cells exact · BIS department LY 743 cells (148 plan stores, ₹38,885.41 L) max 0.0001 L · Sales Plan actual LY 330,733 cells exact · MRP Re-apportionment 212,813 cells, 0.0 L.
- **Chain deep check 17 / 19**, the same two known misses (AOP V2 base vs the current calendar). BIS → Sales Plan = AOP target, 0.0 L. **Open item:** Sales Plan's LADIES TY is now +0.05…+0.12 L over target because L_EW_BLOUSE — inactive in BIS, so not pushed — is still planned in Sales Plan from its own LY with a fallback growth. It is counted in BIS's re-spread and again in Sales Plan. A fix is proposed; nothing changed, since it touches the Sales Plan engine.

### Every app reads the same, newest complete data-lake file (sales sync)
- **Change (user):** "sync the sales data and always pick the latest file from the folders to sync. Post sync, make sure that the data is flowing through all the apps consistently."
- **Found:** new exports landed today (29 Sep): month-wise `master.parquet` (22,769,780 rows, +392k), day-wise `…_20260929T043251` (bills to 28 Sep), and a sell-through file of **exactly 50,000 rows** (the previous one has 7,069,667 — a capped or partial export). The apps chose files in five different ways, so they would have split across files:
  - **BIS sales:** pinned to the 5 Sep copy.
  - **BIS sell-through:** newest by time with no check, so it would have taken the 50,000-row file.
  - **Listing:** newest by the date stamp in the file name, so it would have kept 5 Sep (`master.parquet` has no stamp), and `build_sales` would have crashed.
  - **Sync jobs (`store_actuals`, `day_weights`):** alphabetically-last name, which picked the **old** 28 Aug day-wise file.
  - **Nightly accuracy check:** would have compared the new snapshots with the old 5 Sep file.
  - **Sales Plan's `extract_dept_kpis`:** added up every sell-through export (each week counted 2–4 times).
- **Fix — one rule, `rs_common/lake_files.py`:** each folder holds full re-exports, so exactly one file is read — the newest by modified time, unless it is clearly incomplete (unreadable/still being written, missing columns, or fewer than 90% of the previous export's rows); then the last good one, with a note saying why. BIS (unpinned), the Calendar engine (and through it Sales Plan's snapshots, the AOP syncs and MRP Re-apportionment), the sync jobs, the nightly check and Listing all use it.
- **Picks today:** month-wise `master.parquet` · day-wise 29 Sep · sell-through the complete **2 Sep** export (the 50,000-row file is skipped: "only 50,000 rows vs 7,069,667").
- **Tests:** `rs_common/test_lake_files.py` (newest wins; truncated, column-short and half-written files are skipped). The existing reindex/sync tests pass.

### AOP Re-Aligner: you choose which months are locked
- **Change (user):** "make these locks dynamic for months so that it depends on the user if they want to get it locked or they want to get them changed accordingly. Also auto detect the months as per the original plan upload." Before, Jan and Feb were always locked (`FROZEN = ("Jan", "Feb")`, checked in 14 places), and nothing else could be.
- **Now:** the month chips under "Original plan" are the months found in the uploaded plan (its `<Month> Plan` columns — today Sep'26 … Feb'27 P2). Each chip is a lock button: click to lock (kept exactly as the original, value and qty) or unlock (changes with the realignment). A new plan starts with Jan / Feb locked, as before. A month the previous plan also had keeps your choice. The choice is saved (`.cache/locks.json`, gitignored) and survives restarts. Changing a lock re-checks the revised file and clears an earlier result, since it was realigned with the old locks.
- **How:** `engine.locked(m)` replaces every hard-coded Jan/Feb check; it reads `engine.LOCKED`, which the server sets from your choice, and falls back to Jan / Feb when nothing is set. **The realignment maths is unchanged:** it already kept "frozen" months as the original; only which months count as locked is now yours. Messages, the verify check ("Locked months untouched"), the comparison table header and the Rules panel say "locked months".
- **Check:** `test_realign.py` — all existing checks pass on the default. New check: locking Nov instead of Jan keeps every Nov value exactly as the original, and Jan takes the revised 99 (split 59.4 / 39.6). Live page: Dec'26 locked → chip and server locked; unlocked → back to Jan / Feb.

### Security: the platform no longer runs on a public session key (P0, no calculation changes)
- **Problem:** `SESSION_SECRET` was not set on the live server, so 8010 (and 8000) fell back to `"dev-only-change-me"`, which is written in the code. Every login session, 30-day remember-me cookie and password-reset link was signed with it: anyone with the code could forge an admin session. **Proven before the fix:** a cookie signed with the default key for a made-up user was accepted (`/api/auth/me` → 200).
- **Fix:** `auth.security.session_secret()` is the one rule (8010's SessionMiddleware, remember-me and reset links all use it; AOP 8000 applies the same check). With `APP_ENV=production`, a missing, default or short (<32 chars) secret **stops the app from starting**. Development keeps the documented dev key with a warning. A 64-character random `SESSION_SECRET` and `APP_ENV=production` are now Windows user environment variables on the server. They are never printed and not in any file. `.env.example` lists the names.
- **After the restart:** the same forged cookie is rejected (401). Landing, 8010, 8000 and 5050 answer normally. **Everyone had to sign in again once**, and old remember-me cookies and reset links stopped working.
- **Tests:** new `tests/test_session_secret.py` (3 pass: production refuses empty/default/short, accepts strong; development falls back with a warning). `test_router_mount` / `test_calendar_mount` log in to the live server as the fixture user `planner1`, which fails on this server's database (401) with or without this change.

### BIS: Save says whether Sales Plan received the plan
- **Found on the re-check:** after "reloaded and saved", Sales Plan still had the 09:01 push. The Save left no trace, and BIS gave no sign: a push that sent nothing (AOP not synced on the page, or no rows) was silent, and a successful one looked the same as a failed one.
- **Now** the Save button always reports the outcome: "Saved ✓ — N growth rows sent to Sales Plan", "Saved in this browser only — NOT sent to Sales Plan: <reason>", or "Growth NOT sent to Sales Plan (status – sign in again)". A save that was redirected to the sign-in page counts as a failure. Failures are also shown on automatic saves.
- Checked in the sandbox (its push cannot reach Sales Plan): Save → "Growth NOT sent to Sales Plan (501)"; with no AOP → "NOT sent … no AOP synced".

### Landing (7800) now restarts itself — the whole suite stays reachable
- **Problem (user: "the whole server went down" → "permafix this issue"):** Landing stopped when the Claude session that had started it was restarted. Every app is opened through Landing, so every link died, although the servers behind it (8010, 8000, 5050, 8060, 8070, 8123) were all still running. Nothing watched Landing: its own watchdog restarts the other apps, not itself. The four "RS Planning - … Server" scheduled tasks had **never run** (last run 1999): they fire "at system start-up" but only "when the user is logged on", which Windows never meets. The BIS task also points at an old copy of BIS (`…\Buyers Input Sheet`).
- **Fix:** `Landing/keep_alive.py` starts Landing in the background (no console window, no new browser tab — `--no-browser`) whenever port 7800 is down. The new scheduled task **"RS Planning - Keep Alive"** (`Landing/install_keep_alive.ps1`, current user, no admin) runs it at sign-in and every 2 minutes. Landing's own watchdog then brings back any app that is down within 30 s.
- **Check:** after installing, the task started Landing (result 0). Landing was then stopped on purpose and came back by itself in **24 s**. `/` → 302 to sign-in, `/login` 200, and all six apps answer.
- Not changed: the four old never-firing tasks (disabling them needs an admin window) and the "RS Planning Landing" Startup shortcut, which is harmless — whichever starts Landing second just exits.

### BIS: making a department inactive keeps the division on its AOP target
- **Bug (found on the re-check after the reload):** LADIES reached Sales Plan 0.01–0.08 L a month under AOP (Mar −0.0725, Apr −0.0636, May −0.0800, Jun −0.0137 L). L_EW_BLOUSE had been made inactive by hand; its planned sales were simply dropped instead of passing to the other departments. The toggle also never saved, so Sales Plan only got the change on the next reload.
- **Fix:** making a department inactive or active again rescales the other unlocked, active departments of that division by one factor, so the division lands exactly on its AOP target. Each department keeps its growth relative to the others, and locked cells are untouched. The change then saves and pushes like any edit. A plan already saved off target (like the current one) is put back on target when BIS opens — locally only, since opening pushes nothing — and a message asks for one **Save**.
- **Check (sandbox that cannot push):** inactivate → LADIES gap 0 in all four months, MENS untouched, kurti/dupatta growth ratio unchanged, 1 push. Re-activate → 0, pushed. A stale saved plan 1.5 L off → 0 after opening, no push, message shown.

### Sales Plan PW/W and SOR Deviation: block read from the imported files; SOR laid out like PW/W
- **Change (user):** "similar format for SOR deviation just like PW/W Deviation, and instead of the manual search bar in PW/W I want an auto detect from the file imported so that there is sanctity between modules, make this happen in both". The user chose month columns in the file.
- **PW/W:** the BLOCK search box (91 month combinations) is gone. The PPO Cont % file now carries one column per TY month (DEPARTMENT | ARTICLE NAME | FINAL MRP | Mar'27 | Apr'27 | …). Sync reads those headers (Excel dates, "Mar'27", "Mar-27", "Mar 2027", "2027-03" all work), detects the block (4 months Mar'27–Jun'27 → MAMJ; months must be consecutive plan months) and shows it read-only. Phase 1 and Phase 2 always run on that block. Phase 2 uses each month's own MRP mix; Phase 1 uses the block average. **The current single-column PPO Cont %.xlsx is refused** with a message showing the new columns, until it is re-saved with month columns.
- **SOR:** the two drag-drop boxes are replaced by PW/W's "Sync from Folder" panel. Both files are read from `SalesPlan\SOR Deviation\` (`Sales Plan Cont %.xlsx`, `Stock PPO Cont %.xlsx`), their months are detected the same way and must match, and the block is shown. A red note appears if SOR's block differs from PW/W's. The upload endpoints are gone.
- The standalone Sales Plan server also serves the deviation routes at `/api/planning/deviation/*`, which the pages call.
- **Check** (`SalesPlan/backend/engines/test_deviation_blocks.py`, on temp copies): wide PPO file → MAMJ with per-month mix; old single-column file refused; SOR files with matching months → MAMJ and "same as PW/W"; files with different months refused.

### Sales Plan MRP Re-apportionment: LY sales from the sales engine; page works again
- **Change (user):** "LY actual sales will be taken from the sales engine which is embedded in all the other apps, only the new MRP structure will be given, making sure that there are no mismatches in the actual sales structure." Before, the page wanted an uploaded .xlsb/.xlsx of sales.
- **Now:** the engine reads LY Mar–Jun 2026 from the Calendar engine's own data-lake file, using the Calendar reader (5 Sep 2026 export, the one every app uses), at store × division × department × MRP × display × attribute × month. The only upload is the MRP Mapping Master. Every store × department × month is tied to the Calendar department sales Sales Plan reads: **2,12,799 cells, max difference 0.0 L, ₹56,646.33 L both sides**. Run is blocked if the tie ever breaks. The sales template download and the Historical Sales folder are gone.
- **Bug fixed:** the page's backend router was never mounted in the platform (or the standalone Sales Plan server), so the page could not load anything (the old "MRP Re-apportionment page 404"). It is mounted now at `/api/planning/mrp-reapportionment`.
- **Check** (`SalesPlan/backend/engines/test_mrp_reapportionment.py`): a synthetic MRP structure on real engine sales (MSE_R/N T-SHIRT H/S, two lowest MRPs discontinued) re-apportions 3,327 rows into 9,469 with all 190 store totals unchanged. A planted 0.02 L error is caught.

### Sales Plan Division Plan shows the BIS plan, Mar–Jun 2027 only
- **Change (user):** "LY base should be imported from the data source and static once loaded" and "show the plan shown in BIS and not any day further". Before, the LY base was a typed-over constant (KIDS 54,237.27 L, an annual figure hard-coded in `division_plan.py`), and the plan was spread over a full Apr'27–Mar'28 year.
- **Now:** the page reads the AOP publish that BIS last pushed growth on (else the live saved version; today Version 2, publish 112). Per division and month (Mar'27–Jun'27) it shows the **LY base** (the publish's base, Mar–Jun 2026 like-for-like, read-only) and the **plan** (the publish's division target — BIS spreads every division exactly onto it). Growth is plan ÷ LY − 1 on the period totals: KIDS +12.9%, LADIES +11.6%, MENS +9.3%, total ₹38,882.54 L → ₹43,184.66 L (+11.1%).
- Removed: the editable LY base / growth / FY-start inputs, Add Row, Calculate, the 12-month spread, and the page's "Use This Version" panel (it only fed this page). Change the plan in BIS. Export CSV exports these months.

### BIS: Period 19 V 26 / 25 V 26 = growth on the period totals
- **Bug (user):** L_EW_DUPATTA's Period 19 V 26 read +96.1% while its hover said the period total grew +62%. The cell averaged the four monthly %s (+261.6, +91.1, +31.9, −0.4); the hover summed the ₹. **Fix:** division, department and attribute Period cells now use the summed ₹ behind the hover: DUPATTA +62.6% / +22.2%.
- **Check:** all 239 Period cells across the Buyer's Plan, Department, Attribute and Division views equal the hover's "Period total" (sandbox copy that cannot push).

### BIS: inactive departments show only on the Inactive Depts sheet
- **Bug (user):** a department made inactive by hand still showed as a greyed row in the Buyer's Plan as well as on the Inactive Depts sheet. It (and an attribute whose departments are all inactive) now shows only on the Inactive sheet, where the same toggle re-activates it. Checked in the sandbox: L_EW_DUPATTA made inactive → gone from Buyer's Plan, on the Inactive sheet; re-activated → back.

## 2026-09-28

### BIS: 19 V 26 and 25 V 26 compare Mar–Jun 2026 with the same months earlier
- **Change (user's call):** the "26" side of both history columns is now **Mar–Jun 2026**, the same months as the plan LY, and the "25" base is Mar–Jun 2025. Before, April–June were 2025 against 2024, because the columns used Apr–Mar financial years. Months outside Mar–Jun are unchanged (Jul'25–Feb'26 and a year earlier). Together with the entry below, every Mar–Jun cell now reads 2019 → 2026 or 2025 → 2026 for the same month.
- **Bug fixed along the way:** BIS matched division names by substring, so "CONSIGNMENT" (it contains "men") was counted as MENS. It added up to 7.2 L a month to MENS's 2025 base. Divisions now match on whole words.
- **Effect (MAMJ, same stores):** 19 V 26 MENS +26.0%, LADIES +47.0%, KIDS +25.9%; 25 V 26 MENS +7.5%, LADIES +15.0%, KIDS +14.4%. The same stores are used every month: 31 for 19 V 26 and 120 for 25 V 26. ML_JOGGERS: 0.62 → 1.76 Cr (19 V 26) and 4.75 → 5.49 Cr (25 V 26).
- **Check:** all 2,861 division and department × month cells (Mar–Jun, both columns) and the store counts equal an independent recompute from the raw file (max 0.005 L, planted 0.02 L caught). The hover labels follow (e.g. "Apr'25 → Apr'26"). Browsers re-sync by themselves (`hlflcohort19jjw`).

### BIS: 19 V 26 uses March 2019
- **Change (user's call):** the 19 V 26 base is now calendar 2019, so March is **Mar 2019**. Before, it was FY19's March, Mar 2020 (the lockdown month). Apr–Jun were already 2019. Buyers judge history on the same months as the plan period. 25 V 26 is unchanged.
- **Effect, ML_JOGGERS (same 31 stores):** the base for March goes from 0.1137 to 0.1696 Cr, and the Mar–Jun base from 0.56 to 0.62 Cr. The hover now reads "Mar'19 → Mar'26". Every browser re-syncs its history by itself (version tag `hlflcohort19`).
- **Check:** all 8 ML_JOGGERS 19 V 26 / 25 V 26 month values equal an independent recompute from the raw file.

### BIS: zero-sales departments, re-seed and clearer history hover (follow-up to the department LY fix)
- **Bug found after the reload:** a department with no sales in a month (e.g. winter lines in April) was missing from the new per-department figures, and BIS fell back to the old share estimate for it — MENS April's base read 43.16 Cr instead of 39.10, so BIS seeded MENS Apr at −0.35% and sent plans 51–405 L below AOP. **Fix:** once the sync has delivered a month, a missing department counts as 0. The seed fingerprint carries a version tag, so every browser re-seeds once (locked cells kept).
- **Hover on 19 V 26 / 25 V 26:** each line now names the real months and says it is same-store history, not the plan LY — e.g. ML_JOGGERS "Apr'19 Rs 0.13 Cr → Apr'25 Rs 0.31 Cr, same 31 stores". Before it said "FY19 → FY26", which read like the LY Actual Sales column (Mar–Jun 2026, 148 stores). Note: "19 V 26" compares Apr'19–Mar'20 with Apr'25–Mar'26; "25 V 26" compares Apr'24–Mar'25 with Apr'25–Mar'26.
- **Check (sandbox copy that cannot send to Sales Plan):** every division × month base = the division's actual total; all 12 plans = AOP target (max 2.5e-12 L); ML_JOGGERS LY 2.33 / 1.69 / 1.44 / 1.31 Cr at 7.52 / 10.00 / 10.00 / 9.97 %.

### BIS: departments show their own LY sales
- **Problem:** BIS only received division totals from its sales sync, so each department's monthly LY was estimated as its FY26 share of the division × the division base — every department took the division's seasonality. ML_JOGGERS MAMJ showed ₹6.3 Cr; its actual in the 148 plan stores is ₹6.77 Cr (Mar 2.3303 / Apr 1.6906 / May 1.4406 / Jun 1.3082 Cr).
- **Fix:** the sales sync also returns each department's LY per AOP month for the same 148 plan stores (`sec_actual_ly`, ₹ Cr to 6 dp); department rows, the magnifier and seeding use it (the share estimate stays as a fallback). The seed fingerprint includes a hash of these figures, so a change re-seeds with locked cells kept and every division still plans exactly to AOP. Saved browser copies without the new figures re-sync by themselves.
- **Check:** all 746 KIDS / LADIES / MENS department × month cells equal an independent recompute from the raw file (max 0.0022 L, planted 0.02 L caught). BIS departments sum to the division totals exactly for MENS and KIDS; LADIES is 0.02–0.03 L short from four tiny departments not in BIS's list (three LS_PC personal-care lines, LW_U_CORD SETS).
- The 19 V 26 / 25 V 26 history figures were re-verified at the same time: all 16 ML_JOGGERS values equal the recompute exactly (19 V 26 March = Mar 2020, FY19's March, by design).

### Suite revamp: "Ink and paper" look, three sister schemes, calmer screens
- **New colour schemes** (Landing → Theme; all apps follow): **Ink and paper** (the alternate design's ink chrome, deep teal accent, warm paper page — now the default and the saved choice), **Ink and clay** (terracotta), **Slate and harbour** (harbour blue), **Moss and linen** (moss green). All four meet WCAG AA for every text / fill pair (button text ≥ 8:1, accent on page ≥ 5:1). The five earlier schemes stay in the picker.
- **Type:** the shared theme script loads IBM Plex Sans (text), IBM Plex Mono and Fraunces (page titles) and exposes `--st-font-body / --st-font-mono / --st-font-display`; every app's base font now reads `var(--st-font-body, <old font>)`. Numbers stay in Plex Sans tabular figures so dense grids keep their widths.
- **Calmer screens (styling only — no logic, links or app-to-app navigation changed):**
  - Landing: serif title, one-line descriptions, flat core cards joined by arrows as a chain, slimmer tool cards.
  - Buyer's Input: the per-row "Active" pill is a quiet status dot (still the same on/off button), neutral section headers, flat KPI tiles, serif wordmark.
  - AOP: serif titles, flat cards, the stacked filter bars read as one area, Review growth grid with a light head and pastel month chips (the dense Output pivot keeps its dark head, whose controls are built for it).
  - Sales Plan, Calendar, NSO, Re-Aligner, Listing / Delisting Analyser: serif titles / wordmarks; Listing KPI captions wrap instead of running past the card.
- Checked in the browser: Landing, BIS (row switch still toggles), AOP home / Review / Results / Output (contrast audit clean on Review), Sales Plan home, Listing, Re-Aligner, NSO. Calendar builds; its screens need a sign-in to view.

### Cluster-wise actual vs reindexed report (no code change)
- Excel report (cluster × month, Jan–Aug) built from the Calendar's **day-wise** tables: actual by last-year month vs reindexed by plan month, shift, shift % and plan-day coverage, plus Detail, Conservation and Notes sheets.
- Finding: the **month-wise** reindex moves each last-year month whole into one plan month, so month by month it equals the actuals — real festival and weekday shifts across month boundaries only show at day level.
- Result (data to 27 Aug'26): every cluster conserves exactly (0.00 L); sales move only between Feb and Mar (e.g. N. EAST - PUJA +66 / −66 L, JH + MP + CG +43 / −43 L, JAMMU + RJ +29 / −29 L); Apr–Aug ≈ 0; Aug'27 87% covered. Sep–Nov (Puja / Diwali) need a newer day-wise export and a manual Run Reindex. ₹296.53 L of unclustered stores (closed / HO / warehouse / sites) is not calendarised.

### Nightly accuracy check of the calendarised sales
- Committed `ab9fabe`.
- New job `sync/calendar_check_sync.py`, run by the nightly sync right after the Calendar reindex (and by AOP's "Sync into database" button). Read-only; ~45 s; tolerance 0.01 L per cell:
  1. saved actuals = a fresh read of the raw month-wise export (store × division × month);
  2. saved reindexed = an independent recompute (each cluster's month map rebuilt from the saved day pairs);
  3. conservation: reindexed total = actual total per store × division;
  4. department tables = main tables (actual and reindexed);
  5. every cluster's day map covers each plan day once and reuses no LY day;
  6. every trading store with sales has a calendar cluster (closed stores, HO, warehouses and sites are listed, not shifted — 316 L on 28 Sep);
  plus a self-test: a planted 0.02 L error must be caught.
- A failure marks the run failed with the reason and keeps the per-check detail (`sync/common.py` now stores detail on failure too). The **Sales Sync** page shows "Accuracy check passed 8/8" (or FAILED) under the last sync, with each check on hover.
- First run 28 Sep 12:21: 8/8 pass, every difference 0.0 L.
- Also fixed `sync/test_calendar_reindex_sync.py`, broken by `267d1d6` (snapshot save gained a `suffix` argument).

### Deep check after the department split (no code change)
- 17 of 19 checks pass at 0.01 L (planted 0.02 L errors caught). Calendar department snapshots = totals (0.000000 L); AOP live = V2; BIS, Sales Plan, Attribute Master (DB = file, 978) and Listing / Delisting Analyser all on the new department names; 13 test suites pass.
- After BIS was opened at 12:07 it pushed the new names to Sales Plan (792 rows, AOP 112). Sales Plan now applies exactly AOP's growth (to 0.0003 pp); its SSG plan meets the AOP target within 0.05 L in Mar–May'27 and 0.92–1.16 L in Jun'27.
- The remaining difference is entirely V2's saved LY base vs today's Calendar data (Mar–May ≤ 0.045 L, likely V2's 2-decimal store rows; Jun'27 = the ODISHA calendar re-save). A new AOP version made live would bring both to zero.

### Split departments adopted across the suite — `7c0a1e2` (core), `f682b5d` (additional apps + rename), `4040f68` (attribute master DB)
The data lake's 5 Sep export re-classified six departments back to 2019; the parts add up exactly to the old department (store × month) and division totals are unchanged.

| Old | New |
|---|---|
| MSE_PYJAMA | MSE_HSR PYJAMA, MSE_TXTL PYJAMA |
| KB_T-SHIRT H/S | KB_R/N T-SHIRT H/S, KB_POLO T-SHIRT H/S |
| KB_BERMUDA | KB_HSR BERMUDA, KB_TXTL BERMUDA |
| LW_L_PALAZZO | LW_L_WES PALAZZO, LW_L_ETH PALAZZO |
| LW_L_JEGGING | LW_L_DNM JOGGER, LW_L_WVN JOGGER |
| L_IN_BRA | L_IN_BRA (smaller), L_IN_SPRT BRA |

- **BIS:** new sections (season inherited, FY26 LY split exactly), sales file re-pinned to the 5 Sep export so LY, 19 V 26 / 25 V 26 history and sell-through come from the new names. A saved plan or version on the old names hands each old department's growth, AOP seed, lock and hide state to its parts once, then saves so Sales Plan switches too. Division LY unchanged (388.87 Cr). Check: `node test_dept_split.js`.
- **Sales Plan:** master list on the new names with the right season (the auto-registered REGULAR copies removed); MRP plan split and department active states carried to the parts.
- **Attribute Master (`att master.xlsx`):** the 9 missing new departments added with their old department's section and season, the 5 old names removed (978 rows, one per department; ~618k empty formatted rows dropped).
- **Attribute Master in the database (`masterdata.attribute_master`):** loaded on the user's go-ahead. The table did not exist before — Sales Plan's attribute correction had been falling back to the Excel file — so the loader created it with the 978 rows and no old rows existed to delete. Sales Plan now reads the table (same content). `test_attribute_master.py` expects 978 in both.
- **Listing / Delisting Analyser** (renamed from "Listing / Delisting" on Landing, in the app and in the Re-Aligner): listing history hands each old department's flags to its parts for the months before the listing sheets switched names (Jan'26); the day-wise cache splits an old department's days by that store's month split from the month-wise export (exact per store × month) until a day-wise export with the new names lands. Sales, seasonality and suggestions rebuilt.
- **Verified:** BIS shows the new departments with LY, both history growths and sell-through, and no old names; a saved plan's migration gives each part its old department's exact growth and AOP seed. Listing's split day-wise sales equal the month-wise export in every store × month Jan'24–Jul'26 (max 0.002 L); listing history, sales, seasonality, windows and suggestions carry only the new names (the old ones appear only in the cache's split trace). Suggestions rebuilt: 338 delist, 155 relist.
- **Re-Aligner:** its plan already uses the new names; it reads the rebuilt Listing files and the updated Attribute Master.
- **NSO Distributor:** no names of its own — it uses the uploaded Sales Plan export (new names) and Attribute Master (upload the updated one).

### BIS: smoother section / attribute lock — `7042878`
- One padlock drawing for both states (was a text "○" swapping to a 🔒 emoji of a different size, so the cell jumped). The shackle drops when locked and lifts when unlocked, with a short pop; the growth input tints amber while locked. Animations play even though the table re-draws on each toggle, and are off for reduced-motion users. The button is keyboard-operable and keeps focus after the re-draw.

### Sales Plan uses AOP's 148-store LFL rule for SSG — `9f827f4`
- **Before:** Sales Plan's SSG stores = tag ends with "- Stores" + an ANG override = **121** stores, so its SSG totals could never equal AOP (KIDS Apr'27 ₹2,575 L vs ₹3,108 L).
- **Now:** `store_master.is_ssg` calls AOP's own `engine_v3.auto_tag` (trading store, opened by 31 Dec before the LY window) = **148** stores, the same set AOP and BIS plan on. The 27 added stores are the FY26 Q1–Q3 openings (Mar–Oct 2025); none dropped. ANG override removed (already inside the 148).
- **Check:** SSG LY = AOP base within 0.04 L for Mar–May'27 (e.g. KIDS Apr'27 2,825.51 vs 2,825.49 L); Jun'27 is ~1 L off per division (the known V2 ODISHA Jun'27 calendar difference). Every department with BIS growth plans at exactly +10.0% in Apr–Jun, as in AOP. Missing ref stores 134 → 106.
- **Still short of AOP TY by ~1–1.5%:** departments the data lake names differently from BIS get no growth (e.g. KB_R/N T-SHIRT H/S vs BIS KB_T-SHIRT H/S, MSE_HSR/TXTL PYJAMA vs MSE_PYJAMA, LW_L_WES/ETH PALAZZO vs LW_L_PALAZZO) — needs a department mapping decision.

### BIS: history hover not showing — `0b6f95e`
- **Problem:** the 19 V 26 / 25 V 26 hover and header store counts stayed blank in a browser that had opened BIS before `267d1d6`. BIS keeps the history in the browser (`ck_lfl_growth`) and only re-fetched it when the server's data version changed, so the old copy (no store counts, no ₹ values) was kept.
- **Fix:** a saved copy without store counts is treated as out of date and re-synced on open. Verified by planting an old copy and reloading: headers show "19 V 26 · 31 st" / "25 V 26 · 101–120 st", cells show the per-month ₹ Cr and period total.

### Sales Plan reads LY sales from the Calendar; Buyer's Input drives department status — `267d1d6`
- **Department Master:** "Sync from AOP Forecaster" is now **"Sync from Buyer's Input"**. KIDS / LADIES / MENS departments are active when live BIS plans them (96 / 57 / 39), inactive otherwise; GM / RETAIL are left as set. The AOP division-target loader stays as a small "Load AOP division targets" link.
- **Growth Matrix:** inactive departments are greyed, tagged INACTIVE and read-only; column fill skips them.
- **Sales Sync page:** the manual "Sync Sales" button and the Excel import (MAMJ'26, month locks, admin unlock) are removed. The page is read-only and shows the last nightly sync and the new department-level tables.
- **Sales Plan actuals:** store × department LY sales now come from the Calendar's department snapshots, refreshed nightly by `sync/calendar_reindex_sync.py` — **reindexed sales = plan base**, actual sales alongside. New snapshot kinds `actual_dept` / `trend_shifted_dept` (migration `d9f3b2a7c1e5`). They sum exactly to the existing month-wise snapshots (0.000000 L over 20,569 cells). First full plan built: 425 stores, Mar–Aug'27.
- 29 departments with sales but missing from Sales Plan's department list were auto-registered (incl. ₹36.5 Cr MENS pyjamas).
- **BIS 19 V 26 / 25 V 26:** header shows the like-for-like store count (per-month counts on hover); cell hover shows both years' ₹ Cr per month, store count and period total.

---

## 2026-09-26 — Planning-chain audit fixes — `5f551d7`

Audit tolerance 0.01 L per cell and total; every check also had to catch a planted 0.02 L error. Live AOP = Version 2 (publish 112).

**BIS**
- AOP growth is kept unrounded (was 2 dp → up to 0.15 L/cell off target); display stays 2 dp. Re-balancing no longer re-rounds.
- Seeding uses the LY of **active** departments only (hidden departments had left divisions up to 528.82 L short).
- Reopening keeps the buyer's edits: BIS re-seeds only when the AOP version changes (locked cells kept); "Re-seed plan" is the full reset.
- Pushes to Sales Plan only months BIS actually records, only once AOP is applied, stamped with the AOP publish id; a failed push is shown to the user. One push per AOP apply (was two).

**Calendar**
- Cluster names are case-insensitive: the last-saved spelling wins across all cluster tables (`adopt_cluster_spelling`); "Kashmir" → "KASHMIR".
- Month-cache key now includes the store → cluster map, so a renamed cluster isn't served stale months.

**AOP Forecaster**
- Review grid: fixed column widths, plain "All months" column, month selector; Results follow the same month pick.
- Store rows kept at 4 dp; "Base Calendar" label shows both calendar ids.
- Reindexed-base preview counts DND / CDIT / CONSIGNMENT in the division shares.
- **Lock to Planning:** locking a deleted / unsaved version now refuses with a message (it used to silently lock the latest saved version).

**Sales Plan**
- Plan engines read the live BIS growth on P1/P2 (months BIS doesn't record are hidden); GM / RETAIL stay editable.
- Division Plan: AOP months land exactly on the AOP target; fixed the Apr–Mar plan running Jul–Jun; Export CSV exports the plan on screen.

**Landing**
- Added the missing `/api/config/buyer-department-growth` route, so BIS growth reaches Sales Plan through the shared address.

### Known open items (reported, awaiting a decision)
- ~~Sales Plan SSG uses 121 stores~~ — fixed 28 Sep (`9f827f4`, 148 stores).
- NON FOOD: Sales Plan files it under RETAIL, AOP under GM.
- MRP Re-apportionment page returns 404.
- V2's Mar'27 base is not festival-shifted (141 L, accepted); 38 KLM departments have no BIS growth.
