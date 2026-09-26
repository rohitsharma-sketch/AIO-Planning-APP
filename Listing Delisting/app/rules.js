// Latest rule change, shown at the foot of the "Rules" tab. Only the current rules are kept (user, 2026-09-26:
// no version numbers, no history). When a rule changes: replace `date` and `changes` with what is now true, in
// plain words. The numbers of the rules in force are NOT typed here - the Rules tab reads them live from
// suggestions.json (params), so they can't drift.
const RULES_LATEST = {
  date: '2026-09-26',
  changes: [
    'Sales are read by calendar date (day-wise export), so a festival moving between months never moves a number.',
    "Festival days are removed per store using the Calendar app's Festival Master, and festivals are benchmarked on their own.",
    'Season windows (in-season / normal / off-season) come from the data for each season category and are re-worked on every daily build.',
    "A department is only compared with the same dates in earlier years and with the same department in its cluster's other stores.",
    'A benchmark year counts only if the store traded most of that window and had been open 12 months before it.',
    'Suggestions are Delist, Held (weak only off-season, season about to start) and Relist; every row shows the dates, days and sales behind it.',
  ],
};
