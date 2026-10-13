import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme } from '../theme'

// Which branch of the MRP stage the Sales Plan runs on (user, 2026-10-13: "Add a provision toggle if the user wants to
// go Article Name or MRP route", then "think of it as another parallel branch to MRP"). Both branches stay open; the
// route picks the one Reconciliation checks and the Sales Plan carries forward. Saved on the server, for everyone.
const API = '/api/planning/art-nm/settings'
const ROUTES = [['mrp', 'MRP', '/mrp-plan/output'], ['article', 'Article Name', '/art-plan/output']]

export function useRoute() {
  const [st, setSt] = useState(null)
  useEffect(() => {
    fetch(API).then(r => (r.ok ? r.json() : null)).catch(() => null).then(d => setSt(d || { route: 'mrp', grain: 'cluster' }))
  }, [])
  const save = patch => {
    setSt(s => ({ ...s, ...patch }))
    fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }).catch(() => {})
  }
  return [st, save]
}

export default function RouteBar({ here }) {
  const [st, save] = useRoute()
  const nav = useNavigate()
  if (!st) return null
  const other = ROUTES.find(r => r[0] !== here)
  return (
    <div data-no-undo style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14, position: 'relative', zIndex: 201 }}>
      <span style={{ fontSize: 12, fontWeight: 700, color: theme.textMuted, textTransform: 'uppercase', letterSpacing: 0.6 }}>Sales Plan route</span>
      <div role="radiogroup" aria-label="MRP stage route" style={{ display: 'flex', borderRadius: 7, overflow: 'hidden', border: `1px solid ${theme.border}` }}>
        {ROUTES.map(([k, label]) => (
          <button key={k} role="radio" aria-checked={st.route === k} onClick={() => save({ route: k })} style={{
            padding: '6px 16px', fontSize: 12, fontWeight: 600, cursor: 'pointer', border: 'none',
            background: st.route === k ? 'var(--st-btn,#A8CBB7)' : theme.surface,
            color: st.route === k ? 'var(--st-btn-text,#1F4D3A)' : theme.textMuted }}>{label}</button>
        ))}
      </div>
      <span style={{ fontSize: 11.5, color: st.route === here ? theme.success : theme.warning, fontWeight: 600 }}>
        {st.route === here ? 'This branch is the one the Sales Plan runs on' : `The Sales Plan runs on the ${ROUTES.find(r => r[0] === st.route)[1]} branch - this one is for reference`}
      </span>
      <button type="button" onClick={() => nav(other[2])} style={{ all: 'unset', cursor: 'pointer', fontSize: 12, color: theme.primary, textDecoration: 'underline' }}>
        {other[1]} Plan Output →
      </button>
    </div>
  )
}
