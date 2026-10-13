import { useEffect, useRef, useState } from 'react'
import { theme, alpha } from '../theme'

// Final Results' saved versions (user, 2026-10-13: "give me a save button and all tools related to version selection,
// rename, save as, selection window ... Also add a little know how as to what was changed from the 1st version to
// this"). Save = the live plan (and the Rows / Filters) into the version in use; Save as = a new version; Rename;
// Versions… = the selection window; What changed = this version (or the live plan) against Version 1. Never deletes.
const API = '/api/planning/plan-versions'
const L = v => `₹${(v ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} L`
const G = r => (r.ly ? `${((r.ty / r.ly - 1) * 100).toFixed(1)}%` : '–')
const when = s => (s ? s.replace('T', ' ').slice(0, 16) : '')
const CUR = 'sp.fr.version.current'   // the version Save writes to, per browser

async function call(url, body) {
  const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined)
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`)
  return j
}

const btn = primary => ({ padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
  border: `1px solid ${primary ? theme.primary : theme.border}`, background: primary ? theme.primary : theme.surface, color: primary ? '#fff' : theme.textPrimary })

function Modal({ title, onClose, children, width = 640 }) {
  useEffect(() => {
    const esc = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,.35)', zIndex: 1000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '7vh 16px', overflow: 'auto' }}>
      <div role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}
        style={{ width: `min(${width}px, 100%)`, background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, boxShadow: '0 20px 50px rgba(0,0,0,.25)' }}>
        <div style={{ display: 'flex', alignItems: 'center', padding: '12px 18px', borderBottom: `1px solid ${theme.border}` }}>
          <b style={{ flex: 1, fontSize: 15 }}>{title}</b>
          <button type="button" onClick={onClose} aria-label="Close" style={{ all: 'unset', cursor: 'pointer', fontSize: 18, color: theme.textMuted }}>✕</button>
        </div>
        <div style={{ padding: '14px 18px 16px' }}>{children}</div>
      </div>
    </div>
  )
}

function NameForm({ label, initial, onSubmit, onClose }) {
  const [v, setV] = useState(initial || '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const go = async e => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await onSubmit(v.trim()); onClose() } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <Modal title={label} onClose={onClose} width={440}>
      <form onSubmit={go} style={{ display: 'grid', gap: 10 }}>
        <input autoFocus value={v} onChange={e => setV(e.target.value)} maxLength={80} placeholder="Version name" aria-label="Version name"
          style={{ padding: '7px 10px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 13 }} />
        {err && <div style={{ color: theme.danger, fontSize: 12 }}>{err}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose} style={btn(false)}>Cancel</button>
          <button type="submit" disabled={busy} style={btn(true)}>{busy ? 'Saving…' : 'OK'}</button>
        </div>
      </form>
    </Modal>
  )
}

function Changes({ id, versions, onClose }) {
  const [base, setBase] = useState(versions[0]?.id || '')
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setD(null); setErr('')
    call(`${API}/changes?${new URLSearchParams({ id: id || 'live', base })}`).then(setD).catch(e => setErr(e.message))
  }, [id, base])
  return (
    <Modal title="What changed" onClose={onClose} width={700}>
      <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 10, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        {id ? `"${versions.find(v => v.id === id)?.name}"` : 'The live plan'} compared with
        <select value={base} onChange={e => setBase(e.target.value)} aria-label="Compare with" style={{ fontSize: 12, padding: '2px 6px' }}>
          {versions.map(v => <option key={v.id} value={v.id}>{v.name}{v.n === versions[0].n ? ' (first)' : ''}</option>)}
        </select>
      </div>
      {err && <div style={{ color: theme.danger, fontSize: 13 }}>{err}</div>}
      {!d && !err && <div style={{ color: theme.textMuted, fontSize: 13 }}>Comparing…</div>}
      {d && (<>
        <div style={{ display: 'grid', gap: 7 }}>
          {d.lines.map((x, i) => <div key={i} style={{ fontSize: 13, lineHeight: 1.5 }}><b>{x.h}</b> — {x.t}</div>)}
        </div>
        {d.departments.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12, fontSize: 12 }}>
            <thead><tr>{['Department', 'Division', d.base.name, d.cur.name, 'Change'].map((h, i) => (
              <th key={i} style={{ textAlign: i > 1 ? 'right' : 'left', padding: '5px 8px', color: theme.textMuted, fontSize: 10.5, borderBottom: `1px solid ${theme.border}` }}>{h}</th>))}</tr></thead>
            <tbody>{d.departments.map(r => (
              <tr key={r.division + r.department}>
                <td style={{ padding: '4px 8px' }}>{r.department}</td><td style={{ padding: '4px 8px', color: theme.textMuted }}>{r.division}</td>
                <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(r.base_ty)}</td>
                <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(r.ty)}</td>
                <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono, fontWeight: 700, color: r.diff >= 0 ? theme.success : theme.danger }}>{r.diff >= 0 ? '+' : ''}{r.diff.toFixed(2)}</td>
              </tr>))}</tbody>
          </table>
        )}
      </>)}
    </Modal>
  )
}

export default function PlanVersions({ version, onOpen, view }) {
  const [list, setList] = useState(null)       // {versions, live}
  const [err, setErr] = useState('')
  const [cur, setCur] = useState(() => { try { return localStorage.getItem(CUR) || '' } catch { return '' } })
  const [dlg, setDlg] = useState(null)         // 'pick' | 'saveas' | 'rename' | 'changes'
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const reload = () => call(API).then(setList).catch(e => setErr(e.message))
  useEffect(() => { reload() }, [])
  // the first load takes up where this user left off - in any browser (the server remembers, 2026-10-13: "if i saved
  // a version here it should stay saved in my next session"); a version not on this server: back to the live plan
  const first = useRef(true)
  useEffect(() => {
    if (!list) return
    const me = list.me || {}
    const has = id => list.versions.some(v => v.id === id)
    if (first.current) {
      first.current = false
      if (me.current && has(me.current)) keepCur(me.current)
      if (me.open !== undefined && me.open !== version && (me.open === '' || has(me.open))) { onOpen(list.versions.find(v => v.id === me.open) || null); return }
    }
    if (version && !has(version)) onOpen(null)
  }, [list])   // eslint-disable-line react-hooks/exhaustive-deps
  const openIt = v => { onOpen(v); call(`${API}/open`, { id: v ? v.id : '' }).catch(() => {}) }
  const keepCur = id => { setCur(id); try { localStorage.setItem(CUR, id) } catch { /* ignore */ } }
  const vs = list?.versions || []
  // what Save writes to: the version open, else the one this browser saved last, else the newest
  const target = vs.find(v => v.id === (version || cur)) || vs[vs.length - 1] || null
  const open = vs.find(v => v.id === version) || null
  const unsaved = list && target && (Math.abs(list.live.ty - target.ty) > 0.005 || JSON.stringify(view) !== JSON.stringify(target.view))

  const save = async () => {
    setBusy(true); setNote('')
    try {
      const r = await call(`${API}/save`, target ? { id: target.id, view } : { view })
      keepCur(r.id); setNote(`Saved to "${r.name}" ${when(r.updated_at)}`); await reload()
    } catch (e) { setNote(`Not saved: ${e.message}`) } finally { setBusy(false) }
  }
  const saveAs = async name => { const r = await call(`${API}/save`, { name, view }); keepCur(r.id); setNote(`Saved as "${r.name}"`); await reload() }
  const rename = async name => { const r = await call(`${API}/rename`, { id: target.id, name }); setNote(`Renamed to "${r.name}"`); await reload() }

  return (
    <div data-no-undo style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '8px 16px', marginBottom: 10 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>Version</span>
      <button type="button" onClick={() => setDlg('pick')} aria-haspopup="dialog" title="Open a saved version or the live plan"
        style={{ ...btn(false), display: 'inline-flex', gap: 6, alignItems: 'center', borderColor: open ? theme.primary : theme.border, background: open ? alpha(theme.primary, '12') : theme.surface }}>
        {open ? open.name : 'Live plan'} <span aria-hidden="true" style={{ fontSize: 10, color: theme.textMuted }}>▾</span>
      </button>
      <button type="button" onClick={save} disabled={busy || !list} style={btn(true)}
        title={target ? `Save the live plan and this layout into "${target.name}"` : 'Save the live plan as Version 1'}>
        {busy ? 'Saving…' : target ? `Save to "${target.name}"` : 'Save'}
      </button>
      <button type="button" onClick={() => setDlg('saveas')} disabled={!list} style={btn(false)}>Save as…</button>
      <button type="button" onClick={() => setDlg('rename')} disabled={!target} style={btn(false)}>Rename</button>
      <button type="button" onClick={() => setDlg('changes')} disabled={!vs.length} style={btn(false)} title="What changed from Version 1 to this">What changed</button>
      <span style={{ fontSize: 11.5, color: theme.textMuted }}>
        {err ? <span style={{ color: theme.danger }}>{err}</span>
          : note ? note
          : open ? `Viewing "${open.name}" as saved ${when(open.updated_at)}${open.saved_by ? ` by ${open.saved_by}` : ''} - frozen; the live plan keeps updating`
          : !list ? 'Loading versions…'
          : !target ? 'Nothing saved yet - Save keeps this plan and layout as Version 1'
          : unsaved ? <span style={{ color: theme.warning, fontWeight: 600 }}>Unsaved: the live plan or layout differs from "{target.name}" ({when(target.updated_at)})</span>
          : `Saved - matches "${target.name}" (${when(target.updated_at)})`}
      </span>

      {dlg === 'pick' && (
        <Modal title="Versions" onClose={() => setDlg(null)} width={760}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead><tr>{['Version', 'Saved', 'By', 'Months', 'TY', 'Growth', ''].map((h, i) => (
              <th key={i} style={{ textAlign: i >= 4 && i < 6 ? 'right' : 'left', padding: '6px 8px', fontSize: 10.5, color: theme.textMuted, borderBottom: `1px solid ${theme.border}` }}>{h}</th>))}</tr></thead>
            <tbody>
              <tr style={{ background: !version ? alpha(theme.primary, '10') : undefined }}>
                <td style={{ padding: '6px 8px', fontWeight: 700 }}>Live plan</td><td style={{ padding: '6px 8px', color: theme.textMuted }}>updates by itself</td><td /><td />
                <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(list?.live.ty)}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{list ? G(list.live) : ''}</td>
                <td style={{ padding: '6px 8px', textAlign: 'right' }}><button type="button" style={btn(!version)} onClick={() => { openIt(null); setDlg(null) }}>{!version ? 'Open now' : 'Open'}</button></td>
              </tr>
              {[...vs].reverse().map(v => (
                <tr key={v.id} style={{ borderTop: `1px solid ${theme.border}`, background: v.id === version ? alpha(theme.primary, '10') : undefined }}>
                  <td style={{ padding: '6px 8px', fontWeight: 600 }} title={(v.history || []).map(h => `${when(h.at)} ${h.what}${h.by ? ` (${h.by})` : ''}`).join('\n')}>
                    {v.name}{v.id === target?.id && <span style={{ fontSize: 10, color: theme.primary, marginLeft: 6 }}>Save writes here</span>}
                    {v.n === vs[0].n && <span style={{ fontSize: 10, color: theme.textMuted, marginLeft: 6 }}>first</span>}
                  </td>
                  <td style={{ padding: '6px 8px', color: theme.textMuted, whiteSpace: 'nowrap' }}>{when(v.updated_at)}</td>
                  <td style={{ padding: '6px 8px', color: theme.textMuted }}>{v.saved_by || '–'}</td>
                  <td style={{ padding: '6px 8px', color: theme.textMuted }}>{(v.months || []).join(', ')}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(v.ty)}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{G(v)}</td>
                  <td style={{ padding: '6px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <button type="button" style={btn(v.id === version)} onClick={() => { keepCur(v.id); openIt(v); setDlg(null) }}>{v.id === version ? 'Open now' : 'Open'}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!vs.length && <div style={{ fontSize: 12.5, color: theme.textMuted, padding: '10px 8px' }}>No saved versions yet - Save keeps the live plan and this layout as Version 1.</div>}
          <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 10 }}>Open shows that version's plan and layout exactly as saved. Hover a name for its history. Versions are never deleted.</div>
        </Modal>
      )}
      {dlg === 'saveas' && <NameForm label="Save as a new version" initial={`Version ${vs.reduce((m, v) => Math.max(m, v.n), 0) + 1}`} onSubmit={saveAs} onClose={() => setDlg(null)} />}
      {dlg === 'rename' && target && <NameForm label={`Rename "${target.name}"`} initial={target.name} onSubmit={rename} onClose={() => setDlg(null)} />}
      {dlg === 'changes' && <Changes id={version} versions={vs} onClose={() => setDlg(null)} />}
    </div>
  )
}
