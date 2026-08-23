import { useState, useEffect, useMemo } from 'react'
import { listCalendarLibrary, getCalendar, getStoreClusterMap } from '../../lib/api'

// NOTE: the "Cluster × Day" level toggle below is intentionally not wired up yet.
// The table always shows store-level rows regardless of which radio is selected.
// Aggregating to one row per cluster (and CSV download) is a deliberate follow-up,
// out of scope for this task.
export default function DateShiftPreviewPanel() {
  const [calendars, setCalendars] = useState([])
  const [calendarId, setCalendarId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [storeMap, setStoreMap] = useState(null)
  const [level, setLevel] = useState('store')
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('storeDate')

  useEffect(() => {
    listCalendarLibrary().then(setCalendars)
    getStoreClusterMap().then(setStoreMap)
  }, [])

  useEffect(() => {
    if (calendarId) getCalendar(calendarId).then(setDetail)
  }, [calendarId])

  const rows = useMemo(() => {
    if (!detail || !storeMap) return []
    const out = []
    for (const store of storeMap.stores) {
      const pairs = detail.dayMap[store.cluster] || []
      for (const [refDate, futDate] of pairs) {
        out.push({ store: store.store, cluster: store.cluster, refDate, futDate })
      }
    }
    return out.filter(r => !search || r.store.toLowerCase().includes(search.toLowerCase()) || r.cluster.toLowerCase().includes(search.toLowerCase()))
  }, [detail, storeMap, search])

  return (
    <div className="card">
      <select value={calendarId || ''} onChange={e => setCalendarId(e.target.value)}>
        <option value="">Select a calendar…</option>
        {calendars.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <label><input type="radio" checked={level === 'store'} onChange={() => setLevel('store')} /> Store × Day</label>
      <label><input type="radio" checked={level === 'cluster'} onChange={() => setLevel('cluster')} /> Cluster × Day</label>
      <input placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} />
      <table>
        <thead><tr><th>Store</th><th>Cluster</th><th>Ref Date</th><th>Future Date</th></tr></thead>
        <tbody>
          {rows.map((r, i) => <tr key={i}><td>{r.store}</td><td>{r.cluster}</td><td>{r.refDate}</td><td>{r.futDate}</td></tr>)}
        </tbody>
      </table>
    </div>
  )
}
