// AOP Re-Aligner - the rules in force and the latest rule change, shown by the "Rules" button in the top bar.
// The rules themselves are coded in engine.py and importer.py. Only the current rules are kept (user, 2026-09-26:
// no version numbers, no history): when one changes, update RULES_NOW to match and replace RULES_LATEST.
const RULES_NOW = [
  ['What is kept', [
    'Every <b>Store × Division × Month</b> total of the original plan - the plan being revised - is the target the output lands on.',
    'The values you give (revised, newly listed or split departments) are kept <b>exactly</b>; every other department in the same store × division absorbs the difference, pro-rata to its original value - unless Method 2 runs with the other departments <b>kept as they are</b>.',
    '<b>Locked months are never changed</b> (value and qty) - the planner locks / unlocks each month of the original plan (Jan / Feb locked by default). Locked-month figures in an upload are ignored and flagged.',
  ]],
  ['When a month overflows', [
    "If the kept departments alone exceed a month's store × division total, the other departments go to 0 that month and the excess comes out of the same store × division's other live months, in proportion to their room.",
    "So the store × division <b>season</b> total and the grand total still match; only that month's split moves. A case with nothing left to absorb is flagged, never hidden.",
  ]],
  ['MRP × display rows and qty', [
    "A department value is split to its MRP × display type rows by that month's original share; a month with no original plan uses the row's average share across the revised months it had (locked months do not count).",
    "Qty = value ÷ the original ASP of that Department × MRP × Display type × Month (pooled across stores). No qty that month: the combination's all-month ASP, then MRP. Unchanged cells keep their exact original qty.",
  ]],
  ['Method 1 - store listing changes', [
    'LISTING = N: the department goes to 0 from FROM MONTH (blank = the first month).',
    "LISTING = Y (not planned there): sized, month by month, as its share of the division in same-cluster stores that plan it × this store's division plan - or your own values - with rows borrowed from the peer store that plans it most.",
    'The "From Listing / Delisting Analyser" template leaves out a store × division whose every department is delisted (a closing or not-yet-open store): nothing would be left to absorb it.',
  ]],
  ['Method 2 - existing department changes', [
    'Store × Department rows with "&lt;Month&gt; New" values; months not in the file stay as original.',
    'Other departments in the store × division: <b>absorb the change</b> (default - each store × division stays on the original) or <b>stay as they are</b> (only the revised departments move, e.g. a month re-phase).',
  ]],
  ['Method 2 - Re-phase from last year', [
    '<b>Re-phase &amp; run</b>: pick the department (and, if needed, whose last-year shape to use - any department with last-year sales, e.g. a related department with a fuller history) and it is re-phased, loaded as the revised file and run with the other departments <b>kept as they are</b>, in one step. <b>Re-phase file</b> downloads the same file to check or edit first.',
    "Months re-phased = the <b>unlocked months that have a last-year month</b> (a P1 / P2 half-month has none - it keeps its plan, and the summary says so). Each store keeps its <b>total for those months</b>; only the split between them changes.",
    "Last year's month must be in the data and complete - a month the sales data doesn't have yet, or only has till date, is refused (its shape would be wrong): lock it, or re-phase after it closes.",
    "The split = last year's sales of the shape department in the same months a year earlier (the month-wise data-lake sales), from the first <b>comparable store</b> of: the store itself, its REF store, its REF OLD store; none of them - the comparable stores of its cluster together; still none - the store keeps its planned phasing (never 0). A negative last-year month counts as 0.",
    "<b>Comparable store</b> (may lend its shape): if the plan has an SSG TAG column, a store whose tag starts with SSG; if it has none, a store that sold in the department's division in <b>every one</b> of those months last year - never a store with a part-year history.",
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
    'One row per change: DEPARTMENT, LISTING (Y / N), TARGET (a department, or a whole section from the Attribute Master, in the same division), optional FROM MONTH and STORE NAME (blank = every store it applies to).',
    "A delisted department's plan moves <b>only into the target</b>, split by the target departments' own plan that month; a newly listed one (sized like Method 1, or given) is taken <b>only out of the target</b>, capped at what the target has.",
    'Nothing else moves, so every store × division × month stays exactly as in the original.',
  ]],
  ['Method 5 - growth changes', [
    "DEPARTMENT and NEW GROWTH % (season) and / or per-month growth columns over last year, optional STORE NAME (blank = every store; a store's own row overrides). Last year = the month-wise data-lake sales (Listing / Delisting Analyser app).",
    'Current growth = plan ÷ last year over the live months, on the stores with both; the plan is scaled by (1 + new) ÷ (1 + current) in every live month, keeping its month phasing.',
    'Per month: a "&lt;Month&gt; GROWTH %" column sets that month on its own - its plan vs its own last-year month (so a festival that moved month, e.g. Diwali, shows up there). Months without one take NEW GROWTH %, or stay as planned if that is blank too.',
    'The rest of the same store × division absorbs it (capped at store × division × month); other divisions are not touched. A current growth beyond ±200% is flagged as "last year not comparable".',
  ]],
  ['Display-type cont % (every method)', [
    "The final plan is split to MRP × display rows by the <b>original plan's display-type cont %</b> in every store × department × month; the other departments are scaled as a whole, so theirs is kept too. Every run checks it.",
  ]],
  ['Checks on every run', [
    'Recomputed from the output: kept values exact, store × division season and month totals, grand total, locked months untouched, display-type cont % as the original. Any input error blocks the run; warnings and notes are listed with row examples.',
    'Method 2 with the other departments <b>kept as they are</b>: instead of the store × division totals it checks that every other department is untouched and that the revised departments kept their season total; the store × division month totals are shown for information (they move by exactly the revised departments\' change) and the grand total is still checked.',
  ]],
];

const RULES_LATEST = {
  date: '2026-09-30',
  changes: [
    'Re-phase from last year is generic: a comparable store is one tagged SSG... or, in a plan without that tag, one that sold in every re-phased month last year; any missing store column simply drops out of the order.',
    'A last-year month that is missing from the data or only till date is refused; unlocked half-months are reported, not silently skipped; every re-phase comes with a summary.',
  ],
};
