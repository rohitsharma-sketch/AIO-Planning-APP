import { useState, useRef } from 'react'
import DbSyncPanel from './DbSyncPanel'
import './UploadStep.css'

export default function UploadStep({ onUpload, onUseDb, onEditInputs }) {
  const [dragging, setDragging]  = useState(false)
  const [file, setFile]          = useState(null)
  const [loading, setLoading]    = useState(false)
  const [err, setErr]            = useState(null)
  const [dbBusy, setDbBusy]      = useState(false)
  const inputRef                 = useRef()

  function handleFile(f) {
    if (!f) return
    if (!f.name.endsWith('.xlsx')) { setErr('Please select an .xlsx file'); return }
    setErr(null)
    setFile(f)
  }

  function onDrop(e) {
    e.preventDefault(); setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  // One-off run with this file — bypasses Postgres entirely, useful for
  // testing a hypothetical workbook without touching the database.
  async function submit() {
    if (!file) return
    setLoading(true); setErr(null)
    try { await onUpload(file) }
    catch (e) { setErr(e.message); setLoading(false) }
  }

  async function useDb() {
    setDbBusy(true); setErr(null)
    try { await onUseDb() } catch (e) { setErr(e.message) } finally { setDbBusy(false) }
  }

  return (
    <div className="upload-wrap">
      <div className="upload-hero">
        <h1 className="upload-title">Tentative AOP Forecaster</h1>
        <p className="upload-sub">Continue from the database below, or upload an <code>inputs.xlsx</code> for a one-off forecast.</p>
      </div>

      <div className="card upload-card">
        <div className="upload-actions" style={{ marginBottom: 16 }}>
          <button className="btn-primary" style={{ minWidth: 220 }} onClick={useDb} disabled={dbBusy}>
            {dbBusy ? 'Building from database…' : '🗄 Continue from database →'}
          </button>
          <button className="btn-outline" onClick={onEditInputs}>
            ✎ Edit Growth % / NSO / AOP overrides
          </button>
        </div>
        <DbSyncPanel />
      </div>

      <div className="card upload-card">
        <div
          className={`drop-zone ${dragging ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !file && inputRef.current.click()}
        >
          <input ref={inputRef} type="file" accept=".xlsx" style={{display:'none'}}
            onChange={e => handleFile(e.target.files[0])} />

          {file ? (
            <div className="file-info">
              <div className="file-icon">📊</div>
              <div>
                <div className="file-name">{file.name}</div>
                <div className="file-size">{(file.size / 1024).toFixed(0)} KB</div>
              </div>
              <button className="btn-outline" style={{marginLeft:'auto'}}
                onClick={e => { e.stopPropagation(); setFile(null) }}>
                Remove
              </button>
            </div>
          ) : (
            <div className="drop-prompt">
              <div className="drop-icon">⬆</div>
              <div className="drop-main">Drop <code>inputs.xlsx</code> here</div>
              <div className="drop-hint">or click to browse — one-off forecast, not saved to the database</div>
            </div>
          )}
        </div>

        {err && <p className="upload-err">{err}</p>}

        <div className="upload-actions">
          <button className="btn-primary" style={{minWidth:160}}
            disabled={!file || loading} onClick={submit}>
            {loading ? 'Reading file…' : 'Continue with this file →'}
          </button>
        </div>
      </div>

    </div>
  )
}
