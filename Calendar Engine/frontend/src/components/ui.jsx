import { useRef, useEffect, useState } from 'react'

// Small dropdown menu on a native <details> (2026-10-07 declutter). Contents
// stay in the DOM while closed. Closes on outside click, on Escape (focus goes
// back to the summary) and, unless keepOpen, after any item button is clicked.
export function Menu({ label, children, className = '', title, keepOpen = false }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    function onDown(e) {
      if (!el.open || el.contains(e.target)) return
      // Commit any field being edited inside (e.g. the cluster rename box saves on blur).
      if (el.contains(document.activeElement)) document.activeElement.blur()
      el.open = false
    }
    function onKey(e) {
      if (e.key !== 'Escape' || !el.open) return
      // Deferred so a field's own Escape handler (e.g. revert a draft) re-renders first.
      setTimeout(() => { el.open = false; el.querySelector('summary').focus() })
    }
    document.addEventListener('pointerdown', onDown, true)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown, true)
      document.removeEventListener('keydown', onKey)
    }
  }, [])
  function onPopClick(e) {
    if (!keepOpen && e.target.closest('button')) setTimeout(() => { if (ref.current) ref.current.open = false })
  }
  return (
    <details ref={ref} className={`ce-menu ${className}`}>
      <summary title={title}>{label} <span aria-hidden="true" className="ce-menu-caret">▾</span></summary>
      <div className="ce-menu-pop" onClick={onPopClick}>{children}</div>
    </details>
  )
}

// Boolean UI preference remembered per browser. Keys must start with 'cal.'
// (Calendar, AOP and Sales Plan share the 8010 origin).
export function useStoredFlag(key, initial = false) {
  const [on, setOn] = useState(() => {
    try { const v = localStorage.getItem(key); return v == null ? initial : v === '1' } catch { return initial }
  })
  function set(v) {
    setOn(v)
    try { localStorage.setItem(key, v ? '1' : '0') } catch {}
  }
  return [on, set]
}
