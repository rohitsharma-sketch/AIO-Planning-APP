import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { theme } from '../theme'
import { API, call, openPlanVersion, openVersionId, saveTargetId, keepSaveTarget, versionsChanged, currentView, when } from '../planVersion'
import { Modal, NameForm } from './PlanVersions'

// The header's plan iteration picker, BIS's in Sales Plan (user, 2026-10-14: "how to save plan iterations and give me
// the same features as this button in similar fashion"): pick the live plan or a saved iteration (it opens on Final
// Results), then Save to the iteration in use / Save as new iteration / Rename / Remove (hides it; the file is kept;
// the first stays, like BIS's Original).
const FR = '/department-plan/final-results'

export default function VersionPicker() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [list, setList] = useState(null)
  const [open, setOpen] = useState(openVersionId)
  const [dlg, setDlg] = useState(null)   // 'saveas' | 'rename' | 'rm'
  const [note, setNote] = useState('')
  const reload = () => call(API).then(setList).catch(() => setList(null))
  useEffect(() => {
    reload()
    const v = e => setOpen(e.detail ? e.detail.id : '')
    window.addEventListener('sp-versions', reload)
    window.addEventListener('sp-version', v)
    return () => { window.removeEventListener('sp-versions', reload); window.removeEventListener('sp-version', v) }
  }, [])
  useEffect(() => { if (!note) return; const t = setTimeout(() => setNote(''), 4000); return () => clearTimeout(t) }, [note])

  const vs = list?.versions || []
  const target = vs.find(v => v.id === (open || saveTargetId())) || vs[vs.length - 1] || null
  const tell = t => { setNote(t); versionsChanged() }

  const pick = async id => {
    if (id === '__save') {
      try {
        const r = await call(`${API}/save`, target ? { id: target.id, view: currentView() } : { view: currentView() })
        keepSaveTarget(r.id); tell(`Saved to "${r.name}"`)
      } catch (e) { setNote(`Not saved: ${e.message}`) }
      return
    }
    if (id.startsWith('__')) { setDlg(id.slice(2)); return }
    const v = vs.find(x => x.id === id) || null
    setOpen(id)
    openPlanVersion(v)
    if (!pathname.startsWith(FR)) navigate(FR)
  }
  const saveAs = async name => { const r = await call(`${API}/save`, { name, view: currentView() }); keepSaveTarget(r.id); tell(`Saved as "${r.name}"`) }
  const rename = async name => { const r = await call(`${API}/rename`, { id: target.id, name }); tell(`Renamed to "${r.name}"`) }
  const remove = async v => {
    if (!window.confirm(`Remove "${v.name}" from the list? Its saved file is kept.`)) return
    try {
      await call(`${API}/remove`, { id: v.id })
      if (open === v.id) { setOpen(''); openPlanVersion(null) }
      tell(`Removed "${v.name}"`)
    } catch (e) { setNote(e.message) }
  }

  const sel = { height: 32, maxWidth: 270, padding: '0 8px', borderRadius: 8, fontSize: 12.5, fontWeight: 700, cursor: 'pointer',
    background: 'rgba(255,255,255,0.10)', color: '#fff', border: '1px solid rgba(255,255,255,0.35)' }
  const opt = { color: theme.textPrimary, background: theme.surface }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      {note && <span role="status" style={{ fontSize: 11.5, color: 'rgba(255,255,255,0.8)' }}>{note}</span>}
      <select value={vs.some(v => v.id === open) ? open : ''} onChange={e => pick(e.target.value)} disabled={!list} style={sel}
        aria-label="Plan iteration" title="Open the live plan or a saved iteration (Final Results); save, save as, rename or remove">
        <option value="" style={opt}>Live plan · updates by itself</option>
        {[...vs].reverse().map(v => <option key={v.id} value={v.id} style={opt}>{v.name} · {when(v.updated_at)}</option>)}
        <option disabled style={opt}>──────────</option>
        <option value="__save" style={opt}>💾 {target ? `Save to "${target.name}"` : 'Save the live plan (first iteration)'}</option>
        <option value="__saveas" style={opt}>⧉ Save as new iteration…</option>
        <option value="__rename" style={opt} disabled={!target}>✎ Rename a version…</option>
        <option value="__rm" style={opt} disabled={vs.length < 2}>✕ Remove an iteration…</option>
      </select>
      {dlg === 'saveas' && <NameForm label="Save as a new iteration" initial={`Iteration ${vs.reduce((m, v) => Math.max(m, v.n), 0) + 1}`} onSubmit={saveAs} onClose={() => setDlg(null)} />}
      {dlg === 'rename' && target && <NameForm label={`Rename "${target.name}"`} initial={target.name} onSubmit={rename} onClose={() => setDlg(null)} />}
      {dlg === 'rm' && (
        <Modal title="Remove an iteration" onClose={() => setDlg(null)} width={520}>
          {vs.slice(1).reverse().map(v => (
            <div key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderBottom: `1px solid ${theme.border}`, fontSize: 13 }}>
              <span style={{ flex: 1 }}><b>{v.name}</b> <span style={{ color: theme.textMuted }}>· {when(v.updated_at)}</span></span>
              <button type="button" onClick={() => remove(v)} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 12, cursor: 'pointer', border: `1px solid ${theme.danger}`, background: theme.surface, color: theme.danger }}>Remove</button>
            </div>
          ))}
          <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 10 }}>"{vs[0]?.name}" is the first and stays. A removed iteration leaves the lists; its saved file is kept.</div>
        </Modal>
      )}
    </div>
  )
}
