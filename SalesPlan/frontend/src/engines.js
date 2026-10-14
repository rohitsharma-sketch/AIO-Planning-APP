import { useEffect, useState } from 'react'

// On/off per optional engine (user, 2026-10-14: "for optional engines give a toggle for the user so the user can
// activate and deactive the engine if it is to be used") - kept on the server (engines/engine_switch.py) so the plan
// readers skip a switched-off engine's output; pages listen for 'sp-engines' so the sidebar switch reaches them at once.
const API = '/api/planning/final-results/engines'
let cache = null   // {attr_correction, base_correction, pww, sor} - null until the first answer (treated as all off: opted out is the default)

const publish = e => { cache = e; window.dispatchEvent(new CustomEvent('sp-engines', { detail: e })) }

export async function setEngine(key, on) {
  const r = await fetch(`${API}/${key}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on }) })
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  publish((await r.json()).engines)
}

export function useEngines() {
  const [e, set] = useState(cache)
  useEffect(() => {
    const h = ev => set(ev.detail)
    window.addEventListener('sp-engines', h)
    if (!cache) fetch(API).then(r => r.ok ? r.json() : null).then(j => j && publish(j.engines)).catch(() => {})
    return () => window.removeEventListener('sp-engines', h)
  }, [])
  const on = k => !!e?.[k]
  return [on, setEngine, !!e]
}
