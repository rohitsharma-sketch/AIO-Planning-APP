import { useState } from 'react'
import DbSyncPanel from './DbSyncPanel'
import './UploadStep.css'

export default function UploadStep({ onUseDb, onEditInputs }) {
  const [err, setErr]       = useState(null)
  const [dbBusy, setDbBusy] = useState(false)

  async function useDb() {
    setDbBusy(true); setErr(null)
    try { await onUseDb() } catch (e) { setErr(e.message) } finally { setDbBusy(false) }
  }

  return (
    <div className="us-wrap">

      {/* ── Heading + actions (UI declutter 2026-10-07: the stepper shows the step; one primary
          button + a link replace the two large cards - same handlers) ── */}
      <div className="us-head">
        <h1 className="us-title">Configure the plan</h1>
        <p className="us-sub">Build the store-level forecast from the synced database, or adjust growth, NSO ramp and AOP overrides first.</p>
      </div>

      <div className="us-actions">
        <button className="btn-primary" onClick={useDb} disabled={dbBusy}
                title="Load store counts, actuals, and growth rates from the synced data lake">
          {dbBusy ? 'Building forecast…' : 'Continue from database'}
        </button>
        <button className="us-link" onClick={onEditInputs}
                title="Adjust growth rates, ramp schedules, and AOP overrides before generating the plan">
          Edit Growth % / NSO / AOP
        </button>
      </div>

      {err && <p className="us-err">{err}</p>}

      {/* ── Sync status ───────────────────────────────── */}
      <div className="us-sync-section">
        <div className="us-sync-label">Data Sources</div>
        <DbSyncPanel onSynced={useDb} />
      </div>

    </div>
  )
}
