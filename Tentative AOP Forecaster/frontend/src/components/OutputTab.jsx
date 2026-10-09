import { useState, useEffect, useRef, useMemo } from 'react'
import './OutputTab.css'
import { tagClass, MONTHS, toLeaf } from '../lib/tags'
import { apiUrl } from '../lib/apiBase'
import { useShownMonths, monthSpan } from '../lib/horizon'
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
  // Eff = the Calendar's calendarised (reindexed) LY sales of the row - user, 2026-10-08: "add 2 columns named Eff
  // Sales, Eff Cont % and Eff Gr% in Output. Month Wise and Total Both"; "All sales should match with calendarised
  // sales on month level"
  eff:    { label: 'Eff Sales - calendarised (reindexed) LY sales, = the Calendar\'s Month Wise Matrix', short: 'Eff Sales' },
  effc:   { label: 'Eff Cont % - this row\'s share of the row above, in Eff Sales', short: 'Eff Cont%' },
  effgr:  { label: 'Eff Gr% - Forecast vs Eff Sales', short: 'Eff Gr%' },
}
const VALUE_KEYS = Object.keys(VALUE_DEFS)
const EFF_KEYS = ['eff', 'effc', 'effgr']
const DEFAULT_LAYOUT = { rows: LEVEL_KEYS, values: ['base', 'fcst', 'gr', ...EFF_KEYS], unit: 'L', collapsedQ: [] }
const QTR_DEF = [['Q1', [1, 2, 3]], ['Q2', [4, 5, 6]], ['Q3', [7, 8, 9]], ['Q4', [10, 11, 12]]]   // MONTHS idx; 0 = Mar'27
const LAYOUT_KEY = 'aop.output.pivotLayout'
const KEYS = [...LEVEL_KEYS, 'Department']   // Department = a filter field; drag it onto the header to add the layer

function loadLayout() {
  try {
    const l = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null')
    if (!l) return DEFAULT_LAYOUT
    const saved = (l.rows || []).filter(k => KEYS.includes(k))
    const rows = saved.length ? saved : LEVEL_KEYS   // removed layers wait in the filter bar
    // layouts saved before the Eff columns existed get them switched on once
    const values = VALUE_KEYS.filter(k => k === 'gr' || (l.values || []).includes(k) || (!l.eff && EFF_KEYS.includes(k)))
    return { rows, values, unit: l.unit === 'Cr' ? 'Cr' : 'L', collapsedQ: Array.isArray(l.collapsedQ) ? l.collapsedQ : [], eff: true }
  } catch { return DEFAULT_LAYOUT }
}

const sumIdx = (arr, idx) => idx.reduce((s, i) => s + (arr[i] || 0), 0)
// effIdx = the months that have calendarised LY sales (closed LY months); Eff values are '—' for a group without any
function cellsFor(n, g, parent, effIdx) {
  const b = sumIdx(n.mb, g.idx), f = sumIdx(n.m, g.idx)
  const gi = g.idx.filter(i => effIdx.has(i))
  const e = gi.length ? sumIdx(n.e, gi) : undefined, pe = gi.length && parent ? sumIdx(parent.e, gi) : 0, fe = sumIdx(n.m, gi)
  return { stores: n.stores, base: b, fcst: f, dev: f - b, gr: b > 0 ? (f / b - 1) * 100 : null,
           eff: e, effc: e === undefined ? undefined : pe > 0 ? (e / pe) * 100 : null,
           effgr: e === undefined ? undefined : e > 0 ? (fe / e - 1) * 100 : null }
}

// Department split (user, 2026-10-08, "add the department filter field in the output tab"): each store x division
// row's Base and Forecast are split over its departments by their share of that store-division's ACTUAL LY sales in the
// same month (user, 2026-10-09: "change the cont% to break AOP into Department to Actual Sales Cont % instead of
// RE-indexed Cont %" - dept-mix?sale_type=actual); the department's Eff Sales stay its own calendarised (reindexed)
// sales, so Eff still matches the Calendar. A month without closed
// LY data uses the store-division's mix over the months that have it; a store with no LY sales (new stores) uses the
// division's network-wide mix. Shares add to 100%, so every division's Base / Forecast is kept exactly.
function deptShares(src) {
  const depts = Object.keys(src), tot = new Array(13).fill(0), ytd = {}
  let ytdTot = 0
  for (const dp of depts) {
    ytd[dp] = 0
    src[dp].forEach((x, i) => { const v = Math.max(x || 0, 0); tot[i] += v; ytd[dp] += v })
    ytdTot += ytd[dp]
  }
  if (ytdTot <= 0) return null
  return Object.fromEntries(depts.map(dp => [dp, tot.map((t, i) => (t > 0 ? Math.max(src[dp][i] || 0, 0) / t : ytd[dp] / ytdTot))]))
}
export function splitByDept(leaves, mix, shareMix = mix) {
  const net = {}
  for (const divs of Object.values(shareMix)) for (const [div, depts] of Object.entries(divs)) for (const [dp, v] of Object.entries(depts)) {
    const a = ((net[div] ??= {})[dp] ??= new Array(13).fill(0))
    v.forEach((x, i) => { if (x > 0) a[i] += x })
  }
  const netShares = Object.fromEntries(Object.entries(net).map(([div, src]) => [div, deptShares(src)]))
  const zero = new Array(13).fill(0), out = []
  for (const r of leaves) {
    const st = String(r.Store).trim().toUpperCase()
    const own = mix[st]?.[r.Division], shOwn = shareMix[st]?.[r.Division]
    const shares = (shOwn && deptShares(shOwn)) || netShares[r.Division]
    if (!shares) { out.push({ ...r, Department: '(no LY mix)', e: zero }); continue }
    // every department with a share or with Eff Sales, so Base / Fcst and Eff each still add up to the store-division
    for (const dp of new Set([...Object.keys(shares), ...Object.keys(own || {})])) {
      const sh = shares[dp] || zero
      out.push({ ...r, Department: dp, m: r.m.map((x, i) => x * sh[i]), mb: r.mb.map((x, i) => x * sh[i]),
                 e: own?.[dp] ? own[dp].map(x => x || 0) : zero })
    }
  }
  return out
}
// Store x division Eff Sales = the sum of its departments' calendarised sales (no split needed)
function withEff(leaves, mix) {
  const zero = new Array(13).fill(0)
  return leaves.map(r => {
    const own = mix[String(r.Store).trim().toUpperCase()]?.[r.Division]
    if (!own) return { ...r, e: zero }
    const e = new Array(13).fill(0)
    for (const v of Object.values(own)) v.forEach((x, i) => { e[i] += x || 0 })
    return { ...r, e }
  })
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
  const short = k => VALUE_DEFS[k].short

  // Pivot layout (remembered per browser)
  const [layout, setLayout] = useState(loadLayout)
  useEffect(() => { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify({ ...layout, eff: true })) } catch {} }, [layout])
  // Calendarised LY sales per store x division x department (dept-mix, the Calendar's reindexed department snapshot):
  // Eff Sales, and the department split
  const [mix, setMix] = useState(null)
  const [mixA, setMixA] = useState(null)   // actual LY sales: the department cont % for the split
  useEffect(() => {
    setMix(null); setMixA(null)
    fetch(apiUrl('/api/config/dept-mix?sale_type=actual'))
      .then(r => r.json())
      .then(j => setMixA(j.ok ? j : { error: j.reason || j.detail || 'No actual department sales' }))
      .catch(e => setMixA({ error: e.message }))
    fetch(apiUrl('/api/config/dept-mix?sale_type=reindexed'))
      .then(r => r.json())
      .then(j => setMix(j.ok ? j : { error: j.reason || j.detail || 'No calendarised sales' }))
      .catch(e => setMix({ error: e.message }))
  }, [runKey])
  const effIdx = useMemo(() => new Set(mix?.months || []), [mix])
  const { rows: rowFields, values: valueFields, unit } = layout
  const collapsedQ = useMemo(() => new Set(layout.collapsedQ), [layout.collapsedQ])
  const setL = patch => setLayout(l => ({ ...l, ...(typeof patch === 'function' ? patch(l) : patch) }))
  const [sort, setSort] = useState({ key: 'fcst', dir: -1 })     // Total-group value, or 'name'
  const [depth, setDepth] = useState(2)                           // layers shown (top layer opens expanded)
  const [drag, setDrag] = useState(null)                          // layer key being dragged
  const [over, setOver] = useState(null)                          // { key, side: -1 | 1 }
  const reapply = useRef(false)                                   // re-open `depth` layers after a re-order

  const { shown: VIS, picked: monthsPicked } = useShownMonths()   // the month selection made in Review
  const VIS_IDX = useMemo(() => VIS.map(m => MONTHS.indexOf(m)), [VIS])
  // Month filter (2026-09-25): [] = every shown month. Narrows the month columns,
  // quarter bands AND the Total (+ its Gr%) to the picked months.
  const [monthF, setMonthF] = useState([])
  const SEL_IDX = useMemo(() => (monthF.length ? VIS_IDX.filter(i => monthF.includes(MONTHS[i])) : VIS_IDX), [VIS_IDX, monthF])
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
  // Department rows only when the Department layer or filter is in use (the split is ~90x the rows)
  const deptOn = layout.rows.includes('Department') || (d.dimF.Department || []).length > 0
  const leaves   = useMemo(() => {                                                       // ₹ Lakhs
    const ls = (rows || []).map(r => toLeaf(r, 1))
    if (!mix?.mix) return ls
    return deptOn ? splitByDept(ls, mix.mix, mixA?.mix || mix.mix) : withEff(ls, mix.mix)
  }, [rows, mix, mixA, deptOn])
  const options  = useMemo(() => {
    const o = dimOptions(leaves, LEVEL_KEYS), out = {}
    for (const k of LEVEL_KEYS) out[k] = o[k].map(x => x.value).filter(v => v != null && v !== '' && v !== '—')
    // departments listed from the calendarised sales (for the divisions shown), even before the split is on
    const divs = new Set(out.Division), deps = new Set()
    for (const sd of [...Object.values(mix?.mix || {}), ...Object.values(mixA?.mix || {})]) for (const [dv, dps] of Object.entries(sd)) if (divs.has(dv)) Object.keys(dps).forEach(x => deps.add(x))
    out.Department = [...deps].sort()
    return out
  }, [leaves, mix, mixA])
  const filtered = useMemo(() => filterLeaves(leaves, { dimF: d.dimF, idx: SEL_IDX, keys: deptOn ? KEYS : LEVEL_KEYS }), [leaves, d.dimF, SEL_IDX, deptOn])

  // Column groups: Mar'27, then quarter bands (months, or one column when folded), then Total
  const groups = useMemo(() => {
    const vis = new Set(SEL_IDX), out = []
    if (vis.has(0)) out.push({ key: 'm0', band: null, label: MONTHS[0], idx: [0] })
    for (const [q, ids] of QTR_DEF) {
      const inq = ids.filter(i => vis.has(i))
      if (!inq.length) continue
      const span = inq.length === 1 ? MONTHS[inq[0]].slice(0, 3) : `${MONTHS[inq[0]].slice(0, 3)}–${MONTHS[inq[inq.length - 1]].slice(0, 3)}`
      if (collapsedQ.has(q)) out.push({ key: q, band: q, bandLabel: `${q} · ${span}`, label: `${q} total`, idx: inq, collapsed: true })
      else inq.forEach(i => out.push({ key: `m${i}`, band: q, bandLabel: `${q} · ${span}`, label: MONTHS[i], idx: [i] }))
    }
    const sel = SEL_IDX.map(i => MONTHS[i])
    const contiguous = SEL_IDX.every((v, i) => i === 0 || v === SEL_IDX[i - 1] + 1)
    const span = sel.length === 1 ? sel[0] : contiguous ? `${sel[0]}–${sel[sel.length - 1]}` : `${sel.length} months`
    out.push({ key: 'total', band: null, label: `Total · ${span}`, idx: SEL_IDX, total: true })
    return out
  }, [SEL_IDX, collapsedQ])
  const totalGroup = groups[groups.length - 1]
  const valsFor = g => valueFields.filter(v => g.total || v !== 'stores')   // store count only in Total

  const tree = useMemo(() => {
    const val = n => (sort.key === 'name' ? n.name : cellsFor(n, totalGroup, null, effIdx)[sort.key] ?? null)
    return sortTree(buildTree(filtered, rowFields, SEL_IDX), val, sort.dir)
  }, [filtered, rowFields, SEL_IDX, sort, totalGroup])
  const grand = useMemo(() => aggregate(filtered, SEL_IDX), [filtered, SEL_IDX])
  const exp   = d.expandedFor(tree)
  const flat  = useMemo(() => flatten(tree, exp), [tree, exp])
  // Cont% = this row's forecast / the row above it (grand total = 100%)
  const byId  = useMemo(() => { const m = new Map(); const walk = ns => ns.forEach(n => { m.set(n.id, n); walk(n.children) }); walk(tree); return m }, [tree])
  const parentOf = n => (n === grand ? grand : byId.get(n.id.slice(0, n.id.lastIndexOf('/'))) || grand)

  // Node ids change with the layer order, so re-open the same number of layers.
  useEffect(() => {
    if (!reapply.current) return
    reapply.current = false
    depth <= 1 ? d.collapse() : d.expandTo(tree, depth - 1)
  }, [tree])   // eslint-disable-line react-hooks/exhaustive-deps

  // ── Helpers ────────────────────────────────────────────────────────────
  const U = unit === 'Cr' ? 0.01 : 1
  const fmtVal = (v, key) => v === undefined ? '—'
    : key === 'gr' || key === 'effgr' ? fmtGr(v) : key === 'stores' ? v : key === 'effc' ? (v == null ? '—' : v.toFixed(1) + '%')
    : key === 'dev' ? fmtDev(v * U) : fmt1(v * U)
  const clsVal = (v, key) => key === 'gr' || key === 'effgr' ? (v == null ? 'muted' : v >= 0 ? 'positive' : 'negative')
    : key === 'dev' ? (v > 0 ? 'positive' : v < 0 ? 'negative' : '') : key === 'fcst' ? 'fw-bold' : key === 'effc' ? 'muted' : ''
  const levelLabel = k => LEVELS.find(l => l.key === k)?.label ?? k
  const dimSel = k => d.dimF[k] || []
  const anyFilter = monthF.length > 0 || KEYS.some(k => dimSel(k).length)

  // One click on layer chip i = expand every node of that layer (show layer i+1),
  // click again = collapse them all. The last layer has nothing below it.
  const layerToggle = i => {
    if (i >= rowFields.length - 1) return
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
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); layerToggle(i); return }
      if (e.key === 'Delete') { e.preventDefault(); removeLayer(k); return }
      if (!e.altKey || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
      e.preventDefault()
      const j = i + (e.key === 'ArrowLeft' ? -1 : 1)
      if (j >= 0 && j < rowFields.length) moveLayer(k, rowFields[j], e.key === 'ArrowLeft' ? -1 : 1)
    },
  })

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
    const c = cellsFor(n, g, parentOf(n), effIdx), vs = valsFor(g)
    return vs.map(v => (
      <td key={`${g.key}|${v}`} className={`num ${clsVal(c[v], v)} ${bold ? 'fw-bold' : ''} ${g.total ? 'pv-total' : ''} ${v === vs[0] ? 'pv-gstart' : ''}`}>
        {fmtVal(c[v], v)}
      </td>
    ))
  })

  // Reconciliation to the Calendar (user, 2026-10-08: "How will i know about DND and such cases where there will be a
  // slight difference ... make such a provision in the output tab too"): the calendarised sales of divisions that are
  // not planned (DND, non-trading ...) for the stores in view, and Grand total + those = the Calendar's own total.
  // Only when no Division / Department filter is on (those views are not whole stores).
  const notPlanned = useMemo(() => {
    if (!mix?.other || dimSel('Division').length || dimSel('Department').length) return null
    const stores = new Set(filtered.map(r => String(r.Store).trim().toUpperCase()))
    const e = new Array(13).fill(0), names = {}
    for (const st of stores) for (const [dv, v] of Object.entries(mix.other[st] || {})) {
      v.forEach((x, i) => { e[i] += x || 0 })
      names[dv] = (names[dv] || 0) + v.reduce((a, x) => a + (x || 0), 0)
    }
    return e.some(x => Math.abs(x) > 1e-9) ? { e, names } : null
  }, [mix, filtered, d.dimF])   // eslint-disable-line react-hooks/exhaustive-deps
  const reconCells = (e, cls) => groups.flatMap(g => {
    const gi = g.idx.filter(i => effIdx.has(i)), vs = valsFor(g)
    return vs.map(v => (
      <td key={`${g.key}|${v}`} className={`num ${cls} ${g.total ? 'pv-total' : ''} ${v === vs[0] ? 'pv-gstart' : ''}`}>
        {v === 'eff' ? (gi.length ? fmt1(sumIdx(e, gi) * U) : '—') : ''}
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
  if (!mix || (deptOn && !mixA)) return <div className="out-loading">Loading calendarised sales…</div>

  return (
    <div className="out-wrap out-drill">
      <div className="card pv-card">
        {/* ── One slim bar: filters · values · unit · export ── */}
        <div className={`pv-bar${over?.key === 'bar' ? ' pv-bar--drop' : ''}`} {...barDrop}>
          <MultiSelect label="Month" options={VIS} selected={monthF} onChange={setMonthF} className="pv-mfilter" />
          {/* One filter per layer: hierarchy layers in chip order, then removed layers (dashed) -
              every one is a chip you can drag onto the header to place in the hierarchy */}
          {[...rowFields, ...KEYS.filter(k => !rowFields.includes(k))].map(k => (
            <MultiSelect key={k} label={levelLabel(k)} options={options[k]} selected={dimSel(k)} colorMap={LEVEL_COLORS[k]}
                         onChange={v => d.setDimF(f => ({ ...f, [k]: v }))}
                         className={`pv-fchip${rowFields.includes(k) ? '' : ' pv-fchip--off'}${drag === k ? ' dragging' : ''}`}
                         wrapProps={{ ...dragFrom(k), title: rowFields.includes(k) ? `Drag onto the header to move ${levelLabel(k)}` : `${levelLabel(k)} is not in the hierarchy - drag it onto the header to add it` }} />
          ))}
          {anyFilter && <button className="pv-link" onClick={() => { d.setDimF(EMPTY_DIM); setMonthF([]) }}>Clear filters</button>}
          <span className="pv-bar-gap" />
          <div className="pv-vals" role="group" aria-label="Values">
            {VALUE_KEYS.map(k => (
              <button key={k} className={valueFields.includes(k) ? 'on' : ''} disabled={VALUE_DEFS[k].locked}
                      aria-pressed={valueFields.includes(k)} onClick={() => toggleVal(k)}
                      title={VALUE_DEFS[k].locked ? 'Growth % is always shown' : `Show ${VALUE_DEFS[k].label}`}>
                {short(k)}
              </button>
            ))}
          </div>
          <div className="pv-seg" role="group" aria-label="Unit">
            {['L', 'Cr'].map(u => <button key={u} className={unit === u ? 'on' : ''} onClick={() => setL({ unit: u })}>₹ {u === 'L' ? 'L' : 'Cr'}</button>)}
          </div>
        </div>

        <div className="table-scroll sdt-scroll">
          <table className="stores-table sdt-table pv-table">
            <thead>
              <tr>
                <th rowSpan={3} className="pv-rowhead pv-sticky">
                  <div className={`pv-layers${over?.key === '__end' ? ' drop-end' : ''}`} {...headDrop} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(null) }}>
                    {rowFields.map((k, i) => (
                      <div key={k} role="button" tabIndex={0} {...chipDnd(k, i)} onClick={() => layerToggle(i)}
                              aria-expanded={i < rowFields.length - 1 ? depth > i + 1 : undefined}
                              className={`pv-layer${i < depth ? ' on' : ''}${depth > i + 1 ? ' open' : ''}${drag === k ? ' dragging' : ''}${dimSel(k).length ? ' filtered' : ''}${over?.key === k && drag !== k ? (over.side < 0 ? ' drop-l' : ' drop-r') : ''}`}
                              title={`${i < rowFields.length - 1 ? `Click to ${depth > i + 1 ? 'collapse' : 'expand'} every ${levelLabel(k)} · ` : ''}drag to re-order (Alt+←/→) · drag up to the filter bar to remove (Delete)`}>
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
                          {short(v)}{sort.key === v ? (sort.dir < 0 ? ' ↓' : ' ↑') : ''}
                        </button>
                      : short(v)}
                  </th>
                )) })}
              </tr>
            </thead>
            <tbody>
              <tr className="sdt-grand">
                <td className="sdt-name pv-sticky"><strong>Grand total</strong></td>
                {valueCells(grand, true)}
              </tr>
              {notPlanned && valueFields.includes('eff') && <>
                <tr className="sdt-row pv-recon" title={'Calendarised sales of divisions that are not planned, for the stores in view: '
                  + Object.entries(notPlanned.names).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${fmt1(v * U)}`).join(', ')}>
                  <td className="sdt-name pv-sticky">+ Not in plan <small>({Object.keys(notPlanned.names).sort().join(', ')})</small></td>
                  {reconCells(notPlanned.e, 'muted')}
                </tr>
                <tr className="sdt-row pv-recon pv-recon-total" title="= the Calendar's calendarised sales for these stores (Month Wise Matrix with 'Planning divisions only' off)">
                  <td className="sdt-name pv-sticky">= Calendar total</td>
                  {reconCells(grand.e.map((x, i) => x + notPlanned.e[i]), 'fw-bold')}
                </tr>
              </>}
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
        {mix.error
          ? <div className="pv-foot">Eff Sales unavailable: {mix.error}</div>
          : <div className="pv-foot">
              Eff Sales = the Calendar's calendarised (reindexed) LY sales - the same month figures as its Month Wise Matrix, for the five planning divisions
              (DND / non-trading left out - shown under Grand total as "+ Not in plan", so "= Calendar total" matches the Calendar); '—' = LY month not closed yet. Eff Cont% = share of the row above; Eff Gr% = Fcst vs Eff Sales.
              {deptOn && (mixA?.mix
                ? ' Department rows: Base and Fcst split by the department\'s share of its store-division\'s ACTUAL LY sales in the same month last year (Actual Sales Cont %; store mix over the closed months where a month has none; new stores use the division\'s network mix); each department\'s Eff Sales stay calendarised.'
                : ` Department rows: actual department sales unavailable (${mixA?.error || 'not loaded'}) - split by the calendarised Eff Sales share instead.`)}
              {' '}Calendarised sales as of {new Date(mix.computedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}.
            </div>}
        {VIS.length < MONTHS.length && <div className="pv-foot">{monthSpan(VIS)} shown · {monthsPicked ? 'months as picked in Review' : 'later months appear as their base month closes'}</div>}
      </div>

    </div>
  )
}
