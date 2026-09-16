// ─── Date Utilities ──────────────────────────────────────────────────────────
// Ported verbatim from `Calendar Engine/calendar_engine.html` lines 1340-1375.
// MON3 is ported from the same file's line 1338 (defined just above the Date
// Utilities section there) since fmtDisp depends on it and it has no DOM
// dependency of its own.
const MON3 = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

export function parseDate(s) {
  if (!s) return null;
  const p = s.split('-');
  if (p.length !== 3) return null;
  return new Date(+p[0], +p[1]-1, +p[2]);
}
export function fmtISO(d) {
  return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
}
export function fmtDisp(d) {
  return String(d.getDate()).padStart(2,'0')+'-'+MON3[d.getMonth()]+'-'+d.getFullYear();
}
export function addDays(d, n) {
  const r = new Date(d); r.setDate(r.getDate()+n); return r;
}
export function dayOfYear(d) {
  const s = new Date(d.getFullYear(), 0, 1);
  return Math.round((d - s) / 86400000) + 1;
}
export function calDiff(ref, fut) { // day-of-year diff, wrapping +/-182
  let diff = dayOfYear(fut) - dayOfYear(ref);
  if (diff > 182) diff -= 365;
  if (diff < -182) diff += 365;
  return diff;
}
export function yearDays(yr) {
  const days = [], d = new Date(yr, 0, 1), end = new Date(yr+1, 0, 1);
  while (d < end) { days.push(new Date(d)); d.setDate(d.getDate()+1); }
  return days;
}
export function weekNum(d) {
  const jan1 = new Date(d.getFullYear(), 0, 1);
  return Math.ceil(((d - jan1) / 86400000 + jan1.getDay() + 1) / 7);
}
