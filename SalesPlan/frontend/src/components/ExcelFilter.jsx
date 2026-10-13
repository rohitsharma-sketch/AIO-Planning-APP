import { useEffect, useRef, useState } from 'react'
import { theme } from '../theme'

// One column's Excel-style filter (user, 2026-10-13: "the filters should be individual filters - excel styled", then
// "add the same Excel filters to the Growth Matrix page"): search, (Select all) / (Select all search results), ticks,
// OK / Cancel, Clear filter. `load` gives the column's values (an array, or a function returning one or a promise) -
// the caller passes the values left by the OTHER columns' filters, as Excel does. All ticked = no filter.
// onDone(undefined) = cancelled, onDone([]) = filter off, onDone([...]) = keep these.
export default function ExcelFilter({ title, anchor, load, picked, onDone }) {
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
  const left = Math.max(8, Math.min(rc.left, window.innerWidth - 296))
  const top = Math.min(rc.bottom + 4, window.innerHeight - 120)
  const shown = (vals || []).filter(v => String(v).toLowerCase().includes(q.trim().toLowerCase()))
  const all = shown.length > 0 && shown.every(v => sel.has(v))
  const some = shown.some(v => sel.has(v))
  const flipAll = () => setSel(s0 => { const n = new Set(s0); shown.forEach(v => (all ? n.delete(v) : n.add(v))); return n })
  const flip = v => setSel(s0 => { const n = new Set(s0); n.has(v) ? n.delete(v) : n.add(v); return n })
  // Excel: OK while searching keeps just the ticked search results; every value ticked = the filter is off
  const chosen = q ? shown.filter(v => sel.has(v)) : [...sel]
  const ok = () => onDone(vals && chosen.length === vals.length ? [] : chosen)
  const btn = { padding: '4px 12px', borderRadius: 6, border: `1px solid ${theme.border}`, background: theme.surface, fontSize: 12, cursor: 'pointer' }
  return (
    <div ref={box} data-no-undo role="dialog" aria-label={`Filter ${title}`}
      style={{ position: 'fixed', top, left, width: 280, zIndex: 1000, background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 8, boxShadow: '0 12px 30px rgba(0,0,0,.18)', padding: 10, textTransform: 'none', letterSpacing: 0, fontWeight: 400, color: theme.textPrimary, textAlign: 'left', fontSize: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
        <b style={{ fontSize: 12, flex: 1 }}>Filter · {title}</b>
        {picked && <button type="button" onClick={() => onDone([])} style={{ all: 'unset', cursor: 'pointer', fontSize: 11.5, color: theme.primary, textDecoration: 'underline' }}>Clear filter</button>}
      </div>
      <input type="search" autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search" aria-label={`Search ${title}`}
        style={{ width: '100%', boxSizing: 'border-box', padding: '5px 8px', borderRadius: 6, border: `1px solid ${theme.border}`, fontSize: 12, marginBottom: 6 }} />
      {err && <div style={{ color: theme.danger, fontSize: 12 }}>Could not load the list: {err}</div>}
      {!vals && !err && <div style={{ color: theme.textMuted, fontSize: 12, padding: '6px 2px' }}>Loading…</div>}
      {vals && (
        <div style={{ maxHeight: 260, overflow: 'auto', border: `1px solid ${theme.border}`, borderRadius: 6, padding: '4px 6px' }}>
          <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer', fontWeight: 600, padding: '2px 0' }}>
            <input type="checkbox" checked={all} ref={el => { if (el) el.indeterminate = some && !all }} onChange={flipAll} />
            {q ? '(Select all search results)' : '(Select all)'}
          </label>
          {shown.map(v => (
            <label key={v} style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center', cursor: 'pointer', padding: '2px 0' }}>
              <input type="checkbox" checked={sel.has(v)} onChange={() => flip(v)} />{v}
            </label>
          ))}
          {!shown.length && <div style={{ fontSize: 12, color: theme.textMuted, padding: '4px 0' }}>Nothing matches.</div>}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6, marginTop: 8 }}>
        <button type="button" style={btn} onClick={() => onDone(undefined)}>Cancel</button>
        <button type="button" disabled={!vals || !chosen.length} onClick={ok}
          style={{ ...btn, background: theme.primary, color: '#fff', borderColor: theme.primary, fontWeight: 600, opacity: !vals || !chosen.length ? 0.5 : 1 }}>OK</button>
      </div>
    </div>
  )
}
