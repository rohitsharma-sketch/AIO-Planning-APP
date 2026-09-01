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

  const load = () => fetchJson('/api/config/db-sync/status').then(d => setRuns(d.runs)).catch(e => setErr(e.message))
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

  const anyFailed = runs?.some(r => r.status === 'failed')
  const lastAt = runs?.length ? runs.map(r => r.completed_at || r.started_at).sort().at(-1) : null

  return (
    <div className={`cfg-sync${anyFailed ? ' off' : ''}`}>
      <div className="cfg-sync-main">
        <span className="cfg-sync-dot" />
        <div className="cfg-sync-text">
          <strong>Data lake &amp; Calendar Engine &lt;-&gt; Postgres</strong>
          <span className="cfg-sync-sub">
            {!runs ? 'Checking…'
              : !runs.length ? 'Never synced into Postgres yet.'
              : anyFailed ? 'Last sync had failures — see Details.'
              : <>All {runs.length} sources synced · last {fmtStamp(lastAt)}</>}
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
              <span>{r.status === 'success' ? 'OK' : r.status === 'failed' ? 'Failed' : '…'} {DB_SYNC_LABELS[r.source_key] || r.source_key}</span>
              <span className="cfg-sync-hint">
                {r.status === 'failed' ? r.error_message : `${r.rows_updated ?? r.rows_read ?? 0} rows · ${fmtStamp(r.completed_at || r.started_at)}`}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
