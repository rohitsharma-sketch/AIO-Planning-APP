import { useState, useEffect } from 'react'
import { theme, alpha } from '../theme'

const DIV_COLOR = {
  KIDS: '#C85A12', LADIES: '#7420B8', MENS: '#077A4A', GM: '#1E54C0', RETAIL: '#B22620',
}

const mono = { fontFamily: 'monospace', fontSize: 11 }

export default function MrpImport() {
  const [syncing, setSyncing]     = useState(false)
  const [result, setResult]       = useState(null)
  const [status, setStatus]       = useState(null)   // loaded mrp_plan.json summary
  const [fileInfo, setFileInfo]   = useState(null)   // source file on disk
  const [clearing, setClearing]   = useState(false)

  const reload = () => {
    fetch('/api/planning/mrp-plan/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStatus(d) })
    fetch('/api/planning/mrp-plan/sync-status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setFileInfo(d) })
  }

  useEffect(() => { reload() }, [])

  const handleSync = async () => {
    setSyncing(true); setResult(null)
    try {
      const r = await fetch('/api/planning/mrp-plan/sync', { method: 'POST' })
      const d = await r.json()
      if (!r.ok) { setResult({ ok: false, error: d.detail }); return }
      setResult(d)
      reload()
    } catch (e) {
      setResult({ ok: false, error: String(e) })
    } finally {
      setSyncing(false)
    }
  }

  const handleClear = async () => {
    setClearing(true)
    await fetch('/api/planning/mrp-plan/clear', { method: 'DELETE' })
    setStatus(null); setResult(null); setClearing(false)
  }

  return (
    <div style={{ padding: '28px 32px', minHeight: '100vh', background: theme.surfaceAlt }}>

      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <span style={{
            fontSize: 10, fontWeight: 700, padding: '3px 9px', borderRadius: 4, letterSpacing: 0.6,
            background: `${alpha('var(--st-btn,#A8CBB7)','18')}`, color: theme.primary, border: `1px solid ${alpha('var(--st-btn-hover,#95BFA7)','33')}`,
          }}>MRP PLAN SOURCE</span>
        </div>
        <p style={{ margin: '0 0 10px', fontSize: 13, color: theme.textMuted }}>
          The buyer's MRP contribution plan — always sync from this source. Month-wise growth % structure
          in Re-apportionment is always derived from this file.
        </p>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 7, padding: '6px 12px',
          borderRadius: 6, background: `${alpha(theme.accent,'12')}`, border: `1px solid ${alpha(theme.accent,'33')}`,
          fontSize: 11, color: theme.accent, fontWeight: 600,
        }}>
          ↺ Always re-sync when the buyer updates their plan
        </div>
      </div>

      {/* Loaded data banner */}
      {status?.imported && (
        <div style={{
          marginBottom: 20, padding: '14px 20px', borderRadius: 10,
          background: `${alpha(theme.success,'12')}`, border: `1px solid ${alpha(theme.success,'44')}`,
          display: 'flex', alignItems: 'center', gap: 14,
        }}>
          <span style={{ fontSize: 20 }}>✓</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: theme.success }}>MRP data loaded</div>
            <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 2 }}>
              {status.divisions?.join(', ')} · {status.dept_count} departments · {status.band_count} MRP bands
              {status.months?.length > 0 && ` · ${status.months.length} months (${status.months[0]} – ${status.months[status.months.length - 1]})`}
            </div>
          </div>
          <button onClick={handleClear} disabled={clearing}
            style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, cursor: 'pointer', background: 'transparent', border: `1px solid ${theme.danger}`, color: theme.danger }}>
            {clearing ? 'Clearing…' : 'Clear'}
          </button>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 20, alignItems: 'start' }}>

        {/* Sync card */}
        <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '28px 32px' }}>

          {/* Source file status */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 10 }}>SOURCE FILE</div>
            <div style={{
              padding: '14px 18px', borderRadius: 9,
              background: fileInfo?.file_found ? `${alpha(theme.success,'0e')}` : `${alpha(theme.danger,'0e')}`,
              border: `1px solid ${alpha(fileInfo?.file_found ? theme.success : theme.danger,'44')}`,
              display: 'flex', alignItems: 'center', gap: 14,
            }}>
              <span style={{ fontSize: 22 }}>{fileInfo?.file_found ? '📄' : '📭'}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: fileInfo?.file_found ? theme.success : theme.danger }}>
                  {fileInfo?.file_found ? fileInfo.source_name : 'File not found'}
                </div>
                <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 3, ...mono, wordBreak: 'break-all' }}>
                  {fileInfo?.source_path}
                </div>
                {fileInfo?.file_found && (
                  <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 4 }}>
                    Last modified: <strong style={{ color: theme.textPrimary }}>{fileInfo.file_date}</strong>
                    &ensp;·&ensp;{fileInfo.size_kb} KB
                  </div>
                )}
              </div>
              <button onClick={reload} style={{
                padding: '5px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
                background: 'transparent', border: `1px solid ${theme.border}`, color: theme.textMuted,
              }}>↺ Refresh</button>
            </div>
          </div>

          {/* Sync button */}
          <button
            onClick={handleSync}
            disabled={syncing || !fileInfo?.file_found}
            style={{
              width: '100%', padding: '13px 0', borderRadius: 9, fontSize: 14,
              fontWeight: 700, cursor: (syncing || !fileInfo?.file_found) ? 'not-allowed' : 'pointer',
              background: (syncing || !fileInfo?.file_found) ? theme.border : 'var(--st-btn,#A8CBB7)',
              color: 'var(--st-btn-text,#1F4D3A)', border: 'none', letterSpacing: 0.3,
            }}
          >
            {syncing ? '⟳  Syncing…' : '⟳  Sync from Folder'}
          </button>

          {!fileInfo?.file_found && (
            <div style={{ marginTop: 10, fontSize: 11, color: theme.textMuted, textAlign: 'center' }}>
              Drop <span style={{ ...mono, color: theme.accent }}>MRP Cont %.xlsx</span> into the source folder, then click Refresh.
            </div>
          )}

          {/* Result feedback */}
          {result && (
            <div style={{
              marginTop: 18, padding: '14px 18px', borderRadius: 8, fontSize: 12,
              background: result.ok ? `${alpha(theme.success,'12')}` : `${alpha(theme.danger,'12')}`,
              border: `1px solid ${alpha(result.ok ? theme.success : theme.danger,'44')}`,
              color: result.ok ? theme.success : theme.danger,
            }}>
              {result.ok ? (
                <>
                  <div style={{ fontWeight: 700, marginBottom: 6, fontSize: 13 }}>✓ Synced successfully</div>
                  <div style={{ color: theme.textMuted, fontSize: 11, lineHeight: 1.8 }}>
                    <span style={{ color: theme.textPrimary, fontWeight: 600 }}>{result.divisions?.join(', ')}</span>
                    &ensp;·&ensp;{result.dept_count} departments
                    &ensp;·&ensp;{result.mrp_count} MRP bands
                    &ensp;·&ensp;{result.periods?.length} periods
                  </div>
                  {result.periods?.length > 0 && (
                    <div style={{ marginTop: 6, fontSize: 11, color: theme.textMuted }}>
                      Periods: {result.periods.join(' · ')}
                    </div>
                  )}
                  {result.contrib_warnings?.length > 0 && (
                    <div style={{ marginTop: 10, color: '#B45309', fontSize: 11 }}>
                      <div style={{ fontWeight: 700, marginBottom: 3 }}>⚠ Contribution warnings ({result.contrib_warnings.length}):</div>
                      {result.contrib_warnings.slice(0, 6).map((w, i) => <div key={i}>• {w}</div>)}
                      {result.contrib_warnings.length > 6 && <div>…and {result.contrib_warnings.length - 6} more</div>}
                    </div>
                  )}
                  {result.parse_errors?.length > 0 && (
                    <div style={{ marginTop: 10, color: theme.danger, fontSize: 11 }}>
                      <div style={{ fontWeight: 700, marginBottom: 3 }}>Parse errors ({result.parse_errors.length}):</div>
                      {result.parse_errors.slice(0, 3).map((e, i) => <div key={i}>• {e}</div>)}
                    </div>
                  )}
                </>
              ) : (
                <div>✗ {result.error}</div>
              )}
            </div>
          )}
        </div>

        {/* Info card */}
        <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '20px 22px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 14 }}>HOW IT WORKS</div>

          {[
            { icon: '📂', title: 'Drop the file', body: `Place the updated buyer MRP file as "MRP Cont %.xlsx" in the source folder.` },
            { icon: '↺',  title: 'Refresh & Sync', body: 'Click Refresh to detect the file, then Sync to import it — no browser upload needed.' },
            { icon: '📊', title: 'View output', body: 'Go to Plan Output to see the P1/P2 contribution matrix across all divisions.' },
          ].map(({ icon, title, body }) => (
            <div key={title} style={{ display: 'flex', gap: 12, marginBottom: 18, alignItems: 'flex-start' }}>
              <span style={{ fontSize: 18, lineHeight: 1, marginTop: 1 }}>{icon}</span>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: theme.textPrimary, marginBottom: 3 }}>{title}</div>
                <div style={{ fontSize: 11, color: theme.textMuted, lineHeight: 1.6 }}>{body}</div>
              </div>
            </div>
          ))}

          <div style={{ borderTop: `1px solid ${theme.border}`, paddingTop: 14, marginTop: 4 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, marginBottom: 8 }}>EXPECTED FILE FORMAT</div>
            <div style={{ fontSize: 11, color: theme.textMuted, lineHeight: 1.8 }}>
              <span style={{ ...mono, color: theme.primary }}>Division</span> · <span style={{ ...mono, color: theme.primary }}>Department</span> · <span style={{ ...mono, color: theme.primary }}>MRP</span><br />
              Then period columns: <span style={{ ...mono, color: theme.accent }}>Mar'27 P1</span>, <span style={{ ...mono, color: theme.accent }}>Mar'27 P2</span>, …<br />
              Each cell = contribution % — must sum to <strong>100%</strong> per dept per period.
            </div>
          </div>

          <div style={{ marginTop: 14, borderTop: `1px solid ${theme.border}`, paddingTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, marginBottom: 8 }}>DIVISIONS EXPECTED</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {['KIDS', 'LADIES', 'MENS'].map(d => (
                <span key={d} style={{
                  fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 6,
                  background: `${alpha(DIV_COLOR[d],'18')}`, border: `1px solid ${alpha(DIV_COLOR[d],'44')}`,
                  color: DIV_COLOR[d],
                }}>{d}</span>
              ))}
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
