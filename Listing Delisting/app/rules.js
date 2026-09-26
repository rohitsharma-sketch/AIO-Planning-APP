// Rule version log, shown on the "Rules" tab - newest first.
// Whenever a suggestion / listing rule changes: add an entry at the TOP (next version number, date, what
// changed in plain words, why, and who asked), and mark the old one superseded. The numbers of the rules in
// force are NOT typed here - the Rules tab reads them live from suggestions.json (params), so they can't drift.
const RULE_LOG = [
  {
    version: '4.0', date: '2026-09-26', status: 'in force',
    title: 'Festival- and season-aware, like-for-like suggestions',
    changes: [
      'Sales read by calendar DATE (day-wise export), not by month, so a festival moving between months never moves a number.',
      "Festival days removed per store using the Calendar app's Festival Master (Pre / Core / Post per cluster) on each year's festival date; festivals get their own benchmark (lift vs normal days).",
      'Season windows (in-season / normal / off-season) worked out from the data for each season category, and re-derived on every daily build.',
      "A department is only ever compared with the SAME dates in earlier years and with the same department in its cluster's other stores - never one window against another.",
      'Benchmark years count only if the store traded most of that window and had been open 12 months before it (no new-store launch surges).',
      'New: "Held" (weak only on an off-season read, season about to start - review later) and "Relist" suggestions. Severity is now fixed cut-offs, not thirds.',
      'Every suggestion shows its dates, trading days, sales and benchmark years, traced to the source files.',
    ],
    why: 'User: "no attribute can be having a suggestion which is either driven by some festive period or some other surge … every window should be having their own benchmark … on the basis of calendar dates". Windows and thresholds confirmed by the user the same day: "keep the data-driven windows, thresholds are fine".',
    replaces: '3.0',
  },
  {
    version: '3.0', date: '2026-09-21', status: 'superseded',
    title: 'Fixed calendar-month in-season windows',
    changes: [
      'Each season category got a fixed in-season month list (e.g. summer Mar-Oct, winter Oct-Feb; regular always in season).',
      "Only in-season months of the last 3 complete months were scored, against the combo's own earlier in-season months; an off-season dip gave no signal at all.",
    ],
    why: 'User preferred a simple business rule over the continuous seasonal index of 2.0.',
    replaces: '2.0',
  },
  {
    version: '2.0', date: '2026-09-21', status: 'superseded',
    title: 'Real season category (ATTRIBUTE1) and a seasonal index',
    changes: [
      'Season category taken from the merchandise master attribute ATTRIBUTE1 (regular / summer / light winter / heavy winter / pre-winter / occasional).',
      'Risk dampened by a continuous seasonal index per department.',
    ],
    why: 'User rejected the earlier "how seasonal" tier as ambiguous - it did not say WHICH season.',
    replaces: '1.1',
  },
  {
    version: '1.1', date: '2026-09-21', status: 'superseded',
    title: 'Low / Medium / High severity',
    changes: ['Flagged combos split into thirds of their own score distribution (cut-offs moved with the data).'],
    why: 'User asked for a simple severity label next to the score.',
    replaces: '1.0',
  },
  {
    version: '1.0', date: '2026-09-21', status: 'superseded',
    title: 'First delisting-risk score',
    changes: [
      'A listed combo was flagged when its last 3 complete months averaged 50%+ below the 6 months before (baseline at least Rs 2,000 a month).',
      'Known limitation at the time: seasonal departments (raincoats, winterwear) flagged just for going off-season.',
    ],
    why: 'First screening signal for the app.',
    replaces: null,
  },
];
