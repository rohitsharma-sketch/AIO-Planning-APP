import { useEffect, useRef, useState } from 'react'
import { theme, alpha } from '../theme'

// Excel's AutoFilter list (user, 2026-10-13: "the filters should be individual filters - excel styled", "add the same
// Excel filters to the Growth Matrix page", then "make it more simplistic and more true to their excel counterparts"):
// Sort A to Z / Z to A, Clear Filter From "x", Search, (Select All), the values, OK / Cancel - and, as in a PivotTable's
// "Row Labels" list, an optional Select field box. `load` gives the column's values (an array, or a function returning
// one or a promise) - the caller passes the values left by the OTHER filters, as Excel does. All ticked = no filter.
// onDone(undefined) = cancelled, onDone([]) = filter off, onDone([...]) = keep these. onSort('az' | 'za' | null).
export default function ExcelFilter({ title, anchor, load, picked, onDone, numeric, sort, onSort, fields, field, onField }) {
  const [vals, setVals] = useState(null)
  const [sel, setSel] = useState(() => new Set())
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const box = useRef(null)
  useEffect(() => {
    Promise.resolve(typeof load === 'function' ? load() : load)
      .then(v => { v = v || []; setVals(v); setSel(new Set(picked ? picked.filter(x => v.includes(x)) : v)) })
      .catch(e => setErr(e.message || String(e)))
    const out = e => { if (box.current && !box.current.contains(e.target) && !(anchor && anchor.contains(e.target))) onDone(undefined) }
    const esc = e => { if (e.key === 'Escape') onDone(undefined) }
    document.addEventListener('mousedown', out)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', out); document.removeEventListener('keydown', esc) }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  const rc = anchor ? anchor.getBoundingClientRect() : { left: 100, bottom: 100 }
  const left = Math.max(8, Math.min(rc.left, window.innerWidth - 276))
  const top = Math.min(rc.bottom + 2, window.innerHeight - 160)
  const shown = (vals || []).filter(v => String(v).toLowerCase().includes(q.trim().toLowerCase()))
  const all = shown.length > 0 && shown.every(v => sel.has(v))
  const some = shown.some(v => sel.has(v))
  const flipAll = () => setSel(s0 => { const n = new Set(s0); shown.forEach(v => (all ? n.delete(v) : n.add(v))); return n })
  const flip = v => setSel(s0 => { const n = new Set(s0); n.has(v) ? n.delete(v) : n.add(v); return n })
  // Excel: OK while searching keeps just the ticked search results; every value ticked = the filter is off
  const chosen = q ? shown.filter(v => sel.has(v)) : [...sel]
  const ok = () => onDone(vals && chosen.length === vals.length ? [] : chosen)
  const item = on => ({ all: 'unset', display: 'block', width: '100%', boxSizing: 'border-box', padding: '4px 8px', borderRadius: 3, cursor: 'pointer',
    fontSize: 12, background: on ? alpha(theme.primary, '16') : 'transparent', fontWeight: on ? 600 : 400 })
  const btn = { padding: '3px 14px', borderRadius: 3, border: `1px solid ${theme.border}`, background: theme.surface, fontSize: 12, cursor: 'pointer', minWidth: 64 }
  const sep = <div style={{ borderTop: `1px solid ${theme.border}`, margin: '5px 0' }} />
  return (
    <div ref={box} data-no-undo role="dialog" aria-label={`Filter ${title}`}
      style={{ position: 'fixed', top, left, width: 260, zIndex: 1000, background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 4, boxShadow: '0 8px 24px rgba(0,0,0,.18)', padding: 6, textTransform: 'none', letterSpacing: 0, fontWeight: 400, color: theme.textPrimary, textAlign: 'left', fontSize: 12 }}>
      {fields && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 4px 6px' }}>
          Select field:
          <select value={field} onChange={e => onField(e.target.value)} autoFocus style={{ flex: 1, fontSize: 12, padding: '2px 4px' }}>
            {fields.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
        </label>
      )}
      {onSort && (<>
        <button type="button" style={item(sort === 'az')} onClick={() => onSort(sort === 'az' ? null : 'az')}>↑ {numeric ? 'Sort Smallest to Largest' : 'Sort A to Z'}</button>
        <button type="button" style={item(sort === 'za')} onClick={() => onSort(sort === 'za' ? null : 'za')}>↓ {numeric ? 'Sort Largest to Smallest' : 'Sort Z to A'}</button>
        {sep}
      </>)}
      <button type="button" disabled={!picked} onClick={() => onDone([])} style={{ ...item(false), color: picked ? theme.textPrimary : theme.textMuted, cursor: picked ? 'pointer' : 'default' }}>
        ✕ Clear Filter From "{title}"
      </button>
      {sep}
      <input type="search" autoFocus={!fields} value={q} onChange={e => setQ(e.target.value)} placeholder="Search" aria-label={`Search ${title}`}
        style={{ width: '100%', boxSizing: 'border-box', padding: '4px 6px', borderRadius: 3, border: `1px solid ${theme.border}`, fontSize: 12, margin: '2px 0 4px' }} />
      {err && <div style={{ color: theme.danger, fontSize: 12, padding: 4 }}>Could not load the list: {err}</div>}
      {!vals && !err && <div style={{ color: theme.textMuted, fontSize: 12, padding: '6px 4px' }}>Loading…</div>}
      {vals && (
        <div style={{ maxHeight: 230, overflow: 'auto', border: `1px solid ${theme.border}`, borderRadius: 3, padding: '3px 6px' }}>
          <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer', padding: '1px 0' }}>
            <input type="checkbox" checked={all} ref={el => { if (el) el.indeterminate = some && !all }} onChange={flipAll} />
            {q ? '(Select All Search Results)' : '(Select All)'}
          </label>
          {shown.map(v => (
            <label key={v} style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer', padding: '1px 0' }}>
              <input type="checkbox" checked={sel.has(v)} onChange={() => flip(v)} />{v}
            </label>
          ))}
          {!shown.length && <div style={{ fontSize: 12, color: theme.textMuted, padding: '3px 0' }}>No matches</div>}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginTop: 6 }}>
        <button type="button" disabled={!vals || !chosen.length} onClick={ok}
          style={{ ...btn, background: theme.primary, color: '#fff', borderColor: theme.primary, fontWeight: 600, opacity: !vals || !chosen.length ? 0.5 : 1 }}>OK</button>
        <button type="button" style={btn} onClick={() => onDone(undefined)}>Cancel</button>
      </div>
    </div>
  )
}

// Excel's little drop-down button on a column heading: ▾ normally, a funnel once the column is filtered (and an arrow
// once it is sorted).
export function FilterButton({ active, sorted, onClick, label, title }) {
  return (
    <button type="button" data-no-undo onClick={e => { e.stopPropagation(); onClick(e.currentTarget) }} aria-haspopup="dialog" aria-label={label} title={title}
      style={{ all: 'unset', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 1, minWidth: 14, height: 14,
               marginLeft: 4, padding: '0 2px', verticalAlign: 'middle', borderRadius: 2, border: `1px solid ${active || sorted ? theme.primary : theme.border}`,
               background: active ? alpha(theme.primary, '18') : theme.surface, color: active || sorted ? theme.primary : theme.textMuted, fontSize: 9, lineHeight: 1 }}>
      {active && <svg width="8" height="8" viewBox="0 0 10 10" aria-hidden="true"><path d="M0 0h10L6 5v5L4 9V5z" fill="currentColor" /></svg>}
      {sorted && <span aria-hidden="true">{sorted === 'az' ? '↑' : '↓'}</span>}
      {!active && !sorted && <span aria-hidden="true">▾</span>}
    </button>
  )
}


// The Filters row (user, 2026-10-13: "multi selection filters are required"): one multi-select dropdown per field,
// captioned (All) / the value / (Multiple Items) n, and Clear all. fields = [[key, label]]; filters = {key: [values]};
// values(key) = that field's values inside the OTHER filters. `children` sit at the end (e.g. "showing x of y").
export function FiltersRow({ fields, filters, onChange, values, children, style }) {
  const [edit, setEdit] = useState(null)   // {key, label, anchor}
  const n = Object.keys(filters).length
  const caption = k => (!filters[k] ? '(All)' : filters[k].length === 1 ? filters[k][0] : `(Multiple Items) ${filters[k].length}`)
  return (
    <div data-no-undo style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', ...style }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginRight: 4 }}>Filters</span>
      {fields.map(([k, label]) => (
        <button key={k} type="button" aria-haspopup="dialog" onClick={e => { const el = e.currentTarget; setEdit(x => (x && x.key === k ? null : { key: k, label, anchor: el })) }}
          title={filters[k] ? filters[k].join(', ') : `All ${label.toLowerCase()}`}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 8px', borderRadius: 4, fontSize: 12, cursor: 'pointer', maxWidth: 260,
                   border: `1px solid ${filters[k] ? theme.primary : theme.border}`, background: filters[k] ? alpha(theme.primary, '12') : theme.surface, color: theme.textPrimary }}>
          <span style={{ color: theme.textMuted }}>{label}</span>
          <b style={{ fontWeight: filters[k] ? 700 : 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{caption(k)}</b>
          <span aria-hidden="true" style={{ color: theme.textMuted, fontSize: 10 }}>▾</span>
        </button>
      ))}
      {n > 0 && <button type="button" onClick={() => onChange({})} style={{ all: 'unset', cursor: 'pointer', fontSize: 12, color: theme.textMuted, textDecoration: 'underline' }}>Clear all</button>}
      {children}
      {edit && <ExcelFilter key={edit.key + JSON.stringify(filters)} title={edit.label} anchor={edit.anchor} picked={filters[edit.key]}
        load={() => values(edit.key)}
        onDone={vals => {
          if (vals !== undefined) { const f = { ...filters }; if (vals.length) f[edit.key] = vals; else delete f[edit.key]; onChange(f) }
          setEdit(null)
        }} />}
    </div>
  )
}
