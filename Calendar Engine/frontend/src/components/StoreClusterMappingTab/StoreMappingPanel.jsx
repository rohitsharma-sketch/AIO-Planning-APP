import { useState, useEffect } from 'react'
import {
  getStoreClusterMap, putStoreClusterMap, getStoreClusterLog,
  importStoreCluster, getClusterProfiles,
} from '../../lib/api'

// Ported from the old app's Store/Cluster Mapping panel (calendar_engine.html
// lines ~915-954 markup, ~3081-3245 behaviour): per-cluster count cards, a real
// per-row cluster <select> that persists on change, add/remove one store, and an
// import flow that shows the added/removed/reassigned diff BEFORE it replaces
// anything. PUT /store-cluster-map is a full replace, so every single-row edit
// sends the whole `stores` array back - always carrying the stored `aliases` and
// `source` through, since the endpoint overwrites both unconditionally.

// Quote every CSV field the way the old app's _scmCsv() did, so a store or
// cluster name containing a comma or a quote cannot corrupt the file.
const csvField = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`

function downloadCsv(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function fmtDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return isNaN(d) ? iso : d.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// Compare the current (already-resolved) mapping against an uploaded template.
// The import endpoint hands back `resolvedCluster` alongside the raw file value,
// so "NE" vs "N. EAST" resolving to the same cluster is not reported as a change.
function computeDiff(oldRows, newRows) {
  const oldEff = (s) => s.cluster || ''
  const newEff = (s) => s.resolvedCluster || s.cluster || ''
  const o = new Map(oldRows.map((s) => [s.store.toUpperCase(), s]))
  const n = new Map(newRows.map((s) => [s.store.toUpperCase(), s]))
  const added = [], removed = [], reassigned = []
  n.forEach((s, k) => {
    if (!o.has(k)) added.push({ store: s.store, to: newEff(s) })
    else if (oldEff(o.get(k)) !== newEff(s)) reassigned.push({ store: s.store, from: oldEff(o.get(k)), to: newEff(s) })
  })
  o.forEach((s, k) => { if (!n.has(k)) removed.push({ store: s.store, from: oldEff(s) }) })
  return { added, removed, reassigned }
}

export default function StoreMappingPanel({ isPlanner }) {
  const [mapping, setMapping] = useState(null)
  const [clusterNames, setClusterNames] = useState([])
  const [clustersLoaded, setClustersLoaded] = useState(false)
  const [log, setLog] = useState([])
  const [showLog, setShowLog] = useState(false)
  const [openEntries, setOpenEntries] = useState({})
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [importPreview, setImportPreview] = useState(null)
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [newStore, setNewStore] = useState('')
  const [newCluster, setNewCluster] = useState('')

  function refresh() {
    return getStoreClusterMap().then(setMapping).catch((e) => setStatus({ ok: false, msg: e.message }))
  }

  useEffect(() => {
    refresh()
    getClusterProfiles()
      .then((r) => { setClusterNames((r.profiles || []).map((p) => p.name)); setClustersLoaded(true) })
      .catch((e) => { setStatus({ ok: false, msg: e.message }); setClustersLoaded(true) })
  }, [])

  // Full-replace PUT, preserving source + aliases. `overrides` lets the import
  // path swap in the uploaded filename as the new source.
  async function persist(stores, msg, overrides = {}) {
    if (!isPlanner || !mapping) return false
    setBusy(true)
    try {
      await putStoreClusterMap({
        stores,
        source: mapping.source,
        aliases: mapping.aliases || {},
        ...overrides,
      })
      await refresh()
      if (showLog) await loadLog()
      setStatus({ ok: true, msg })
      return true
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
      return false
    } finally {
      setBusy(false)
    }
  }

  async function loadLog() {
    try {
      setLog(await getStoreClusterLog())
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  function handleRowCluster(store, cluster) {
    if (!isPlanner || !cluster) return
    const row = mapping.stores.find((s) => s.store === store)
    if (!row || row.cluster === cluster) return
    persist(
      mapping.stores.map((s) => (s.store === store ? { ...s, cluster } : s)),
      `${store}: ${row.cluster || 'unassigned'} -> ${cluster}`,
    )
  }

  async function handleAddStore() {
    if (!isPlanner) return
    const name = newStore.trim()
    if (!name) { setStatus({ ok: false, msg: 'Enter a store name.' }); return }
    if (!newCluster) { setStatus({ ok: false, msg: 'Select a cluster for the new store.' }); return }
    if (mapping.stores.some((s) => s.store.toUpperCase() === name.toUpperCase())) {
      setStatus({ ok: false, msg: `Store "${name}" already exists in the mapping.` })
      return
    }
    const ok = await persist([...mapping.stores, { store: name, cluster: newCluster }], `Store ${name} added to ${newCluster}`)
    if (ok) { setNewStore(''); setNewCluster('') }
  }

  function handleRemoveStore(store) {
    if (!isPlanner) return
    if (!window.confirm(`Remove store "${store}" from the mapping?`)) return
    persist(mapping.stores.filter((s) => s.store !== store), `Store ${store} removed`)
  }

  async function handleFile(file) {
    if (!isPlanner || !file) return
    try {
      const result = await importStoreCluster(file)
      const diff = computeDiff(mapping.stores, result.rows)
      if (!diff.added.length && !diff.removed.length && !diff.reassigned.length) {
        setImportPreview(null)
        setStatus({ ok: false, msg: `This template is identical to the current mapping (${mapping.stores.length} stores) - nothing to import.` })
        return
      }
      setStatus(null)
      setImportPreview({ filename: result.filename || file.name, rows: result.rows, diff })
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    }
  }

  async function confirmImport() {
    if (!isPlanner || !importPreview) return
    // Send the RAW uploaded cluster values: the backend re-resolves them itself,
    // so there is no chance of drift between this preview and what actually lands.
    const stores = importPreview.rows.map((r) => ({ store: r.store, cluster: r.cluster }))
    const ok = await persist(stores, `Store-cluster map replaced from ${importPreview.filename}`, { source: importPreview.filename })
    if (ok) setImportPreview(null)
  }

  function downloadTemplate() {
    if (!mapping) return
    const rows = ['Store Name,CALENDAR CLUSTER',
      ...mapping.stores.map((s) => [s.store, s.cluster].map(csvField).join(','))]
    downloadCsv(rows.join('\n'), 'store_cluster_template.csv')
  }

  async function downloadLog() {
    let entries = log
    if (!entries.length) {
      try { entries = await getStoreClusterLog(); setLog(entries) } catch (e) { setStatus({ ok: false, msg: e.message }); return }
    }
    const rows = ['Date,Source,Change,Store,From,To']
    entries.forEach((e) => (e.details || []).forEach((x) => {
      rows.push([e.at, e.source, x.type, x.store, x.from || '', x.to || ''].map(csvField).join(','))
    }))
    downloadCsv(rows.join('\n'), 'store_cluster_change_log.csv')
  }

  async function toggleLog() {
    if (!showLog) await loadLog()
    setShowLog(!showLog)
  }

  if (!mapping || !clustersLoaded) return <p>Loading...</p>

  const known = new Set(clusterNames)
  const counts = {}
  let unassigned = 0
  mapping.stores.forEach((s) => {
    if (known.has(s.cluster)) counts[s.cluster] = (counts[s.cluster] || 0) + 1
    else unassigned++
  })

  const q = search.trim().toLowerCase()
  const filtered = mapping.stores.filter((s) => {
    if (q && !(s.store.toLowerCase().includes(q) || (s.cluster || '').toLowerCase().includes(q))) return false
    if (filter === '__none__') return !known.has(s.cluster)
    if (filter && s.cluster !== filter) return false
    return true
  })

  const d = importPreview?.diff

  return (
    <div>
      <div className="card">
        <div className="scm-toolbar">
          <span className={`scm-pill ${mapping.locked ? 'scm-pill-ok' : 'scm-pill-warn'}`}>
            {mapping.locked ? 'Locked' : 'Not locked'}
          </span>
          <span style={{ fontSize: '12px' }}>
            {mapping.stores.length} stores · imported {fmtDate(mapping.lockedAt)} from <strong>{mapping.source || '-'}</strong>
            {mapping.editedAt ? ` · last edited ${fmtDate(mapping.editedAt)}` : ''}
          </span>
          {unassigned > 0 && (
            <span className="scm-pill scm-pill-warn">{unassigned} store{unassigned > 1 ? 's' : ''} unassigned</span>
          )}
          <span className="scm-toolbar-right">
            {isPlanner && (
              <label className="btn" style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
                Import New Template
                <input type="file" accept=".xlsx,.xlsm,.csv,.txt,.tsv" style={{ display: 'none' }}
                  onChange={(e) => { const f = e.target.files[0]; e.target.value = ''; handleFile(f) }} />
              </label>
            )}
            <button onClick={downloadTemplate}>Download Current Template (CSV)</button>
            <button onClick={toggleLog}>{showLog ? 'Hide Change Log' : 'Change Log'}</button>
            <button onClick={downloadLog}>Download Change Log (CSV)</button>
          </span>
        </div>
        <p style={{ color: 'var(--muted)', fontSize: '12px', margin: 0 }}>
          Edit a single store with the Calendar Cluster dropdown in the table below - it saves immediately and is
          recorded in the change log. For a bulk change, import a template (columns: <strong>Store Name</strong>,{' '}
          <strong>CALENDAR CLUSTER</strong>) and review the differences before it replaces the mapping.
        </p>
        {status && (
          <p style={{ color: status.ok ? 'var(--green)' : 'var(--red)', fontSize: '12px', margin: '8px 0 0' }}>
            {status.msg}
          </p>
        )}
      </div>

      {importPreview && (
        <div className="card">
          <h4 style={{ marginTop: 0 }}>Review changes from {importPreview.filename}</h4>
          <div className="scm-toolbar">
            <span className="scm-pill scm-pill-ok">+{d.added.length} added</span>
            <span className="scm-pill scm-pill-warn">{d.reassigned.length} reassigned</span>
            <span className="scm-pill scm-pill-bad">-{d.removed.length} removed</span>
            <span style={{ color: 'var(--muted)', fontSize: '12px' }}>
              · {importPreview.rows.length} stores after import (currently {mapping.stores.length})
            </span>
          </div>
          <div className="scm-mini-wrap">
            <table className="scm-mini">
              <thead><tr><th>Change</th><th>Store</th><th>From</th><th>To</th></tr></thead>
              <tbody>
                {d.added.map((x) => <tr key={`a-${x.store}`}><td>Added</td><td style={{ fontWeight: 600 }}>{x.store}</td><td>-</td><td>{x.to}</td></tr>)}
                {d.reassigned.map((x) => <tr key={`r-${x.store}`}><td>Reassigned</td><td style={{ fontWeight: 600 }}>{x.store}</td><td>{x.from}</td><td>{x.to}</td></tr>)}
                {d.removed.map((x) => <tr key={`d-${x.store}`}><td>Removed</td><td style={{ fontWeight: 600 }}>{x.store}</td><td>{x.from}</td><td>-</td></tr>)}
              </tbody>
            </table>
          </div>
          <div className="scm-toolbar" style={{ marginTop: '10px', marginBottom: 0 }}>
            <button className="btn" disabled={busy} onClick={confirmImport}>Confirm &amp; Replace Mapping</button>
            <button disabled={busy} onClick={() => setImportPreview(null)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="card">
        <h4 style={{ marginTop: 0 }}>Stores per calendar cluster</h4>
        <div className="scm-cluster-grid">
          {clusterNames.map((c) => (
            <div className="scm-cl" key={c}>
              <div className="scm-cl-name" title={c}>{c}</div>
              <div className="scm-cl-count">{counts[c] || 0}</div>
            </div>
          ))}
          {unassigned > 0 && (
            <div className="scm-cl scm-cl-miss">
              <div className="scm-cl-name" title="Stores whose cluster does not match any calendar cluster">Unassigned</div>
              <div className="scm-cl-count">{unassigned}</div>
            </div>
          )}
          {!clusterNames.length && (
            <div style={{ color: 'var(--muted)', fontSize: '12px' }}>No clusters defined in the calendar engine.</div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="scm-toolbar">
          <input placeholder="Search store or cluster..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ width: '200px' }} />
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All clusters</option>
            {clusterNames.map((n) => <option key={n} value={n}>{n}</option>)}
            <option value="__none__">Unassigned</option>
          </select>
          <span style={{ fontSize: '11px', color: 'var(--muted)' }}>{filtered.length} of {mapping.stores.length} stores</span>
          {isPlanner && (
            <span className="scm-toolbar-right">
              <input placeholder="New store name" value={newStore} style={{ width: '150px' }}
                onChange={(e) => setNewStore(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleAddStore() }} />
              <select value={newCluster} onChange={(e) => setNewCluster(e.target.value)}>
                <option value="">- cluster -</option>
                {clusterNames.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <button className="btn" disabled={busy} onClick={handleAddStore}>+ Add Store</button>
            </span>
          )}
        </div>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th><th>Store Name</th><th>Stored Cluster</th><th>Calendar Cluster</th>
                {isPlanner && <th aria-label="Remove" />}
              </tr>
            </thead>
            <tbody>
              {filtered.map((s, i) => {
                const missing = !known.has(s.cluster)
                return (
                  <tr key={s.store}>
                    <td style={{ color: 'var(--muted)' }}>{i + 1}</td>
                    <td style={{ fontWeight: 600 }}>{s.store}</td>
                    <td>{s.cluster || '-'}</td>
                    <td>
                      <select
                        className={`scm-sel${missing ? ' scm-sel-miss' : ''}`}
                        value={missing ? '' : s.cluster}
                        disabled={!isPlanner || busy}
                        onChange={(e) => handleRowCluster(s.store, e.target.value)}
                      >
                        <option value="" disabled>- select cluster -</option>
                        {clusterNames.map((n) => <option key={n} value={n}>{n}</option>)}
                      </select>
                    </td>
                    {isPlanner && (
                      <td>
                        <button className="scm-remove-btn" title="Remove store" disabled={busy}
                          onClick={() => handleRemoveStore(s.store)}>x</button>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {showLog && (
        <div className="card">
          <h4 style={{ marginTop: 0 }}>Change Log</h4>
          {!log.length && <div style={{ color: 'var(--muted)', fontSize: '12px', marginBottom: '8px' }}>No changes logged yet.</div>}
          {log.map((entry, i) => {
            const details = entry.details || []
            const open = !!openEntries[i]
            return (
              <div className="scm-log-entry" key={`${entry.at}-${i}`}>
                <div className="scm-log-head" onClick={() => setOpenEntries((o) => ({ ...o, [i]: !o[i] }))}>
                  <strong>{fmtDate(entry.at)}</strong>
                  <span>· {entry.source || '-'}</span>
                  <span>· {entry.summary}</span>
                  <span className="scm-log-toggle">{open ? 'hide' : 'details'} ({details.length})</span>
                </div>
                {open && (
                  <div className="scm-log-details">
                    <div className="scm-mini-wrap">
                      <table className="scm-mini">
                        <thead><tr><th>Change</th><th>Store</th><th>From</th><th>To</th></tr></thead>
                        <tbody>
                          {details.map((x, j) => (
                            <tr key={j}>
                              <td>{x.type}</td>
                              <td style={{ fontWeight: 600 }}>{x.store}</td>
                              <td>{x.from || '-'}</td>
                              <td>{x.to || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
          <button onClick={() => setShowLog(false)}>Close</button>
        </div>
      )}
    </div>
  )
}
