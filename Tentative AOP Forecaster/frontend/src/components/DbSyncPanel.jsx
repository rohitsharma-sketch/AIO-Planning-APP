import { useState, useEffect } from 'react'
import './DbSyncPanel.css'
import { apiUrl } from '../lib/apiBase'

export const fmtStamp = s => s ? new Date(s).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—'

export async function fetchJson(url, opts) {
  const res = await fetch(apiUrl(url), opts)
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const e = await res.json(); msg = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail ?? e) } catch {}
    throw new Error(msg)
  }
  return res.json()
}

// Data-lake / Calendar Engine -> Postgres sync. This is now the ONLY sync path
// (the older calendar_sync.py -> levers.json flow, and the config-editing UI
// that consumed it, were removed once this one was validated as a full
// replacement — see the RS Planning session history).
const DB_SYNC_LABELS = {
  data_lake_site_master:      'Site Master (data lake)',
  store_master_xlsx:          'Store Master.xlsx',
  data_lake_day_shift:        'Day-shift calendar (data lake)',
  data_lake_sales:            'Store Actuals (day-shifted sales)',
}

export default function DbSyncPanel({ onSynced }) {
  const [runs, setRuns]   = useState(null)
  const [busy, setBusy]   = useState(false)
  const [err, setErr]     = useState(null)
  const [open, setOpen]   = useState(false)
  const [closedThrough, setClosedThrough] = useState(null)   // 'YYYY-MM', persisted by store_actuals_sync

  const load = () => fetchJson('/api/config/db-sync/status').then(d => { setRuns(d.runs); setClosedThrough(d.closed_through) }).catch(e => setErr(e.message))
  const closedLabel = closedThrough
    ? new Date(`${closedThrough}-01T00:00:00`).toLocaleString('en-US', { month: 'short' }) + "'" + closedThrough.slice(2, 4)
    : null
  useEffect(() => { load() }, [])

  async function syncAll() {
    setBusy(true); setErr(null)
    try {
      const d = await fetchJson('/api/config/db-sync', { method: 'POST' })
      const failed = Object.entries(d.results).filter(([, r]) => !r.ok)
      if (failed.length) setErr(failed.map(([k, r]) => `${DB_SYNC_LABELS[k] || k}: ${r.error}`).join(' · '))
      await load()
      onSynced?.()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  const anyFailed  = runs?.some(r => r.status === 'failed')
  const anyOffline = runs?.some(r => r.status === 'offline')
  const lastAt = runs?.length ? runs.map(r => r.completed_at || r.started_at).sort().at(-1) : null

  const statusClass = anyFailed ? ' off' : anyOffline ? ' warn' : ''

  function rowLabel(r) {
    if (r.status === 'success')  return 'OK'
    if (r.status === 'failed')   return 'Failed'
    if (r.status === 'offline')  return 'Offline'
    return '…'
  }
  function rowHint(r) {
    if (r.status === 'failed')  return r.error_message
    if (r.status === 'offline') {
      const lastOk = r.last_success_at ? `Last synced ${fmtStamp(r.last_success_at)}` : 'Never successfully synced'
      return `Source machine offline — data still valid. ${lastOk}`
    }
    return `${r.rows_updated ?? r.rows_read ?? 0} rows · ${fmtStamp(r.completed_at || r.started_at)}`
  }

  return (
    <div className={`cfg-sync${statusClass}`}>
      <div className="cfg-sync-main">
        <span className="cfg-sync-dot" />
        <div className="cfg-sync-text">
          <strong>Data lake &amp; Calendar Engine &lt;-&gt; Postgres</strong>
          <span className="cfg-sync-sub">
            {!runs ? 'Checking…'
              : !runs.length ? 'Never synced into Postgres yet.'
              : anyFailed  ? 'Last sync had failures — see Details.'
              : anyOffline ? 'Some sources were offline — existing data still active.'
              : <>All {runs.length} sources synced · last {fmtStamp(lastAt)}</>}
            {closedLabel && <> · Actuals closed through {closedLabel}</>}
          </span>
        </div>
        <div className="cfg-sync-actions">
          <button className="btn-outline cfg-btn" onClick={() => setOpen(o => !o)}>{open ? 'Hide' : 'Details'}</button>
          <button className="btn-outline cfg-btn" onClick={syncAll} disabled={busy}>{busy ? 'Syncing…' : 'Sync into database'}</button>
        </div>
      </div>
      {err && <p className="upload-err">{err}</p>}
      {open && runs && (
        <div className="cfg-sync-details">
          {runs.map(r => (
            <div key={r.source_key} className="cfg-sync-row" style={{ justifyContent: 'space-between' }}>
              <span style={r.status === 'offline' ? { color: 'var(--amber, #d97706)' } : undefined}>
                {rowLabel(r)} {DB_SYNC_LABELS[r.source_key] || r.source_key}
              </span>
              <span className="cfg-sync-hint">{rowHint(r)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
