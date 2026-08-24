import { useState, useEffect, useRef } from 'react'
import LinkStatusPanel from './LinkStatusPanel'
import ReindexOutputPanel from './ReindexOutputPanel'
import { startReindex, pollReindex, listCalendarLibrary, getCalendar, getStoreClusterMap } from '../../lib/api'

export default function CalendarisedSalesTab({ isPlanner }) {
  const [selections, setSelections] = useState({})
  const [calendars, setCalendars] = useState([])
  const [source, setSource] = useState('dw')
  const [calendarId, setCalendarId] = useState(null)
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState(null)
  // null = idle; otherwise {pct, filesDone, filesTotal} while a background
  // reindex job is running (day-wise can read tens of millions of rows - the
  // old runReindex() call just blocked with no feedback for however long that took).
  const [progress, setProgress] = useState(null)
  const pollTimer = useRef(null)

  useEffect(() => { listCalendarLibrary().then(cs => setCalendars(cs.filter(c => c.mappingSummary?.length))) }, [])
  useEffect(() => () => clearTimeout(pollTimer.current), []) // stop polling if the tab unmounts mid-run

  function handleSelectionChange(sourceType, payload) {
    setSelections(prev => ({ ...prev, [sourceType]: payload }))
  }

  async function runRx() {
    if (!isPlanner || !calendarId || progress) return
    setStatus(null)
    setProgress({ pct: 0, filesDone: 0, filesTotal: 0 })
    try {
      const [detail, storeMap] = await Promise.all([getCalendar(calendarId), getStoreClusterMap()])
      const storeCluster = Object.fromEntries((storeMap.stores || []).map(s => [s.store, s.cluster]))
      const sel = selections[source]
      const { jobId } = await startReindex({
        source, months: sel?.months || [],
        storeCluster,
        dayMap: detail.dayMap, syncedAt: sel?.syncedAt,
      })

      // A single poll can transiently fail - the backend does its own CPU-bound
      // pandas/pyarrow work on a background thread, which can occasionally
      // starve the request briefly enough for the connection to reset even
      // though the job itself is still running fine. Retry through a handful
      // of those before actually giving up, rather than treating one dropped
      // poll as the whole reindex having failed.
      let misses = 0
      const MAX_MISSES = 5
      const poll = async () => {
        let p
        try {
          p = await pollReindex(jobId)
          misses = 0
        } catch (e) {
          misses += 1
          if (misses >= MAX_MISSES) { setProgress(null); setStatus({ ok: false, msg: `Lost contact with the reindex job: ${e.message}` }); return }
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        if (p.status === 'running') {
          setProgress({ pct: p.progressPct || 0, filesDone: p.filesDone || 0, filesTotal: p.filesTotal || 0 })
          pollTimer.current = setTimeout(poll, 1000)
          return
        }
        setProgress(null)
        if (p.status === 'error' || !p.ok) { setStatus({ ok: false, msg: p.error }); return }
        setResult(p)
      }
      await poll()
    } catch (e) {
      setProgress(null)
      setStatus({ ok: false, msg: e.message })
    }
  }

  return (
    <div className="module-panel">
      <LinkStatusPanel sourceType="mw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />
      <LinkStatusPanel sourceType="dw" isPlanner={isPlanner} onSelectionChange={handleSelectionChange} />

      <div className="card">
        <h4>Run Reindex</h4>
        <select value={source} onChange={e => setSource(e.target.value)}>
          <option value="dw">Day-wise NETAMT</option>
          <option value="mw">Month-wise Sales Value</option>
        </select>
        <select value={calendarId || ''} onChange={e => setCalendarId(e.target.value)}>
          <option value="">Select a locked calendar…</option>
          {calendars.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {isPlanner && <button className="btn" onClick={runRx} disabled={!!progress}>{progress ? 'Reindexing…' : 'Run Reindex'}</button>}
        {progress && (
          <div style={{ marginTop: '8px' }}>
            <div style={{ background: 'var(--border)', borderRadius: '4px', height: '8px', overflow: 'hidden' }}>
              <div style={{
                width: `${progress.pct}%`, height: '100%', background: 'var(--navy2)',
                transition: 'width 0.3s ease',
              }} />
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
              {progress.pct}%{progress.filesTotal > 0 && ` — ${progress.filesDone} of ${progress.filesTotal} files`}
            </div>
          </div>
        )}
        {status && <p style={{ color: 'var(--red)' }}>{status.msg}</p>}
      </div>

      <ReindexOutputPanel result={result} />
    </div>
  )
}
