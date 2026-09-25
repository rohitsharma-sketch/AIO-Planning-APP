import { useState, useEffect, useRef, useMemo } from 'react'
import './OutputTab.css'
import { tagClass, MONTHS, toLeaf } from '../lib/tags'
import { apiUrl } from '../lib/apiBase'
import { useVisibleMonths } from '../lib/horizon'
import { LEVELS, LEVEL_KEYS, EMPTY_DIM, aggregate, buildTree, sortTree, flatten, dimOptions, filterLeaves, HeaderFilter, useDrill } from '../lib/drill'

const DIVS = ["GM","KIDS","LADIES","MENS","RETAIL"]
const TAGS = ["LfL","Ramp","NSO"]
const PAGE_SIZE = 50

const DIV_COLORS = { GM:'#334155', KIDS:'#A16207', LADIES:'#9D174D', MENS:'#0F766E', RETAIL:'#5B21B6' }
const TAG_COLORS = { LfL:'#3D5AD6', Ramp:'#B45309', NSO:'#15803D' }  // = .tag-* chips / Summary charts

function fmt1(v) {
  if (v == null) return '—'
  return v.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}
function fmtDev(v) {
  if (v == null) return '—'
  const s = v.toLocaleString('en-IN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  return v > 0 ? '+' + s : s
}

// ── Multi-select dropdown — Excel pivot style ─────────────────────
// • Click checkbox  → toggle that item (multi-select)
// • Click item label → exclusive select (only that item)
// • (Select All) row → all on/off
// • selected=[] means "all" (no filter applied)
function MultiSelect({ label, options, selected, onChange, colorMap, width }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handler(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const allSelected = selected.length === 0 || selected.length === options.length
  const display = (selected.length === 0 || selected.length === options.length)
    ? `All`
    : selected.length === 1 ? selected[0]
    : `${selected.length} items`

  // Checkbox toggle (multi-select)
  function toggleCheck(opt, e) {
    e.stopPropagation()
    const next = selected.includes(opt)
      ? selected.filter(x => x !== opt)
      : [...selected, opt]
    // Empty selection = "All"
    onChange(next.length === options.length ? [] : next)
  }

  // Label click = exclusive select (only this item)
  function selectOnly(opt, e) {
    e.stopPropagation()
    // If already the sole selection, reset to All
    if (selected.length === 1 && selected[0] === opt) {
      onChange([])
    } else {
      onChange([opt])
    }
  }

  // (Select All) row checkbox
  function toggleAll(e) {
    e.stopPropagation()
    onChange([])
  }

  const isChecked = (opt) => selected.length === 0 || selected.includes(opt)

  return (
    <div className="ms-wrap" ref={ref} style={width ? { minWidth: width } : {}}>
      <button
        className={`ms-trigger${!allSelected ? ' has-sel' : ''}`}
        onClick={() => setOpen(o => !o)}
      >
        <span className="ms-label-text">{label}</span>
        <span className={`ms-val${!allSelected ? ' ms-val--active' : ''}`}>{display}</span>
        {!allSelected && (
          <span className="ms-sel-badge">{selected.length}</span>
        )}
        <span className="ms-caret">{open ? '^' : 'v'}</span>
      </button>
      {open && (
        <div className="ms-dropdown">
          <div className="ms-pv-header">
            <span className="ms-pv-title">{label}</span>
            {!allSelected && (
              <button className="ms-pv-clear" onClick={() => onChange([])}>Clear</button>
            )}
          </div>
          {/* Search hint for larger lists */}
          <div className="ms-pv-options">
            {/* (Select All) row */}
            <div
              className={`ms-pv-row ms-pv-all${allSelected ? ' ms-pv-row--checked' : ''}`}
              onClick={toggleAll}
            >
              <span className={`ms-pv-cb${allSelected ? ' ms-pv-cb--on' : ''}`} />
              <span className="ms-pv-row-label">(Select All)</span>
            </div>
            <div className="ms-pv-divider" />
            {options.map(opt => {
              const checked = isChecked(opt)
              const exclusive = selected.length === 1 && selected[0] === opt
              return (
                <div
                  key={opt}
                  className={`ms-pv-row${checked ? ' ms-pv-row--checked' : ''}${exclusive ? ' ms-pv-row--only' : ''}`}
                >
                  {/* Checkbox — multi-toggle */}
                  <span
                    className={`ms-pv-cb${checked ? ' ms-pv-cb--on' : ''}`}
                    onClick={e => toggleCheck(opt, e)}
                  />
                  {/* Color dot */}
                  {colorMap?.[opt] && (
                    <span className="ms-dot" style={{ background: colorMap[opt] }} />
                  )}
                  {/* Label — exclusive select */}
                  <span className="ms-pv-row-label" onClick={e => selectOnly(opt, e)}>
                    {opt}
                  </span>
                  {exclusive && <span className="ms-pv-only-tag">only</span>}
                </div>
              )
            })}
          </div>
          <div className="ms-pv-footer">
            <span className="ms-pv-hint">Checkbox = multi-select · label = only</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Pivot Output (2026-09-25, user: "combine the output summary into one,
// make the headers expandable and collapsable on click, … a drag and drop
// panel like we do it in excel pivot … keep everything on a month and total
// rollup with gr% for all") ──────────────────────────────────────────────
// One table replaces Store summary / Monthly detail / Division rollup:
//  • rows    = the Rows fields in order (drag to reorder / add / remove);
//              the header breadcrumb expands/collapses the table by level
//  • columns = every shown month (rule 1, lib/horizon) grouped in quarters
//              (click a quarter band to collapse it into one column) + Total
//  • values  = Stores / Base / Forecast / Deviation (toggle) + Growth % always
const VALUE_DEFS = {
  stores: { label: 'Stores',    short: 'Stores' },
  base:   { label: 'Base',      short: 'Base' },
  fcst:   { label: 'Forecast',  short: 'Fcst' },
  dev:    { label: 'Deviation', short: 'Dev' },
  gr:     { label: 'Growth %',  short: 'Gr%', locked: true },
}
const VALUE_KEYS = Object.keys(VALUE_DEFS)
const DEFAULT_LAYOUT = { rows: LEVEL_KEYS, values: ['base', 'fcst', 'gr'], unit: 'L', collapsedQ: [] }
const QTR_DEF = [['Q1', [1, 2, 3]], ['Q2', [4, 5, 6]], ['Q3', [7, 8, 9]], ['Q4', [10, 11, 12]]]   // MONTHS idx; 0 = Mar'27
const LAYOUT_KEY = 'aop.output.pivotLayout'

function loadLayout() {
  try {
    const l = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null')
    if (!l) return DEFAULT_LAYOUT
    const rows = (l.rows || []).filter(k => LEVEL_KEYS.includes(k))
    const values = (l.values || []).filter(k => VALUE_KEYS.includes(k))
    return { rows: rows.length ? rows : LEVEL_KEYS, values: values.includes('gr') ? values : [...values, 'gr'],
             unit: l.unit === 'Cr' ? 'Cr' : 'L', collapsedQ: Array.isArray(l.collapsedQ) ? l.collapsedQ : [] }
  } catch { return DEFAULT_LAYOUT }
}

const sumIdx = (arr, idx) => idx.reduce((s, i) => s + (arr[i] || 0), 0)
function cellsFor(n, g) {
  const b = sumIdx(n.mb, g.idx), f = sumIdx(n.m, g.idx)
  return { stores: n.stores, base: b, fcst: f, dev: f - b, gr: b > 0 ? (f / b - 1) * 100 : null }
}
const fmtGr = v => (v == null ? 'new' : (v > 0 ? '+' : '') + v.toFixed(1) + '%')

export default function OutputTab({ sessionId, runKey }) {
  const [rows, setRows]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  // Filter bar
  const [divFilter, setDivFilter]     = useState([])
  const [tagFilter, setTagFilter]     = useState([])
  const [clusterFilter, setCluster]   = useState('')
  const [storeSearch, setStoreSearch] = useState('')

  // Pivot layout (remembered per browser)
  const [layout, setLayout] = useState(loadLayout)
  useEffect(() => { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)) } catch {} }, [layout])
  const { rows: rowFields, values: valueFields, unit } = layout
  const collapsedQ = useMemo(() => new Set(layout.collapsedQ), [layout.collapsedQ])
  const setL = patch => setLayout(l => ({ ...l, ...(typeof patch === 'function' ? patch(l) : patch) }))
  const [panelOpen, setPanelOpen] = useState(true)
  const [sort, setSort] = useState({ key: 'fcst', dir: -1 })     // Total-group value, or 'name'
  const [depth, setDepth] = useState(2)                           // levels shown (top level opens expanded)
  const [drag, setDrag] = useState(null)                          // { kind: 'row' | 'val', key }
  const [over, setOver] = useState(null)

  const VIS = useVisibleMonths()
  const VIS_IDX = useMemo(() => VIS.map(m => MONTHS.indexOf(m)), [VIS])
  const d = useDrill({ defaultSort: 'fcst', resetKey: runKey })

  useEffect(() => { setDivFilter([]); setTagFilter([]); setCluster(''); setStoreSearch(''); setDepth(2) }, [runKey])

  useEffect(() => {
    if (!sessionId) return
    setRows(null); setLoading(true); setError(null)
    fetch(apiUrl(`/api/data/${sessionId}`))
      .then(r => r.ok ? r.json() : r.json().then(e => { throw new Error(e.detail || 'Failed') }))
      .then(data => { setRows(data); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [sessionId, runKey])

  // ── Data pipeline ──────────────────────────────────────────────────────
  const leaves   = useMemo(() => (rows || []).map(r => toLeaf(r, 1)), [rows])          // ₹ Lakhs
  const clusters = useMemo(() => Array.from(new Set(leaves.map(r => r.Cluster).filter(c => c && c !== '—'))).sort(), [leaves])
  const options  = useMemo(() => dimOptions(leaves), [leaves])

  const barFiltered = useMemo(() => {
    let r = leaves
    if (divFilter.length)   r = r.filter(x => divFilter.includes(x.Division))
    if (tagFilter.length)   r = r.filter(x => tagFilter.includes(x.Type))
    if (clusterFilter)      r = r.filter(x => x.Cluster === clusterFilter)
    const q = storeSearch.trim().toLowerCase()
    if (q)                  r = r.filter(x => x.Store?.toLowerCase().includes(q))
    return r
  }, [leaves, divFilter, tagFilter, clusterFilter, storeSearch])
  const filtered = useMemo(() => filterLeaves(barFiltered, { dimF: d.dimF, idx: VIS_IDX }), [barFiltered, d.dimF, VIS_IDX])

  // Column groups: Mar'27, then quarter bands (months, or one column when collapsed), then Total
  const groups = useMemo(() => {
    const vis = new Set(VIS_IDX), out = []
    if (vis.has(0)) out.push({ key: 'm0', band: null, label: MONTHS[0], idx: [0] })
    for (const [q, ids] of QTR_DEF) {
      const inq = ids.filter(i => vis.has(i))
      if (!inq.length) continue
      const span = `${MONTHS[inq[0]].slice(0, 3)}–${MONTHS[inq[inq.length - 1]].slice(0, 3)}`
      if (collapsedQ.has(q)) out.push({ key: q, band: q, bandLabel: `${q} · ${span}`, label: `${q} total`, idx: inq, collapsed: true })
      else inq.forEach(i => out.push({ key: `m${i}`, band: q, bandLabel: `${q} · ${span}`, label: MONTHS[i], idx: [i] }))
    }
    out.push({ key: 'total', band: null, label: `Total · ${VIS[0]}–${VIS[VIS.length - 1]}`, idx: VIS_IDX, total: true })
    return out
  }, [VIS, VIS_IDX, collapsedQ])
  const totalGroup = groups[groups.length - 1]
  const valsFor = g => valueFields.filter(v => g.total || v !== 'stores')   // store count only in Total

  const tree = useMemo(() => {
    const val = n => (sort.key === 'name' ? n.name : cellsFor(n, totalGroup)[sort.key])
    return sortTree(buildTree(filtered, rowFields, VIS_IDX), val, sort.dir)
  }, [filtered, rowFields, VIS_IDX, sort, totalGroup])
  const grand = useMemo(() => aggregate(filtered, VIS_IDX), [filtered, VIS_IDX])
  const exp   = d.expandedFor(tree)
  const flat  = useMemo(() => flatten(tree, exp), [tree, exp])

  // ── Helpers ────────────────────────────────────────────────────────────
  const U = unit === 'Cr' ? 0.01 : 1
  const fmtVal = (v, key) => key === 'gr' ? fmtGr(v) : key === 'stores' ? v : key === 'dev' ? fmtDev(v * U) : fmt1(v * U)
  const clsVal = (v, key) => key === 'gr' ? (v == null ? 'muted' : v >= 0 ? 'positive' : 'negative')
    : key === 'dev' ? (v > 0 ? 'positive' : v < 0 ? 'negative' : '') : key === 'fcst' ? 'fw-bold' : ''
  const levelLabel = k => LEVELS.find(l => l.key === k).label
  const drillFilters = LEVEL_KEYS.filter(k => d.dimF[k].length).length
  const hasBarFilters = divFilter.length || tagFilter.length || clusterFilter || storeSearch
  const resetAll = () => { setDivFilter([]); setTagFilter([]); setCluster(''); setStoreSearch(''); d.setDimF(EMPTY_DIM) }

  // Breadcrumb header: click level i = show rows down to it; click the deepest
  // shown level again = collapse one level up. `depth` = number of levels shown.
  const crumbClick = i => {
    const target = depth === i + 1 ? i : i + 1
    if (target <= 1) { d.collapse(); setDepth(1) } else { d.expandTo(tree, target - 1); setDepth(target) }
  }
  const toggleQ = q => setL(l => ({ collapsedQ: l.collapsedQ.includes(q) ? l.collapsedQ.filter(x => x !== q) : [...l.collapsedQ, q] }))
  const sortBy = key => setSort(s => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === 'name' ? 1 : -1 }))

  // ── Drag & drop (field panel) ──────────────────────────────────────────
  const moveInto = (list, key, beforeKey) => {
    const without = list.filter(k => k !== key)
    const i = beforeKey && without.includes(beforeKey) ? without.indexOf(beforeKey) : without.length
    return [...without.slice(0, i), key, ...without.slice(i)]
  }
  const dropRows = beforeKey => {
    if (drag?.kind === 'row') setL(l => ({ rows: moveInto(l.rows, drag.key, beforeKey) }))
    setDrag(null); setOver(null)
  }
  const dropRowPool = () => {
    if (drag?.kind === 'row') setL(l => ({ rows: l.rows.length > 1 ? l.rows.filter(k => k !== drag.key) : l.rows }))
    setDrag(null); setOver(null)
  }
  const dropValues = beforeKey => {
    if (drag?.kind === 'val') setL(l => ({ values: moveInto(l.values, drag.key, beforeKey) }))
    setDrag(null); setOver(null)
  }
  const dropValPool = () => {
    if (drag?.kind === 'val' && !VALUE_DEFS[drag.key].locked) setL(l => ({ values: l.values.filter(k => k !== drag.key) }))
    setDrag(null); setOver(null)
  }
  const dz = (id, onDrop) => ({
    onDragOver: e => { e.preventDefault(); e.stopPropagation(); setOver(id) },
    onDragLeave: () => setOver(o => (o === id ? null : o)),
    onDrop: e => { e.preventDefault(); e.stopPropagation(); onDrop() },
  })
  const dragProps = (kind, key) => ({
    draggable: true,
    onDragStart: e => { setDrag({ kind, key }); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', key) },
    onDragEnd: () => { setDrag(null); setOver(null) },
  })

  // ── Export exactly what is shown ───────────────────────────────────────
  function exportCsv() {
    const cols = groups.flatMap(g => valsFor(g).map(v => [g, v]))
    const head = ['Row', 'Level', ...cols.map(([g, v]) => `${g.label} ${VALUE_DEFS[v].short}${v === 'gr' || v === 'stores' ? '' : ` (Rs ${unit})`}`)]
    const line = (label, level, n) => [label, level, ...cols.map(([g, v]) => {
      const c = cellsFor(n, g)[v]
      return c == null ? '' : v === 'gr' ? c.toFixed(1) : v === 'stores' ? c : (c * U).toFixed(2)
    })]
    const out = [head, line('Grand total', '', grand), ...flat.map(n => line(`${'  '.repeat(n.depth)}${n.name}`, n.level, n))]
    const csv = out.map(r => r.map(x => /[",\n]/.test(String(x)) ? `"${String(x).replace(/"/g, '""')}"` : x).join(',')).join('\r\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }))
    a.download = `AOP_output_${rowFields.join('-')}.csv`
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }

  const renderName = n => (
    <td className="sdt-name pv-sticky">
      <span className="sdt-indent" style={{ width: n.depth * 18 }} />
      <span className={`sdt-caret${!n.children.length ? ' none' : exp.has(n.id) ? ' open' : ''}`}>&gt;</span>
      {n.level === 'Division' ? <span className="div-pill" style={{ background: DIV_COLORS[n.name] }}>{n.name}</span>
     : n.level === 'Type'     ? <span className={`tag ${n.name === 'NSO' ? 'tag-nso' : n.name === 'Ramp' ? 'tag-ramp' : 'tag-lfl'}`}>{n.name}</span>
     : n.level === 'Tag'      ? <span className={`tag ${tagClass(n.name)}`}>{n.name}</span>
     : n.level === 'Store'    ? <span className="store-name">{n.name}</span>
     : <span className="cluster-cell">{n.name}</span>}
      <span className="sdt-level-hint">{n.level}</span>
    </td>
  )
  const valueCells = (n, bold) => groups.flatMap(g => {
    const c = cellsFor(n, g), vs = valsFor(g)
    return vs.map(v => (
      <td key={`${g.key}|${v}`} className={`num ${clsVal(c[v], v)} ${bold ? 'fw-bold' : ''} ${g.total ? 'pv-total' : ''} ${v === vs[0] ? 'pv-gstart' : ''}`}>
        {fmtVal(c[v], v)}
      </td>
    ))
  })

  // Header row 1: quarter bands (clickable) / stand-alone groups
  const bandCells = []
  for (let i = 0; i < groups.length; i++) {
    const g = groups[i]
    if (!g.band) {
      bandCells.push(<th key={g.key} rowSpan={2} colSpan={valsFor(g).length} className={`pv-group pv-gstart ${g.total ? 'pv-total-h' : ''}`}>{g.label}</th>)
      continue
    }
    let span = 0, j = i
    while (j < groups.length && groups[j].band === g.band) { span += valsFor(groups[j]).length; j++ }
    const collapsed = collapsedQ.has(g.band)
    bandCells.push(
      <th key={g.band} colSpan={span} className="pv-band pv-gstart">
        <button className="pv-band-btn" onClick={() => toggleQ(g.band)} title={collapsed ? 'Expand to months' : 'Collapse to one quarter column'}>
          <span className="pv-tw">{collapsed ? '▸' : '▾'}</span>{g.bandLabel}
        </button>
      </th>)
    i = j - 1
  }

  if (loading) return <div className="out-loading">Loading detail data…</div>
  if (error)   return <div className="out-error">Error: {error}</div>
  if (!rows)   return null

  const available = LEVEL_KEYS.filter(k => !rowFields.includes(k))
  const valuePool = VALUE_KEYS.filter(k => !valueFields.includes(k))

  return (
    <div className="out-wrap out-drill">

      {/* ── Filter bar ── */}
      <div className="out-filters card">
        <div className="out-filter-row">
          <MultiSelect label="Division"   options={DIVS} selected={divFilter} onChange={setDivFilter} colorMap={DIV_COLORS} />
          <MultiSelect label="Store Type" options={TAGS} selected={tagFilter} onChange={setTagFilter} colorMap={TAG_COLORS} width={130} />
          <div className="out-filter-sep" />
          <div className="out-cluster-wrap">
            <span className="out-inline-label">Cluster</span>
            <select className="out-select" value={clusterFilter} onChange={e => setCluster(e.target.value)}>
              <option value="">All</option>
              {clusters.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="out-search-wrap">
            <input className="out-search" placeholder="Search store…" value={storeSearch} onChange={e => setStoreSearch(e.target.value)} />
            {storeSearch && <button className="out-search-clear" onClick={() => setStoreSearch('')}>x</button>}
          </div>
          {(hasBarFilters || drillFilters > 0) && (
            <button className="out-reset-btn" onClick={resetAll}>Reset filters{drillFilters ? ` (${drillFilters} on fields)` : ''}</button>
          )}
          <span className="out-count">
            {grand.stores.toLocaleString()} <span className="out-count-label">stores</span> · {filtered.length.toLocaleString()} <span className="out-count-label">rows</span>
          </span>
        </div>
      </div>

      <div className={`pv-layout${panelOpen ? '' : ' pv-layout--closed'}`}>
        {/* ── Pivot table ── */}
        <div className="card out-table-card sdt-card pv-card">
          <div className="pv-toolbar">
            <span className="sdt-count">
              {flat.length} rows · ₹ {unit === 'Cr' ? 'Crore' : 'Lakhs'}
              {VIS.length < MONTHS.length ? ` · ${VIS[0]}–${VIS[VIS.length - 1]} shown (later months appear as their base month closes)` : ''}
            </span>
            <div className="pv-toolbar-actions">
              <div className="pv-seg" role="group" aria-label="Unit">
                {['L', 'Cr'].map(u => <button key={u} className={unit === u ? 'on' : ''} onClick={() => setL({ unit: u })}>₹ {u === 'L' ? 'Lakhs' : 'Crore'}</button>)}
              </div>
              <button className="btn-outline pv-btn" onClick={exportCsv}>Export view</button>
              <button className="btn-outline pv-btn" onClick={() => setPanelOpen(o => !o)} aria-expanded={panelOpen}>{panelOpen ? 'Hide fields' : 'Fields'}</button>
            </div>
          </div>

          <div className="table-scroll sdt-scroll">
            <table className="stores-table sdt-table pv-table">
              <thead>
                <tr>
                  <th rowSpan={3} className="pv-rowhead pv-sticky">
                    <div className="pv-crumbs">
                      {rowFields.map((k, i) => (
                        <span key={k} className="pv-crumb-wrap">
                          {i > 0 && <span className="pv-crumb-sep">›</span>}
                          <button className={`pv-crumb${i < depth ? ' on' : ''}`} onClick={() => crumbClick(i)}
                                  title={depth === i + 1 ? `Collapse ${levelLabel(k)}` : `Expand to ${levelLabel(k)}`}>
                            {levelLabel(k)}
                          </button>
                        </span>
                      ))}
                    </div>
                    <button className="pv-sortname" onClick={() => sortBy('name')}>Sort A–Z{sort.key === 'name' ? (sort.dir > 0 ? ' ↑' : ' ↓') : ''}</button>
                  </th>
                  {bandCells}
                </tr>
                <tr>
                  {groups.filter(g => g.band).map(g => (
                    <th key={g.key} colSpan={valsFor(g).length} className={`pv-month pv-gstart${g.collapsed ? ' pv-qcol' : ''}`}>{g.label}</th>
                  ))}
                </tr>
                <tr>
                  {groups.flatMap(g => { const vs = valsFor(g); return vs.map(v => (
                    <th key={`${g.key}|${v}`} className={`num pv-val ${v === vs[0] ? 'pv-gstart' : ''} ${g.total ? 'pv-total-h' : ''}`}>
                      {g.total
                        ? <button className="pv-valsort" onClick={() => sortBy(v)} title={`Sort by total ${VALUE_DEFS[v].label}`}>
                            {VALUE_DEFS[v].short}{sort.key === v ? (sort.dir < 0 ? ' ↓' : ' ↑') : ''}
                          </button>
                        : VALUE_DEFS[v].short}
                    </th>
                  )) })}
                </tr>
              </thead>
              <tbody>
                <tr className="sdt-grand">
                  <td className="sdt-name pv-sticky"><strong>Grand total</strong></td>
                  {valueCells(grand, true)}
                </tr>
                {flat.map(n => (
                  <tr key={n.id} className={`sdt-row d${n.depth}${!n.children.length ? ' leaf' : ''}`} onClick={() => n.children.length && d.toggleNode(tree, n.id)}>
                    {renderName(n)}
                    {valueCells(n, false)}
                  </tr>
                ))}
                {!flat.length && <tr><td colSpan={200} className="sdt-empty">No rows match the current filters.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* ── Field panel (Excel PivotTable Fields) ── */}
        {panelOpen && (
          <aside className="pv-panel card" aria-label="Pivot fields">
            <div className="pv-panel-hd">
              <span>Pivot fields</span>
              <button className="pv-reset" onClick={() => { setLayout(DEFAULT_LAYOUT); d.setDimF(EMPTY_DIM); d.collapse(); setDepth(1) }}>Reset layout</button>
            </div>
            <p className="pv-hint">Drag fields between areas. Rows builds the hierarchy top to bottom; ▾ filters a field.</p>

            <div className="pv-area-label">Rows</div>
            <div className={`pv-area${over === 'rows' ? ' pv-over' : ''}`} {...dz('rows', () => dropRows(null))}>
              {rowFields.map((k, i) => (
                <div key={k} className={`pv-chip pv-chip--row${d.dimF[k].length ? ' filtered' : ''}${over === `r:${k}` ? ' pv-before' : ''}`}
                     {...dragProps('row', k)} {...dz(`r:${k}`, () => dropRows(k))}>
                  <span className="pv-grip" aria-hidden>⋮⋮</span>
                  <span className="pv-chip-n">{i + 1}</span>
                  <span className="pv-chip-label">{levelLabel(k)}</span>
                  <button className="pv-chip-btn" title={`Filter ${levelLabel(k)}`} onClick={e => d.openF(k, e)}>▾</button>
                  <button className="pv-chip-btn" title="Remove from rows" disabled={rowFields.length === 1}
                          onClick={() => setL(l => ({ rows: l.rows.filter(x => x !== k) }))}>✕</button>
                </div>
              ))}
            </div>

            <div className="pv-area-label">Available fields</div>
            <div className={`pv-area pv-area--pool${over === 'pool' ? ' pv-over' : ''}`} {...dz('pool', dropRowPool)}>
              {available.length ? available.map(k => (
                <div key={k} className={`pv-chip${d.dimF[k].length ? ' filtered' : ''}`} {...dragProps('row', k)}
                     onDoubleClick={() => setL(l => ({ rows: [...l.rows, k] }))} title="Drag to Rows (or double-click to add)">
                  <span className="pv-grip" aria-hidden>⋮⋮</span>
                  <span className="pv-chip-label">{levelLabel(k)}</span>
                  <button className="pv-chip-btn" title={`Filter ${levelLabel(k)}`} onClick={e => d.openF(k, e)}>▾</button>
                  <button className="pv-chip-btn" title="Add to rows" onClick={() => setL(l => ({ rows: [...l.rows, k] }))}>＋</button>
                </div>
              )) : <span className="pv-empty">All fields are in Rows</span>}
            </div>

            <div className="pv-area-label">Values <span className="pv-sub">(each month, quarter and Total)</span></div>
            <div className={`pv-area${over === 'vals' ? ' pv-over' : ''}`} {...dz('vals', () => dropValues(null))}>
              {valueFields.map(k => (
                <div key={k} className={`pv-chip pv-chip--val${over === `v:${k}` ? ' pv-before' : ''}`}
                     {...dragProps('val', k)} {...dz(`v:${k}`, () => dropValues(k))}>
                  <span className="pv-grip" aria-hidden>⋮⋮</span>
                  <span className="pv-chip-label">{VALUE_DEFS[k].label}</span>
                  {VALUE_DEFS[k].locked
                    ? <span className="pv-lock" title="Growth % is always shown">always</span>
                    : <button className="pv-chip-btn" title="Remove value" onClick={() => setL(l => ({ values: l.values.filter(x => x !== k) }))}>✕</button>}
                </div>
              ))}
            </div>
            {valuePool.length > 0 && (
              <div className={`pv-area pv-area--pool${over === 'vpool' ? ' pv-over' : ''}`} {...dz('vpool', dropValPool)}>
                {valuePool.map(k => (
                  <div key={k} className="pv-chip" {...dragProps('val', k)} title="Drag to Values (or click ＋)">
                    <span className="pv-grip" aria-hidden>⋮⋮</span>
                    <span className="pv-chip-label">{VALUE_DEFS[k].label}</span>
                    <button className="pv-chip-btn" title="Add value" onClick={() => setL(l => ({ values: [...l.values.filter(x => x !== 'gr'), k, 'gr'] }))}>＋</button>
                  </div>
                ))}
              </div>
            )}

            <div className="pv-area-label">Columns</div>
            <div className="pv-area pv-area--static">
              <div className="pv-colrow"><span>Months</span><span className="pv-sub">{VIS[0]}–{VIS[VIS.length - 1]}</span></div>
              <div className="pv-colrow">
                <button className="pv-link" onClick={() => setL({ collapsedQ: QTR_DEF.map(([q]) => q) })}>Collapse quarters</button>
                <button className="pv-link" onClick={() => setL({ collapsedQ: [] })}>Expand all</button>
              </div>
              <div className="pv-colrow"><span>Total</span><span className="pv-sub">always last</span></div>
            </div>
          </aside>
        )}
      </div>

      {d.openFilter && LEVEL_KEYS.includes(d.openFilter.col) && (
        <HeaderFilter title={levelLabel(d.openFilter.col)} options={options[d.openFilter.col]} selected={d.dimF[d.openFilter.col]}
          onChange={v => d.setDimF(f => ({ ...f, [d.openFilter.col]: v }))} onClose={d.closeF} anchor={d.openFilter.anchor} />
      )}
    </div>
  )
}
