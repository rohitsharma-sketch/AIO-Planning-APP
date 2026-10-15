import { useState, useEffect, useRef, Fragment } from 'react'
import { theme, alpha } from '../theme'
import ExcelFilter from './ExcelFilter'
import PlanVersions from './PlanVersions'

// user, 2026-10-13: "i need a editable hierarchial system for editing a hierarchy for view" - pick the levels and their
// order, then drill the plan as a tree (view only). Each branch is fetched when it is opened
// (GET /api/planning/grain/hierarchy, from the same plan the Store / Cluster panels use). The order is kept per browser.
const LEVELS = {
  cluster: 'Cluster', store: 'Store', stype: 'Store group', division: 'Division',
  attribute: 'Attribute', department: 'Department', month: 'Month',
}
const COLS = { ly: 'LY (₹L)', ty: 'TY (₹L)', growth: 'Growth %' }   // the number columns (Re-apportionment: Before / After)
const DEFAULT = ['cluster', 'store', 'division', 'department']
const L = v => (v ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const gr = (ty, ly) => (ly > 0 ? (ty / ly - 1) * 100 : null)
const P = v => (v == null ? '–' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`)

// user, 2026-10-13: "a pop up of how the respective department or cluster is getting that number ... To validate ...
// in plain words and summarised" - GET /api/planning/grain/explain builds it from the very cells the row adds up, so the
// parts always add back to the number on the row; what it explains follows the level clicked (division, department,
// cluster, store, month ...)
function Explain({ api, LV, query, cols = COLS, levels, path, filters, version, onClose }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    const qs = new URLSearchParams({ levels: levels.join(','), path: JSON.stringify(path), filters: JSON.stringify(filters), version, ...query })
    fetch(`${api}/explain?${qs}`)
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
              {path.length ? path.map((v, i) => <span key={i}>{i > 0 && <span style={{ color: theme.textMuted }}> → </span>}{v} <span style={{ fontSize: 10.5, fontWeight: 400, color: theme.textMuted }}>{LV[levels[i]]}</span></span>) : 'Total'}
            </div>
          </div>
          <button type="button" autoFocus onClick={onClose} aria-label="Close" style={{ all: 'unset', cursor: 'pointer', fontSize: 18, color: theme.textMuted, padding: '0 4px' }}>✕</button>
        </div>
        <div style={{ padding: '14px 18px 16px' }}>
          {err && <div style={{ color: theme.danger, fontSize: 13 }}>Could not explain it: {err}</div>}
          {!d && !err && <div style={{ color: theme.textMuted, fontSize: 13 }}>Working it out…</div>}
          {d && (<>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
              <div style={tile}><div style={cap}>{cols.ly}</div><div style={big}>{L(d.ly)}</div></div>
              <div style={tile}><div style={cap}>{cols.ty}</div><div style={big}>{L(d.ty)}</div></div>
              <div style={tile} title={d.ref ? `A new department grows as its reference: ${d.ref.pct}% of ${d.ref.dept}'s plan (its own LY is not the base)` : undefined}>
                <div style={cap}>{d.growth_label || cols.growth}</div><div style={{ ...big, color: (d.growth ?? 0) >= 0 ? theme.success : theme.danger }}>{P(d.growth)}</div></div>
              <div style={tile}><div style={cap}>Cont %</div><div style={big}>{d.cont == null ? (path.length ? '–' : '100%') : `${d.cont.toFixed(1)}%`}</div></div>
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {d.lines.map((x, i) => (
                <div key={i} style={{ fontSize: 13, lineHeight: 1.5, ...(x.h === 'Check' ? { background: alpha(theme.success, '14'), border: `1px solid ${alpha(theme.success, '40')}`, borderRadius: 8, padding: '8px 10px' } : {}) }}>
                  <b style={{ color: theme.navy || theme.textPrimary }}>{x.h}</b> — {x.t}
                </div>
              ))}
            </div>
            {d.table && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 10.5, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 4 }}>{d.table.title}</div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                    <thead><tr>{d.table.cols.map((h, i) => <th key={h} style={{ textAlign: i ? 'right' : 'left', padding: '4px 6px', color: theme.textMuted, fontSize: 10, borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap' }}>{h}</th>)}</tr></thead>
                    <tbody>{d.table.rows.map((r, j) => <tr key={j}>{r.map((v, i) => <td key={i} style={{ padding: '3px 6px', textAlign: i ? 'right' : 'left', fontFamily: i ? theme.fontMono : 'inherit', whiteSpace: 'nowrap', fontWeight: i === r.length - 1 ? 700 : 400 }}>{v}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              </div>
            )}
            {d.months?.length > 1 && !d.table && (
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 12, fontSize: 12 }}>
                <thead><tr>{['Month', cols.ly, cols.ty, d.ref ? `Growth · as ${d.ref.dept}` : cols.growth].map((h, i) => <th key={h} style={{ textAlign: i ? 'right' : 'left', padding: '5px 8px', color: theme.textMuted, fontSize: 10.5, borderBottom: `1px solid ${theme.border}` }}>{h}</th>)}</tr></thead>
                <tbody>{d.months.map(m => (
                  <tr key={m.month}>
                    <td style={{ padding: '4px 8px' }}>{m.month}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{L(m.ly)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono, fontWeight: 600 }}>{L(m.ty)}</td>
                    <td style={{ padding: '4px 8px', textAlign: 'right', fontFamily: theme.fontMono }}>{P(d.ref ? m.growth_ref : gr(m.ty, m.ly))}</td>
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
function loadFilters(store) {
  try { const v = JSON.parse(localStorage.getItem(`${store}.filters`) || '{}'); if (v && typeof v === 'object') return v } catch { /* ignore */ }
  return {}
}
function loadLevels(store, LV, defaults) {
  try {
    const v = JSON.parse(localStorage.getItem(`${store}.hierarchy`) || 'null')
    if (Array.isArray(v) && v.length && v.every(x => LV[x]) && new Set(v).size === v.length) return v
  } catch { /* ignore */ }
  return defaults
}

// the same tree serves the department plan (Final Results) and the Article Name plan (user, 2026-10-13: "make similar
// output page as the department with all features similarly"): api = where hierarchy / hierarchy-options / explain
// live, LV = its fields, query = extra query (e.g. grain), store = the localStorage prefix, versions = the version bar
// halves: the Month / P1-P2 switch (user, 2026-10-14: "a view with toggle for month wise or P1 P2, which is also availble
// in excel download too ... P1 P2 is 15 day interval for the month") - the api takes ?period=month|half; Export Excel
// downloads the view as on screen (api/hierarchy-export: Rows, filters, version, period - every branch opened)
export default function HierarchyView({ api = '/api/planning/grain', levels: LV = LEVELS, defaults = DEFAULT, store = 'sp.fr', versions = true, query: query0 = {}, cols = COLS, halves = false }) {
  const [period, setPeriod] = useState(() => { try { return (halves && localStorage.getItem(`${store}.period`)) || 'month' } catch { return 'month' } })
  const query = halves ? { ...query0, period } : query0
  const [levels, setLevels] = useState(() => loadLevels(store, LV, defaults))
  const [nodes, setNodes] = useState({})          // JSON(path) -> {rows, total, level} | {err} | 'loading'
  const [open, setOpen] = useState(() => new Set())
  const [source, setSource] = useState(null)
  const [filters, setFilters] = useState(() => loadFilters(store))   // {level: [values]} - any field, in Rows or not
  const [editing, setEditing] = useState(null)          // {level, anchor} - the filter list open now
  // the saved version being viewed ('' = the live plan) - PlanVersions (2026-10-13); kept per browser
  const [version, setVersion] = useState(() => { try { return (versions && localStorage.getItem(`${store}.version`)) || '' } catch { return '' } })
  const qx = JSON.stringify(query)
  const fkey = JSON.stringify(filters)
  // header sort (user, 2026-10-15: "sort functions in all headers where such tables exist"): {k: name|ly|ty|gr|cont, d: 1 / -1}
  // or null = the plan's own order; sorts the rows inside every branch (the tree stays), kept per browser
  const [sort, setSort] = useState(() => { try { return JSON.parse(localStorage.getItem(`${store}.sort`) || 'null') } catch { return null } })
  const pickSort = k => setSort(s => {
    const first = k === 'name' ? 1 : -1   // names A to Z first, numbers largest first; a third click = the plan's order
    const n = !s || s.k !== k ? { k, d: first } : s.d === first ? { k, d: -first } : null
    try { localStorage.setItem(`${store}.sort`, JSON.stringify(n)) } catch { /* ignore */ }
    return n
  })
  const sorted = (rows, parentTy) => {
    if (!sort) return rows
    const v = r => sort.k === 'name' ? String(r.key) : sort.k === 'ly' ? r.ly : sort.k === 'ty' ? r.ty
      : sort.k === 'gr' ? (gr(r.ty, r.ly) ?? -Infinity) : (parentTy ? r.ty / parentTy : 0)
    return [...rows].sort((a, b) => { const x = v(a), y = v(b); return (typeof x === 'string' ? x.localeCompare(y, undefined, { numeric: true }) : x - y) * sort.d })
  }
  const [why, setWhy] = useState(null)            // path of the row whose numbers are being explained
  const back = useRef(null)                       // the ⓘ that opened it - focus goes back there on close
  const lastLv = useRef(null)
  const drag = useRef(null)                       // index of the field being dragged in the Rows bar
  const info = p => (
    <button type="button" onClick={e => { back.current = e.currentTarget; setWhy(p) }} aria-label={`How ${p.length ? p[p.length - 1] : 'the total'} is made`} title="How is this number made?"
      style={{ all: 'unset', cursor: 'pointer', marginLeft: 6, fontSize: 12, color: theme.primary, padding: '0 3px' }}>ⓘ</button>
  )

  const fetchNode = path => {
    const k = JSON.stringify(path)
    setNodes(n => ({ ...n, [k]: 'loading' }))
    const qs = new URLSearchParams({ levels: levels.join(','), path: k, filters: fkey, version, ...query })
    fetch(`${api}/hierarchy?${qs}`)
      .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j })
      .then(j => { setNodes(n => ({ ...n, [k]: j })); if (j.source) setSource(j.source) })
      .catch(e => setNodes(n => ({ ...n, [k]: { err: e.message } })))
  }

  // a new hierarchy starts again from the top; new filters keep the open branches open (each re-fetched at once)
  useEffect(() => {
    try { localStorage.setItem(`${store}.hierarchy`, JSON.stringify(levels)); localStorage.setItem(`${store}.filters`, fkey); if (versions) localStorage.setItem(`${store}.version`, version); if (halves) localStorage.setItem(`${store}.period`, period) } catch { /* ignore */ }
    const lv = levels.join(',') + '|' + version + '|' + qx, same = lastLv.current === lv
    lastLv.current = lv
    setNodes({})
    if (!same) setOpen(new Set())
    fetchNode([])
    if (same) open.forEach(k => fetchNode(JSON.parse(k)))
  }, [levels.join(','), fkey, version, qx])   // eslint-disable-line react-hooks/exhaustive-deps
  // opening a version brings back its plan and the Rows / Filters it was saved with
  const openVersion = v => {
    setVersion(v ? v.id : '')
    if (v?.view?.levels?.length && v.view.levels.every(x => LV[x])) setLevels(v.view.levels)
    if (v?.view?.filters) setFilters(v.view.filters)
  }
  // a version opened from the header picker or a Home tile (planVersion.js, 2026-10-14)
  useEffect(() => {
    if (!versions) return
    const h = e => openVersion(e.detail)
    window.addEventListener('sp-version', h)
    return () => window.removeEventListener('sp-version', h)
  }, [versions])   // eslint-disable-line react-hooks/exhaustive-deps
  // the month filter follows the switch: Mar'27 <-> Mar'27 P1 + Mar'27 P2
  const switchPeriod = p => {
    if (p === period) return
    setFilters(f => {
      if (!f.month) return f
      const m = p === 'half' ? f.month.flatMap(x => (/ P[12]$/.test(x) ? [x] : [`${x} P1`, `${x} P2`])) : [...new Set(f.month.map(x => x.replace(/ P[12]$/, '')))]
      return { ...f, month: m }
    })
    setPeriod(p)
  }
  const exportXlsx = () => window.open(`${api}/hierarchy-export?${new URLSearchParams({ levels: levels.join(','), filters: fkey, version, ...query })}`, '_blank')
  const setFilter = (lv, vals) => setFilters(f => { const n = { ...f }; if (vals && vals.length) n[lv] = vals; else delete n[lv]; return n })

  const toggle = path => {
    const k = JSON.stringify(path)
    setOpen(o => { const n = new Set(o); n.has(k) ? n.delete(k) : n.add(k); return n })
    if (!nodes[k]) fetchNode(path)
  }
  const moveTo = (from, to) => setLevels(l => { const n = [...l]; const [x] = n.splice(from, 1); n.splice(to, 0, x); return n })
  const unused = Object.keys(LV).filter(x => !levels.includes(x))

  const mini = { all: 'unset', cursor: 'pointer', padding: '0 3px', color: theme.textMuted, fontSize: 12 }
  const th = { padding: '8px 12px', fontSize: 11, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.4, textAlign: 'right', borderBottom: `1px solid ${theme.border}`, background: theme.surfaceAlt }
  const td = { padding: '6px 12px', fontSize: 12.5, textAlign: 'right', fontFamily: theme.fontMono, borderBottom: `1px solid ${theme.border}`, whiteSpace: 'nowrap' }
  const field = { display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 4px 3px 8px', borderRadius: 4, border: `1px solid ${theme.border}`,
    background: theme.surface, fontSize: 12, fontWeight: 600, color: theme.textPrimary, cursor: 'grab', userSelect: 'none' }

  const renderRows = (path, depth) => {
    const node = nodes[JSON.stringify(path)]
    if (!node || node === 'loading') return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', paddingLeft: 16 + depth * 22, color: theme.textMuted }}>Loading…</td></tr>
    if (node.err) return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', paddingLeft: 16 + depth * 22, color: theme.danger }}>{node.err}</td></tr>
    if (!node.rows.length && depth === 0) return <tr><td colSpan={5} style={{ ...td, textAlign: 'left', color: theme.textMuted }}>Nothing inside these filters.</td></tr>
    const parentTy = node.total?.ty || 0
    return sorted(node.rows, parentTy).map(r => {
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
              <span style={{ marginLeft: 8, fontSize: 10.5, color: theme.textMuted, fontWeight: 400 }}>{LV[node.level]}</span>
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
  // Excel's report-filter caption: (All), the one value, or (Multiple Items)
  const caption = lv => (!filters[lv] ? '(All)' : filters[lv].length === 1 ? filters[lv][0] : `(Multiple Items) ${filters[lv].length}`)
  return (
    <div>
      {versions && <PlanVersions version={version} onOpen={openVersion} view={{ levels, filters }} />}
      {/* Excel's PivotTable Rows area - view controls, not plan edits: kept out of the suite's Undo */}
      <div data-no-undo style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '10px 16px', marginBottom: 14 }}>
        <div role="list" aria-label="Row fields" style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginRight: 4 }}>Rows</span>
          {levels.map((x, i) => (
            <Fragment key={x}>
              {i > 0 && <span aria-hidden="true" style={{ color: theme.textMuted, fontSize: 11 }}>›</span>}
              <span style={field} draggable tabIndex={0} role="listitem"
                aria-label={`${LV[x]}, row field ${i + 1} of ${levels.length}. Alt+Left or Alt+Right to move`}
                title="Drag to change the order (Alt+← / Alt+→)"
                onDragStart={e => { drag.current = i; e.dataTransfer.effectAllowed = 'move' }}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = drag.current; drag.current = null; if (f != null && f !== i) moveTo(f, i) }}
                onKeyDown={e => {
                  if (e.altKey && e.key === 'ArrowLeft' && i > 0) { e.preventDefault(); moveTo(i, i - 1) }
                  if (e.altKey && e.key === 'ArrowRight' && i < levels.length - 1) { e.preventDefault(); moveTo(i, i + 1) }
                }}>
                <span aria-hidden="true" style={{ color: theme.textMuted, fontSize: 10 }}>⠿</span>
                {LV[x]}
                <button type="button" style={mini} disabled={levels.length === 1} onClick={() => setLevels(l => l.filter(y => y !== x))} aria-label={`Remove ${LV[x]}`} title="Remove from Rows">✕</button>
              </span>
            </Fragment>
          ))}
          {unused.length > 0 && (
            <select value="" onChange={e => e.target.value && setLevels(l => [...l, e.target.value])} aria-label="Add a field to Rows"
              style={{ padding: '3px 6px', borderRadius: 4, border: `1px dashed ${theme.border}`, fontSize: 12, background: theme.surface }}>
              <option value="">+ Add field</option>
              {unused.map(x => <option key={x} value={x}>{LV[x]}</option>)}
            </select>
          )}
          <span style={{ flex: 1 }} />
          {halves && (
            <div role="group" aria-label="Months by" style={{ display: 'inline-flex', border: `1px solid ${theme.border}`, borderRadius: 6, overflow: 'hidden' }}>
              {[['month', 'Month'], ['half', 'P1 / P2']].map(([k, t]) => (
                <button key={k} type="button" aria-pressed={period === k} onClick={() => switchPeriod(k)}
                  title={k === 'half' ? 'Each month as its two fortnights: P1 = days 1–15, P2 = 16th to month end' : 'Whole months'}
                  style={{ padding: '3px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', border: 'none',
                           background: period === k ? 'var(--st-btn,#A8CBB7)' : theme.surface, color: period === k ? 'var(--st-btn-text,#1F4D3A)' : theme.textMuted }}>{t}</button>
              ))}
            </div>
          )}
          <button type="button" onClick={exportXlsx} title="This view - Rows, filters and months as set here - with every branch opened"
            style={{ padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', border: `1px solid ${theme.border}`, background: theme.surface, color: theme.textPrimary }}>Export Excel ↓</button>
          <button type="button" onClick={() => setLevels(defaults)} style={{ ...mini, textDecoration: 'underline' }}>Reset</button>
        </div>
        {/* one multi-select filter per field, as an Excel PivotTable's report filters (user, 2026-10-13: "multi selection
            filters are required") - each ticks any number of values; all of them apply together */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginRight: 4 }}>Filters</span>
          {Object.keys(LV).map(lv => (
            <button key={lv} type="button" aria-haspopup="dialog" onClick={e => { const el = e.currentTarget; setEditing(x => (x && x.level === lv ? null : { level: lv, anchor: el })) }}
              title={filters[lv] ? filters[lv].join(', ') : `All ${LV[lv].toLowerCase()}s`}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 8px', borderRadius: 4, fontSize: 12, cursor: 'pointer', maxWidth: 260,
                       border: `1px solid ${filters[lv] ? theme.primary : theme.border}`, background: filters[lv] ? alpha(theme.primary, '12') : theme.surface, color: theme.textPrimary }}>
              <span style={{ color: theme.textMuted }}>{LV[lv]}</span>
              <b style={{ fontWeight: filters[lv] ? 700 : 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{caption(lv)}</b>
              <span aria-hidden="true" style={{ color: theme.textMuted, fontSize: 10 }}>▾</span>
            </button>
          ))}
          {nF > 0 && <button type="button" onClick={() => setFilters({})} style={{ ...mini, textDecoration: 'underline' }}>Clear all</button>}
        </div>
        <div style={{ fontSize: 11.5, color: theme.textMuted, marginTop: 6 }}>
          View only · ₹ lakh · {halves && period === 'half' ? (levels.includes('month') ? 'by fortnight - P1 = days 1–15, P2 = 16th to month end' : 'all plan months added up') : levels.includes('month') ? 'by month' : 'all plan months added up'} · Cont % = share of the level above · ⓘ = how a row's numbers are made
          {source && <> · from {source.note || source.name}</>}
        </div>
      </div>
      <div style={{ background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr>
            {[['name', levels.map(x => LV[x]).join(' › ')], ['ly', cols.ly], ['ty', cols.ty], ['gr', cols.growth], ['cont', 'Cont %']].map(([k, t]) => {
              const on = sort?.k === k
              return (
                <th key={k} aria-sort={on ? (sort.d > 0 ? 'ascending' : 'descending') : 'none'} style={{ ...th, ...(k === 'name' ? { textAlign: 'left' } : {}), padding: 0 }}>
                  <button type="button" onClick={() => pickSort(k)} data-no-undo
                    title={on ? (sort.d === (k === 'name' ? 1 : -1) ? 'Sorted - click to reverse' : 'Click for the plan’s own order') : `Sort by ${t}`}
                    style={{ all: 'unset', boxSizing: 'border-box', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, width: '100%', padding: '8px 12px',
                             justifyContent: k === 'name' ? 'flex-start' : 'flex-end', color: on ? theme.textPrimary : 'inherit' }}>
                    {t}<span aria-hidden="true" style={{ fontSize: 9, opacity: on ? 1 : 0.35 }}>{on ? (sort.d > 0 ? '▲' : '▼') : '⇅'}</span>
                  </button>
                </th>
              )
            })}
          </tr></thead>
          <tbody>
            {renderRows([], 0)}
            {root && root !== 'loading' && !root.err && (
              <tr style={{ fontWeight: 700 }}>
                <td style={{ ...td, textAlign: 'left', fontFamily: 'inherit' }}>Grand Total{info([])}</td>
                <td style={td}>{L(root.total.ly)}</td><td style={td}>{L(root.total.ty)}</td>
                <td style={td}>{P(gr(root.total.ty, root.total.ly))}</td><td style={td}>100%</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {editing && <ExcelFilter key={editing.level + fkey} title={LV[editing.level]} anchor={editing.anchor} picked={filters[editing.level]}
        load={() => fetch(`${api}/hierarchy-options?${new URLSearchParams({ level: editing.level, filters: fkey, version, ...query })}`)
          .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`); return j[editing.level] || [] })}
        onDone={vals => { if (vals !== undefined) setFilter(editing.level, vals); setEditing(null) }} />}
      {why && <Explain key={JSON.stringify(why) + fkey + version + qx} api={api} LV={LV} query={query} cols={cols} levels={levels} path={why} filters={filters} version={version} onClose={() => { setWhy(null); back.current?.focus() }} />}
    </div>
  )
}
