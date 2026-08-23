import { useState, useEffect } from 'react'
import LinkStatusPanel from './LinkStatusPanel'
import ReindexOutputPanel from './ReindexOutputPanel'
import { runReindex, listCalendarLibrary, getCalendar, getStoreClusterMap } from '../../lib/api'

export default function CalendarisedSalesTab({ isPlanner }) {
  const [selections, setSelections] = useState({})
  const [calendars, setCalendars] = useState([])
  const [source, setSource] = useState('dw')
  const [calendarId, setCalendarId] = useState(null)
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState(null)

  useEffect(() => { listCalendarLibrary().then(cs => setCalendars(cs.filter(c => c.mappingSummary?.length))) }, [])

  function handleSelectionChange(sourceType, payload) {
    setSelections(prev => ({ ...prev, [sourceType]: payload }))
  }

  async function runRx() {
    if (!isPlanner || !calendarId) return
    try {
      const [detail, storeMap] = await Promise.all([getCalendar(calendarId), getStoreClusterMap()])
      const storeCluster = Object.fromEntries((storeMap.stores || []).map(s => [s.store, s.cluster]))
      const sel = selections[source]
      const r = await runReindex({
        source, months: sel?.months || [],
        storeCluster,
        dayMap: detail.dayMap, syncedAt: sel?.syncedAt,
      })
      setResult(r)
      if (!r.ok) setStatus({ ok: false, msg: r.error })
      else setStatus(null)
    } catch (e) {
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
        {isPlanner && <button className="btn" onClick={runRx}>Run Reindex</button>}
        {status && <p style={{ color: 'var(--red)' }}>{status.msg}</p>}
      </div>

      <ReindexOutputPanel result={result} />
    </div>
  )
}
