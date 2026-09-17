// Regenerate calendar day pairs for both locked 2026->2027 templates using V2 engine
// Usage: node regen_calendars.mjs
// Outputs SQL to regen_calendars.sql — run it via psql

import { readFileSync, writeFileSync } from 'fs';

// ── Date utils ────────────────────────────────────────────────────────────────
function parseDate(s) {
  if (!s) return null;
  const [y, m, d] = s.split('-').map(Number);
  return isNaN(y) ? null : new Date(y, m - 1, d);
}
function fmtISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
function addDays(d, n) { const r = new Date(d); r.setDate(r.getDate()+n); return r; }
function calDiff(a, b) {
  const doy = d => Math.floor((d - new Date(d.getFullYear(), 0, 0)) / 86400000);
  let v = doy(b) - doy(a);
  if (v > 182) v -= 365; if (v < -182) v += 365;
  return v;
}
function yearDays(yr) {
  const days = [];
  for (let m = 0; m < 12; m++) {
    const n = new Date(yr, m+1, 0).getDate();
    for (let d = 1; d <= n; d++) days.push(new Date(yr, m, d));
  }
  return days;
}

// ── Engine ────────────────────────────────────────────────────────────────────
function buildFestMap(yr, fests, refYear) {
  const map = {};
  for (const f of fests) {
    const ds = yr === refYear ? (f.refDate ?? f.ref_date) : (f.futDate ?? f.fut_date);
    if (!ds) continue;
    const fd = parseDate(ds); if (!fd) continue;
    const pre = +f.pre||0, core = +f.core||1, post = +f.post||0;
    for (let pos = -pre; pos <= post+core-1; pos++) {
      const dd = addDays(fd, pos);
      if (dd.getFullYear() !== yr) continue;
      const cat = pos < 0 ? 'Pre-Festive' : pos < core ? 'Core Festive' : 'Post-Festive';
      const key = fmtISO(dd);
      if (!map[key]) map[key] = { festival: f.name, position: pos, category: cat };
    }
  }
  return map;
}
function getWeights() { return { festival: 1000, position: 500, month: 200, weekday: 100, prox: 1 }; }
function scoreMapping(rDay, fDay, rInfo, fInfo, W, maxShift, moPri) {
  let score = 0, mtype, mpri;
  const monthMatch = rDay.getMonth() === fDay.getMonth();
  const weekdayMatch = rDay.getDay() === fDay.getDay();
  const diff = calDiff(rDay, fDay);
  if (rInfo && fInfo && rInfo.festival === fInfo.festival && rInfo.position === fInfo.position) {
    score += W.festival + W.position; mtype = 'Festival-to-Festival'; mpri = 1;
  } else if (rInfo && fInfo && rInfo.position === fInfo.position) {
    score += W.position; mtype = 'Festive Relative Day'; mpri = 2;
  }
  score += (monthMatch ? W.month : 0) + (weekdayMatch ? W.weekday : 0)
         + W.prox * Math.max(0, maxShift - Math.abs(diff));
  if (!mtype) {
    if (monthMatch && weekdayMatch)           { mtype = 'Same Month + Same Weekday';    mpri = 3; }
    else if (monthMatch)                      { mtype = 'Same Month + Nearest Weekday'; mpri = 4; }
    else {
      const rm = rDay.getMonth(), fm = fDay.getMonth();
      const prev = (rm-1+12)%12, next = (rm+1)%12;
      if (moPri === 'prev') {
        if (fm === prev && weekdayMatch)      { mtype = 'Previous Month + Same Weekday'; mpri = 5; }
        else if (fm === next && weekdayMatch) { mtype = 'Next Month + Same Weekday';     mpri = 6; }
        else                                  { mtype = 'Nearest Available Date';         mpri = 7; }
      } else {
        if (fm === next && weekdayMatch)      { mtype = 'Next Month + Same Weekday';     mpri = 5; }
        else if (fm === prev && weekdayMatch) { mtype = 'Previous Month + Same Weekday'; mpri = 6; }
        else                                  { mtype = 'Nearest Available Date';         mpri = 7; }
      }
    }
  }
  return { score, mtype, mpri, monthMatch, weekdayMatch, diff };
}

function repairExcessiveShifts(assignments, rMap, fMap, W, maxShift, moPri) {
  const refToFut = new Map();
  assignments.forEach((m, fs) => refToFut.set(fmtISO(m.refDate), fs));
  const usedRefDays = [...refToFut.keys()].map(parseDate);
  const excess = d => Math.max(0, Math.abs(d) - maxShift);
  const swappable = m => m && m.mappingPriority >= 3 && !m.sharedRef;
  const applyRef = (m, rd, fd) => {
    const rs = fmtISO(rd), fs = fmtISO(fd), ri = rMap[rs], fi = fMap[fs];
    const s = scoreMapping(rd, fd, ri, fi, W, maxShift, moPri);
    Object.assign(m, { refDate: rd, festival: ri?.festival??null, festivePosition: ri?.position??null,
      festiveCategory: ri?.category??(fi?.category??'Non-Festive'),
      mappingType: s.mtype, mappingPriority: s.mpri, score: s.score,
      monthMatch: s.monthMatch, weekdayMatch: s.weekdayMatch, dateDiff: s.diff });
  };
  for (let pass = 0; pass < 10; pass++) {
    const outliers = [...assignments.values()].filter(m => swappable(m) && excess(m.dateDiff) > 0)
      .sort((a, b) => Math.abs(b.dateDiff) - Math.abs(a.dateDiff));
    if (!outliers.length) break;
    let improved = false;
    for (const m of outliers) {
      if (excess(m.dateDiff) === 0) continue;
      const fd = m.futureDate, fs = fmtISO(fd), r1 = m.refDate, r1s = fmtISO(r1);
      const cands = usedRefDays
        .filter(r => Math.abs(calDiff(r, fd)) < Math.abs(m.dateDiff) && r.getMonth() === fd.getMonth())
        .sort((a, b) => ((b.getDay()===fd.getDay())-(a.getDay()===fd.getDay())) || (Math.abs(calDiff(a,fd))-Math.abs(calDiff(b,fd))));
      let best = null, bestGain = 0;
      for (const r2 of cands) {
        const r2s = fmtISO(r2), f2s = refToFut.get(r2s);
        if (!f2s || f2s === fs) continue;
        const m2 = assignments.get(f2s);
        if (!swappable(m2)) continue;
        const d1 = calDiff(r2, fd), d2 = calDiff(r1, m2.futureDate);
        const gain = (excess(m.dateDiff)+excess(m2.dateDiff))-(excess(d1)+excess(d2));
        if (gain > bestGain) { bestGain = gain; best = { m2, r2 }; if (excess(d1)===0&&excess(d2)===0) break; }
      }
      if (!best) continue;
      const { m2, r2 } = best, r2s = fmtISO(r2), f2 = m2.futureDate, f2s = fmtISO(f2);
      applyRef(m, r2, fd); applyRef(m2, r1, f2);
      refToFut.set(r2s, fs); refToFut.set(r1s, f2s);
      improved = true;
    }
    if (!improved) break;
  }
}

function _v1Core(fests, refYr, futYr, maxShift, moPri, coreNames) {
  maxShift = +maxShift||45;
  const W = getWeights();
  const rDays = yearDays(refYr), fDays = yearDays(futYr);
  const rMapFull = buildFestMap(refYr, fests, refYr), fMapFull = buildFestMap(futYr, fests, refYr);
  const coreFests = coreNames ? fests.filter(f => coreNames.includes(f.name)) : fests;
  const rMap = buildFestMap(refYr, coreFests, refYr), fMap = buildFestMap(futYr, coreFests, refYr);
  const refFestLookup = {};
  for (const [ds, info] of Object.entries(rMap)) {
    const key = info.festival+'::'+info.position;
    if (!refFestLookup[key]) refFestLookup[key] = parseDate(ds);
  }
  const assignments = new Map(), usedRef = new Set();
  const festFutDays = fDays.filter(d => fMap[fmtISO(d)]);
  festFutDays.sort((a, b) => Math.abs(fMap[fmtISO(a)].position) - Math.abs(fMap[fmtISO(b)].position));
  for (const fd of festFutDays) {
    const fs = fmtISO(fd), fi = fMap[fs];
    const rd = refFestLookup[fi.festival+'::'+fi.position]; if (!rd) continue;
    const rs = fmtISO(rd); if (usedRef.has(rs)) continue;
    const ri = rMap[rs];
    const { score, mtype, mpri, monthMatch, weekdayMatch, diff } = scoreMapping(rd, fd, ri, fi, W, maxShift, moPri);
    assignments.set(fs, { refDate: rd, futureDate: fd,
      festival: ri?.festival??fi.festival, festivePosition: ri?.position??fi.position,
      festiveCategory: ri?.category??fi.category, futFestInfo: fi,
      mappingType: mtype, mappingPriority: mpri, score, monthMatch, weekdayMatch, dateDiff: diff });
    usedRef.add(rs);
  }
  const remFut = fDays.filter(d => !assignments.has(fmtISO(d)));
  const remRef = rDays.filter(d => !usedRef.has(fmtISO(d)));
  const remRefByMonth = new Map();
  for (const d of remRef) { const mo = d.getMonth(); if (!remRefByMonth.has(mo)) remRefByMonth.set(mo,[]); remRefByMonth.get(mo).push(d); }
  const allPairs = [];
  for (const fd of remFut) {
    const fs = fmtISO(fd), fi = fMap[fs];
    for (const rd of remRefByMonth.get(fd.getMonth())||[]) {
      const rs = fmtISO(rd), ri = rMap[rs];
      allPairs.push({ rs, fs, rd, fd, ri, fi, ...scoreMapping(rd, fd, ri, fi, W, maxShift, moPri) });
    }
  }
  allPairs.sort((a, b) => b.score - a.score);
  const localUsedFut = new Set(), localUsedRef = new Set();
  for (const p of allPairs) {
    if (localUsedFut.has(p.fs)||localUsedRef.has(p.rs)) continue;
    assignments.set(p.fs, { refDate: p.rd, futureDate: p.fd,
      festival: p.ri?.festival??null, festivePosition: p.ri?.position??null,
      festiveCategory: p.ri?.category??(p.fi?.category??'Non-Festive'), futFestInfo: p.fi,
      mappingType: p.mtype, mappingPriority: p.mpri, score: p.score,
      monthMatch: p.monthMatch, weekdayMatch: p.weekdayMatch, dateDiff: p.diff });
    localUsedFut.add(p.fs); localUsedRef.add(p.rs);
  }
  const stillUnassigned = fDays.filter(d => !assignments.has(fmtISO(d)));
  const stillAvailRef = rDays.filter(d => !usedRef.has(fmtISO(d)) && !localUsedRef.has(fmtISO(d)));
  for (const fd of stillUnassigned) {
    const fs = fmtISO(fd), fi = fMap[fs], fMonth = fd.getMonth();
    let rd, sharedRef = false, mappingLabel;
    const sameAvail = stillAvailRef.filter(d => d.getMonth() === fMonth);
    if (sameAvail.length) {
      sameAvail.sort((a, b) => Math.abs(calDiff(fd,a))-Math.abs(calDiff(fd,b)));
      rd = sameAvail[0]; stillAvailRef.splice(stillAvailRef.indexOf(rd),1); mappingLabel = 'Nearest Available Date';
    } else {
      const sameAny = rDays.filter(d => d.getMonth() === fMonth);
      if (sameAny.length) {
        sameAny.sort((a, b) => Math.abs(calDiff(fd,a))-Math.abs(calDiff(fd,b)));
        rd = sameAny[0]; sharedRef = true; mappingLabel = 'Nearest Available Date (Same-Month Reuse)';
      } else {
        rd = rDays.slice().sort((a, b) => (Math.abs(calDiff(fd,a))-Math.abs(calDiff(fd,b)))||((b.getDay()===fd.getDay())-(a.getDay()===fd.getDay())))[0];
        sharedRef = true; mappingLabel = 'Nearest Available Date (Leap Year Reuse)';
      }
    }
    const rs = fmtISO(rd), ri = rMap[rs];
    const s = scoreMapping(rd, fd, ri, fi, W, maxShift, moPri);
    assignments.set(fs, { refDate: rd, futureDate: fd, festival: ri?.festival??null,
      festivePosition: ri?.position??null, festiveCategory: ri?.category??(fi?.category??'Non-Festive'), futFestInfo: fi,
      mappingType: mappingLabel, mappingPriority: 7, score: s.score,
      monthMatch: s.monthMatch, weekdayMatch: s.weekdayMatch, dateDiff: s.diff, sharedRef });
  }
  repairExcessiveShifts(assignments, rMap, fMap, W, maxShift, moPri);
  const mappings = fDays.map(d => assignments.get(fmtISO(d))).filter(Boolean);
  for (const m of mappings) {
    if (m.mappingPriority <= 2) continue;
    const fi = fMapFull[fmtISO(m.futureDate)];
    if (fi) { m.festival = fi.festival; m.festivePosition = fi.position; m.festiveCategory = fi.category; }
  }
  return mappings;
}

function _v2Remap(v1, fests, refYr, futYr, maxShift, moPri, coreNames) {
  maxShift = +maxShift||45;
  const W = getWeights();
  const rDays = yearDays(refYr), fDays = yearDays(futYr);
  const rMapFull = buildFestMap(refYr, fests, refYr), fMapFull = buildFestMap(futYr, fests, refYr);
  const coreFests = coreNames ? fests.filter(f => coreNames.includes(f.name)) : fests;
  const rMap = buildFestMap(refYr, coreFests, refYr), fMap = buildFestMap(futYr, coreFests, refYr);
  const anchors    = v1.filter(m => m.mappingPriority <= 2);
  const toReassign = v1.filter(m => m.mappingPriority > 2);
  const committed  = new Set(anchors.map(m => fmtISO(m.refDate)));
  const lyByMonth  = new Map();
  for (const d of rDays) {
    if (committed.has(fmtISO(d))) continue;
    const mo = d.getMonth();
    if (!lyByMonth.has(mo)) lyByMonth.set(mo,[]); lyByMonth.get(mo).push(d);
  }
  const allPairs = [];
  for (const m of toReassign) {
    const fd = m.futureDate, fs = fmtISO(fd), fi = fMap[fs];
    let pool;
    if (fMapFull[fs]) {
      pool = lyByMonth.get(fd.getMonth())||[];
    } else {
      const adjMo = moPri === 'next' ? (fd.getMonth()+1)%12 : (fd.getMonth()-1+12)%12;
      pool = lyByMonth.get(adjMo)||[];
    }
    for (const rd of pool) {
      const rs = fmtISO(rd), ri = rMap[rs];
      allPairs.push({ rs, fs, rd, fd, ri, fi, ...scoreMapping(rd, fd, ri, fi, W, maxShift, moPri) });
    }
  }
  allPairs.sort((a, b) => b.score - a.score);
  const assigned = new Map();
  const usedFut = new Set(), usedRef = new Set(committed);
  for (const p of allPairs) {
    if (usedFut.has(p.fs)||usedRef.has(p.rs)) continue;
    assigned.set(p.fs, { refDate: p.rd, futureDate: p.fd,
      festival: p.ri?.festival??null, festivePosition: p.ri?.position??null,
      festiveCategory: p.ri?.category??(p.fi?.category??'Non-Festive'), futFestInfo: p.fi,
      mappingType: p.mtype, mappingPriority: p.mpri, score: p.score,
      monthMatch: p.monthMatch, weekdayMatch: p.weekdayMatch, dateDiff: p.diff, sharedRef: false });
    usedFut.add(p.fs); usedRef.add(p.rs);
  }
  const stillAvail = rDays.filter(d => !usedRef.has(fmtISO(d)));
  for (const m of toReassign) {
    const fs = fmtISO(m.futureDate);
    if (assigned.has(fs)) continue;
    if (!stillAvail.length) { assigned.set(fs, {...m, sharedRef: true}); continue; }
    stillAvail.sort((a, b) => Math.abs(calDiff(a, m.futureDate))-Math.abs(calDiff(b, m.futureDate)));
    const rd = stillAvail.shift(), rs = fmtISO(rd), ri = rMap[rs], fi = fMap[fs];
    const s = scoreMapping(rd, m.futureDate, ri, fi, W, maxShift, moPri);
    assigned.set(fs, { refDate: rd, futureDate: m.futureDate,
      festival: ri?.festival??null, festivePosition: ri?.position??null,
      festiveCategory: ri?.category??(fi?.category??'Non-Festive'), futFestInfo: fi,
      mappingType: 'Nearest Available Date (Cross-Month)', mappingPriority: 7, score: s.score,
      monthMatch: s.monthMatch, weekdayMatch: s.weekdayMatch, dateDiff: s.diff, sharedRef: false });
    usedRef.add(rs);
  }
  const anchorMap = new Map(anchors.map(m => [fmtISO(m.futureDate), m]));
  const result = fDays.map(d => anchorMap.get(fmtISO(d))||assigned.get(fmtISO(d))).filter(Boolean);
  for (const m of result) {
    if (m.mappingPriority <= 2) continue;
    const fi = fMapFull[fmtISO(m.futureDate)];
    if (fi) { m.festival = fi.festival; m.festivePosition = fi.position; m.festiveCategory = fi.category; }
  }
  return result;
}

function generateMappingsV2(fests, refYr, futYr, maxShift, moPri, coreNames) {
  const v1 = _v1Core(fests, refYr, futYr, maxShift, moPri, coreNames);
  return _v2Remap(v1, fests, refYr, futYr, maxShift, moPri, coreNames);
}

// ── Config ────────────────────────────────────────────────────────────────────
const REF_YR = 2026, FUT_YR = 2027, MAX_SHIFT = 45, MO_PRI = 'prev';

// Exact DB cluster names as keys
const CORE_BY_CLUSTER = {
  'Kashmir':            ['Diwali', 'Eid al-Fitr', 'Eid al-Adha'],
  'UP + NCR':           ['Holi', 'Navratri', 'Dussehra', 'Diwali'],
  'UP + BIHAR - PUJA':  ['Holi', 'Navratri', 'Dussehra', 'Diwali', 'Chhath Puja'],
  'BIHAR':              ['Holi', 'Navratri', 'Dussehra', 'Diwali', 'Chhath Puja'],
  'JAMMU + RJ':         ['Holi', 'Navratri', 'Dussehra', 'Diwali'],
  'ODISHA':             ['Holi', 'Navratri', 'Dussehra', 'Diwali', 'Rath Yatra', 'Nuakhai'],
  'N. EAST - PUJA':     ['Navratri', 'Dussehra', 'Diwali'],
  'N. EAST':            ['Navratri', 'Dussehra', 'Diwali'],
  'JH + MP + CG':       ['Holi', 'Navratri', 'Dussehra', 'Diwali'],
  'WB':                 ['Navratri', 'Dussehra', 'Diwali'],
};

// Calendar IDs from DB
const CALENDARS = {
  'all':      { id: 1789555936689n, name: '2026 -> 2027 Calendar - All',        coreOnly: false },
  'coreOnly': { id: 1789556012651n, name: '2026 -> 2027 Calendar W/ Core Only', coreOnly: true  },
};

// ── Load cluster data ─────────────────────────────────────────────────────────
const SCRATCHPAD = 'C:/Users/A9820/AppData/Local/Temp/claude/C--Users-A9820-Documents-CLaude---New-Projects-Buyer-s-Input-Sheet/dee85349-5077-4530-bf28-2ec362ba99d0/scratchpad';
const clusters = readFileSync(`${SCRATCHPAD}/clusters_v2.jsonl`, 'utf8')
  .split('\n').filter(l => l.trim()).map(l => JSON.parse(l));

// ── Generate SQL ──────────────────────────────────────────────────────────────
const sqlLines = ['BEGIN;'];

for (const [mode, cal] of Object.entries(CALENDARS)) {
  const calId = cal.id.toString();
  sqlLines.push(`\n-- Delete existing day pairs for: ${cal.name}`);
  sqlLines.push(`DELETE FROM calendar.calendar_day_pairs WHERE calendar_id = ${calId};`);

  let totalPairs = 0;
  const insertLines = [];

  for (const { cluster, festivals } of clusters) {
    const coreNames = cal.coreOnly ? (CORE_BY_CLUSTER[cluster] || ['Holi','Navratri','Dussehra','Diwali']) : null;
    const v2 = generateMappingsV2(festivals, REF_YR, FUT_YR, MAX_SHIFT, MO_PRI, coreNames);

    if (v2.length !== 365) {
      console.error(`FAIL: ${cluster} produced ${v2.length} pairs (expected 365) for ${cal.name}`);
      process.exit(1);
    }

    const refs = new Set(v2.map(m => fmtISO(m.refDate)));
    if (refs.size !== 365) {
      console.error(`FAIL: ${cluster} has ${refs.size} distinct ref dates (expected 365) for ${cal.name}`);
      process.exit(1);
    }

    for (let i = 0; i < v2.length; i++) {
      const m = v2[i];
      insertLines.push(`(${calId}, '${cluster.replace(/'/g,"''")}', ${i+1}, '${fmtISO(m.refDate)}', '${fmtISO(m.futureDate)}')`);
    }
    totalPairs += v2.length;
    console.log(`  ${cal.name.slice(0,30).padEnd(30)} | ${cluster.padEnd(18)} | ${v2.length} pairs | ${refs.size} unique ref`);
  }

  sqlLines.push(`\n-- Insert ${totalPairs} new day pairs for: ${cal.name}`);
  sqlLines.push(`INSERT INTO calendar.calendar_day_pairs (calendar_id, cluster_name, seq, ref_date, fut_date) VALUES`);
  sqlLines.push(insertLines.join(',\n') + ';');
}

sqlLines.push('\nCOMMIT;');

// Verify totals
const sql = sqlLines.join('\n');
writeFileSync(`${SCRATCHPAD}/regen_calendars.sql`, sql, 'utf8');
console.log(`\nSQL written to regen_calendars.sql (${Math.round(sql.length/1024)}KB)`);
