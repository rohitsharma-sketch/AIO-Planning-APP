import { useState, useEffect } from 'react'
import { getStoreClusterMap, putStoreClusterMap, getStoreClusterLog, importStoreCluster } from '../../lib/api'

// Ported from the old app's Store/Cluster Mapping panel (calendar_engine.html lines ~915-954).
// The old app also had inline per-store add/remove controls (scmAddStore/scmRemoveStore)
// alongside this bulk-import flow. This version supports only the bulk-import-and-replace
// path — the primary, backend-supported flow (PUT /store-cluster-map is a full replace,
// matching the API's own semantics) — and deliberately drops the individual add/remove-one-store
// UI since it duplicates what re-importing an edited CSV/xlsx already accomplishes.
export default function StoreMappingPanel({ isPlanner }) {
  const [mapping, setMapping] = useState(null)
  const [log, setLog] = useState([])
  const [showLog, setShowLog] = useState(false)
  const [search, setSearch] = useState('')
  const [importPreview, setImportPreview] = useState(null)
  const [status, setStatus] = useState(null)

  function refresh() {
    getStoreClusterMap().then(setMapping).catch(e => setStatus({ ok: false, msg: e.message }))
  }
  useEffect(refresh, [])

  async function handleFile(file) {
    if (!isPlanner || !file) return
    try {
      const result = await importStoreCluster(file)
      setImportPreview({ filename: file.name, rows: result.rows })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function confirmImport() {
    if (!isPlanner || !importPreview) return
    try {
      await putStoreClusterMap({ stores: importPreview.rows, source: importPreview.filename })
      setImportPreview(null)
      setStatus({ ok: true, msg: 'Store-cluster map replaced' })
      refresh()
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  function downloadTemplate() {
    if (!mapping) return
    const csv = ['Store Name,Calendar Cluster', ...mapping.stores.map(s => `${s.store},${s.cluster}`)].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'store_cluster_map.csv'
    a.click()
  }

  async function showChangeLog() {
    setLog(await getStoreClusterLog())
    setShowLog(true)
  }

  if (!mapping) return <p>Loading…</p>

  const clusters = [...new Set(mapping.stores.map(s => s.cluster))].sort()
  const filtered = mapping.stores.filter(s =>
    !search || s.store.toLowerCase().includes(search.toLowerCase()) || s.cluster.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <div className="card">
        <p>{mapping.stores.length} stores mapped. Locked: {mapping.locked ? 'Yes' : 'No'}.
           Source: {mapping.source || '—'}. Last edited: {mapping.editedAt || '—'}.</p>
        {isPlanner && (
          <>
            <input type="file" accept=".xlsx,.xlsm,.csv,.txt,.tsv" onChange={e => handleFile(e.target.files[0])} />
            <button onClick={downloadTemplate}>Download Current Template (CSV)</button>
            <button onClick={showChangeLog}>Change Log</button>
          </>
        )}
        <p style={{ color: 'var(--muted)', fontSize: '12px' }}>Expected columns: "Store Name", "CALENDAR CLUSTER"</p>
      </div>

      {importPreview && (
        <div className="card">
          <h4>Confirm import: {importPreview.filename} ({importPreview.rows.length} stores)</h4>
          <button onClick={confirmImport}>Confirm & Replace Mapping</button>
          <button onClick={() => setImportPreview(null)}>Cancel</button>
        </div>
      )}

      <div className="card">
        <h4>Stores per calendar cluster</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '8px' }}>
          {clusters.map(c => (
            <div key={c}>{c}: {mapping.stores.filter(s => s.cluster === c).length}</div>
          ))}
        </div>
      </div>

      <div className="card">
        <input placeholder="Search stores…" value={search} onChange={e => setSearch(e.target.value)} />
        <span>{filtered.length} of {mapping.stores.length}</span>
        <table>
          <thead><tr><th>#</th><th>Store Name</th><th>Calendar Cluster</th></tr></thead>
          <tbody>
            {filtered.map((s, i) => (
              <tr key={s.store}><td>{i + 1}</td><td>{s.store}</td><td>{s.cluster}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {showLog && (
        <div className="card">
          <h4>Change Log</h4>
          <ul>
            {log.map((entry, i) => (
              <li key={i}>{entry.at} — {entry.summary} (added {entry.added}, removed {entry.removed}, reassigned {entry.reassigned})</li>
            ))}
          </ul>
          <button onClick={() => setShowLog(false)}>Close</button>
        </div>
      )}
      {status && <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)' }}>{status.msg}</p>}
    </div>
  )
}
