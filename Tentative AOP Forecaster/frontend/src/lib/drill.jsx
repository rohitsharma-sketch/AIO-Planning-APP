// Shared drill-down (pivot-tree) engine used by OutputTab. Was also used by
// StoreDrillTable (Summary tab's own drill table, removed 2026-09-22 as a
// duplicate of this one) - the CSS import below stays since OutputTab's
// table still reuses those .sdt-* classes.
import { useState, useEffect, useRef } from 'react'
import { TYPES } from './tags'
import '../components/StoreDrillTable.css'

// Hierarchy (pivot row fields), top → bottom
export const LEVELS = [
  { key: 'Type',     label: 'Type'     },
  { key: 'Tag',      label: 'Tag'      },
  { key: 'Cluster',  label: 'Cluster'  },
  { key: 'Store',    label: 'Store'    },
  { key: 'Division', label: 'Division' },
]
export const LEVEL_KEYS = LEVELS.map(l => l.key)
export const EMPTY_DIM  = { Type: [], Tag: [], Cluster: [], Store: [], Division: [] }
export const ALL_IDX    = [...Array(13).keys()]

export const fmt1   = v => v == null ? '—' : v.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
export const fmtDev = v => v == null ? '—' : (v > 0 ? '+' : '') + fmt1(v)
export const fmtPct = v => v == null ? 'new' : (v > 0 ? '+' : '') + v.toFixed(1) + '%'
export const cmpStr = (a, b) => String(a).localeCompare(String(b), undefined, { numeric: true })

// ── Aggregation ────────────────────────────────────────────────────────────
// `idx` = month indexes included in the scalar totals (base/fcst/dev). Month arrays stay full-length.
export function aggregate(leaves, idx = ALL_IDX) {
  const mb = new Array(13).fill(0), m = new Array(13).fill(0), e = new Array(13).fill(0)   // e = Eff Sales (Output)
  const storesByType = { LfL: new Set(), Ramp: new Set(), NSO: new Set() }
  const stores = new Set()
  for (const r of leaves) {
    stores.add(r.Store); storesByType[r.Type]?.add(r.Store)
    for (let i = 0; i < 13; i++) { mb[i] += r.mb[i]; m[i] += r.m[i]; if (r.e) e[i] += r.e[i] }
  }
  let base = 0, fcst = 0
  for (const i of idx) { base += mb[i]; fcst += m[i] }
  return {
    base, fcst, dev: fcst - base, mb, m, e,
    stores: stores.size,
    typeCounts: Object.fromEntries(TYPES.map(t => [t, storesByType[t].size])),
    // Forecast (incl. the ref-store deviation layer) vs Base - the same growth
    // as the Summary tab and BIS (2026-09-25). The engine-only growth shown here
    // before left the deviation out and never matched BIS.
    growth: base > 0 ? (fcst / base - 1) * 100 : null,
  }
}

export function buildTree(leaves, levels, idx = ALL_IDX, depth = 0, path = '') {
  if (depth >= levels.length || !leaves.length) return []
  const key = levels[depth]
  const groups = new Map()
  for (const r of leaves) {
    const k = r[key]
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k).push(r)
  }
  return [...groups].map(([name, rs]) => {
    const id = `${path}/${name}`
    return { id, name, level: key, depth, ...aggregate(rs, idx), children: buildTree(rs, levels, idx, depth + 1, id) }
  })
}

// val(node) → string | number | null. Nulls always sort last.
export function sortTree(nodes, val, dir) {
  const sorted = [...nodes].sort((a, b) => {
    const va = val(a), vb = val(b)
    if (typeof va === 'string' || typeof vb === 'string') return dir * cmpStr(va ?? '', vb ?? '')
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    return dir * (va - vb)
  })
  return sorted.map(n => ({ ...n, children: sortTree(n.children, val, dir) }))
}

export function flatten(nodes, expanded, out = []) {
  for (const n of nodes) {
    out.push(n)
    if (n.children.length && expanded.has(n.id)) flatten(n.children, expanded, out)
  }
  return out
}
export function allIds(nodes, maxDepth = Infinity, out = []) {
  for (const n of nodes) {
    if (n.depth < maxDepth && n.children.length) { out.push(n.id); allIds(n.children, maxDepth, out) }
  }
  return out
}

// Distinct values + counts per dimension (for the header filter dropdowns)
export function dimOptions(leaves, keys = LEVEL_KEYS) {
  const out = {}
  for (const k of keys) {
    const c = new Map()
    for (const r of leaves) c.set(r[k], (c.get(r[k]) || 0) + 1)
    out[k] = [...c].map(([value, count]) => ({ value, count })).sort((a, b) => cmpStr(a.value, b.value))
  }
  return out
}

// Apply header dimension filters, free-text search and numeric (store-total) range filters.
// numF: { [key]: {min,max} } where key ∈ metric names returned by aggregate() (base, fcst, dev, growth).
export function filterLeaves(leaves, { dimF = EMPTY_DIM, search = '', numF = {}, idx = ALL_IDX, keys = LEVEL_KEYS } = {}) {
  let rs = leaves
  for (const k of keys) if (dimF[k]?.length) rs = rs.filter(r => dimF[k].includes(r[k]))
  const q = search.trim().toLowerCase()
  if (q) rs = rs.filter(r => LEVEL_KEYS.some(k => String(r[k]).toLowerCase().includes(q)))
  const numKeys = Object.keys(numF).filter(k => numF[k].min !== '' || numF[k].max !== '')
  if (numKeys.length) {
    const byStore = new Map()
    for (const r of rs) { if (!byStore.has(r.Store)) byStore.set(r.Store, []); byStore.get(r.Store).push(r) }
    const ok = new Set()
    for (const [s, srs] of byStore) {
      const a = aggregate(srs, idx)
      const pass = numKeys.every(k => {
        const { min, max } = numF[k], v = a[k]
        if (v == null) return false
        return (min === '' || v >= +min) && (max === '' || v <= +max)
      })
      if (pass) ok.add(s)
    }
    rs = rs.filter(r => ok.has(r.Store))
  }
  return rs
}

export const hasNum = f => f && (f.min !== '' || f.max !== '')

// ── Excel-pivot style column filter (position: fixed so it escapes the scroll box) ──
export function HeaderFilter({ title, options, selected, onChange, range, onRange, onClose, anchor, hint }) {
  const [q, setQ] = useState('')
  const ref = useRef(null)
  useEffect(() => {
    const h = e => { if (ref.current && !ref.current.contains(e.target)) onClose() }
    const k = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', h); document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [onClose])

  const style = { top: anchor.bottom + 4, left: Math.max(8, Math.min(anchor.left, window.innerWidth - 300)) }

  if (range) {
    return (
      <div className="sdt-dd" ref={ref} style={style}>
        <div className="sdt-dd-head"><span>{title}</span>
          {hasNum(range) && <button className="sdt-dd-clear" onClick={() => onRange({ min: '', max: '' })}>Clear</button>}
        </div>
        <div className="sdt-dd-range">
          <label>Min <input type="number" autoFocus value={range.min} onChange={e => onRange({ ...range, min: e.target.value })} placeholder="any" /></label>
          <label>Max <input type="number" value={range.max} onChange={e => onRange({ ...range, max: e.target.value })} placeholder="any" /></label>
        </div>
        <div className="sdt-dd-hint">{hint || 'Applies to store totals'}</div>
      </div>
    )
  }

  const visible = options.filter(o => o.value.toLowerCase().includes(q.toLowerCase()))
  const allOn   = selected.length === 0
  const isOn    = v => allOn || selected.includes(v)
  const current = () => selected.length ? selected : options.map(o => o.value)
  const commit  = next => onChange(next.length === options.length ? [] : next)
  const toggle  = v => { const cur = current(); commit(cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v]) }
  const only    = v => onChange(selected.length === 1 && selected[0] === v ? [] : [v])
  const toggleAllVisible = () => {
    if (!q) return onChange(allOn ? [' none'] : [])
    const vis = visible.map(o => o.value)
    const cur = current()
    commit(vis.every(isOn) ? cur.filter(x => !vis.includes(x)) : [...new Set([...cur, ...vis])])
  }
  const allVisibleOn = q ? visible.length > 0 && visible.every(o => isOn(o.value)) : allOn

  return (
    <div className="sdt-dd" ref={ref} style={style}>
      <div className="sdt-dd-head"><span>{title}</span>
        {!allOn && <button className="sdt-dd-clear" onClick={() => onChange([])}>Clear</button>}
      </div>
      <input className="sdt-dd-search" autoFocus placeholder="Search…" value={q} onChange={e => setQ(e.target.value)} />
      <div className="sdt-dd-list">
        <div className="sdt-dd-row sdt-dd-all" onClick={toggleAllVisible}>
          <span className="sdt-cb">{allVisibleOn ? '[x]' : '[ ]'}</span>
          <span>{q ? '(Select All Search Results)' : '(Select All)'}</span>
        </div>
        {visible.map(o => (
          <div key={o.value} className={`sdt-dd-row${isOn(o.value) ? '' : ' off'}`}>
            <span className="sdt-cb" onClick={() => toggle(o.value)}>{isOn(o.value) ? '[x]' : '[ ]'}</span>
            <span className="sdt-dd-label" onClick={() => only(o.value)} title="Click to select only this">{o.value}</span>
            <span className="sdt-dd-count">{o.count}</span>
          </div>
        ))}
        {!visible.length && <div className="sdt-dd-empty">No matches</div>}
      </div>
      <div className="sdt-dd-hint">Checkbox = toggle · Label = only this</div>
    </div>
  )
}

// Sortable (optionally filterable) header cell. `sub` renders a second line (e.g. month / metric).
export function Th({ col, label, sub, num, filterable, sortCol, sortDir, toggleSort, hasFilter, openF, className = '' }) {
  const sorted = sortCol === col
  return (
    <th className={`${num ? 'num' : ''}${sorted ? ' sorted' : ''} ${className}`}>
      <div className="sdt-th">
        <button className="sdt-th-sort" onClick={() => toggleSort(col)} title="Sort">
          <span className="sdt-th-text">
            {sub ? <><div className="sdt-th-l1">{label}</div><div className="sdt-th-l2">{sub}</div></> : label}
          </span>
          <span className={`sdt-sort-ic${sorted ? ' on' : ''}`}>{sorted ? (sortDir < 0 ? 'v' : '^') : '^v'}</span>
        </button>
        {filterable && <button className={`sdt-th-filter${hasFilter?.(col) ? ' on' : ''}`} onClick={e => openF(col, e)} title="Filter">v</button>}
      </div>
    </th>
  )
}

// Dimension-filter header buttons (Type ▼ … Division ▼)
export function DimFilterHeaders({ hasFilter, openF }) {
  return LEVELS.map(l => (
    <th key={l.key} className="sdt-dim-th">
      <button className={`sdt-th-filter sdt-dim-filter${hasFilter(l.key) ? ' on' : ''}`} onClick={e => openF(l.key, e)} title={`Filter ${l.label}`}>
        {l.label} v
      </button>
    </th>
  ))
}

// Levels / Expand-to toolbar segment
export function DrillToolbar({ levels, toggleLevel, expandTo, collapse, lockedFirst }) {
  return (
    <>
      <div className="sdt-levels">
        <span className="sdt-tb-label">Levels</span>
        {LEVELS.map(l => (
          <button key={l.key} className={`sdt-chip${levels.includes(l.key) ? ' on' : ''}`}
                  disabled={lockedFirst === l.key} title={lockedFirst === l.key ? 'Fixed as top level in this view' : ''}
                  onClick={() => toggleLevel(l.key)}>{l.label}</button>
        ))}
      </div>
      <div className="sdt-expand">
        <span className="sdt-tb-label">Expand to</span>
        {levels.map((k, i) => <button key={k} className="sdt-chip" onClick={() => expandTo(i)} title={`Show down to ${k}`}>{i + 1}</button>)}
        <button className="sdt-chip" onClick={() => expandTo(Infinity)}>All</button>
        <button className="sdt-chip" onClick={collapse}>Collapse</button>
      </div>
    </>
  )
}

// Common drill view-state + handlers. The caller builds the tree (it depends on dimF/levels/sort
// returned here) and passes it back into the tree-aware helpers.
export function useDrill({ defaultSort = 'fcst', resetKey } = {}) {
  const [levels, setLevels]     = useState(LEVEL_KEYS)
  const [expanded, setExpanded] = useState(null)          // null → top level auto-expanded
  const [sortCol, setSortCol]   = useState(defaultSort)
  const [sortDir, setSortDir]   = useState(-1)
  const [dimF, setDimF]         = useState(EMPTY_DIM)
  const [openFilter, setOpenFilter] = useState(null)      // { col, anchor }

  useEffect(() => { setExpanded(null); setDimF(EMPTY_DIM); setOpenFilter(null) }, [resetKey])

  const expandedFor = tree => expanded ?? new Set(tree.map(n => n.id))
  const toggleNode  = (tree, id) => { const n = new Set(expandedFor(tree)); n.has(id) ? n.delete(id) : n.add(id); setExpanded(n) }
  const expandTo    = (tree, d)  => setExpanded(new Set(allIds(tree, d)))
  const collapse    = () => setExpanded(new Set())
  const toggleLevel = k  => setLevels(ls => {
    const next = ls.includes(k) ? ls.filter(x => x !== k) : LEVEL_KEYS.filter(x => ls.includes(x) || x === k)
    return next.length ? next : ls
  })
  const toggleSort = col => { if (sortCol === col) setSortDir(d => -d); else { setSortCol(col); setSortDir(col === 'name' ? 1 : -1) } }
  const openF = (col, e) => {
    e.stopPropagation()
    const anchor = e.currentTarget.getBoundingClientRect()
    setOpenFilter(o => o?.col === col ? null : { col, anchor })
  }
  const closeF = () => setOpenFilter(null)
  return { levels, setLevels, toggleLevel, expandedFor, toggleNode, expandTo, collapse,
           sortCol, setSortCol, sortDir, setSortDir, toggleSort, dimF, setDimF, openFilter, openF, closeF }
}
