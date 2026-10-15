# RS Planning — Rule Book (the default rules of every engine)

User, 15 Oct 2026: *"Keep the different rules in the iteration for planner growth and keep the rules in generic rule book
for the engines. Make sure that every step is in accordance to the sales plan manual which is shared. So make it all the
rule engines in the system for future prospects also by default."*

**The manual** = the colleague's working file *"MAMJ'27 DEPARTMENT - AOP (NEW APPROACH) - FOR BUYERS INPUT - UPDATED.xlsx"*
(DEPT INPUT: D department, DO planner growth, DR buyer growth, DS / DT new-department reference + cont %; COMPARISON:
the department plan per SSG cluster x P1 / P2, BK:BR; the AOP sheet: store x division x P1 / P2) and its back-working
*"MAMJ'27 DEPARTMENT - AOP (NEW APPROACH).xlsx"* (MAIN DATA - 1, FACTOR - 1).

Every rule below is **on by default** in the engines named, and the run-through follows the manual as closely as it can unless the user changes a rule (user, 15 Oct 2026). A rule changes only on the user's say: change it here,
in the code, and in `CHANGELOG.md` together. Each BIS iteration also keeps the rules it was saved under (rule B10).

Check that the system follows the manual: like-for-like apparel Mar-Jun = AOP in AOP Forecaster, BIS and Sales Plan
(rule X1), and the Sales Plan by department within 0.2 L of the manual's COMPARISON sheet (rule X2) — 15 Oct 2026:
43,188.03 L everywhere, 0.17 L by department.

---

## S — Stores

| # | Rule | Where |
|---|------|-------|
| S1 | **Like-for-like (SSG) stores** = the AOP Forecaster's LFL tags (`032 / 080 / 095 / 125 / 3 - Stores`, `FY26 - Q1..Q3`) — 148 stores. Ramp = `FY26 - Q4`, `FY27 - Q1..Q2`; NSO = `NSO`, `MAMJ-NSO`. | `engine_v3.LFL_TAGS`, `store_master.is_ssg` |
| S2 | **Store cluster, reference store and tag come from `Store Master/Store Master.xlsx`** (the store-master sync's source). Change the file, not only the database — the nightly sync puts the file's values back. 8010 caches the store master: restart it after a change. | `sync/store_master_xlsx_sync.py` |
| S3 | **A renamed store is one store**: the old code is an alias of the new one everywhere a store code comes in (lake, uploads, editors); the database holds only the new code. Today NLD -> NEG, KGP -> MKG. | `rs_common/stores.py` (`ALIAS`, `canon_store`) |
| S4 | GBG, GKT, GRK are in **UP 2 - (NP)** (as the manual). | Store Master.xlsx |

## A — AOP Forecaster

| # | Rule | Where |
|---|------|-------|
| A1 | The plan sits on one saved AOP version (today **Version 2 = publish 119**). BIS and Sales Plan read the publish stamped on BIS's last growth push. | `aop_publish_history`, `division_plan._bis_aop` |
| A2 | **Apparel total = AOP**: KIDS + LADIES + MENS of every plan month is the AOP in AOP Forecaster, BIS and Sales Plan. Division totals may differ between them. | rule X1 |
| A3 | A store's AOP is **overwritten by the AOP (Optional) overrides** (store x division x month) — they win outright over the engine's figure. To put a user's AOP sheet into a saved version without moving its LY bases: overrides into the database and into that version's session sheet (file time kept), re-run that session, re-save the version. | `engine_v3.build_df`, `db/editor.put_aop_overrides` |
| A4 | A forecast month shows once its base month (one year earlier) is **closed** (`closed_through` from the month-wise lake export). | `sync/common.get_closed_through` |

## B — Buyer's Input Sheet (BIS)

| # | Rule | Where |
|---|------|-------|
| B1 | **Buyer's growth** = the manual's DR: one % per department, flat over the MAMJ block (Phase 1 - Block). | BIS inputs |
| B2 | **Planner's growth = "Planner input"** (the manual's Factor 1, default method): per department x month, FACTOR-1[the month's sell-thru vs its division's — 8 deviation bands][MAMJ'26 sell-thru status — Low / Average / High / Excellent] = 0-30%; **no factor when MAMJ sell-thru <= 4% and the deviation averages <= 50% over Mar-Jul**; inactive = -100%. The other methods (Weighted, Continuous, ML) stay selectable; **Matrix was removed** (15 Oct) - a table saved with no method or 'matrix' reads as Planner input. | `factor_table.json` mode `factor1`, `SalesPlan/backend/engines/sellthru_factor.py` |
| B3 | **Buyer within ±3 points of the planner** is flagged, not capped. | Sales Plan check-up `buyer_band` (`BUYER_BAND_PCT = 3.0`) |
| B4 | **-100% buyer input = inactive** (the department goes to the Inactive sheet). An inactive department's LY counts, its plan is 0. | `_autoInactive100` |
| B5 | **Off-season departments are inactive**: a department whose attribute is out of season for the plan months is switched off, and back on when its season comes (PEAK SUMMER counts as SUMMER). Season per month = the Sales Plan's one rule: `SalesPlan/backend/season_attributes.json`, else SUMMER / OCCASIONAL / REGULAR for Mar-Jun; a month with no rule = every attribute in season. MAMJ'27: the PREWINTER / LT WINTER / HVY WINTER departments (77). | `_applySeason`, `/api/planner/season`, `plan_checkup.season` |
| B6 | **New departments** keep their cont % from the manual (DT) of their reference (DS); the reference is **not** cut: L_EW_SAREE_JAIPURI = 25% of L_EW_SAREE_FNCY, LW_U_ETHNIC DRESS = 35% of LW_U_DRESS, LW_U_CORD SETS = 10% of L_EW_KURTI SET. | `SalesPlan/backend/new_dept_mapping.json` (one list, edited from BIS → New departments) |
| B7 | **A new department with no LY of its own is a value row**: LY 0, plan = its % of the reference's plan every month, no growth of its own (CORD SETS). | `_ndNoLy`, `_secTy` |
| B8 | **Split departments keep their new names; the parent's growth is copied to the children.** | `DEPT_SPLITS` |
| B9 | **Every Save holds the apparel total on the AOP**: one factor a month over the three divisions' **unlocked** departments (locked tiles and locked divisions held - 15 Oct; the buyer's mix kept); divisions may end off their own AOP. Everything locked in a month = not capped there (a toast says so). | `saveState` -> `capToApparelAop` |
| B10 | **Each iteration keeps its rules**: planner growth method, AOP version, apparel = AOP, division locks, the season rule, off-season / inactive counts, the new departments — shown on the version picker. A save within 0.5 Cr of the loaded iteration updates it; a bigger change is a new iteration. **Every saved iteration is kept** (no cap - 15 Oct). | `_vlRules`, `_maybeSaveVersion`, `bis_plan_versions.MAX_VERSIONS = None` |
| B11 | Only **Save** sends the plan to the Sales Plan (opening the page sends nothing). | `pushBuyerGrowthLive` |
| B12 | **How a new department moves the others** (shown per department as "Buyer's input"): the new department is set first at its % of its reference's plan; the division goes back to its AOP and every **unlocked** department gives up plan x new / unlocked others; a locked month or a locked division stays as entered (the new department then adds on top). | `_ndSettle`, `_divRescale0`; described by `_inputWhy` |
| B13 | **The summaries are the Buyer's Plan**: Division / Department / Attribute summaries add up to it, division x month; the sidebar sync pill re-checks this, apparel = AOP, that the last Save reached the Sales Plan, and that the screen = the saved version. | `_syncChecks` |
| B14 | **Input tiles are drivers**: a department's Block Growth% tile keeps its input as typed / imported and no rule rewrites it; the plan's growth after the rules is the **Re-cal Gr%** column next to it (amber when it differs). Unlocked: the tile drives and the rules re-calibrate (re-balance to the division AOP, new departments, apparel cap). Locked: the plan takes the tile exactly and the rest of the unlocked plan re-calibrates around it. Inputs imported stay locked (15 Oct, user). | `S.drv`, `_recalWhy`, `toggleSecLock` |
| B15 | **Plan basis** (toolbar "Basis"): Buyer's input (the Block Growth% tiles) / Planner's input (the planner's growth per department x month) / **Blend - the default**, w% buyer + (100-w)% planner, 50/50 (one of the two where the other has none). Apply re-seeds every unlocked month from the basis, releases the import's division locks (cells you locked stay held), re-calibrates each division to its AOP and locks the basis; the tiles keep the buyer's text, Re-cal Gr% shows the plan, Save sends it to Sales Plan. A plan saved before 15 Oct shows Blend as the default but stays as imported until Apply (15 Oct, user). | `S.basis`, `applyBasis`, `_basisG` |
| B16 | **BIS buyers by division** (Users & access > BIS divisions; none ticked = planner). A buyer sees only the Buyer's Input Sheet (Landing shows only its card; Landing's server refuses every other app and action), only their divisions, Phase 1, and can type only the Block Growth% tiles; none of the guarded actions. Their Save ("Send to planner") sends their tiles for review - never to Sales Plan; a newer Save replaces their pending one. The planner: "Buyer inputs" in BIS -> Apply to plan (unlocks that division, sets the tiles, re-calibrates) or Dismiss -> Save sends the plan as usual. BIS versions and the factor table: planners only (`buyer_push`). (15 Oct, user.) Only the **Buyer** role is limited - divisions ticked for a Planner / Reviewer have no effect (shown as all). | `auth/rights.py` divisions, `auth/bis_submissions.py`, Landing `_buyer_refused`, BIS `BUYER` / `_bsubApply` |

## P — Sales Plan (department plan)

| # | Rule | Where |
|---|------|-------|
| P1 | **SSG LY = actual LY sales** of the same months a year earlier, store x department. | `dept_sales_engine` Step 1 |
| P2 | **P1 / P2 halves**: P1 = days 1-15, P2 = 16th to month end. LY split by the department's own half-month share in its SSG cluster (manual COMPARISON H:O), else the store's, else 50/50; plan half = LY half x BIS growth. A month whose LY sits wholly in one half keeps that split (share 0 or 1 - 15 Oct fix; they had been dropped). The SSG cap's month AOP = the AOP store plan's own total when the publish's 2-decimal division totals agree with it within rounding (`month_aop`). A non-SSG store's division x month splits P1 / P2 by its **month-mix reference** store's split on the AOP (manual AOP sheet Ref Name / STORE MASTER REFF_STORE_MONTH_MIX, kept in `aop_halves.json` month_ref / div_shares - the database has only REF_STORE, the merchandise-mix reference that its department mix follows); its departments keep their reference-plan shape inside it (`fit_halves`). | `ly_halves.json`, `actuals_manager.day_halves` |
| P3 | **Cap per SSG cluster x month x half over ALL divisions** on that cluster's AOP (sum of its SSG stores' AOP store plans, P1 share from the manual's AOP sheet); clusters scaled to the month's AOP. Division totals float. | Step 1b, `aop_halves.json` |
| P4 | **Store balance**: each SSG store x month x half = its AOP store plan; each (division, department) keeps its cluster total (RAS); negative-LY cells fixed; new departments tied to their reference. | `_store_balance` (Step 1c) |
| P5 | **New departments** carved at store level (rule B6), re-balanced per cluster x half. | `apply_new_dept_adjustments` |
| P6 | **Non-SSG stores** (NSO / Ramp / placeholders) = the AOP store plan x the reference store's department cont % (ref chain to an SSG store). | `grain_view._aop_by_store`, `store_group` |
| P7 | **Active departments** = BIS active and in season (rule B5); inactive ones are planned at 0. | `run_dept_plan` |
| P8 | The saved plan follows its inputs on its own (BIS growth, AOP publish, store master, LY): 8010 regenerates it within a minute of a change. | `refresh_saved_plan` |
| P9 | **Built on cluster (preview, not in use)**: each SSG cluster x department x fortnight plan (the same as P3-P4 give) goes to its stores by their **LY cont %** of the department in the cluster (no LY there: the store's share of the cluster's division LY, else equally); the cluster's MRP x display plan goes to the stores by a two-way fit seeded on each store's own LY on the merged MRPs (store department plan and cluster MRP x display plan both kept; a new MRP gets room by the store's LY cont %). Store -> cluster = the plain sum, so every cluster total is unchanged. Non-SSG stores as in P6. Shown next to the store-built plan in the Display Type tree ("Built on: Store / Cluster"). | `grain_view._cluster_built`, `display-view/*?build=cluster` |

## M — MRP, display type, quantity

| # | Rule | Where |
|---|------|-------|
| M0 | **The buyers' plan file ("for ASP MAMJ 2.xlsx") is the plan's article x MRP x UDF mix and the sole ASP file** (user, 15 Oct 2026). One import (Display Type → `POST /import/plan-file`) sets both. | `plan_file_mix.py`, `dt_asp.json` |
| M1 | **MRP x display type x article of a file department = the file's mix**, per half-month: a like-for-like store by its cluster's like-for-like rows, a non-SSG store by its **reference store's cluster**, the chain's where the file has no such cluster. Department totals stay the Sales Plan's (the file's own department totals are not used). Same split in Final Results (MRP / Display trees), the Display Type run and the chain MRP split (`effective_shares`). | `plan_file_mix`, `grain_view._mrp_index` / `_display_index`, `display_type_engine.run_plan` |
| M2 | A department the file doesn't have: **MRP Cont % = the re-apportioned LY sales on the MRP master in use**, the buyers' MRP file where picked; **display type %** = each store x department x MRP x month's own LY mix (store -> chain -> department). The check-up's Rectify rebuilds the re-apportioned shares for every department. | `mrp_plan_engine._load`, `display_type_engine.MIX_LEVELS` |
| M3 | **Qty = value / ASP, to 2 decimals (not whole pieces)** from the sole ASP file (its VAL / QTY on its new MRP / display type); every in-season value needs an ASP (check-up fails otherwise). | `display_type_engine.run_qty`, check `Qty (ASP master)` |
| M4 | **Article plan** = each store x file department x half's plan x the file's article x MRP x display share of its mix, at the file's grain (cluster x group x department x article x MRP x display x half) — downloadable (`GET /export/article-plan`). Check: inside every like-for-like cluster x department x half the split equals the file's (15 Oct: 39,314 rows, 0 differ). | `plan_file_mix.article_plan` |

## R — Rule change control (user, 15 Oct 2026: "i want foolproof rules and regulations intact, mrps can be variable and other rules too unless i add a rule or subtract a rule this should not be deviating on every iteration")

| # | Rule | Where |
|---|------|-------|
| R1 | The rules are this book. They change only when the user adds or removes one - then the code, this book and CHANGELOG change together, and the history line below records it. Nothing else changes a rule. | this file |
| R2 | **Inputs vary, rules don't:** BIS growth (typed / imported / basis), the AOP version, the MRP split and ASPs, the plan file's mix, new departments and their %, the store master, the Calendar sales, the manual's half-month inputs. A new iteration = new inputs through the same rules. | - |
| R3 | **Same inputs -> same plan**, every run: the saved plan is regenerated whenever an input file or table changes (the inputs key includes the half-month files), never on a timer or by hand edits. | `dept_sales_engine._plan_inputs_key` |
| R4 | **Final = passes everything:** Sales Plan check-up all pass; BIS sync pill green (summaries = plan, apparel = AOP, Sales Plan holds exactly this plan, screen = saved); and, when a manual is given, manual parity P1-P4 all 0.00. | X2, X3, BIS sync pill |
| R5 | **No pop-up without a change:** BIS's "not as saved" bar shows only when the plan's numbers or department inputs differ from the saved version (not for locks alone, never for a buyer). | BIS `_vlStaleCheck` |

## X — Reconciliation checks (run after every change)

| # | Check | Pass |
|---|-------|------|
| X1 | Like-for-like apparel per AOP month: AOP Forecaster = BIS = Sales Plan | equal to 0.01 L |
| X2 | **Manual parity** - `SalesPlan/backend/tools/manual_parity.py <manual.xlsx>`: P1 SSG cluster x department x month x half = the manual's buyers'-input plan (COMPARISON, block "CAPPED AT CLUSTER (BUYERS INPUT)"); P2 every store x month = its AOP sheet; P3 every non-SSG store x division x month x half = its AOP sheet; P4 the SSG total and each month. Columns found by header text, any months; a layout that doesn't match stops with the reason. `--import` loads the manual's half-month inputs (LY halves, AOP halves, month-mix references) first. | every cell 0.00 (15 Oct: 0 of 14,040 / 1,704 / 6,672 / 5) |
| X3 | Sales Plan check-up | pass (the ±3 point flag is a warning) |
| X5 | Sales Plan article x MRP x display split vs the buyers' plan file, like-for-like cluster x department x half | equal shares (M4) |
| X6 | **Rules in force** — every check-up records the rule settings the engines read (planner growth, AOP publish, season, new departments, ±3 band, plan file, ASP, MRP source) and logs any change with its time | `rules_log.json`; check-up line "Rules in force" |
| X4 | BIS vs Sales Plan by department | differs only by the cluster x half cap (Sales Plan) vs the chain-level apparel cap (BIS) — 172 L on 15 Oct |

---

### Rule history
- 14 Oct 2026 — the colleague's department method (cluster cap over all divisions, actual LY, store balance, ±3 flag): `f7b6ba3`, `638e82f`.
- 15 Oct 2026 — P1 / P2 halves `5ae7b3a`; Planner input (Factor 1) as a BIS method; apparel total = AOP; store alias `9282094`; AOP Version 2 = the user's store AOP (publish 119); off-season departments inactive + GBG / GKT / GRK in UP 2 `4ef726b`; CORD SETS value row `d6aeaa3`; defaults switched on (B2 Planner input, B5 season, B9 cap on Save, B10 iteration rules) and this rule book; the buyers' plan file as the article x MRP x UDF mix + sole ASP file (M0-M4). Later the same day: one version each (BIS "Plan Iteration - 01", Sales Plan "Final - matches manual (15 Oct)"); B12 / B13 described in BIS `8ec522b` / `f772c03`; Matrix removed from the factor table `f772c03`; P9 built-on-cluster preview.
