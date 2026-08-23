import { useState, useEffect } from 'react'
import { getSalesdataLink, getSalesdataLinkDaywise, getSalesdataLinkSelection, putSalesdataLinkSelection } from '../../lib/api'

const FETCHERS = { mw: getSalesdataLink, dw: getSalesdataLinkDaywise }
const LABELS = { mw: 'Month-wise', dw: 'Day-wise' }

export default function LinkStatusPanel({ sourceType, isPlanner, onSelectionChange }) {
  const [link, setLink] = useState(null)
  const [selection, setSelection] = useState(null)
  const [selectedMonths, setSelectedMonths] = useState([])

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

  async function sync() {
    if (!isPlanner || !link) return
    // The mw scan result carries a single `path` string, but the dw (day-wise)
    // scan result has no `path` field at all - it reads from multiple folders
    // and returns them as `dirs` (see scans.py _scan_daywise_link). The backend's
    // salesdata_link_selection.path column is NOT NULL, so sending `path: undefined`
    // (dropped by JSON.stringify) would 500 with a KeyError on PUT for dw. Fall back
    // to joining `dirs` so both source types always send a non-empty string.
    const path = link.path || (Array.isArray(link.dirs) ? link.dirs.join('; ') : '')
    const payload = { months: selectedMonths, path, syncedAt: new Date().toISOString() }
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
          <div>
            {(link.months || []).map(m => (
              <label key={m.month}>
                <input type="checkbox" checked={selectedMonths.includes(m.month)} disabled={!isPlanner}
                  onChange={e => setSelectedMonths(e.target.checked ? [...selectedMonths, m.month] : selectedMonths.filter(x => x !== m.month))} />
                {m.month} ({m.rows.toLocaleString()})
              </label>
            ))}
          </div>
          {isPlanner && <button className="btn" onClick={sync}>Sync Selected Months</button>}
        </>
      ) : (
        <p><span className="scm-pill scm-pill-bad">Not linked</span> <span style={{ color: 'var(--red)' }}>{link.error}</span></p>
      )}
      <button onClick={() => refresh(true)}>Refresh</button>
      {selection?.syncedAt && <p style={{ color: 'var(--muted)' }}>Last synced: {selection.syncedAt}</p>}
    </div>
  )
}
