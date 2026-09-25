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
