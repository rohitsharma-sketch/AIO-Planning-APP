// Forecast horizon (user rule 2026-09-25): show a forecast month only once its
// base month - the same month one year earlier - has CLOSED. Closed-through
// comes from the actuals sync (GET /api/config/db-sync/status -> closed_through,
// e.g. '2026-08' -> Mar'27..Aug'27 shown, Sep'27..Mar'28 hidden). Months
// appear on their own as they close; no config to touch. Falls back to
// "last calendar month" when the sync hasn't recorded a value.
import { useEffect, useMemo, useState } from 'react'
import { MONTHS } from './tags'
import { apiUrl } from './apiBase'

const MON = { Jan: 1, Feb: 2, Mar: 3, Apr: 4, May: 5, Jun: 6, Jul: 7, Aug: 8, Sep: 9, Oct: 10, Nov: 11, Dec: 12 }
// "Sep'27" -> "2026-09" (its base month, one year earlier)
export const baseYm = m => `${1999 + +m.slice(-2)}-${String(MON[m.slice(0, 3)]).padStart(2, '0')}`

function lastMonth() {
  const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export const visibleMonths = closedThrough => MONTHS.filter(m => baseYm(m) <= (closedThrough || lastMonth()))

let cached = null   // one fetch per page load, shared by every screen
export function useVisibleMonths() {
  const [ct, setCt] = useState(cached)
  useEffect(() => {
    if (cached) return
    fetch(apiUrl('/api/config/db-sync/status'), { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : {}))
      .then(d => { cached = d.closed_through || lastMonth(); setCt(cached) })
      .catch(() => { cached = lastMonth(); setCt(cached) })
  }, [])
  return useMemo(() => visibleMonths(ct), [ct])
}

// Month selection (user, 2026-09-26): the closed months by default, or the months picked by hand in Review - a
// future one too. Review and Results both read it, so they always show the same months. Remembered in this
// browser only; the 'aop-months' event keeps screens that are open at the same time in step.
// The pick also stores which months were closed when it was made, so a month that closes later still appears on
// its own. Anything unreadable (old format, no valid month) counts as "no pick" rather than crashing Results.
const PICK_KEY = 'aop_review_months'
function readPick() {
  try {
    const v = JSON.parse(localStorage.getItem(PICK_KEY))
    const months = (Array.isArray(v) ? v : v?.months || []).filter(m => MONTHS.includes(m))
    return months.length ? { months, closedAtPick: Array.isArray(v?.closedAtPick) ? v.closedAtPick : null } : null
  } catch { return null }
}

export function useShownMonths() {
  const closed = useVisibleMonths()
  const [picked, setPicked] = useState(readPick)
  useEffect(() => {
    const on = () => setPicked(readPick())
    window.addEventListener('aop-months', on)
    return () => window.removeEventListener('aop-months', on)
  }, [])
  const shown = useMemo(() => {
    if (!picked) return closed
    const newlyClosed = picked.closedAtPick ? closed.filter(m => !picked.closedAtPick.includes(m)) : []
    return MONTHS.filter(m => picked.months.includes(m) || newlyClosed.includes(m))
  }, [picked, closed])
  const pick = next => {   // [months] or null = back to the closed months
    const v = next ? { months: next, closedAtPick: closed } : null
    try { v ? localStorage.setItem(PICK_KEY, JSON.stringify(v)) : localStorage.removeItem(PICK_KEY) } catch { /* private window */ }
    setPicked(v)
    window.dispatchEvent(new Event('aop-months'))
  }
  return { shown, closed, picked: !!picked, pick }
}

// "Mar'27 – Jun'27" for a run of consecutive months, else the months listed (a pick can skip months, 2026-09-26).
export function monthSpan(list, fmt = m => m) {
  if (!list.length) return ''
  const idx = list.map(m => MONTHS.indexOf(m))
  const contiguous = idx.every((v, i) => i === 0 || v === idx[i - 1] + 1)
  return contiguous ? (list.length === 1 ? fmt(list[0]) : `${fmt(list[0])} – ${fmt(list[list.length - 1])}`) : list.map(fmt).join(', ')
}
