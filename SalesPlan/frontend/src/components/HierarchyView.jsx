import { useState, useEffect, useRef, Fragment } from 'react'
import { theme, alpha } from '../theme'
import ExcelFilter from './ExcelFilter'

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

// user, 2026-10-13: "a pop up of how the respective department or cluster is getting that number ... To validate ...
// in plain words and summarised" - GET /api/planning/grain/explain builds it from the very cells the row adds up, so the
// parts always add back to the number on the row; what it explains follows the level clicked (division, department,
// cluster, store, month ...)
function Explain({ levels, path, filters, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    const qs = new URLSearchParams({ levels: levels.join(','), path: JSON.stringify(path), filters: JSON.stringify(filters) })
    fetch(`/api/planning/grain/explain?${qs}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(setD).catch(e => setErr(e.message))
    const esc = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  const tile = { flex: '1 1 110px', background: theme.surfaceAlt, border: `1px solid ${theme.border}`, borderRadius: 8, padding: '8px 10px' }
  const cap = { fontSize: 10.5, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4 }
  const big = { fontSize: 16, fontWeight: 700, fontFamily: theme.fontMono, marginTop: 2 }
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,.35)', zIndex: 1000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '6vh 16px', overflow: 'auto' }}>
      <div role="dialog" aria-modal="true" aria-label="How this number is made" onClick={e => e.stopPropagation()}
        style={{ width: 'min(720px, 100%)', background: theme.surface, borderRadius: 12, border: `1px solid ${theme.border}`, boxShadow: '0 20px 50px rgba(0,0,0,.25)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '14px 18px', borderBottom: `1px solid ${theme.border}` }}>
          <div style={{ flex: 1 }}>
            <div style={cap}>How this number is made</div>
            <div style={{ fontSize: 15, fontWeight: 700, marginTop: 3 }}>
              {path.length ? path.map((v, i) => <span key={i}>{i > 0 && <span style={{ color: theme.textMuted }}> → </span>}{v} <span style={{ fontSize: 10.5, fontWeight: 400, color: theme.textMuted }}>{LEVELS[levels[i]]}</span></span>) : 'Total'}
            </div>
          </div>
          <button type="button" autoFocus onClick={onClose} aria-label="Close" style={{ all: 'unset', cursor: 'pointer', fontSize: 18, color: theme.textMuted, padding: '0 4px' }}>✕</button>
        </div>
        <div style={{ padding: '14px 18px 16px' }}>
          {err && <div style={{ color: theme.danger, fontSize: 13 }}>Could not explain it: {err}</div>}
          {!d && !err && <div style={{ color: theme.textMuted, fontSize: 13 }}>Working it out…</div>}
          {d && (<>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <div style={tile}><div style={cap}>LY (₹L)</div><div style={big}>{L(d.ly)}</div></div>
              <div style={tile}><div style={cap}>TY (₹L)</div><div style={big}>{L(d.ty)}</div></div>
              <div style={tile}><div style={cap}>Growth %</div><div style={{ ...big, color: (d.growth ?? 0) >= 0 ? theme.success : theme.danger }}>{P(d.growth)}</div></div>
              <div style={tile}><div style={cap}>Cont %</div><div style={big}>{d.cont == null ? (path.length ? '–' : '100%') : `${d.cont.toFixed(1)}%`}</div></div>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {d.lines.map((x, i) => (
                <div key={i} style={{ fontSize: 13, lineHeight: 1.5, ...(x.h === 'Check' ? { background: alpha(theme.success, '14'), border: `1px solid ${alpha(theme.success, '40')}`, borderRadius: 8, padding: '8px 10px' } : {}) }}>
                  <b style={{ color: theme.navy || theme.textPrimary }}>{x.h}</b> — {x.t}
                </div>
              ))}
            </div>
            {d.months?.length > 1 && (
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12, fontSize: 12 }}>
                <thead><tr>{['Month', 'LY (₹L)', 'TY (₹L)', 'Growth %'].map((h, i) => <th key={h} style={{ textAlign: i ? 'right' : 'left', padding: '5px 8px', color: theme.textMuted, fontSize: 10.5, borderBottom: `1px solid ${theme.border}` }}>{h}</th>)}</tr></thead>
                <tbody>{d.months.map(m => (
                  <tr key={m.month}>
                    <td style={{ padding: '4px 8px' }}>{m.month}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(m.ly)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono, fontWeight: 600 }}>{L(m.ty)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{P(gr(m.ty, m.ly))}</td>
                  </tr>))}</tbody>
              </table>
            )}
            {d.source && <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 10 }}>From {d.source} · ₹ lakh · view only</div>}
          </>)}
        </div>
      </div>
    </div>
  )
}

// user, 2026-10-13: "filters required" then "the filters should be individual filters - excel styled": every level has
// its own Excel-style list; the tree, totals, Cont % and the ⓘ pop-up count only what is inside them. Kept per browser.
const FKEY = 'sp.fr.filters'
function loadFilters() {
  try { const v = JSON.parse(localStorage.getItem(FKEY) || '{}'); if (v && typeof v === 'object') return v } catch { /* ignore */ }
  return {}
}
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
  const [filters, setFilters] = useState(loadFilters)   // {level: [values]}
  const [editing, setEditing] = useState(null)          // {level, anchor} - the Excel filter open now
  const fkey = JSON.stringify(filters)
  const [why, setWhy] = useState(null)            // path of the row whose numbers are being explained
  const back = useRef(null)                       // the ⓘ that opened it - focus goes back there on close
  const lastLv = useRef(null)
  const info = p => (
    <button type="button" onClick={e => { back.current = e.currentTarget; setWhy(p) }} aria-label={`How ${p.length ? p[p.length - 1] : 'the total'} is made`} title="How is this number made?"
      style={{ all: 'unset', cursor: 'pointer', marginLeft: 6, fontSize: 12, color: theme.primary, padding: '0 3px' }}>ⓘ</button>
  )

  const fetchNode = path => {
    const k = JSON.stringify(path)
    setNodes(n => ({ ...n, [k]: 'loading' }))
    const qs = new URLSearchParams({ levels: levels.join(','), path: k, filters: fkey })
    fetch(`/api/planning/grain/hierarchy?${qs}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(j => { setNodes(n => ({ ...n, [k]: j })); if (j.source) setSource(j.source) })
      .catch(e => setNodes(n => ({ ...n, [k]: { err: e.message } })))
  }

  // a new hierarchy starts again from the top; new filters keep the open branches open (each re-fetched at once)
  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(levels)); localStorage.setItem(FKEY, fkey) } catch { /* ignore */ }
    const lv = levels.join(','), same = lastLv.current === lv
    lastLv.current = lv
    setNodes({})
    if (!same) setOpen(new Set())
    fetchNode([])
    if (same) open.forEach(k => fetchNode(JSON.parse(k)))
  }, [levels.join(','), fkey])   // eslint-disable-line react-hooks/exhaustive-deps
  const setFilter = (lv, vals) => setFilters(f => { const n = { ...f }; if (vals && vals.length) n[lv] = vals; else delete n[lv]; return n })
  const openFilter = (lv, el) => setEditing(e => (e && e.level === lv ? null : { level: lv, anchor: el }))

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
  const fbtn = lv => ({ all: 'unset', cursor: 'pointer', borderRadius: 4, padding: '1px 4px', color: filters[lv] ? theme.primary : 'inherit', background: filters[lv] ? alpha(theme.primary, '14') : 'transparent' })

  const renderRows = (path, depth) => {
    const node = nodes[JSON.stringify(path)]
    if (!node || node === 'loading') return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', paddingLeft: 16 + depth * 22, color: theme.textMuted }}>Loading…</td></tr>
    if (node.err) return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', paddingLeft: 16 + depth * 22, color: theme.danger }}>{node.err}</td></tr>
    if (!node.rows.length && depth === 0) return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', color: theme.textMuted }}>Nothing inside these filters.</td></tr>
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
              {info(p)}
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
  const nF = Object.keys(filters).length
  return (
    <div>
      {/* view controls, not plan edits: kept out of the suite's Undo */}
      <div data-no-undo style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '12px 16px', marginBottom: 14 }}>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginRight: 4 }}>Filters</span>
          {!nF && <span style={{ fontSize: 12, color: theme.textMuted }}>none - click ▾ on a column heading below</span>}
          {Object.entries(filters).map(([lv, vals]) => (
            <span key={lv} style={{ ...chip, background: alpha(theme.primary, '12'), borderColor: alpha(theme.primary, '50') }}>
              <button type="button" onClick={e => openFilter(lv, e.currentTarget)} style={{ all: 'unset', cursor: 'pointer' }} title="Change">
                {LEVELS[lv]}: <span style={{ fontWeight: 400 }}>{vals.length > 3 ? `${vals.slice(0, 3).join(', ')} +${vals.length - 3}` : vals.join(', ')}</span>
              </button>
              <button type="button" style={mini} onClick={() => setFilter(lv, null)} aria-label={`Remove the ${LEVELS[lv]} filter`} title="Remove this filter">✕</button>
            </span>
          ))}
          {unused.filter(x => !filters[x]).length > 0 && (
            <select value="" onChange={e => { const v = e.target.value; if (v) openFilter(v, e.target) }} aria-label="Filter a level that is not in the hierarchy"
              style={{ padding: '5px 8px', borderRadius: 8, border: `1px dashed ${theme.border}`, fontSize: 12, background: theme.surface }}>
              <option value="">+ Other level…</option>
              {unused.filter(x => !filters[x]).map(x => <option key={x} value={x}>{LEVELS[x]}</option>)}
            </select>
          )}
          {nF > 0 && <button type="button" onClick={() => setFilters({})} style={{ ...mini, textDecoration: 'underline' }}>Clear all filters</button>}
        </div>
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 8 }}>
          View only · ₹ lakh · {levels.includes('month') ? 'by month' : 'all plan months added up'} · Cont % = share of the level above · ⓘ = how a row's numbers are made
          {source && <> · from {source.note || source.name}</>}
        </div>
      </div>
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr>
            <th style={{ ...th, textAlign: 'left' }} data-no-undo>
              {levels.map((x, i) => (
                <Fragment key={x}>
                  {i > 0 && ' → '}
                  <button type="button" onClick={e => openFilter(x, e.currentTarget)} style={fbtn(x)} aria-haspopup="dialog"
                    aria-label={`Filter ${LEVELS[x]}${filters[x] ? ` (${filters[x].length} picked)` : ''}`} title={filters[x] ? `Filtered: ${filters[x].join(', ')}` : `Filter ${LEVELS[x]}`}>
                    {LEVELS[x]} <span aria-hidden="true">{filters[x] ? '▼' : '▾'}</span>
                  </button>
                </Fragment>
              ))}
            </th>
            <th style={th}>LY (₹L)</th><th style={th}>TY (₹L)</th><th style={th}>Growth %</th><th style={th}>Cont %</th>
          </tr></thead>
          <tbody>
            {renderRows([], 0)}
            {root && root !== 'loading' && !root.err && (
              <tr style={{ fontWeight: 700 }}>
                <td style={{ ...td, textAlign: 'left', fontFamily: 'inherit' }}>Total{nF ? ' (filtered)' : ''}{info([])}</td>
                <td style={td}>{L(root.total.ly)}</td><td style={td}>{L(root.total.ty)}</td>
                <td style={td}>{P(gr(root.total.ty, root.total.ly))}</td><td style={td}>100%</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && <ExcelFilter key={editing.level + fkey} title={LEVELS[editing.level]} anchor={editing.anchor} picked={filters[editing.level]}
        load={() => fetch(`/api/planning/grain/hierarchy-options?${new URLSearchParams({ level: editing.level, filters: fkey })}`)
          .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j[editing.level] || [] })}
        onDone={vals => { if (vals !== undefined) setFilter(editing.level, vals); setEditing(null) }} />}
      {why && <Explain key={JSON.stringify(why) + fkey} levels={levels} path={why} filters={filters} onClose={() => { setWhy(null); back.current?.focus() }} />}
    </div>
  )
}
