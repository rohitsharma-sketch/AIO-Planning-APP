// The saved plan versions ("iterations") shared by the header picker, Final Results' version bar and the Home tiles
// (user, 2026-10-14: "give me the same features as this button [BIS's iteration picker] ... and i want the saved plans
// to be highlighted here as a tile so that i can easily view the plan and compare it with the new iteration").
// 'sp-version' = a version was opened (detail: the version, or null = the live plan); 'sp-versions' = the list changed.
export const API = '/api/planning/plan-versions'
const OPEN = 'sp.fr.version'          // HierarchyView's key for Final Results (store 'sp.fr')
const CUR = 'sp.fr.version.current'   // the version Save writes to

export async function call(url, body) {
  const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined)
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(j.detail || `HTTP ${r.status}`)
  return j
}

const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k) || ''; localStorage.setItem(k, v) } catch { return '' } }
export const openVersionId = () => ls(OPEN)
export const saveTargetId = () => ls(CUR)
export const keepSaveTarget = id => ls(CUR, id)

export function openPlanVersion(v) {
  ls(OPEN, v ? v.id : '')
  if (v) keepSaveTarget(v.id)
  window.dispatchEvent(new CustomEvent('sp-version', { detail: v || null }))
  call(`${API}/open`, { id: v ? v.id : '' }).catch(() => {})
}

export const versionsChanged = () => window.dispatchEvent(new Event('sp-versions'))

// the Final Results layout (Rows + Filters) kept with a version saved from outside Final Results
export function currentView() {
  try {
    const levels = JSON.parse(localStorage.getItem('sp.fr.hierarchy') || 'null')
    const filters = JSON.parse(localStorage.getItem('sp.fr.filters') || '{}')
    return levels ? { levels, filters } : undefined
  } catch { return undefined }
}

export const when = s => {
  if (!s) return ''
  const d = new Date(s)
  return isNaN(d) ? s : `${d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}, ${d.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}`
}
