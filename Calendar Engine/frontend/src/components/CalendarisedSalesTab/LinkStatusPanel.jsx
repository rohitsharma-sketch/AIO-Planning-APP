import { useState, useEffect, useMemo } from 'react'
import { getSalesdataLink, getSalesdataLinkDaywise, getSalesdataLinkSelection, putSalesdataLinkSelection } from '../../lib/api'

const FETCHERS = { mw: getSalesdataLink, dw: getSalesdataLinkDaywise }
const LABELS = { mw: 'Month-wise', dw: 'Day-wise' }
const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function LinkStatusPanel({ sourceType, isPlanner, onSelectionChange }) {
  const [link, setLink] = useState(null)
  const [selection, setSelection] = useState(null)
  const [selectedMonths, setSelectedMonths] = useState([])
  // Which year's month pills are on screen. This is a VIEW filter only - it never
  // touches `selectedMonths`, which stays a flat list of 'YYYY-MM' strings spanning
  // every year (matching the old app, where _linkSelectedMonths was one global Set
  // per source and linkSelectYear only re-rendered the pills). So a user can have
  // 2026-08 ticked while looking at 2025's pills.
  const [year, setYear] = useState('')

  function refresh(force) {
    FETCHERS[sourceType](force).then(setLink)
  }
  useEffect(() => {
    refresh(false)
    getSalesdataLinkSelection(sourceType).then(s => {
      setSelection(s)
      setSelectedMonths(s.months || [])
      // Push the PERSISTED selection up to the parent too, not just the one made by
      // an explicit sync() below. Without this the checkboxes visibly show last
      // session's synced months while the parent's `selections` state is still {},
      // so "Run Reindex" on a freshly loaded page posts months: [] and the backend
      // rejects it with "months is required".
      onSelectionChange?.(sourceType, s)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceType])

  // Group the flat, already-sorted `months` array from the backend
  // (scans.py returns [{month:'YYYY-MM', rows:N}, ...] sorted ascending) by year.
  // Years run newest-first so the most recent year is the default, exactly as the
  // old app did (`Object.keys(byYear).sort().reverse()`, then `years[0]`).
  const { byYear, years } = useMemo(() => {
    const g = {}
    ;(link?.months || []).forEach(m => { const y = m.month.slice(0, 4); (g[y] = g[y] || []).push(m) })
    return { byYear: g, years: Object.keys(g).sort().reverse() }
  }, [link])

  // Derive rather than store the effective year, so a Refresh that changes the
  // available years can never strand us on a year that no longer exists. Mirrors
  // the old app's `if (!_linkSelectedYear[src] || !byYear[...]) = years[0]` guard.
  const activeYear = (year && byYear[year]) ? year : years[0]
  const monthsForYear = byYear[activeYear] || []

  // Select All / Clear are scoped to the CURRENTLY VISIBLE year only - the old
  // app's linkSelectAllMonths() iterates byYear[_linkSelectedYear[src]], not the
  // whole month list, and its button is literally labelled "Select All (this year)".
  function setYearMonths(on) {
    const inYear = monthsForYear.map(m => m.month)
    setSelectedMonths(on
      ? [...selectedMonths, ...inYear.filter(m => !selectedMonths.includes(m))]
      : selectedMonths.filter(m => !inYear.includes(m)))
  }

  async function sync() {
    if (!isPlanner || !link) return
    // The mw scan result carries a single `path` string, but the dw (day-wise)
    // scan result has no `path` field at all - it reads from multiple folders
    // and returns them as `dirs` (see scans.py _scan_daywise_link). The backend's
    // salesdata_link_selection.path column is NOT NULL, so sending `path: undefined`
    // (dropped by JSON.stringify) would 500 with a KeyError on PUT for dw. Fall back
    // to joining `dirs` so both source types always send a non-empty string.
    const path = link.path || (Array.isArray(link.dirs) ? link.dirs.join('; ') : '')
    // Sort before sending: with the year-scoped picker the user can tick months in
    // any order across years, and the old app likewise sorted on sync
    // (`[..._linkSelectedMonths[src]].sort()`). Keeps the persisted list readable
    // and the "Last synced" line stable.
    const payload = { months: [...selectedMonths].sort(), path, syncedAt: new Date().toISOString() }
    await putSalesdataLinkSelection(sourceType, payload)
    setSelection(payload)
    onSelectionChange?.(sourceType, payload)
  }

  if (!link) return <p>Loading…</p>

  return (
    <div className="card">
      <h4>Link Sales Data Source · {LABELS[sourceType]}</h4>
      {link.ok ? (
        <>
          {link.offline && (
            <p>
              <span className="scm-pill scm-pill-warn">Offline</span>{' '}
              Source unreachable right now — showing last known data as of{' '}
              <span className="date-mono">{link.scannedAt}</span>.
            </p>
          )}
          <p>
            <span className="scm-pill scm-pill-ok">Linked</span>{' '}
            {link.rowCount?.toLocaleString()} rows across {link.months?.length} months.
            {' '}Range: <span className="date-mono">{link.dateRange?.min}</span> – <span className="date-mono">{link.dateRange?.max}</span>.
          </p>
          <p>
            Stores: <span className="scm-pill scm-pill-ok">{link.stores?.matched?.length} matched</span>{' '}
            <span className={`scm-pill ${link.stores?.unmatchedInSource?.length ? 'scm-pill-warn' : 'scm-pill-ok'}`}>
              {link.stores?.unmatchedInSource?.length} unmatched in source
            </span>
          </p>
          <div className="link-month-picker">
            <div className="field">
              <label htmlFor={`linkYearSel_${sourceType}`}>Sync Year</label>
              <select id={`linkYearSel_${sourceType}`} value={activeYear || ''} onChange={e => setYear(e.target.value)}>
                {years.map(y => (
                  <option key={y} value={y}>{y} ({byYear[y].length} months)</option>
                ))}
              </select>
            </div>
            <div className="link-month-picker-months">
              <label>Months</label>
              <div className="month-pills">
                {monthsForYear.map(m => {
                  const id = `lmp_${sourceType}_${m.month}`
                  return (
                    <div className="month-pill" key={m.month}>
                      <input type="checkbox" id={id} checked={selectedMonths.includes(m.month)} disabled={!isPlanner}
                        onChange={e => setSelectedMonths(e.target.checked ? [...selectedMonths, m.month] : selectedMonths.filter(x => x !== m.month))} />
                      <label htmlFor={id} title={`${m.rows.toLocaleString()} rows`}>{MONTH_ABBR[+m.month.slice(5, 7) - 1]}</label>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
          {isPlanner && (
            <div className="link-month-actions">
              <button onClick={() => setYearMonths(true)}>Select All (this year)</button>
              <button onClick={() => setYearMonths(false)}>Clear</button>
              <button className="btn" onClick={sync}>Sync Selected Months</button>
            </div>
          )}
        </>
      ) : (
        <p><span className="scm-pill scm-pill-bad">Not linked</span> <span style={{ color: 'var(--red)' }}>{link.error}</span></p>
      )}
      <button onClick={() => refresh(true)}>Refresh</button>
      {selection?.syncedAt && <p style={{ color: 'var(--muted)' }}>Last synced: {selection.syncedAt}</p>}
    </div>
  )
}
