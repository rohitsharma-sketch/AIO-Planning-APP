// "Why did part of this month's sales land in another month?" - hover text
// for the Month Wise Matrix (user request 2026-09-25: no guesswork when e.g.
// Feb and Mar share March's sales). Pure: works off the calendar detail
// (getCalendar) already loaded for the reindex - its day map and each
// cluster's festival list with LY/TY dates and pre/core/post windows.
//
// A moved day FOLLOWS a festival when it sits at the same offset from that
// festival in both years (e.g. 3 days before Holi 2025 -> 3 days before Holi
// 2026). Every other moved day is an ORDINARY day re-placed to keep each TY
// day matched to one LY day once festival days shifted around it.

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const toDate = s => new Date(`${s}T00:00:00`)
const dayDiff = (a, b) => Math.round((toDate(a) - toDate(b)) / 864e5)
const fmtDay = s => `${+s.slice(8, 10)} ${MON[+s.slice(5, 7) - 1]} ${s.slice(0, 4)}`
export const fmtMonth = ym => `${MON[+ym.slice(5, 7) - 1]}'${ym.slice(2, 4)}`

// {cluster: {refMonth: {futMonth: [[ref, fut], ...]}}} for days that change month,
// plus {cluster: festivals} - from getCalendar's detail.
export function buildMoveInfo(detail) {
  const moves = {}, fests = {}
  for (const cl of detail?.clusters || []) fests[cl.name] = cl.festivals || []
  for (const [cl, pairs] of Object.entries(detail?.dayMap || {})) {
    const m = (moves[cl] = {})
    for (const [ref, fut] of pairs) {
      const rm = ref.slice(0, 7), fm = fut.slice(0, 7)
      if (rm.slice(5) === fm.slice(5)) continue   // same calendar month -> not a move
      ;((m[rm] ??= {})[fm] ??= []).push([ref, fut])
    }
  }
  return { moves, fests }
}

function followedFestival(festivals, ref, fut) {
  for (const f of festivals) {
    if (!f.refDate || !f.futDate) continue
    const pre = +f.pre || 0, core = +f.core || 1, post = +f.post || 0
    const pos = dayDiff(ref, f.refDate)
    if (pos < -pre || pos > core + post - 1 || dayDiff(fut, f.futDate) !== pos) continue
    return { f, part: pos < 0 ? 'build-up' : pos < core ? 'festival days' : 'after-days' }
  }
  return null
}

// "11–14 Mar 2025" style ranges from a sorted list of ISO dates.
function ranges(dates) {
  const out = []
  let start = dates[0], prev = dates[0]
  for (const d of dates.slice(1).concat([null])) {
    if (d && dayDiff(d, prev) === 1) { prev = d; continue }
    out.push(start === prev ? fmtDay(start)
      : start.slice(0, 7) === prev.slice(0, 7) ? `${+start.slice(8, 10)}–${fmtDay(prev)}` : `${fmtDay(start)}–${fmtDay(prev)}`)
    start = prev = d
  }
  return out.join(', ')
}

const shiftYear = (ym, dy) => `${+ym.slice(0, 4) + dy}${ym.slice(4)}`

// "Feb'25 (7)" list + the festivals behind those flows, for the domino text.
function flowText(entries, festivals) {
  const names = new Set()
  const parts = entries.map(([ym, pairs]) => {
    for (const [r, f] of pairs) { const h = followedFestival(festivals, r, f); if (h) names.add(h.f.name) }
    return `${fmtMonth(ym)} (${pairs.length})`
  })
  return parts.join(', ') + (names.size ? ` - ${[...names].join(' / ')}` : '')
}

// Why ordinary days had to cross from rm to fm: fm's own LY month sent days
// elsewhere (leaving fm short) and/or rm's own TY month already took days in
// from other LY months (leaving rm with spare days) - a domino of festival shifts.
function dominoReason(info, cluster, rm, fm, festivals) {
  const moves = info.moves[cluster] || {}
  const fmLY = shiftYear(fm, -1), rmTY = shiftYear(rm, 1)
  const sentAway = Object.entries(moves[fmLY] || {}).filter(([to]) => to !== fm)
  const takenIn = Object.entries(moves).filter(([from]) => from !== rm)
    .map(([from, tos]) => [from, tos[rmTY]]).filter(([, p]) => p?.length)
  const bits = []
  if (sentAway.length) bits.push(`${fmtMonth(fmLY)} sent ${sentAway.reduce((a, [, p]) => a + p.length, 0)} of its days to ${flowText(sentAway, festivals)}, leaving ${fmtMonth(fm)} short`)
  if (takenIn.length) bits.push(`${fmtMonth(rmTY)} already takes ${takenIn.reduce((a, [, p]) => a + p.length, 0)} days from ${flowText(takenIn, festivals)}, so ${fmtMonth(rm)} has spare days`)
  return bits.length ? bits.join('; ') + '.' : 'Re-placed to keep every TY day matched to one LY day after festival days shifted.'
}

// Multi-line hover text for one Month Wise Matrix cell; null when no day changed month.
export function explainMove(info, cluster, rm, fm, { amount, refDays } = {}) {
  const pairs = info?.moves?.[cluster]?.[rm]?.[fm]
  if (!pairs?.length) return null
  const festivals = info.fests?.[cluster] || []
  const groups = new Map()
  for (const [ref, fut] of pairs) {
    const hit = followedFestival(festivals, ref, fut)
    const key = hit ? `${hit.f.name}|${hit.part}` : 'ordinary'
    if (!groups.has(key)) groups.set(key, { hit, refs: [], futs: [] })
    groups.get(key).refs.push(ref); groups.get(key).futs.push(fut)
  }
  const head = `${fmtMonth(rm)} → ${fmtMonth(fm)}: ${pairs.length}${refDays ? ` of ${refDays}` : ''} day${pairs.length > 1 ? 's' : ''} moved`
    + (amount != null ? ` · ₹${Math.round(amount).toLocaleString('en-IN')}` : '')
  const lines = [head]
  for (const { hit, refs, futs } of groups.values()) {
    refs.sort(); futs.sort()
    const span = `${ranges(refs)} → ${ranges(futs)}`
    if (hit) {
      lines.push(`• ${hit.f.name} ${hit.part} (${refs.length}): ${span}`)
      lines.push(`  ${hit.f.name} moved from ${fmtDay(hit.f.refDate)} to ${fmtDay(hit.f.futDate)}, so its ${hit.part} moved with it.`)
    } else {
      lines.push(`• Ordinary days (${refs.length}): ${span}`)
      lines.push(`  ${dominoReason(info, cluster, rm, fm, festivals)}`)
    }
  }
  lines.push('Sales split by the share of the month\'s days that moved.')
  return lines.join('\n')
}
