import { useEffect, useState } from 'react'

// Store / Cluster switch (user, 2026-10-12: "a switch in the planning engine for working as Cluster or Store") - one
// choice for every page, kept in this browser; pages listen for 'sp-grain' so they follow the header at once.
const KEY = 'sp.grain'

export function getGrain() {
  try { return localStorage.getItem(KEY) === 'cluster' ? 'cluster' : 'store' } catch { return 'store' }
}

export function setGrain(g) {
  try { localStorage.setItem(KEY, g) } catch { /* private window: this page only */ }
  window.dispatchEvent(new CustomEvent('sp-grain', { detail: g }))
}

export function useGrain() {
  const [g, set] = useState(getGrain)
  useEffect(() => {
    const h = (e) => set(e.detail)
    window.addEventListener('sp-grain', h)
    return () => window.removeEventListener('sp-grain', h)
  }, [])
  return [g, setGrain]
}
