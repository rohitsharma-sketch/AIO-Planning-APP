import { useState, useEffect, Fragment } from 'react'
import { theme, alpha } from '../theme'

// user, 2026-10-13: "i need a editable hierarchial system for editing a hierarchy for view" - pick the levels and their
// order, then drill the plan as a tree (view only). Each branch is fetched when it is opened
// (GET /api/planning/grain/hierarchy, from the same plan the Store / Cluster panels use). The order is kept per browser.
const LEVELS = {
  cluster: 'Cluster', store: 'Store', stype: 'Store type (SSG / NSO)', division: 'Division',
  attribute: 'Attribute', department: 'Department', month: 'Month',
}
const DEFAULT = ['cluster', 'store', 'division', 'department']
const KEY = 'sp.fr.hierarchy'
const L = v => (v ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const gr = (ty, ly) => (ly > 0 ? (ty / ly - 1) * 100 : null)
const P = v => (v == null ? '–' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`)

function loadLevels() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || 'null')
    if (Array.isArray(v) && v.length && v.every(x => LEVELS[x]) && new Set(v).size === v.length) return v
  } catch { /* ignore */ }
  return DEFAULT
}

export default function HierarchyView() {
  const [levels, setLevels] = useState(loadLevels)
  const [nodes, setNodes] = useState({})          // JSON(path) -> {rows, total, level} | {err} | 'loading'
  const [open, setOpen] = useState(() => new Set())
  const [source, setSource] = useState(null)

  const fetchNode = path => {
    const k = JSON.stringify(path)
    setNodes(n => ({ ...n, [k]: 'loading' }))
    const qs = new URLSearchParams({ levels: levels.join(','), path: k })
    fetch(`/api/planning/grain/hierarchy?${qs}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(j => { setNodes(n => ({ ...n, [k]: j })); if (j.source) setSource(j.source) })
      .catch(e => setNodes(n => ({ ...n, [k]: { err: e.message } })))
  }

  // a new hierarchy starts again from the top
  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(levels)) } catch { /* ignore */ }
    setNodes({}); setOpen(new Set()); fetchNode([])
  }, [levels.join(',')])   // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = path => {
    const k = JSON.stringify(path)
    setOpen(o => { const n = new Set(o); n.has(k) ? n.delete(k) : n.add(k); return n })
    if (!nodes[k]) fetchNode(path)
  }
  const move = (i, d) => setLevels(l => { const n = [...l]; [n[i], n[i + d]] = [n[i + d], n[i]]; return n })
  const unused = Object.keys(LEVELS).filter(x => !levels.includes(x))

  const chip = { display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 6px 4px 10px', borderRadius: 8, border: `1px solid ${theme.border}`, background: theme.surface, fontSize: 12, fontWeight: 600, color: theme.textPrimary }
  const mini = { all: 'unset', cursor: 'pointer', padding: '0 4px', color: theme.textMuted, fontSize: 12 }
  const th = { padding: '8px 12px', fontSize: 11, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, textAlign: 'right', borderBottom: `1px solid ${theme.border}`, background: theme.surfaceAlt }
  const td = { padding: '6px 12px', fontSize: 12.5, textAlign: 'right', fontFamily: theme.fontMono, borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap' }

  const renderRows = (path, depth) => {
    const node = nodes[JSON.stringify(path)]
    if (!node || node === 'loading') return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', paddingLeft: 16 + depth * 22, color: theme.textMuted }}>Loading…</td></tr>
    if (node.err) return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', paddingLeft: 16 + depth * 22, color: theme.danger }}>{node.err}</td></tr>
    const parentTy = node.total?.ty || 0
    return node.rows.map(r => {
      const p = [...path, r.key], k = JSON.stringify(p), leaf = p.length >= levels.length, isOpen = open.has(k)
      return (
        <Fragment key={k}>
          <tr style={{ background: depth === 0 ? theme.surface : alpha(theme.primary, (4 + depth * 3).toString().padStart(2, '0')) }}>
            <td style={{ ...td, textAlign: 'left', fontFamily: 'inherit', paddingLeft: 12 + depth * 22, fontWeight: depth === 0 ? 700 : 500 }}>
              {leaf ? <span style={{ display: 'inline-block', width: 18 }} /> : (
                <button type="button" onClick={() => toggle(p)} aria-expanded={isOpen} aria-label={`${isOpen ? 'Close' : 'Open'} ${r.key}`}
                  style={{ ...mini, width: 18, color: theme.textPrimary }}>{isOpen ? '▾' : '▸'}</button>
              )}
              {r.key}
              <span style={{ marginLeft: 8, fontSize: 10.5, color: theme.textMuted, fontWeight: 400 }}>{LEVELS[node.level]}</span>
            </td>
            <td style={{ ...td, color: theme.textSecondary }}>{L(r.ly)}</td>
            <td style={{ ...td, fontWeight: 700 }}>{L(r.ty)}</td>
            <td style={{ ...td, color: (gr(r.ty, r.ly) ?? 0) >= 0 ? theme.success : theme.danger }}>{P(gr(r.ty, r.ly))}</td>
            <td style={{ ...td, color: theme.textSecondary }}>{parentTy ? `${(r.ty / parentTy * 100).toFixed(1)}%` : '–'}</td>
          </tr>
          {isOpen && renderRows(p, depth + 1)}
        </Fragment>
      )
    })
  }

  const root = nodes['[]']
  return (
    <div>
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '12px 16px', marginBottom: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 8 }}>Hierarchy - pick the levels and their order</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {levels.map((x, i) => (
            <Fragment key={x}>
              {i > 0 && <span style={{ color: theme.textMuted }}>→</span>}
              <span style={chip}>
                {LEVELS[x]}
                <button type="button" style={mini} disabled={i === 0} onClick={() => move(i, -1)} aria-label={`Move ${LEVELS[x]} up`} title="Move up a level">◀</button>
                <button type="button" style={mini} disabled={i === levels.length - 1} onClick={() => move(i, 1)} aria-label={`Move ${LEVELS[x]} down`} title="Move down a level">▶</button>
                <button type="button" style={mini} disabled={levels.length === 1} onClick={() => setLevels(l => l.filter(y => y !== x))} aria-label={`Remove ${LEVELS[x]}`} title="Remove this level">✕</button>
              </span>
            </Fragment>
          ))}
          {unused.length > 0 && (
            <select value="" onChange={e => e.target.value && setLevels(l => [...l, e.target.value])} aria-label="Add a level"
              style={{ padding: '5px 8px', borderRadius: 8, border: `1px dashed ${theme.border}`, fontSize: 12, background: theme.surface }}>
              <option value="">+ Add level…</option>
              {unused.map(x => <option key={x} value={x}>{LEVELS[x]}</option>)}
            </select>
          )}
          <button type="button" onClick={() => setLevels(DEFAULT)} style={{ ...mini, marginLeft: 'auto', textDecoration: 'underline' }}>Reset</button>
        </div>
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 8 }}>
          View only · ₹ lakh · {levels.includes('month') ? 'by month' : 'all plan months added up'} · Cont % = share of the level above
          {source && <> · from {source.note || source.name}</>}
        </div>
      </div>
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr>
            <th style={{ ...th, textAlign: 'left' }}>{levels.map(x => LEVELS[x]).join(' → ')}</th>
            <th style={th}>LY (₹L)</th><th style={th}>TY (₹L)</th><th style={th}>Growth %</th><th style={th}>Cont %</th>
          </tr></thead>
          <tbody>
            {renderRows([], 0)}
            {root && root !== 'loading' && !root.err && (
              <tr style={{ fontWeight: 700 }}>
                <td style={{ ...td, textAlign: 'left', fontFamily: 'inherit' }}>Total</td>
                <td style={td}>{L(root.total.ly)}</td><td style={td}>{L(root.total.ty)}</td>
                <td style={td}>{P(gr(root.total.ty, root.total.ly))}</td><td style={td}>100%</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
