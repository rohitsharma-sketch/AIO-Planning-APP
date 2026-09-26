// AOP Re-Aligner - rules in force and the rule version log, shown by the "Rules" button in the top bar.
// The rules themselves are coded in engine.py (realign / listing_targets / split_targets) and importer.py.
// Whenever one changes: update RULES_NOW to match, add a RULE_LOG entry at the TOP (next version, date,
// what changed in plain words, why + who asked, commit), and mark the previous one superseded.
const RULES_NOW = [
  ['What is kept', [
    'Every <b>Store × Division × Month</b> total of the original plan - the plan being revised - is the target the output lands on.',
    'The values you give (revised, newly listed or split departments) are kept <b>exactly</b>; every other department in the same store × division absorbs the difference, pro-rata to its original value.',
    '<b>Jan and Feb are never changed</b> (value and qty). Jan / Feb figures in an upload are ignored and flagged.',
  ]],
  ['When a month overflows', [
    "If the kept departments alone exceed a month's store × division total, the other departments go to 0 that month and the excess comes out of the same store × division's other live months, in proportion to their room.",
    "So the store × division <b>season</b> total and the grand total still match; only that month's split moves. A case with nothing left to absorb is flagged, never hidden.",
  ]],
  ['MRP × display rows and qty', [
    "A department value is split to its MRP × display type rows by that month's original share; a month with no original plan uses the row's average share across the months it had.",
    "Qty = value ÷ the original ASP of that Department × MRP × Display type × Month (pooled across stores). No qty that month: the combination's all-month ASP, then MRP. Unchanged cells keep their exact original qty.",
  ]],
  ['Method 1 - store listing changes', [
    'LISTING = N: the department goes to 0 from FROM MONTH (blank = the first month).',
    "LISTING = Y (not planned there): sized, month by month, as its share of the division in same-cluster stores that plan it × this store's division plan - or your own values - with rows borrowed from the peer store that plans it most.",
    'The "From Listing / Delisting" template leaves out a store × division whose every department is delisted (a closing or not-yet-open store): nothing would be left to absorb it.',
  ]],
  ['Method 2 - existing department changes', [
    'Store × Department rows with "&lt;Month&gt; New" values; months not in the file stay as original.',
  ]],
  ['Method 3 - new or split departments', [
    "Split: PARENT DEPARTMENT, NEW DEPARTMENT, SHARE % (optional STORE NAME; a store's own row overrides the all-store row). The parent keeps what is not shared out, the new departments take their share with the parent's MRP × display mix and ASPs; nothing else moves. Shares over 100% are refused.",
    "New department: \"&lt;Month&gt; New\" values with COPY FROM (whose MRP × display rows it takes); without it, a new name must start with an existing department's (LW_U_T-TOP F/S).",
  ]],
  ['Method 4 - listing / delisting shifted to a target', [
    'One row per change: DEPARTMENT, LISTING (Y / N), TARGET (a department, or a whole section from the Attribute Master, in the same division), optional FROM MONTH and STORE NAME (blank = every store it applies to).',
    "A delisted department's plan moves <b>only into the target</b>, split by the target departments' own plan that month; a newly listed one (sized like Method 1, or given) is taken <b>only out of the target</b>, capped at what the target has.",
    'Nothing else moves, so every store × division × month stays exactly as in the original.',
  ]],
  ['Method 5 - growth changes', [
    "DEPARTMENT and NEW GROWTH % over last year, optional STORE NAME (blank = every store; a store's own row overrides). Last year = the month-wise data-lake sales (Listing / Delisting app).",
    'Current growth = plan ÷ last year over the live months, on the stores with both; the plan is scaled by (1 + new) ÷ (1 + current) in every live month, keeping its month phasing.',
    'The rest of the same store × division absorbs it (capped at store × division × month); other divisions are not touched. A current growth beyond ±200% is flagged as "last year not comparable".',
  ]],
  ['Display-type cont % (every method)', [
    "The final plan is split to MRP × display rows by the <b>original plan's display-type cont %</b> in every store × department × month; the other departments are scaled as a whole, so theirs is kept too. Every run checks it.",
  ]],
  ['Checks on every run', [
    'Recomputed from the output: kept values exact, store × division season and month totals, grand total, Jan / Feb untouched, display-type cont % as the original. Any input error blocks the run; warnings and notes are listed with row examples.',
  ]],
];

const RULE_LOG = [
  {
    version: '4.0', date: '2026-09-26', status: 'in force', commit: 'this change',
    title: 'Method 4 (listing shift to a target), Method 5 (growth changes), display cont % rule for all',
    changes: [
      "Method 4: a delisted department's plan moves only into a chosen department or section; a new listing is taken only out of it - nothing else moves, store × division × month unchanged.",
      "Method 5: a department's new growth over last year (month-wise data-lake sales) scales its plan in every live month; only its own store × division absorbs it, capped at store × division × month.",
      "All methods: the final plan follows the original plan's display-type cont %; a new check proves it on every run.",
    ],
    why: 'User: "Shift will happen to the targeted choice and will only affect the target" / "the change should happen on the target\'s division and not all division" / "The final plan should be generated as per the original display plan cont % … This is for all methods".',
  },
  {
    version: '3.0', date: '2026-09-26', status: 'superseded', commit: '15d590e',
    title: 'Three revision methods; renamed AOP Re-Aligner',
    changes: [
      'Method 1 store listing changes (delist to 0 from a month; new listings sized from same-cluster peers), pre-filled from the Listing / Delisting app.',
      'Method 2 existing department changes - the original flow, unchanged.',
      'Method 3 new or split departments (split by share %, or a new department with COPY FROM).',
      'All three end in the same store × division realign, with the same checks.',
    ],
    why: 'User: "different ways to align the aop … changes which will be made when an already existing plan is there and some revisions are to be made".',
  },
  {
    version: '2.2', date: '2026-09-25', status: 'superseded', commit: '2a97a42',
    title: 'Strict input checks and independent verification',
    changes: [
      'Uploads are validated before anything runs: unknown stores, orphan departments, duplicate keys, wrong-slot files and non-numbers are reported with row examples; errors block the run.',
      'Every run is re-checked from the output (kept values, store × division totals by season and month, grand total, Jan / Feb untouched).',
    ],
    why: 'Revamp for reliability on the real 674k-row plan.',
  },
  {
    version: '2.1', date: '2026-09-24', status: 'superseded', commit: 'bfa32df',
    title: 'Revised values never change; qty at the original month-wise ASP',
    changes: [
      "When revised departments exceed a month's store × division total, the excess moves to the same store × division's other live months instead of scaling the revised values down.",
      'Qty = value ÷ the original ASP per Department × MRP × Display type × Month.',
    ],
    why: 'User: "the aop total for LW_U_T-top comes to 772.43 instead of 772.76" and "ASPs have to be calculated on department x mrp x display type for each month individually according to the original plan".',
  },
  {
    version: '2.0', date: '2026-09-24', status: 'superseded', commit: 'ae27ead',
    title: 'Target = Store × Division (attribute dropped)',
    changes: [
      'The attribute bucket was dropped: the store × division × month total is the target.',
      'Revised departments were capped (scaled down) when they alone exceeded that total.',
    ],
    why: 'User: "so drop attribute logic cap it on store x division".',
  },
  {
    version: '1.1', date: '2026-09-24', status: 'superseded', commit: 'f558834',
    title: 'Store × Division × Attribute target, Jan / Feb frozen',
    changes: [
      'Target = the original total per store × division × attribute × month.',
      "A month with no original plan split by the row's average share; Jan and Feb frozen.",
    ],
    why: 'User rules: store × division AOP stays true to the original; Jan & Feb never touched.',
  },
  {
    version: '1.0', date: '2026-09-24', status: 'superseded', commit: 'de6afc4',
    title: 'First version: pull a revised department plan back onto the original',
    changes: ["Revised departments keep their values; the store's other departments absorb the difference pro-rata, at Store × Department × MRP × Display type level."],
    why: 'User: "adjusts according to the original plan value keeping the revised plan values same and the month plan should be readjusted to the original plan at store_department_mrp_display type level".',
  },
];
