import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { theme, alpha } from '../theme'

// Which branch of the MRP stage the Sales Plan runs on (user, 2026-10-13: "Add a provision toggle if the user wants to
// go Article Name or MRP route", then "think of it as another parallel branch to MRP"). Both branches stay open; the
// route picks the one Reconciliation checks and the Sales Plan carries forward. Saved on the server, for everyone.
// user, 2026-10-14: "this route should be a prompt which redirects to Article module or MRP module after the department
// plan is done and reviewed, it should be a redirection for the user to click on" - the choice is made at the end of
// Final Results (RoutePrompt); the branch pages only say which branch is in use.
const API = '/api/planning/art-nm/settings'
const ROUTES = [
  ['mrp', 'MRP', '/mrp-plan/import', 'Split the department plan over MRP price points: Buyer’s Input → Re-apportionment → Plan Output → Display Type.'],
  ['article', 'Article Name', '/art-plan/import', 'Split the department plan over article names: Buyer’s Input (Art Nm Cont %) → Plan Output, promote to the MRP stage when ready.'],
]

export function useRoute() {
  const [st, setSt] = useState(null)
  useEffect(() => {
    fetch(API).then(r => (r.ok ? r.json() : null)).catch(() => null).then(d => setSt(d || { route: 'mrp', grain: 'cluster' }))
  }, [])
  const save = patch => {
    setSt(s => ({ ...s, ...patch }))
    return fetch(API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) }).catch(() => {})
  }
  return [st, save]
}

// the branch pages: which branch the Sales Plan runs on, and where it is chosen
export default function RouteBar({ here }) {
  const [st] = useRoute()
  const nav = useNavigate()
  if (!st) return null
  const on = ROUTES.find(r => r[0] === st.route) || ROUTES[0]
  return (
    <div data-no-undo style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 14, fontSize: 12 }}>
      <span style={{ color: st.route === here ? theme.success : theme.warning, fontWeight: 600 }}>
        {st.route === here ? `The Sales Plan runs on this branch (${on[1]})` : `The Sales Plan runs on the ${on[1]} branch - this one is for reference`}
      </span>
      <button type="button" onClick={() => nav('/department-plan/final-results#route')} style={{ all: 'unset', cursor: 'pointer', color: theme.primary, textDecoration: 'underline' }}>
        Choose the branch at the end of Final Results →
      </button>
    </div>
  )
}

// Final Results, after the department plan is reviewed: pick the next module - saves the route and goes there
export function RoutePrompt() {
  const [st, save] = useRoute()
  const nav = useNavigate()
  const [busy, setBusy] = useState('')
  useEffect(() => { if (window.location.hash === '#route') document.getElementById('route')?.scrollIntoView({ behavior: 'smooth' }) }, [st])
  if (!st) return null
  const go = async ([k, , to]) => {
    setBusy(k)
    if (st.route !== k) await save({ route: k })
    nav(to)
  }
  return (
    <div id="route" data-no-undo style={{ marginTop: 18, background: theme.surface, border: `1px solid ${theme.border}`, borderRadius: 12, padding: '16px 20px' }}>
      <div style={{ fontSize: 14, fontWeight: 700 }}>Department plan reviewed? Take it to the next stage</div>
      <div style={{ fontSize: 12, color: theme.textMuted, margin: '3px 0 12px' }}>
        Pick the branch the Sales Plan runs on - it opens that module. Now: <b style={{ color: theme.textPrimary }}>{(ROUTES.find(r => r[0] === st.route) || ROUTES[0])[1]}</b>.
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {ROUTES.map(r => {
          const cur = st.route === r[0]
          return (
            <button key={r[0]} type="button" disabled={!!busy} onClick={() => go(r)} style={{
              flex: '1 1 300px', textAlign: 'left', cursor: 'pointer', padding: '12px 14px', borderRadius: 10,
              border: `1.5px solid ${cur ? theme.primary : theme.border}`, background: cur ? alpha(theme.primary, '0d') : theme.surface }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: theme.textPrimary }}>
                {busy === r[0] ? 'Opening…' : `${r[1]} plan →`}{cur && <span style={{ marginLeft: 8, fontSize: 11, color: theme.success }}>in use</span>}
              </div>
              <div style={{ fontSize: 12, color: theme.textMuted, marginTop: 3 }}>{r[3]}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
