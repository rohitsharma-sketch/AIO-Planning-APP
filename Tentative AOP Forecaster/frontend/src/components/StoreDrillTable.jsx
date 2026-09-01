import { useState, useMemo } from 'react'
import { tagClass, MONTHS } from '../lib/tags'
import {
  LEVELS, LEVEL_KEYS, EMPTY_DIM, fmt1, fmtPct, aggregate, buildTree, sortTree, flatten,
  dimOptions, filterLeaves, hasNum, HeaderFilter, Th, DimFilterHeaders, DrillToolbar, useDrill,
} from '../lib/drill'

const EMPTY_NUM  = { base: { min: '', max: '' }, fcst: { min: '', max: '' }, growth: { min: '', max: '' } }
const NUM_TITLES = { base: 'Base', fcst: 'Forecast', growth: 'Growth %' }

// `leaves`: normalised store×division rows in ₹ Cr (see lib/tags.js toLeaf). null = loading.
export default function StoreDrillTable({ leaves, error, runKey }) {
  const [numF, setNumF]     = useState(EMPTY_NUM)
  const [search, setSearch] = useState('')
  const [showMonths, setShowMonths] = useState(false)
  const d = useDrill({ defaultSort: 'fcst', resetKey: runKey })
  const { levels, sortCol, sortDir, dimF } = d

  const options  = useMemo(() => dimOptions(leaves || []), [leaves])
  const filtered = useMemo(() => filterLeaves(leaves || [], { dimF, search, numF }), [leaves, dimF, search, numF])
  const tree = useMemo(() => {
    const val = n => sortCol === 'name' ? n.name : sortCol.startsWith('m') ? n.m[+sortCol.slice(1)] : sortCol === 'share' ? n.fcst : n[sortCol]
    return sortTree(buildTree(filtered, levels), val, sortDir)
  }, [filtered, levels, sortCol, sortDir])
  const grand = useMemo(() => aggregate(filtered), [filtered])
  const exp   = d.expandedFor(tree)
  const rows  = useMemo(() => flatten(tree, exp), [tree, exp])

  const hasFilter = col => LEVEL_KEYS.includes(col) ? dimF[col].length > 0 : hasNum(numF[col])
  const activeFilters = [...LEVEL_KEYS, 'base', 'fcst', 'growth'].filter(hasFilter).length + (search ? 1 : 0)
  const clearAll = () => { d.setDimF(EMPTY_DIM); setNumF(EMPTY_NUM); setSearch('') }
  const th = { sortCol, sortDir, toggleSort: d.toggleSort, hasFilter, openF: d.openF }

  const head = <h3 className="section-title">Store drill-down  (₹ Cr)</h3>
  if (error)   return <div className="card table-card">{head}<div className="sdt-error">{error}</div></div>
  if (!leaves) return <div className="card table-card">{head}<div className="sdt-loading">Loading detail data…</div></div>

  const nameLabel = levels.map(k => LEVELS.find(l => l.key === k).label).join(' › ')
  const nCols = 1 + LEVEL_KEYS.length + 5 + (showMonths ? 13 : 0)

  return (
    <div className="card table-card sdt-card">
      <div className="sdt-head">
        {head}
        <div className="sdt-count">{rows.length} rows · {grand.stores} stores{activeFilters ? ` · ${activeFilters} filter${activeFilters > 1 ? 's' : ''} active` : ''}</div>
      </div>

      <div className="sdt-toolbar">
        <DrillToolbar levels={levels} toggleLevel={d.toggleLevel} expandTo={n => d.expandTo(tree, n)} collapse={d.collapse} />
        <label className="sdt-chip sdt-toggle">
          <input type="checkbox" checked={showMonths} onChange={e => setShowMonths(e.target.checked)} /> Monthly forecast
        </label>
        <div className="sdt-search-wrap">
          <input className="sdt-search" placeholder="Search store / cluster / tag…" value={search} onChange={e => setSearch(e.target.value)} />
          {search && <button className="sdt-search-x" onClick={() => setSearch('')}>×</button>}
        </div>
        {activeFilters > 0 && <button className="sdt-reset" onClick={clearAll}>Clear filters</button>}
      </div>

      <div className="table-scroll sdt-scroll">
        <table className="stores-table sdt-table">
          <thead>
            <tr>
              <Th {...th} col="name" label={nameLabel} filterable={false} />
              <DimFilterHeaders hasFilter={hasFilter} openF={d.openF} />
              <Th {...th} col="stores" label="Stores"   num filterable={false} />
              <Th {...th} col="base"   label="Base"     num filterable />
              <Th {...th} col="fcst"   label="Forecast" num filterable />
              <Th {...th} col="growth" label="Growth"   num filterable />
              <Th {...th} col="share"  label="Share"    num filterable={false} />
              {showMonths && MONTHS.map((m, i) => <Th {...th} key={m} col={`m${i}`} label={m} num filterable={false} />)}
            </tr>
          </thead>
          <tbody>
            <tr className="sdt-grand">
              <td className="sdt-name"><strong>Grand total</strong></td>
              <td colSpan={LEVEL_KEYS.length} className="sdt-dim-cell" />
              <td className="num">{grand.stores}</td>
              <td className="num">₹{fmt1(grand.base)}</td>
              <td className="num fw-bold">₹{fmt1(grand.fcst)}</td>
              <td className="num">{fmtPct(grand.growth)}</td>
              <td className="num">100.0%</td>
              {showMonths && grand.m.map((v, i) => <td key={i} className="num">{fmt1(v)}</td>)}
            </tr>
            {rows.map(n => {
              const isLeaf = !n.children.length
              const open = exp.has(n.id)
              return (
                <tr key={n.id} className={`sdt-row d${n.depth}${isLeaf ? ' leaf' : ''}`} onClick={() => !isLeaf && d.toggleNode(tree, n.id)}>
                  <td className="sdt-name">
                    <span className="sdt-indent" style={{ width: n.depth * 18 }} />
                    <span className={`sdt-caret${isLeaf ? ' none' : open ? ' open' : ''}`}>&gt;</span>
                    {n.level === 'Tag'   ? <span className={`tag ${tagClass(n.name)}`}>{n.name}</span>
                   : n.level === 'Store' ? <span className="store-name">{n.name}</span>
                   : <span>{n.name}</span>}
                    <span className="sdt-level-hint">{n.level}</span>
                  </td>
                  <td colSpan={LEVEL_KEYS.length} className="sdt-dim-cell" />
                  <td className="num">{n.stores}</td>
                  <td className="num">₹{fmt1(n.base)}</td>
                  <td className="num fw-bold">₹{fmt1(n.fcst)}</td>
                  <td className={`num ${n.growth == null ? 'muted' : n.growth >= 0 ? 'positive' : 'negative'}`}>{fmtPct(n.growth)}</td>
                  <td className="num muted">{grand.fcst ? (n.fcst / grand.fcst * 100).toFixed(1) + '%' : '—'}</td>
                  {showMonths && n.m.map((v, i) => <td key={i} className="num">{fmt1(v)}</td>)}
                </tr>
              )
            })}
            {!rows.length && <tr><td colSpan={nCols} className="sdt-empty">No rows match the current filters.</td></tr>}
          </tbody>
        </table>
      </div>

      {d.openFilter && (LEVEL_KEYS.includes(d.openFilter.col)
        ? <HeaderFilter title={d.openFilter.col} options={options[d.openFilter.col]} selected={dimF[d.openFilter.col]}
            onChange={v => d.setDimF(f => ({ ...f, [d.openFilter.col]: v }))} onClose={d.closeF} anchor={d.openFilter.anchor} />
        : <HeaderFilter title={NUM_TITLES[d.openFilter.col]} range={numF[d.openFilter.col]} hint="Applies to store totals (₹ Cr / %)"
            onRange={v => setNumF(f => ({ ...f, [d.openFilter.col]: v }))} onClose={d.closeF} anchor={d.openFilter.anchor} />
      )}
    </div>
  )
}
