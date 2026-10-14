# RS Planning Suite — Changelog

Suite-wide changes across Calendar → AOP Forecaster → Buyer's Input Sheet (BIS) → Sales Plan.
Newest first. Each entry names its commit.

---

## 2026-10-14

### Division x Cluster x Cluster-tag cap tried and reverted - back to the AOP hold per division x month
- **Asked (user):** "CLUSTER x CLUSTER TAG should be maintained only so cap should be that" (commit `9ae33d4`: one factor per division x cluster x month for the SSG stores - all 54 cells on the AOP, factors 0.67-1.51, the manual-vs-portal gap unchanged at ~₹2,015 L), then "remove the cap and revert back to the previous version".
- Reverted (`git revert` of `9ae33d4`, this entry kept as the record): the SSG stores are held on the AOP per division x month again (one factor over all 148 stores, the mix kept); the new-department re-balance keeps SSG stores together. Plan regenerated, Display Type / Qty re-run (23,406,367 pieces - the same as before the cap), every check passes. Cluster totals are free flow inside each division again (NSO / Others stay on their AOP store plans).

### Display Type: Validation tab removed
- **Asked (user):** "remove validation" (Display Type page tabs ₹L Plan / Validation / Qty Plan).
- The Validation tab, the "✓ Validate" button and its gate are gone; "Run Qty" shows once the plan has run (ASP imported), next to "Re-run Plan". The same checks stay in Reconciliation's full check-up (UDF and Qty stages) and Rectify still runs the server-side validation; the `/validate` endpoint stays for them.

### Decision: Sales Plan keeps the AOP hold on each division
- **User (14 Oct):** "keep the AOP hold on each division". The like-for-like plan stays on each division's AOP month by month (one factor per division x month over the 148 SSG stores, the department mix kept), also when BIS divisions are locked off AOP (Iteration 4: KIDS Mar x1.11). No code change - recorded so it isn't reopened; the portal vs BIS difference on the manual table (+₹239.5 L) is this hold, by design.

### Like-for-like department LY = AOP base split by ACTUAL LY sales; store-group filter in every export; BIS = 148 SSG
- **Asked (user):** "the filters should be present to see actual sales growth %. Secondly, the BIS will only and only run on 148 stores AOP always which are SSG. Also, AOP forecaster will use LY cont % actual sales will be used to break the target instead of reindexed."
- Sales Plan like-for-like step: each store x division x month AOP base (else the Calendar's reindexed total) is broken into departments by the departments' share of ACTUAL LY sales (Calendar actual_dept, the same month last year); the reindexed mix only where that store x division x month has no actual sales (`dept_sales_engine`, meta `lfl_dept_mix`). Same rule as the AOP Forecaster's Output tab (actual cont % since 9 Oct) and BIS (own actual department LY): Sales Plan's department LY now equals BIS's for all 113 departments of the manual-vs-portal table (max 0.01%) - the "LY base" step went from -₹154.7 L to 0; what is left between portal and BIS is the AOP division hold (+₹239.5 L). Check-up "department LY = split by actual LY cont %" passes; Journey shows "Actual LY". Totals unchanged (₹79,403.1 L; SSG ₹43,186.8 L).
- Store group filter: "Store type" is now "Store group (SSG / NSO / Others)" on every Hierarchy (Final Results, MRP, Display Type, Article Name); every Excel export carries it as a column (added as the last field when not in the Rows), so a filter on SSG gives the like-for-like growth.
- BIS rule recorded: BIS plans only the 148 like-for-like (SSG) stores against the AOP like-for-like division targets (sync_server `plan_lfl_stores`); NSO / Others live in Sales Plan only.

### Excel downloads in the classic pivot layout (no drill-down rows)
- **Asked (user):** "also make the download happen in classic pivot table formats rather than straight drill downs as it increases rows and blank space".
- Sales Plan hierarchy exports (Final Results, MRP Output, Display Type, Article Name, re-apportionment compare - `grain_view.tree_xlsx`): Excel's tabular form with every item label repeated - one row per combination of the Rows fields (the deepest level, in the page's order), each field in its own column, LY / TY / Growth % / Cont % (of the level above), Grand Total last; no parent / outline rows, no indented first column. Final Results Division › Department › Month: 771 rows, no blank labels, rows add up to the Grand Total (₹79,403.1 L).
- STR Forecaster Excel: the "Drill-down" sheet (one row per layer level) is now "Pivot" - one row per cluster x division x department x store (the page's layers), labels on every row, the N-month average and each month's figures alongside (21,903 rows).

### STR Forecaster: Mar-Jul (July fixture and sales plan added)
- **Asked (user):** "this is the respective sales plan and fixture plan sheet. Implement the respective plans till july and preview the same logic till july in the STR forecaster" (Mar'26 to Oct'26 Fixture Allocation (2).xlsx, month wise sales plan - julyu - feb.xlsx).
- Fixture upload 7 = the new workbook's Mar'26-Jul'26 sheets through the app's own parser (Aug fresh / old stock, Sep, Oct left out), +12 -> Mar-Jul'27: 112,180 rows; Mar / Apr / Jun the same as before, May MDQ 6.79 M -> 6.89 M (the new file), Jul 203 stores, 6.93 M MDQ.
- Sales plan upload 9 = the MAMJ plan in use (upload 6) + the JULY sheet (Store Name / DEPARTMENT / UDF 06 / "July Sales Plan - Final" Rs lakh / "... Final Qty"): July Rs 85.88 Cr, 2.95 M pcs, 194 stores (no article column - July splits at department level). The same 180 stores are compared (every month in both files); LY Jul'26 from the Calendar actuals.
- The logic is the same, now over 5 months: forward cover walks Jun into Jul; the festival lift is learnt on Mar-Jul festival days (str_season FEST_MONTHS (3, 7); season file rebuilt - Rath Yatra 6 days in Jul'27 for Odisha / WB). Labels follow the months loaded ("5-month avg", "MDQ (all months)") on the page and in the Excel.
- Fix: an upload with an empty article / display failed (COPY read '' as NULL; `_copy` now uses FORCE_NOT_NULL). The earlier uploads stay (Rollback switches back).
- Today (division, forward-cover days Mar / Apr / May / Jun / Jul): KIDS 61 / 63 / 70 / 86 / 96, LADIES 58 / 59 / 57 / 63 / 69, MENS 43 / 45 / 46 / 50 / 57.

### Number journey: Excel in plain words
- **Asked (user):** "give me an excel downloader for this journey so that in plain words can be explained" (and, on cluster / SSG-NSO-Others tags: "nervermind it is there in the right side").
- "⬇ Excel (this journey)" on the Journey page (`GET /display-type/journey/export`, `journey.journey_xlsx`): sheet Journey = store, group, cluster, tag, reference, department, month, then one row per step (stage, step, in plain words, calculation, value, unit, check); sheet "All MRPs to UDF" = every MRP of the department that month with all 32 export fields. The store picker also shows each store's group (e.g. "ABD · SSG · BH - (NP)").

### Sales Plan: Number journey (how a number is made, sources to UDF) + export of every field
- **Asked (user):** "i want a journey mapper in the side tile where i can know about how a number was derived till udf. Make sure that each and every contribution towards the numbers are mapped in a plain flow. Also i want all the fields availble for export till display type so that the user can easily export the report for fact finding".
- Sidebar "Number journey" (`/journey`, `pages/Journey.jsx`; `engines/journey.py`, `GET /display-type/journey`, `/journey/options`): pick store (grouped SSG / NSO / Others), department, month, MRP, display type -> a top-to-bottom flow, each step re-derived from its own input with its value and formula. SSG: Calendar LY -> x AOP LY base -> x BIS growth P1 / P2 -> x AOP hold (division x month) -> new-department step (LADIES) -> department plan (checked against the saved plan, ✓ / ✗). NSO / Others: AOP Forecaster store plan -> x the reference store's department share -> P1 / P2 like the reference -> department plan. Then MRP share (and where the split comes from) -> Table / Non-Table share (which LY mix, the reference store's for non-SSG) -> ASP (own / other display type) -> pieces. An MRP list beside it to follow any MRP.
- Export (`GET /display-type/export?format=csv|xlsx&division=&group=&store=`, replaces the old 14-column Excel): one row per store x department x MRP x month with 32 fields - store group, cluster, tag, reference store, division, attribute, department, month, dept LY, BIS growth P1 / P2 (SSG), AOP hold factor (SSG), store-division TY, dept share, dept TY P1 / P2 / total, growth %, MRP, MRP share P1 / P2, MRP TY, Table / Non-Table %, where the mix came from, Table / Non-Table TY, ASP and qty. All stores = 701,415 rows (CSV ~258 MB, ~40 s); Excel up to 1,000,000 rows, filtered by division / store group. On the Journey page (filters) and Display Type ("Export all fields (CSV)").
- Self-check (`python -m engines.journey`): one store of each group lands on its saved department plan, down to pieces.

### Sales Plan: every AOP store planned down to UDF (SSG / NSO / Others), on its reference store's split
- **Asked (user):** "148 are SSG, plan should come for the 309 stores or whatever count it is for the sales in the aop forecaster. The stores are tagged with clusters. Clusters can have 3 sets - SSG/NSO/Others wherein NSO means stores which have names and are not genericly numbered. Others are the ones which will fall under the NSO-01 or MAMJ-01 category. For stores which are out of the SSG 148 stores - their respective ref stores plan cont % can be taken and moved forward on every step. Go and fix this issue".
- Before: 428 stores in the plan file (319 AOP-tagged + 109 untagged ERP rows), 188 with a plan (148 SSG + 40 ramp stores on their own LY x the division's average BIS growth, ₹52,667.9 L); only the 148 SSG stores went through Display Type and Qty (₹43,186.8 L).
- Now (`dept_sales_engine` Step 2): a non-SSG store's TY = the AOP Forecaster's store plan (store x division x month, the publish BIS plans on, K/L/M), split by its reference store's department cont % and P1 / P2 (a non-LFL reference is followed to its own reference); the MRP split is the department's (same for all stores); the Table / Non-Table % is the reference store's (`display_type_engine.display_shares` maps a non-SSG store to its reference); qty from the ASP master. The Display Type / Qty runs cover every planned store. Store groups: SSG / NSO (named) / Others (NS- / AD- / MAMJ placeholders, the AOP's own prefixes) / Untagged (no AOP plan) - `group` and `ref_used` on every store, the Hierarchy's store type uses them.
- New-department step: the one-factor re-balance kept SSG stores together but now holds every other store on its own total (together, it had moved ₹30.85 L from the placeholder stores to the named ones).
- Result: 313 stores planned, ₹79,403.1 L = the AOP Forecaster's K/L/M MAMJ exactly - SSG 148 ₹43,186.8 L (unchanged), NSO 83 ₹19,887.6 L, Others 82 ₹16,328.7 L; Display Type run 701,415 rows for all 313 (0 errors); every value has a qty (23,322,932 pieces). Not planned: 109 untagged ERP rows, 10 DB-only ramp stores with a 0 AOP forecast, 2 named NSO (no opening month) and 4 placeholders without an AOP forecast. Named NSO have only a Mar'27 AOP value (the AOP has no opening month for them).
- Check-up: new "Store x Division x Month (NSO / Others): plan TY = the AOP Forecaster's store plan" (3,360 cells, 0 off) and "Store: plan TY = its Display Type run total" (313 stores, 0 off); the run check now covers all planned stores; the store-group table shows SSG / NSO / Others. All checks pass. Backup `backups/final_dept_plan.before-all-stores-14Oct2026.json`.

### Manual vs portal department differences explained
- **Asked (user):** "i have this difference which is coming, check why it there is difference, identify what is the step" (Made Manually vs Through Portal, 114 departments, ₹43,188.04 vs ₹43,186.78 L).
- Portal = BIS Iteration 4 (₹42,947.4 L) + LY base step (Sales Plan's department LY = AOP base x Calendar mix vs BIS's own LY: -₹154.7 L) + the division x month hold onto AOP (+₹394.2 L: Iteration 4 is exact-as-typed, KIDS ₹3.2 Cr below AOP -> KIDS Mar x1.11) = ₹43,186.8 L, 0 residual. The manual sheet is not Iteration 4's numbers: KIDS -₹421.5 L, LADIES +₹442.6 L, MENS +₹219.7 L vs BIS. The "Through Portal" column sent predates the 15:20 regeneration (₹216.7 L lower on these departments). Workbook: "Manual vs Portal - step breakdown.xlsx".

### BIS: a browser showing an older copy of its iteration says so, with a Load button
- **Asked (user):** "load iteration 4 in my browser and fix it" (their Chrome showed "Iteration 4 · 14 Oct, 3:19 pm" in the picker but its own older plan: Rs.431.9 Cr held on AOP, nothing locked - the saved Iteration 4 is Rs.430.4 Cr with the three divisions locked; a Save there would have made an Iteration 5 and sent it to Sales Plan).
- Claude in Chrome was not connected, so the user's browser could not be driven. Fix for every browser instead: on open, after the shared version list arrives, BIS compares the plan on screen with the version it says it came from - each division's plan total (to Rs.0.01 Cr) and the division locks (not the raw inputs, which page load seeds for inactive departments) - and when they differ shows a bar: what is on screen vs saved, "Load the saved <version>" (BIS's own Load, with its confirm) or "Keep this screen". Nothing changes until clicked.
- Tested: a clean Iteration 4 shows no bar; a screen re-balanced onto AOP and kept only in that browser (Rs.431.87 Cr, no lock) shows it, and Load brings back Rs.430.45 Cr with the three divisions locked; the saved Iteration 4 in the database untouched.

### BIS Planner's columns (and group growth %) on the Buyer's Plan LY
- **Asked (user):** "fix planner's output too" (grand total: Planner Value Rs.431.9 Cr but Planner Gr% +11.7%).
- Planner Gr% on a division header / the grand total divided by the active departments' LY only (Rs.431.9 Cr vs Rs.386.7 Cr = +11.7%); the Buyer's Plan's LY also carries the inactive departments' LY at a plan of 0. New `_offLY(row, mi)` adds that LY on division / grand rows - used by Planner Gr% / Planner Value (`_plannerRowAgg`), Block Growth% and the monthly growth cells (`_effGrowth`), and their hovers (`_blockWhy`, `_plannerWhy`, which now names the inactive LY). Departments and attributes unchanged.
- Iteration 4: Planner Gr% grand +11.07% (= Rs.431.87 Cr AOP on Rs.388.84 Cr LY); per division the planner's LY = the Buyer's Plan's LY, and Block Growth% = plan vs LY exactly (MENS +10.42%, LADIES +11.59%, KIDS +10.21%, total +10.70%). Same on Buyer's Plan and Attribute Summary.

### Home Saved plans: one squeezed tile (the first version) + a dropdown layer of the later iterations
- **Asked (user):** "keep ver 1 and squeeze the tiles and give a layer where the versions open afterwards on clicking like a dropdown with a small gist".
- One compact tile for the first version (FIRST / OPEN tags, saved time, gist: TY · LY · growth on one line, how far the live plan has moved since; View, Compare…). "n later iterations ▾" opens a dropdown layer under it - newest first (LATEST tag), each with the same small gist and View / Compare…; closes on an outside click or Esc.

### Home: Live plan tile removed from Saved plans
- **Asked (user):** "remove live plan". Saved plans shows only the saved iterations ("No saved plans yet." when none); each tile still says how far the live plan has moved since it was saved, and Compare can still pick the live plan.

### BIS reports = the Buyer's Plan (latest iteration)
- **Asked (user):** "patch the rest of the modules to buyer's plan's latest iteration. they all should display the same output as highlighted in the buyer's plan as per the respective nomenclature and hierarchy specified."
- Found on Iteration 4: plan ₹430.4 Cr everywhere, but LY ₹388.8 Cr (+10.7%) on Buyer's Plan / Department Summary vs ₹386.7 Cr (+11.3%) on Division / Attribute Summary - those two left the inactive departments' LY out; Division Summary also left a department with no growth typed out of TY (the Buyer's Plan plans it at LY); Inactive Depts showed LY x the department's growth though its plan is 0.
- Division Summary and Attribute Summary now follow the Buyer's Plan's rules (buildRows_dept): an inactive department's LY counts in its division with a plan of 0, no growth typed = plan at LY, Attribute contrib against the division's active LY. Inactive Depts shows plan 0.
- Checked on Iteration 4: Division and Attribute Summary = Buyer's Plan for every division x month and the grand total, LY and plan (0 differences at 1e-6): LY ₹388.84 Cr, plan ₹430.45 Cr, +10.7%; Inactive Depts 60 departments, plan 0.

### Sales Plan iterations: header picker (as BIS's) + Saved plans tiles on Home
- **Asked (user):** "how to save plan iterations and give me the same features as this button in similar fashion, and i want the saved plans to be highlighted here as a tile so that i can easily view the plan and compare it with the new iteration if reauired".
- Top bar, every page: plan iteration picker - Live plan / each saved iteration ("name · date") - picking one opens it on Final Results; then 💾 Save to the iteration in use, ⧉ Save as new iteration…, ✎ Rename a version…, ✕ Remove an iteration… (`components/VersionPicker.jsx`).
- Remove (`POST /plan-versions/remove`): soft - hidden from every list, its file and index line kept (marked removed); the first version can't be removed (like BIS's Original).
- Home: "Saved plans" tiles - the live plan + every iteration (newest first): TY, LY, growth, how far the live plan has moved since, OPEN tag on the one being viewed; View (opens it on Final Results), Compare… ("What changed", now with both sides pickable - any iteration or the live plan).
- One shared module (`planVersion.js`) keeps the picker, Final Results' version bar and the tiles in step ('sp-version' / 'sp-versions' events). Save as defaults to "Iteration n".

### Reconciliation check-up: progress bar with elapsed and remaining time
- **Asked (user):** "give me a progress bar, elapsed time and remaining time true to the progress bar".
- The check-up and Rectify mark each step as they reach it (`plan_checkup._prog_mark`); `GET /reconciliation/checkup/progress` -> step i of n, elapsed, remaining, %. Remaining = what each step took last time (`backend/checkup_timing.json`, git-ignored; rough defaults until the first run) plus the current step's left-over; the bar = elapsed / (elapsed + remaining), so bar and times agree. Steps - check: reading the plan and versions / Calendar, AOP, BIS and season checks / building the trees / MRP, display and qty checks; Rectify adds department plan / MRP Cont % (re-apportionment source only) / Display Type run / validation / Qty run in front. The page polls every 0.5 s while it runs. A cached result (nothing changed) opens instantly with no bar.

### MRP split and ASPs from "for ASP MAMJ 2.xlsx"; BIS Iteration 4 = the buyers' growth sheet
- **Asked (user):** "make the mrp changes and everything related to MRP and its respective ASP as per this file. Where plan is 0 it should reflect 0 and take thier respective ASPs"; and (BIS) "import this as the buyer's input in bis in iteration 4 and update the iteration 4" - "bvhvh remove it dont consider this. Keep the rest department's working as is just replace the Buyer's input"; "LW_U_CORD SETS is a new department ... keep its respective new department ref intact".
- BIS Iteration 4: the pasted DEPARTMENT / FINAL GROWTH % (bvhvh dropped) imported Exact as typed (Plan tools · Import block growth %) - 113 departments set, 44 inactive left alone, 19 names not in BIS left out (LW_U_CORD SETS among them: its new-department set-up - ref L_EW_KURTI SET, 10% - untouched), the three divisions locked; saved INTO Iteration 4 (in place, though the total moved 1.42 Cr) and sent to Sales Plan (944 rows). Totals KIDS 133.22 / LADIES 128.17 / MENS 169.07 Cr vs AOP 136.42 / 128.15 / 167.30. Version list backup `SalesPlan/backend/backups/bis_plan_versions.before-iter4-import.json`.
- MRP Cont % from the file: company level, each department x NEW MRP x fortnight's share of the department's VAL (all clusters, articles, display types) - 114 departments, 622 bands, 29 at 0 (e.g. L_EW_SAREE_FNCY 3999 / 4599 / 5599); source switched to the buyers' file. `mrp_plan_engine._load`: with the file picked, departments it doesn't cover keep the re-apportioned split (110 of 224) - file-only had left them with no MRP split.
- ASP master: the file priced on NEW MRP x NEW DISPLAY TYPE; its values replace the master's (48 replaced, 42 rows added), periods the file leaves empty keep the master's. The 29 zero-plan bands have no value or pieces in the file (nor in the master), so no ASP - their plan and qty are 0. Backup `backups/dt_asp.before-file2-mrp-14Oct2026.json`.
- Re-run: Display Type 371,776 rows (0 errors), Qty: every projected value has a qty (₹52,667.89 L, 15,682,849 pieces; was ₹1,365 L without an ASP). Check-up: every check passes - the MRP source check now reads "the buyers' file (its departments) + the re-apportioned LY sales (the rest)" and checks every file department x fortnight adds to 100% (or 0) instead of failing whenever the file is picked.

### Division Plan: "Compare with" shows its comparison where you pick it
- **Asked (user):** "doesnt work" (Division Plan header bar: Compare with / Export CSV / Data).
- The compare request worked (Version 1, publish 32: KIDS 133.11 / LADIES 124.80 / MENS 162.99 Cr), but the comparison table rendered under the Store / Cluster breakdown, ~1,550 px down, so picking a version looked like nothing happened. It now sits right under the bar, with "Loading that version…" while it fetches.
- Export CSV frees its download link a second after the click (freed at once, some browsers dropped the file); the bar's text keeps its width and the buttons wrap below it on narrow screens.

### Attr Correction: a failed load no longer reads as "the plan has no months"
- **Asked (user):** "yes look into the attribute data issue" ("No attribute data for KIDS - the saved department plan has no plan months yet").
- The saved plan is fine (Mar-Jun'27, 148 SSG stores) and the engine's preview returns KIDS / LADIES / MENS attribute data in 1.6 s. The message came from the test copy of the app, which didn't load the Attr Correction engine: the page hid the failed request (404) and showed the "no plan months" note with a "Generate the department plan" button - the same would show on live during an 8010 restart or after a sign-out, and the button would regenerate the real base plan.
- The page now shows "Could not load the attribute data" with the reason (signed out / server restarting / the server's message) and a Retry button; the Generate note stays for a plan that really has no months. Test copy (`sp_sandbox.py`) now loads the Attr Correction engine, its writes going to the scratchpad.

### Attr / Base Correction: no longer Store-only
- **Asked (user):** "remove this from store only to general" (the "store only" tag on Attr / Base Correction in Cluster view).
- Both run in Store and Cluster view: the sidebar rows are plain links with their on/off switch, their pages open in either view, Growth Matrix's "What next?" offers them in either view. They still correct the store-level plan; Cluster view shows it rolled up. `ClusterOff` removed; the switched-off page note is now `components/EngineGate.jsx`.

### Optional engines: on/off switch (opted out by default)
- **Asked (user):** "for optional engines give a toggle for the user so the user can activate and deactive the engine if it is to be used"; then "toggles missing from attr correction and base correction and toggles not working they are static - they should active - inactive the optional engine, opted out is their default".
- Sidebar: Attr Correction, Base Correction, PW/W Deviation and SOR Deviation each have a switch on their row (replaces the "opt" tag; Attr / Base keep it in Cluster view too). Off = the row is greyed and struck through, its page says "switched off" with a Switch on button, Growth Matrix's "What next?" offers only switched-on corrections (none on → Generate Base Plan goes straight to Final Results), MRP Plan Output drops it from the step bar and the "Apply Deviations?" prompt (both off → no prompt).
- Backend `engines/engine_switch.py` (state in `backend/engine_switches.json`, git-ignored; **default all off**); `GET /api/planning/final-results/engines`, `PUT /engines/{key}` `{on}`. Every plan reader (Final Results / grain trees / reconciliation, MRP plan, Article Name, Display Type, Base Correction's source, the base-plan auto-refresh) skips a switched-off correction's plan file - the file stays on disk, so switching back on brings it back as it was.
- "Static" toggles: 8010 was serving the new screens on the old backend (no switch endpoint) - restarted.

### Display Type page latency; Home card live; reconciliation issues report (one file)
- **Asked (user):** "fix the display type page latency too"; "fix this too" (Home: Display Type Plan "Coming soon"); "need a download excel button to check on such issues higlighted in reco ... or give a 1 button to download the report so that all issues can be addressed at one go ... in different spreadsheets in 1 files".
- Display Type: `status` reads the run times from the files' save times (it parsed the 153 MB run + 198 MB Qty files on every page open); the page no longer downloads them - the Qty tab asks `GET /display-type/qty-view?month=&store=&division=&dept=` for one slice (up to 500 rows, largest first, totals of every row inside the filters, the filter choices), served from the Qty run kept as a table in memory and in `dt_qty_result.view.pkl` (per file version). Page status 0.01 s, Qty tab 0.05-0.07 s / ~160 KB (3.3 s the first time after a restart) instead of ~350 MB.
- Home: Display Type Plan card active, opens the page, describes the Table / Non-Table split with ASP and qty.
- Reconciliation: "⬇ Issues report" - one Excel: Summary (failures first, fix, link to each sheet), Versions, one sheet per failing / flagged check with every row it found (up to 20,000 per check; the page shows the first 300), then the information tables (i - ...). Today: Qty - no ASP (185 rows) + 4 information sheets.
- .gitignore: `SalesPlan/backend/*.pkl`, `SalesPlan/backend/backups/`.

### ASP master kept in memory
- **Asked (user):** "keep the ASP masters in cache donot parse on every run".
- `display_type_engine.load_asp()`: dt_asp.json is parsed once per file version and kept; Import / Add missing write the file, so the next read takes the new one. The Qty run, the ASP preview, status, export / template, fill and the check-up (versions, Qty check, Rectify) all read it from there. Check-up results unchanged.

### Reconciliation check-up: latency
- **Asked (user):** "fix the latency issue in this module" (the check-up and the 8-decimal table sat on "Checking…").
- The page opens on the last check-up while nothing it reads has changed (`plan_checkup.checkup`: plan / stamp / ASP / Display Type run / Qty / MRP Cont % / New Departments / Department Master / season file times, the re-apportionment key, the versions); "Check again" (`?fresh=1`), Rectify and Sign off check anew. 8010 runs it in the background at start, after the trees.
- The MRP-mix check reads the re-apportioned LY table kept on disk (`_display_ly.pkl`, now with the signed values - returns netted, as the MRP Cont % is made) instead of re-running the re-apportionment (32 s cold); the version names (AOP publish, BIS save, Calendar snapshot - database reads) are kept a minute; the Display Type / Qty run times come from the files' save times instead of loading the 153 MB / 198 MB files; the run's totals are read once per file version.
- Timings: cold 55 s → 16 s (in the background at start), page open 6 s → instant, Check again 6 s → 1.3 s; every check's result unchanged.

### ASP fallback: the other display type's ASP; reconciliation re-run
- **Asked (user):** "use the other display type ASP as fallback and rerun reco".
- `display_type_engine.asp_lookup`: a department × MRP × display type × month with no ASP takes the same department × MRP × month's ASP on the other display type (TABLE ↔ NON_TABLE). Used by the Qty run and the check-up; the check-up says how much rests on the fallback.
- Re-run (Display Type run 0 errors / 0 warnings, Qty, check-up): every check passes except Qty - ₹50,118.74 L of ₹51,484.13 L has a qty (14,741,485 pieces), ₹1,759.89 L of it on the fallback; ₹1,365.39 L still has no ASP (₹1,315.8 L MRP in neither file, e.g. MU_SEMI CASUAL SHIRT F/S 649 TABLE ₹264.2 L, L_EW_SAREE_FNCY 3999 ₹191.5 L; ₹26.4 L department not in the files; ₹23.1 L no pieces that month). ASP coverage REGULAR 96.7%, SUMMER 99.3%, OCCASIONAL 85.6%.

### MAMJ: winter / pre-winter off, Occasional on their LY MRPs, ASP filled from file 2, new-department preset check; reconciliation re-run
- **Asked (user):** "MAKE WINTER/PREWINTER INACTIVE FOR MAMJ. TAKE THIS FILE ADD THE ASPS FROM THIS FILE FOR MISSING ENTRIES AND RERUN RECONCILIATION" (for ASP MAMJ 2.xlsx); "also add a check that the new department - ref department ratio is maintained as per the preset at BIS"; "for occasional departments go with the last year mrp and thier cont % the inputs for occasinoal mrp inputs were not there with us so yes intiatie this step make the plan wherever missing and update the reco".
- Winter / pre-winter: the 62 PREWINTER / LT WINTER / HVY WINTER departments set inactive in the Department Master (backup `SalesPlan/backend/backups/department_state.before-winter-off-14Oct2026.json`). The plan engine's "BIS growth keeps a department planned" rule no longer re-activates a department the master has inactive while its attribute is off season (`plan_checkup.season`); the "sync from Buyer's Input" button keeps them inactive too. Regenerated plan: winter departments carry their LY with plan 0; like-for-like stays on AOP (12 / 12).
- Departments the MRP master doesn't cover (the 12 Occasional ones): every Department × Display × MRP they sold LY is listed to itself (`mrp_reapportionment_engine._with_ly_departments`, KIDS / LADIES / MENS Department Master only, blank displays stay Unmapped) - so their MRP Cont % is their own LY MRP mix and their Table / Non-Table split their LY display mix, in the run, the shares, Before → After, the display split and the check-up. MRP Cont % rebuilt: 224 departments; every in-season department split (Occasional 100%).
- ASP: "Add missing ↑" on the Display Type ASP card (`POST /display-type/import/asp?mode=fill`, `fill_missing`): another file only adds Department × MRP × Display Type rows / periods the ASP in use lacks - nothing is overwritten. A file with NEW MRP / NEW DISPLAY TYPE columns is priced on them directly. for ASP MAMJ 2.xlsx: 653 rows, 7 added (backup `backups/dt_asp.before-fill-file2-14Oct2026.json`).
- Check-up: "Store × Month: new department = its preset % of the reference department" (New Departments preset; 5,136 store-months, all exact) plus a per-new-department summary (preset vs actual %).
- Display Type run skips inactive departments (441,632 rows, was 892,736 with the zero rows).
- Re-run: plan → MRP Cont % → Display Type run (0 errors, 0 warnings) → Qty → check-up: every check passes except Qty - ₹3,125.28 L of ₹51,484.13 L in-season plan has no ASP in either file (₹1,752.3 L the files price that MRP only on the other display type, ₹1,315.8 L MRP in neither file, ₹30.7 L no pieces that month, ₹26.4 L department not in the files); ASP coverage REGULAR 94.8%, SUMMER 93.9%, OCCASIONAL 85.6%.

### Check-up: season-aware attribute checks (Winter / PreWinter left out for MAMJ)
- **Asked (user):** "if the attributes are Winter or PReWinter then they should be avoided as neither they have a Buyer's input so they donot have a plan so they can be avoided, check for SOR only since we are making for MAMJ. Suggest me an auto check for attributes and its respective checks similar to this."
- Season rule: attributes in season per plan month - default Mar–Jun = SUMMER, OCCASIONAL, REGULAR; `SalesPlan/backend/season_attributes.json` overrides / adds months ({"Jul": [...], ...}); a month with no rule excludes nothing.
- New stage "Attributes (season)": the season table (per attribute: in / off, departments planned, LY / TY, departments with BIS growth, MRP split %, ASP coverage %); off-season departments carrying a plan (your input); in-season departments with BIS growth for every plan month. The MRP-split check and the Qty check now count in-season departments only (the attribute shown per row; the off-season amount named in the note).
- Today: in-season REGULAR 58 departments / SUMMER 46 / OCCASIONAL 12 - all with BIS growth; REGULAR and SUMMER 100% MRP-split, ASP coverage 94.4% / 93.9%; OCCASIONAL 0% split - its 12 departments (sarees, fancy frocks, indo-western, ME_BLAZER S/L, ME_KURTA PYJAMA; ₹2,554.40 L) are not in the MRP master → the MRP-split check fails on them. Off season: PREWINTER 16, LT WINTER 26, HVY WINTER 20 departments carry ₹220.58 L of plan (BIS gives them growth and the Department Master has them active) - listed as a warning, left out of the MRP / qty checks.

### Display Type ASP: the planners' file carried onto the new MRPs through the MRP master
- **Asked (user):** "carry the ASP onto the new MRPs through the master".
- Import of the raw VAL / QTY file now runs every row through the MRP Re-apportionment's own rule (`_redistribute`, master in use): a listed old MRP moves whole to its new MRP, a discontinued one splits to the nearest listed MRP below / above (Summer 60/40, others 40/60, by ATTRIBUTE-1); value and pieces split alike, so a new MRP's ASP = the piece-weighted mix of the old MRPs it took. An MRP the master doesn't list is treated as the sales are (listed to itself when it is a new MRP there, else discontinued); a Department × Display the master doesn't cover keeps its own MRPs. `display_type_engine._onto_new_mrps`.
- Re-imported live (for ASP MAMJ.xlsx): 604 rows on the new MRPs (4,914 moved whole, 12 split parts; ₹4,677.6 L of ₹91,034.7 L file value kept on its own MRP - Department × Display not in the master). Previous ASP kept in `SalesPlan/backend/backups/dt_asp.before-new-mrps-14Oct2026.json`; converted file `Downloads/for ASP MAMJ - ASP on new MRPs.xlsx`.
- Check-up Qty: projected value with no ASP ₹43,181.61 L → ₹2,847.97 L (₹45,861.18 L of ₹48,709.15 L now has a qty, 13,868,246 pieces). Left (88 rows): ₹1,406.9 L the file prices that MRP only on the other display type, ₹1,384.5 L a new MRP no old MRP of the file maps to, ₹30.4 L no pieces that month, ₹26.1 L departments not in the file.

### Reconciliation: full check-up - plan tied back to Calendar, AOP, BIS, the re-apportionment and the ASP master; Rectify and Sign off
- **Asked (user):** "in this stage i want a full check up from Calendar APP where the sales are being brought in ... aligned with AOP forecast (version name) and BIS (version Name) on what all levels - Div/Dep/MRP/UDF. Separate checks for if the sales output is being generated on Re-apportioned MRP sales and the sales plan is all the way backwards compatible and checked and forward checked too. Qtys should be there for all values which are projected ... validated at your end and then signed off otherwise there should be a button which rectifies by churning the whole system again ... fast and accurate".
- `engines/plan_checkup.py`; `GET /api/planning/reconciliation/checkup`, `POST /checkup/rectify`, `POST /checkup/signoff`, `GET /checkup/export`; the panel on top of Reconciliation (`components/CheckUp.jsx`). Versions shown: Calendar snapshot time, AOP version + publish, live BIS save time + last saved BIS version, plan file, MRP Cont % run, ASP master, Display Type / Qty runs.
- Checks (₹0.10 tolerance on source tie-outs): Calendar → LY (other stores = Calendar reindexed; like-for-like = AOP version's LY base; department mix = Calendar's; chain gap as info), AOP → TY (like-for-like division × month = AOP; built on the publish BIS plans on), BIS → TY (growth in the plan = BIS growth in use; every like-for-like TY = LY/2 × BIS P1/P2 × one division-month factor, new departments = their % of the reference; plan on today's inputs), MRP (Cont % = latest re-apportionment on the master in use and = its LY mix; department TY / LY = Σ MRPs; departments with no split), UDF (MRP = Σ display types, both ways; display mix fallbacks; Display Type run = the tree), Qty (every projected department × MRP × display × month has an ASP; the gaps listed with the reason).
- On today's data every tie-out passes (e.g. 141,488 department LY cells = Calendar mix, 155,914 like-for-like TY cells on BIS × factor, 2,245 MRP shares = re-apportioned mix, Display Type run = tree on 4,608 cells); the one fail is the ASP master: ₹43,181.61 L of ₹48,709.15 L projected has no ASP (the file is on the old MRPs); warning: 74 departments (₹2,774.98 L) with no MRP split. ~5 s warm.
- Rectify re-runs the chain (saved plan on today's inputs unless a correction step is applied, MRP Cont % from the master in use, Display Type run + validation, Qty run when an ASP is imported) and checks again; inputs are never changed. Sign off only when nothing fails; recorded in `SalesPlan/backend/checkup_signoff.json` with the versions - shown as outdated when a source changes.
- Qty run: "missing ASP" now counts only projected values (it counted display types with no plan too).

### Display Type Plan: ASP import / export at company level (template by default)
- **Asked (user):** "import this and calculate the ASP for P1 P2 and month wise ASPs too and convert the file like that, also remove the extras like sales and qty in the import file so that the preview is all about ASP on Company level. Make the template default and start the import and export functionality in UDF page" (file: for ASP MAMJ.xlsx).
- Template (Export gives it, Import reads it): Division | Department | MRP | Display Type | Mar'27 P1 | Mar'27 P2 | Mar'27 | … (₹ per piece). Import also takes the planners' raw file (CLUSTER TAG | CLUSTER | ATTRIBUTE-1 | DEPARTMENT | ARTICLE NAME | MRP | DISPLAY TYPE | <Mon>'yy P1/P2 VAL (₹ L) / QTY) and converts it: every cluster, tag, attribute and article added up per Department × MRP × Display Type; P1 / P2 ASP = VAL × 1e5 ÷ QTY; the month = (P1 + P2 VAL) ÷ (P1 + P2 QTY). Sales and quantity are not kept. Division comes from the plan. ASP matches on Department × MRP × Display Type.
- Display Type page: "ASP · company level" card - Import ↑, Export ↓ (blank Template ↓ on the plan's Department × MRP × Display Type when none is imported), and the ASP preview with one multi-select filter per field (Division, Department, MRP, Display type), month columns shaded. `GET /display-type/asp`, `GET /display-type/export/asp`, `asp_from_frame`.
- Imported for real: for ASP MAMJ.xlsx → 659 company rows, Mar–Jul'27 (17,793 file rows; all 114 departments known). Converted file: `Downloads/for ASP MAMJ - ASP company level.xlsx`. Round trip export → import identical.
- Found, not changed: the file's ASP is ~5% above MRP (median ASP / MRP 1.053, e.g. MRP 299 → ₹324.5) - VAL likely includes tax; and the file is on the old MRPs, so a Qty run finds no ASP for ₹36,170 L of the ₹40,790 L SSG plan (₹34,305 L MRP not in the file, ₹1,843 L only the other display type, ₹21.9 L department not in the file).

### Display Type Plan: Table / Non-Table % from the re-apportioned LY sales; the MRP plan broken by display type
- **Asked (user):** "i will give the ASP file in an imported format everytime. Cont % should be according the Re-apportioned MRPs and their respective Display types % as per LY sales. the MRP plan should break and the it should be highlighted as per that only".
- No contributions upload any more (`POST /display-type/import/contributions` and `dt_contributions.json` gone). Each store x department x new MRP x plan month splits by its own LY sales on that MRP by display type (MRP Re-apportionment's after side on the master in use, Unmapped left out). Fallbacks, first with sales: the store's mix over all months → the chain's that month → the chain's over all months → the department's → a new department takes its reference department's mix (as it takes its MRP split; LW_U_CORD SETS → L_EW_KURTI SET). `display_type_engine.display_shares`.
- Run Plan (SSG stores, as before): 340,992 rows - 293,302 on the store's own month mix, 23,514 store all-months, 16,771 chain month, 2,669 chain, 4,736 reference; Table + Non-Table = the MRP plan in every row; Validate 0 errors, gate open (1,761 warnings = departments with no MRP split, as before).
- ASP stays an import, every time; the match ignores case / spacing / 749 vs 749.0 / Table vs TABLE / Non-Table vs NON_TABLE.
- The ₹L Plan tab is now the department view's tree with a Display type level (`/api/planning/grain/display-view/*`, all stores): Division › Department › MRP › Display type, filters, ⓘ pop-up (which LY mix each rupee used, check vs the MRP plan), Month / P1-P2, Export Excel. Ties to the MRP tree at every level (LY ₹46,333.86 L / TY ₹51,484.13 L); by display TABLE ₹13,162.5 L, NON_TABLE ₹35,546.7 L, not split ₹2,775.0 L (no MRP split / not planned). The Store / Cluster panel is replaced by it; Validate / Qty tabs stay.
- The LY table is kept on disk (`Output/_display_ly.pkl`, keyed on the re-apportionment's inputs): first open after a restart 58 s → 8 s; 8010 builds it at start.
- Status: "MRP Plan" now ticks off the split in use (it read the old mrp_plan.json).

### Sales Plan route: chosen at the end of Final Results, opens the module
- **Asked (user):** "this route should be a prompt which redirects to Article module or MRP module after the department plan is done and reviewed, it should be a redirection for the user to click on" and "After the toggle is promote to MRP and the MRP route is clicked from Article Name the landing page should be Buyer's input instead of the direct output page".
- Final Results ends with "Department plan reviewed? Take it to the next stage": MRP plan → / Article Name plan → - saves the route and opens that module's Buyer's Input. The branch pages show which branch is in use with a link back to it (no toggle there). Article Name's after-promote button opens MRP Plan · Buyer's Input.
- MRP Plan Output: a proxy error page (8010 restarting) is retried with "The planning server is restarting - trying again…" instead of "Unexpected token '<'".

### MRP Cont % rebuilt from the master in use (data, no code change)
- **Asked (user):** "rebuild the mrp cont % from the master in use".
- `POST /mrp-reapportionment/shares/rebuild` at 11:27 on mrp master.xlsx, actual LY sales Mar-Jun 2026; every check passed. 104 departments, 568 bands, every department x period 100%. 50 departments' shares moved, mostly from the "a sold MRP that is itself a new MRP stays listed" fix (ML_JEANS 749 Mar'27 P1 4.55% → 5.07%, 829 3.75% → 3.24%). MRP Output, the MRP tree, Display Type and Reconciliation read it at once.
- The previous file is kept in `Output/Backups/_reapp_shares.before-rebuild-14Oct2026.json`.

### Sales Plan: faster Hierarchy views (Final Results, MRP Plan Output, version bar)
- **Asked (user):** "decrease the latency for such views" (Final Results on P1 / P2 stuck on "Loading…" / "Loading versions…").
- P1 / P2 tree: derived from the month index with numpy instead of a second pass over every cell - first P1 / P2 open 1.0 s → 0.04 s.
- MRP tree: built once by fortnight, the month view read off it (P1 / P2 switch 3.6 s → 0.03 s); the stores' re-apportioned LY mix it needs is kept on disk (`MRP Merging Engine/.../Output/_store_mix.pkl`, keyed on the sales file, Calendar snapshot stamps, basis and master), so after a restart the tree is ready in ~4 s instead of re-running the re-apportionment (35.5 s → 3.9 s cold).
- Every tree click: the cached re-apportionment is checked on a key (`compare_key`) before the LY sales table is copied - repeat MRP clicks 0.26 s → 0.03 s; the Calendar snapshot stamps are read at most every 30 s.
- Version bar: the live plan's totals kept per plan instead of walked on every page open (1.7 s → 0.02 s).
- 8010 start warms the department tree (month and P1 / P2), the version totals and the MRP tree, in that order.
- Same numbers: LY ₹46,333.86 L / TY ₹51,484.13 L on both trees, every division / cluster / store / month, by month and P1 / P2; P1 + P2 = the month.

### Sales Plan: Month / P1-P2 switch and Excel export on the Hierarchy view; MRP Plan Output on the same tree
- **Asked (user):** "i want a view with toggle for month wise or P1 P2, which is also availble in excel download too keeping the same view availbe. P1 P2 is 15 day interval for the month" and "merge all the views similarly to the department view which is the final design".
- Final Results: a Month | P1 / P2 switch (P1 = days 1-15, P2 = 16th to month end). P1 / P2 = the plan's own TY P1 / TY P2; LY = half of each month (as the plan engine grows it, LY half x BIS P1 / P2 growth). P1 + P2 = the month to the paisa (MENS, all months, LY and TY). The month filter follows the switch; the ⓘ pop-up shows the fortnight's numbers on top of the month's working. `?period=month|half` on `/api/planning/grain/hierarchy`, `/hierarchy-options`, `/explain`.
- Today's plan has BIS P1 growth = P2 growth in every cell (0 of 414,304 differ), so P1 = P2 until BIS gives them different growth.
- **Export Excel ↓** on every Hierarchy tree (Final Results, MRP Plan Output, Article Name Plan Output, Re-apportionment Before → After): the view as on screen - Rows, filters, version, month or P1 / P2 - every branch opened in the page's order, indented with Excel +/- grouping, one column per Rows field, LY / TY / Growth % / Cont %, Grand Total, an About sheet (view, filters, source, time). `grain_view.tree_xlsx`; `GET .../hierarchy-export` on grain, grain/mrp-view, art-nm and mrp-reapportionment.
- MRP Plan Output: the division tabs, P1/P2 matrix and the Store / Cluster panel are replaced by the department view's tree with an MRP level (`/api/planning/grain/mrp-view/*`): Cluster, Store, Store type, Division, Attribute, Department, MRP, Month; filters, ⓘ pop-up, Month / P1-P2, Export. TY = each store x department x fortnight's plan x the department's MRP share of that fortnight (effective_shares - the same split MRP Output had); LY = the store's department LY x that store's own re-apportioned LY mix over the new MRPs. Departments without a split sit under "No MRP split" and inactive departments' LY under "Not planned", so every level ties to Final Results: LY ₹46,333.86 L / TY ₹51,484.13 L, every division, cluster, store and month, by month and by P1 / P2. Step bar, route banner, Deviations and the CSV export stay. Built at 8010 start (about 40 s cold).
- Not changed: Display Type Plan (no run saved yet to show).

### MRP Re-apportionment: a sold MRP that is itself a new MRP stays listed
- **Asked (user):** "shouldnt this be listed instead of discontinued, as it is LY = TY MRPs matching" (ML_JEANS · NON_TABLE · 749: the file lists 699 -> 749 but not 749 itself, so 749 was discontinued and split 40% to 749 / 60% to 829).
- `_expand_listed`: an MRP sold LY that the file doesn't list but that is one of the new MRPs of the same Department x Display is listed to itself (100%), no longer split. ML_JEANS · NON_TABLE · 749: ₹14.9 L now stays on 749 (was ₹5.9 L on 749 + ₹8.9 L to 829).
- The saved MRP Cont % shares predate this: MRP Plan · Buyer's Input → "Rebuild from the master in use" (or a Run) brings it into the MRP plan.

### Sales Plan MRP Plan Buyer's Input: folder-sync panel removed
- **Asked (user):** "remove all this" (the Source file card, Sync from Folder, How it works, Expected file format, Divisions expected).
- Gone from the page; the buyers' file is synced from a small "Sync the buyers' file" button on the "Where it comes from" card (same `POST /mrp-plan/sync`, same folder). Header text no longer says the page must always be synced from the file.

### Sales Plan MRP Plan: MRP Cont % from the re-apportioned sales by default; the buyers' file optional
- **Asked (user):** "i want the user to be asked to either drop a file for cont % or by default the cont % for the re-apportioned sales will be taken, this is an optional scenario now" and "upon running the new re-apportionment how will the user get its benefits ... how can i point to the latest version of the re-apportionment run in the engine, find a way to easily carry this out".
- Every MRP re-apportionment run whose checks pass saves its MRP shares (`Output/_reapp_shares.json`: per division x department x new MRP, each month's re-apportioned LY sales as % of the department, on its plan period - same % in P1 and P2; Unmapped left out). `POST /api/planning/mrp-reapportionment/shares/rebuild` builds them from the master in use without a full run (same rule and checks); `GET /shares-status`.
- MRP Plan reads them by default (`mrp_plan_engine.get_source()` = "reapp", `backend/mrp_source.json`; `GET/POST /api/planning/mrp-plan/source`): a department the run doesn't cover keeps the buyers' file share if one is synced; picking "Buyer's MRP Cont % file" uses the file as before. Buyer's Input shows the choice, which run is in use (master, basis, months, departments) and Rebuild from the master in use - so the latest run flows into MRP Output, Display Type and Reconciliation by itself.
- Built from the master in use (mrp master.xlsx, imported by the user): 104 departments; MRP Output on them: 576 bands, every department's shares 100% and its bands = its plan (largest difference 0.0000000000002 L); 74 departments (₹2,775 L) are outside the master - no split until the master or a buyers' file covers them.

### STR Forecaster: band table counts department x month; a click shows and highlights the matching months
- **Asked (user):** "i want total month x count instead of focusing on avg for this so that every month's count is there in this table and when upon clicking the data should be populated for that branch only and it should get highlighted wherever it meets the criteria ... if mar, may and june have 60 for a combination they should get highlighted ... instead of avg".
- The table is now "Department × month by band": each department x month counts once in that month's band (MENS / LADIES / KIDS / All, then a row per month under All; All = the sum of the months, e.g. 422 = 110 + 104 + 104 + 104).
- A count opens that division's departments with that band in any month (or in that month, from a month row) - not the 4-month band - with the months shown and every matching month's Band and STR days cells lightly shaded (also in the stores under them). Revert / Clear bring the view back. Then (user: "i wanted the view to be restricted to division remove the light colored months below ... shift the month table to the right of this division table") the division table has MENS / LADIES / KIDS / All only, and a separate "By month (all divisions)" table sits to its right (wraps below on a narrow screen), month labels in full ink.

### STR Forecaster: the detailed Excel ~3x faster to build, instant to download again
- **Asked (user):** "decrease the latency for extracting output in STR forecaster in excel".
- Profiled: pandas' cell-by-cell Excel formatter ~230 s of 5.1 million cells, and the new forward-cover days looping over ~40,000 store x department groups ~90 s. Now the rows go straight to xlsxwriter in streaming mode (`_write_sheet`), and `forward_days` works on whole arrays (proved equal to the per-group `cover_days` on 1,017 random rows, gaps and zero months included). Same four sheets, same values.
- The finished workbook is kept per inputs version x layers x filters (last 4), dropped on any change; the default one (the page's layers, no filters) is built in the background at start and after every change.
- Result: first build 66 s (was ~200 s live), the same download again 0.1 s, a filtered one (MENS) 16.5 s. Read me texts updated for forward cover and the 15-day bands.

### Sales Plan MRP Re-apportionment: the listed-MRPs master format
- **Asked (user):** "i will give the mrp master like this from now on. How about you convert it and give me the output so that it matches the ly sales and follows the existing rules for change" - `mrp master.xlsx`: DEPARTMENT | DISPLAY TYPE | MRP | REVISE MRP, only the MRPs that stay.
- `_load_mapping` reads it (REVISE MRP = the new MRP) and `_expand_listed` adds every MRP the Department x Display sold LY that the file doesn't list as discontinued (new MRP 0), so the rule is unchanged (listed -> revised MRP; discontinued -> nearest listed below / above, 40/60, Summer 60/40; nothing listed -> Unmapped). Old pre-split department names (KB_BERMUDA, KB_T-SHIRT H/S, LW_L_JEGGING, LW_L_PALAZZO, MSE_PYJAMA) are removed - the master runs on the new names only (user: "if you find old names just remove them and generate with new names only"; L_IN_BRA, still a department, stays). Import new version accepts the format; new **Export as read** gives the master as the rule reads it (status, nearest listed below / above, LY sales).
- On the user's file (dry run, the live master not replaced): 600 listed (42 old-name rows removed) + 930 discontinued MRPs, 130 Department x Display, 104 departments; LY ₹44,189.30 L -> ₹44,116.15 L on the new MRPs + ₹73.16 L Unmapped (displays of those departments the file doesn't list); all five post-run checks pass. Outputs in `Output\Previews\` (converted master, full re-apportionment workbook). 7 listed MRPs had no LY sales.

### STR Forecaster: STR days by forward cover; bands every 15 days, 60-120
- **Asked (user):** "If i am standing in Mar i will take the MDQ for the month and will divide the Avg Sales Per Day & Calculate if the MDQ is being able to fulfil with the current month's sales or not, if not i will move forward in months till i have 0 for Mar's MDQ ... introduce +15 interval in between too ... like 60, 75, 90 etc till 120 ... revise the ceiling to being 60 to 120 instead of the earlier 180".
- `str_engine.cover_days` / `forward_days` / `cover_walk`: a month's STR days = its MDQ sold down by that month's planned sales, then the next months', till none is left (a month with no sales lets its days pass; past the last plan month at the last selling rate). Used for every roll-up month, the department editor's store / display-type cells, and the Excel export; LY days the same way on LY sales. The 4-month figure = the months' STR days weighted by their MDQ. The rest unchanged (MDQ, planned qty, seasons, peak-oriented column).
- Band: the nearest 15, kept between 60 and 120 (`BAND_STEP, BAND_MIN, BAND_MAX = 15, 60, 120`; was nearest 30, 60-180), in the engine and the page. The pop-up's STR days row shows the walk (e.g. KI_AP_BABA SUIT HSR H/S Mar'27: MDQ 1,94,210 - Mar sells 84,671 (31 d), Apr 69,248 (30 d), May the last 40,291 in 18.6 d = 79.6 days -> 75; the old MDQ / per-day gave 71.1).
- Result: department bands (4-month) 60: 51, 75: 11, 90: 15, 105: 7, 120: 27. Self-check extended (cover, walk, 15-step band, 120 ceiling).

### Sales Plan MRP Re-apportionment: LY sales from the Calendar app, Actual / Reindexed toggle
- **Asked (user):** "link the sales from the backend sales of the calendar app - keep the reindexed and actual toggle with this".
- The input card is now "LY Sales · Calendar app" with an **Actual / Reindexed** switch (saved on the server, `Output/_sales_basis.json`; `GET/POST /api/planning/mrp-reapportionment/sales-basis`). The Calendar keeps no MRP detail, so the MRP x display x attribute rows still come from the Calendar engine's own data-lake reader; Actual ties them to the Calendar's `actual_dept` snapshot (LY months, as before), Reindexed puts every store x department x month onto the Calendar's reindexed `trend_shifted_dept` figure on the plan months (Mar-Jun 2027), each row keeping its LY share of that store x department (its mix over all the months when that month has none).
- Result: Actual ₹56,646.33 L, 2,45,872 cells, max diff 0; Reindexed ₹55,786.39 L, 2,23,538 cells tie exactly (max diff 0.0 L); ₹111.71 L of reindexed sales have no LY rows at all (new stores / departments) - reported, nothing to split by MRP. The run's validation and all post-run checks pass on both. The run history records the basis; the Before -> After tree rebuilds when it changes. The setting is left on Actual.

### Sales Plan MRP Re-apportionment: Before -> After comparison with the working pop-up
- **Asked (user):** "keep the rules intact, i will give you the master for new listed mrps against the old ones, the engine has to run true to its core working, and should be making a before and after comp for the mrp to easily identify and put all the necessary things in a similar pop up style on click just like the rest of the modules".
- New **Before -> After** tab (no Run needed): the department Final Results tree over the re-apportionment the master in use gives, through the engine's own `_redistribute` (rules untouched - listed -> its new MRP; discontinued -> nearest listed below / above, 40/60, Summer 60/40; one side -> 100%; nothing listed -> Unmapped). Rows Department > Display > MRP (price order) by default, plus Attribute / Division / Store / Month; a filter per field; Before = LY sold at the old MRP, After = on the new MRP structure, Unmapped its own row.
- The ⓘ pop-up per row: the number, the rule, for one MRP where its sales went and what it received (with the master's listed / discontinued and nearest below / above), a table of every old -> new move (attribute, share %, ₹ L), and for departments / displays the check before = after + Unmapped.
- Built at server start and again in the background after a new master is imported (~50 s); `/api/planning/mrp-reapportionment/hierarchy|hierarchy-options|explain|compare-summary`. `HierarchyView` gets configurable column names; grain_view `index_from_frame` + MRP price-order sorting.
- Result on the current master (MRP MASTER 27-04-2026): before ₹41,062.26 L = after ₹40,824.36 L + Unmapped ₹237.90 L exactly; listed ₹39,695.1 L, discontinued ₹1,129.3 L. The existing re-apportionment checks still pass.

### Sales Plan: post-generation check - department sales plan per department x month, AOP per month
- **Asked (user):** "make a check where the post generation of the data it should look if the department sales plan is matching for all departments x months and AOP is correct for all months".
- `art_nm_engine.post_check()` (`/api/planning/art-nm/post-check`), traced from the plan file, not the build: every division x department x month - Article Name plan = department sales plan (a negative cluster / store plan counts as 0, as the plan is built); every division x month - the like-for-like department plan = the AOP publish's division plan, with the all-store plan and the article plan beside it. Two new checks on Article Name Plan Output (they replace the old always-OK "trace" line) and a Post-generation check panel (division x month table; department x month - the ones off, or all). Reconciliation gets the level "Division x Month: like-for-like department plan = AOP" whichever route is in use.
- Result: 648 of 648 department x month cells = department sales plan by cluster and by store (16 by store carry a negative store plan, -0.037 L, at 0); 12 of 12 division x month = AOP (Version 2 - 25 Sept 2026, 43,186.78 L, largest difference 0.000000 L). A ₹1 L nudge to one store is caught (MENS Mar'27 +1.0). Test `test_post_check`.

## 2026-10-13

### Sales Plan Article Name: the plan engine month by month, in-active MC = 0%, new article names on the input %; output page = the department Final Results tree with the working pop-up
- **Asked (user):** "if the input file has an inactive mc then it should be considered 0%"; "Department selection ... ly sales data on cluster/store x dep x art name ... pitted against the input file cont % and deviation ... below 50% ... 50% and max 150%"; "for every month the base ly sales cont % should be multiplied with the deviation ... Resultant should be apportioned to 100% ... multiplied with the AOP resultant of the department engine. Mimic the working pop up for every entry and make similar output page as the department with all features similarly"; "new departments introduced, new article name introduced, and split department introduced should be taken as per the cont % imported".
- **Engine** (`art_nm_engine.shares_for`): per Cluster/Store x Department x month - LY cont % (the article's share of the department's LY), deviation = input % / LY cont % capped 50-150%, resultant = LY cont % x capped, apportioned to 100% and x the department AOP (was one deviation for the whole block). IN-ACTIVE MC (MC TAG, or the article's MC STATUS) counts as 0% (the file's figure kept as "given"; method "In-active MC"). A new article name (in the file, never sold in the chain) takes its input % as it is, the other articles sharing the rest; new and split departments as before. Re-read the MAMJ file under the rule: 3 articles in 2 departments zeroed; 18 cluster departments on the in-active rule.
- **Output page** (Article Name Plan -> Plan Output): the department Final Results tree (`HierarchyView` now reusable: api / fields / store / versions props; grain_view `make_index` / `rows_of` / `values_of` shared) - Rows Department > Article Name > Month by default (Cluster / Store, Store type, Division, Attribute too), a multi-select filter per field with Department first (the department selection), LY (sales engine) / TY (article plan) / Growth % / Cont %, Grand Total, and the ⓘ pop-up on every row (`/art-nm/explain`): the number, growth, Cont %, the department AOP it splits, how it is split, the steps, and for one article the working month by month (LY, LY cont %, input %, deviation, capped, resultant, share %, department AOP, plan; across many clusters/stores the deviation as a range). A five-step strip shows the engine. Checks, Promote and the route bar stay.
- **Fixed:** Plan Output's Export Excel returned the buyers' file (two `/export` routes) - it is `/art-nm/plan-export` now, one row per group x department x article x month with the working.
- Checked on the real plan: articles = department AOP (6,242 of 6,244 cluster cells; 2 negative department plans at 0), caps 13,425 within 50-150%, Final Results unchanged (Grand Total 51,484.1 L). Tests updated + `test_monthly_deviation_inactive_and_new_article`.

### Sales Plan Final Results: versions pick up where you left off, in any session
- **Asked (user):** "if i saved a version here it should stay saved in my next session".
- Saved versions were already kept on the server (`backend/plan_versions/`, Version 1 saved by Admin 17:14 is there); which version was open lived only in the browser. Now the server keeps, per user, the version open and the one Save writes to (`plan_versions/state.json`; `POST /plan-versions/open`; `me` in the list), and the Hierarchy reopens it with its saved layout on the first load - any browser, any PC. Checked by clearing the browser's storage: the page came back on the version and layout last opened.

### Sales Plan: Article Name Buyer's Input = Import / Export; Article Name Plan listed before MRP Plan
- **Asked (user):** "give me an import and export function not this" (the folder sync card), "shift the art name order to precede the mrp plan module".
- Buyer's Input: **Import** (upload, checked before it replaces the file in use) and **Export** - the file in use exactly as imported (`backend/art_nm_cont_source.xlsx`, gitignored; seeded with the MAMJ file already imported), or before the first import a template in the same layout: every plan department x its LY articles, filled with the chain LY Art Nm cont % (178 departments, each 100%; re-imports cleanly). The folder sync (`/sync`, `/sync-status`) is removed.
- A "Not signed in" message instead of an empty page when the 8010 session has ended.
- Sidebar: Article Name Plan now sits above MRP Plan.

### Sales Plan: promote the Article Name plan to the MRP stage
- **Asked (user):** "also give a provision if the art nm plan has to be promoted to mrp planning stage" -> chose "Split it into MRP bands".
- **Promote to MRP stage** (Article Name Plan -> Plan Output; `POST /api/planning/art-nm/promote`): each store / cluster x department x article plan is split over MRP bands by that group's LY (MAMJ) article x MRP mix; old MRPs move to the new structure by the Re-apportionment master's rule (listed -> new MRP; discontinued -> nearest listed below / above, Summer 60/40, others 40/60; not in the master -> as sold). Fallback: the chain's article mix, then the department's. Summed over the groups it is saved as the MRP stage's split (`backend/mrp_promoted.json`, division x department x MRP x P1/P2 %) and sets the route to Article Name.
- While the route is Article Name and a promote exists, `mrp_plan_engine.effective_shares()` returns the promoted split, so MRP Plan Output (banner "promoted from the Article Name plan"), Display Type (Run plan again after a promote), the Store / Cluster MRP panel and Reconciliation (both the article level and the MRP-band level) use it. Switching the route to MRP brings back the buyers' MRP Cont % split.
- The panel shows when, by whom, by which Plan by, how much used each mix, and "promote again" when the file, Plan by or department plan changed since.
- **Result (by store):** 178 departments over 1,252 MRP bands (the buyers' split had 4 departments with none); ₹51,026.6 L on the store's own mix, ₹457.5 L on the chain's article mix; every department's bands = its plan except MW_PULLOVER S/L's -0.006 L month (a negative department plan, nothing to split). Test: `test_promote_split`.

### Sales Plan: Article Name Plan as its own branch beside MRP Plan; saved versions on Final Results
- **Asked (user):** "where is the article name Module in parallel to MRP similar to the Department plan by store or cluster", "the article name should be a MRP counterpart, it should follow the current selected toggle ... think of it as another parallel branch to MRP"; and on Final Results "give me a save button and all tools related to version selection, rename, save as, selection window ... Also add a little know how as to what was changed from the 1st version to this".
- **Article Name Plan** (sidebar, after MRP Plan):
  - *Buyer's Input* (`pages/ArtNmImport.jsx`): Sync from Folder (`SalesPlan\Art NM Cont %`, the newest .xlsx; the buyers' MAMJ file placed there) or Upload; the file in use per department (MC Tag, how it is used, articles, Σ %, check) with a Filters row (Division, Department, MC Tag, Check).
  - *Plan Output* (`components/ArtNmRoute.jsx`): follows the header's Plan by Store / Cluster (its own switch and import button removed); a department with negative store-month plan cells (returns in LY) shows `= AOP*` - its articles there are 0 - instead of `≠ AOP 0.00`. Every department = AOP by store and by cluster.
  - **Sales Plan route** bar on both Plan Outputs (`components/RouteBar.jsx`): MRP / Article Name, saved on the server; MRP Plan Output is the MRP branch only again. With the Article Name route, Reconciliation checks "Cluster/Store x Dept x Month: department AOP = Σ Article Names" (6,242 cells, 0 off by cluster) and lists negative plan cells apart; Display Type says it follows the MRP split (its shares are per MRP).
- **Final Results versions** (`engines/plan_versions.py`, `/api/planning/plan-versions`; `components/PlanVersions.jsx` above the Hierarchy): Save (the live plan + Rows / Filters into the version in use), Save as (new, unique name), Rename, the Versions window (live plan + every version: saved, by, months, TY, growth, history; Open), and What changed (vs Version 1 or any version: plan / LY, divisions, departments planned now / dropped, biggest department moves, plan months, why - BIS saved, base plan regenerated, New departments template - and the layout). An open version is frozen - Hierarchy, filters and ⓘ read it via `?version=`. Files `backend/plan_versions/` (gitignored, ~3.5 MB a version); never deleted. Tests: `engines/test_plan_versions.py`.

### Sales Plan: MRP stage - Article Name route beside the MRP route
- **Asked (user):** "Add A provision toggle if the user wants to go Article Name or MRP route. Follow the MRP route as is", with the Article Name route's rules; then "for new departments and split departments use the imported buyer's cont % at art nm", and the buyers' file `art nm cont % mamj.xlsx` (MC TAG per department).
- **Toggle:** MRP Plan → Plan Output has a Route switch (MRP / Article Name), saved on the server (`backend/mrp_route.json`, default MRP). The MRP route is unchanged.
- **Article Name route** (`engines/art_nm_engine.py`, `/api/planning/art-nm`; page `components/ArtNmRoute.jsx`):
  - LY sales per Cluster or Store (switch) x Department x Article Name x month from the sales engine (lake, LY Mar-Jun 2026); ties to the Calendar department sales (0.0 L).
  - Import the buyers' Art Nm Cont % (one MAMJ % per Department x Article Name; fractions read as %). Deviation = buyer % / the cluster's own LY % of the block, capped 50-150%; new base = LY x capped (LY below 0 counts as 0); apportioned to 100% per Cluster x Department x month and applied to the department plan, adding back exactly.
  - NEW ACTIVE MC and NEW SPLIT MC departments take the buyers' % as it is; a split department is named by its old name in the file, so each part takes it by article tier (EPP, ECO, ...) over its own articles.
  - Fallbacks, each shown as the department's method: no buyer % -> LY mix; store with no LY -> its cluster's mix; no LY here -> buyer %, else the chain LY mix.
  - Checks on the page: file and block vs plan months, 100% per department, LY tie, caps / no negatives, article plan = department AOP per group x department x month, AOP traced to the department plan. Filters row: Cluster/Store, Department, Tag, Method, Check. Excel export: Article Plan, Department Check, Checks.
- **Result (MAMJ, by cluster):** ₹51,484.13 L split over 1,561 cluster x department rows; 6,242 of 6,244 month cells = department AOP; the 2 others are negative department plans (-0.007 L, returns in LY) kept at 0. By store: 123,203 of 123,220.
- Test: `engines/test_art_nm.py`.

### Sales Plan: the department plan at the MRP stage; Filters row on the MRP pages
- **Asked (user):** "add the same filters row to the MRP pages", then "now take the department plan to the MRP stage".
- **MRP stage:**
  - MRP Plan Output splits the live department plan (now self-refreshing) over the buyers' MRP shares (`mrp_plan.json`, Mar-Jun'27).
  - `mrp_plan_engine.effective_shares()`: a NEW department without its own split uses its reference department's split (New departments template). LW_U_CORD SETS, ₹220.7 L, is split as L_EW_KURTI SET over 8 bands; it had vanished from Plan Output.
  - A department the plan has but no split covers is now listed as "NO MRP SPLIT" with its plan unsplit, instead of being dropped.
  - Plan Output, the Store / Cluster MRP panel, Display Type and Reconciliation all use the same shares. Reconciliation lists the no-split departments under "not covered", not as rounding gaps.
- **Result:**
  - ₹51,464.5 of ₹51,484.1 L (99.96%) split to MRP bands; bands = department to 2e-13 L (Reconciliation MRP check: 176 cells, 0 off).
  - 4 departments (₹19.6 L) have no shares in the MRP Cont % file: KI_AP_TOP F/S, KB_BABA SUIT DNM F/S, KI_AP_CASUAL SHIRT F/S, LW_U_T-TOP F/S.
- **Filters row on the MRP pages** (shared `FiltersRow` in `components/ExcelFilter.jsx`):
  - Plan Output: Department + Check (OK / Contrib ≠ 100% / No MRP split / Split from reference). Replaces the search box and the "Contrib ≠ 100%" toggle.
  - Re-apportionment: Department + Display on the MRP groups. Replaces the text filter.
  - SOR Deviation: Attribute + Department, multi-select. Replaces the single-pick pills and select; shown once SOR has data.
  - Buyer's Input has no table, so nothing to filter.
- **Checked in the sandbox:**
  - LADIES Plan Output: CORD SETS split as KURTI SET; Check = No MRP split → LW_U_T-TOP F/S only.
  - Re-apportionment: Display = NON_TABLE → 237 of 284 groups.
  - SOR has no files yet, so it could not be checked on data.

### Sales Plan Master Setup: the same Filters row
- **Asked (user):** "add the same filters row to Master Setup".
- **What changed:** the search box and the folded "Filter by attribute" chips are replaced by a **Filters** row of multi-select dropdowns: **Department**, **Attribute**, **Status** (Active / Inactive), **Source** (Master / Custom).
  - Each reads (All), the value, or (Multiple Items) n, with "showing X of Y" and Clear all.
  - A list shows only the values left by the other filters. Filters clear when the division changes.
- **Checked in the sandbox (KIDS):** Status = Inactive → 31 of 122 (= 122 − 91 active). Ticking both Sources leaves Source at (All).

### Sales Plan Growth Matrix: the same Filters row as Final Results
- **Asked (user):** "add the same filters row to the Growth Matrix".
- **What changed:**
  - The attribute chips and the "All Departments" search box are replaced by a **Filters** row with one multi-select dropdown each for **Department**, **Attribute**, **Status** (Active / Inactive) and **Month** (which month columns show).
  - Each reads (All), the value, or (Multiple Items) n, with "showing X of Y" and Clear all.
  - The ▾ on period headings still filters by growth value and works together with the row. Filters clear when the division changes.
- **Checked in the sandbox (KIDS):**
  - Status = Inactive → 31 of 122 rows, all inactive.
  - Month = Mar + Apr'27 → only those two month columns ("2 months").
  - The Month list = Mar-Jun'27.

### Sales Plan Final Results: one multi-select filter per field
- **Asked (user):** "multi selection filters are required not this slop".
- **Filters row:** a **Filters** row under Rows with one dropdown per field (Cluster, Store, Store type, Division, Attribute, Department, Month), as an Excel PivotTable's report filters.
  - Each shows **(All)**, the one value, or **(Multiple Items) n**, and opens the tick list (Clear Filter From, Search, (Select All), OK / Cancel).
  - All filters apply together. **Clear all** is next to them.
  - A field can be filtered whether it is in Rows or not, and removing it from Rows keeps its filter.
- **Removed:** the single Row Labels dropdown, its Select field box and its sorting. The table heading names the row fields.
- **Checked in the sandbox:** Division = MENS + LADIES and Month = Mar + Apr'27 → Grand Total ₹16,402.2 → ₹18,175.6 L, the server's figure for the same filters.

### Sales Plan: the saved base plan keeps itself current; Hierarchy and Growth Matrix filters as in Excel
- **Asked (user):** "make it more simplistic and more true to thier excel counterparts", then "still showing stale updates".
- **Stale plan:**
  - Final Results, MRP and every later engine read the saved base plan (`final_dept_plan.json`), which changed only on a manual Generate Base Plan, so it lagged behind a BIS save (14:46) or an AOP publish.
  - `dept_sales_engine.refresh_saved_plan()` now runs in the 60-second background loop. It remakes the plan when its inputs change: BIS growth, AOP publish, Department Master, plan months or LY (a hash of `_plan_inputs_key`, kept in `final_dept_plan.inputs.json`, git-ignored).
  - It never runs once a correction step has been used, because a new base plan would wipe it.
  - Final Results shows "made <time> · BIS saved <time>". Division Plan shows "BIS last saved …" and notes that its division totals are held on AOP, so a BIS save shows in departments.
  - **Checked:** the first refresh remade the plan (12.8 s) and the second was a no-op (0.1 s). LFL is still = AOP (43,186.78 L). The 14:46 save changed no department against the plan made before it.
- **Hierarchy as an Excel PivotTable:**
  - A **Rows** bar of fields you drag to reorder (Alt+← / Alt+→), with ✕ and "+ Add field". The ◀ ▶ buttons and the separate FILTERS / "+ Other level…" row are gone.
  - One **Row Labels ▾** heading, whose list starts with **Select field:**, then Sort A to Z / Z to A, Clear Filter From "…", Search, (Select All), values, OK / Cancel.
  - The button shows a funnel when filtered and an arrow when sorted. "Total" is "Grand Total".
  - A field removed from Rows takes its filter and sort with it, as in Excel. "Store type (SSG / NSO)" is now "Store type".
- **Growth Matrix:** the same list with sorting (Sort Smallest to Largest / Largest to Smallest on period columns), one column sorted at a time, and the same funnel / arrow buttons. The shared `ExcelFilter` gains `FilterButton`, `fields`, `sort` and `numeric`.
- **Checked in the sandbox:**
  - An old filter on a field not in Rows was dropped.
  - Sort A to Z, Select field → Month (Mar-Jun only), and Month = Mar'27 → Grand Total ₹12,683.4 → ₹14,442.0 L.
  - Alt+→ moved Department behind Division.
  - Growth Matrix: Mar'27 P1 sorted Largest to Smallest (129.2 first).

### Sales Plan Growth Matrix: the same Excel-style column filters
- **Asked (user):** "add the same Excel filters to the Growth Matrix page".
- **Where:** a ▾ on the Department and Attribute headings and on every P1 / P2 period heading. Period lists show that column's growth index values, in numeric order (0 = delisted).
- **How they behave:** search, (Select all) / (Select all search results), OK / Cancel, Clear filter. Each list holds only the values left by the other column filters, as in Excel.
- **Alongside the existing filters:** they combine with the department search and attribute chips. "showing X of Y" and "Clear column filters (n)" sit in the FILTER row. Filters clear when the division changes.
- **Column fill:** the ▾ doesn't trigger a period heading's column fill (stopPropagation).
- **Shared component:** the dropdown is now `components/ExcelFilter.jsx`, used by both the Final Results Hierarchy and the Growth Matrix.
- **Checked in the sandbox:**
  - KIDS Attribute = SUMMER → 40 of 122 rows (= the SUMMER chip).
  - The Mar'27 P1 list then holds exactly the 29 values in those rows.
  - Opening a period list didn't open the fill prompt.

### Plan = the AOP Forecaster's MAMJ (+11.1%) in BIS and Sales Plan; Excel-style Hierarchy filters; faster Hierarchy
- **Asked (user):**
  - "growth should have been 11.1% can you check on that ?"
  - "this should match the AOP Forecster's projection for MAMJ which is 11.1% and then only it hould be pushed to sales plan engine. Check why the difference and rectify"
  - "the filters should be individual filters - excel styled, also make sure that the population speed is fast"
- **Why the growth differed.** AOP V2 (publish 118) is LY ₹38,884.3 L → ₹43,186.8 L = +11.06%.
  - BIS showed ₹387.7 → ₹431.9 Cr = +11.4% because its LY left out the inactive departments' LY (₹1.14 Cr, plan 0); AOP's base counts it.
  - Sales Plan showed +11.3% for two reasons:
    - its like-for-like LY came from today's Calendar snapshot. That has Mar'26 festival-shifted, ₹508 L below V2's unshifted March base (Apr-Jun matched to 0.0 L), so BIS's growth landed ₹5.9 Cr short of the AOP plan;
    - Final Results also left out inactive LY.
- **BIS** (department view): an inactive department's LY counts in its division's LY and in the header, with a plan of 0. The header shows LY ₹388.8 → ₹431.9 Cr **+11.1%**, MENS +9.3%, LADIES +11.6%, KIDS +12.9% (= AOP). The tooltip says how much inactive LY is included.
- **Sales Plan** (`run_dept_plan`):
  - **LY:** a like-for-like store's department LY is scaled so each store x division x month equals the base of the AOP publish BIS plans on; the department mix stays today's (`_aop_lfl_base`, `_base_scale`).
  - **Hold on AOP:** each division x month of the LFL stores is held on its AOP plan by one factor (≤0.18%, March only), as BIS does, because BIS spreads over its own department mix (`_aop_lfl_targets`; factors in `meta.lfl_hold_on_aop`).
  - **New departments:** the re-balance is done separately for LFL and other stores, so LFL stays on AOP (over all stores together it moved LADIES' LFL by 2.4 L).
- **Final Results** counts inactive departments' LY with plan 0. The ⓘ pop-up gains "Not planned this year" and explains the AOP base and the hold factor.
- **Result (base plan regenerated, backups in the scratchpad):**
  - LFL LY ₹38,884.31 L vs AOP ₹38,884.32 L.
  - TY ₹43,186.78 L = AOP exactly: **+11.065% = AOP**, worst division-month gap 0.004 L.
  - All 426 stores: ₹46,333.9 → ₹51,484.1 L = +11.1%.
- **Excel-style filters:**
  - Each hierarchy level's heading has its own ▾ list: search, (Select all) / (Select all search results), ticks, OK / Cancel, Clear filter. A filtered heading shows ▼.
  - The lists follow the other levels' filters, as in Excel (`/grain/hierarchy-options?level=&filters=`). "+ Other level…" filters a level that is not in the tree.
  - Open branches stay open when filters change.
- **Speed:**
  - A numpy column index of the plan replaces the cell walk: 1.7 ms vs 22 ms a branch, 0 differences on 51 branches; all 7 filter lists take about 6 ms.
  - The index is built at 8010 start (`warm_hierarchy`).
  - BIS input months are re-checked in the background instead of blocking a request about every minute (it was ~0.3 s).
- **Checked:**
  - test_final_hierarchy (inactive LY, Excel lists), test_grain_view, test_new_dept_template and test_division_plan pass.
  - Explanation = row on 244 real nodes.
  - BIS: node --check clean; header +11.1% in the browser.
  - Sandbox: header filters, search + OK, cascading lists, root in 12 ms.

### Sales Plan: plan months = BIS's input months (MAMJ) + Hierarchy filters
- **Asked (user):** "filters required, also the Plan should be made on auto detect from BIS input months, it should be restricted to that only. So BIS is currently there for MAMJ, so MAMJ should be the plan which is to be pushed in planning engine too".
- **Plan months follow BIS:**
  - `actuals_manager.plan_ty_months()` = the TY months BIS has sent growth for (any BIS division), read live and cached a minute. Today that is Mar-Jun'27 for KIDS, LADIES and MENS.
  - It falls back to the AOP-forecast months only if BIS can't be reached.
  - `locked_ly_months()`, which every engine reads its months from, follows it, so the plan now runs on LY Mar-Jun'26. A month joins the plan the day BIS starts planning it.
- **Saved plans show only those months:** grain_view `_cube()` shows a saved plan with just the plan months (`only_months`), so an older Mar-Sep file no longer shows Jul-Sep anywhere.
- **Base plan regenerated** (same as Generate Base Plan; backup in the scratchpad; no correction files existed):
  - `final_dept_plan.json` now holds Mar-Jun'27 only, 426 stores.
  - Mar-Jun is identical to before in all 179 departments (KIDS ₹15,864.9 L, LADIES ₹15,242.0 L, MENS ₹19,784.9 L).
- **Final Results Hierarchy filters:**
  - "+ Filter…" on any level (cluster, store, store type, division, attribute, department, month), with a search-and-tick list.
  - Active filters show as chips; Clear filters removes them; they are kept per browser.
  - The tree, totals, Cont % and the ⓘ pop-up (which states the filters) count only what is inside them. The API takes `filters=` on `/grain/hierarchy` and `/grain/explain`; `/grain/hierarchy-options` lists the values.
  - The Hierarchy controls are view controls, kept out of the suite Undo (`data-no-undo`).
- **Checked:**
  - test_final_hierarchy (filter cases) and test_grain_view (only_months) pass.
  - Sandbox: the page shows Mar-Jun (Total ₹50,891.8 L). The ML_JEANS filter gives ₹2,071.4 → ₹2,295.4 L, and the pop-up's parts (₹1,916.4 LFL + ₹379.0 other) add to it.

### Sales Plan Final Results: "how is this number made" pop-up on every Hierarchy row
- **Asked (user):** "can i have a pop up of how the respective department or cluster is getting that number ? To validate ofcourse, with proper explanations in plain words and summarised manner ... the number displayed should be the number we are trying to validate".
- Every Hierarchy row, and the Total, has an ⓘ. It opens a pop-up for that row:
  - the row's own LY, TY, Growth % and Cont %;
  - plain-language steps;
  - a month table;
  - a **Check** line where the parts add back to the number on screen.
- It is built from the very cells the row adds up (shared `_cells` walk with `hierarchy_rows`), via GET `/api/planning/grain/explain`.
- **The steps follow the plan's rules:**
  - Growth % = TY ÷ LY − 1; Cont % = TY ÷ the level above.
  - LY = last year's sales on this year's calendar.
  - Like-for-like stores = own LY × the BIS growth of each department and month, then the division re-balance factor where new departments exist.
  - Other stores = division LY × the division's average BIS growth, split by the reference store's mix.
  - New departments = New dept % of the reference's plan, with a ✓ check.
- **What it says follows the level clicked:**
  - A department lists the BIS growth used per month.
  - A reference department names its new department.
  - A store gives its cluster, type and reference store.
  - A cluster or division gives its store mix.
- **New in the plan cube:** the growth each LFL department x month was planned on, and each store's reference store.
- **Checked:**
  - 321 nodes across 4 hierarchies: the explanation's LY and TY = the row's, 0 mismatches; every new-department check ✓.
  - MENS ₹30,237.8 L and ML_JEANS ₹3,467.4 L / 11.5% match the screen.
  - BH - (NP) breaks into ₹18,258.2 LFL + ₹3,939.0 other + ₹292.3 new.
  - Pop-up checked in the sandbox (opens, Esc closes, focus returns).
  - test_final_hierarchy (explain cases added) and test_grain_view pass.

### BIS: Save as, New iteration, Rename + Sales Plan Department pages compare with a BIS iteration
- **Asked (user):** "yes add it on the department pages. Also, add a save as button for new iteration, a new iteration button to create a new BIS sheet, a rename button to rename existing iterations". This followed the question "why is not showing up in the version selector": the Division Plan's "Compare with" lists AOP Forecaster publishes only. The last BIS save was at 10:56 (Iteration 4); later edits were never saved.
- **BIS version picker** (bottom of the list, where "Remove an iteration" already was):
  - **New iteration (fresh sheet)**: every unlocked division goes back to the plain AOP share (Plan tools > Reset to AOP share) and is kept as the next iteration. Sales Plan doesn't change until Save.
  - **Save as new iteration**: the plan on screen becomes a new iteration whatever changed. It's a full Save, so it is sent to Sales Plan.
  - **Rename this version**: renames the version on screen; with none loaded, it opens the version list.
- **Plan history:** every version has a Rename button.
- **Names:**
  - A name is shown as "Name (Iteration N)" and is shared through the database (`{"rename": id, "name": ...}` on `/api/config/bis-plan-versions`).
  - An empty name goes back to the number. A re-save keeps the name.
- **Not toolbar buttons:** at 1366 px they squeezed the "Buyer's Input Sheet" title to 28 px. In the picker the title keeps its 146 px.
- **Sales Plan, Department pages (Master Setup and Growth Matrix):** new panel "compare with a BIS iteration".
  - It sets any saved BIS version beside the live plan, department by department, for Mar-Jun'27: LY, live plan and growth, the version's plan and growth, and the difference. Departments are sorted by the gap; "Changed departments only" is on by default; click a department for its months.
  - Both sides are priced on the same LY, Sales Plan's 148 like-for-like stores.
  - A department missing from an older version (split after it was saved) is marked "NOT IN ...".
- **Checked:**
  - Iteration 4 = the live plan in all 3 divisions (0 departments differ).
  - Original vs live: KIDS 91, LADIES 55, MENS 36 differ. 4 KIDS departments are not in the Original (split on 28 Sep).
  - Panel opened on both pages on the stand-alone Sales Plan server.
  - Rename endpoint 404 path checked; rename SQL tested on a temp table.
  - BIS `node --check` clean; test_bis_plan_versions passes. Save as, New iteration and Rename were not run on the live list (they write to it).

### Sales Plan: cluster-built plan weighted by sell-thru factors (the MAMJ'27 cluster workbook's working)
- **Asked (user):** "design a similar working with the components in the Cluster level planning engine for Department output", then "just import the logics ... donot replicate the output just as is, i want the existing apps to flow their respective components as in relation to the present columns". Choices: chain-level sell-thru from the data lake, AOP held per cluster x division, view only.
- The Store / Cluster panel's "How the plan is built" menu (Division Plan, Department Growth Matrix) has a third preview: **cluster-built (AOP x sell-thru factor)**. It shows in the panel's existing columns (months, Plan, LY, Growth, Today's plan, vs today, AOP). It is the same cluster-built split, weighted by LY x (1 + sell-thru factor) instead of LY x BIS growth.
- **Where each piece comes from:**
  - LY comes from the Calendar app (Sales Plan's cube).
  - Cluster x division AOP comes from the AOP Forecaster.
  - Average weekly sell-thru comes from BIS's file `rs_weekly_sell_ths_apps` (same filters: SEASON contains 26, ACTIVE stores).
  - The active departments come from the Department Master (the plan).
- **The rules** (`SalesPlan/backend/engines/sellthru_factor.py`):
  - The tag (Low / Average / High / Excellent) comes from the Mar-Jun'26 sell-thru.
  - Deviation = department / division sell-thru.
  - The workbook's FACTOR matrix gives 0-30%.
  - On the workbook's 1,764 rows this logic gives 0 tag differences and 0 factor differences.
- One department picked: the panel shows its tag and each month's sell-thru, its division's, the deviation and the factor.
- **Sell-thru is chain level.** The file has no store column, so the factors are the same in every cluster; clusters differ by their own LY mix and AOP. It is read once per file (about 30 s, warmed at 8010 start) and cached in `SalesPlan/backend/sellthru_factor_st.json` (git-ignored).
- **Checked in-process:**
  - Every KIDS cluster adds back to its AOP, with nothing unallocated.
  - BH - (NP) KB_R/N T-SHIRT H/S Mar'27 = 110.8372 L, both from the endpoint and by hand.
  - Response time is 0.2-0.8 s warm.
  - `test_grain_view` and the module's self-check pass.
  - The page sits behind the 8010 sign-in, so it was not opened in the browser. The built bundle carries the new option.

### STR Forecaster: the Excel export's 4-month figures are averages too
- **Asked (user):** "put the same averages in the excel export too".
- In the Drill-down sheet ("4-month avg ..." columns) and the By month sheet ("4-month avg" rows), plan qty, MDQ, LY qty / MDQ, plan Rs, fixtures and store count are now the average month: the months' figures over the months that have one, as on the page. They were 4-month totals.
- STR %, days and bands are unchanged. The Read me sheet says so. The separate "avg fixtures" column is gone, because "4-month avg fixtures" is the average now.
- **Checked by downloading the export:** BH - (NP) 4-month avg = plan qty 10,21,779, MDQ 18,70,087, fixtures 15,233, 52 stores (= the page).
- **Ops:** an earlier STR restart left two servers running, and the old one kept port 8085. Both were stopped and one fresh server started.

### STR Forecaster: the 4-month block shows averages for Plan qty and MDQ
- **Asked (user):** "in the averge columns only average should be there for Plan Qty,MDQ".
- The 4-month avg block showed the 4-month *totals* of plan qty and MDQ (All 1,41,18,535 / 2,52,48,122). It now shows the average month, the monthly figures over the months that have one: **Avg plan qty** / **Avg MDQ** (All 35,29,634 / 63,12,030; BH - (NP) 10,21,779 plan qty).
- Sorting and filters use the average too.
- STR days and Band are unchanged; they were already worked out from the average month. The months keep their own figures.
- Checked on 8085.

### STR Forecaster: fixture count and store count in the drill-down
- **Asked (user):** "I need Avg Fixtures, Avg Store Count in this view and its respective month fixture count and store count" (the Department > Cluster > Store view).
- **4-month avg block:** **Avg fixtures** (fixtures in the average month, over the months with fixtures) and **Avg store count** (stores with fixtures in the average month).
- **Each month:** **Fixtures** (from the fixture plan, with edits) and **Store count** (stores with fixtures that month). Every column sorts and filters like the others.
- Store count = distinct stores, so a store under many departments counts once. The **All** row takes it from the server (`/api/rollup` `all_stores`) and shows "-" while a row filter is on, since a filtered set can't be added up.
- **Code:**
  - `str_engine.rollup`: per row x month `stores`; on the 4-month cell `fixtures_avg` and `stores`. Self-check extended.
  - The Excel workbook's drill-down / by-month sheets gain "avg fixtures" and "stores".
- **Checked on 8085:**
  - All rows: 180 stores each month, 52,601.8 avg fixtures.
  - BH - (NP): 15,340 / 15,181 / 15,202 / 15,210 fixtures Mar-Jun -> avg 15,233.3, 52 stores.
  - KI_AP_BABA SUIT HSR H/S: 621 / 516 / 444 / 381 -> 490.5.
  - 8085 restarted.

### BIS: a buyer input of -100% moves the department to Inactive automatically
- **Asked (user):** "add one additional provisiion if a buyer's inout is -100 it should automatically shift the department to the inactive session".
- Any active department whose buyer input is -100% in every Mar-Jun month goes to the Inactive departments sheet. That covers a -100 block typed in, an import, a loaded version, or the plan as BIS opens. A single Phase 2 month at -100 doesn't count.
- It is the same move as making it inactive by hand (manual inactive, the division re-balanced to AOP), and it's saved in the browser. Its -100 entries are cleared, so re-activating it later doesn't send it straight back. A toast names what moved.
- It runs at the start of every redraw (`_autoInactive100` in `refresh`), so a typed -100 moves when you leave the cell, not while typing. NEW departments are left alone (their plan comes from the New departments list).
- Inactive departments go to Sales Plan as 0 (-100), as before.
- **Checked in BIS on 5050:** ML_JEANS block -100 -> inactive (manual), entries cleared, MENS = AOP each month; one month -100 on M_IN_BRIEF -> stays active. The test browser was restored. `node --check` OK.

### BIS: a NEW department's growth cells show 0
- **Asked (user):** "it should be 0 by default if the new tag is there" (screenshot: L_EW_SAREE_JAIPURI NEW, Block Growth 228.64).
- A department on the New departments list has no buyer growth of its own, so its Block Growth and month cells show **0**, read-only.
- Its plan is still the New departments % of its reference: Plan Total / vs LY show what it gets (JAIPURI Rs 1.6 Cr, +226.6% on its own LY), and the tooltip gives both.
- Display only: the plan, the totals and what goes to Sales Plan are unchanged. Checked in BIS on 5050.

### New departments: plan = exactly New dept % of the reference, division re-balanced to AOP automatically
- **Asked (user):** "Keep new dept cont % the same as fixed in the plan and reapportion on the mix and adjust the aop always it should happen automatically". The result was 25.4% of the reference, not 25%.
- **Cause:** Sales Plan *added* the carve (New dept % x reference) to the new department's own BIS plan (its buyer growth on its own LY), and the division total moved by the carve.
- **Sales Plan engine** (`apply_new_dept_adjustments`, used by Generate Base Plan, the new-dept save and /run):
  - the new department's plan IS reference x New dept % (its own plan is replaced; no reference in a store -> 0);
  - the reference keeps 100 - Ref dept %;
  - then every active department of the division x month is scaled by ONE factor over all stores, back to the division's pre-carve total (the BIS / AOP plan).
  - So the mix is kept, the division stays on its total, and the new department is exactly New dept % of its reference in every store and in total.
  - Checked on the real plan: JAIPURI / FNCY = 0.25, ETHNIC DRESS / DRESS = 0.40, CORD SETS / KURTI SET = 0.10 in every month Mar-Sep and in a single store; LADIES total unchanged every month (e.g. Mar'27 3,878.57 L). Self-check `engines/test_new_dept_template.py` extended.
- **BIS:**
  - The same rule runs in the plan itself, after every re-balance (`_divReapp` / `_divRescale` now settle new departments), on load and after the New departments window saves. Each listed new department's month = New dept % x its reference's, then the division is re-balanced on the mix to AOP, repeated until it holds.
  - The new department's block and month cells are read-only (NEW tag; the tooltip names the reference and %).
  - BIS sets only the new department's side: Ref dept % is applied by Sales Plan, so it isn't cut twice. A new department with no LY row in BIS (LW_U_CORD SETS) is planned by Sales Plan only.
  - The window's preview uses the same replace-then-re-balance rule.
  - Checked in BIS on 5050: JAIPURI / FNCY = 0.25 and ETHNIC DRESS / DRESS = 0.40 in Mar-Jun; LADIES = AOP each month; the JAIPURI cell is read-only (+226.6% shown).
- 8010 restarted. The saved base plan (final_dept_plan.json) picks the rule up at the next Generate Base Plan or New departments save.

### BIS: Contrib% no longer changes with the filters
- **Asked (user):** "check this why is the new cont % as per refernce superseeding the buyer's cont % which has no meaning ?" (screenshot: LADIES filtered to L_EW_SAREE_FNCY + L_EW_SAREE_JAIPURI, Contrib% 92.4% / 7.6%).
- **Cause:** not the new-department setting. With a department / attribute / section filter on, the department view worked out Contrib% against only the rows left on screen, so any two filtered rows added up to 100%.
- **Fix:** Contrib% is always the row's share of its whole division's active LY on a division tab, or of every division shown on ALL (`_divLYAll`). Filters only choose which rows are listed.
- **Checked in BIS on 5050 (LADIES):** filtered and unfiltered both give L_EW_SAREE_FNCY 5.06%, L_EW_SAREE_JAIPURI 0.42% (was 92.4% / 7.6% filtered); ALL tab 1.49% / 0.12%. `node --check` OK.

### BIS: Plan tools -> Import block growth % (paste from Excel)
- **Asked (user):** "if i want to import this type of data for growth % for the block update, please update in the iteration 2 and give a provision to import such changes through" (a pasted DEPARTMENT / FINAL GROWTH % table).
- **Follow-ups:** "apply on the screen doesnt seem to work" (Apply stayed greyed until Preview, and again after a mode change; it now works on its own); "growth numbers seem to be unchanged even after succesful preview" (they had changed, but "Hold each division on AOP" scales them; the preview now shows the result).
- **New, Plan tools -> Import block growth %:** paste two columns from Excel (DEPARTMENT, growth %; a header row is skipped). Optional Preview, then **Apply to the plan on screen** sets each matched department's Phase 1 block % (flat Mar-Jun) as a buyer entry.
  - **Name matching:** by BIS name or id. A pre-split name goes to its parts (`DEPT_SPLITS`) and wins over the parts' own rows; in these sheets those rows are the old inactive leftovers, e.g. MSE_PYJAMA 13.6% -> MSE_HSR PYJAMA and MSE_TXTL PYJAMA, not their 0.0%.
  - Inactive BIS departments aren't touched, and departments with no row keep their value.
  - "14.3%", "14.3" and Excel fractions ("0.143", when no value has a % sign and all are within +-1) all read as 14.3%.
  - **Exact as typed:** the pasted numbers, with the three divisions locked so nothing re-balances them (they can sit off AOP).
  - **Hold each division on AOP:** the departments are scaled together each month onto the AOP, keeping the mix (as Re-calibrate), so the block % differs from the pasted %.
  - The preview shows, per department: block % now, pasted, block % after for the option picked, and the source row. It also lists division totals now / after / AOP, names not in BIS, inactive ones skipped, and very large growths (e.g. L_EW_SAREE_JAIPURI +229.3%).
  - Nothing goes to Sales Plan until Save.
- **Iteration 2:** load it, import, then Save. On AOP the totals barely move, so Save updates Iteration 2 in place; exact-as-typed totals move more than 0.5 Cr, so Save creates the next iteration.
- **Checked in BIS on 5050 with Iteration 2:**
  - Apply without Preview -> on AOP (167.30 / 128.15 / 136.41 Cr), mix kept, split parts get the old name's value.
  - Exact -> ML_JEANS 12.2, M_IN_BRIEF 9.4, MSE_POLO 18.3, L_EW_NIGHTY 31.5, MSE_HSR PYJAMA 13.6; divisions locked.
  - `node --check` OK; the test browser was restored.

### Sales Plan: faster views, plan months follow the AOP forecast, Final Results = Hierarchy only, GM / RETAIL fully out
- **Asked (user):**
  - "population latency for the every view in the planning engine";
  - "remove the GM & retail from the planning engine until further advisememnt";
  - "if there is no data in the no cluster level just remove it from any view";
  - "only populate for which all AOP is being forecasted ..." (chose: the months AOP has a forecast for);
  - "also populate Sep'26 data everywhere";
  - "remove multiple views just keep the hierarchial view".
- **Latency:**
  - The live plan run (~5-10 s) used to run once per view per request. Now one run feeds every read-only view (`dept_sales_engine.plan_views`: plan summary, Cluster View, the Store / Cluster cube) and runs again only when an input changes. The plan itself isn't kept in memory (~1.5 GB); only what the views need.
  - 8010 keeps it warm in the background (`warm_plan_views`, checks the inputs every minute from start).
  - The AOP store forecast behind the store-built / cluster-built preview is read once per publish, not on every call.
  - Measured in-process, before -> after: Cluster View 4.2-4.9 s on every open -> 0.3 s; Store / Cluster panels 0.2 s, with no 8.6 s first open; preview 1.7-3.3 s -> 0.4-1.9 s; Final Results 0.46 s + 1.3 MB -> 0.01 s (pipeline only; the tree loads branch by branch, 0.01-0.8 s).
  - Callers that change the plan (Generate Base Plan, new-dept map, /run) still take their own fresh run.
- **Months:**
  - `actuals_manager.locked_ly_months()`, where every engine gets its months, now keeps only the months the live AOP version has a forecast for (`grain_view.aop_forecast_months`, re-checked every minute).
  - V2 / publish 118 forecasts Mar-Sep'27 (Sep = new stores only) and nothing from Oct'27, so the plan runs on LY Mar-Sep'26.
  - Oct'27 onwards stays out until AOP forecasts it. If AOP can't be read, there is no filter (never an empty plan).
  - The store-built / cluster-built preview still compares on the months AOP has a base for (Mar-Aug'27): Sep'27 there is new stores only, so it isn't like for like.
- **Final Results:**
  - Only the Hierarchy view. The Store / Department / Cluster / Dashboard views and their `/final-results/data` + `/dashboard` routes (a 1.3 MB read of the whole plan file, and the GM / RETAIL cards) are removed.
  - The page reads `/final-results/pipeline` for the banner.
- **GM / RETAIL:** Master Setup (`department-plan/config`) lists KIDS / LADIES / MENS only. A scan of every planning GET response finds no GM / RETAIL.
- **No cluster:** a Hierarchy branch with no LY and no TY isn't listed. The Store / Cluster panels already left empty stores out, so their total is unchanged: 9 clusters.
- **Checked:**
  - Self-checks: actuals manager, grain view, final hierarchy (with an empty no-cluster store).
  - Plan summary, Cluster View and Hierarchy by month all give Mar'27-Sep'27. Hierarchy by month TY (L): 13,815 / 12,363 / 12,420 / 12,251 / 7,994 / 10,844 / 7,407.
  - dist rebuilt; 8010 restarted.

### Sales Plan Final Results: Hierarchy view (pick the levels and their order)
- **Asked (user):** "i need a editable hierarchial system for editing a hierarchy for view". The user chose "the hierarchy itself (view only)", with all levels: Cluster, Store, Division, Department, Month, Attribute, Store type.
- **New view: Final Results -> Hierarchy** (next to Dashboard).
  - The level chips can be moved up / down (◀ ▶), removed (✕) or added (+ Add level…); Reset puts back Cluster -> Store -> Division -> Department. The chosen order is kept per browser.
  - The plan shows as an expandable tree with LY, TY, Growth % and Cont % (share of the level above) at every level, plus a total.
  - Without Month as a level, all plan months are added up.
- **Backend:** `GET /api/planning/grain/hierarchy?levels=...&path=[...]` (`grain_view.hierarchy_rows`, self-check `engines/test_final_hierarchy.py`) returns the children of one node, so a branch loads only when it is opened.
  - It reads the same cached plan cube as the Store / Cluster panels: the active saved plan, or the live base plan while the saved file has no months (as now). KIDS / LADIES / MENS only, active departments only.
- **Checked:**
  - Timings on the live plan: top level 0.5 s; a cluster's stores 0.1 s; one store's departments by month 0.01 s.
  - Sandbox: 10 clusters, total 77,093.4 L (= Store / Cluster panel); BH - (NP) opens to its stores; moving Division to the top gives MENS / LADIES / KIDS = 30,312.2 / 23,606.0 / 23,175.1 L; KIDS opens to its clusters.
  - dist rebuilt; 8010 restarted.

### Sales Plan: GM and RETAIL removed from the planning engine
- **Asked (user):** "remove divisions - gm and retail from sales plan engine" (screenshot: the Store / Cluster panel's All divisions).
- **Engine:** `dept_sales_engine.DIVISIONS` is now KIDS / LADIES / MENS. Every plan build loops over it (base plan, plan summary, department plan, MRP and everything after), so GM and RETAIL are no longer planned or totalled.
- **Saved plans:** a plan file saved before this still holds them until the next Generate Base Plan. The Store / Cluster views skip them already (`grain_view.PLAN_DIVS`).
- **Screens:** GM and RETAIL taken out of the division lists on Store / Cluster, Department Plan, Growth Matrix, Attribute Correction, New Departments and Division Growth Structure.
- **Left as is:**
  - The actuals import (`actuals_manager`) still maps and stores GM / RETAIL LY, so their data isn't lost.
  - Final Results' GM / RETAIL special case is inert now.
  - `department_custom.json` (user config) is untouched.
- **Checked:**
  - Self-checks: grain view, actuals manager, division plan.
  - Baseline compare: the only differences are GM / RETAIL gone from the plan summary (grand LY 71,364 -> 57,926 L), plus today's buyer-growth push and sync timestamps. Calendar and AOP are unchanged.
  - Sandbox: plan summary, division plan and Store / Cluster all return KIDS / LADIES / MENS only. All divisions total 77,093 L, was 94,283 L with GM / RETAIL. The division dropdown lists All, KIDS, LADIES, MENS.
  - dist rebuilt; 8010 restarted.

### BIS -> Sales Plan: re-calibrated buyer plan pushed (data)
- **Asked (user):** "push the re-calibrated plan to sales plan".
- **What was sent:** Iteration 1 (the buyer sheet), re-calibrated to AOP (MENS 167.30 / LADIES 128.15 / KIDS 136.42 Cr, buyer mix kept), saved and pushed from BIS on 5050 exactly as the Save button does. It became **Iteration 2**.
- **Sales Plan now holds** 944 rows, Mar-Jun'27, publish 118, sent 13 Oct 08:24 (was 12 Oct 16:54). Examples: M_IN_BRIEF 5.23 / 8.02 / 7.92 / 7.81 %; ML_JEANS 10.01 / 12.93 / 12.83 / 12.71 %.
- **Backup** of the rows it replaced: `Backups/buyer_growth_before_recalibrated_push_2026-10-13/buyer_department_growth.json`.
- **Note:** pushed through 5050, the BIS server on this machine. That route skips Landing's per-person "buyer_push" right, which only applies to pushes going through Landing (7800).

## 2026-10-12

### BIS: Re-calibrate to AOP does all three divisions in one click (2026-10-13, `a66dbc3`)
- **Asked (user):** "It should recaliberate for ALL divisions once it is clicked not individual division in a single time".
- Re-calibrate to AOP no longer follows the open division tab: one click always does MENS, LADIES and KIDS together, and the menu text says so.
- Checked in BIS on 5050 with Iteration 1 loaded on the MENS tab: one click moved MENS 171.79 -> 167.30, LADIES 129.19 -> 128.15, KIDS 133.41 -> 136.42 (all = AOP). All 3 division locks went; 135 buyer entries were kept. The confirm listed all three. `node --check` OK; the test browser was restored.

### BIS: Plan tools -> Re-calibrate to AOP (keeps the buyer's mix)
- **Asked (user):** "I want to re-calibrate so where is the operation for doing that" (screenshot: Iteration 1 loaded, MENS / LADIES / KIDS off AOP, 236 locked, 135 buyer-set).
- There was no such action. The chip pointed to Plan tools, but only Reset to AOP share (which clears the buyer entries) and Re-apportion by LY Cont% were there.
- **New, Plan tools -> Re-calibrate to AOP:** for the division on the open tab, or all three on ALL:
  - the division lock is removed (only the locks it added; departments the buyer locked stay fixed);
  - every Mar-Jun month is scaled together onto its AOP (`_divRescale`, the same re-balance BIS runs when it opens);
  - the buyer's mix and the buyer entries are kept.
  - It asks first, showing each division's total -> AOP, and says if your own locks hold more than the AOP. Nothing is sent until Save.
- **Checked in BIS on 5050 with Iteration 1:**
  - MENS 171.79 -> 167.30, LADIES 129.19 -> 128.15, KIDS 133.41 -> 136.42 (= AOP); chips "= AOP"; 135 buyer entries kept.
  - ML_JEANS vs M_IN_BRIEF ratio identical every month; block growth now ML_JEANS +11.86%, M_IN_BRIEF +7.14%.
  - The test browser's state was restored afterwards.
- **Slip:** my first edit put real line breaks inside a JS string. BIS failed to load for about 2 minutes (5050 and /buyer) until it was fixed; the script was then checked with `node --check`.

### BIS: Iteration 1 = the buyer input sheet, exact as typed (data, no code change)
- **Asked (user):** "I have given you a buyer's input sheet which is used in the current plan replicate the buyer's input on block and make an iteration according to it". The user chose "Exact as typed".
- Source: `MAMJ'27 DEPARTMENT - AOP (NEW APPROACH) - FOR BUYERS INPUT - UPDATED.xlsx`, sheet DEPT INPUT, column "BUYERS INPUT AT MAMJ".
- **How it was built:** on the database's Original (25 Sep). The user's list moved into the DB at 17:20, and the user then removed its other iterations.
  - Each matched department gets the sheet's % as a flat Mar-Jun block growth, set as buyer-entered. 135 departments are set.
  - Old names reach BIS's split parts (`DEPT_SPLITS`): MSE_PYJAMA, KB_BERMUDA, KB_T-SHIRT H/S, LW_L_PALAZZO, LW_L_JEGGING, L_IN_BRA.
  - IN-ACTIVE rows that are still live in BIS get -100.
  - All three divisions are locked, so nothing re-balances back to AOP.
  - 63 departments have no row in the sheet (mostly winter, tiny MAMJ LY) and keep the Original's value. Months outside Mar-Jun are untouched.
- **Result on BIS's LY:**

  | Division | Iteration 1 | AOP |
  |---|---|---|
  | MENS | Rs 171.79 Cr | 167.30 |
  | LADIES | Rs 129.19 Cr | 128.15 |
  | KIDS | Rs 133.41 Cr | 136.42 |

  Stored as Iteration 1, with 135 buyer entries, 3 locked divisions and a note naming the sheet. Not pushed to Sales Plan: Load it, then Save, to send it.
- The build script is in the session scratchpad (`bis_buyer_iteration.js`); it was dry-run twice before the post.

### Sales Plan Division Plan: store / cluster breakup right under the division table
- **Asked (user):** "can i have a cluster/store breakup based on the toggle ?" (screenshot of Division Plan).
- The breakup panel was already on the page but sat at the very bottom, under the collapsed charts. It is now directly under "Division Plan (as in BIS)", titled **Division plan · by store / by cluster**. It follows the header's Plan by Store | Cluster toggle and its own Store | Cluster buttons. Clusters expand to their stores; a store row shows its cluster's total.
- Checked in the sandbox of the built pages: table, then breakup, then charts; switching to Cluster shows 9 clusters / 207 stores. dist rebuilt; 8010 serves it from disk (a tab opened earlier needs a refresh).

### BIS: top-bar overlap fixed, iteration remover, versions keep buyer entries + division locks
- **Asked (user):** "rectify this overlap. Also, give me a iteration remover in the selection pane" (screenshot: the "Buyer's Input Sheet" title under the AOP chip).
- **Overlap:** the action buttons were allowed to shrink, so when they didn't fit they slid left over the centred title. Now they never shrink, and the title takes the space left: centred while there is room, shortened with "…" when there isn't. Checked at 1630 / 1400 / 1200 px: no overlap, title not cut.
- **Remover:**
  - The selector's last entry is **"✕ Remove an iteration…"**. It opens Plan history, where every iteration has **✕ Remove** (asks first).
  - The Original can't be removed (the server refuses it too), and the other iterations keep their numbers.
  - The removal applies to the shared list; the plan on screen is not changed.
  - Backend: `POST /api/config/bis-plan-versions {"remove": id}` (404 for an unknown id or the Original).
- **Versions now also keep** the buyer-entered departments and the division locks (`buyerSet`, `divLocked`, `divLockAdded`). Loading a version therefore re-balances the way it did when saved. Versions saved before this have neither, and Load leaves those as they are.
- **Safety:** if a browser's own versions would be replaced by the database list, they are first kept once under `bis.plan_versions.before_db`.
- **Checked:**
  - In BIS on 5050 against an in-memory stand-in for the server: 4 versions; removing Iteration 2 leaves Original, Iteration 1 and Iteration 3; only the iterations have Remove buttons; a loaded version brings back its buyer entries and division lock.
  - The real route: removing an unknown id returns 404.
  - 8000 restarted.

### BIS: plan versions moved to the database
- **Asked (user):** "move the BIS versions to the database".
- **Where they live:** the Original + iterations are now in Postgres, `planning_inputs.bis_plan_versions` (`id`, `data` JSONB = the BIS entry as before, `last_modified_at`), so every machine sees the same list. This is the same approach as AOP's own `plan_versions`.
  - Backend: `Tentative AOP Forecaster/db/bis_plan_versions.py` (self-check `db/test_bis_plan_versions.py`).
  - Routes: `GET`/`POST /api/config/bis-plan-versions` on AOP 8000, reached through the BIS server (5050 proxy, and `/buyer/...` behind Landing). No Landing change and no Landing restart.
- **The server numbers every new version,** so two machines can't both make an Original or reuse an iteration number:
  - with no Original yet, a new version becomes the Original; otherwise it becomes the next iteration;
  - an existing version keeps its number;
  - the Original is never overwritten;
  - the cap keeps the Original plus the newest iterations (10 in all).
- **First move:** the first BIS that opens with an empty table copies its own browser list in as it is, keeping its Original and numbers. After that, every browser follows the database list.
- **When the server can't be reached:** the browser copy stays. A version saved meanwhile is marked "not in the database yet" and is sent the next time BIS opens or the list is pulled.
- **Fixed from `19577b9`:** on page load the selector ran before the version-log setup and always showed "No saved version yet" until the first Save. It now runs at the end of the script.
- **Checked:**
  - `test_bis_plan_versions` OK.
  - Save and import ran against the real DB inside a transaction that was rolled back: Original, then Iteration 1; Original kept; second import refused; table empty afterwards.
  - The BIS page on 5050 was tested against an in-memory stand-in for the server: first save, a save while down (pending), reconnect (sent), another machine's iteration showing up, first-move import.
  - The real table is still empty: your browser's list moves in the first time you open BIS.
  - 8000 and 5050 restarted.

### BIS: version selector - one Original, the rest iterations
- **Asked (user):** "give me a version selector just like AOP forecaster in BIS so that there is 1 original version where the others are iterations".
- A **version selector** in the top bar (next to Before / after and Save) lists **Original**, then **Iteration 1, 2, ...** with each one's save time. The version the plan on screen came from is selected; picking another loads it (asks first, as Plan history's Load does).
- **The Original is your first saved plan and never changes.** Saving an unchanged plan while on it does nothing. Saving a changed plan creates the next iteration. Iterations keep the old rule: a save whose division totals move by no more than Rs 0.5 Cr refreshes that iteration in place; a bigger change creates a new one. The 10-version cap now drops the oldest iteration, never the Original. Iteration numbers never move.
- Plan history shows the same names with ORIGINAL / ON SCREEN tags. For versions saved before this change, the oldest one left becomes the Original and the rest are numbered by age.
- Versions are still kept in this browser only (`bis.plan_versions`), as before.
- **Checked in the in-app browser on 5050:** I called the save-version function directly rather than pressing Save, because Save would also push growth to Sales Plan. The browser's own version list was restored afterwards. Results: an empty list shows "No saved version yet". The first save creates the Original, and an unchanged re-save changes nothing. A changed save from the Original creates Iteration 1 and leaves the Original's snapshot identical. After 12 more changed saves the list holds the Original plus Iterations 4-12. An old list of 3 versions converts to Original, Iteration 1, Iteration 2.

### Sales Plan: Attr / Base Correction off in Cluster view
- **Asked (user):** "disable attr correction and base correction in cluster view" (screenshot of the sidebar).
- Both correct the plan store by store, so with the header switch on Cluster: the two sidebar items are greyed with a "store only" tag and a tooltip (not links); the Growth Matrix "what next" pop-up after Generate Base Plan shows them disabled with a one-line reason (Opt out to Final Results still works); opening either page by link shows "... is off in Cluster view" with a **Switch to Store** button (`components/ClusterOff.jsx`; the pages are wrapped, so nothing of theirs runs in Cluster view). PW/W and SOR Deviation are untouched. Store view: everything as before.
- Checked in the sandbox of the built pages: Cluster -> both items off and both pages gated, PW/W / SOR still on; Switch to Store -> back to normal. The pop-up was not opened (it needs a Generate Base Plan run, which saves the plan). dist rebuilt.

### Sales Plan: preview of a store-built / cluster-built plan from AOP Forecaster x BIS x Calendar (step 2)
- **Asked (user):** the same request, step 2 - chose "By each store's LY share" (cluster -> stores) and "AOP store forecast x BIS mix" (anchor).
- On Division Plan and Growth Matrix the Store / Cluster panel has **How the plan is built: Today's plan | Preview: store-built (AOP x BIS) | Preview: cluster-built (AOP x BIS)** - nothing is saved or adopted; the table adds Today's plan, vs today and (division) AOP columns and a note explaining the method.
  - **Store-built:** each store x division x month = its AOP Forecaster store forecast, split over departments by the store's own LY department mix x BIS growth; a store with no LY of its own (a new store) takes its cluster's mix. Clusters = the sum of their stores.
  - **Cluster-built:** each cluster x division x month = the sum of its stores' AOP forecasts, split over departments by the cluster's LY mix x BIS growth, then to its stores by each store's LY share. Stores with no LY get nothing; their AOP lands on the cluster's other stores.
  - Sources: AOP = the publish BIS plans on (118, Version 2), per store from that AOP session's detail.json (1,595 store x division rows, every store incl. NSO / ramp - its KIDS LFL Mar'27 sums to the published 4,533.82 L); LY = the plan's re-indexed LY (Calendar); growth = the live BIS growth matrix (P1 / P2 averaged). Only the months that AOP version has LY for (V2 ran 25 Sep: Mar-Aug'27; its Sep figure is new stores only).
- **What it shows today (Mar-Aug'27, all divisions):** LY 79,722 L; today's plan 84,745 L; both previews 132,590 L (= the AOP store forecast). Most of the gap is new / ramp stores, which today's plan gives nothing (no LY) - UP 1 - (NP) 44,806 L in AOP vs 15,101 L today. Store-built keeps that on the new stores (PNA, an LFL store: 1,114.8 L = its AOP, +10.1% on LY); cluster-built spreads it over the existing stores (PNA 1,281.1 L, +26.5%).
- `grain_view.build_methods` (pure, self-checked in engines/test_grain_view.py: each store lands on its AOP, each cluster on its stores' AOP, splits add back exactly, a no-LY store takes its cluster's mix / gets nothing cluster-built); `GET /api/planning/grain/methods`. Checked in the sandbox of the built pages (all four method x grain views add up); 8010 restarted; baseline compare identical.

### Sales Plan: Store / Cluster switch with a preview on every stage (step 1 - view only)
- **Asked (user):** "can i have a switch in the planning engine for working as Cluster or Store ... give a vice versa preview on all stages - Division, Department, MRP or Display Type ... The sales plan and historical data should be an amalgamation of data from AOP forecaster + BIS + Calendar" -> chose "Both, in two steps": step 1 (this) shows the plan by store or cluster with no number change; step 2 (next) a cluster-built method anchored on the AOP store forecast x BIS mix, cluster -> stores by LY share, shown side by side before it is adopted.
- **Header switch "Plan by Store | Cluster"** (kept in this browser, `sp.grain`); every page follows it.
- **One panel on Division Plan, Growth Matrix (the tab's division, a department picker), MRP Output (the tab's division, a department picker) and Display Type:** the plan by cluster - each cluster opens to its stores with their share of it (the plan flowing down) - or by store - each store with its cluster and its share of the cluster (what it rolls up to); months (or MRP bands / Table + Non-Table), Plan / LY / Growth %, totals, find, LFL tag. Final Results' Store / Cluster view follows the switch.
- **Server:** `engines/grain_view.py` (`/api/planning/grain/{meta,division,department,mrp,display}`, sign-in as the other routes). It reads the plan Final Results shows (base > attribute > generated); the saved `final_dept_plan.json` has no months (generated 23 Sep, before the LY months closed), so until Generate Base Plan is run it uses the live base plan, cached on its inputs, and says so. MRP = each store's fortnight plan x the department's MRP split, only for the months the split covers (Mar-Jun). Stores with nothing in them (warehouses, dummy codes, new stores without LY) are counted, not listed. Self-check `engines/test_grain_view.py`.
- Today (live plan, all divisions, Mar-Sep'27): 9 clusters, 207 stores with a plan (219 empty), Rs 94,282.7 L plan vs 89,260.0 L LY (+5.6%); BH - (NP) 27,542.7 L across 59 stores. Checked in a no-sign-in sandbox of the built pages (every grain call 200; cluster -> stores and store -> cluster add up; Final Results follows the switch); 8010 restarted (route answers 401 signed out). Baseline compare: only the 15:14 BIS Save moved numbers (growth pushed on publish 118 - the Division Plan now reads "BIS plan on AOP Version 2 (publish 118)"); no test regressed; baseline re-captured.

### BIS: a revert button in front of every department
- **Asked (user):** "add a revert button in front of every department in every BIS tab" -> chose "Its AOP share".
- A small ↺ before each active department's name on the tabs that list departments (Buyer's Plan, Department Summary; Division / Attribute Summary list divisions / attributes and keep their own ↺ Revert, the Inactive tab uses Reactivate). It does what the attribute ↺ Revert does, for one department: back to its AOP-seeded growth for the selected months, its locks and "buyer's own growth" flag cleared, the rest of its division re-balanced onto AOP (`revertToAop(dv, null, secId)`; `revertDeptToAop`). Faded with the reason in its tooltip - and a toast if clicked - when already on its AOP share, the division is locked, or no AOP is synced. Counts in the before / after comparison as an edit of that department. Nothing reaches Sales Plan until Save.
- Checked: M_IN_BRIEF Apr set to +25% -> ↺ -> +10.0% (its AOP seed), flag cleared, MENS Apr back on its AOP; 198 buttons on Buyer's Plan and Department Summary; BIS node tests pass; outside copy byte-identical.

### Sales Plan Division Plan falls back to the live AOP version
- **Asked (user):** "make the division plan fall back to the live AOP version".
- `division_plan._pick_publish`: the publish stamped on BIS's last Save while it is still a saved version's latest, else the live saved version; the page's source line then reads "Live AOP Version 2 - 25 Sept 2026 (publish 118) - BIS was last saved on publish 116; Save in BIS to plan on this one" and the response carries `bis_publish_id`. Before, BIS's Save of 7 Oct was stamped 116, Version 2 was published again as 118 on 8 Oct, 116 left the version list and the page showed "No AOP published yet" with zeros.
- Now: KIDS 12,087.67 L LY -> 13,641.52 L (+12.85%), LADIES 11,485.44 -> 12,815.30 (+11.58%), MENS 15,311.21 -> 16,729.96 (+9.27%); total LY 388.8 Cr, plan 431.9 Cr (= the BIS plan). Self-check added to engines/test_division_plan.py; 8010 restarted; README updated.
- Noticed while comparing: the BIS factor table was saved again at 14:50 today, back to Matrix (version 3) - a user action, left as is. Baseline updated for both.

### BIS department details: click a month for the planner's working
- **Asked (user):** "if i click on any month i want to see the working of how the factor was derived".
- In the department details panel the Month by month rows (and Block) are clickable (mouse, Enter / Space). A month shows its working in six steps: the factor and its inputs (method, sell-thru / LY growth / fill rate and their bands; Phase 1 = one factor for the block, Phase 2 = that month's own), LY and LY cont % of the division, the division's AOP x cont % = AOP share, x factor, the re-balance (every department's step 4 added up, scaled by AOP / total so the division lands exactly on its month AOP), and the Planner Gr% against the buyer's growth. Block shows the summary as before.
- **Fixed:** in Phase 2 the block text showed the first month's factor (Mar 1.08) as the block factor while the header said 1.04; it now gives the AOP-share-weighted factor (1.04) and each month's own (Mar 1.08 / Apr 1.00 / May 1.02 / Jun 1.08), so the two agree.
- Display only (same numbers as the planner calculation - checked: the month's departments add up to its AOP exactly). BIS node tests pass; outside copy byte-identical.

### BIS factor table: ML breakdown tab + plain-words key
- **Asked (user):** "show the ml factor breakdown visually in the factor table in a separate tab", then "perhaps give a simple explanation legend for terms like error and no error values and other complex graphical values".
- New third tab **ML breakdown** in the Planner's factor table pop-up (front end only, reads the loaded history check): a card per division (how its factors spread x0.80-x1.20 with a neutral "about level" bar, whether sell-thru / fill rate are used and what twice the division's level does, the history part's error vs no factor on the past cycles); then every department - History part, Sell-thru, Fill rate, Model factor, Damping + limits, Factor used - with a waterfall from x1.00 on one log scale (one coloured lane per step) and its main reasons as chips; division filter, find, sort (biggest move / largest LY / A-Z), Preview > opens that department on the first tab. Shows the same honest note (did no better than no factor on past cycles) and whether the saved factors come from an older check.
- **How to read this - plain words** key (open on the tab, folded on the ML settings view): x1.00, each column, Error (the share of sales planned in the wrong department on past seasons, lower is better), No factor (keep last-year share - the benchmark), "better in 2 of 6", "twice the division's sell-thru", the waterfall, the division bars, main reasons.
- Then (user: "plain words needed to decipher this", about the grey x1.000 in the Sell-thru / Fill rate columns): those cells now read **No effect** with the reason underneath - "KIDS doesn't use it" (switched off in that division because it did not make the plan more accurate there) or "no sell-thru figure" / "no fill-rate figure" (treated as average for its division); the key gets a "No effect" entry in the same words. Today: 190 cells "KIDS doesn't use it", 36 + 36 with no figure (MENS / LADIES).
- Then (user: "give the damping lane its own colour"): the Damping + limits lane is purple (new token `--blk-guard:#9333EA`) in the waterfall, legend and key, so grey only means neutral (the x1.00 line, "No effect", in-between values, "about level").
- Then (user: "show the No effect reason tags as a legend too"): a second legend line under the waterfall legend shows both tags as they look in the table - "No effect / KIDS doesn't use it" (the divisions with sell-thru / fill rate switched off, read from the check) and "No effect / no sell-thru figure" - each with its meaning in one line.
- Checked in the browser: 190 departments, 3 cards, find / division / sort, key open-fold kept across re-renders, console only the expected sign-in 401 / 404 on BIS's own port. BIS node tests pass. Outside copy byte-identical.

### Declutter (suite-wide, from the signed-off register)
- **Asked (user):** "Run a full audit for all the apps and declutter the unused features and other trash ... Only declutter which is not related to the Core functionality" -> register https://claude.ai/artifact/7ZsdAdkSBaJD9faDmBazF4 -> "Use every suggested Remove" (Unsure rows left as they are). Nothing is hard-deleted: tracked files go in commits, everything else is moved to `Backups/declutter_quarantine_2026-10-12/<same path>` (`Backups/declutter_baseline_2026-10-12/quarantine.py restore <path>` puts one back). Every step is checked with `golden.py compare` against the 12 Oct 12:18 baseline (33 number sources, 31 test suites) and must come back identical.
- **Step 1 - disk clutter (no tracked change):** 3 unused Re-Aligner workspaces identical to the starting copy (md5), locks.json.bak leftovers, 2 stale Growth-vs-LY LY caches, every __pycache__ / .pytest_cache, finished Calendar job folders (older than 2 h), Landing keep_alive.log, old qa-runner screenshots / results / saved login, empty .superpowers, data/sync_scratch, SalesPlan/backend/data - 663 items, 780 MB. Compare: identical (two Sales Plan name lists only came back in another order - golden.py now compares such lists as sets).
- **Step 2 - retired launchers, one-off scripts, docs:** removed `Tentative AOP Forecaster/launch.bat` (started the pre-database AOP copy outside the repo); Sales Plan's 8002 scripts (start.bat, install_service / install_watchdog / watchdog / install_shortcut / install_firewall / make_icon .ps1, icon.ico - uninstall_service.ps1 kept); BIS REGISTER_NSO_SERVER_AS_ADMIN.ps1; Listing scripts/consolidate.py; AOP db/migrate_manual_levers.py; calendar_engine/migrate_from_json.py + tests/test_calendar_migration.py (it replays the Aug-24 JSON over the live calendar tables) + Calendar Engine/Local DB/*.json; the never-built docker spec. Untracked REGISTER_TASK_AS_ADMIN.ps1 + start_platform_server.bat/.ps1 quarantined - the boot task "RS Planning - Platform Server 8010" (0.0.0.0) now has nothing to run; disable it in Task Scheduler (admin). AOP dev preview config pointed at the repo frontend instead of the legacy copy. Compare: identical.
- **Step 3 - dead code in AOP / Platform / Calendar / Landing / Re-Aligner (no caller anywhere):** AOP standalone GET /api/palettes, DELETE /api/sessions/{id} and DELETE /api/config/store-master/untagged (both deleted data on the unauthenticated :8000) and app.py's stale DB_SYNC_JOBS copy (run_all.py holds the one list); Calendar GET salesdata/link, link-daywise and snapshot/{source}/{kind}, 4 unused api.js exports (dist rebuilt), 5 constants left from the old local server; Landing's /api/otb/ proxy (no such BIS route); Re-Aligner's loader for the pre-30-Sep tuple pickle. Servers restarted; removed routes now 404 / 405. Compare: identical.
- **Step 4 - Sales Plan, no caller anywhere:** routes base-correction/review, department-plan/contrib + auto-balance (and their request models), dept-sales/final-plan, store/{store}/{division}, meta, division-plan/stores, final-results/status (the `_pipeline_status` helper stays - Reconciliation uses it), deviation/pww/phase1-result; dead constants DEPT_GROWTH_PATH (x2, pointed at a file that does not exist) and FY28_MONTHS; New departments page lost its 'in pipeline' branch (New depts left the optional steps today - the page and its config role stay). dist rebuilt; 8010 restarted. golden.py no longer reads the two removed routes. Compare: identical.
- **Step 5 - BIS (last, inline handlers checked as text):** removed the old manual AOP entry (onAopInput, onAopPaste, importAndLockAop, downloadAopTemplate, importFromFile, parseAopCSV - AOP only arrives by sync), the old sales-only syncData (Refresh calls syncAll), the light/dark applyTheme (single theme since 25 Sep; _recomputeAccentDerived and the suite theme hook stay), abbrev, qset (+ its .qb toggle), _deptAvgST, globalReapportion, _fmBandTxt, and 28 lines of CSS no element uses (.aop-hint/-inp/-locked-row/-lock-tag/-ok, .qb/.qbtns, .saved-tag, .srch, .empty, .cs-lbl/-sep, .ni .ico, .cfd-count, .fm-hist li.fm-warn) - 227 lines. Each name was found only at its definition (onclick strings included). Page in the browser: 205 rows, AOP window opens and renders, month range, menus; console only the expected sign-in 401. BIS node tests pass; page surface: only those 12 functions gone, no id or handler changed. Outside copy kept byte-identical. Compare: identical.
- **Step 6 - outside the repo (quarantined, not in git):** the legacy pre-database `CLaude - New Projects/Tentative AOP Forecaster` copy (launch.bat and the AOP dev config no longer point at it), the Ver-1 `Calendar Engine`, the old SalesPlan app (backend, frontend, root scripts) - its data folders stay: MRP Cont %, PW-W Deviation and SOR Deviation are live engine inputs, Actual Sales / Attribute Master / New Departments / UDF Cont % + ASP are the user's workbooks - and the leftovers in the BIS working folder (old sync_server.py, NSO copy + .vbs, standalone prototype, lagan files, old CHANGELOG / test, GM master copy, data/, __pycache__); otb-plan-app.html, ml_study, AOP/ and the notes stay. Compare: identical.
- **Stale docs (user: "fix the stale docs too"):** SalesPlan/README.md rewritten for how it runs now (inside 8010 at /planning/, API under /api/planning/*, where every input comes from incl. the outside-repo workbooks, build + restart loop; the 8002 setup marked retired); Listing Delisting/README.md written (was only the old repo title); Listing PRD_ARCHITECTURE gets a "Current state" section (serve.py via Landing, today's tabs and data files; the Phase 2 section is labelled history), PRD_LOGIC marks the risk score as superseded by build_suggestions (rule v4.0), Listing HANDOVER gets a status note (data/listing paths, consolidate.py removed); docs/HANDOVER.md - one-address map, Keep Alive as the auto-start, Calendar's local_server / Local DB gone, AOP launch.json fixed, Sales Plan section (no 8002 installers, outside-repo inputs, the two "open bugs" that were already fixed), Store Master is a file not a tool, data/ contents, new 3.9 Additional tools, open items 1/2/4 struck; PROJECT-CONTEXT lists the STR Forecaster and the four factor models; CALENDAR_ENGINE_ARCHITECTURE; comments in Landing (proxy table, Re-Aligner / Listing notes), listing_delisting_sync (step order), calendar router / cluster_names, AOP db/editor, festivalData.js. Text only - no behaviour change (Calendar dist identical).
- **Sales Plan dev proxy -> 8010 (user: "repoint the sales plan dev proxy to 8010"):** `frontend/vite.config.js` proxies `/api` to the unified platform instead of the retired 8002 standalone app, so `npm run dev` (5175) runs against the real backend and data; sign in once at localhost:8010/login (host-only session cookie, sent to :5175 too). Checked: through 5175, /api/auth/me and /api/planning/dept-sales/plan-summary answer 8010's own 401 "Not authenticated" (signed out); the dev server starts clean. Build output unchanged (the proxy is dev-only). README updated.
- **Totals:** 6 steps, 1,176 MB quarantined in `Backups/declutter_quarantine_2026-10-12` (empty it when happy), 21 tracked files and ~420 lines of dead code removed in git. Not done (Unsure / not chosen): AOP sessions/ pruning, Sales Plan standalone main.py, the stale-docs pass (L-15), qa-runner spec, scheduled tasks (admin - "Platform Server 8010", "BIS Server 5050", "NSO Distributor Server", "AOP Server 8000", "Landing Server 7800").

### QA: STR Forecaster
- **Asked (user):** "run the qa on str forecaster too"
- Server 8085 up (Landing /str behind sign-in); str_engine self-check OK; uploads in use 5 (fixtures) / 6 (plan), 180 stores, 115 departments, displays TABLE / NON_TABLE, 279 articles, every season 60-180.
- API: rollups by division / department / cluster x department / department x display / department x display x article / season / tag x attribute - no band below 60 or above 180; values (display, season), editor cells 540 rows (All / TABLE / NON_TABLE, 180 editable), tags, Excel downloads (stores, tags, detailed 1.36 MB in 7 s); edit without sign-in refused (403); unknown layer refused.
- Rules on the live data: display split adds back (MDQ, fixtures, plan qty, plan Rs); article days never above the department's (every store-month); article stock never above its display type; peak only with a reason; every compared store has all 4 months; band rule 60-180 nearest 30, off floor 60. Articles hold 89.2% of MDQ (the cap).
- Page: table and layers (Display type, Article offered and added), no LY days column, figure columns Band / STR days / Plan qty / MDQ, Season tags toggle, no 90-180 text; editor Display type column with All / TABLE / NON_TABLE; calculation pop-up Regular | Peak-oriented (no Last year). Console only the expected sign-in 401. Nothing to fix.

### QA: Sales Plan + BIS (today's changes)
- **Asked (user):** "run the qa on sales plan and bis"
- Servers 7800 / 8000 / 8010 / 5050 up; Sales Plan, AOP, Calendar builds fresh; Sales Plan bundle has the New depts config button + banner and no optional New Depts step; Sales Plan new-dept routes present behind sign-in (401 unsigned).
- Tests: BIS node tests (attr_preserve, dept_split, factor_model, phase2), test_sync_server_ly, Sales Plan engine tests (new_dept_template, deviation_blocks, division_plan, mrp_reapportionment) pass. **Fixed:** `test_lfl_auto.py` was stale since `726074d` (Jul-Jun years) - it fed Apr-2024 / Apr-2025 dates that are outside the windows now; dates moved one year, passes (the code was right).
- BIS in the browser: factor table tabs, 4 named methods, history table, vs-ML row, every settings view incl. the per-division ML page; New departments 2 / 5 / 1 rows, no self references; buyer input held through another edit; main before / after ("edited here"), Undo exact; attribute keep-mix lands on the typed growth, comparison opens, Undo exact; Excel export 200. AOP check after two edits: 0.0000035 Cr residue (Rs ~35) - the old re-balance path leaves the same (0.0000047), inside the page's 0.01 L AOP check, not a regression. **Fixed:** the New departments table no longer asks /api/planning on BIS's own port (only logged a 404 before falling back). Console otherwise only the expected 401 from /api/auth/me (preview not signed in).

### New departments: 5 self-referencing KIDS rows removed
- **Asked (user):** "fix the self-referencing KIDS rows with proper reference depts" -> chose "Remove the 5 rows".
- KG_HIPSTER SET F/S, KI_AP_HIPSTER SET F/S, KGW_JACKET, KGW_PYJAMA and KB_T-SHIRT F/S each named itself as reference with New dept % = Ref dept % (120/120, 90/90) - a no-op (ty x (1 - r) + ty x r = ty). All five are established, active departments with their own LY (0.86 / 1.73 / 5.65 / 3.26 / 6.22 Cr), planned from their own LY x BIS growth. Removed directly from SalesPlan/backend/new_dept_mapping.json (backup: Backups/new_dept_mapping_before_kids_selfref_fix_20261012.json) rather than through Save & apply, which would have cleared any Attr / Base corrections for a change that moves no number. KIDS keeps its 2 real carves (KB_BABA SUIT TXTL H/S, KI_AP_BABA SUIT TXTL H/S). Then (user: "remove the LADIES self-referencing rows too") LWW_WINTER TOP (75/75) and LWW_KURTI SET (130/130) removed the same way (both active; backup Backups/new_dept_mapping_before_ladies_selfref_fix_20261012.json) - LWW_WINTER T-SHIRT still carves 50% from LWW_WINTER TOP, unchanged. No self-references left: KIDS 2, LADIES 5, MENS 1.

### New departments flow from BIS into the Sales Plan engine
- **Asked (user):** "link new departments in sales plan engine from the new department induction of the BIS. keep the rest of the information such as cont % or reference department true to the BIS table. Remove this from the optional section of the planning engine, as all the info will flow from BIS now" (chose "Move the table into BIS"); then "keep a config button if possible in the sales plan engine if the user wants to change the ref or cont % for the new department already flowing from the BIS so that they can see the results from their end".
- **BIS > New departments** (sidebar, replaces "Add Department"): division tabs with counts; per new department its reference department (picker of that division's BIS departments), New dept %, Ref dept %, Cont % and Mar-Jun values in Rs lakh - the BIS plan with the new departments carved out of their reference exactly as the Sales Plan engine does (same order; a new department already planned in BIS gets the carve on top, and says so); the adjusted reference row under each; warnings for a missing / inactive / self reference. Save & apply, Download template and Upload filled template go through Sales Plan's own endpoints (`/api/planning/dept-sales/new-depts`, checked there, plan regenerated); the planner's reference departments reload from the same list. Signed out or on BIS's own port it is read-only (BIS server `GET /api/planner/new-depts`, file order kept). The old BIS-only custom department pop-up stays one click away.
- **Sales Plan:** New Depts is no longer an optional engine (removed from the sidebar's optional list and the "what next?" pipeline after Generate Base Plan - the base plan already applies the list). A **⚙ New depts config** button on the Growth Matrix opens the same page as a config view (banner: the list flows from BIS; a change here shows in BIS too) with its store-level results. Final Results wording updated. One file for both: SalesPlan/backend/new_dept_mapping.json (15 rows today - KIDS 7, LADIES 7, MENS 1 - unchanged).

### BIS: Excel export with the before / after comparison
- **Asked (user):** "add the before and after comparison to the excel export too"
- Data › **Export to Excel** now downloads one workbook (.xlsx): **Plan** (the current view, as the CSV had it, numbers as numbers), **Before and after** (every department since the last save - Level / Division / Attribute / Department, Gr % before / after / change, Rs Cr before / after, change in Rs lakh, months changed, note; division and attribute rows in bold, buyer-entered departments moved without an edit in red; two explanation lines on top; frozen headers and filters) and, while Edit by attribute is open, **Attribute edits** (the pane's own before / after). The comparison pop-up has its own "Export to Excel" (that comparison only). Export CSV is still there (current view only), and is the fallback if the BIS server cannot be reached.
- Written by the BIS server (`POST /api/export/xlsx`, xlsxwriter, values only - text is never a formula; max 10 sheets / 200k rows). Checked: server test client (formats, "=..." text kept as text, empty request refused) and from the page (Plan 198 rows + Before and after 222 rows -> 33 KB workbook in 1.2 s).

### BIS: before / after comparison for the main Buyer's Plan
- **Asked (user):** "add the same before and after comparison to the main bis"
- New **Before / after** button next to Save. Before = the plan as last saved in this browser (or as the page opened if not saved yet; every Save starts it again); after = now. Same table as the attribute pane - division › attribute › department, Mar-Jun Gr % and Rs Cr before / after / change, months changed, and a note: edited here (typed in the main sheet, Use, lock, magnified editor), edited by attribute, changed by <plan tool> (Reset to AOP share, Re-apportion by LY Cont%, Clear all inputs, Re-seed from AOP, Load a saved version, Revert to AOP - also listed in the header), re-balanced (plain share), made active / inactive, buyer-entered - changed (red, a buyer department moved without being edited). **Undo all changes since last save** puts inputs, locks, buyer-entered flags and active / inactive departments back exactly.
- One comparison code for both views (`_attrCmpData` / `_renderAttrCompare` with `_cmpKind`), attribute-pane edits are remembered for the main view until the next save.
- Checked in the browser (nothing saved): one department typed to +20% + a MENS REGULAR attribute edit -> 40 departments changed: 1 edited here, 15 edited by attribute, 25 re-balanced, 0 buyer-entered moved, division total held; Undo restored every cell (0 differences). test_attr_preserve.js / test_phase2.js pass.

### BIS: buyer input preserved across main-sheet and attribute edits; attribute edits keep the mix; before / after comparison
- **Asked (user):** "if one edits in the main bis and then proceed to the attribute sheet and edits does it have a backward compatibility to preserve the buyer's input and accomodate the attribute changes and give it a proprt before and after comp ?" -> "build all three". (Before: an attribute edit set one growth on every department of the attribute, the division re-balance re-spread every unlocked department by LY share - buyer edits included - and there was no comparison.)
- **Buyer input held (`_divReapp`, the one re-balance every edit path uses):** departments a buyer typed (S.buyerSet) hold their value; departments still on the plain AOP share absorb the difference. Only when that is not enough (they would go below zero) does everything unlocked move together, each keeping its own growth mix, and a toast names the buyer-entered departments and months that moved. Phase 2 (`_phase2Edit`) first solves with buyer-entered months held too and keeps that when every month still lands on the AOP and every department keeps its block total; otherwise the old solve, with the same toast. Reset to AOP share / Revert / Re-apportion LY Cont clear the buyer flags first, so they behave as before.
- **Attribute edits keep the mix (`_attrScale`):** a Phase 1 attribute edit scales its departments' unlocked months by one factor so the attribute lands on the typed growth - a +15% / +5% pair stays apart (×same factor) - and Phase 2 does the same for one month. The attribute bar has "A change keeps each department's mix / sets every department the same" (localStorage bis_attr_mix; default keep the mix).
- **Before / after:** opening Edit by attribute snapshots the plan; Done (or "Before / after" any time) opens "Attribute edits - before and after": division › attribute › department, Mar-Jun Gr % and Rs Cr before / after / change, months changed ("every month +3.00 pts" or month by month), and a note (edited by attribute / re-balanced (plain share) / buyer-entered - changed (red) / buyer-entered - kept / locked - kept); "Only what changed"; Undo all attribute edits (back to the snapshot exactly) or Keep changes and finish. Leaving the attribute report keeps the edits.
- Checked: new `test_attr_preserve.js` (buyer department holds, plain share absorbs, fallback keeps the mix and reports, attribute scaling keeps the ratio, Phase 2 holds buyer months with AOP and block totals) plus test_phase2 / factor_model / dept_split all pass; in the browser a +20% buyer department held through a MENS REGULAR attribute edit (6.98% -> 11.98%), every MENS month stayed on AOP, the comparison showed 0 buyer-entered departments changed outside, and Undo restored every cell (0 differences).

### BIS Ridge regression (ML): one model per division, sell-thru and fill rate added
- **Asked (user):** "add sell-thru and fill rate as clues in the ml" and "make sure the performance is measured in their respective division and no cross division referncing is there in the ml concept"; chose "Hybrid: learn on 2026" (no sell-thru or fill-rate history exists before 2026 - the weekly sell-thru files, closing stock and stock snapshot all start in 2026).
- **Within division only (`ml_assist.py`):** one weighted ridge regression per division (MENS, LADIES, KIDS), each learnt only from its own division's departments, its penalty λ picked on its own earlier cycle (MENS 3, LADIES 300, KIDS 300); division labels removed; department size is now vs its division's middle department; the "similar departments" bands are per division (6 growth, 4 momentum); errors scored division by division. Isolation check (`python ml_assist.py --isolation`): scrambling LADIES' sales moved 56 LADIES factors and 0 MENS / KIDS. History part on 6 unseen cycles: MENS 16.03% vs 15.54% no factor, LADIES 22.46% vs 21.35%, KIDS 21.13% vs 20.03% (all three 19.48% vs 18.62%; pooled was 19.28%).
- **Sell-thru and fill rate (hybrid):** sell-thru = the BIS Mar-Jun'26 average weekly sell-thru (same file, weeks, stores and averaging as the BIS), fill rate = fill_rate.json, each as log(department / its division's middle department). Learnt per division on Jul-Aug'26 (the months after Mar-Jun'26) on top of the history part (its own view taken out first), penalty by leave-one-department-out, off where it does not help: MENS 13.95% -> 12.32% (fill rate ×1.105 per typical difference, sell-thru ×0.989), LADIES 24.52% -> 19.65% (sell-thru ×1.111, fill rate ×0.854), KIDS no help -> off. One window - weak evidence, the page says so. The BIS server's rebuild passes the same sell-thru file.
- **Page:** the Ridge regression (ML) column's Sell-thru and Fill rate rows now show their multipliers ("learnt on Jul-Aug'26 (LADIES only)"); History model row = the history part; the settings page shows the history part per division, the sell-thru / fill-rate table per division and what the history part learnt per division. History check table / all-departments table use the division's own bands. The ML snapshot on Save now carries the parts.
- The live plan is unchanged: the factor table was saved on Ridge regression (ML) at 10:08 with the 9 Oct check; Save again to take the per-division factors.

### BIS: Ridge regression (ML) is a usable 4th method; every method shows its model type
- **Asked (user):** "make the ml suggestion use able like the others." and "also give it a proper name of the models used"
- The ML column is now **Ridge regression (ML)** - a weighted ridge regression - with **Use this** and **Settings ›** like Matrix (rule-based lookup table), Weighted builder (weighted scoring model) and Continuous (relative-strength power curve); each column head names its model type.
- **Use this + Save:** the BIS server (`sync_server.py`) accepts mode `ml` and snapshots the history check's factors (ml_guarded per department, the raw model factor and its reasons, the check's date and test result) into factor_table.json - never from the request. The planner uses that snapshot (`_plannerFactor`), so refreshing the history check does not move the plan until a planner saves again; the settings page says when a newer check is available. Departments without like-for-like history stay neutral 1.00; Phase 2 months use the department's one factor. Divisions still land exactly on the AOP (checked: worst gap 2e-14 L).
- **Settings tab for it:** what the model is (penalty λ, cycles, damping and limits), its error on the 6 cycles it had not seen vs no factor (19.28% vs 18.62%, better in 1 of 6) and what it learnt (each input's effect for a typical difference, e.g. recent momentum ×1.063, department size ×1.049). Nothing to tune.
- The Suggested box still ranks the three BIS methods by their back-test (the ML's error comes from a different test) and says so; the "vs ML suggestion" gauge row stays.
- Checked with a test client on a temporary file: saving `ml` stores 209 factors within 0.8-1.2, a forged `ml` block in the request is ignored, switching back drops it. The live factor table was not changed (still Matrix).

### BIS: ML suggestion as a 4th column to gauge the three methods
- **Asked (user):** "i wanted ml to suggest me a 4th way if possible so that i can gauge the 3 existing models too"
- The Department preview table has a 4th column, **ML suggestion** (advisory badge): the history model's factor for the department (ml_assist.json: learnt from 12 past planning cycles - 25V26 growth, 2-year growth, recent momentum, size - with the BIS damping and 0.8-1.2 limits), worked through the same rows (new "History model (ML)" row, damping, division re-balance, department plan in Rs Cr, "For this department", "How it works" with its back-test: 19.28% vs 18.62% no factor on 6 cycles).
- New **vs ML suggestion** row under the three methods: this department (same way / other way / about level, and Rs L above or below the ML plan) and all departments (same direction where both move, average gap). Today: Matrix 20 of 76 (26%), Weighted builder 17 of 49 (35%), Continuous 46 of 71 (65%).
- Not selectable (no "Use this") and left out of the Suggested ranking - it has not beaten no factor on past cycles. Pop-up widened to fit four columns (min(1140px, 96vw)); the tabs bar no longer lets rows show above it.

### BIS: factor table moved to its own tab in the pop-up
- **Asked (user):** "move the factor table in a secondary tab in the same pop up" (the bands + 36-row Sell-Thru x LY Growth x Fill Rate table)
- The Planner's factor table pop-up has two tabs: **Department preview** (opens first - the department comparison, history check, all-departments table) and **Factor table & settings** (fill-rate line + Refresh, a Method switch Matrix / Weighted builder / Continuous with "(in use)", and that method's table / settings). "Settings ›" under each method in the preview opens the second tab on that method. Nothing about the factors changed; Save works from either tab.

### BIS: factor table - history check as a comparison table with bars
- **Asked (user):** "can i visually see ML concept changes in the factor table and ensure that the working is simplified for others to understand similar to the table comparison in factor table ?"
- "What sales history says" is now a table like the department table above it: the method in use first (its factor and Rs effect after the division re-balance = the yardstick), then one row per history signal - 25V26 growth, Recent momentum, Model (all signals together) - with what the signal means in one line, this department's value, the band of similar departments in past cycles, what they got the next year (a bar around ×1.00, green up / red down, ≈ Rs effect on its own) and "Agrees with <method>?" (✓ same way / ⚠ other way - weak evidence / about level). A "= Verdict" row sums it up in one sentence. The all-departments table shows the same small bars on the method factor, both "next year" columns and the model.
- Advisory only, as before - nothing here changes a factor. Example (L_EW_KURTI, Matrix ×1.08 +25.1 L): recent momentum ×0.92 leans the other way; 25V26 growth and the model are about level.

## 2026-10-09

### STR Forecaster: Display type in the department editor
- **Asked (user):** "add display type to the department editor table too"
- New Display type column (with its search button and header menu). A store with one display type in the department = one row of that type, editable as before; a store with both = an editable **All** row (fixture edits are saved per store x department) plus read-only TABLE and NON_TABLE rows with their own fixtures, MDQ, plan qty and STR (e.g. MSE_R/N T-SHIRT H/S, ABD Mar: All 22 days, TABLE 26.2, NON_TABLE 12.2).

### STR Forecaster: Display type (TABLE / NON_TABLE) layer
- **Asked (user):** "Break it further into table and non-tbale" ... "display type"
- Both files carry the display type (fixture plan UDF-06, sales plan UDF06); it was summed per store x department. Now kept per row: migration `a3d8e1f5c2b7` adds `display` to str_fixture_rows / str_plan_rows (in the PK); both files re-uploaded as uploads 5 (fixtures) and 6 (sales plan) - totals identical to uploads 1 / 4 (fixtures 221,169, MDQ 26.4M, plan Rs 508.6 Cr, 15.4M pcs); backups in `Backups\planning_inputs_*_before_display_type_20261009_1753.csv`.
- New row layer and filter **Display type**: each display type gets its own fixtures / MDQ (its fixture-plan rows) and planned Rs / qty (its plan rows; LY by the plan share), so its STR is its own (e.g. MSE_R/N T-SHIRT H/S: TABLE 41.5 days, NON_TABLE 30.0, department 37.7). Department totals unchanged. Articles now split inside their display type and are still capped at the department's days in each store and month (0 of 208,280 rows above). Excel adds a "display type" column.

### STR Forecaster: every season on the 60-180 band range
- **Asked (user):** "range for all tags seasonality is 60 -180 remove 90 - 180 range from wherever it was the minimum"
- Off months were 90-180; now peak, normal and off all band 60-180, so the season no longer moves a band - it stays as a tag (Peak / Peak ✦ / Off) and drives the peak-oriented suggestion. The checkbox is now "Season tags" (shows / hides the tags); page note, popup range and matrix title updated.

### STR Forecaster: article STR days vary by the article's own performance, capped at the department
- **Asked (user):** "there can be variation in STR days in Article name ... it can be on the basis of its own performance in a cluster or store ... but yes it should be capping to the original STR decided on Department"
- An article's fixtures and MDQ now follow its cont % (planned qty) in its AOP cluster that month; its selling rate stays its own store plan. Days = department days x cluster cont / store cont, capped at the department: stock share = min(store cont, cluster cont). An article planned to sell faster in a store than across its cluster holds fewer days; none holds more than the department's days in that store and month (0 of 193,519 rows above; 45% below, median = the department). The articles together hold 93.9% of the department MDQ (the rest is stock the cap does not hand out). Stores without an AOP cluster or without an article plan keep the plain store / chain share. LY is still split by the store share. Excel adds "article cont % in its cluster" and "stock share". In roll-ups an article can sit above its department's average (43 of 2,548 cluster x department x article rows) when it is planned mostly in the stores where the department itself runs slow.

### STR Forecaster: LY days column removed from the main table
- **Asked (user):** "remove the LY days column from the main table too"
- The forecast table shows Band, STR days, Plan qty and MDQ per period (4-month avg and each month); the department editor's band cell shows the band, season badge and actual STR days only. The Excel still carries the last-year columns.

### STR Forecaster fix: article split by each store's planned QTY cont %
- **Reported (user):** MSE_R/N T-SHIRT H/S Mar'27 - article MDQ shares (19.9 / 46.2 / 31.9 / 2.0%) did not follow the plan (32.8 / 47.1 / 19.2 / 0.9%). "Bifurcate each stores' plan cont % on month and take that cont % to divide the MDQ and Fixtures as per their store x month x dept x art name share"
- Cause: the split used each article's share of the department's planned sales VALUE (Rs); cheap articles (01-EPP) are a bigger share of pieces than of rupees, so they got too little MDQ. Now fixtures, MDQ and LY are split by the article's share of the department's planned QTY in that store and month (Rs share only where the store-month plan has no qty; chain share where the store has no article plan). In each store x month the MDQ share now equals the qty share exactly; the chain total follows within a fraction of a point (01-EPP 32.78% qty / 32.50% MDQ, 02-ECO 47.12 / 47.27, 03-REGULAR 19.20 / 19.31, 04-PREMIUM 0.91 / 0.91 - the small gaps come from stores having different MDQ per piece). Department totals unchanged.

### STR Forecaster: Last year column removed from the calculation table
- **Asked (user):** "remove the last year numbers in the table those are baseless" (the circled Last year column of the info table)
- The click popup's table is Regular | Peak-oriented only; the "last year: N store-months" note is gone from "Based on". Season, season index, festivals and the rule stay below.

### STR Forecaster: hover messages removed; detailed calculation table
- **Asked (user):** "remove the hover message now" and "make the tabular form info as detailed as it can be. Make sure it gives a good detailed view as earlier for all calculations. Donot clutter it though"
- The hover texts on band cells, Peak / Off badges and the band-table headers are gone (the click popup carries the working).
- The click popup is one table with three columns - Regular | Peak-oriented | Last year - and a row per step: selling rate (whose plan / which peak run, planned ahead or ended / which LY month), qty and days, qty per day, MDQ (average per month; LY on the fixture file), STR days, nearest 30, range (and why: peak / normal 60-180, off from 90), suggested band (and the 60-180 base band when different), sell-thru at MDQ. Below it: Season (tag and reason), Season index (vs the window and vs the year), Festivals (each festival's days and lift at store level), and a one-line rule. Store-month cells also show MDQ = fixtures x qty per fixture (edits noted) and where the planned qty comes from.

### STR Forecaster: festival lift per festival (Bihu for all N. East); search buttons on the department editor
- **Asked (user):** "Bihu is there in NE as a whole not just NE(P) so why only Peak season for NE(P) and not the other one" and "add the same search filter to the department editor table"
- Cause: the festival lift was pooled per AOP cluster x department over all Mar-Jun festivals; NE - (NP) has 2 stores with history, so it leaned on the chain lift (Holi / Eid dominated, no Bihu) - x1.40 vs x2.65 in NE - (P) - and April did not stand out. Now each festival has its own lift per department, learnt from every store whose calendar has it (str_season.festival_lift: festival-day sales per open store-day / the same stores' other Mar-Jun days, 2022-25; few stores lean on the department's pooled lift; clipped 0.5-3), and a month's uplift = sum over its festivals of days / month days x (lift - 1). R/N T-shirts: Bihu x2.85, Holi x1.63, Eid al-Adha x1.61, Eid al-Fitr x1.22, Rath Yatra x0.95. NE - (NP) R/N T-shirts is now Peak (festival) in Mar and Apr like NE - (P); NE - (NP) Apr: 62 of 109 departments peak. Popups / Excel show each festival's days and lift ("Bihu 8 days x2.85").
- Department editor: Store and Cluster search buttons above the table (same menu as the headers: type, tick, type again to add), "N of M stores shown", Clear.

### STR Forecaster: search-driven picking in every filter
- **Asked (user):** "if i filter something by typing and i click on it, it should be the default and add a multi selection by typing norm in the serch filter too"
- In every filter menu (hierarchy chips and column menus): with a search typed, the first tick makes that value the only one selected; further ticks - after the same or another search - add to it (multi-select by typing); Enter or Select all picks every match of the search, None drops them; without a search, ticks work as before. The menu shows "N of M selected" and the match count; every value is searchable (the list shows the first 500 matches).

### STR Forecaster: Excel-style column menus; peak-oriented plans ahead to the peak; peak needs a reason
- **Asked (user):** "incuclcate filter and sort functions like theyr are in excel spreadsheets"; "peak should inculcate future stock days on the basis of peak month + its effective month(s) so that we can plan better in advance till the festive period" / "if the peak has ended then it should revert to its regular monthly STR suggestion"; "differentiate peak only if the festival is there or high sales is recorded as per the yoy avg"
- Every column of every table (forecast, department editor, Store mapping, Department tags) has a menu: Sort smallest-largest / largest-smallest (A-Z / Z-A for text), Clear sort, a Number filter (=, !=, >, >=, <, <=, between, top N, bottom N) or Text filter (contains, does not contain, begins / ends with, equals, does not equal), a searchable value list with Select all / None, and Clear filter. Filtered columns are highlighted; Clear sort & filters resets all.
- Peak-oriented suggestion: a month before or inside a peak run (consecutive peak months of that row, festivals included) is sized at the run's planned selling rate (its qty / its days) - planned ahead of the festive period; after the last peak it is the regular suggestion again ("the peak ended in Apr'27 - back to the regular suggestion"). E.g. UP 1 MSE_BERMUDA Mar'27 (off, regular 90) -> peak month Jun'27 planned ahead: 42,630 / 2,010.9 = 21.2 days -> 60.
- Peak needs a reason: festival days in the month (with a sales lift) or festival-free history >= 1.15x the department's average month of the year (2022-25); otherwise normal. Roll-ups: peak only when most of the plan has a reason. Peak rows now: festival + high sales 7,475 / high sales 6,091 / festival 1,447 (757 cluster x department peak months). Hover and Excel show the reason.

### STR Forecaster: sales plan with article names; fixture plan split to articles by cont %
- **Asked (user):** "replace the sales plan sheet with this one it has article names in it" (and: "break the fixture plan as per the sales plan imported and make the fixture plan as per the Cont % of sales plan")
- The user's new "MAMJ'26 - Sales Plan.xlsx" (ARTICLE NAME per row, e.g. "02-ECO [KB02]"; 279 articles in the compared stores) is the active plan (upload 4, +12 months; uploads 2 and earlier kept for roll-back; backup of str_uploads / str_plan_rows in Backups before the change). Totals equal the previous plan (15,419,386 pcs, Rs 508.6 Cr), so every STR figure is unchanged (All 54.54 days).
- Migration f7a2c9e4b1d6: str_plan_rows.article (NOT NULL DEFAULT '', part of the primary key). read_sales_plan keeps the article; the department split (old names) keeps it too.
- New Article layer and search filter: a store x department x month's fixtures, MDQ and last year's sales are split by each article's share of the department's planned sales (Rs) in that store and month (store's own plan, else the chain's; the article's own planned Rs / qty). Adds back exactly to the department (e.g. KB_BABA SUIT DNM H/S MDQ 4,23,300 = ECO 1,01,156 + REGULAR 2,50,986 + PREMIUM 71,158; days 43 / 73 / 88). Excel adds article, cont % and source columns when Article is a layer or filter. The prepared MRP-mapping module str_article.py is removed (articles come with the plan).

### STR Forecaster: cluster count table on Store mapping; article split prepared
- **Asked (user):** "add a cluster count table similar to the STR main page" and "I will give an Article name Sheet too so you can break the fixture plan as per the sales plan imported and make the fixture plan as per the Cont % of sales plan. Be ready with other things in the module, keep it handy"
- Store mapping tab: a Cluster x status count table (Mapped - compared / Month missing / Sales plan only / Fixture plan only / Total, plus All); clicking a count filters the store list to that cluster and status, "Revert" restores the list.
- New STR Forecaster/str_article.py (not wired into the page or DB yet): read_plan_detail keeps the sales plan below department (MRP, ATTRIBUTE, ATTRIBUTE 2, UDF06 TABLE / NON_TABLE - 414,240 rows in MAMJ'26, 65 MRPs); read_articles reads DEPARTMENT + ARTICLE plus any link column (MRP / ATTRIBUTE / ATTRIBUTE 2 / UDF06) or an own CONT % column; split() gives each store x department x month fixture row per article with fixtures / MDQ x the article's cont % of the plan (store's own plan, else chain, else sheet CONT %, else equal; unclaimed plan -> "(other)") so totals always add back. Self-check: python str_article.py.

### STR Forecaster: Store mapping tab; Regular vs Peak-oriented side by side in the popup
- **Asked (user):** "also add the mapped and unmapped store list tab in the app just like Department Tags" and "i need complete info on the peak oriented subject and remove duplicacy sentences, also from where is the 21.2 pcs coming ? How about if i click and the pop up shows side by side comparison for peak and Regular ones"
- New "Store mapping" tab: every store in the fixture plan or the sales plan with its status (Mapped - compared 180, Month missing 9, Sales plan only 7, Fixture plan only 6), AOP cluster, months in each file, what is missing, MDQ and plan; sortable / filterable; Excel export (GET /api/stores/download). Built in str_engine.build (info.common.store_map).
- Calculation popup rebuilt: a Regular | Peak-oriented table - selling rate source, planned qty and days, qty per day, MDQ, STR days, range, suggested band, sell-thru at MDQ - then Season, Festivals and Last year once each (repeated sentences removed). The peak column shows where its rate comes from, e.g. KI_AP_JEANS NE - (P) Apr'27: busiest planned month Mar'27 = 656 pcs / 31 days = 21.2 pcs/day -> 1,600 / 21.2 = 75.6 days -> 90 vs regular 215.4 -> 180.

### STR Forecaster: peak-oriented STR suggestion in the click message
- **Asked (user):** "i want a peak oriented separate STR too as a suggestion from which i can differ from the regular suggestion of yours. Keep the suggestion in the message which appears on the click."
- Every calculation popup (any level, and the store x month cells of the department editor) now shows a "Peak-oriented suggestion" under the regular band: the same display stock sized for the row's busiest planned month - days = MDQ / (that month's planned qty per day), band = nearest 30 within 60-180 - with the regular suggestion beside it. E.g. a NE - (P) store's R/N T-shirt May: regular 120 days (off month, 112.7 days) vs peak-oriented 60 days (42.5 days at April's rate).

### STR Forecaster: Season chip in the Rows bar
- **Asked (user):** "add a season filter chip to the Rows bar too"
- Season (Peak / Normal / Off - each cluster's own, festivals included) is now a chip like Cluster / Department / Store: drag it in as a layer (e.g. Season > Cluster > Department: normal 97.8 lakh pcs planned, off 15.1 lakh at band 90, peak 28.2 lakh) and its search filter picks one or more seasons. The separate season dropdown is gone - one place to filter. Server: season is a rollup layer / values key / Excel drill-down column.

### STR Forecaster: search filter on every hierarchy; dynamic cluster season tags
- **Asked (user):** "INDIVIDIUAL SEARCH FILTER MISSING ADD THAT FOR EVERY HIERARCHY" and "I see generic peak tags in 100/ 100 department clusters. I want the tags to be dynamic which in terms will point to the cluster's performance and thierrespective festive period and their performacne if it was peak or not"
- Every hierarchy chip in the Rows bar (Cluster, Department, Store, Division, Tag, Attribute - shown as a layer or not) has a search filter: search box, All / None, multi-select. Filters apply to every level, the All row, the band table and the Excel; the chip shows how many values are picked; "Clear sort & filters" resets them. The separate division / cluster dropdowns and the top-layer header filter are gone (one place to filter). Server: filters take several values; GET /api/values?key= lists a hierarchy's values.
- Season tags: against the whole year every summer department was "Peak" in Mar-Jun. The tag now compares a month with the same cluster x department's average month of the plan window (Mar-Jun), festivals included, so it shows which months stand out for that cluster: across cluster x department x month 1,951 normal / 944 off / 766 peak (was nearly all peak). "Peak ✦" = festival-driven (most of the planned qty in months with festival days). Hover gives the window multiple and the whole-year multiple (e.g. "Peak (festival): sells 1.33x its average month of Mar'27-Jun'27 ... - 2.90x its average month of the whole year"). Off months keep the 90-day band floor. Excel: year index and window index columns.

### STR Forecaster: peak keeps the 60-180 range; hover text explains every band
- **Asked (user):** "make ranges fall under 60 to 180 scale" (chose "Peak 60-180, Off 90-180") and "if any reasonable hover message can be there to make others understand of the choice you took based on data"
- Season band limits: peak 60-180 and normal 60-180 (the base rule), off 90-180. An overstocked peak row now shows its real band (e.g. 169 days -> 180, was capped at 90). Department counts by 4-month band: 60:65, 90:19, 120:9, 150:5, 180:13, no band 4.
- Hover on any band: the days of cover, the nearest-30 rounding, any limit applied and why (off months start at 90), and the season reason ("this department sells 1.79x its average month here - cluster sales 2022-25, festivals included; peak = 1.15x or more, off = 0.85x or less"). Hover on Peak / Off badges and on the band table headers too.

### STR Forecaster: season filter, cluster-led STR with Mar-Jun festivals, detailed Excel
- **Asked (user):** "1.) i also need a peak/ normal / off season filter on the tab. 2.) also i need the cluster to act as a cornerstone for STR allocation, different Clusters can be having different STR for same departments as per their off, normal or in season capping for the department. Take festivals falling in MAMJ into account" and "also make sure the excel gives me a detailed version not just a summary excerpt like what i preview on the front end"
- Season filter (All / Peak / Normal / Off) beside division and cluster: keeps only the store x department x month rows in that season; table, All row, band table, Revert and Excel follow it.
- Cluster first: default rows Cluster > Department > Store. Season index now = the cluster's festival-free curve x (1 + festival days in the month / days x (festival lift - 1)): festival days from each store's own calendar cluster for the forecast month (Mar'27 Eid al-Fitr + Holi everywhere, Apr Bihu in N. East, May Eid al-Adha in Kashmir, Jun 30 Rath Yatra in Odisha / WB); lift = sales per open store-day on Mar-Jun festival days vs other Mar-Jun days, 2022-25, per AOP cluster x department (leaning on the chain with few stores, clipped 0.5-3). So the same department can be peak in one cluster and normal / off in another and gets that cluster's band limits (e.g. R/N T-shirts NE - (P): Mar index 5.2, Apr 3.9 with Bihu, May 1.2). Popups list the festivals and show festival-free index -> festival-adjusted index.
- Excel (detailed): Read me (how each figure is worked out, filters, season build); STR detail = every store x department x month with 36 columns (fixtures, density, MDQ, plan Rs / qty and source, LY price / qty / Rs, qty per day, STR days, LY days, season base, festival days + names, festival lift, season index, season, season band, base band, LY band, STR %); Drill-down = the page's layers fully opened (every level, 4-month + each month, 13 measures each); By month = long format per cluster / division / department / cluster x department / store. Follows the filters and the layer order.

### STR Forecaster fix: no band under 60 days in peak months
- **Reported (user):** "i found a bug - why is 30 days STR being suggested where min 60 Days - max 180 days is capping"
- Cause: the season-aware band's peak limits were 30-90 (my default, never confirmed), which broke the user's 60-day minimum. Peak is now 60-90, normal 60-180, off 90-180, and str_band clamps every season inside BAND_MIN-BAND_MAX (60-180) so a season can never go outside the user's range. Checked: every roll-up level now has bands 60 / 90 / 120 / 150 / 180 only (e.g. KG_TEES in JH, OD - (P): 42 days, peak -> 60). Self-check asserts no band under 60.

### STR Forecaster: Tag / Attribute columns removed (the layers replace them)
- **Asked (user):** "tag and attribute are duplicate features check"
- The Tag and Attribute columns in the forecast table duplicated the new Tag / Attribute row layers (and were blank on every non-department row), so the columns are gone; group, sort and filter by them with the layers. The Department tags tab and the Excel tag / attribute columns stay.

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
