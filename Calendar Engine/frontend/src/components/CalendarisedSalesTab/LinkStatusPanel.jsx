import { useState, useEffect, useMemo, useRef } from 'react'
import { startLinkScan, pollLinkScan, getSalesdataLinkSelection, putSalesdataLinkSelection } from '../../lib/api'

const LABELS = { mw: 'Month-wise', dw: 'Day-wise' }
const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

// "45s" / "2m 05s" - matches the compact style everywhere else in this app,
// not a full duration-formatting library for what's just an estimate.
function fmtDuration(totalSeconds) {
  if (totalSeconds == null) return null
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return m > 0 ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`
}

export default function LinkStatusPanel({ sourceType, isPlanner, onSelectionChange, hintYear, hintCalendarName }) {
  const [link, setLink] = useState(null)
  // null = idle; otherwise {pct, filesDone, filesTotal, elapsedSeconds, etaSeconds}
  // while a background scan job is running. Day-wise reads real columns across
  // 86M+ rows - the old code just called the scan endpoint directly and showed
  // a bare "Loading…" with no feedback and, worse, no error handling at all: a
  // network failure (not just a "not linked" response) left it stuck on
  // "Loading…" forever with no way to recover short of a full page reload.
  const [progress, setProgress] = useState(null)
  const [fetchError, setFetchError] = useState(null)
  const pollTimer = useRef(null)
  const [selection, setSelection] = useState(null)
  const [selectedMonths, setSelectedMonths] = useState([])
  // Which year's month pills are on screen. This is a VIEW filter only - it never
  // touches `selectedMonths`, which stays a flat list of 'YYYY-MM' strings spanning
  // every year (matching the old app, where _linkSelectedMonths was one global Set
  // per source and linkSelectYear only re-rendered the pills). So a user can have
  // 2026-08 ticked while looking at 2025's pills.
  const [year, setYear] = useState('')
  // Bulk "From year -> To year" range select, same idea as Version Setting's
  // Reference Year/Future Year pair used to generate a calendar - lets a multi-
  // year comparison (e.g. sync 2023-2026 in one go) be selected without
  // switching the single-year Sync Year view and clicking Select All per year.
  const [rangeFrom, setRangeFrom] = useState('')
  const [rangeTo, setRangeTo] = useState('')

  async function refresh(force) {
    clearTimeout(pollTimer.current)
    setFetchError(null)
    setLink(null)
    setProgress({ pct: 0, filesDone: 0, filesTotal: 0, etaSeconds: null })
    try {
      const { jobId } = await startLinkScan(sourceType, force)

      // Same transient-failure tolerance as Run Reindex's poll loop (see
      // CalendarisedSalesTab/index.jsx) - the scan's own background work can
      // briefly delay a poll response even though the job is still running fine.
      let misses = 0
      const MAX_MISSES = 5
      const poll = async () => {
        let p
        try {
          p = await pollLinkScan(jobId)
          misses = 0
        } catch (e) {
          misses += 1
          if (misses >= MAX_MISSES) { setProgress(null); setFetchError(`Lost contact with the scan job: ${e.message}`); return }
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        if (p.status === 'running') {
          setProgress({ pct: p.progressPct || 0, filesDone: p.filesDone || 0, filesTotal: p.filesTotal || 0, etaSeconds: p.etaSeconds })
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        setProgress(null)
        if (p.status === 'error' || !p.ok) { setFetchError(p.error || 'Scan failed'); return }
        setLink(p)
      }
      await poll()
    } catch (e) {
      setProgress(null)
      setFetchError(e.message)
    }
  }
  useEffect(() => {
    refresh(false)
    return () => clearTimeout(pollTimer.current) // stop polling if the tab/panel unmounts mid-scan
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
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
  // The selected Run Reindex calendar's reference year wins over "newest first"
  // when its data is actually available here - reindex only ever matches sales
  // from that exact year (see the comment in CalendarisedSalesTab/index.jsx), so
  // defaulting the pills to it is what actually lets the user pick a working
  // combination instead of guessing.
  const hintYearStr = hintYear != null ? String(hintYear) : null
  const activeYear = (year && byYear[year]) ? year
    : (hintYearStr && byYear[hintYearStr]) ? hintYearStr
    : years[0]
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

  // Same derive-don't-store pattern as activeYear above, so a Refresh that
  // shrinks `years` can't leave the range selects pointing at a year that no
  // longer exists. Defaults to the full span (oldest -> newest) so "Select
  // Range" with no prior interaction just selects everything, like ticking
  // every year one by one would.
  const effRangeFrom = (rangeFrom && byYear[rangeFrom]) ? rangeFrom : years[years.length - 1]
  const effRangeTo = (rangeTo && byYear[rangeTo]) ? rangeTo : years[0]

  function setRangeMonths(on) {
    if (!effRangeFrom || !effRangeTo) return
    const lo = Math.min(+effRangeFrom, +effRangeTo)
    const hi = Math.max(+effRangeFrom, +effRangeTo)
    const inRange = (link?.months || [])
      .filter(m => { const y = +m.month.slice(0, 4); return y >= lo && y <= hi })
      .map(m => m.month)
    setSelectedMonths(on
      ? [...selectedMonths, ...inRange.filter(m => !selectedMonths.includes(m))]
      : selectedMonths.filter(m => !inRange.includes(m)))
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

  if (progress) {
    return (
      <div className="card">
        <h4>Link Sales Data Source · {LABELS[sourceType]}</h4>
        <div style={{ background: 'var(--border)', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
          <div style={{
            width: `${progress.pct}%`, height: '100%', background: 'var(--navy2)',
            transition: 'width 0.3s ease',
          }} />
        </div>
        <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
          {progress.pct}%{progress.filesTotal > 0 && ` — ${progress.filesDone} of ${progress.filesTotal} files`}
          {progress.etaSeconds != null
            ? ` — about ${fmtDuration(progress.etaSeconds)} remaining`
            : (progress.filesDone > 0 ? '' : ' — estimating time remaining…')}
        </div>
      </div>
    )
  }

  if (fetchError) {
    return (
      <div className="card">
        <h4>Link Sales Data Source · {LABELS[sourceType]}</h4>
        <p><span className="scm-pill scm-pill-bad">Not linked</span> <span style={{ color: 'var(--red)' }}>{fetchError}</span></p>
        <button className="btn" onClick={() => refresh(false)}>Retry</button>
      </div>
    )
  }

  if (!link) return null // brief gap between the progress state clearing and `link` being set

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
          {hintCalendarName && (
            hintYearStr && byYear[hintYearStr] ? (
              <p style={{ fontSize: '11px', color: 'var(--muted)' }}>
                "{hintCalendarName}" reindexes <strong>{hintYear}</strong> sales — showing that year's months below.
              </p>
            ) : hintYearStr ? (
              <p style={{ fontSize: '11px', color: 'var(--warn)' }}>
                "{hintCalendarName}" reindexes <strong>{hintYear}</strong> sales, but no {hintYear} data is linked for {LABELS[sourceType]} here — Run Reindex will return nothing until that year is available.
              </p>
            ) : null
          )}
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
          {isPlanner && years.length > 1 && (
            <div className="link-month-picker" style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid var(--border)' }}>
              <div className="field">
                <label htmlFor={`linkRangeFrom_${sourceType}`}>From Year</label>
                <select id={`linkRangeFrom_${sourceType}`} value={effRangeFrom || ''} onChange={e => setRangeFrom(e.target.value)}>
                  {years.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor={`linkRangeTo_${sourceType}`}>To Year</label>
                <select id={`linkRangeTo_${sourceType}`} value={effRangeTo || ''} onChange={e => setRangeTo(e.target.value)}>
                  {years.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div className="link-month-picker-months">
                <label>&nbsp;</label>
                <div className="link-month-actions" style={{ marginTop: 0 }}>
                  <button onClick={() => setRangeMonths(true)} title={`Select every month from ${Math.min(+effRangeFrom, +effRangeTo)} to ${Math.max(+effRangeFrom, +effRangeTo)}`}>
                    Select Range
                  </button>
                  <button onClick={() => setRangeMonths(false)} title="Deselect every month in this range">Clear Range</button>
                </div>
              </div>
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
