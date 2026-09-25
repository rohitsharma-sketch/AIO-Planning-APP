import { useState, useEffect, useRef, useMemo } from 'react'
import './OutputTab.css'
import { tagClass, MONTHS, toLeaf } from '../lib/tags'
import { apiUrl } from '../lib/apiBase'
import { useVisibleMonths } from '../lib/horizon'
import { LEVELS, LEVEL_KEYS, EMPTY_DIM, aggregate, buildTree, sortTree, flatten, dimOptions, filterLeaves, useDrill } from '../lib/drill'


const DIV_COLORS = { GM:'#334155', KIDS:'#A16207', LADIES:'#9D174D', MENS:'#0F766E', RETAIL:'#5B21B6' }
const TAG_COLORS = { LfL:'#3D5AD6', Ramp:'#B45309', NSO:'#15803D' }  // = .tag-* chips / Summary charts
const LEVEL_COLORS = { Division: DIV_COLORS, Type: TAG_COLORS }

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
function MultiSelect({ label, options, selected, onChange, colorMap, width, className = '', wrapProps }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)
  const shown = q ? options.filter(o => String(o).toLowerCase().includes(q.trim().toLowerCase())) : options

  useEffect(() => {
    function handler(e) { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setQ('') } }
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
    <div className={`ms-wrap ${className}`} ref={ref} style={width ? { minWidth: width } : {}} {...wrapProps}>
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
          {options.length > 12 && (
            <input className="ms-search" autoFocus placeholder={`Search ${label.toLowerCase()}…`} value={q} onChange={e => setQ(e.target.value)} />
          )}
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
            {shown.map(opt => {
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

// ── Pivot Output (2026-09-25). One compact table replaces Store summary /
// Monthly detail / Division rollup. No field panel (user: "more minimalistic
// and much more compact … i dont need field panes"):
//  • rows    = the hierarchy chips in the header. Click a chip = expand the
//              table to that layer (click the deepest open one = fold it);
//              drag a chip in front of / behind another to re-order the layers
//  • columns = every shown month (rule 1, lib/horizon) in quarter bands (click
//              a band to fold it into one column) + Total
//  • values  = small toggles in the toolbar; Growth % always on
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
    const saved = (l.rows || []).filter(k => LEVEL_KEYS.includes(k))
    const rows = saved.length ? saved : LEVEL_KEYS   // removed layers wait in the filter bar
    const values = VALUE_KEYS.filter(k => k === 'gr' || (l.values || []).includes(k))
    return { rows, values, unit: l.unit === 'Cr' ? 'Cr' : 'L', collapsedQ: Array.isArray(l.collapsedQ) ? l.collapsedQ : [] }
  } catch { return DEFAULT_LAYOUT }
}

const sumIdx = (arr, idx) => idx.reduce((s, i) => s + (arr[i] || 0), 0)
function cellsFor(n, g) {
  const b = sumIdx(n.mb, g.idx), f = sumIdx(n.m, g.idx)
  return { stores: n.stores, base: b, fcst: f, dev: f - b, gr: b > 0 ? (f / b - 1) * 100 : null }
}
const fmtGr = v => (v == null ? 'new' : (v > 0 ? '+' : '') + v.toFixed(1) + '%')

// Move `key` in front of (side -1) or behind (side +1) `target`.
export function reorder(list, key, target, side) {
  if (key === target) return list
  const without = list.filter(k => k !== key)
  const i = without.indexOf(target) + (side > 0 ? 1 : 0)
  return [...without.slice(0, i), key, ...without.slice(i)]
}

export default function OutputTab({ sessionId, runKey }) {
  const [rows, setRows]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  // Pivot layout (remembered per browser)
  const [layout, setLayout] = useState(loadLayout)
  useEffect(() => { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)) } catch {} }, [layout])
  const { rows: rowFields, values: valueFields, unit } = layout
  const collapsedQ = useMemo(() => new Set(layout.collapsedQ), [layout.collapsedQ])
  const setL = patch => setLayout(l => ({ ...l, ...(typeof patch === 'function' ? patch(l) : patch) }))
  const [sort, setSort] = useState({ key: 'fcst', dir: -1 })     // Total-group value, or 'name'
  const [depth, setDepth] = useState(2)                           // layers shown (top layer opens expanded)
  const [drag, setDrag] = useState(null)                          // layer key being dragged
  const [over, setOver] = useState(null)                          // { key, side: -1 | 1 }
  const reapply = useRef(false)                                   // re-open `depth` layers after a re-order

  const VIS = useVisibleMonths()
  const VIS_IDX = useMemo(() => VIS.map(m => MONTHS.indexOf(m)), [VIS])
  const d = useDrill({ defaultSort: 'fcst', resetKey: runKey })

  useEffect(() => { setDepth(2) }, [runKey])   // useDrill clears the layer filters on runKey

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
  const options  = useMemo(() => {
    const o = dimOptions(leaves), out = {}
    for (const k of LEVEL_KEYS) out[k] = o[k].map(x => x.value).filter(v => v != null && v !== '' && v !== '—')
    return out
  }, [leaves])
  const filtered = useMemo(() => filterLeaves(leaves, { dimF: d.dimF, idx: VIS_IDX }), [leaves, d.dimF, VIS_IDX])

  // Column groups: Mar'27, then quarter bands (months, or one column when folded), then Total
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

  // Node ids change with the layer order, so re-open the same number of layers.
  useEffect(() => {
    if (!reapply.current) return
    reapply.current = false
    depth <= 1 ? d.collapse() : d.expandTo(tree, depth - 1)
  }, [tree])   // eslint-disable-line react-hooks/exhaustive-deps

  // ── Helpers ────────────────────────────────────────────────────────────
  const U = unit === 'Cr' ? 0.01 : 1
  const fmtVal = (v, key) => key === 'gr' ? fmtGr(v) : key === 'stores' ? v : key === 'dev' ? fmtDev(v * U) : fmt1(v * U)
  const clsVal = (v, key) => key === 'gr' ? (v == null ? 'muted' : v >= 0 ? 'positive' : 'negative')
    : key === 'dev' ? (v > 0 ? 'positive' : v < 0 ? 'negative' : '') : key === 'fcst' ? 'fw-bold' : ''
  const levelLabel = k => LEVELS.find(l => l.key === k).label
  const anyFilter = LEVEL_KEYS.some(k => d.dimF[k].length)

  // Layer chip click: open the table down to layer i; click the deepest open layer again = fold it.
  const crumbClick = i => {
    const target = depth === i + 1 ? i : i + 1
    if (target <= 1) { d.collapse(); setDepth(1) } else { d.expandTo(tree, target - 1); setDepth(target) }
  }
  // +/- on layer i: open every node of that layer (show layer i+1) or close them all.
  const layerToggle = (i, e) => {
    e.stopPropagation()
    const target = depth > i + 1 ? i + 1 : i + 2
    if (target <= 1) { d.collapse(); setDepth(1) } else { d.expandTo(tree, target - 1); setDepth(target) }
  }
  const moveLayer = (key, target, side) => { reapply.current = true; setL(l => ({ rows: reorder(l.rows, key, target, side) })) }
  // Drag a header chip up to the filter bar = take that layer out of the hierarchy
  // (its filter keeps working); drag it back from the bar onto the header to re-add it.
  const removeLayer = k => {
    if (!rowFields.includes(k) || rowFields.length === 1) return
    reapply.current = true
    setDepth(dp => Math.min(dp, rowFields.length - 1))
    setL(l => ({ rows: l.rows.filter(x => x !== k) }))
  }
  const endDrag = () => { setDrag(null); setOver(null) }
  const dragFrom = k => ({
    draggable: true,
    onDragStart: e => { setDrag(k); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', k) },
    onDragEnd: endDrag,
  })
  const barDrop = {
    onDragOver: e => { if (drag && rowFields.includes(drag) && rowFields.length > 1) { e.preventDefault(); setOver({ key: 'bar' }) } },
    onDragLeave: e => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(o => (o?.key === 'bar' ? null : o)) },
    onDrop: e => { e.preventDefault(); removeLayer(drag); endDrag() },
  }
  const headDrop = {   // empty space after the last chip = add at the end
    onDragOver: e => { if (drag) { e.preventDefault(); setOver(o => (o?.key === '__end' ? o : { key: '__end' })) } },
    onDrop: e => { e.preventDefault(); if (drag) moveLayer(drag, rowFields[rowFields.length - 1], 1); endDrag() },
  }
  const toggleQ = q => setL(l => ({ collapsedQ: l.collapsedQ.includes(q) ? l.collapsedQ.filter(x => x !== q) : [...l.collapsedQ, q] }))
  const toggleVal = k => setL(l => ({ values: VALUE_KEYS.filter(x => x === k ? !l.values.includes(k) : l.values.includes(x)) }))
  const sortBy = key => setSort(s => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === 'name' ? 1 : -1 }))

  // Chip drag & drop: drop on a chip's left half = in front of it, right half = behind it.
  const chipDnd = (k, i) => ({
    ...dragFrom(k),
    onDragOver: e => {
      if (!drag) return
      e.preventDefault(); e.stopPropagation()
      const r = e.currentTarget.getBoundingClientRect()
      const side = e.clientX < r.left + r.width / 2 ? -1 : 1
      setOver(o => (o?.key === k && o.side === side ? o : { key: k, side }))
    },
    onDrop: e => { e.preventDefault(); e.stopPropagation(); if (drag && over?.side) moveLayer(drag, k, over.side); endDrag() },
    // Keyboard: Enter/Space = click, Delete = remove the layer, Alt+← / Alt+→ moves it
    onKeyDown: e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); crumbClick(i); return }
      if (e.key === 'Delete') { e.preventDefault(); removeLayer(k); return }
      if (!e.altKey || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
      e.preventDefault()
      const j = i + (e.key === 'ArrowLeft' ? -1 : 1)
      if (j >= 0 && j < rowFields.length) moveLayer(k, rowFields[j], e.key === 'ArrowLeft' ? -1 : 1)
    },
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
      <span className="sdt-indent" style={{ width: n.depth * 14 }} />
      <span className={`sdt-caret${!n.children.length ? ' none' : exp.has(n.id) ? ' open' : ''}`}>&gt;</span>
      {n.level === 'Division' ? <span className="div-pill" style={{ background: DIV_COLORS[n.name] }}>{n.name}</span>
     : n.level === 'Type'     ? <span className={`tag ${n.name === 'NSO' ? 'tag-nso' : n.name === 'Ramp' ? 'tag-ramp' : 'tag-lfl'}`}>{n.name}</span>
     : n.level === 'Tag'      ? <span className={`tag ${tagClass(n.name)}`}>{n.name}</span>
     : n.level === 'Store'    ? <span className="store-name">{n.name}</span>
     : <span className="cluster-cell">{n.name}</span>}
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
        <button className="pv-band-btn" onClick={() => toggleQ(g.band)} title={collapsed ? 'Expand to months' : 'Fold into one quarter column'}>
          <span className="pv-tw">{collapsed ? '▸' : '▾'}</span>{g.bandLabel}
        </button>
      </th>)
    i = j - 1
  }

  if (loading) return <div className="out-loading">Loading detail data…</div>
  if (error)   return <div className="out-error">Error: {error}</div>
  if (!rows)   return null

  return (
    <div className="out-wrap out-drill">
      <div className="card pv-card">
        {/* ── One slim bar: filters · values · unit · export ── */}
        <div className={`pv-bar${over?.key === 'bar' ? ' pv-bar--drop' : ''}`} {...barDrop}>
          {/* One filter per layer: hierarchy layers in chip order, then removed layers (dashed) -
              every one is a chip you can drag onto the header to place in the hierarchy */}
          {[...rowFields, ...LEVEL_KEYS.filter(k => !rowFields.includes(k))].map(k => (
            <MultiSelect key={k} label={levelLabel(k)} options={options[k]} selected={d.dimF[k]} colorMap={LEVEL_COLORS[k]}
                         onChange={v => d.setDimF(f => ({ ...f, [k]: v }))}
                         className={`pv-fchip${rowFields.includes(k) ? '' : ' pv-fchip--off'}${drag === k ? ' dragging' : ''}`}
                         wrapProps={{ ...dragFrom(k), title: rowFields.includes(k) ? `Drag onto the header to move ${levelLabel(k)}` : `${levelLabel(k)} is not in the hierarchy - drag it onto the header to add it` }} />
          ))}
          {anyFilter && <button className="pv-link" onClick={() => d.setDimF(EMPTY_DIM)}>Clear filters</button>}
          <span className="pv-bar-gap" />
          <div className="pv-vals" role="group" aria-label="Values">
            {VALUE_KEYS.map(k => (
              <button key={k} className={valueFields.includes(k) ? 'on' : ''} disabled={VALUE_DEFS[k].locked}
                      aria-pressed={valueFields.includes(k)} onClick={() => toggleVal(k)}
                      title={VALUE_DEFS[k].locked ? 'Growth % is always shown' : `Show ${VALUE_DEFS[k].label}`}>
                {VALUE_DEFS[k].short}
              </button>
            ))}
          </div>
          <div className="pv-seg" role="group" aria-label="Unit">
            {['L', 'Cr'].map(u => <button key={u} className={unit === u ? 'on' : ''} onClick={() => setL({ unit: u })}>₹ {u === 'L' ? 'L' : 'Cr'}</button>)}
          </div>
          <button className="pv-link" onClick={exportCsv} title="Download exactly this view as CSV">Export ↓</button>
        </div>

        <div className="table-scroll sdt-scroll">
          <table className="stores-table sdt-table pv-table">
            <thead>
              <tr>
                <th rowSpan={3} className="pv-rowhead pv-sticky">
                  <div className={`pv-layers${over?.key === '__end' ? ' drop-end' : ''}`} {...headDrop} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(null) }}>
                    {rowFields.map((k, i) => (
                      <div key={k} role="button" tabIndex={0} {...chipDnd(k, i)} onClick={() => crumbClick(i)}
                              className={`pv-layer${i < depth ? ' on' : ''}${drag === k ? ' dragging' : ''}${d.dimF[k].length ? ' filtered' : ''}${over?.key === k && drag !== k ? (over.side < 0 ? ' drop-l' : ' drop-r') : ''}`}
                              title={`${depth === i + 1 ? 'Fold' : 'Open to'} ${levelLabel(k)} · drag to re-order (Alt+←/→) · drag up to the filter bar to remove (Delete)`}>
                        {i < rowFields.length - 1 && (
                          <span className="pv-layer-t" role="button" aria-label={`${depth > i + 1 ? 'Collapse' : 'Expand'} every ${levelLabel(k)}`}
                                title={`${depth > i + 1 ? 'Collapse' : 'Expand'} every ${levelLabel(k)}`} onClick={e => layerToggle(i, e)}>
                            {depth > i + 1 ? '−' : '+'}
                          </span>
                        )}
                        {levelLabel(k)}
                      </div>
                    ))}
                  </div>
                  <button className="pv-sortname" onClick={() => sortBy('name')}>A–Z{sort.key === 'name' ? (sort.dir > 0 ? ' ↑' : ' ↓') : ''}</button>
                  <span className="pv-meta">{grand.stores.toLocaleString()} stores · ₹ {unit === 'Cr' ? 'Cr' : 'Lakhs'}</span>
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
        {VIS.length < MONTHS.length && <div className="pv-foot">{VIS[0]}–{VIS[VIS.length - 1]} shown · later months appear as their base month closes</div>}
      </div>

    </div>
  )
}
