import { useState, useRef, useEffect } from 'react'
import { theme, alpha } from '../theme'

/**
 * Pivot-style multi-select slicer with search-inside.
 *
 * Props:
 *   items        — string[]          full list of options
 *   selected     — Set<string>       currently selected (empty Set = "all")
 *   onChange     — (Set<string>) => void
 *   label        — string            label when nothing / all selected  e.g. "All Stores"
 *   width        — number            trigger button min-width (default 160)
 *   placeholder  — string            search input placeholder
 *   accentColor  — string            optional override (default theme.primary)
 */
export default function SearchSlicer({
  items = [],
  selected,
  onChange,
  label = 'All',
  width = 160,
  placeholder = 'Search…',
  accentColor,
}) {
  const color = accentColor || theme.primary
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])

  const filtered = items.filter(i => i.toLowerCase().includes(q.toLowerCase()))
  const count    = selected.size

  const toggle = (item) => {
    const next = new Set(selected.size === 0 ? items : selected)
    if (next.has(item)) next.delete(item); else next.add(item)
    onChange(next.size === items.length ? new Set() : next)
  }

  const isChecked = (item) => selected.size === 0 || selected.has(item)

  const displayLabel = count === 0
    ? label
    : count === 1
      ? [...selected][0]
      : `${count} selected`

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'flex', alignItems: 'center', gap: 7,
          background: open ? theme.surfaceUp : theme.surface,
          border: `1px solid ${count > 0 ? color : theme.border}`,
          color: theme.textPrimary, borderRadius: 7,
          padding: '6px 12px', fontSize: 12, cursor: 'pointer', minWidth: width,
        }}
      >
        <span style={{ flex: 1, textAlign: 'left', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {displayLabel}
        </span>
        {count > 0 && (
          <span style={{ fontSize: 10, background: color, color: '#fff', borderRadius: 10, padding: '1px 6px', fontWeight: 700, flexShrink: 0 }}>
            {count}
          </span>
        )}
        <span style={{ fontSize: 10, color: theme.textMuted, flexShrink: 0 }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 200,
          background: theme.surface, border: `1px solid ${theme.border}`,
          borderRadius: 9, boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
          width: Math.max(width, 220), maxHeight: 340, display: 'flex', flexDirection: 'column',
        }}>
          {/* Search */}
          <div style={{ padding: '10px 12px 6px', borderBottom: `1px solid ${theme.border}` }}>
            <input
              autoFocus
              placeholder={placeholder}
              value={q}
              onChange={e => setQ(e.target.value)}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: theme.surfaceAlt, border: `1px solid ${theme.border}`,
                color: theme.textPrimary, borderRadius: 6, padding: '5px 10px',
                fontSize: 12, outline: 'none',
              }}
            />
          </div>

          {/* Select All / Clear */}
          <div style={{ display: 'flex', gap: 6, padding: '6px 12px', borderBottom: `1px solid ${theme.border}` }}>
            <button
              onClick={() => onChange(new Set())}
              style={{ flex: 1, fontSize: 11, padding: '3px 0', borderRadius: 5, cursor: 'pointer', background: 'transparent', border: `1px solid ${theme.border}`, color: theme.textMuted }}
            >Select All</button>
            <button
              onClick={() => onChange(new Set(items.length > 0 ? [] : []))}
              style={{ flex: 1, fontSize: 11, padding: '3px 0', borderRadius: 5, cursor: 'pointer', background: 'transparent', border: `1px solid ${theme.border}`, color: theme.textMuted }}
            >Clear</button>
          </div>

          {/* List */}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filtered.length === 0 ? (
              <div style={{ padding: 14, textAlign: 'center', color: theme.textMuted, fontSize: 12 }}>No match</div>
            ) : filtered.map(item => (
              <label key={item} style={{
                display: 'flex', alignItems: 'center', gap: 9,
                padding: '7px 14px', cursor: 'pointer', fontSize: 12,
                color: isChecked(item) ? theme.textPrimary : theme.textMuted,
                background: selected.has(item) ? `${alpha(color,'12')}` : 'transparent',
                borderBottom: `1px solid ${theme.border}`,
              }}>
                <input
                  type="checkbox"
                  checked={isChecked(item)}
                  onChange={() => toggle(item)}
                  style={{ accentColor: color, width: 13, height: 13, cursor: 'pointer' }}
                />
                {item}
              </label>
            ))}
          </div>

          {/* Footer count */}
          {filtered.length > 0 && (
            <div style={{ padding: '6px 14px', borderTop: `1px solid ${theme.border}`, fontSize: 11, color: theme.textMuted }}>
              {filtered.length} of {items.length} shown
            </div>
          )}
        </div>
      )}
    </div>
  )
}
