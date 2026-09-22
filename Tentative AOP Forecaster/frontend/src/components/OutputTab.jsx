import { useState, useEffect, useRef, useMemo } from 'react'
import './OutputTab.css'
import { tagClass, MONTHS, toLeaf } from '../lib/tags'
import { apiUrl } from '../lib/apiBase'
import { LEVELS, LEVEL_KEYS, EMPTY_DIM, ALL_IDX, aggregate, buildTree, sortTree, flatten, dimOptions, filterLeaves, hasNum, HeaderFilter, Th, DimFilterHeaders, DrillToolbar, useDrill } from '../lib/drill'

const DIVS = ["GM","KIDS","LADIES","MENS","RETAIL"]
const TAGS = ["LfL","Ramp","NSO"]
const PAGE_SIZE = 50

const DIV_COLORS = { GM:'#1A4B8C', KIDS:'#7C6B14', LADIES:'#8B2252', MENS:'#1A5C3A', RETAIL:'#5A3680' }
const TAG_COLORS = { LfL:'#1A4B8C', Ramp:'#7C6B14', NSO:'#1A5C3A' }

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

// ── Month select — pivot style with H1/H2 presets ────────────────
function MonthSelect({ selected, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function handler(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const H1 = MONTHS.slice(0, 6)
  const H2 = MONTHS.slice(6)
  const allSelected = selected.length === MONTHS.length
  const display = allSelected ? 'All months'
    : selected.length === 1 ? selected[0]
    : `${selected.length} months`

  // Checkbox — multi-toggle (keep at least one selected)
  function toggleCheck(m, e) {
    e.stopPropagation()
    if (selected.includes(m)) {
      if (selected.length > 1) onChange(selected.filter(x => x !== m))
    } else {
      onChange([...selected, m].sort((a, b) => MONTHS.indexOf(a) - MONTHS.indexOf(b)))
    }
  }

  // Label — exclusive select (click again to restore all)
  function selectOnly(m, e) {
    e.stopPropagation()
    if (selected.length === 1 && selected[0] === m) {
      onChange([...MONTHS])
    } else {
      onChange([m])
    }
  }

  const isChecked = m => selected.includes(m)

  return (
    <div className="ms-wrap" ref={ref} style={{ minWidth: 130 }}>
      <button
        className={`ms-trigger${!allSelected ? ' has-sel' : ''}`}
        onClick={() => setOpen(o => !o)}
      >
        <span className="ms-label-text">Months</span>
        <span className={`ms-val${!allSelected ? ' ms-val--active' : ''}`}>{display}</span>
        {!allSelected && <span className="ms-sel-badge">{selected.length}</span>}
        <span className="ms-caret">{open ? '^' : 'v'}</span>
      </button>
      {open && (
        <div className="ms-dropdown ms-dropdown--months">
          <div className="ms-pv-header">
            <span className="ms-pv-title">Months</span>
            <div className="ms-quick">
              <button onClick={e => { e.stopPropagation(); onChange([...MONTHS]) }}>All</button>
              <button onClick={e => { e.stopPropagation(); onChange([...H1]) }}>H1</button>
              <button onClick={e => { e.stopPropagation(); onChange([...H2]) }}>H2</button>
              {selected.length > 0 && (
                <button onClick={e => { e.stopPropagation(); onChange([]) }}>None</button>
              )}
            </div>
          </div>
          {/* (Select All) row */}
          <div className="ms-pv-options">
            <div
              className={`ms-pv-row ms-pv-all${allSelected ? ' ms-pv-row--checked' : ''}`}
              onClick={() => onChange(allSelected ? [] : [...MONTHS])}
            >
              <span className={`ms-pv-cb${allSelected ? ' ms-pv-cb--on' : ''}`} />
              <span className="ms-pv-row-label">(Select All)</span>
            </div>
            <div className="ms-pv-divider" />
            {/* 2-column grid of months */}
            <div className="ms-pv-month-grid">
              {MONTHS.map(m => {
                const checked = isChecked(m)
                const exclusive = selected.length === 1 && selected[0] === m
                return (
                  <div
                    key={m}
                    className={`ms-pv-row${checked ? ' ms-pv-row--checked' : ''}${exclusive ? ' ms-pv-row--only' : ''}`}
                  >
                    <span
                      className={`ms-pv-cb${checked ? ' ms-pv-cb--on' : ''}`}
                      onClick={e => toggleCheck(m, e)}
                    />
                    <span className="ms-pv-row-label" onClick={e => selectOnly(m, e)}>
                      {m}
                    </span>
                    {exclusive && <span className="ms-pv-only-tag">only</span>}
                  </div>
                )
              })}
            </div>
          </div>
          <div className="ms-pv-footer">
            <span className="ms-pv-hint">Checkbox = multi-select · label = only</span>
          </div>
        </div>
      )}
    </div>
  )
}

const EMPTY_NUM  = { base: { min: '', max: '' }, fcst: { min: '', max: '' }, dev: { min: '', max: '' }, growthEng: { min: '', max: '' } }
const NUM_TITLES = { base: 'Base', fcst: 'Forecast', dev: 'Deviation', growthEng: 'Growth %' }
const COL_SETS   = { fcst: ['fcst'], base_fcst: ['base', 'fcst'], all: ['base', 'fcst', 'dev', 'gr'] }
const COL_LABEL  = { base: 'Base', fcst: 'Forecast', dev: 'Deviation', gr: 'Growth %' }
const MONTH_RE   = /^m(\d+)\|(base|fcst|dev)$/

export default function OutputTab({ sessionId, runKey }) {
  const [rows, setRows]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState(null)

  // Filter bar (original essence)
  const [divFilter, setDivFilter]     = useState([])
  const [tagFilter, setTagFilter]     = useState([])
  const [clusterFilter, setCluster]   = useState('')
  const [storeSearch, setStoreSearch] = useState('')

  // View controls (original essence)
  const [viewMode, setViewMode]   = useState('summary')
  const [selMonths, setSelMonths] = useState(MONTHS)
  const [colSet, setColSet]       = useState('fcst')

  // Drill-down structure (shared with the Summary tab's drill table)
  const [numF, setNumF] = useState(EMPTY_NUM)
  const d = useDrill({ defaultSort: 'fcst', resetKey: runKey })

  // Reset everything when a new run completes — keeps state across navigation
  useEffect(() => {
    setDivFilter([]); setTagFilter([]); setCluster(''); setStoreSearch('')
    setViewMode('summary'); setSelMonths(MONTHS); setColSet('fcst'); setNumF(EMPTY_NUM)
    d.setSortCol('fcst'); d.setSortDir(-1)
  }, [runKey]) // eslint-disable-line react-hooks/exhaustive-deps

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

  const idx = useMemo(() => viewMode === 'summary' ? ALL_IDX : selMonths.map(m => MONTHS.indexOf(m)), [viewMode, selMonths])
  // Division rollup keeps Division as the fixed top level
  const levels = useMemo(() => viewMode === 'division' ? ['Division', ...d.levels.filter(k => k !== 'Division')] : d.levels, [viewMode, d.levels])

  const barFiltered = useMemo(() => {
    let r = leaves
    if (divFilter.length)   r = r.filter(x => divFilter.includes(x.Division))
    if (tagFilter.length)   r = r.filter(x => tagFilter.includes(x.Type))
    if (clusterFilter)      r = r.filter(x => x.Cluster === clusterFilter)
    const q = storeSearch.trim().toLowerCase()
    if (q)                  r = r.filter(x => x.Store?.toLowerCase().includes(q))
    return r
  }, [leaves, divFilter, tagFilter, clusterFilter, storeSearch])

  const filtered = useMemo(() => filterLeaves(barFiltered, { dimF: d.dimF, numF, idx }), [barFiltered, d.dimF, numF, idx])

  const { sortCol, sortDir } = d
  const tree = useMemo(() => {
    const val = n => {
      if (sortCol === 'name') return n.name
      if (sortCol === 'growth') return n.growthEng
      if (sortCol === 'lfl' || sortCol === 'ramp' || sortCol === 'nso') return n.typeCounts[{ lfl: 'LfL', ramp: 'Ramp', nso: 'NSO' }[sortCol]]
      const mm = sortCol.match(MONTH_RE)
      if (mm) { const i = +mm[1]; return mm[2] === 'base' ? n.mb[i] : mm[2] === 'fcst' ? n.m[i] : n.m[i] - n.mb[i] }
      return n[sortCol]
    }
    return sortTree(buildTree(filtered, levels, idx), val, sortDir)
  }, [filtered, levels, idx, sortCol, sortDir])
  const grand = useMemo(() => aggregate(filtered, idx), [filtered, idx])
  const exp   = d.expandedFor(tree)
  const flat  = useMemo(() => flatten(tree, exp), [tree, exp])

  // ── Helpers ────────────────────────────────────────────────────────────
  const U    = viewMode === 'division' ? 0.01 : 1           // Division rollup is shown in ₹ Cr (original essence)
  const unit = viewMode === 'division' ? 'Cr' : 'L'
  const fU   = v => fmt1(v * U)
  const fD   = v => fmtDev(v * U)
  const monthCols = COL_SETS[colSet]
  const cellVal = (n, i, c) => c === 'base' ? n.mb[i] : c === 'fcst' ? n.m[i]
    : c === 'gr' ? (n.mb[i] > 0 ? (n.m[i] / n.mb[i] - 1) * 100 : null)
    : n.m[i] - n.mb[i]

  const hasFilter = col => LEVEL_KEYS.includes(col) ? d.dimF[col].length > 0 : hasNum(numF[col])
  const drillFilters = [...LEVEL_KEYS, ...Object.keys(EMPTY_NUM)].filter(hasFilter).length
  const hasBarFilters = divFilter.length || tagFilter.length || clusterFilter || storeSearch
  const resetAll = () => { setDivFilter([]); setTagFilter([]); setCluster(''); setStoreSearch(''); d.setDimF(EMPTY_DIM); setNumF(EMPTY_NUM) }
  const th = { sortCol, sortDir, toggleSort: d.toggleSort, hasFilter, openF: d.openF }
  const nameLabel = levels.map(k => LEVELS.find(l => l.key === k).label).join(' › ')

  const renderName = n => (
    <td className="sdt-name">
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
  const growthCell = (v, bold) => <td className={`num ${bold ? 'fw-bold' : ''} ${v == null ? 'muted' : v >= 0 ? 'positive' : 'negative'}`}>{v == null ? 'new' : (v > 0 ? '+' : '') + v.toFixed(1) + '%'}</td>
  const devCell    = (v, bold) => <td className={`num ${bold ? 'fw-bold' : ''} ${v >= 0 ? 'positive' : 'negative'}`}>{fD(v)}</td>

  // Per-view metric cells (everything after the name + dim-filter columns)
  const metricCells = (n, isGrand) => {
    const b = isGrand
    if (viewMode === 'summary') return (<>
      <td className="num">{n.stores}</td>
      <td className={`num ${b ? 'fw-bold' : ''}`}>{fU(n.base)}</td>
      <td className="num fw-bold">{fU(n.fcst)}</td>
      {devCell(n.dev, b)}
      {growthCell(n.growthEng, b)}
    </>)
    if (viewMode === 'monthly') return (<>
      {selMonths.map(m => { const i = MONTHS.indexOf(m); return monthCols.map(c => {
        const v = cellVal(n, i, c)
        if (c === 'gr') return <td key={`${m}|${c}`} className={`num ${v == null ? 'muted' : v >= 0 ? 'positive' : 'negative'}`}>{v == null ? 'new' : (v > 0 ? '+' : '') + v.toFixed(1) + '%'}</td>
        return <td key={`${m}|${c}`} className={`num ${c === 'fcst' ? 'fw-bold' : ''} ${c === 'dev' ? (v > 0 ? 'positive' : v < 0 ? 'negative' : '') : ''}`}>{c === 'dev' ? fD(v) : fU(v)}</td>
      }) })}
      <td className="num fw-bold">{fU(n.fcst)}</td>
    </>)
    return (<>
      <td className="num">{n.stores}</td>
      <td className="num">{n.typeCounts.LfL}</td>
      <td className="num tag-lfl-num">{n.typeCounts.Ramp}</td>
      <td className="num tag-nso-num">{n.typeCounts.NSO}</td>
      <td className={`num ${b ? 'fw-bold' : ''}`}>{fU(n.base)}</td>
      <td className="num fw-bold">{fU(n.fcst)}</td>
      {devCell(n.dev, b)}
      {growthCell(n.growthEng, b)}
      {selMonths.map(m => { const i = MONTHS.indexOf(m); return (
        <td key={m} className="num sdt-month-cell">
          <div className="fw-bold">{fU(n.m[i])}</div>
          <div className="sdt-month-base">{fU(n.mb[i])}</div>
        </td>) })}
    </>)
  }

  const metricHeaders = () => {
    if (viewMode === 'summary') return (<>
      <Th {...th} col="stores" label="Stores" num />
      <Th {...th} col="base"   label={`Base (${unit})`}      num filterable />
      <Th {...th} col="fcst"   label={`Forecast (${unit})`}  num filterable />
      <Th {...th} col="dev"    label={`Deviation (${unit})`} num filterable />
      <Th {...th} col="growthEng" label="Growth %" num filterable />
    </>)
    if (viewMode === 'monthly') return (<>
      {selMonths.map(m => { const i = MONTHS.indexOf(m); return monthCols.map(c =>
        <Th {...th} key={`${m}|${c}`} col={`m${i}|${c}`} label={m} sub={COL_LABEL[c]} num />) })}
      <Th {...th} col="fcst" label="Total" sub="Forecast" num filterable />
    </>)
    return (<>
      <Th {...th} col="stores" label="Stores" num />
      <Th {...th} col="lfl"    label="LfL"    num />
      <Th {...th} col="ramp"   label="Ramp"   num />
      <Th {...th} col="nso"    label="NSO"    num />
      <Th {...th} col="base"   label="Base (Cr)"      num filterable />
      <Th {...th} col="fcst"   label="Forecast (Cr)"  num filterable />
      <Th {...th} col="dev"    label="Deviation (Cr)" num filterable />
      <Th {...th} col="growthEng" label="Growth %" num filterable />
      {selMonths.map(m => <Th {...th} key={m} col={`m${MONTHS.indexOf(m)}|fcst`} label={m} sub="Fcst / Base" num />)}
    </>)
  }

  if (loading) return <div className="out-loading">Loading detail data…</div>
  if (error)   return <div className="out-error">Error: {error}</div>
  if (!rows)   return null

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
            <button className="out-reset-btn" onClick={resetAll}>Reset filters{drillFilters ? ` (${drillFilters} in table)` : ''}</button>
          )}
          <span className="out-count">
            {grand.stores.toLocaleString()} <span className="out-count-label">stores</span> · {filtered.length.toLocaleString()} <span className="out-count-label">rows</span>
          </span>
        </div>
      </div>

      {/* ── View controls ── */}
      <div className="out-view-bar">
        <div className="out-view-toggle">
          <button className={viewMode === 'summary'  ? 'active' : ''} onClick={() => setViewMode('summary')}>Store summary</button>
          <button className={viewMode === 'monthly'  ? 'active' : ''} onClick={() => setViewMode('monthly')}>Monthly detail</button>
          <button className={viewMode === 'division' ? 'active' : ''} onClick={() => setViewMode('division')}>Division rollup</button>
        </div>
        {viewMode === 'monthly' && (
          <div className="out-col-opts">
            <span className="out-inline-label">Show</span>
            {[['fcst', 'Forecast'], ['base_fcst', 'Base + Forecast'], ['all', 'Base + Fcst + Dev + Gr%']].map(([v, l]) => (
              <button key={v} className={`out-col-btn ${colSet === v ? 'active' : ''}`} onClick={() => setColSet(v)}>{l}</button>
            ))}
          </div>
        )}
        {(viewMode === 'monthly' || viewMode === 'division') && <MonthSelect selected={selMonths} onChange={setSelMonths} />}
      </div>

      {/* ── Drill-down table ── */}
      <div className="card out-table-card sdt-card">
        <div className="sdt-toolbar">
          <DrillToolbar levels={levels} toggleLevel={d.toggleLevel} expandTo={n => d.expandTo(tree, n)} collapse={d.collapse}
                        lockedFirst={viewMode === 'division' ? 'Division' : undefined} />
          <span className="sdt-count" style={{ marginLeft: 'auto' }}>
            {flat.length} rows shown · values in ₹ {unit === 'Cr' ? 'Crore' : 'Lakhs'}{viewMode !== 'summary' && selMonths.length < MONTHS.length ? ` · ${selMonths.length} of 13 months` : ''}
          </span>
        </div>

        <div className="table-scroll sdt-scroll">
          <table className="stores-table sdt-table">
            <thead>
              <tr>
                <Th {...th} col="name" label={nameLabel} />
                <DimFilterHeaders hasFilter={hasFilter} openF={d.openF} />
                {metricHeaders()}
              </tr>
            </thead>
            <tbody>
              <tr className="sdt-grand">
                <td className="sdt-name"><strong>Grand total</strong></td>
                <td colSpan={LEVEL_KEYS.length} className="sdt-dim-cell" />
                {metricCells(grand, true)}
              </tr>
              {flat.map(n => (
                <tr key={n.id} className={`sdt-row d${n.depth}${!n.children.length ? ' leaf' : ''}`} onClick={() => n.children.length && d.toggleNode(tree, n.id)}>
                  {renderName(n)}
                  <td colSpan={LEVEL_KEYS.length} className="sdt-dim-cell" />
                  {metricCells(n, false)}
                </tr>
              ))}
              {!flat.length && <tr><td colSpan={40} className="sdt-empty">No rows match the current filters.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {d.openFilter && (LEVEL_KEYS.includes(d.openFilter.col)
        ? <HeaderFilter title={d.openFilter.col} options={options[d.openFilter.col]} selected={d.dimF[d.openFilter.col]}
            onChange={v => d.setDimF(f => ({ ...f, [d.openFilter.col]: v }))} onClose={d.closeF} anchor={d.openFilter.anchor} />
        : <HeaderFilter title={NUM_TITLES[d.openFilter.col]} range={numF[d.openFilter.col]} hint={`Applies to store totals (₹ ${unit === 'Cr' ? 'Cr' : 'L'} / %)`}
            onRange={v => setNumF(f => ({ ...f, [d.openFilter.col]: v }))} onClose={d.closeF} anchor={d.openFilter.anchor} />
      )}
    </div>
  )
}
