import { useState, useEffect } from 'react'
import { theme, alpha } from '../theme'

// Where the MRP Cont % comes from (user, 2026-10-14: "either drop a file for cont % or by default the cont % for the
// re-apportioned sales will be taken, this is an optional scenario now" and "how can i point to the latest version of
// the re-apportionment run in the engine"): the latest passed re-apportionment run's shares (default) or the buyers' file
function SourcePick({ onSynced }) {
  const [s, setS] = useState(null)
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const load = () => fetch('/api/planning/mrp-plan/source').then(r => (r.ok ? r.json() : null)).then(setS).catch(() => setS(null))
  useEffect(() => { load() }, [])
  const pick = async source => {
    setBusy('pick'); setErr('')
    const r = await fetch('/api/planning/mrp-plan/source', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source }) }).catch(() => null)
    if (r && r.ok) setS(await r.json()); else setErr('Could not change the source')
    setBusy('')
  }
  const rebuild = async () => {
    setBusy('build'); setErr('')
    try {
      const r = await fetch('/api/planning/mrp-reapportionment/shares/rebuild', { method: 'POST' })
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.detail || `HTTP ${r.status}`) }
      if (s?.source !== 'reapp') await pick('reapp'); else load()
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }
  const sync = async () => {
    setBusy('sync'); setErr('')
    try {
      const r = await fetch('/api/planning/mrp-plan/sync', { method: 'POST' })
      const j = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`)
      onSynced?.(); load()
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }
  if (!s) return null
  const R = s.reapp || {}
  const opt = (k, title, body) => (
    <label style={{ flex: '1 1 320px', display: 'flex', gap: 10, alignItems: 'flex-start', padding: '12px 14px', borderRadius: 10, cursor: 'pointer',
      border: `1.5px solid ${s.source === k ? theme.primary : theme.border}`, background: s.source === k ? alpha(theme.primary, '0d') : theme.surface }}>
      <input type="radio" name="mrp-src" checked={s.source === k} disabled={!!busy} onChange={() => pick(k)} style={{ marginTop: 3 }} />
      <div><div style={{ fontSize: 13, fontWeight: 700 }}>{title}</div><div style={{ fontSize: 12, color: theme.textMuted, marginTop: 3 }}>{body}</div></div>
    </label>)
  return (
    <div style={{ background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, padding: '16px 20px', marginBottom: 20 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: theme.textMuted, letterSpacing: 0.5, marginBottom: 10 }}>MRP CONT % - WHERE IT COMES FROM</div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {opt('reapp', 'Re-apportioned LY sales (default)', R.built
          ? <>The latest re-apportionment: <b>{R.source}</b> · {String(R.built_at).replace('T', ' ').slice(0, 16)} · master {R.master} · {R.basis} sales {R.months?.[0]}–{R.months?.[R.months.length - 1]} · {R.departments} departments. Each department's mix over its new MRPs, month by month; a department the run doesn't cover keeps the buyers' file share, if synced. Every passed run updates it by itself.</>
          : <>No run has saved its shares yet - run MRP Re-apportionment, or build them from the master in use now.</>)}
        {opt('file', "Buyer's MRP Cont % file", <>The buyers' own contribution % per MRP and period - put "MRP Cont %.xlsx" in the SalesPlan\MRP Cont % folder, then Sync. {s.file?.imported ? 'A file is synced.' : 'No file synced yet.'}</>)}
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 10, flexWrap: 'wrap' }}>
        <button type="button" disabled={!!busy} onClick={rebuild} style={{ padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer',
          background: 'var(--st-btn,#A8CBB7)', border: 'none', color: 'var(--st-btn-text,#1F4D3A)' }}>
          {busy === 'build' ? 'Building… (about a minute)' : R.built ? '↻ Rebuild from the master in use' : '↻ Build from the master in use now'}
        </button>
        <button type="button" disabled={!!busy} onClick={sync} style={{ padding: '6px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: 'pointer',
          background: 'transparent', border: `1px solid ${theme.border}`, color: theme.textPrimary }}>
          {busy === 'sync' ? 'Syncing…' : "⟳ Sync the buyers' file"}
        </button>
        <span style={{ fontSize: 12, color: s.in_use ? theme.success : theme.danger, fontWeight: 600 }}>
          {s.in_use === 'reapp' ? 'In use: the re-apportioned LY sales' : s.in_use === 'file' ? "In use: the buyers' file" : 'Nothing to split by yet'}
          {s.source === 'reapp' && s.in_use === 'file' && ' (no run shares yet)'}
        </span>
        {err && <span style={{ fontSize: 12, color: theme.danger }}>{err}</span>}
      </div>
    </div>
  )
}

export default function MrpImport() {
  const [status, setStatus]       = useState(null)   // loaded mrp_plan.json summary
  const [clearing, setClearing]   = useState(false)

  const reload = () => {
    fetch('/api/planning/mrp-plan/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setStatus(d) })
  }

  useEffect(() => { reload() }, [])

  const handleClear = async () => {
    setClearing(true)
    await fetch('/api/planning/mrp-plan/clear', { method: 'DELETE' })
    setStatus(null); setClearing(false)
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
          The MRP contribution % the MRP plan splits each department by.
        </p>
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

      <SourcePick onSynced={reload} />

    </div>
  )
}
