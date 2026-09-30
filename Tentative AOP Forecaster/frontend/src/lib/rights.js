import { useEffect, useState } from 'react'

// Actions an admin can switch off per person (Users & access > Access to important actions). Asked once per page
// load. Standalone :8000 has no sign-in, so the answer there is null = show everything (the server still checks).
let asked = null
const ask = () => (asked ??= fetch('/api/auth/rights', { credentials: 'same-origin' })
  .then(r => (r.ok ? r.json() : null)).then(d => d?.rights ?? null).catch(() => null))

export function useCan(right) {
  const [rights, setRights] = useState(null)
  useEffect(() => { ask().then(setRights) }, [])
  return !rights || rights.includes(right)
}
