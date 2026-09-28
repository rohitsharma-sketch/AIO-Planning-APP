# OTB Plan App — Changelog

> From 26 Sep 2026 changes are logged suite-wide in [../CHANGELOG.md](../CHANGELOG.md).

---

## 2026-08-14 — Buyer's Plan: Division Tabs, Growth Lock & Re-apportioning

### What changed

**1. Division tabs** — `[ALL] [MENS] [LADIES] [KIDS]` tab strip above the KPI strip in Buyer's Plan and Plan Summary views. Clicking a division filters the table to that division only and groups sections by their attribute (e.g. REGULAR, OCCASIONAL, HVY WINTER). Clicking ALL restores the full cross-division view.

**2. Growth input highlighting** — All 920 growth% inputs now wrap in a `.gi-wrap` with a lock icon (🔓/🔒). Visual state:
- Positive growth → green border/background (`.gi.has`)
- Negative growth → red border/background (`.gi.neg`)
- Locked cell → grey, read-only (`.gi.lk`)

**3. Auto-recalibration** — TY recalculates immediately on every growth% change (unchanged from before; confirmed working).

**4. Per-cell lock toggle** — Clicking the 🔓 icon next to any input locks that cell (`S.locked` Set). Locked cells render as read-only grey inputs with a 🔒 icon and are excluded from re-apportioning. Locks persist via `saveState`.

**5. Re-apportioning within div+attr group** — When a growth% cell changes, all unlocked siblings in the same division + attribute group automatically adjust to maintain the attr-level AOP target (attr's proportional share of division AOP by annual LY weight). Algorithm:
- `changedTY` = new growth applied to changed section's monthly LY
- Locked siblings' TY held fixed
- Remaining budget distributed to unlocked siblings proportionally by their monthly LY weight
- Only applies to AOP months (mi = 11, 0, 1, 2); non-AOP months are unaffected
- Requires AOP to be locked

**6. Revert to AOP** — Each attribute-group header (visible in divTab mode) has a `↺ Revert` button calling `revertToAop(dvId, attr)`. Resets all unlocked cells in that div+attr group back to their AOP-seeded growth% (`S.aopSeeds`). Does not affect locked cells. LY and AOP targets themselves are never modified.

**7. `S.aopSeeds` snapshot** — `seedPlanFromAop()` now also writes to `S.aopSeeds` (keyed `secId__mi`) so the revert target is always the AOP-seeded value, not the current user-edited one. Auto-seed on first load also populates `aopSeeds`.

### New state fields
| Field | Type | Purpose |
|-------|------|---------|
| `S.locked` | `Set<string>` | Keys (`secId__mi`) of locked cells |
| `S.aopSeeds` | `Object` | AOP-seeded growth% per key, for revert |
| `S.divTab` | `null \| 'mens' \| 'ladies' \| 'kids'` | Active division tab |

### New functions
`setDivTab(id)` · `toggleLock(k)` · `reapportion(secId, mi)` · `revertToAop(dvId, attr)`

---

## 2026-08-14 — Buyer's Plan: Actual LY Fix + AOP Re-seed

### What changed

**1. `DEPT_ACTUAL_LY` constant added** (before `const DVDATA`)

Embedded actual monthly LY by division for the AOP period (Mar–Jun 2026), derived by summing the store-wise parquet actuals from `STORE_ACTUAL_LY` by department. Format: `{ kids: {11,0,1,2}, ladies: {11,0,1,2}, mens: {11,0,1,2} }` in Rs. Crore.

**2. `buildRows_dept()` updated — proportional distribution of actual LY**

Previously, section LY was computed as `annual_LY × SEA[mi]`, which overestimated the 4-month AOP period (465.5 Cr vs actual 388.75 Cr). Now, for months 11/0/1/2, each section's LY is distributed proportionally from `DEPT_ACTUAL_LY[divId][mi]` using the section's weight within its division annual total. SEA fallback still applies for all other months.

**3. `seedPlanFromAop()` updated**

The re-seed function also used the old SEA-based `divLYMon`. Fixed to use `DEPT_ACTUAL_LY[dv.id][mi]` directly for months where actuals are available, so re-seeding correctly targets `growth% = AOP / actual_LY - 1`.

**4. Action required: re-seed plan from AOP**

After the LY baseline changed, previously saved growth% inputs (calibrated against the old 465.5 Cr LY) produce the wrong TY. Click **"Seed Plan from AOP"** in the app to recalibrate all 920 inputs against the corrected 388.75 Cr LY — this sets growth% = AOP_target / actual_LY − 1 per month per section.

### Expected numbers after re-seeding (Buyer's Plan, Mar→Jun 4mo)

| Division | LY Actual (Cr) | TY Plan (Cr) | Growth |
|----------|---------------|--------------|--------|
| MENS     | 139.52        | 162.95       | +16.8% |
| LADIES   | 122.97        | 124.78       | +1.5%  |
| KIDS     | 126.25        | 133.06       | +5.4%  |
| **Grand Total** | **388.75** | **420.79** | **+8.2%** |

Before re-seeding: TY shows ~353 Cr / −9.2% (old growth% × new LY — incorrect).

---

## 2026-08-14 — Store Summary: Actual LY Data + LFL Grand Total Fix

### What changed

**1. `STORE_ACTUAL_LY` constant added** (before `const STOREDATA`, line ~891)

Embedded actual store-level LY sales for the AOP period (Mar–Jun 2026) for all 148 LFL stores, sourced from store-wise parquet data (KIDS + LADIES + MENS, converted from Lakhs to Crore). Format: `{ 'STORE_ID': { 11: Cr, 0: Cr, 1: Cr, 2: Cr } }` where `mi=11=Mar, 0=Apr, 1=May, 2=Jun`.

Previously, store LY was estimated using annual LY × seasonality index (`SEA[mi]`). Now actual monthly values are used for these 4 months; SEA fallback still applies for any other month.

**2. `buildRows_store()` updated — LFL-only LY for region & grand totals**

Added separate `rLYlfl` / `gLYlfl` accumulators that only include stores where a TY plan exists (i.e. LFL stores). Region headers, region totals, and Grand Total now use LFL-only LY, making growth % apples-to-apples against TY scope.

NSO stores (21 stores) still appear as individual rows showing their own LY for reference, but are excluded from region and grand roll-ups.

**3. `cellVal` `'ly'` case updated**

Now passes `row._lyMo` to `monLY()` so per-month LY cells in the store detail view show actual parquet-derived values instead of SEA estimates.

### Verified numbers

| Region | LY (LFL, Cr) | TY Plan (Cr) | Growth |
|--------|-------------|--------------|--------|
| CENTRAL | 7.45 | 7.79 | +4.6% |
| EAST | 183.00 | 196.83 | +7.6% |
| NORTH | 177.39 | 193.17 | +8.9% |
| NORTHEAST | 21.02 | 22.96 | +9.2% |
| **GRAND TOTAL (LFL)** | **388.86** | **420.75** | **+8.2%** |

NSO store LY (excluded from totals): 33.01 Cr across 21 stores.

---
