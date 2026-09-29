# RS Planning Suite — Changelog

Suite-wide changes across Calendar → AOP Forecaster → Buyer's Input Sheet (BIS) → Sales Plan.
Newest first. Each entry names its commit.

---

## 2026-09-29

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
