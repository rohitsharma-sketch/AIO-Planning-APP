import { useState, useRef, useEffect } from 'react'
import './ThemeSelector.css'

const THEMES = [
  { id: 'classic', label: 'Classic Navy',       primary: '#1F3864', accent: '#4472C4' },
  { id: 'emerald', label: 'Slate & Emerald',     primary: '#1E293B', accent: '#10B981' },
  { id: 'amber',   label: 'Midnight & Amber',    primary: '#0F172A', accent: '#F59E0B' },
  { id: 'coral',   label: 'Deep Purple & Coral', primary: '#3B1F6A', accent: '#F4845F' },
  { id: 'forest',  label: 'Forest & Gold',       primary: '#14532D', accent: '#D97706' },
]

export default function ThemeSelector({ current, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef()

  useEffect(() => {
    function handler(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const active = THEMES.find(t => t.id === current) || THEMES[0]

  return (
    <div className="theme-selector" ref={ref}>
      <button className="theme-trigger" onClick={() => setOpen(o => !o)} title="Change theme">
        <span className="theme-swatch-pair">
          <span className="swatch" style={{ background: active.primary }} />
          <span className="swatch" style={{ background: active.accent }} />
        </span>
        <span className="theme-label">{active.label}</span>
        <span className={`theme-chevron ${open ? 'open' : ''}`}>v</span>
      </button>

      {open && (
        <div className="theme-dropdown">
          <div className="theme-dropdown-title">Theme</div>
          {THEMES.map(t => (
            <button
              key={t.id}
              className={`theme-option ${t.id === current ? 'active' : ''}`}
              onClick={() => { onChange(t.id); setOpen(false) }}
            >
              <span className="theme-swatch-pair">
                <span className="swatch" style={{ background: t.primary }} />
                <span className="swatch" style={{ background: t.accent }} />
              </span>
              <span>{t.label}</span>
              {t.id === current && <span className="theme-check">Selected</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
