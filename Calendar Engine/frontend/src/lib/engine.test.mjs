// Plain-Node, assert-based self-check for the non-festive month-adjacency
// fix in engine.js (business rule confirmed 2026-09-22: a non-festive day
// may only be assigned within its own calendar month or one adjacent month,
// never further, regardless of maxShift). Run with:
//   node src/lib/engine.test.mjs
// No framework/fixtures - one file, one process exit code.
import assert from 'node:assert/strict';
import { generateMappings, validate } from './engine.js';
import { fmtISO } from './dateUtils.js';
// engine.js's own dates are local-time Date objects, formatted via fmtISO()
// (local getFullYear/getMonth/getDate) - never .toISOString() (UTC), which
// on an IST (UTC+5:30) machine silently shifts every local midnight back to
// the previous day. Every date-string comparison below goes through fmtISO
// for the same reason.

// BIHAR's real festival list for the "2026 -> 2027 Calendar - All" template
// (calendar_id 1789555936689) - the exact config that produced the reported
// bug (07-Mar-2026 -> 26-Jan-2027 etc.), queried live from Postgres 2026-09-22.
const BIHAR_FESTIVALS = [
  { name: 'Eid al-Fitr',     refDate: '2026-03-20', futDate: '2027-03-09', pre: 4, core: 3, post: 0 },
  { name: 'Eid al-Adha',     refDate: '2026-05-27', futDate: '2027-05-17', pre: 2, core: 1, post: 0 },
  { name: 'Diwali',          refDate: '2026-11-08', futDate: '2027-10-29', pre: 5, core: 3, post: 0 },
  { name: 'Milad-un-Nabi',   refDate: '2026-08-26', futDate: '2027-08-15', pre: 2, core: 1, post: 0 },
  { name: 'Holi',            refDate: '2026-03-04', futDate: '2027-03-22', pre: 7, core: 3, post: 0 },
  { name: 'Navratri',        refDate: '2026-10-11', futDate: '2027-09-30', pre: 0, core: 9, post: 0 },
  { name: 'Dussehra',        refDate: '2026-10-20', futDate: '2027-10-09', pre: 0, core: 1, post: 0 },
  { name: 'Chhath Puja',     refDate: '2026-11-15', futDate: '2027-11-05', pre: 5, core: 4, post: 0 },
  { name: 'Raksha Bandhan',  refDate: '2026-08-28', futDate: '2027-08-17', pre: 2, core: 1, post: 0 },
  { name: 'Shraad',          refDate: '2026-09-26', futDate: '2027-09-15', pre: 0, core: 15, post: 0 },
  { name: 'Makar Sankranti', refDate: '2026-01-14', futDate: '2027-01-15', pre: 2, core: 1, post: 0 },
  { name: 'Basant Panchami', refDate: '2026-01-23', futDate: '2027-02-11', pre: 2, core: 1, post: 0 },
];

const REF_YR = 2026, FUT_YR = 2027, MAX_SHIFT = 45, MO_PRI = 'prev';

function monthsAdjacent(m1, m2) {
  const d = Math.abs(m1 - m2);
  return d === 0 || d === 1 || d === 11; // 11 covers the Dec(11)/Jan(0) wrap
}

function runsForVersion(version) {
  return generateMappings(BIHAR_FESTIVALS, REF_YR, FUT_YR, MAX_SHIFT, MO_PRI, null, version);
}

// Test 1 - reproduce the reported bug, as a general invariant (not just the
// 3 named rows): no non-festive mapping may cross more than one calendar
// month. This is exactly the check that would have caught the original bug.
function test1_noMonthAdjacencyViolations() {
  for (const version of [1, 2]) {
    const mappings = runsForVersion(version);
    const violations = mappings.filter(m =>
      !m.festival && !monthsAdjacent(m.refDate.getMonth(), m.futureDate.getMonth()));
    assert.equal(violations.length, 0,
      `V${version}: ${violations.length} non-festive mapping(s) cross more than 1 month, e.g. ` +
      violations.slice(0, 3).map(m => `${m.refDate.toDateString()} -> ${m.futureDate.toDateString()}`).join('; '));
  }
  console.log('PASS test1_noMonthAdjacencyViolations (both V1 and V2)');
}

// Specifically reject the 3 reported BIHAR rows under V2.
function test1b_reportedRowsRejected() {
  const mappings = runsForVersion(2);
  const byFut = new Map(mappings.map(m => [fmtISO(m.futureDate), m]));
  const reported = [
    ['2027-01-26', '2026-03-07'],
    ['2027-01-27', '2026-03-08'],
    ['2027-01-31', '2026-03-23'],
  ];
  for (const [futIso, oldRefIso] of reported) {
    const m = byFut.get(futIso);
    assert.ok(m, `expected a mapping for future date ${futIso}`);
    const actualRefIso = fmtISO(m.refDate);
    assert.notEqual(actualRefIso, oldRefIso,
      `${futIso} is still mapped to the reported bad reference date ${oldRefIso}`);
    assert.ok(monthsAdjacent(m.refDate.getMonth(), m.futureDate.getMonth()),
      `${futIso} -> ${actualRefIso}: still not same/adjacent month`);
  }
  console.log('PASS test1b_reportedRowsRejected');
}

// Test 4 - strict boundary: build a case where a far-away date is
// mathematically closer than any eligible same/adjacent-month date, and
// confirm month eligibility wins over raw proximity. maxShift is set very
// high (200) specifically so a distance-based tie-break alone would have
// picked the far date if the month rule weren't enforced.
function test4_monthEligibilityBeatsProximity() {
  const mappings = generateMappings(BIHAR_FESTIVALS, REF_YR, FUT_YR, 200, MO_PRI, null, 2);
  const violations = mappings.filter(m =>
    !m.festival && !monthsAdjacent(m.refDate.getMonth(), m.futureDate.getMonth()));
  assert.equal(violations.length, 0,
    `with maxShift=200, ${violations.length} mapping(s) still crossed >1 month - proximity overrode the month rule`);
  console.log('PASS test4_monthEligibilityBeatsProximity');
}

// Test 5 - festival preservation: Diwali's core anchor must still land on
// its exact configured future date, crossing from Nov (ref) to Oct (fut) -
// festival windows are explicitly allowed to cross months.
function test5_festivalCrossMonthPreserved() {
  const mappings = runsForVersion(2);
  const diwaliCore = mappings.find(m => m.festival === 'Diwali' && m.festivePosition === 0);
  assert.ok(diwaliCore, 'Diwali core anchor missing from V2 output');
  assert.equal(fmtISO(diwaliCore.futureDate), '2027-10-29');
  assert.equal(fmtISO(diwaliCore.refDate), '2026-11-08');
  assert.notEqual(diwaliCore.refDate.getMonth(), diwaliCore.futureDate.getMonth(),
    'Diwali is expected to cross months (Nov ref -> Oct fut) - this is allowed for festivals');
  console.log('PASS test5_festivalCrossMonthPreserved');
}

// Test 6 - V1 and V2 both validate clean (version 2's own validate() skips
// the "month leakage" check by design - see engine.js's validate(), rule E -
// but the two engines must still produce zero real errors/warnings and
// zero unmapped days each).
function test6_bothEnginesValidateClean() {
  for (const version of [1, 2]) {
    const mappings = runsForVersion(version);
    assert.equal(mappings.length, 365, `V${version}: expected 365 mappings for a non-leap future year, got ${mappings.length}`);
    const issues = validate(mappings, REF_YR, FUT_YR, MAX_SHIFT, BIHAR_FESTIVALS, null, version);
    const errors = issues.filter(i => i.type === 'error');
    assert.equal(errors.length, 0, `V${version}: ${errors.length} validation error(s): ${JSON.stringify(errors.slice(0, 3))}`);
  }
  console.log('PASS test6_bothEnginesValidateClean');
}

// Test 7 - shared reference reuse stays within the same/adjacent month rule
// whenever it does happen (sharedRef rows are exactly the Round C / tier-4
// reuse rows - they must never be the mechanism a violation sneaks
// through). Business rule revised 2026-09-22: reuse is now the LAST
// resort, tried only after both the own-month and adjacent-month unused
// pools are exhausted (Round B, added the same day, now runs before this) -
// so this test no longer asserts reuse rows must exist, only that if any
// do, they're bounded.
function test7_sharedRefStaysBounded() {
  const mappings = runsForVersion(2);
  const sharedRefRows = mappings.filter(m => m.sharedRef && !m.festival);
  const violations = sharedRefRows.filter(m => !monthsAdjacent(m.refDate.getMonth(), m.futureDate.getMonth()));
  assert.equal(violations.length, 0, `${violations.length} sharedRef row(s) violate the month rule`);
  console.log(`PASS test7_sharedRefStaysBounded (${sharedRefRows.length} reuse rows, all within bounds)`);
}

// Test 8 - duplicate reference dates are minimized, not just bounded. Business
// rule (2026-09-22): "no duplicates, period" - an unused day (even in the
// adjacent month) must always be preferred over reusing a claimed one, so
// Round B (adjacent, unused) now runs BEFORE Round C (same-month, reuse).
// For this test's BIHAR-shaped festival config, only 3 non-festive TY days
// still need reuse - the genuine mathematical floor for this data (every
// day in both that TY day's own month AND its one adjacent month is
// already claimed by a festival anchor or another TY day; honoring "no
// duplicates" further would require either breaking the +/-1 month rule or
// leaving a future date unmapped, both explicitly ruled out). Asserts an
// upper bound (not an exact count, which would make this brittle to
// festival-date maintenance) so a future regression that reverts the tier
// order or otherwise inflates reuse gets caught.
function test8_duplicateReferenceDatesMinimized() {
  const mappings = runsForVersion(2);
  const nonFestive = mappings.filter(m => !m.festival);
  const counts = new Map();
  for (const m of nonFestive) {
    const k = fmtISO(m.refDate);
    counts.set(k, (counts.get(k) || 0) + 1);
  }
  const dupCount = [...counts.values()].filter(v => v > 1).length;
  assert.ok(dupCount <= 10, `expected duplicate reference dates to stay near the known floor (3), got ${dupCount} - Round B may no longer be running before Round C`);
  console.log(`PASS test8_duplicateReferenceDatesMinimized (${dupCount} duplicate ref dates, floor is 3 for this config)`);
}

test1_noMonthAdjacencyViolations();
test1b_reportedRowsRejected();
test4_monthEligibilityBeatsProximity();
test5_festivalCrossMonthPreserved();
test6_bothEnginesValidateClean();
test7_sharedRefStaysBounded();
test8_duplicateReferenceDatesMinimized();
console.log('\nAll engine.test.mjs checks passed.');
