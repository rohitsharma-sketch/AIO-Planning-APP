# Logic PRD — Listing/Delisting Impact Analysis

Scope of this doc: data/logic rules — what values mean, how source data is transformed,
dedup rules, the knowledge base schema. For layout/app-functioning/cosmetic changes, see
[PRD_ARCHITECTURE.md](PRD_ARCHITECTURE.md).

**Convention:** every future change to a logic rule, data transformation, or the knowledge
base schema gets a dated entry in the Change Log at the bottom of this file.

## Goal (as given 2026-09-21)
Listing data for the app should be taken from the knowledge base built from the
2023–2026 `Directories\<year>\Directory - Listing'YY.xlsx` files (themselves built per
[HANDOVER.md](HANDOVER.md) from the raw `.xlsb` allocation reports — that extraction logic
is unchanged and documented there).

## Current Logic (Phase 2, v1)

### Knowledge base build (`scripts/build_knowledge_base.py`)
- Input: the 4 existing `Directories\<year>\Directory - Listing'YY.xlsx` files (2023–2026),
  each row = one (STORE_NAME, DEPARTMENT, Month) combo with `MC_LISTING(Rev)` = `Y`/`N`.
- Output: `app/kb.json` with:
  - `months`: ordered list of all months present across all 4 years (`Jan'23` … the latest
    month in the 2026 file), chronological.
  - `stores`: sorted list of all distinct STORE_NAME values.
  - `departments`: sorted list of all distinct DEPARTMENT values.
  - `data[store][dept]`: a string, one character per entry in `months`, aligned by index —
    `Y` / `N` / `.` (no row found for that store×dept×month, i.e. store or department
    didn't exist / wasn't tracked that month).
- As of 2026-09-21: 61,258 distinct (store, department) combos, 282 stores, 271 departments,
  42 months (2023 is Apr–Dec only per the known Q1'23 source gap — see HANDOVER.md).
- Hard rule carried over from the extraction/consolidation scripts: the source directory
  files are already deduped 1 row per (store, dept, month) — the KB builder does not
  re-dedup, it hard-fails if it ever sees a duplicate key across the 4 files (should be
  structurally impossible since years don't overlap in month labels).

### Sales data build (`scripts/build_sales.py`)
- Source: RS sales data lake parquet at
  `\\10.0.1.85\Users\Citykart\Desktop\AI_WORK\INVENTORY AUTOMATION\data_lake\raw\rs_sales_19-_till_date\`
  (per user, 2026-09-21). Two files exist there (a 2026-08-17 and a 2026-09-05 export); same
  "periodic full re-export, always read the latest" pattern as the Calendar Engine day-wise
  source (see memory) — the script always picks the newest by the `_YYYYMMDDTHHMMSS` suffix
  in the filename, not both.
- Schema: one row per sale line, columns include `STORE_NAME`, `DEPARTMENT`, `BILLMONTH`
  (month-start timestamp), `SL_V` (sale value — the metric used), plus qty/tax/cost columns
  not currently used. `STORE_NAME`/`DEPARTMENT` values match the listing KB's naming exactly
  (verified: 3-letter store codes, `PREFIX_REST` department codes) — direct join key, no
  mapping needed.
- Same apparel-only 21-token scope as the listing extraction (`ALLOWED_TOKENS`, duplicated
  in this script rather than shared — see note below).
- Aggregation: sums `SL_V` per (STORE_NAME, DEPARTMENT, month), where month is matched to the
  **exact label string already in `kb.json`'s `months` list** (so `Sep'26` sales lines join
  to `Sep'26(Till Date)` in the listing KB) — rows for months outside the listing KB's range
  (2019–2022, i.e. before the KB's Q1'23 gap onward) are dropped, since the app's month axis
  is defined by the listing side.
- As of 2026-09-21: 740,842 store×department×month sales rows (13.08 MB `app/sales.json`),
  from 22.4M raw sale lines (8.2M dropped as non-apparel, 5.9M dropped as outside the KB's
  month range).
- Known duplication to clean up later: `ALLOWED_TOKENS`/`category_token` now live in 3 places
  (`extract_one.py`, `build_knowledge_base.py`'s upstream source, `build_sales.py`) — fine at
  this scale, but if the apparel scope list ever changes, all 3 need updating together.

### Delisting-risk score (`scripts/build_risk_scores.py`) — fixed in-season windows (2026-09-21 rework)
Business question: *which currently-Listed store×department combos look at risk of being
delisted soon?* Built as a static `app/risk.json`, same pattern as `sales.json` — no backend.
**Run this script AFTER `build_season_category.py`/`build_seasonality.py`** — it reads
`app/seasonality.json`'s per-department `season_category` field as its only input from that
file (the continuous `avg_sales_by_month`/`overall_avg_monthly_sales` seasonal-index math from
the previous rework is no longer used by this script at all).

This is a full replacement of the same-day continuous-seasonal-index rework (see Change Log for
that method and why the user rejected it too — a continuous ratio still let a bad recent month
partially "borrow" against an unrelated seasonal shape). The user's fixed business rule: a
department is either in-season or off-season for a given calendar month, full stop, and an
off-season dip produces **no signal at all**, not a dampened one.

**Fixed in-season calendar-month windows per `season_category`** (calendar months, not
year-specific — same window every year):
| `season_category` | In-season months |
|---|---|
| `regular` | always (no restriction) |
| `occasional` | always (no restriction — event/festival-driven, no natural calendar window; the safe default is "no seasonal exemption" rather than guessing at festival dates) |
| `summer` | Mar, Apr, May, Jun, Jul, Aug, Sep, Oct |
| `prewinter` | Aug, Sep, Oct |
| `lt_winter` | Oct, Nov, Dec, Jan, Feb |
| `hvy_winter` | Oct, Nov, Dec, Jan, Feb (same window as `lt_winter` — user explicitly grouped "LT_Winter & Hvy_winter" together) |

October deliberately overlaps `summer` and both winter categories — confirmed intentional by
the user (a realistic shoulder month), not a bug. A department with `season_category`
missing/null (16 departments with no apparel sales rows, per `build_season_category.py`'s
purity check) defaults to the same "always in-season" treatment as `regular` — an explicit
fallback, not a silent one. The windows live in `IN_SEASON_WINDOWS` at the top of
`scripts/build_risk_scores.py` (inlined there since it's the sole consumer — `build_seasonality.py`'s
own continuous calendar-month analysis is untouched and doesn't need this table).

**Exact rule:**
1. Only score a combo if its **latest recorded month** (last non-`.` entry in its `kb.json`
   history string) is `Y` — i.e. it is Listed as of the most current data available. Anything
   else (currently `N`, or no record at all) is not scored. Unchanged from before.
2. The KB's last month is often a partial "till date" month (e.g. `Sep'26(Till Date)`) — a few
   days of billing, not comparable to a full month. It still counts for step 1, but the
   **trend window is anchored to the last complete month instead**. Unchanged from before.
3. `recent_idxs` = the 3 complete months ending at the anchor (`RECENT_N = 3`, same as before).
4. Look up the combo's department's in-season calendar-month set `S` from the fixed table
   above (keyed by `season_category`; `None` = always in-season).
5. `recent_in_season_idxs` = the subset of `recent_idxs` whose calendar month is in `S`.
   **If this is empty (none of the 3 recent months are in-season for this department), skip —
   not flagged.** This is the core fix: an off-season dip for a seasonal department produces no
   signal at all, by construction — no expected-value math trying to compensate for it.
6. `history_in_season_idxs` = every month index before the recent window whose calendar month
   is in `S`, taken most-recent-first, capped at the **6** most recent (mirrors the old
   `BASELINE_N = 6` concept, just filtered to in-season months now). Require **at least 3**
   such months to proceed — otherwise skip as insufficient history (same "skip, don't assume
   low-risk" precedent as before).
7. `baseline_avg` = mean actual `SL_V` over `history_in_season_idxs`. Same `MIN_BASELINE =
   ₹2,000` floor as before — skip if below (noise, not signal).
8. `recent_avg` = mean actual `SL_V` over `recent_in_season_idxs` only — may be 1, 2, or 3
   months, whichever of the recent 3 were actually in-season.
9. `shortfall = clamp((baseline_avg − recent_avg) / baseline_avg, 0, 1)`. **Flagged** if
   `shortfall >= 0.5` — same 50% threshold as before.
10. Reason text: "Sales down N% vs this department's own prior in-season average (M of 3 recent
    months were in-season)" (M = `recent_in_season_count`), or "Zero sales in the in-season
    portion of the last 3 months despite still Listed" when `recent_avg == 0`.
    `history_months_used` in the output JSON is now the count of in-season baseline months used
    (3–6), and `baseline_avg` is the prior in-season average (not a season-expected figure) —
    same field names as before where possible, new meaning; the UI's risk column header was
    relabeled "Prior in-season avg → recent avg sales" to match.
11. `risk_tier` (Low/Medium/High) is recomputed fresh as tertiles of the new flagged-score
    distribution (`statistics.quantiles(scores, n=3)`, unchanged method) — the exact cutoffs
    necessarily shifted since the underlying scores changed; read `risk.json`'s
    `params.risk_tier_cutoffs` for the current values.

**As of 2026-09-21 (this rework):** 61,257 currently-Listed combos evaluated (unchanged);
**4,093 flagged (6.7%)**, up from 1,040 (1.7%) under the continuous-seasonal-index method (and
compared to 9,587 (15.7%) under the original flat-trailing-window method two reworks ago). This
increase (not a decrease) is expected and correct, not a regression: the continuous method
could partially offset a real recent decline against an unrelated part of the seasonal curve
(the `expected(m)` redistribution spread a combo's own 9-month total across the whole shape),
while the fixed-window rule compares recent in-season months only to a purely in-season prior
baseline — a stricter, more literal reading of "is this combo underperforming its own
in-season track record," so more genuine in-season declines surface uncompensated. See Change
Log for concrete before/after examples (an off-season false positive that still correctly
clears, and a genuine in-season decline that flags).

**Known limitations — do not overstate confidence:**
- **Department-wide season_category applied per store.** `season_category` is a single
  merchandise-master label for the whole department (same source as before) — this rule
  assumes an individual store×dept combo shares the same in-season window as the department
  overall. A store with a genuinely different local season (e.g. a hill-station store where
  winterwear sells earlier) could still be mis-classified as off-season when it isn't. No
  per-store seasonal baseline exists to check against.
- **occasional/regular have no seasonal exemption by design.** A genuine decline in a `regular`
  or `occasional` department was already being caught before this rework and still will be —
  these categories behave like a flat trailing comparison (always in-season), same as the
  original pre-seasonal-adjustment rule. This is intentional, not an oversight.
- **The October overlap is intentional** (see above) — a department transitioning between
  `summer` and a winter category in October will register as in-season under either
  classification; this is a deliberate shoulder-month allowance, not a data bug.
- **Small-sample noise** persists: a combo's 3–6 in-season history months, and even the
  recent 1–3 in-season months, are a small base — a single unusually slow in-season month can
  flip a combo to "flagged." The score is a screening signal, not a certainty — always check
  the trend chart (click the row) before treating a flagged combo as a real delisting risk.
- **The 2023 Q1 gap** can reduce the pool of in-season history months available for
  departments whose window falls partly in Jan–Mar (e.g. `lt_winter`/`hvy_winter`'s Jan/Feb),
  making the "insufficient in-season history" skip trigger more often for combos anchored near
  the start of the dataset — same silent-skip treatment as before, not a scoring error.
- **Sales-only signal.** This rule only looks at `SL_V` trend; it does not use any other
  merchandise/inventory signal (none exists in this pipeline — see memory:
  `aop-forecaster-lfl-data-model`), so it cannot distinguish "this department is being wound
  down" from "this department is just having a quiet quarter." The fixed in-season windows fix
  the seasonal false-positive class specifically — they do not add any new signal beyond `SL_V`.

### Season category (`scripts/build_season_category.py`)
Business question: *what is this department's real merchandise-master seasonality category* —
replaces the earlier CV-derived Low/Medium/High/Very High tier as the primary label (the user
rejected it as ambiguous: it said "how seasonal" but not "which season"). The real category
already exists as merchandise-master data, not something to derive statistically.

**Source**: the sales parquet's `ATTRIBUTE1` column (same file/scope as `build_sales.py` — same
`ALLOWED_TOKENS`/`category_token` apparel filter, latest-file-by-timestamp pattern). Verified
2026-09-21: within apparel-scoped departments, `ATTRIBUTE1` is **100% pure per department** —
every row for a given `DEPARTMENT` has the exact same value, zero exceptions, zero nulls, across
14,202,373 apparel rows / 263 departments. Values: `REGULAR` (91 depts), `SUMMER` (57),
`LT WINTER` (39), `HVY WINTER` (28), `PREWINTER` (25), `OCCASIONAL` (23) — plus `GM`/`RETAIL`
which only appear on non-apparel departments (out of scope, filtered by `ALLOWED_TOKENS` same
as elsewhere). `RAINCOAT`/`MSE_RAINCOAT`/`LW_U_RAINCOAT` are all `OCCASIONAL`, not a winter
family, confirming they're correctly distinct from the `KBW`/`KGW`/`MW` winter families.

**Exact method:**
1. Read `DEPARTMENT`/`ATTRIBUTE1` from the latest sales parquet, filter to apparel scope.
2. Group by `DEPARTMENT`, take the single `ATTRIBUTE1` value. **Hard-fail** (matching this
   project's data-integrity convention) if any department ever shows more than one distinct
   non-null value, or a null value, within apparel scope — purity is asserted, not assumed.
3. Normalize to lowercase-with-underscore: `regular`, `summer`, `lt_winter`, `hvy_winter`,
   `prewinter`, `occasional`.
4. Merge into `app/seasonality.json`'s existing `departments[dept]` entries as
   `season_category`, alongside (not replacing) `seasonality_index`/`seasonality_tier` — those
   stay as a magnitude signal (how volatile a department's sales are month-to-month), while
   `season_category` is now the primary, human-legible label. Also adds a top-level
   `season_categories` list (the 6 distinct values) for the frontend's filter dropdowns.
5. A department in `kb.json`/`seasonality.json` with **zero apparel sales rows** in the parquet
   (no `ATTRIBUTE1` data to read at all — different from a purity violation) gets
   `season_category: null`, not a hard fail — a coverage gap, not corruption, same treatment as
   `years_count_by_month` gaps elsewhere in this file.

**As of 2026-09-21:** 254 of 270 `seasonality.json` departments got a `season_category`; 16 had
no apparel sales rows at all (e.g. `KB_BERMUDA`, `KGW_PAYJAMA`, `LWW_WINDCHEATER` — likely
recently added or thinly-tracked department codes) and are `null`.

**Known limitations:**
- **16 departments have no `season_category`** (see above) — the frontend must handle `null`
  (renders as an "unknown" badge, not hidden or defaulted to a real category).
- **9 departments present in the parquet's `ATTRIBUTE1` data are not in `kb.json`'s department
  list** (263 parquet departments vs. 254 matched + the 16 nulls = 270 kb departments) — this is
  expected: the listing KB and the sales parquet are independently-scoped sources; a department
  can have sales history without ever appearing in a Directory Listing file, or vice versa. Not
  a purity or integrity issue, just two sources with slightly different coverage.

### Seasonality (`scripts/build_seasonality.py`)
Business questions: *for a department, based on previous sales trends, when are the natural
periods to list or delist?* and *if I were to bank on (invest heavily in) a department, when
historically gives max growth?* Built as a static `app/seasonality.json`, one entry per
department (dept-level = `SL_V` summed across **all stores** for that department per month —
this is department seasonality, not a store×dept view).

**Exact method:**
1. Take every month in `kb.json`'s `months` list except the trailing partial month (the
   `(Till Date)` suffix) — a few days' billing isn't comparable to a full month, same reasoning
   as the risk score's anchor logic.
2. Sum `SL_V` across all stores for that department, per full month.
3. Pool by **calendar month across years** (all `Jan'*` values together, etc.) — `months`
   list terms are matched by prefix, so `Jan'24`, `Jan'25`, `Jan'26` all count toward "Jan".
   `avg_sales_by_month[mon]` = mean of whatever years are present; `years_count_by_month[mon]`
   states exactly how many years back that mean (usually 3–4; fewer for Jan/Feb/Mar since the
   2023 Q1 source data doesn't exist at all, and fewer for Sep since Sep'26 is excluded as
   partial).
4. `overall_avg_monthly_sales` = mean of the 12 `avg_sales_by_month` values (department's own
   annual baseline, not company-wide).
5. **Weak/delist-candidate months**: every calendar month's % difference from that department's
   own `overall_avg_monthly_sales`, sorted ascending (most negative first) — these are the
   calendar months a buyer should consider for delisting/relisting, framed relative to the
   department's own pattern, not an absolute sales floor.
6. **Growth periods, month-wise (reworked 2026-09-21)**: for each of the 12 month-to-month
   pairs (Jan→Feb, …, Dec→Jan wraparound), compute `(to − from) / from × 100` for every year
   where both months are full (non-partial) months. Two guards before a year's value counts at
   all:
   - **`MIN_TRANSITION_BASE = ₹2,000`**: skip a year entirely if the "from" month's total is
     below this floor. A near-zero base (e.g. ₹159) turns an ordinary seasonal ramp-up into a
     meaningless six-digit "% growth" figure purely from dividing by almost nothing — this isn't
     a growth signal, it's a division artifact.
   - **`MIN_TRANSITION_YEARS = 2`**: a calendar month needs at least 2 qualifying years to be
     reported at all; fewer than that isn't a pattern, it's one data point dressed up as a trend.

   The reported figure is the **median**, not the mean, of the qualifying years' % changes —
   chosen specifically so a single unusually extreme year (see the real example below) can't
   dominate a 2–4 year average. This is neither CAGR (no compounding across periods — each
   year's figure is one independent single-step change) nor a weighted average (no weighting by
   volume/recency, plain median).

   **Attributed to the destination month, not shown as a "Mon1→Mon2" pair** (reworked
   2026-09-21, at the user's request — a transition pair reads as a different unit than
   `weak_months`' single-month list, and the two tables sitting side by side with mismatched
   grains was confusing when a month showed up as "weak" in one and part of a "growth" label in
   the other). So the `Mar` row *is* the Feb→Mar transition; `from_month` names the prior month
   for transparency, but the primary key is the single destination month, same grain as
   `weak_months`.

   **A non-positive median is excluded, not shown as the least-bad option** (also
   2026-09-21) — a "best growth periods" table showing an actual decline (e.g. −63.5%) because
   it happened to rank higher than four other declines is actively misleading, not merely
   unimpressive. A department with no genuinely positive month-to-month window will show fewer
   than 5 rows, possibly zero — that's the honest answer, not something to pad out.

   **Not ambiguous — a destination month below the department's own annual average never
   qualifies** (2026-09-21), even with a large, clean, floor-clearing % growth number. A month
   can grow strongly off an even-worse prior month while still being, in absolute terms, one of
   the department's weaker months (it can even appear in `weak_months` at the same time) — that
   is not a contradiction in the underlying data, but presenting it as "the best time to bank on
   this department" while the same month is also flagged as a delist candidate is genuinely
   ambiguous guidance. Only a month that clears its own department's `overall_avg_monthly_sales`
   is eligible for the growth list — unambiguously good by both the relative (month-over-month)
   and absolute (vs. annual average) measures, never both a growth pick and a weak pick at once.

   Sorted descending by the median, so "best growth periods" is a ranked list of genuine growth
   windows, not a single answer.

**As of 2026-09-21:** 270 departments scored, `app/seasonality.json` is ~400 KB.

**Real example of why the median + floor guards matter** — `KBW_THERMAL UPPER`, Sep→Oct across
its 3 years: 2023 `159 → 880,194` (+553,481%), 2024 `1,031 → 1,240,359` (+120,206%), 2025
`29,624 → 1,747,621` (+5,799%). Under the old mean-of-all-three method this reported as
**+226,495%** "best growth period" — meaningless. Under the new method, all three years'
"from" values are below the ₹2,000 floor, so **the Sep→Oct transition doesn't qualify at all**;
the department's actual top (and only) reported growth period is Oct→Nov at a sane +228.0%
(3 years, median). `KB_PYJAMA`'s Feb→Mar, by contrast, genuinely doesn't have this problem —
its 3 years (129.5%, 112.1%, 87.3%) are consistent, and the median (112.1%) is close to the old
mean (109.6%) precisely because there's no outlier to correct for.

**Known limitations — do not overstate confidence:**
- **Small per-calendar-month sample size.** Most departments have only 3–4 data points per
  calendar month (one per year). A month backed by only its minimum 2 qualifying years is shown
  with its year count, not hidden — but 2 data points is barely a pattern, and the UI surfaces
  the year count specifically so a buyer can down-weight it.
- **The ₹2,000 floor is the same value used elsewhere in this project** (`build_risk_scores.py`'s
  `MIN_BASELINE`) for consistency, not independently tuned for this specific calculation — a
  department whose entire scale sits just above or below that line may see a transition
  flicker in or out of eligibility from noise alone.
- **New/thin departments are noisier.** A department with sparse or recent listing history will
  more often fail the `MIN_TRANSITION_YEARS` floor and simply have no reportable growth periods
  at all (an empty table), which is the honest answer for a department this project doesn't yet
  have enough history on — not a bug to work around.
- **Update (2026-09-21): now feeds the delisting-risk score directly.** `risk.json` (see the
  Delisting-risk score section above) now reads this file's `avg_sales_by_month`/
  `overall_avg_monthly_sales` to season-adjust its own comparison, rather than reading a flat
  trailing window. This is no longer a standalone cross-reference-only view — it is a required
  input, and `build_risk_scores.py` must run after this script.
- **Verified against a known seasonal example**: `RAINCOAT` (dept-level, all stores) — best
  growth periods Jun→Jul (+1461.6%, 4 yrs of data) and May→Jun (+753.1%, 4 yrs), weakest months
  Apr/Feb/Dec/Jan/Nov (all ~98% below its own annual average) — matches the expected monsoon
  pattern, not a random result.

## Change Log
- **2026-09-21 (bi-analyst pass, fixed in-season windows — full rework of risk scoring)** — User
  rejected the continuous seasonal-index risk method (same day, previous entry below) in favor
  of a simpler, fixed business-rule definition: each `season_category` maps to a hard calendar-
  month in-season window (see the Delisting-risk score section above for the exact table and
  formula), and an off-season dip produces **no signal at all** rather than a dampened one. This
  is a full replacement, not a layering, of the continuous method — `build_risk_scores.py` no
  longer reads `avg_sales_by_month`/`overall_avg_monthly_sales` at all, only `season_category`.
  - **Before/after example 1 (off-season false positive, still correctly clears)**:
    `AGT / KGW_JACKET` and `ABD / KBW_JACKET` (both `hvy_winter`) — anchored on `Aug'26`, so the
    recent window is Jun/Jul/Aug'26, none of which fall in the `hvy_winter` in-season window
    (Oct–Feb). Under **both** the old continuous method and this new fixed-window method, these
    two combos are **not flagged** — confirmed by re-running `score_combo` against the live
    data: neither appears in the new `app/risk.json`'s flagged list. The mechanism differs
    (old: seasonal index for Jun/Jul/Aug was itself ~0, so `expected` was trivial and the
    ₹2,000 recent-expected floor caught it; new: `recent_in_season_idxs` is empty outright,
    skipped before any average is even computed) but the practical outcome for this exact
    false-positive class is the same, confirming the fix generalizes.
  - **Before/after example 2 (genuine in-season decline, still flags)**:
    `BHF / KBW_JACKET` (`hvy_winter`) — last recorded month `Nov'25` (this combo stopped being
    tracked after that), anchor `Nov'25`, recent window Sep/Oct/Nov'25, of which **Oct and Nov
    are in-season** (`recent_in_season_count: 2`). The 6 in-season history months before that
    (capped from a longer available run) averaged **₹28,905/month**; the 2 in-season recent
    months averaged **₹0**. Flagged at **100%**, reason: "Zero sales in the in-season portion of
    the last 3 months despite still Listed." This is exactly the kind of real signal the rule is
    designed to keep catching — the in-season restriction only suppresses off-season noise, it
    doesn't mask a genuine collapse during the department's own season.
  - **Also unaffected (regular/occasional behave like before)**: `ANG / MSE_RAINCOAT`
    (`occasional`, always in-season) still flags — now at **92.4%** ("Sales down 92% vs this
    department's own prior in-season average (3 of 3 recent months were in-season)"), prior
    in-season (= all-history) average ₹3,051.64/month vs. recent ₹232.67/month. A genuine
    decline in a `regular`/`occasional` department was already being caught before this rework
    and still will be — these categories have no seasonal exemption by design (see limitations).
  - **Aggregate effect**: 4,093 flagged (6.7% of 61,257 evaluated), **up** from 1,040 (1.7%)
    under the continuous-seasonal-index method this same day, and also up from the very first
    flat-trailing-window method's 9,587 (15.7%) two reworks ago — but not a return to the
    original false-positive problem: `AGT/KGW_JACKET` and `ABD/KBW_JACKET` above, the two
    documented false-positive examples from the original method, still correctly don't flag.
    The increase vs. the continuous method reflects the fixed-window rule being *stricter* about
    what counts as "the same season" for baseline vs. recent comparison (see the Delisting-risk
    score section's "As of 2026-09-21" note for why this is an expected, not a regressive,
    change) — by season category: `prewinter` 1,905, `summer` 619, `occasional` 531,
    `hvy_winter` 137, `lt_winter` 190, `regular` 711.
  - **Limitations carried forward / added**: department-wide `season_category` applied per
    individual store (no per-store seasonal baseline exists); the October shoulder-month overlap
    between `summer` and both winter categories is intentional; small-sample noise persists in
    both the in-season history window (3–6 months) and the in-season recent window (1–3
    months); `regular`/`occasional` have no seasonal exemption by design, matching pre-seasonal-
    adjustment behavior for those categories. See the Delisting-risk score section above for the
    full list.
- **2026-09-21 (bi-analyst pass, real season category + season-aware risk)** — User rejected the
  CV-derived seasonality tier (Low/Medium/High/Very High) as ambiguous ("how seasonal" but not
  "which season") and pointed out the real business attribute already exists in the sales source
  data. Two changes, both detailed in full in the main sections above:
  1. **Added `scripts/build_season_category.py`** → merges a `season_category` field
     (`regular`/`summer`/`lt_winter`/`hvy_winter`/`prewinter`/`occasional`) into
     `app/seasonality.json`'s per-department entries, sourced from the sales parquet's
     `ATTRIBUTE1` column — real merchandise-master data, verified 100% pure per department
     (zero violations across 14,202,373 apparel rows / 263 departments; distribution 91/57/39/
     28/25/23 matching REGULAR/SUMMER/LT WINTER/HVY WINTER/PREWINTER/OCCASIONAL exactly).
     `seasonality_index`/`seasonality_tier` are kept (still a useful magnitude signal), just no
     longer the primary label. See "Season category" section above for the exact method.
  2. **Reworked `scripts/build_risk_scores.py`** to be season-aware, using this same
     `seasonality.json` data (see "Delisting-risk score" section above for the exact formula).
     **Before/after, real examples** (recent window = Jun/Jul/Aug'26, anchored on the last
     complete month, `Aug'26`, since `Sep'26(Till Date)` is partial):
     - **`AGT / KGW_JACKET`** (hvy_winter): was flagged at **100%**, "Zero sales in the last 3
       months despite still Listed." `KGW_JACKET` sells essentially nothing company-wide in
       Jun/Jul/Aug (dept-wide avg ₹0/₹0/₹0 those months vs. ₹11.3M/₹11.7M/₹13.5M in Jan/Nov/Dec)
       — a textbook seasonal false positive. **After**: no longer flagged at all — the
       season-expected sales for Jun-Aug is itself ~0, so there's nothing meaningful to compare
       against (skipped, not scored as risk).
     - **`ANG / MSE_RAINCOAT`** (occasional): was flagged at 92% ("Sales down 92% vs the
       trailing 6-month average"). **After**: still flags, now at 96%, but the reason changed to
       reflect a genuine problem: Jun-Aug is `MSE_RAINCOAT`'s dept-wide monsoon **peak**
       (₹552K/₹1.72M/₹823K avg vs. ₹277K overall average) — i.e. the recent window is this
       department's *biggest* months, not its off-season. Yet this store's actual recent sales
       are only ₹233/month, below even the old flat off-season baseline of ₹3,052/month. The
       season-adjusted expected level is ₹6,242/month. This is a real, not seasonal-blind-spot,
       signal — the combo isn't participating in the seasonal peak at all, unlike the rest of
       the chain.
     - **`ABD / KBW_JACKET`** (hvy_winter): found during verification — still flagged at 100%
       after the season-aware fix alone, because the department's Jun/Jul/Aug dept-wide average
       (₹0/₹224.75/₹149.75) is a few rupees, not exactly zero, so the "nothing to compare
       against" skip didn't trigger, and `(tiny − 0) / tiny` still computes to a mathematically
       valid but meaningless 100% "shortfall." Added a second `₹2,000` floor on the recent
       months' own season-expected average (see rule step 9) — after that, this combo correctly
       drops out too.
     - **Aggregate effect**: 9,587 flagged (15.7% of 61,257 evaluated) → 1,040 flagged (1.7%).
       By season category, before → after: `lt_winter` 3,925 → 37, `hvy_winter` 2,900 → 17,
       `prewinter` 1,188 → 304, `regular` 705 → 353, `occasional` 530 → 98, `summer` 339 → 231.
       The reduction is overwhelmingly concentrated in the winter-family categories (8,013 →
       358, a 95.5% drop) that were the documented false-positive class — `regular` (non-
       seasonal) and `summer` (currently on-season) dropped far less, which is the expected
       signature of a real fix rather than the model simply going quiet everywhere.
  - **Limitations carried forward / added**: `seasonal_index` is department-wide (all stores),
    applied per individual store×dept combo — a store with a genuinely different local season
    could still be mis-adjusted (no per-store seasonal baseline exists to check against); this
    rework inherits `seasonality.json`'s own small-sample-per-calendar-month ceiling; it is
    still a pure `SL_V`-trend heuristic with no other merchandise/inventory signal. None of
    these are new — they're the same caveats already on `seasonality.json` and the original risk
    rule, now explicitly inherited.
- **2026-09-21 (bi-analyst pass, seasonality-intensity)** — Extended `scripts/build_seasonality.py`
  to add a per-department **seasonality-intensity index and tier**, so listing/delisting work can
  be segregated by "how seasonal is this department" everywhere a department appears, not just
  the Seasonality tab (business ask: buyers need to discount a flagged risk that's actually just
  seasonal, per the limitation already documented above).
  - **Formula**: `seasonality_index` = coefficient of variation = population stdev ÷ mean, computed
    over the department's covered `avg_sales_by_month` values (the same 12-calendar-month averages
    already in the file; "covered" = calendar months with at least 1 year of data). A flat
    department's CV is near 0; a hard-seasonal one is large. Needs at least 2 covered months and a
    positive mean, else undefined and set to `0.0` (see limitations below).
  - **Tiers**: `seasonality_tier` (Low/Medium/High/Very High) is bucketed by the **quartiles of the
    actual `seasonality_index` distribution across all 270 departments in this file** — not
    hardcoded round numbers. As computed 2026-09-21: Q1 = 0.4770, Q2 (median) = 0.8545,
    Q3 = 1.4363 (`statistics.quantiles(cvs, n=4)`, default exclusive method). Low = index ≤ Q1,
    Medium = Q1 < index ≤ Q2, High = Q2 < index ≤ Q3, Very High = index > Q3. Both cutoffs and the
    quartile method are stored in `seasonality.json`'s top-level `seasonality_index_quartiles`, so
    they're always traceable to the data that produced them, not re-derived blind by a reader.
  - **Verified example**: `RAINCOAT` (dept-level, all stores) — `seasonality_index` = 1.7082,
    tier = **Very High** (well above Q3), consistent with its known Jun–Aug monsoon spike.
    `MSE_RAINCOAT` = 1.8431 (Very High), `LW_U_RAINCOAT` = 1.6361 (Very High) — the other two
    RAINCOAT-token departments land the same way. Tier distribution across all 270 departments:
    67 Low / 68 Medium / 68 High / 67 Very High (quartiles split it roughly evenly, as expected).
  - **Limitations (same caveats as the rest of the seasonality work, do not overstate confidence)**:
    a department with very low or highly volatile absolute sales can produce a distorted CV (a
    near-zero mean makes the ratio unstable even for a modest absolute swing); a department with
    few years of data behind its calendar-month averages (see `years_count_by_month`, same 2023
    Q1 gap and 2026 partial-tail effects as elsewhere in this file) gets a noisier index and tier
    assignment than one backed by the full 3–4 years — always cross-check the underlying
    `avg_sales_by_month`/`years_count_by_month` for a department whose tier looks surprising,
    same discipline as the existing weak-months/growth-transitions caveats.
  - This does **not** touch `risk.json`'s own scoring logic — same ground rule as the original
    seasonality work — it's added as cross-referenceable context so a buyer can see, right next
    to a flagged risk row, whether that department is inherently seasonal.
- **2026-09-21 (bi-analyst pass)** — Added `scripts/build_seasonality.py` → `app/seasonality.json`
  (calendar-month-pooled seasonality per department, across all stores) and the exact method +
  limitations above. Backs the new Seasonality tab (see PRD_ARCHITECTURE.md). Verified against
  `RAINCOAT` as a known-seasonal sanity check.
- **2026-09-21** — Phase 2 kickoff. Built `scripts/build_knowledge_base.py` and generated
  `app/kb.json` from the 4 existing Directory Listing files. Sales logic not started —
  blocked on identifying a sales data source.
- **2026-09-21 (later same day)** — User provided the sales source (data lake parquet path
  above). Built `scripts/build_sales.py`, generated `app/sales.json`. Sales metric chosen:
  `SL_V` (sale value) — qty/tax/cost columns exist in source but aren't surfaced yet.
- **2026-09-21 (later still)** — Added the delisting-risk scoring rule (see above) and
  `scripts/build_risk_scores.py` → `app/risk.json` (9,587 combos flagged of 61,257 evaluated).
  Verified against a real seasonal example (`ANG / MSE_RAINCOAT`) that the rule flags
  seasonality as risk — documented as a known limitation, not fixed, per this project's
  no-fabricated-confidence rule.
- **2026-09-21 (final pass)** — Added a Low/Medium/High **risk-severity tier** to
  `app/risk.json`'s flagged combos, at the user's explicit request to keep a simple severity
  label alongside the numeric score and season-category badge. Cutoffs are **tertiles of the
  flagged score distribution itself** (`statistics.quantiles(scores, n=3)`, same data-driven
  approach as the seasonality-tier quartiles), not fixed round numbers — as of this run:
  low_max=0.607, medium_max=0.794 (score range for flagged combos is 0.5–1.0 by construction,
  since 0.5 is the flag threshold), splitting 1,040 flagged combos into 347 Low / 348 Medium /
  345 High. Recomputed every time `build_risk_scores.py` runs, so the exact cutoffs will drift
  as the underlying data changes — read `risk.json`'s `params.risk_tier_cutoffs` for the
  current values rather than trusting the numbers above as permanent. Degenerate case (fewer
  than 3 flagged combos): tiers aren't meaningful, everything gets `'High'`.
- **2026-09-21 (growth-periods rework)** — User asked two things about the Seasonality tab's
  "Best growth periods" table: (1) reframe it month-wise instead of as Mon1→Mon2 pairs, to match
  `weak_months`' grain, and (2) guard against a single year's outlier dominating the multi-year
  average — confirmed real via a full-dataset scan (122 departments had a top "growth" figure
  over 400%, driven by near-zero starting bases). Fixed both at once in `build_seasonality.py`:
  growth is now attributed to the destination month (`from_month` kept for transparency), a
  `₹2,000` floor drops any year whose starting month is too small to divide by meaningfully, at
  least 2 qualifying years are required to report a month at all, the reported figure is the
  **median** (not mean) across qualifying years, and a non-positive median is excluded entirely
  rather than shown as a decline dressed up as "growth." See the full method + real
  `KBW_THERMAL UPPER` before/after example above. `demo()` extended with 4 new assertions
  (floor exclusion, insufficient-years exclusion, median-over-mean, decline-exclusion).
  Regenerated the full pipeline in the correct order (`build_seasonality.py` →
  `build_season_category.py` → `build_risk_scores.py`, since the first two feed the third) —
  `risk.json`'s flagged count is unchanged (4,093) since it doesn't use `growth_transitions`.
- **2026-09-21 (not-ambiguous rule)** — User pointed out the growth-periods rework above still
  didn't fully close the gap: a month could clear the new floor/median/decline guards yet still
  be one of the department's own weak months in absolute terms (e.g. `KB_PYJAMA`'s `Feb`, at
  −23.5% vs. its annual average, still showed as a +53.6% "best growth period" off an
  even-weaker `Jan`). Added one more guard: a destination month is only growth-list-eligible if
  its own `avg_sales_by_month` is at or above `overall_avg_monthly_sales` — verified on real
  data that `KB_PYJAMA`'s growth list is now `Mar/Oct/Aug/May` with zero overlap against its
  weak-months list (`Dec/Jan/Feb/Jul/Sep`). New `demo()` case (`PEAK` department) asserts a
  clean +100% MoM month is excluded when it's below the department's own average, while the
  genuine peak month one step later is still included.

- **2026-09-26 (unified data)** — (1) `scripts/_paths.py`: the data-lake sales folder comes from
  the SAME setting the core syncs use (Postgres `sync.sources` 'data_lake_sales'), with the old
  path as fallback; yearly workbooks come from `RS_planning/data/listing/`. (2) New
  `scripts/build_stores.py` -> `app/stores.json` from `masterdata.stores`, classifying LfL / Ramp /
  NSO with the AOP Forecaster's own rule (`engine_v3.auto_tag`, December cut-off): 280 of 281 KB
  stores join; 148 LfL, same as AOP. (3) The whole pipeline (KB -> sales -> seasonality -> season
  category -> risk -> stores) runs daily as the `listing_delisting` job at the end of the
  data-lake sync (`Tentative AOP Forecaster/sync/listing_delisting_sync.py`, ~3 min), visible in
  Landing's Data sync panel. First rebuild: kb / sales / seasonality identical to the previous
  files, risk identical except its date (4,093 of 61,257 flagged).
