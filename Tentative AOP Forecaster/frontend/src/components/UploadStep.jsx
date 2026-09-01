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
    <div className="upload-wrap">
      <div className="upload-hero">
        <h1 className="upload-title">Tentative AOP Forecaster</h1>
        <p className="upload-sub">Continue from the database below, or edit the Growth %/NSO/AOP overrides that feed it.</p>
      </div>

      <div className="card upload-card">
        <div className="upload-actions" style={{ marginBottom: 16 }}>
          <button className="btn-primary" style={{ minWidth: 220 }} onClick={useDb} disabled={dbBusy}>
            {dbBusy ? 'Building from database…' : 'Continue from database'}
          </button>
          <button className="btn-outline" onClick={onEditInputs}>
            Edit Growth % / NSO / AOP overrides
          </button>
        </div>
        {err && <p className="upload-err">{err}</p>}
        <DbSyncPanel />
      </div>
    </div>
  )
}
