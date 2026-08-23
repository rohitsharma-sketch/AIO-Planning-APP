// Column sort + Excel-style filter for flat editable grids (configure page).
import { useState, useEffect, useMemo } from 'react'
import { HeaderFilter, cmpStr, hasNum } from './drill'

const str = v => (v == null ? '' : String(v))
const numOf = v => (typeof v === 'number' ? v : (typeof v === 'string' && v.trim() !== '' && !isNaN(Number(v)) ? Number(v) : null))

/**
 * rows: array of records; ncol: number of columns; getCell(row, j) → cell value.
 * Returns visible rows as [{ r, i }] (i = original index) after filters + sort.
 */
export function useGrid(rows, ncol, { getCell = (r, j) => r[j], resetKey } = {}) {
  const [sortCol, setSortCol] = useState(null)
  const [sortDir, setSortDir] = useState(1)
  const [colF, setColF]       = useState({})   // j → [values]  ([] / undefined = all)
  const [numF, setNumF]       = useState({})   // j → {min,max}
  const [openFilter, setOpenFilter] = useState(null)

  useEffect(() => { setSortCol(null); setSortDir(1); setColF({}); setNumF({}); setOpenFilter(null) }, [resetKey])

  // Column is numeric when ≥80% of its non-empty cells parse as numbers
  const numeric = useMemo(() => {
    const out = []
    for (let j = 0; j < ncol; j++) {
      let n = 0, k = 0
      for (const r of rows) { const v = getCell(r, j); if (v == null || str(v).trim() === '') continue; n++; if (numOf(v) != null) k++ }
      out[j] = n > 0 && k / n >= 0.8
    }
    return out
  }, [rows, ncol]) // eslint-disable-line

  const options = useMemo(() => {
    const out = {}
    for (let j = 0; j < ncol; j++) {
      if (numeric[j]) continue
      const c = new Map()
      for (const r of rows) { const v = str(getCell(r, j)); c.set(v, (c.get(v) || 0) + 1) }
      out[j] = [...c].map(([value, count]) => ({ value: value === '' ? '(blank)' : value, raw: value, count })).sort((a, b) => cmpStr(a.value, b.value))
    }
    return out
  }, [rows, ncol, numeric]) // eslint-disable-line

  const visible = useMemo(() => {
    let out = rows.map((r, i) => ({ r, i }))
    for (const [j, sel] of Object.entries(colF)) {
      if (!sel?.length) continue
      const set = new Set(sel.map(v => (v === '(blank)' ? '' : v)))
      out = out.filter(({ r }) => set.has(str(getCell(r, +j))))
    }
    for (const [j, rg] of Object.entries(numF)) {
      if (!hasNum(rg)) continue
      out = out.filter(({ r }) => { const v = numOf(getCell(r, +j)); if (v == null) return false; return (rg.min === '' || v >= +rg.min) && (rg.max === '' || v <= +rg.max) })
    }
    if (sortCol != null) {
      const j = sortCol
      out = [...out].sort((a, b) => {
        const va = getCell(a.r, j), vb = getCell(b.r, j)
        const ea = va == null || str(va).trim() === '', eb = vb == null || str(vb).trim() === ''
        if (ea && eb) return 0
        if (ea) return 1
        if (eb) return -1
        const na = numOf(va), nb = numOf(vb)
        if (na != null && nb != null) return sortDir * (na - nb)
        return sortDir * cmpStr(va, vb)
      })
    }
    return out
  }, [rows, colF, numF, sortCol, sortDir]) // eslint-disable-line

  const toggleSort = j => { if (sortCol === j) setSortDir(d => -d); else { setSortCol(j); setSortDir(1) } }
  const openF = (j, e) => { e.stopPropagation(); const anchor = e.currentTarget.getBoundingClientRect(); setOpenFilter(o => (o?.col === j ? null : { col: j, anchor })) }
  const closeF = () => setOpenFilter(null)
  const hasFilter = j => (numeric[j] ? hasNum(numF[j]) : (colF[j]?.length > 0))
  const activeFilters = [...Array(ncol).keys()].filter(hasFilter).length
  const clearAll = () => { setColF({}); setNumF({}); setSortCol(null) }

  return { visible, sortCol, sortDir, toggleSort, colF, setColF, numF, setNumF, numeric, options, openFilter, openF, closeF, hasFilter, activeFilters, clearAll }
}

// Header cell with sort (click label) + filter (▼)
export function GridTh({ j, label, grid, num, filterable = true, className = '', style }) {
  const sorted = grid.sortCol === j
  return (
    <th className={`${num || grid.numeric[j] ? 'num' : ''}${sorted ? ' sorted' : ''} ${className}`} style={style}>
      <div className="sdt-th">
        <button className="sdt-th-sort" onClick={() => grid.toggleSort(j)} title="Sort">
          {label}<span className={`sdt-sort-ic${sorted ? ' on' : ''}`}>{sorted ? (grid.sortDir < 0 ? '↓' : '↑') : '↕'}</span>
        </button>
        {filterable && <button className={`sdt-th-filter${grid.hasFilter(j) ? ' on' : ''}`} onClick={e => grid.openF(j, e)} title="Filter">▼</button>}
      </div>
    </th>
  )
}

// The open dropdown for a grid (render once per table)
export function GridFilter({ grid, labels }) {
  const o = grid.openFilter
  if (!o) return null
  const j = o.col, title = labels?.[j] ?? `Column ${j + 1}`
  return grid.numeric[j]
    ? <HeaderFilter title={title} range={grid.numF[j] || { min: '', max: '' }} hint="Numeric range" anchor={o.anchor} onClose={grid.closeF}
        onRange={v => grid.setNumF(f => ({ ...f, [j]: v }))} />
    : <HeaderFilter title={title} options={grid.options[j] || []} selected={grid.colF[j] || []} anchor={o.anchor} onClose={grid.closeF}
        onChange={v => grid.setColF(f => ({ ...f, [j]: v }))} />
}
