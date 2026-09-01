// Ported from `Calendar Engine/calendar_engine.html` lines 1376-1732
// (─── Festive Map ─── through ─── Monthly Summary ───).
//
// Deviation from a strict verbatim copy: the source functions read
// configuration (refYear/futYear/maxShift/moPri) directly off the DOM via
// `g(id)` (= document.getElementById) and `document.querySelector`, and
// `buildFestMap` fell back to a page-level `festivals` global when no list
// was passed in. None of that is available in a standalone module, so those
// reads have been converted to explicit function parameters (refYr, futYr,
// maxShift, moPri, fests) threaded through the call chain. The scoring/
// assignment/repair/validation algorithm itself is unchanged.
import { parseDate, fmtISO, fmtDisp, addDays, calDiff, yearDays } from './dateUtils';

// Ported from the source file's lines 1336-1337 (defined alongside MON3,
// just above the Date Utilities section there) since `validate` depends on
// them for issue descriptions and they have no DOM dependency of their own.
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

// ─── Festive Map ─────────────────────────────────────────────────────────────
export function buildFestMap(yr, fests, refYear) {
  // Returns { dateStr: { festival, festObj, position, category, priority } }
  const map = {};
  for (const f of fests) {
    const ds = yr === refYear ? f.refDate : f.futDate;
    if (!ds) continue;
    const fd = parseDate(ds);
    if (!fd) continue;
    const pre = +f.pre || 0, core = +f.core || 1, post = +f.post || 0;
    for (let pos = -pre; pos <= post + core - 1; pos++) {
      const dd = addDays(fd, pos);
      if (dd.getFullYear() !== yr) continue;
      let cat = pos < 0 ? 'Pre-Festive' : pos < core ? 'Core Festive' : 'Post-Festive';
      const key = fmtISO(dd);
      if (!map[key]) {
        map[key] = { festival: f.name, festObj: f, position: pos, category: cat };
      }
    }
  }
  return map;
}

// ─── Scoring ─────────────────────────────────────────────────────────────────
export function getWeights() {
  return { festival: 1000, position: 500, month: 200, weekday: 100, prox: 1 };
}
export function scoreMapping(rDay, fDay, rInfo, fInfo, W, maxShift, moPri) {
  let score = 0, mtype, mpri;
  const monthMatch   = rDay.getMonth() === fDay.getMonth();
  const weekdayMatch = rDay.getDay()   === fDay.getDay();
  const diff = calDiff(rDay, fDay);
  if (rInfo && fInfo && rInfo.festival === fInfo.festival && rInfo.position === fInfo.position) {
    score += W.festival + W.position; mtype = 'Festival-to-Festival'; mpri = 1;
  } else if (rInfo && fInfo && rInfo.position === fInfo.position) {
    score += W.position; mtype = 'Festive Relative Day'; mpri = 2;
  }
  score += (monthMatch ? W.month : 0) + (weekdayMatch ? W.weekday : 0)
         + W.prox * Math.max(0, maxShift - Math.abs(diff));
  if (!mtype) {
    if (monthMatch && weekdayMatch)         { mtype = 'Same Month + Same Weekday';    mpri = 3; }
    else if (monthMatch)                    { mtype = 'Same Month + Nearest Weekday'; mpri = 4; }
    else {
      const mPri = moPri;
      const rm = rDay.getMonth(), fm = fDay.getMonth();
      const prev = (rm-1+12)%12, next = (rm+1)%12;
      if (mPri === 'prev') {
        if (fm === prev && weekdayMatch)    { mtype = 'Previous Month + Same Weekday'; mpri = 5; }
        else if (fm === next && weekdayMatch){ mtype = 'Next Month + Same Weekday';    mpri = 6; }
        else                               { mtype = 'Nearest Available Date';         mpri = 7; }
      } else {
        if (fm === next && weekdayMatch)    { mtype = 'Next Month + Same Weekday';    mpri = 5; }
        else if (fm === prev && weekdayMatch){ mtype = 'Previous Month + Same Weekday';mpri = 6; }
        else                               { mtype = 'Nearest Available Date';         mpri = 7; }
      }
    }
  }
  return { score, mtype, mpri, monthMatch, weekdayMatch, diff };
}

// ─── Engine ───────────────────────────────────────────────────────────────────
// coreNames: per-cluster list of festival NAMES allowed to anchor the shift
// (Phase 1) or exempt a mapping from the same-month containment rule below -
// see CORE_FESTIVALS_BY_CLUSTER in festivalData.js. null/undefined = no
// restriction (every festival on the list is core) - kept only so any other
// caller of this function that hasn't been updated to pass core names still
// behaves exactly as before, rather than silently losing every anchor.
export function generateMappings(fests, refYr, futYr, maxShift, moPri, coreNames) {
  maxShift = +maxShift || 45;
  const W = getWeights();
  const rDays = yearDays(refYr), fDays = yearDays(futYr);

  // Full festival map (every festival on the cluster's list, core or not) -
  // used ONLY to LABEL each mapping's festival/festivePosition/
  // festiveCategory for display (Monthly Summary, the output preview, the
  // reindexed-sales Festival row) at the end of this function. Never
  // consulted while deciding which day maps to which - a non-core festival
  // like Good Friday must not get to move the calendar just because it's on
  // the list.
  const rMapFull = buildFestMap(refYr, fests, refYr), fMapFull = buildFestMap(futYr, fests, refYr);

  // Core-only map - the ONLY festivals that can anchor Phase 1 or exempt a
  // day from the same-month rule in Phases 2-4.
  const coreFests = coreNames ? fests.filter(f => coreNames.includes(f.name)) : fests;
  const rMap = buildFestMap(refYr, coreFests, refYr), fMap = buildFestMap(futYr, coreFests, refYr);

  // Build ref festive lookup: festival+position -> refDate
  const refFestLookup = {}; // 'FestName::pos' -> refDate
  for (const [ds, info] of Object.entries(rMap)) {
    const key = info.festival + '::' + info.position;
    if (!refFestLookup[key]) refFestLookup[key] = parseDate(ds);
  }

  const assignments = new Map(); // futDateStr -> mapping obj
  const usedRef = new Set();

  // ── Phase 1: Core festival anchor assignments (iterate FUT festive days) ──
  const festFutDays = fDays.filter(d => fMap[fmtISO(d)]);
  // Sort: core days first (position=0), then pre/post by absolute position
  festFutDays.sort((a, b) => Math.abs(fMap[fmtISO(a)].position) - Math.abs(fMap[fmtISO(b)].position));
  for (const fd of festFutDays) {
    const fs = fmtISO(fd), fi = fMap[fs];
    const fk = fi.festival + '::' + fi.position;
    const rd = refFestLookup[fk];
    if (!rd) continue;
    const rs = fmtISO(rd);
    if (usedRef.has(rs)) continue;
    const ri = rMap[rs];
    const { score, mtype, mpri, monthMatch, weekdayMatch, diff } = scoreMapping(rd, fd, ri, fi, W, maxShift, moPri);
    assignments.set(fs, { refDate: rd, futureDate: fd,
      festival: ri ? ri.festival : fi.festival,
      festivePosition: ri ? ri.position : fi.position,
      festiveCategory: ri ? ri.category : fi.category,
      futFestInfo: fi,
      mappingType: mtype, mappingPriority: mpri, score, monthMatch, weekdayMatch, dateDiff: diff });
    usedRef.add(rs);
  }

  // ── Phase 2: Remaining days - SAME MONTH ONLY ─────────────────────────────
  // Once core festivals are anchored, every other day (including non-core
  // festival days - Good Friday etc. are ordinary days for this purpose)
  // must be re-shuffled strictly within its own calendar month, never into
  // an adjacent one. Bucketing candidates by month NUMBER (0-11, ignoring
  // year since ref/fut are different years) enforces this directly - it
  // replaces the old ±(maxShift + 14) day search window, which only
  // preferred same-month via scoring and could still cross a boundary.
  const remFut = fDays.filter(d => !assignments.has(fmtISO(d)));
  const remRef = rDays.filter(d => !usedRef.has(fmtISO(d)));

  const remRefByMonth = new Map();
  for (const d of remRef) {
    const mo = d.getMonth();
    if (!remRefByMonth.has(mo)) remRefByMonth.set(mo, []);
    remRefByMonth.get(mo).push(d);
  }

  const allPairs = [];
  for (const fd of remFut) {
    const fs = fmtISO(fd), fi = fMap[fs];
    const sameMonthRef = remRefByMonth.get(fd.getMonth()) || [];
    for (const rd of sameMonthRef) {
      const rs = fmtISO(rd), ri = rMap[rs];
      const s = scoreMapping(rd, fd, ri, fi, W, maxShift, moPri);
      allPairs.push({ rs, fs, rd, fd, ri, fi, ...s });
    }
  }
  allPairs.sort((a, b) => b.score - a.score);

  const localUsedFut = new Set(), localUsedRef = new Set();
  for (const p of allPairs) {
    if (localUsedFut.has(p.fs) || localUsedRef.has(p.rs)) continue;
    assignments.set(p.fs, {
      refDate: p.rd, futureDate: p.fd,
      festival: p.ri ? p.ri.festival : null,
      festivePosition: p.ri ? p.ri.position : null,
      festiveCategory: p.ri ? p.ri.category : (p.fi ? p.fi.category : 'Non-Festive'),
      futFestInfo: p.fi,
      mappingType: p.mtype, mappingPriority: p.mpri, score: p.score,
      monthMatch: p.monthMatch, weekdayMatch: p.weekdayMatch, dateDiff: p.diff
    });
    localUsedFut.add(p.fs); localUsedRef.add(p.rs);
  }

  // ── Phase 3: Fallback for any still-unassigned fut days - same month first ─
  const stillUnassigned = fDays.filter(d => !assignments.has(fmtISO(d)));
  const stillAvailRef   = rDays.filter(d => !usedRef.has(fmtISO(d)) && !localUsedRef.has(fmtISO(d)));
  for (const fd of stillUnassigned) {
    const fs = fmtISO(fd), fi = fMap[fs];
    const fMonth = fd.getMonth();
    let rd, sharedRef = false, mappingLabel;

    const sameMonthAvail = stillAvailRef.filter(d => d.getMonth() === fMonth);
    if (sameMonthAvail.length) {
      sameMonthAvail.sort((a, b) => Math.abs(calDiff(fd, a)) - Math.abs(calDiff(fd, b)));
      rd = sameMonthAvail[0];
      stillAvailRef.splice(stillAvailRef.indexOf(rd), 1);
      mappingLabel = 'Nearest Available Date';
    } else {
      // This month's own reference days are completely exhausted - a real
      // imbalance (e.g. a core festival's true date fell in a different
      // month between refYr and futYr, shrinking this month's leftover
      // pool). Non-festive days may NEVER cross into another month, so
      // reuse (share) the nearest reference day already assigned within
      // THIS SAME month rather than borrowing an unused day from
      // elsewhere - the same sharing mechanism the leap-year case below
      // already uses, just scoped to one month instead of the whole year.
      const sameMonthAny = rDays.filter(d => d.getMonth() === fMonth);
      if (sameMonthAny.length) {
        sameMonthAny.sort((a, b) => Math.abs(calDiff(fd, a)) - Math.abs(calDiff(fd, b)));
        rd = sameMonthAny[0];
        sharedRef = true;
        mappingLabel = 'Nearest Available Date (Same-Month Reuse)';
      } else {
        // Leap-year case (or, defensively, a reference year with literally
        // no days in this month): reuse the nearest reference day anywhere
        // (prefer same weekday) instead of leaving this future day unmapped.
        rd = rDays.slice().sort((a, b) =>
          (Math.abs(calDiff(fd, a)) - Math.abs(calDiff(fd, b))) ||
          ((b.getDay() === fd.getDay()) - (a.getDay() === fd.getDay())))[0];
        sharedRef = true;
        mappingLabel = 'Nearest Available Date (Leap Year Reuse)';
      }
    }
    const rs = fmtISO(rd), ri = rMap[rs];
    const s = scoreMapping(rd, fd, ri, fi, W, maxShift, moPri);
    assignments.set(fs, {
      refDate: rd, futureDate: fd,
      festival: ri ? ri.festival : null, festivalPriority: ri ? ri.priority : null,
      festivePosition: ri ? ri.position : null,
      festiveCategory: ri ? ri.category : (fi ? fi.category : 'Non-Festive'),
      futFestInfo: fi,
      mappingType: mappingLabel,
      mappingPriority: 7, score: s.score,
      monthMatch: s.monthMatch, weekdayMatch: s.weekdayMatch, dateDiff: s.diff,
      sharedRef
    });
  }

  // ── Phase 4: repair excessive shifts by swapping reference days ──────────
  // (same-month constrained too - see repairExcessiveShifts)
  repairExcessiveShifts(assignments, rMap, fMap, W, maxShift, moPri);

  const mappings = fDays.map(d => assignments.get(fmtISO(d))).filter(Boolean);

  // ── Labeling pass: attach the FULL festival identity for display ─────────
  // Phases 1-4 above only ever see core festivals, so every non-core day's
  // festival/festivePosition/festiveCategory is still null/Non-Festive at
  // this point. Fill those in from the full map now - purely cosmetic, runs
  // after every date decision is already final. Skips mappings the core map
  // already anchored (mappingPriority <= 2: Festival-to-Festival / Festive
  // Relative Day) so a genuinely core-anchored day can never be relabeled
  // with a different, non-core festival that happens to share the date
  // under "first defined wins" overlap resolution.
  for (const m of mappings) {
    if (m.mappingPriority <= 2) continue;
    const fi = fMapFull[fmtISO(m.futureDate)];
    if (fi) {
      m.festival = fi.festival;
      m.festivePosition = fi.position;
      m.festiveCategory = fi.category;
    }
  }

  return mappings;
}

// Greedy assignment can strand a few non-festive future days far from any free
// reference day (the "100-day shift" problem). For each mapping beyond maxShift,
// look for a neighbouring reference day within the limit and swap with its
// current partner when that lowers the combined excess. Festival-anchored days
// (Festival-to-Festival / Festive Relative Day) and leap-year shared days are
// never moved. Repeats until no swap improves anything.
export function repairExcessiveShifts(assignments, rMap, fMap, W, maxShift, moPri) {
  const refToFut = new Map();
  assignments.forEach((m, fs) => refToFut.set(fmtISO(m.refDate), fs));
  const usedRefDays = [...refToFut.keys()].map(parseDate);
  const excess = d => Math.max(0, Math.abs(d) - maxShift);
  const swappable = m => m && m.mappingPriority >= 3 && !m.sharedRef;
  const applyRef = (m, rd, fd) => {
    const rs = fmtISO(rd), fs = fmtISO(fd), ri = rMap[rs], fi = fMap[fs];
    const s = scoreMapping(rd, fd, ri, fi, W, maxShift, moPri);
    Object.assign(m, {
      refDate: rd,
      festival: ri ? ri.festival : null,
      festivePosition: ri ? ri.position : null,
      festiveCategory: ri ? ri.category : (fi ? fi.category : 'Non-Festive'),
      mappingType: s.mtype, mappingPriority: s.mpri, score: s.score,
      monthMatch: s.monthMatch, weekdayMatch: s.weekdayMatch, dateDiff: s.diff
    });
  };

  for (let pass = 0; pass < 10; pass++) {
    const outliers = [...assignments.values()]
      .filter(m => swappable(m) && excess(m.dateDiff) > 0)
      .sort((a, b) => Math.abs(b.dateDiff) - Math.abs(a.dateDiff));
    if (!outliers.length) break;
    let improved = false;
    for (const m of outliers) {
      if (excess(m.dateDiff) === 0) continue; // fixed by an earlier swap this pass
      const fd = m.futureDate, fs = fmtISO(fd), r1 = m.refDate, r1s = fmtISO(r1);
      // Reference days closer to this future day than its current one (ideally within
      // the limit), same weekday first, nearest first - same month only (see
      // generateMappings' Phase 2 comment: non-core days may never cross a
      // month boundary, and a repair swap must not undo that either).
      const cands = usedRefDays
        .filter(r => Math.abs(calDiff(r, fd)) < Math.abs(m.dateDiff) && r.getMonth() === fd.getMonth())
        .sort((a, b) => ((b.getDay() === fd.getDay()) - (a.getDay() === fd.getDay()))
                     || (Math.abs(calDiff(a, fd)) - Math.abs(calDiff(b, fd))));
      let best = null, bestGain = 0;
      for (const r2 of cands) {
        const r2s = fmtISO(r2), f2s = refToFut.get(r2s);
        if (!f2s || f2s === fs) continue;
        const m2 = assignments.get(f2s);
        if (!swappable(m2)) continue;
        const d1 = calDiff(r2, fd), d2 = calDiff(r1, m2.futureDate);
        const gain = (excess(m.dateDiff) + excess(m2.dateDiff)) - (excess(d1) + excess(d2));
        if (gain > bestGain) {
          bestGain = gain; best = { m2, r2 };
          if (excess(d1) === 0 && excess(d2) === 0) break; // both inside the limit - good enough
        }
      }
      if (!best) continue;
      const { m2, r2 } = best, r2s = fmtISO(r2), f2 = m2.futureDate, f2s = fmtISO(f2);
      applyRef(m, r2, fd);
      applyRef(m2, r1, f2);
      refToFut.set(r2s, fs);
      refToFut.set(r1s, f2s);
      improved = true;
    }
    if (!improved) break;
  }
}

// ─── Validation ───────────────────────────────────────────────────────────────
// coreNames: same per-cluster core-festival list generateMappings takes -
// check C below only makes sense for festivals that are actually allowed to
// anchor the shift; flagging a non-core festival (Good Friday etc.) as
// "mismatched" would just be re-describing the same-month containment rule
// as if it were a bug. null/undefined = every festival treated as core
// (matches generateMappings' own no-restriction default).
export function validate(mappings, refYr, futYr, maxShift, fests, coreNames) {
  const issues = [];
  const usedFutDates = new Map(); // futDateStr -> [refDates]
  maxShift = +maxShift || 45;
  const rMap = buildFestMap(refYr, fests, refYr);
  const fMap = buildFestMap(futYr, fests, refYr);
  const futFestLookup = {};
  for (const [ds, info] of Object.entries(fMap)) {
    const key = info.festival + '::' + info.position;
    if (!futFestLookup[key]) futFestLookup[key] = ds;
  }

  const usedRefDates = new Map(); // refDateStr -> [futDates]
  for (const m of mappings) {
    const rk = fmtISO(m.refDate);
    if (!usedRefDates.has(rk)) usedRefDates.set(rk, []);
    usedRefDates.get(rk).push(fmtDisp(m.futureDate));
  }

  // A: Unmapped future dates
  const mapped = new Set(mappings.map(m => fmtISO(m.futureDate)));
  for (const d of yearDays(futYr)) {
    if (!mapped.has(fmtISO(d))) {
      issues.push({ type:'error', icon:'ERR', title:'Unmapped Future Date', desc:`${fmtDisp(d)} has no Reference Year mapping.` });
    }
  }

  // B: Duplicate reference dates
  for (const [rd, futs] of usedRefDates.entries()) {
    if (futs.length > 1) {
      const shared = mappings.some(m => fmtISO(m.refDate) === rd && m.sharedRef);
      if (shared) {
        issues.push({ type:'info', icon:'INFO', title:'Shared Reference Date', desc:`Reference ${rd} is reused for ${futs.join(', ')} — that month (or ${futYr} overall, if it's a leap year) has more future days needing a match than it has spare reference days.` });
      } else {
        issues.push({ type:'error', icon:'ERR', title:'Duplicate Reference Date', desc:`${rd} is used by ${futs.length} future dates: ${futs.join(', ')}` });
      }
    }
  }

  // C: Festival mismatch (festive ref → non-festive future when festive future available)
  for (const m of mappings) {
    if (!m.festival) continue;
    if (coreNames && !coreNames.includes(m.festival)) continue; // non-core - not supposed to anchor, not a mismatch
    if (m.mappingType !== 'Festival-to-Festival' && m.mappingType !== 'Festive Relative Day') {
      const targetKey = m.festival + '::' + m.festivePosition;
      const targetFutDs = futFestLookup[targetKey];
      if (targetFutDs) {
        issues.push({ type:'warn', icon:'WARN', title:'Festival Mismatch', desc:`${fmtDisp(m.refDate)} (${m.festival} pos ${m.festivePosition >= 0 ? '+' : ''}${m.festivePosition}) mapped to ${fmtDisp(m.futureDate)} instead of its festive equivalent ${targetFutDs}. The target date was already claimed by an earlier festival in the list.` });
      }
    }
  }

  // D: Excessive date shift
  for (const m of mappings) {
    if (Math.abs(m.dateDiff) > maxShift) {
      issues.push({ type:'warn', icon:'WARN', title:'Excessive Date Shift', desc:`${fmtDisp(m.refDate)} -> ${fmtDisp(m.futureDate)}: calendar shift of ${m.dateDiff > 0 ? '+' : ''}${m.dateDiff} days exceeds max (${maxShift}).` });
    }
  }

  // E: Month leakage (non-festive crossed month when same-month option existed)
  const futByMonthWday = {};
  const allFutDays = yearDays(futYr);
  for (const fd of allFutDays) {
    const k = fd.getMonth()+'::'+fd.getDay();
    if (!futByMonthWday[k]) futByMonthWday[k] = [];
    futByMonthWday[k].push(fmtISO(fd));
  }
  const assignedFut = new Set(mappings.map(m => fmtISO(m.futureDate)));
  for (const m of mappings) {
    if (m.festival) continue; // skip festive days
    if (m.monthMatch) continue; // same month is fine
    const k = m.refDate.getMonth()+'::'+m.refDate.getDay();
    const candidates = (futByMonthWday[k] || []).filter(ds => assignedFut.has(ds));
    // Check if any same-month same-weekday was available (might be used by other mappings, but flag if it exists)
    const sameMonthSameWday = (futByMonthWday[k] || []).filter(ds => {
      const dd = parseDate(ds); return dd && dd.getMonth() === m.refDate.getMonth();
    });
    if (sameMonthSameWday.length > 0 && !m.monthMatch) {
      issues.push({ type:'info', icon:'INFO', title:'Month Leakage', desc:`Non-festive ${fmtDisp(m.refDate)} (${DAYS[m.refDate.getDay()]}) mapped across month to ${fmtDisp(m.futureDate)}. Same-month ${DAYS[m.refDate.getDay()]}s in ${MONTHS[m.refDate.getMonth()]} may have been consumed by other mappings.` });
    }
  }

  // F: Weekday mismatch for non-festive same-month
  for (const m of mappings) {
    if (m.festival) continue;
    if (!m.monthMatch) continue;
    if (!m.weekdayMatch) {
      issues.push({ type:'info', icon:'INFO', title:'Weekday Mismatch', desc:`Non-festive ${fmtDisp(m.refDate)} (${DAYS[m.refDate.getDay()]}) mapped to ${fmtDisp(m.futureDate)} (${DAYS[m.futureDate.getDay()]}) — different weekday within same month. Same-month ${DAYS[m.refDate.getDay()]}s may have been consumed.` });
    }
  }

  return issues;
}

// ─── Monthly Summary ──────────────────────────────────────────────────────────
export function computeMonthly(mappings) {
  // byRefMonth[m] = { total, sameMonth, prevMonth, nextMonth, other, pre, core, post, non }
  const byRef = Array.from({length:12}, () => ({ total:0, sameMonth:0, prevMonth:0, nextMonth:0, other:0, pre:0, core:0, post:0, non:0, daysToFut:{} }));
  const byFut = Array.from({length:12}, () => ({ total:0, daysFromRef:{} }));
  for (const m of mappings) {
    const rm = m.refDate.getMonth(), fm = m.futureDate.getMonth();
    const r = byRef[rm], f = byFut[fm];
    r.total++;
    if (rm === fm)           r.sameMonth++;
    else if (fm === (rm-1+12)%12) r.prevMonth++;
    else if (fm === (rm+1)%12)   r.nextMonth++;
    else                          r.other++;
    if (!r.daysToFut[fm]) r.daysToFut[fm] = 0; r.daysToFut[fm]++;
    if (m.festiveCategory === 'Pre-Festive')  r.pre++;
    else if (m.festiveCategory === 'Core Festive') r.core++;
    else if (m.festiveCategory === 'Post-Festive') r.post++;
    else r.non++;
    f.total++;
    if (!f.daysFromRef[rm]) f.daysFromRef[rm] = 0; f.daysFromRef[rm]++;
  }
  return { byRef, byFut };
}
