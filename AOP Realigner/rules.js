// Sales Plan Re-Aligner - the rules in force and the latest rule change, shown by the "Rules" button in the top bar.
// The rules themselves are coded in engine.py and importer.py. Only the current rules are kept (user, 2026-09-26:
// no version numbers, no history): when one changes, update RULES_NOW to match and replace RULES_LATEST.
const RULES_NOW = [
  ['What is kept', [
    'Every <b>Store × Division × Attribute × Month</b> total of the original plan - the file imported in step 1 - is the <b>cap</b>: the output lands exactly on it, and every run checks it (pass / fail). So a department change stays <b>inside its own attribute</b> - nothing is apportioned across attributes - and the store × division × month follows. (A plan without an ATTRIBUTE column is capped at store × division × month.)',
    'The values you give (revised, newly listed or split departments) are kept <b>exactly</b> within the cap; every other department of the same attribute in that store × division absorbs the difference, pro-rata to its original value. A department alone in its attribute in a store has nothing to absorb into: its change is flagged, never spread to another attribute.',
    '<b>No negative plan</b>: after apportioning, every negative cell in an unlocked month (e.g. -0.01) is set to <b>0</b>, and the balance comes back out of the same store × division × attribute × month by the same rules - a revised department’s negative row out of that department’s own other rows (its value stays as given), any other out of the other departments pro-rata - so the cap still holds. Negatives in locked months stay as they are. Checked on every run.',
    '<b>Locked months are never changed</b> (value and qty) - the planner locks / unlocks each month of the original plan (Jan / Feb locked by default). Locked-month figures in an upload are ignored and flagged.',
  ]],
  ['When a month overflows', [
    "If the departments you gave alone exceed a month's cap, they are <b>cut to the cap</b> that month (the other departments go to 0) and the excess moves into the <b>same departments' other live months</b> that still have room - the other departments there shrink by the same amount.",
    "So every store × division × attribute × month, the season total, the grand total and the revised departments' own season totals all still match; only those departments' month split moves (the Revised-values check says how many). Excess with no room anywhere, or a shortfall with nothing left to absorb, is flagged, never hidden.",
  ]],
  ['MRP × display rows and qty', [
    "A department value is split to its MRP × display type rows by that month's original share; a month with no original plan uses the row's average share across the revised months it had (locked months do not count).",
    "Qty = value ÷ the original ASP of that Department × MRP × Display type × Month (pooled across stores). No qty that month: the combination's all-month ASP, then MRP. Unchanged cells keep their exact original qty.",
  ]],
  ['Method 1 - store listing changes', [
    'The blank template is <b>Department | Store | Listing (Y/N)</b>. An optional FROM MONTH column and "&lt;Month&gt; New" values are still read if added.',
    'Listing = N: the department goes to 0 from FROM MONTH (blank = the first month).',
    "Listing = Y (not planned there): month by month, the department's <b>cont % of its division in the store's REF store</b> (when the REF store plans it), else pooled over the same-cluster stores that plan it (else every store that does), × <b>this store's division AOP</b> - or your own values. Its MRP × display rows come from that REF store (else the peer planning it most).",
    "A store × division with a new listing is re-split over <b>all</b> its departments: the others give way pro-rata (scaled by 1 − the new cont %), so the store × division AOP stays exact - capped at store × division, not attribute, for that store × division only. Delistings stay inside their attribute.",
    '<b>Listing check file</b> (after uploading): every department of the store × divisions the changes touch, original vs new per month (newly listed / delisted / gives way), a "How it was built" sheet (REF store or cluster, cont %, division AOP) and a store × division summary - the realigned result, before Run.',
    'The "From Listing / Delisting Analyser" template leaves out a store × division whose every department is delisted (a closing or not-yet-open store): nothing would be left to absorb it.',
  ]],
  ['Method 2 - existing department changes', [
    'Store × Department rows with "&lt;Month&gt; New" values; months not in the file stay as original.',
    'Every other department of the same attribute in the store × division absorbs the change, so each store × division × attribute × month stays on the original (there is no "stay as they are" option).',
  ]],
  ['Method 2 - Re-phase from last year', [
    '<b>Re-phase &amp; run</b>: pick the department (and, if needed, whose last-year shape to use - any department with last-year sales, e.g. a related department with a fuller history) and it is re-phased, loaded as the revised file and run with the other departments <b>absorbing the change</b>, in one step - so every store × division × attribute × month stays on the original file (the cap). <b>Re-phase file</b> downloads the same file to check or edit first.',
    "Months re-phased = the <b>unlocked months that have a last-year month</b> (a P1 / P2 half-month has none - it keeps its plan, and the summary says so). Each store keeps its <b>total for those months</b>; only the split between them changes.",
    "Last year's month must be in the data and complete - a month the sales data doesn't have yet, or only has till date, is refused (its shape would be wrong): lock it, or re-phase after it closes.",
    "The split = last year's sales of the shape department in the same months a year earlier (the month-wise data-lake sales), from the first <b>comparable store</b> of: the store itself, its REF store, its REF OLD store; none of them - the comparable stores of its cluster together; still none - the store keeps its planned phasing (never 0). A negative last-year month counts as 0.",
    "<b>Comparable store</b> (may lend its shape): a store that sold in the department's division in <b>every one</b> of those months last year - never a part-year history - <b>and</b>, if the plan has an SSG TAG column, is tagged SSG. Both are required; a tagged store without a full last year is left out and named in the summary.",
    "A month the store doesn't trade in (no plan in the department's division that month) gets 0 and the rest is scaled back to 100%.",
    'REF, REF OLD, SSG TAG and CLUSTER are read from the original plan\'s own columns when it has them; each missing one simply drops out of the order above.',
    '<b>Store overrides</b> (upload once, kept until cleared): STORE NAME + REF OLD - a store attribute, used before the cluster for every department - and / or DEPARTMENT + "&lt;Month&gt; %" - a fixed month mix for that store and department only (any scale, rescaled to 100%), replacing its last-year shape there. A mix without a DEPARTMENT is refused, so a mix set for one department never moves another. The <b>Overrides template</b> lists the stores needing a look first.',
    'Every re-phase comes with a <b>Summary</b> (also shown in step 2: stores, months, the comparable rule used, where each store\'s shape came from, stores left on their planned phasing, months not traded, half-months skipped) and a "How it was built" sheet per store.',
  ]],
  ['Method 3 - new or split departments', [
    "Split: PARENT DEPARTMENT, NEW DEPARTMENT, SHARE % (optional STORE NAME; a store's own row overrides the all-store row). The parent keeps what is not shared out, the new departments take their share with the parent's MRP × display mix and ASPs; nothing else moves. Shares over 100% are refused.",
    "New department: \"&lt;Month&gt; New\" values with COPY FROM (whose MRP × display rows it takes); without it, a new name must start with an existing department's (e.g. an F/S split named after its parent department).",
  ]],
  ['Method 4 - listing / delisting shifted to a target', [
    'One row per change: DEPARTMENT, LISTING (Y / N), TARGET (a department, or a whole section from the Attribute Master, in the same division and attribute), optional FROM MONTH and STORE NAME (blank = every store it applies to).',
    "A delisted department's plan moves <b>only into the target</b>, split by the target departments' own plan that month; a newly listed one (sized like Method 1, or given) is taken <b>only out of the target</b>, capped at what the target has.",
    'Nothing else moves, so every store × division × attribute × month stays exactly as in the original; a target in another attribute is refused.',
  ]],
  ['Method 5 - growth changes', [
    "DEPARTMENT and NEW GROWTH % (season) and / or per-month growth columns over last year, optional STORE NAME (blank = every store; a store's own row overrides). Last year = the month-wise data-lake sales (Listing / Delisting Analyser app).",
    'Current growth = plan ÷ last year over the live months, on the stores with both; the plan is scaled by (1 + new) ÷ (1 + current) in every live month, keeping its month phasing.',
    'Per month: a "&lt;Month&gt; GROWTH %" column sets that month on its own - its plan vs its own last-year month (so a festival that moved month, e.g. Diwali, shows up there). Months without one take NEW GROWTH %, or stay as planned if that is blank too.',
    'The rest of the same store × division × attribute absorbs it (the cap); other attributes and divisions are not touched. A current growth beyond ±200% is flagged as "last year not comparable".',
  ]],
  ['Display-type cont % (every method)', [
    "The final plan is split to MRP × display rows by the <b>original plan's display-type cont %</b> in every store × department × month; the other departments are scaled as a whole, so theirs is kept too. Every run checks it.",
  ]],
  ['Checks on every run', [
    'Recomputed from the output: kept values exact, store × division season totals, <b>Store × Division × Attribute × Month = original (the cap)</b>, store × division × month, grand total, locked months untouched, display-type cont % as the original. Any input error blocks the run; warnings and notes are listed with row examples.',
    '<b>Comparison vs original</b> (download after a run): Summary (division × month), <b>Store x Div x Attribute x Month</b> - every one, original vs new, difference and "Within cap" - <b>Store x Dept x Month</b> - every department month that moved - and <b>Changed Rows</b> (every MRP × display cell, with why).',
    '<b>Plan to plan</b> (download after a run): the <b>whole</b> plan, not just the changes - every Store × Department × MRP × Display Type row of the original and the final, each month Original / Final / Difference plus the season, with Changed / Months changed up front to filter on (rows of a new department say "new in final").',
  ]],
];

const RULES_LATEST = {
  date: '2026-10-01',
  changes: [
    'The cap is now <b>Store × Division × Attribute × Month</b> (was Store × Division × Month): a department change is absorbed only by the other departments of its own attribute in that store × division - nothing is apportioned across attributes. Store × division × month still matches, as it follows.',
    'A department that is alone in its attribute in a store has nothing to absorb its change: flagged ("couldn\'t fully land"), never spread to another attribute.',
    'Method 4: a shift target must be in the same division <b>and attribute</b>; a section target takes only its departments of that attribute.',
    'Method 1 new listings: sized from the REF store\'s cont % first, then the cluster\'s, × the store\'s division AOP; the rest of that store × division gives way pro-rata (division-level cap there). New <b>Listing check file</b> to see it before running.',
    'Negative plan cells in the unlocked months are set to 0 after apportioning; the balance is re-apportioned inside their store × division × attribute × month (new check: "No negative plan in the unlocked months").',
    'New download <b>Plan to plan</b>: the full original vs final plan, row for row (Store × Department × MRP × Display Type), every month, Changed flag to filter on.',
    'Checks: "Store × Division × Attribute × Month = original (the cap)" plus "Store × Division × Month = original". The comparison download\'s cap sheet is now Store x Div x Attribute x Month.',
  ],
};
