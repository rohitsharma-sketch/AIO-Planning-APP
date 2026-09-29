# Rule set — Re-phase one department's plan across months (store-level seasonality)

Derived from `LW_U_T-TOP Working.xlsx` (user's working file, 23–25 Sep 2026; 554 MB, 6 sheets) and verified
cell by cell against its saved values (29 Sep 2026). The workbook re-phases **LW_U_T-TOP**'s Sep–Dec'26 plan;
the rules below are written generically so any department / window can be re-phased the same way.

## 1. What the method does (one line)

Keep every store's **window total** for the department exactly as planned, but **re-split it across the months of
the window** by a store-level LY seasonality mix, then split each new store-month down to **MRP × display type**
by the old plan's mix. Everything outside the department or the window stays as it was.

## 2. Inputs and parameters

| Input | In the workbook | Grain |
|---|---|---|
| Old plan (value + qty) | `PSP Plan - 8th Aug` (the "Original" plan) | Store × Dept × MRP × Display × Month (Sep'26 … Feb'27 P1/P2) |
| LY sales of the **mix department** | `Approaches` AA:AF (pivot of Sep–Dec'25) | Store × Month |
| Store attributes | `Base - Dep` / plan columns | SSG TAG (SSG / SSG - ANG / OTHERS), REF (buddy store), REF OLD, ST TAG, Cluster |

| Parameter | This workbook | Generic meaning |
|---|---|---|
| Target department **D** | LW_U_T-TOP | the department whose months are re-phased |
| Mix department **M** | LW_U_T-TOP **F/S** | whose LY month shape is used (default M = D) |
| Window **W** | Sep, Oct, Nov, Dec (SOND) | months re-split among themselves |
| Locked months | Jan'27 P1/P2, Feb'27 P1/P2 | copied unchanged |
| Own-mix tags | SSG, SSG-ANG | stores that may use their own LY |

## 3. Rules

**R1 — Scope.** Only rows of department D change, and only in the window months. Every other department and every
month outside W is copied exactly. *Workbook:* the PSP plan's grand totals move by exactly D's changes
(Sep −246.13, Oct +93.69, Nov +96.73, Dec +55.71 L); Jan/Feb for D: 188.91 L before = after.

**R2 — Store window total is conserved.** `New_s,W = Σ_{m∈W} Old_s,D,m` for every store s.
*Workbook:* 303 stores, 772.77 L before and after, max per-store difference **0.0**.

**R3 — Month mix = LY month share of the mix department.** For a source store x:
`p_x,m = LY_x,M,m / Σ_{m∈W} LY_x,M,m` (0 if the store has no LY in W).

**R4 — Whose mix a store uses (reference cascade).**
1. SSG TAG ∈ {SSG, SSG-ANG} → the store's **own** mix;
2. otherwise → its **REF** (buddy) store's mix;
3. if REF has no LY → **REF OLD**'s mix;
4. if none → 0 (the Excel `MAX(IFERROR(...),0%)`).
*Workbook:* 120 stores own mix, 183 via REF / REF OLD; all 303 mixes sum to 100%.

**R5 — The mix department may be a proxy.** Use M ≠ D when D's own LY is too thin or shaped by a different season
to give a usable month curve. *Workbook:* LW_U_T-TOP's own SOND LY = 44.0 L, 67% in Sep (a summer-shaped tail);
LW_U_T-TOP F/S = 228.1 L with a real SOND curve (38 / 43 / 12 / 7%) — the file uses F/S. The choice of M is a
planner decision and must be recorded with the reason.

**R6 — Non-trading months are removed and the mix rescaled.** If a store is not trading in a window month (it opens
later / closes / is refitted), that month gets 0 and the store's remaining mix is scaled back to 100%:
`p'_s,m = p_s,m / Σ_{trading m} p_s,m`. *Workbook:* the 17 rows marked "Exception" in `Approaches` BB — 16 stores
with an old plan only in Oct (Sep = 0: not yet open, e.g. NS-63/64/65) follow this **exactly** (max diff 0.0000).
Generic: take trading months from the store's opening / closing dates (store master) or, failing that, from the
store's plan across **all** departments — not from D's plan alone (D can be 0 in a month for season reasons).

**R7 — New month value.** `New_s,D,m = New_s,W × p'_s,m`.

**R8 — Down to MRP × display type.** Within each store-month, split `New_s,D,m` by the old plan's MRP × display
share **of that month**. For a window month with no old plan at all (Nov / Dec here — D was not planned in winter),
use each row's **average share of the months that did have a plan** (`AVERAGEIF(<>0)` of Sep / Oct), then
**renormalise to 100%** per store (the workbook happens to sum to 1; the average does not guarantee it).
*Workbook:* 7,878 rows, every store-month equals `Base - Dep` exactly; no new value was left without a mix.

**R9 — Quantity.** `Qty = Value / ASP`, with ASP = the old plan's value ÷ qty for the same
Store × Dept × MRP × Display × Month; if that month had no old qty, the row's all-month ASP (the AOP Re-Aligner's
existing rule). The workbook's "Post … Qty" columns are still empty (see finding 3).

**R10 — Write-back key.** Join on `Store & Dept & MRP & Display` (the workbook's CONC-UDF key). Only D's rows are
replaced (`IF(DEPARTMENT = D, new, old)`).

## 4. Checks every run must pass (invariants)

| # | Check | Workbook result |
|---|---|---|
| C1 | each store's window total unchanged (R2) | 303 / 303, max 0.0 |
| C2 | each store's month mix sums to 100% (or the store has no plan) | 303 / 303 |
| C3 | MRP × display rows sum to the store-month value (R8) | exact, every store-month |
| C4 | department totals outside the window and all other departments unchanged (R1) | exact |
| C5 | every stored override (hand-typed mix) is explained by R6, or listed as an exception | 16 explained, **1 not (JHM)** |
| C6 | no store-month value without somewhere to land (no MRP × display mix) | 0 |

## 5. Findings in this workbook

1. **JHM** (SSG, own mix) is typed as Sep 60.4 / Oct 0 / Nov 25.4 / Dec 14.2%. R6 gives 52.5 / 0 / 26.6 / 20.9%.
   It also plans Nov / Dec while its old plan had no Oct — right if JHM is shut in Oct only (refit), but the numbers
   don't follow the rule. Needs the planner's confirmation.
2. **LW_U_T-TOP F/S** has 279 store rows with a 0 plan in every month: its LY is used as the curve (R5) but it is not
   planned itself. If part of LW_U_T-TOP's plan should move to F/S (the department split of 28 Sep), that is a
   separate step (department split), not this re-phase.
3. In `PSP Plan - 24th Aug`, the **Pre** block (new value for D, old for the rest) and the **App** block (the new plan
   read back per key from `Sheet2`, a pivot of the new plan) are filled; the **Post** block (final value + qty) has a
   single formula — the qty step (R9) was not done in the file. (App's `#N/A` is only on the blank-key subtotal row.)
4. Size: the workbook stores the full Store × Dept × MRP × Display plan twice (8th + 24th Aug, ≈2.7 GB of sheet XML)
   plus three pivot caches — the method itself needs only D's rows.

## 6. Where it fits in the suite

This is a **month re-phase** of an existing plan with store totals fixed — close to the AOP Re-Aligner's
"Existing department changes" method, but driven by a seasonality source instead of a revised file. It can be added
as a Re-Aligner method: inputs = the loaded original plan, D, M, W, locked months (the Re-Aligner's month locks),
the store master (SSG tag, REF, REF OLD, opening dates) and LY sales from the sales engine; output = the realigned
plan with checks C1–C6.
